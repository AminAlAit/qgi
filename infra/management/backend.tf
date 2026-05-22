terraform {
  backend "s3" {
    bucket         = "qgi-aws-tf-state-783811616921"
    key            = "management/terraform.tfstate"
    region         = "eu-central-1"
    dynamodb_table = "qgi-aws-tf-state-lock"
    encrypt        = true
  }
}
