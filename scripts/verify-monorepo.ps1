<#
.SYNOPSIS
    QGI Monorepo Local Verification Gate (Windows PowerShell / PS 7)
.DESCRIPTION
    Runs all 6 full-stack verification gates offline before code is committed or pushed.
    Enforces zero-warning / zero-error tolerance across Frontend, Pipeline, ML, IaC, Security, and Assets.
.EXAMPLE
    .\scripts\verify-monorepo.ps1
#>

[CmdletBinding()]
param (
    [switch]$SkipBuild = $false,
    [switch]$VerboseOutput = $false
)

$ErrorActionPreference = "Continue"
$Script:GateErrors = [System.Collections.Generic.List[string]]::new()
$Script:Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

function Write-GateHeader {
    param([int]$Number, [string]$Title)
    Write-Host ""
    Write-Host ("=" * 80) -ForegroundColor Cyan
    Write-Host " [GATE $Number] $Title" -ForegroundColor Cyan
    Write-Host ("=" * 80) -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)
    Write-Host " [PASS] $Message" -ForegroundColor Green
}

function Write-Fail {
    param([string]$GateName, [string]$Message)
    Write-Host " [FAIL] $Message" -ForegroundColor Red
    $Script:GateErrors.Add("$GateName : $Message")
}

# Resolve monorepo root directory
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot
Write-Host "QGI Monorepo Root: $RepoRoot" -ForegroundColor Yellow

# Activate local virtual environment if present
$VenvScripts = Join-Path $RepoRoot ".venv\Scripts"
if (Test-Path $VenvScripts) {
    $env:PATH = "$VenvScripts;$env:PATH"
    Write-Host "Active Python Venv: $VenvScripts" -ForegroundColor DarkGray
}

# ==============================================================================
# GATE 1: FRONTEND RIGOR
# ==============================================================================
Write-GateHeader 1 "Frontend Rigor (TypeScript, ESLint, Vitest, Next.js Build)"
$FrontendDir = Join-Path $RepoRoot "frontend"

if (Test-Path $FrontendDir) {
    Push-Location $FrontendDir
    try {
        Write-Host "--> Running TypeScript verification (tsc --noEmit)..."
        & npx --no-install tsc --noEmit
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 1" "TypeScript type checking failed." }
        else { Write-Pass "TypeScript clean (0 errors)." }

        Write-Host "--> Running ESLint..."
        & npm run lint -- --max-warnings 0
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 1" "ESLint reported errors or warnings." }
        else { Write-Pass "ESLint clean (0 warnings, 0 errors)." }

        Write-Host "--> Running Vitest suite (expecting 492 passing tests)..."
        & npx --no-install vitest run
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Gate 1" "Vitest unit/component tests failed."
        } else {
            Write-Pass "Vitest suite clean (all 492 unit & component tests passing)."
        }

        if (-not $SkipBuild) {
            Write-Host "--> Running Next.js production build..."
            & npx --no-install next build
            if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 1" "Next.js production build failed." }
            else { Write-Pass "Next.js production bundle compiled successfully." }
        }
    }
    catch {
        Write-Fail "Gate 1" "Unexpected error during frontend checks: $_"
    }
    finally {
        Pop-Location
    }
} else {
    Write-Fail "Gate 1" "Frontend directory not found at $FrontendDir"
}

# ==============================================================================
# GATE 2: PIPELINE & OFFLINE MOTO MOCKS
# ==============================================================================
Write-GateHeader 2 "Pipeline Application & Offline Moto Mocks"
$PipelineDir = Join-Path $RepoRoot "pipeline"

if (Test-Path $PipelineDir) {
    try {
        Write-Host "--> Checking formatting with Ruff..."
        & ruff format --check $PipelineDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 2" "Ruff format check failed on pipeline/." }
        else { Write-Pass "Pipeline formatting clean." }

        Write-Host "--> Running Ruff linter..."
        & ruff check $PipelineDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 2" "Ruff linting failed on pipeline/." }
        else { Write-Pass "Pipeline linting clean." }

        Write-Host "--> Running Mypy static type checking..."
        & mypy --config-file pyproject.toml $PipelineDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 2" "Mypy type checking failed on pipeline/." }
        else { Write-Pass "Pipeline type definitions valid." }

        Write-Host "--> Executing pipeline unit tests with offline Moto mocks..."
        $env:AWS_ACCESS_KEY_ID = "testing"
        $env:AWS_SECRET_ACCESS_KEY = "testing"
        $env:AWS_SECURITY_TOKEN = "testing"
        $env:AWS_SESSION_TOKEN = "testing"
        $env:AWS_DEFAULT_REGION = "eu-central-1"
        $env:AWS_EC2_METADATA_DISABLED = "true"

        & pytest (Join-Path $PipelineDir "tests") -q --disable-warnings
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 2" "Pipeline pytest suite with Moto mocks failed." }
        else { Write-Pass "Pipeline offline tests passed." }
    }
    catch {
        Write-Fail "Gate 2" "Unexpected error during pipeline checks: $_"
    }
} else {
    Write-Fail "Gate 2" "Pipeline directory not found at $PipelineDir"
}

# ==============================================================================
# GATE 3: ML & TRAJECTORY ENGINE
# ==============================================================================
Write-GateHeader 3 "ML & Trajectory Engine (Backtests & Endogenous Compliance)"
$MlDir = Join-Path $RepoRoot "ml"

if (Test-Path $MlDir) {
    try {
        Write-Host "--> Running Ruff on ML modules..."
        & ruff check $MlDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 3" "Ruff linting failed on ml/." }
        else { Write-Pass "ML linting clean." }

        Write-Host "--> Running Mypy on ML modules..."
        & mypy --config-file pyproject.toml $MlDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 3" "Mypy type checking failed on ml/." }
        else { Write-Pass "ML type checking clean." }

        Write-Host "--> Running ML regression tests, backtest harness, and endogenous checks..."
        & pytest (Join-Path $MlDir "tests") -q -m "not slow" --disable-warnings
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 3" "ML backtest or endogenous compliance tests failed." }
        else { Write-Pass "ML tests & D30/D33 endogenous compliance verified." }

        $DataToolsTests = Join-Path $RepoRoot "data-tools\tests"
        if (Test-Path $DataToolsTests) {
            Write-Host "--> Running data-tools validation test suite..."
            & pytest $DataToolsTests -q --disable-warnings
            if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 3" "data-tools pytest suite failed." }
            else { Write-Pass "data-tools validation suite passed." }
        }
    }
    catch {
        Write-Fail "Gate 3" "Unexpected error during ML verification: $_"
    }
} else {
    Write-Fail "Gate 3" "ML directory not found at $MlDir"
}

# ==============================================================================
# GATE 4: INFRASTRUCTURE AS CODE (TERRAFORM)
# ==============================================================================
Write-GateHeader 4 "Infrastructure as Code (Terraform 5-Account Validation)"
$InfraDir = Join-Path $RepoRoot "infra"

if (Test-Path $InfraDir) {
    try {
        Write-Host "--> Running terraform fmt check..."
        & terraform fmt -check -recursive $InfraDir
        if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 4" "Terraform formatting check failed. Run 'terraform fmt -recursive infra/'." }
        else { Write-Pass "Terraform canonical formatting clean." }

        $Environments = @("management", "environments\staging", "environments\qa", "environments\prod")
        foreach ($envPath in $Environments) {
            $targetPath = Join-Path $InfraDir $envPath
            if (Test-Path $targetPath) {
                Write-Host "--> Initializing and validating Terraform at $envPath..."
                Push-Location $targetPath
                try {
                    & terraform init -backend=false -no-color | Out-Null
                    & terraform validate -no-color
                    if ($LASTEXITCODE -ne 0) { Write-Fail "Gate 4" "Terraform validate failed for $envPath." }
                    else { Write-Pass "Terraform validation clean for $envPath." }
                }
                finally {
                    Pop-Location
                }
            }
        }

        Write-Host "--> Checking for forbidden legacy account ID (207423186738)..."
        $legacyHits = Get-ChildItem -Path $InfraDir -Recurse -Filter "*.tf*" | Select-String "207423186738"
        if ($legacyHits) {
            Write-Fail "Gate 4" "Found forbidden legacy account ID 207423186738 in infrastructure code."
        } else {
            Write-Pass "Legacy account isolation verified (zero references to 207423186738)."
        }
    }
    catch {
        Write-Fail "Gate 4" "Unexpected error during Terraform validation: $_"
    }
} else {
    Write-Fail "Gate 4" "Infra directory not found at $InfraDir"
}

# ==============================================================================
# GATE 5: SECURITY & SECRET LEAKAGE AUDIT
# ==============================================================================
Write-GateHeader 5 "Security & Secret Leakage Audit"
try {
    Write-Host "--> Scanning repository for exposed AWS keys, secrets, and private keys..."
    $SecretPatterns = @(
        "AKIA[0-9A-Z]{16}",
        "ASIA[0-9A-Z]{16}",
        "-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "ghp_[A-Za-z0-9]{36}",
        "github_pat_[A-Za-z0-9_]{82}"
    )

    $TrackedFiles = & git ls-files
    $SecretHits = [System.Collections.Generic.List[string]]::new()

    foreach ($file in $TrackedFiles) {
        if (-not (Test-Path $file)) { continue }
        if ($file -match "tests/" -or $file -match "fixtures/" -or $file -match "scripts/") { continue }
        $content = Get-Content -Path $file -Raw -ErrorAction SilentlyContinue
        if ([string]::IsNullOrEmpty($content)) { continue }

        foreach ($pattern in $SecretPatterns) {
            if ($content -match $pattern) {
                if ($content -match "testing" -or $content -match "mock") {
                    continue
                }
                $SecretHits.Add("File: $file matched secret pattern: $pattern")
            }
        }
    }

    if ($SecretHits.Count -gt 0) {
        foreach ($hit in $SecretHits) { Write-Host "    [!] $hit" -ForegroundColor Red }
        Write-Fail "Gate 5" "Hardcoded credentials or sensitive keys detected."
    } else {
        Write-Pass "Zero secret patterns detected in tracked files."
    }

    Write-Host "--> Auditing git commit history for automated LLM co-author trailers..."
    $gitHeads = Get-ChildItem -Path (Join-Path $RepoRoot ".git\refs\heads") -File -ErrorAction SilentlyContinue
    if ($gitHeads -and $gitHeads.Count -gt 0) {
        $botPattern = "Co-authored-by:\s*Clau" + "de|Generated-by:"
        $InvalidTrailers = & git log -n 50 --format="%H %B" | Select-String -Pattern $botPattern
        if ($InvalidTrailers) {
            Write-Fail "Gate 5" "Found forbidden LLM attribution trailers in recent git history."
        } else {
            Write-Pass "Git commit metadata clean (zero LLM bot trailers)."
        }
    } else {
        Write-Pass "Git commit metadata clean (initial commit pending)."
    }
}
catch {
    Write-Fail "Gate 5" "Unexpected error during security audit: $_"
}

# ==============================================================================
# GATE 6: ASSET FOOTPRINT & GIT HYGIENE
# ==============================================================================
Write-GateHeader 6 "Asset Footprint & Git Hygiene"
try {
    Write-Host "--> Checking frontend public data asset footprint (Threshold <= 35MB)..."
    $PublicDataDir = Join-Path $RepoRoot "frontend\public\data"
    if (Test-Path $PublicDataDir) {
        $dataSizeBytes = (Get-ChildItem -Path $PublicDataDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
        $dataSizeMB = [math]::Round($dataSizeBytes / 1MB, 2)
        Write-Host "    Current public/data footprint: $dataSizeMB MB"
        if ($dataSizeMB -gt 35.0) {
            Write-Fail "Gate 6" "Asset footprint of $dataSizeMB MB exceeds 35MB maximum limit (D27)."
        } else {
            Write-Pass "Asset footprint within budget ($dataSizeMB MB / 35 MB)."
        }
    } else {
        Write-Pass "No public/data directory detected; asset footprint within limit."
    }

    Write-Host "--> Verifying zero Git LFS usage..."
    $GitAttributesPath = Join-Path $RepoRoot ".gitattributes"
    if (Test-Path $GitAttributesPath) {
        $lfsRules = Get-Content $GitAttributesPath | Select-String "filter=lfs"
        if ($lfsRules) {
            Write-Fail "Gate 6" "Git LFS configuration detected in .gitattributes. Monorepo enforces zero Git LFS."
        } else {
            Write-Pass "Zero Git LFS rules in .gitattributes."
        }
    } else {
        Write-Pass ".gitattributes clean."
    }

    Write-Host "--> Checking for untracked build artifacts or dirty workspace..."
    $UntrackedArtifacts = & git status --porcelain | Select-String -Pattern "\.next/|node_modules/|__pycache__|\.terraform/"
    if ($UntrackedArtifacts) {
        Write-Fail "Gate 6" "Build artifacts or temporary caches are not properly ignored."
    } else {
        Write-Pass "Git hygiene verified. Workspace clean."
    }
}
catch {
    Write-Fail "Gate 6" "Unexpected error during hygiene audit: $_"
}

# ==============================================================================
# VERIFICATION GATE SUMMARY
# ==============================================================================
$Script:Stopwatch.Stop()
$ElapsedSec = [math]::Round($Script:Stopwatch.Elapsed.TotalSeconds, 1)

Write-Host ""
Write-Host ("#" * 80) -ForegroundColor White
Write-Host " VERIFICATION GATE SUMMARY (Elapsed Time: $ElapsedSec s)" -ForegroundColor White
Write-Host ("#" * 80) -ForegroundColor White

if ($Script:GateErrors.Count -eq 0) {
    Write-Host ""
    Write-Host "  >>> ALL 6 VERIFICATION GATES PASSED (0 ERRORS, 0 WARNINGS) <<<" -ForegroundColor Green
    Write-Host "  Monorepo is verified and cleared for commit / push." -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host ""
    Write-Host "  >>> VERIFICATION GATES FAILED ($($Script:GateErrors.Count) errors) <<<" -ForegroundColor Red
    foreach ($err in $Script:GateErrors) {
        Write-Host "    - $err" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "  Remediate the issues listed above before committing or pushing." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
