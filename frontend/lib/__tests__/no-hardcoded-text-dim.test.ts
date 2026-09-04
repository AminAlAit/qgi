/**
 * #737 regression guard (2026-05-16).
 *
 * The 34 hard-coded `#4a6280` literals across 14 V1 / chart / palette
 * files were swept to `#8aa6be` in PR #82 so they match the new
 * AA-compliant value of `--qgi-text-dim`. This test fails CI if a new
 * occurrence appears anywhere in `app/`, `components/`, or `lib/`
 * (excluding `app/globals.css` which keeps two `#4a6280` references in
 * the historical-note comment).
 *
 * The grep also catches the rgba-decimal form `rgba(74, 98, 128, …)`
 * since that's just `#4a6280` rewritten — same a11y failure mode, same
 * AA-failing slate.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

// Walk every source root where this slate could plausibly hide. tests/
// + scripts/ + e2e specs are included so a future bake script or
// Playwright spec can't sneak the pre-#706 color back into the tree.
const ROOTS = ["app", "components", "lib", "tests", "scripts"];
const EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".css", ".mjs", ".cjs"]);

// globals.css holds two intentional historical references in the #706
// fix's comment block (lines 21 + 35 as of 2026-05-16). Those are
// documentation, not active values. The test file itself is also
// allowlisted because the regex literal would otherwise trip the guard
// (#737 self-detection edge case). Entries use forward slashes so the
// match works on Windows dev boxes (PR #82 nit fix); the loop
// normalizes every walked path before checking.
const ALLOWLIST = new Set([
  "app/globals.css",
  "lib/__tests__/no-hardcoded-text-dim.test.ts",
]);

function walk(dir: string, acc: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith(".")) continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full, acc);
    } else if (st.isFile()) {
      const dot = name.lastIndexOf(".");
      const ext = dot >= 0 ? name.slice(dot) : "";
      if (EXTS.has(ext)) acc.push(full);
    }
  }
  return acc;
}

describe("#737 regression guard — no hard-coded #4a6280", () => {
  it("no source file outside the allowlist contains #4a6280 or its rgb form", () => {
    const offenders: string[] = [];
    for (const root of ROOTS) {
      const files = walk(root);
      for (const file of files) {
        // Normalize to forward-slash so allowlist hits the same string
        // whether the runner is Linux CI or a Windows dev box.
        const rel = file.replace(/\\/g, "/");
        if (ALLOWLIST.has(rel)) continue;
        const text = readFileSync(file, "utf8");
        const hexHit = /#4a6280/i.test(text);
        const rgbHit = /\brgba?\(\s*74\s*,\s*98\s*,\s*128/i.test(text);
        if (hexHit || rgbHit) offenders.push(rel);
      }
    }
    expect(
      offenders,
      `Found pre-#706 slate (#4a6280 / rgb(74,98,128)) in:\n  ${offenders.join("\n  ")}\nUse #8aa6be (or var(--qgi-text-dim) for JSX style props) instead.`
    ).toEqual([]);
  });
});
