# Security Posture & Zero-Trust Identity Federation

## 1. Zero Static Cloud Credentials (Decision D20)

The QGI monorepo enforces a strict zero-static-key policy:
- **GitHub Actions to AWS OIDC:** All CI/CD infrastructure workflows (`.github/workflows/oidc-infra-deploy.yml`) authenticate to AWS via short-lived OpenID Connect (OIDC) tokens (`aud: sts.amazonaws.com`, `sub: repo:AminAlAit/qgi:*`) using `aws-actions/configure-aws-credentials@v4`.
- **Vercel Build-Time OIDC:** Next.js production builds authenticate to S3 via `@vercel/oidc-aws-credentials-provider` to verify and fetch pinned dataset manifests (`frontend/scripts/fetch-build-data.mjs`).

## 2. Pre-Push Verification Firewall

Every local commit and push is guarded by the 6-gate offline verification harness (`scripts/verify-monorepo.ps1` and `scripts/verify-monorepo.sh`), which scans tracked files and git history for:
- AWS Access Key IDs (`AKIA...`, `ASIA...`)
- Cryptographic private keys (`-----BEGIN ... PRIVATE KEY-----`)
- GitHub Personal Access Tokens (`ghp_...`, `github_pat_...`)
- Quarantined legacy AWS account references (`207423186738`)
- Automated AI co-author commit trailers

## 3. Reporting Security Issues

To report a potential vulnerability in the public codebase or at `https://qgintelligence.com`, contact **aminalait.de@gmail.com**.
