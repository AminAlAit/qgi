.PHONY: help verify test test-pipeline test-ml test-data test-frontend lint fmt validate-infra

help:
	@echo "QGI Monorepo Automation Targets:"
	@echo "  make verify          - Run full 6-gate offline verification suite"
	@echo "  make test            - Run all Python (pipeline, ml, data-tools) and Frontend unit tests"
	@echo "  make lint            - Run Ruff, Mypy, ESLint, and TypeScript checks"
	@echo "  make validate-infra  - Validate all 4 AWS Terraform environments offline"

verify:
	./scripts/verify-monorepo.sh

test: test-pipeline test-ml test-data test-frontend

test-pipeline:
	pytest pipeline/tests -q --disable-warnings

test-ml:
	pytest ml/tests -q -m "not slow" --disable-warnings

test-data:
	pytest data-tools/tests -q --disable-warnings

test-frontend:
	cd frontend && npx --no-install vitest run

lint:
	ruff format --check pipeline/
	ruff check pipeline/ ml/
	mypy --config-file pyproject.toml pipeline/ ml/
	cd frontend && npx --no-install tsc --noEmit && npm run lint -- --max-warnings 0

validate-infra:
	terraform fmt -check -recursive infra/
	terraform -chdir=infra/management init -backend=false && terraform -chdir=infra/management validate
	terraform -chdir=infra/environments/staging init -backend=false && terraform -chdir=infra/environments/staging validate
	terraform -chdir=infra/environments/qa init -backend=false && terraform -chdir=infra/environments/qa validate
	terraform -chdir=infra/environments/prod init -backend=false && terraform -chdir=infra/environments/prod validate
