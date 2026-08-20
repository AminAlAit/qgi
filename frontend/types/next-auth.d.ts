// Module augmentation so the session/JWT carry the Cognito plan group + the
// sign-in provider without `any` casts. Picked up via tsconfig `**/*.ts`.
import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface User {
    /** cognito:groups from the Cognito id-token (email/password users). */
    groups?: string[];
  }
  interface Session {
    user: {
      groups?: string[];
      provider?: string;
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    groups?: string[];
    provider?: string;
  }
}
