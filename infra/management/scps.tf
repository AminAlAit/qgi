# Service Control Policies
# Applied to member accounts only (management account is exempt from SCPs by design).

locals {
  # Active pipeline member accounts subject to region-lock and CloudTrail-protect enforcement.
  member_account_ids = var.member_account_ids
}


# ---------------------------------------------------------------------------
# SCP 1 — Region restriction
# Deny all actions outside eu-central-1, except global services that must
# run in us-east-1 (IAM, STS, CloudFront, Route 53, Support, Budgets, etc.)
# ---------------------------------------------------------------------------
resource "aws_organizations_policy" "region_restriction" {
  name        = "region-restriction"
  description = "Deny actions outside eu-central-1 and us-east-1 (global services)"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyNonApprovedRegions"
        Effect   = "Deny"
        Action   = "*"
        Resource = "*"
        Condition = {
          StringNotEquals = {
            "aws:RequestedRegion" = ["eu-central-1", "us-east-1"]
          }
          BoolIfExists = {
            "aws:PrincipalIsAWSService" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_organizations_policy_attachment" "region_restriction" {
  for_each  = toset(local.member_account_ids)
  policy_id = aws_organizations_policy.region_restriction.id
  target_id = each.value
}

# ---------------------------------------------------------------------------
# SCP 2 — Prevent CloudTrail disable
# Protects audit logging from being silenced by any principal in member accounts.
# ---------------------------------------------------------------------------
resource "aws_organizations_policy" "protect_cloudtrail" {
  name        = "protect-cloudtrail"
  description = "Prevent disabling or modifying CloudTrail"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DenyCloudTrailDisable"
        Effect = "Deny"
        Action = [
          "cloudtrail:DeleteTrail",
          "cloudtrail:StopLogging",
          "cloudtrail:UpdateTrail"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_organizations_policy_attachment" "protect_cloudtrail" {
  for_each  = toset(local.member_account_ids)
  policy_id = aws_organizations_policy.protect_cloudtrail.id
  target_id = each.value
}

# ---------------------------------------------------------------------------
# SCP 3 — Prevent leaving the organization
# Ensures member accounts cannot be detached without management account action.
# ---------------------------------------------------------------------------
resource "aws_organizations_policy" "prevent_leave_org" {
  name        = "prevent-leave-org"
  description = "Prevent member accounts from leaving the organization"
  type        = "SERVICE_CONTROL_POLICY"

  content = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DenyLeaveOrganization"
        Effect   = "Deny"
        Action   = "organizations:LeaveOrganization"
        Resource = "*"
      }
    ]
  })
}

resource "aws_organizations_policy_attachment" "prevent_leave_org" {
  for_each  = toset(local.member_account_ids)
  policy_id = aws_organizations_policy.prevent_leave_org.id
  target_id = each.value
}
