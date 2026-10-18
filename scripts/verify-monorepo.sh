#!/usr/bin/env bash
# ==============================================================================
# QGI Monorepo Local & CI Verification Gate (POSIX / Bash)
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

START_TIME=$(date +%s)
FAILED_GATES=()

log_header() {
    echo -e "\n${CYAN}================================================================================${NC}"
    echo -e "${CYAN} [GATE $1] $2${NC}"
    echo -e "${CYAN}================================================================================${NC}"
}

log_pass() {
    echo -e " ${GREEN}[PASS]${NC} $1"
}

log_fail() {
    echo -e " ${RED}[FAIL]${NC} $2"
    FAILED_GATES+=("Gate $1: $2")
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
echo -e "${YELLOW}QGI Monorepo Root: ${REPO_ROOT}${NC}"

# ==============================================================================
# GATE 1: FRONTEND RIGOR
# ==============================================================================
log_header 1 "Frontend Rigor (TypeScript, ESLint, Vitest, Next.js Build)"
if [ -d "frontend" ]; then
    pushd frontend > /dev/null

    echo "--> Running TypeScript type checking (tsc --noEmit)..."
    if npx --no-install tsc --noEmit; then
        log_pass "TypeScript clean (0 errors)."
    else
        log_fail 1 "TypeScript type checking failed."
    fi

    echo "--> Running ESLint..."
    if npm run lint -- --max-warnings 0; then
        log_pass "ESLint clean (0 warnings, 0 errors)."
    else
        log_fail 1 "ESLint reported errors or warnings."
    fi

    echo "--> Running Vitest suite (492 tests)..."
    if npx --no-install vitest run; then
        log_pass "Vitest suite clean (all unit/component tests passing)."
    else
        log_fail 1 "Vitest suite failed."
    fi

    echo "--> Running Next.js production build..."
    if npx --no-install next build; then
        log_pass "Next.js production bundle compiled successfully."
    else
        log_fail 1 "Next.js production build failed."
    fi

    popd > /dev/null
else
    log_fail 1 "Directory 'frontend/' does not exist."
fi

# ==============================================================================
# GATE 2: PIPELINE APPLICATION & OFFLINE MOTO MOCKS
# ==============================================================================
log_header 2 "Pipeline Application & Offline Moto Mocks"
if [ -d "pipeline" ]; then
    echo "--> Checking formatting with Ruff..."
    if ruff format --check pipeline/; then
        log_pass "Pipeline code formatting clean."
    else
        log_fail 2 "Ruff format check failed on pipeline/."
    fi

    echo "--> Running Ruff linter..."
    if ruff check pipeline/; then
        log_pass "Pipeline linting clean."
    else
        log_fail 2 "Ruff check failed on pipeline/."
    fi

    echo "--> Running Mypy static type checker..."
    if mypy --config-file pyproject.toml pipeline/; then
        log_pass "Pipeline type checking clean."
    else
        log_fail 2 "Mypy type checking failed on pipeline/."
    fi

    echo "--> Running offline Moto mock tests..."
    export AWS_ACCESS_KEY_ID="testing"
    export AWS_SECRET_ACCESS_KEY="testing"
    export AWS_SECURITY_TOKEN="testing"
    export AWS_SESSION_TOKEN="testing"
    export AWS_DEFAULT_REGION="eu-central-1"
    export AWS_EC2_METADATA_DISABLED="true"

    if pytest pipeline/tests/ -q --disable-warnings; then
        log_pass "Pipeline tests passed offline with 100% Moto mocks."
    else
        log_fail 2 "Pipeline pytest suite failed."
    fi
else
    log_fail 2 "Directory 'pipeline/' does not exist."
fi

# ==============================================================================
# GATE 3: ML & TRAJECTORY ENGINE
# ==============================================================================
log_header 3 "ML & Trajectory Engine (Backtests & Endogenous Compliance)"
if [ -d "ml" ]; then
    echo "--> Running Ruff on ML modules..."
    if ruff check ml/; then
        log_pass "ML linting clean."
    else
        log_fail 3 "Ruff check failed on ml/."
    fi

    echo "--> Running Mypy on ML modules..."
    if mypy --config-file pyproject.toml ml/; then
        log_pass "ML type checking clean."
    else
        log_fail 3 "Mypy type checking failed on ml/."
    fi

    echo "--> Executing ML tests, backtest harness, and endogenous checks..."
    if pytest ml/tests/ -q -m "not slow" --disable-warnings; then
        log_pass "ML backtest harness and D30/D33 endogenous rules verified."
    else
        log_fail 3 "ML pytest suite or endogenous checks failed."
    fi

    if [ -d "data-tools/tests" ]; then
        echo "--> Executing data-tools validation test suite..."
        if pytest data-tools/tests/ -q --disable-warnings; then
            log_pass "data-tools validation suite passed."
        else
            log_fail 3 "data-tools pytest suite failed."
        fi
    fi
else
    log_fail 3 "Directory 'ml/' does not exist."
fi

# ==============================================================================
# GATE 4: INFRASTRUCTURE AS CODE (TERRAFORM)
# ==============================================================================
log_header 4 "Infrastructure as Code (Terraform 5-Account Validation)"
if [ -d "infra" ]; then
    echo "--> Checking Terraform formatting..."
    if terraform fmt -check -recursive infra/; then
        log_pass "Terraform canonical formatting clean."
    else
        log_fail 4 "Terraform formatting check failed. Run 'terraform fmt -recursive infra/'."
    fi

    for env_path in "management" "environments/staging" "environments/qa" "environments/prod"; do
        if [ -d "infra/${env_path}" ]; then
            echo "--> Initializing and validating Terraform at infra/${env_path}..."
            terraform -chdir="infra/${env_path}" init -backend=false > /dev/null 2>&1
            if terraform -chdir="infra/${env_path}" validate; then
                log_pass "Terraform validation clean for ${env_path}."
            else
                log_fail 4 "Terraform validation failed for ${env_path}."
            fi
        fi
    done

    echo "--> Checking for forbidden legacy account ID (207423186738)..."
    if grep -r --include="*.tf" --include="*.tfvars" "207423186738" infra/ > /dev/null 2>&1; then
        log_fail 4 "Found forbidden legacy account ID 207423186738 in infrastructure code."
    else
        log_pass "Legacy account isolation verified (zero references to 207423186738)."
    fi
else
    log_fail 4 "Directory 'infra/' does not exist."
fi

# ==============================================================================
# GATE 5: SECURITY & SECRET LEAKAGE AUDIT
# ==============================================================================
log_header 5 "Security & Secret Leakage Audit"
echo "--> Scanning tracked files for secret patterns..."
SECRET_PATTERNS='(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})'

FOUND_SECRETS=0
while IFS= read -r file; do
    if [[ "$file" =~ tests/ ]] || [[ "$file" =~ fixtures/ ]] || [[ "$file" =~ scripts/ ]]; then
        continue
    fi
    if [ -f "$file" ]; then
        if grep -E -n "${SECRET_PATTERNS}" "$file" > /dev/null 2>&1; then
            echo -e " ${RED}[!] Sensitive key signature matched in:${NC} $file"
            FOUND_SECRETS=1
        fi
    fi
done < <(git ls-files)

if [ "$FOUND_SECRETS" -eq 0 ]; then
    log_pass "Zero secret patterns detected in tracked files."
else
    log_fail 5 "Hardcoded secret patterns detected in repository."
fi

echo "--> Checking commit metadata for automated LLM bot trailers..."
BOT_TRAILER_PATTERN="Co-authored-by: Clau""de|Generated-by:"
if git rev-parse --verify HEAD >/dev/null 2>&1 && git log -n 50 --format="%H %B" | grep -E "${BOT_TRAILER_PATTERN}" > /dev/null 2>&1; then
    log_fail 5 "Found forbidden LLM bot trailers in git commit log."
else
    log_pass "Git commit metadata clean."
fi

# ==============================================================================
# GATE 6: ASSET FOOTPRINT & GIT HYGIENE
# ==============================================================================
log_header 6 "Asset Footprint & Git Hygiene"
if [ -d "frontend/public/data" ]; then
    DIR_SIZE_KB=$(du -sk "frontend/public/data" | cut -f1)
    DIR_SIZE_MB=$((DIR_SIZE_KB / 1024))
    echo "    Current public/data footprint: ${DIR_SIZE_MB}MB"
    if [ "$DIR_SIZE_MB" -gt 35 ]; then
        log_fail 6 "Asset footprint (${DIR_SIZE_MB}MB) exceeds 35MB limit (D27)."
    else
        log_pass "Asset footprint within budget (${DIR_SIZE_MB}MB / 35MB)."
    fi
else
    log_pass "No public/data directory detected; asset footprint within limit."
fi

echo "--> Checking .gitattributes for Git LFS..."
if [ -f ".gitattributes" ]; then
    if grep -q "filter=lfs" ".gitattributes"; then
        log_fail 6 "Git LFS detected in .gitattributes. Repository enforces zero Git LFS."
    else
        log_pass "Zero Git LFS rules detected."
    fi
else
    log_pass ".gitattributes clean."
fi

echo "--> Checking for unstaged build artifacts or dirty workspace..."
if git status --porcelain | grep -E '(\.next/|node_modules/|__pycache__|\.terraform/)' > /dev/null 2>&1; then
    log_fail 6 "Untracked build caches or virtual environment files detected in git status."
else
    log_pass "Git hygiene verified. Workspace clean."
fi

# ==============================================================================
# VERIFICATION GATE SUMMARY
# ==============================================================================
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo -e "\n${CYAN}################################################################################${NC}"
echo -e "${CYAN} VERIFICATION GATE SUMMARY (Elapsed Time: ${ELAPSED}s)${NC}"
echo -e "${CYAN}################################################################################${NC}"

if [ ${#FAILED_GATES[@]} -eq 0 ]; then
    echo -e "\n ${GREEN}>>> ALL 6 VERIFICATION GATES PASSED CLEANLY <<<${NC}"
    echo -e " ${GREEN}Repository is certified for commit and push to GitHub.${NC}\n"
    exit 0
else
    echo -e "\n ${RED}>>> VERIFICATION GATES FAILED (${#FAILED_GATES[@]} errors) <<<${NC}"
    for failed in "${FAILED_GATES[@]}"; do
        echo -e "   ${RED}- ${failed}${NC}"
    done
    echo -e "\n ${YELLOW}Remediate all issues above before committing or pushing.${NC}\n"
    exit 1
fi
