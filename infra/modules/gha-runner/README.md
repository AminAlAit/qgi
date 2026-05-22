# `gha-runner` module — self-hosted GHA runner on Spot Graviton EC2

Provisions one self-hosted GitHub Actions runner per invocation, on a
c7g.medium Spot Graviton instance (~$5/mo). Replaces GHA-hosted minutes
when the org quota is exhausted (qgi-aws-tf#970 — founder declined top-up).

Documented in architectural decision records and fleet specifications.


## What it creates

- **EC2 launch template** for c7g.medium Spot Graviton
- **Auto Scaling Group** with `desired_capacity = 1` — replaces the
  instance if it terminates (Spot interruption → fresh registration)
- **IAM instance profile** with minimum scope: Session Manager + read
  the runner-registration secret from Secrets Manager
- **cloud-init** script that:
  1. Installs the GitHub Actions runner binary (arm64)
  2. Fetches a short-lived registration token via the GitHub API
  3. Registers the runner with the target repo, with the supplied label

## What you must create OUTSIDE Terraform

A **fine-grained PAT secret** in Secrets Manager with `Administration:
Read and Write` on the target repo. The cloud-init script reads this
secret to mint a registration token.

```bash
# One-time founder step (per runner):
aws secretsmanager create-secret \
  --name qgi-gha-runner-registration-<repo-shortname>-pat \
  --secret-string "<fine-grained-pat-value>"
```

## Trade-offs

- **Why one runner per repo**: GitHub Actions on a personal account
  (AminAlAit) does NOT support org-level runners — each repo registers
  its own. Three runners cost ~$15/mo total; still cheaper than topping
  up GHA-hosted minutes.
- **Why c7g.medium (and not c7g.large)**: the workloads on these runners
  are git, `aws s3 sync`, and `gh` — all CPU-light, network-bound. 2
  vCPU + 4 GB RAM is enough.
- **Why ASG with desired=1, not a bare EC2**: Spot interruption
  recovery is automatic. The new instance re-registers on boot.
- **Idempotency on registration**: the cloud-init script calls
  `config.sh remove` before `config.sh --token ...` so a re-registered
  instance doesn't pile up zombie runners in GitHub's runner list.

## Inputs

| Name | Description |
|---|---|
| `repo` | `<owner>/<repo>` slug (e.g. `AminAlAit/qgi-frontend`) |
| `runner_label` | Workflow label (e.g. `qgi-frontend`); the workflow uses `runs-on: [self-hosted, <label>]` |
| `runner_pat_secret_name` | Secrets Manager secret holding the registration PAT |
| `subnet_id` | VPC subnet for the runner (private subnet preferred) |
| `vpc_id` | VPC ID (for the security group) |
| `instance_type` | Default: `c7g.medium` |
| `tags` | Standard tags |

## Outputs

| Name | Description |
|---|---|
| `asg_name` | ASG name |
| `launch_template_id` | LT ID (for diagnostics) |
| `instance_profile_arn` | IAM instance profile ARN |
