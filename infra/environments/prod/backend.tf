terraform {
  backend "s3" {
    bucket         = "qgi-infra-state-297797204453"
    key            = "prod/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "qgi-infra-state-lock"
    encrypt        = true

    # #96: backend blocks can't use variables. If you're authenticated as
    # prod directly (prod SSO, CI OIDC role in prod), override at init time:
    #
    #   terraform init -reconfigure -backend-config='assume_role={}'
    #
    # See staging/backend.tf for full explanation.
    assume_role = {
      role_arn = "arn:aws:iam::297797204453:role/OrganizationAccountAccessRole"
    }
  }
}
