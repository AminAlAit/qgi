.PHONY: all fmt fmt-check validate plan-staging plan-qa plan-prod

all: fmt-check validate

fmt:
	terraform fmt -recursive .

fmt-check:
	terraform fmt -check -recursive .

validate:
	terraform -chdir=management init -backend=false
	terraform -chdir=management validate
	terraform -chdir=environments/staging init -backend=false
	terraform -chdir=environments/staging validate
	terraform -chdir=environments/qa init -backend=false
	terraform -chdir=environments/qa validate
	terraform -chdir=environments/prod init -backend=false
	terraform -chdir=environments/prod validate

plan-staging:
	terraform -chdir=environments/staging plan

plan-qa:
	terraform -chdir=environments/qa plan

plan-prod:
	terraform -chdir=environments/prod plan
