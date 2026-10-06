/**
 * GemCard — server component, purely presentational.
 *
 * A single structural-resemblance gem card with a colored left border,
 * hover lift, and a CTA link. No client JS, no data fetching.
 */
import Link from "next/link";
import type { Route } from "next";

export interface GemCardProps {
  eyebrow: string;
  headline: string;
  body: string;
  href: string;
  accentColor: string;
}

export function GemCard({ eyebrow, headline, body, href, accentColor }: GemCardProps) {
  const cls = `gem-card-${accentColor.replace("#", "")}`;
  return (
    <>
      <style>{`
        .${cls} {
          transition: transform 0.16s ease, box-shadow 0.16s ease;
          cursor: pointer;
        }
        .${cls}:hover {
          transform: translateY(-3px);
          box-shadow: 0 6px 20px rgba(0,0,0,0.18);
        }
      `}</style>
      <div
        className={cls}
        style={{
          backgroundColor: "var(--qgi-surface)",
          borderLeft: `3px solid ${accentColor}`,
          borderRadius: "8px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
        }}
      >
        <p
          className="text-[10px] tracking-widest uppercase"
          style={{
            color: "var(--qgi-text-dim)",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {eyebrow}
        </p>

        <h3
          className="text-[15px] font-semibold leading-snug"
          style={{ color: "var(--qgi-text)" }}
        >
          {headline}
        </h3>

        <p
          className="text-[13px] leading-relaxed flex-1"
          style={{ color: "var(--qgi-text-muted)" }}
        >
          {body}
        </p>

        <Link
          href={href as Route}
          className="gem-link text-[12px] font-medium border-b pb-0.5 w-fit"
          style={{ color: accentColor, borderColor: accentColor }}
        >
          Read report &rarr;
        </Link>
      </div>
    </>
  );
}
