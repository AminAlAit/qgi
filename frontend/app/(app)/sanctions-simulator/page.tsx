/**
 * /sanctions-simulator — "coming soon" surface.
 *
 * The full interactive scenario bench (the realized vision) renders as a rich,
 * scrollable, blurred backdrop; a centered "coming soon" sign sits on top and
 * stays centered while the backdrop scrolls. The interactive model is still
 * R&D, so the surface is gated this way rather than shipped live. To take it
 * live later, render <SanctionsSimulator/> directly instead of via ComingSoonGlass.
 *
 * See `docs/specs/internal/ops/sanctions-simulator-rnd-brief-2026-06-04.md`.
 */
import type { Metadata } from "next";
import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { Route } from "next";
import {
  ComingSoonGlass,
  ComingSoonCard,
} from "@/components/coming-soon/ComingSoonGlass";
import { SanctionsSimulator } from "@/components/sanctions-sim/SanctionsSimulator";

export const metadata: Metadata = {
  title: "Sanctions Simulator · QG Intelligence",
  description:
    "A what-if scenario tool: pick a country and a sanctions hardness level, see how its indicators bend and which event trends it drifts toward over a five-year horizon. A scenario, not a forecast.",
  robots: { index: false, follow: false },
};

export default function SanctionsSimulatorPage() {
  return (
    <ComingSoonGlass
      backdrop={
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          <header style={{ marginBottom: 22 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                color: "var(--qgi-accent)",
                fontSize: 10,
                letterSpacing: "3px",
                textTransform: "uppercase",
                fontFamily: "ui-monospace, monospace",
                marginBottom: 12,
              }}
            >
              <ShieldAlert size={13} strokeWidth={2} />
              Sanctions Simulator
            </div>
            <h1
              style={{
                fontSize: "clamp(26px, 4vw, 38px)",
                fontWeight: 700,
                lineHeight: 1.1,
                margin: "0 0 12px",
              }}
            >
              What would a sanction do?
            </h1>
            <p
              style={{
                fontSize: 16,
                lineHeight: 1.6,
                color: "var(--qgi-text-muted)",
                maxWidth: 820,
                margin: 0,
              }}
            >
              Pick a country and a sanctions hardness, then watch how its indicators bend
              and which historical event trends it starts to resemble over a five-year
              horizon. A scenario, not a forecast.
            </p>
          </header>
          <SanctionsSimulator />
        </div>
      }
    >
      <ComingSoonCard title="Sanctions Simulator">
        <p style={{ margin: 0 }}>
          A what-if scenario tool. Pick a country and a sanctions hardness, then see how
          its indicators bend and which event trends it starts to resemble over a
          five-year horizon. The interactive model is in development. It is a scenario,
          not a forecast.
        </p>
        <p style={{ margin: "10px 0 0" }}>
          In the meantime, see the historical cases each country most resembles via{" "}
          <Link
            href={"/analogues" as Route}
            style={{ color: "var(--qgi-accent)", textDecoration: "none" }}
          >
            Analogues
          </Link>
          .
        </p>
      </ComingSoonCard>
    </ComingSoonGlass>
  );
}
