// Vitest stub for Next.js's `server-only` package. The real package
// throws at import time when used in a Client Component context;
// vitest runs in Node so the guard is moot. Stub exists purely so the
// `import "server-only"` directive in lib files doesn't fail to resolve.
//
// See vitest.config.ts `resolve.alias` for how this stub is wired in.
export {};
