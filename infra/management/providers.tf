provider "aws" {
  region = "eu-central-1"

  default_tags {
    tags = {
      Project     = "qgi"
      Environment = "production"
      ManagedBy   = "terraform"
      Owner       = "amin.al-ait"
    }
  }
}
