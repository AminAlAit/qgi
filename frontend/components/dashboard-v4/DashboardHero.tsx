import type { LucideIcon } from "lucide-react";

export interface HeroTile {
  value: string;
  label: string;
  sublabel: string;
  Icon: LucideIcon;
  color: string;
  big?: boolean;
}

export function DashboardHero({ tiles }: { tiles: HeroTile[] }) {
  return (
    <section style={{ marginBottom: "32px" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "12px",
        }}
      >
        {tiles.map((t, i) => (
          <ScoreTile key={`${t.label}-${i}`} tile={t} />
        ))}
      </div>
    </section>
  );
}

function ScoreTile({ tile }: { tile: HeroTile }) {
  const { value, label, sublabel, Icon, color, big } = tile;
  return (
    <div
      style={{
        background: "var(--qgi-surface)",
        border: `1px solid ${color}66`,
        borderLeft: `3px solid ${color}`,
        borderRadius: "8px",
        padding: big ? "18px 20px" : "14px 16px",
        display: "flex",
        alignItems: "flex-start",
        gap: "12px",
        minHeight: big ? "108px" : "92px",
        boxShadow: big ? `0 0 22px ${color}22` : "none",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: big ? "40px" : "34px",
          height: big ? "40px" : "34px",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--qgi-bg)",
          border: `1px solid ${color}`,
          borderRadius: "6px",
          color,
        }}
      >
        <Icon size={big ? 22 : 18} strokeWidth={1.6} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontWeight: 600,
            fontSize: big ? "32px" : "24px",
            lineHeight: 1,
            color,
            letterSpacing: "-0.5px",
            wordBreak: "break-word",
          }}
        >
          {value}
        </div>
        <div
          style={{
            marginTop: "8px",
            fontSize: "10.5px",
            letterSpacing: "1px",
            textTransform: "uppercase",
            fontFamily: "ui-monospace, monospace",
            color: "var(--qgi-text)",
            fontWeight: 600,
          }}
        >
          {label}
        </div>
        <div
          style={{
            fontSize: "10.5px",
            color: "var(--qgi-text-muted)",
            marginTop: "2px",
            lineHeight: 1.3,
          }}
        >
          {sublabel}
        </div>
      </div>
    </div>
  );
}
