"use client";

import { SessionProvider } from "next-auth/react";

/**
 * Client wrapper so server components in the tree can host NextAuth's
 * SessionProvider (required for useSession / the auth menu). Mounted once in
 * app/layout.tsx around {children}.
 */
export function SessionProviderWrapper({ children }: { children: React.ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
