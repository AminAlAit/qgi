# ---------------------------------------------------------------------------
# Identity Center — account assignments for Amin
#
# Gives Amin AdministratorAccess to all active accounts so he can
# inspect resources (Step Functions, CloudWatch, Batch) from the SSO portal.
# qgi-prod already had this assignment — adding staging and qa.
# ---------------------------------------------------------------------------

locals {
  sso_instance_arn     = "arn:aws:sso:::instance/ssoins-6987d6075367cce2"
  admin_permission_set = "arn:aws:sso:::permissionSet/ssoins-6987d6075367cce2/ps-e02aa732751e3389"
  amin_user_id         = "836498c2-9071-70e6-6b1f-e71a5d79536c"
}

resource "aws_ssoadmin_account_assignment" "amin_staging" {
  instance_arn       = local.sso_instance_arn
  permission_set_arn = local.admin_permission_set
  principal_id       = local.amin_user_id
  principal_type     = "USER"
  target_id          = var.staging_account_id # qgi-staging
  target_type        = "AWS_ACCOUNT"
}

resource "aws_ssoadmin_account_assignment" "amin_qa" {
  instance_arn       = local.sso_instance_arn
  permission_set_arn = local.admin_permission_set
  principal_id       = local.amin_user_id
  principal_type     = "USER"
  target_id          = var.qa_account_id # qgi-qa
  target_type        = "AWS_ACCOUNT"
}

