import "server-only";

import type { AwsCredentialIdentityProvider } from "@aws-sdk/types";

/**
 * Runtime AWS credentials for server-side SDK clients (DynamoDB, Cognito).
 *
 * On Vercel the runtime has a signed OIDC token + `AWS_ROLE_ARN` but NO static
 * access keys, and the AWS SDK's DEFAULT credential chain does not understand
 * Vercel OIDC — so a client built with just `{ region }` throws "Credential is
 * missing" the moment it makes an authenticated call (e.g. DynamoDB GetItem,
 * Cognito ListUsers). When `AWS_ROLE_ARN` is present we federate through
 * Vercel's OIDC provider to assume that role (the same pattern the live-pulse
 * S3 readers use — lib/hf/live-pulse.ts / live-pulse-buckets.ts).
 *
 * Locally (and in any non-Vercel runtime) `AWS_ROLE_ARN` is unset, so we return
 * `undefined` and the caller lets the default chain pick up the `.env.local`
 * STS creds — unchanged from before. The `@vercel/oidc-aws-credentials-provider`
 * import is dynamic so it's only pulled in when actually federating.
 */
export async function awsRuntimeCredentials(): Promise<
  AwsCredentialIdentityProvider | undefined
> {
  const roleArn = process.env.AWS_ROLE_ARN;
  if (!roleArn) return undefined;
  const { awsCredentialsProvider } =
    await import("@vercel/oidc-aws-credentials-provider");
  return awsCredentialsProvider({ roleArn });
}
