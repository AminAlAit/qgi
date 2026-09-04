/**
 * lib/aws-credentials.ts — runtime AWS credential selection.
 *
 * Pins the branch that matters for the prod launch: on Vercel (AWS_ROLE_ARN
 * set) we MUST federate via the OIDC provider or DynamoDB/Cognito authenticated
 * calls fail; locally (unset) we MUST return undefined so the default chain
 * uses the .env.local STS creds. The @vercel provider is mocked so no network
 * or real OIDC token is needed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@vercel/oidc-aws-credentials-provider", () => ({
  awsCredentialsProvider: vi.fn((args?: { roleArn?: string }) => ({
    __mockProviderFor: args?.roleArn ?? null,
  })),
}));

import { awsCredentialsProvider } from "@vercel/oidc-aws-credentials-provider";
import { awsRuntimeCredentials } from "@/lib/aws-credentials";

const mockProvider = vi.mocked(awsCredentialsProvider);
const ROLE = "arn:aws:iam::771606957899:role/qgi-vercel-frontend-reader";

describe("awsRuntimeCredentials", () => {
  const original = process.env.AWS_ROLE_ARN;
  beforeEach(() => mockProvider.mockClear());
  afterEach(() => {
    if (original === undefined) delete process.env.AWS_ROLE_ARN;
    else process.env.AWS_ROLE_ARN = original;
  });

  it("returns undefined when AWS_ROLE_ARN is unset (local → default chain)", async () => {
    delete process.env.AWS_ROLE_ARN;
    expect(await awsRuntimeCredentials()).toBeUndefined();
    expect(mockProvider).not.toHaveBeenCalled();
  });

  it("federates via the Vercel OIDC provider when AWS_ROLE_ARN is set", async () => {
    process.env.AWS_ROLE_ARN = ROLE;
    const creds = await awsRuntimeCredentials();
    expect(mockProvider).toHaveBeenCalledWith({ roleArn: ROLE });
    expect(creds).toEqual({ __mockProviderFor: ROLE });
  });
});
