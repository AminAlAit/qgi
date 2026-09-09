/**
 * SurfaceGrid — V4.1 rebuild.
 *
 * Changes from V4:
 * - Wrapped in PanelBase (calm slate-blue, aggregator accent).
 * - Accepts V4.1 SurfaceCardData (ribbon-free, metric optional).
 * - The §02 section-number header and "{N} deep pages" subtitle are
 *   superseded by PanelBase's title/caption — removed from inner markup.
 *
 * Unchanged from V4:
 * - auto-fill minmax(280px, 1fr) responsive card grid.
 * - SurfaceCard rendering per card.
 */
import { SurfaceCard, type SurfaceCardData } from "./SurfaceCard";
import { PanelBase } from "./PanelBase";

export function SurfaceGrid({ cards }: { cards: SurfaceCardData[] }) {
  return (
    <PanelBase
      title="Surfaces"
      caption="The six pages that make up the platform. Open any to see the data for that lens."
      accent="#5B7E99"
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "14px",
        }}
      >
        {cards.map((c) => (
          <SurfaceCard key={c.surface_id} card={c} />
        ))}
      </div>
    </PanelBase>
  );
}
