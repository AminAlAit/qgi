<#
.SYNOPSIS
    Local rebuild + push of the qgi-recipe-fleet image to staging ECR (#967).

.DESCRIPTION
    Mirror of .github/workflows/ecr-push.yml's recipe-fleet job. Use when the
    GHA workflow is quota-rejected (stepCount:0 since 2026-05-28) and a fresh
    image must be in ECR before wave-N can resume / re-canary fires.

    What this script does (in order):
      1. Verifies Docker Desktop + AWS CLI are available and you are logged in
         to STAGING (account 771606957899).
      2. Checks both qgi-pipeline and qgi-ml are on `main` with a clean tree
         (refuses to build a stale image).
      3. Captures both repo SHAs for the LABEL traceability stamp.
      4. Logs the Docker client into staging ECR via aws ecr get-login-password.
      5. Builds the recipe-fleet image with buildx (linux/arm64 via QEMU), with
         the qgi-ml repo passed as a named build context.
      6. Pushes both tags ({short_sha} + latest).
      7. Verifies the push by querying ECR for the new digest.

.PARAMETER QgiPipelineRoot
    Path to qgi-pipeline working copy. Default: parent of this script.

.PARAMETER QgiMlRoot
    Path to qgi-ml working copy. Default: ../qgi-ml relative to QgiPipelineRoot.

.PARAMETER SkipDirtyCheck
    Skip the "must be on main + clean" guard. Default: false. Use ONLY when
    you've verified intentionally-uncommitted state is safe to bake (e.g. a
    hot-patch the founder explicitly wants in the image).

.PARAMETER DryRun
    Print the docker buildx command without executing it.

.EXAMPLE
    PS> .\rebuild-and-push-local.ps1

.NOTES
    Requires:
      - Docker Desktop running (with buildx + QEMU for arm64-on-amd64 emulation)
      - AWS CLI v2 with active SSO session to staging (771606957899)
      - Both qgi-pipeline and qgi-ml checked out locally on `main`

    Founder cost approval required per session for AWS-touching ops
    (AWS cost control policy). ECR Put cost:
    ~$0.10 per GB stored / month + ~$0.09 / GB out. The image is ~2 GB
    (xgboost + shap + numpy + pandas + entrypoint + vendored scripts).
#>

[CmdletBinding()]
param(
    [string]$QgiPipelineRoot,
    [string]$QgiMlRoot,
    [switch]$SkipDirtyCheck,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# ─── 0. Resolve paths ─────────────────────────────────────────────────────
if (-not $QgiPipelineRoot) {
    $QgiPipelineRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
}
if (-not $QgiMlRoot) {
    $QgiMlRoot = (Resolve-Path "$QgiPipelineRoot\..\qgi-ml").Path
}

Write-Host "[paths] qgi-pipeline = $QgiPipelineRoot" -ForegroundColor Cyan
Write-Host "[paths] qgi-ml       = $QgiMlRoot" -ForegroundColor Cyan

if (-not (Test-Path "$QgiPipelineRoot\batch\recipe-fleet\Dockerfile")) {
    throw "Dockerfile not found at $QgiPipelineRoot\batch\recipe-fleet\Dockerfile"
}
if (-not (Test-Path "$QgiMlRoot\scripts\run_f_ml_1_poc.py")) {
    throw "qgi-ml walk driver not found at $QgiMlRoot\scripts\run_f_ml_1_poc.py -- wrong QgiMlRoot?"
}

# ─── 1. Pre-flight: Docker + AWS CLI + SSO session ────────────────────────
Write-Host "`n[preflight] Checking Docker Desktop..." -ForegroundColor Cyan
$null = docker info --format '{{.ServerVersion}}' 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running. Start it before re-running this script."
}

Write-Host "[preflight] Checking AWS CLI + SSO session..." -ForegroundColor Cyan
# Capture raw output FIRST, then check exit code, then parse -- piping straight
# into ConvertFrom-Json shadows the AWS CLI's exit code with ConvertFrom-Json's
# (which is always 0 on success), and a non-JSON error string from the CLI would
# surface as a cryptic parse failure rather than the SSO-refresh hint.
# (QA PR #48 review N1.)
$callerRaw = aws sts get-caller-identity --output json 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "aws sts get-caller-identity failed. Refresh your SSO session (paste fresh staging creds).`nRaw output: $callerRaw"
}
$caller = $callerRaw | ConvertFrom-Json
$targetAccount = if ($env:AWS_ACCOUNT_ID) { $env:AWS_ACCOUNT_ID } else { "771606957899" }
if ($caller.Account -ne $targetAccount) {
    throw "Wrong AWS account: caller is in $($caller.Account); need target $targetAccount. Paste valid credentials."
}
Write-Host "[preflight] AWS account: $($caller.Account) -- OK" -ForegroundColor Green
Write-Host "[preflight] Caller arn: $($caller.Arn)" -ForegroundColor Gray

# ─── 2. Repo cleanliness check ────────────────────────────────────────────
function Test-RepoClean {
    param([string]$Path, [string]$Label)
    Push-Location $Path
    try {
        $branch = git rev-parse --abbrev-ref HEAD
        $dirty = git status --porcelain
        # Verify the upstream tracking branch exists BEFORE asking for the
        # ahead count. Without this, `git rev-list @{u}..HEAD 2>$null` would
        # silently emit an empty string for a repo with no upstream, the
        # ahead-check would pass, and we'd happily bake from a local-only
        # commit that was never pushed. (PR #48 review N3.)
        $upstreamRaw = git rev-parse --abbrev-ref "@{u}" 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "[$Label] no upstream tracking branch configured -- cannot confirm sync with origin. Raw: $upstreamRaw"
        }
        $ahead = git rev-list "@{u}..HEAD" --count
        if ($branch -ne "main") {
            throw "[$Label] branch is '$branch', not 'main'. Refusing to bake a feature branch into the image."
        }
        if ($dirty) {
            throw "[$Label] working tree is dirty:`n$dirty`nCommit/stash before rebuilding (or pass -SkipDirtyCheck)."
        }
        if ($ahead -and [int]$ahead -gt 0) {
            throw "[$Label] local main is $ahead commit(s) ahead of origin/main -- push first."
        }
        Write-Host "[$Label] clean on main, in sync with origin" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

if (-not $SkipDirtyCheck) {
    Test-RepoClean -Path $QgiPipelineRoot -Label "qgi-pipeline"
    Test-RepoClean -Path $QgiMlRoot       -Label "qgi-ml"
} else {
    Write-Host "[preflight] -SkipDirtyCheck set -- skipping repo cleanliness check (you take the blame for any drift)" -ForegroundColor Yellow
}

# ─── 3. Capture SHAs for traceability LABEL ──────────────────────────────
Push-Location $QgiPipelineRoot
$pipelineSha = (git rev-parse HEAD).Substring(0, 8)
Pop-Location
Push-Location $QgiMlRoot
$qgiMlSha = git rev-parse HEAD
$qgiMlShaShort = $qgiMlSha.Substring(0, 8)
Pop-Location

$ImageTag   = $pipelineSha
$EcrRegistry = "$targetAccount.dkr.ecr.eu-central-1.amazonaws.com"
$ImageRepo  = "$EcrRegistry/qgi-recipe-fleet"

Write-Host "`n[stamp] qgi-pipeline HEAD = $pipelineSha" -ForegroundColor Cyan
Write-Host "[stamp] qgi-ml HEAD       = $qgiMlSha" -ForegroundColor Cyan
Write-Host "[stamp] image tag         = $ImageTag" -ForegroundColor Cyan

# ─── 4. ECR docker login ─────────────────────────────────────────────────
Write-Host "`n[login] Logging Docker client into ECR..." -ForegroundColor Cyan
$loginPwd = aws ecr get-login-password --region eu-central-1
if ($LASTEXITCODE -ne 0) { throw "aws ecr get-login-password failed" }
$loginPwd | docker login --username AWS --password-stdin $EcrRegistry
if ($LASTEXITCODE -ne 0) { throw "docker login to $EcrRegistry failed" }

# ─── 5. Buildx setup (one-time on a fresh machine, idempotent) ───────────
Write-Host "`n[buildx] Ensuring multi-platform builder is available..." -ForegroundColor Cyan
# Suppress stderr instead of merging (2>&1) -- PS 5.1's $ErrorActionPreference=Stop
# treats stderr from native exes as terminating errors even when the exe exits 0
# (the "NativeCommandError" trap). $LASTEXITCODE is the authoritative signal here.
# PS 5.1 NativeCommandError trap: 2>$null alone does NOT bypass the trap when a
# native exe emits ANY stderr with non-zero exit. Only try/catch swallows it
# cleanly. $LASTEXITCODE is the authoritative signal inside the try.
$builderExists = $true
try {
    docker buildx inspect qgi-recipe-fleet-builder 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { $builderExists = $false }
} catch {
    $builderExists = $false
}
if (-not $builderExists) {
    Write-Host "[buildx] Creating qgi-recipe-fleet-builder (one-time)..." -ForegroundColor Yellow
    docker buildx create --name qgi-recipe-fleet-builder --driver docker-container --bootstrap | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "docker buildx create failed" }
}
try {
    docker buildx use qgi-recipe-fleet-builder | Out-Null
} catch {
    throw "docker buildx use qgi-recipe-fleet-builder failed: $_"
}
if ($LASTEXITCODE -ne 0) { throw "docker buildx use qgi-recipe-fleet-builder failed (rc=$LASTEXITCODE)" }

# ─── 6. Build + push ─────────────────────────────────────────────────────
$BuildContextDir = Join-Path $QgiPipelineRoot "batch\recipe-fleet"
$buildArgs = @(
    "buildx", "build",
    "--platform", "linux/arm64",
    "--build-context", "qgi-ml=$QgiMlRoot",
    "--build-arg", "QGI_ML_SHA=$qgiMlSha",
    "-t", "${ImageRepo}:${ImageTag}",
    "-t", "${ImageRepo}:latest",
    "--push",
    $BuildContextDir
)

Write-Host "`n[build] docker $($buildArgs -join ' ')" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "[dry-run] not executing buildx -- re-run without -DryRun to push" -ForegroundColor Yellow
    return
}

& docker @buildArgs
if ($LASTEXITCODE -ne 0) { throw "docker buildx build failed" }

# ─── 7. Verify push ──────────────────────────────────────────────────────
Write-Host "`n[verify] Querying ECR for the freshly-pushed image..." -ForegroundColor Cyan
$descJson = aws ecr describe-images `
    --repository-name qgi-recipe-fleet `
    --image-ids "imageTag=$ImageTag" `
    --region eu-central-1 `
    --output json
if ($LASTEXITCODE -ne 0) { throw "ECR describe-images failed; the push may not have landed" }
$desc = $descJson | ConvertFrom-Json
$digest = $desc.imageDetails[0].imageDigest
$pushedAt = $desc.imageDetails[0].imagePushedAt
$sizeMb = [math]::Round($desc.imageDetails[0].imageSizeInBytes / 1MB, 1)

Write-Host "`n=== REBUILD COMPLETE ===" -ForegroundColor Green
Write-Host "Image:   ${ImageRepo}:${ImageTag}" -ForegroundColor Green
Write-Host "Latest:  ${ImageRepo}:latest" -ForegroundColor Green
Write-Host "Digest:  $digest" -ForegroundColor Green
Write-Host "Pushed:  $pushedAt" -ForegroundColor Green
Write-Host "Size:    $sizeMb MB" -ForegroundColor Green
Write-Host "qgi-ml:  $qgiMlSha" -ForegroundColor Gray
Write-Host "" -ForegroundColor Green
Write-Host "Next: fire §2.5 canary diff harness on technology_breakthrough." -ForegroundColor Cyan
Write-Host "      Confirm technology_breakthrough has NO pre-existing greedy-result.json" -ForegroundColor Cyan
Write-Host "      in S3 before triggering, or the resume guard skips the walk." -ForegroundColor Cyan
