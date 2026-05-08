# ─── Self-hosted GHA runner — Spot Graviton EC2 ──────────────────────────────
#
# Replaces GHA-hosted minutes when the org quota is exhausted (qgi-aws-tf#970).
# Single instance per invocation; one ASG keeps it warm and re-registers if a
# Spot interruption terminates the instance.
#
# See module README for the trade-off rationale.

locals {
  # Deterministic prefix so two invocations targeting different repos don't
  # collide on names.
  name_prefix = var.name_prefix != "" ? var.name_prefix : "qgi-gha-runner-${var.runner_label}"
}

# ─── AMI — latest Amazon Linux 2023 (arm64) ──────────────────────────────────
data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-arm64"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ─── IAM — instance role + profile ───────────────────────────────────────────
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "runner" {
  name               = "${local.name_prefix}-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = var.tags
}

# AWS-managed: enables Session Manager (no SSH key needed; founder can shell in
# via SSM when debugging a stuck runner registration).
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.runner.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Custom: read ONE secret (the PAT used at cloud-init time to mint a
# registration token). Scoped tight; runner can NOT read any other secret.
data "aws_iam_policy_document" "read_pat" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:aws:secretsmanager:*:*:secret:${var.runner_pat_secret_name}-*",
      "arn:aws:secretsmanager:*:*:secret:${var.runner_pat_secret_name}",
    ]
  }
}

resource "aws_iam_role_policy" "read_pat" {
  name   = "${local.name_prefix}-read-pat"
  role   = aws_iam_role.runner.id
  policy = data.aws_iam_policy_document.read_pat.json
}

resource "aws_iam_instance_profile" "runner" {
  name = "${local.name_prefix}-profile"
  role = aws_iam_role.runner.name
  tags = var.tags
}

# ─── Security group — outbound-only (no inbound) ─────────────────────────────
resource "aws_security_group" "runner" {
  name        = "${local.name_prefix}-sg"
  description = "GHA self-hosted runner -- outbound-only (GitHub API + S3 + Secrets Manager)"
  vpc_id      = var.vpc_id

  egress {
    description      = "All outbound (GitHub + AWS services + repo dependencies)"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = var.tags
}

# ─── cloud-init — register the runner with GitHub ────────────────────────────
locals {
  user_data = templatefile("${path.module}/cloud-init.sh.tftpl", {
    repo                   = var.repo
    runner_label           = var.runner_label
    runner_pat_secret_name = var.runner_pat_secret_name
  })
}

# ─── Launch template ─────────────────────────────────────────────────────────
resource "aws_launch_template" "runner" {
  name_prefix   = "${local.name_prefix}-"
  image_id      = data.aws_ami.al2023_arm64.id
  instance_type = var.instance_type
  user_data     = base64encode(local.user_data)

  iam_instance_profile {
    arn = aws_iam_instance_profile.runner.arn
  }

  network_interfaces {
    # QA B1: default VPC's default subnets are public (Internet Gateway,
    # no NAT). Without a public IP the runner can't reach github.com or dnf
    # repos and cloud-init fails at step 1. Sg is outbound-only with no
    # inbound rules — the public IP is purely egress.
    associate_public_ip_address = true
    security_groups             = [aws_security_group.runner.id]
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 20 # GB; runner binary + a clone of qgi-frontend (~100 MB)
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }

  metadata_options {
    http_tokens   = "required" # IMDSv2 only
    http_endpoint = "enabled"
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(var.tags, { Name = local.name_prefix })
  }

  tag_specifications {
    resource_type = "volume"
    tags          = merge(var.tags, { Name = "${local.name_prefix}-volume" })
  }

  tags = var.tags
}

# ─── Auto Scaling Group (size 1) — survives Spot interruption ────────────────
resource "aws_autoscaling_group" "runner" {
  name                = local.name_prefix
  vpc_zone_identifier = [var.subnet_id]
  desired_capacity    = var.desired_capacity
  min_size            = 0
  max_size            = 1

  health_check_type         = "EC2"
  health_check_grace_period = 600 # 10 min — let cloud-init register the runner

  mixed_instances_policy {
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.runner.id
        version            = "$Latest"
      }
    }

    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "capacity-optimized"
      spot_max_price                           = var.spot_max_price
    }
  }

  tag {
    key                 = "Name"
    value               = local.name_prefix
    propagate_at_launch = false
  }

  dynamic "tag" {
    for_each = var.tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }
}
