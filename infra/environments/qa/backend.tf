terraform {
  backend "s3" {
    bucket         = "qgi-infra-state-928648269104"
    key            = "qa/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "qgi-infra-state-lock"
    encrypt        = true
  }
}
