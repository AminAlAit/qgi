/**
 * HeroNewsPieces — compact news headlines for the Briefing hero left column.
 *
 * Server component. Receives up to 3 LiveArticle rows (already filtered +
 * sorted by the page). Renders nothing when the list is empty (confidence-first:
 * no placeholders, no "coming soon").
 *
 * deriveTitle is COPIED (not imported) from LivePulseTerminal so the terminal
 * component remains independent.
 */
import type { LiveArticle } from "@/lib/hf/live-pulse-series";

/* ── deriveTitle (copied from components/countries-v4-1/LivePulseTerminal.tsx) ── */

const GENERIC: ReadonlySet<string> = new Set([
  "news",
  "world",
  "international",
  "national",
  "article",
  "articles",
  "story",
  "stories",
  "amp",
  "live",
  "updates",
  "update",
  "index",
  "home",
  "category",
  "politics",
  "business",
  "opinion",
  "video",
  "photos",
  "gallery",
  "breaking",
  "latest",
  "en",
  "ar",
  "section",
  "content",
  "web",
  "wire",
  "node",
]);

function hasVowel(t: string): boolean {
  return /[aeiou]/i.test(t);
}
function junkTok(t: string): boolean {
  if (/^\d{1,4}$/.test(t)) return false;
  const digits = (t.match(/\d/g) || []).length;
  if (t.length >= 16) return true;
  if (digits && digits / t.length > 0.4) return true;
  if (t.length >= 7 && !hasVowel(t)) return true;
  if (/^[0-9a-f]{6,}$/i.test(t)) return true;
  return false;
}
function wordsFrom(slug: string): { kept: string[]; real: string[] } {
  const s = slug.replace(/\.(html?|php|aspx?|ece|cms|amp|stm)$/i, "");
  const kept = s
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .filter((t) => !junkTok(t));
  while (kept.length && /^\d+$/.test(kept[0])) kept.shift();
  while (kept.length && /^\d+$/.test(kept[kept.length - 1])) kept.pop();
  const real = kept.filter((t) => /[A-Za-z]/.test(t) && hasVowel(t) && t.length >= 2);
  return { kept, real };
}
function deriveTitle(url: string, domain: string, topicLabel: string): string {
  let path = (url || "").split("?")[0].split("#")[0];
  if (domain && path.indexOf(domain) >= 0) path = path.split(domain)[1] || "";
  const segs = path.split("/").filter((s) => s && !GENERIC.has(s.toLowerCase()));
  for (let i = segs.length - 1; i >= 0; i--) {
    const w = wordsFrom(segs[i]);
    if (w.real.length >= 3) {
      return w.kept
        .join(" ")
        .replace(/\b\w/g, (c) => c.toUpperCase())
        .slice(0, 96);
    }
  }
  const dom = (domain || "source").replace(/^www\./, "").split(".")[0];
  return dom.charAt(0).toUpperCase() + dom.slice(1) + " · " + (topicLabel || "report");
}

/* ── short date from GKG dt stamp ─────────────────────────────────────── */

const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function shortDate(dt: string): string {
  if (!dt || dt.length < 8) return "";
  const m = parseInt(dt.slice(4, 6), 10) - 1;
  return `${MONTHS[m] ?? "?"} ${dt.slice(6, 8)}`;
}

/* ── component ─────────────────────────────────────────────────────────── */

interface HeroNewsPiecesProps {
  articles: LiveArticle[]; // 0–3 items, already filtered + sorted
}

export function HeroNewsPieces({ articles }: HeroNewsPiecesProps) {
  if (articles.length === 0) return null;

  return (
    <div
      style={{
        marginBottom: "18px",
      }}
    >
      {/* Label */}
      <p
        style={{
          fontSize: "9px",
          fontWeight: 700,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          fontFamily: "ui-monospace, monospace",
          color: "var(--qgi-text-dim)",
          margin: "0 0 8px",
        }}
      >
        In the news
      </p>

      {/* Article list */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        {articles.map((a, i) => {
          const title = deriveTitle(a.url, a.domain, a.topicLabel);
          const date = shortDate(a.dt);
          const displayDomain = (a.domain || "").replace(/^www\./, "");

          return (
            <a
              key={`${a.url}-${i}`}
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "block",
                textDecoration: "none",
                padding: "7px 9px",
                background: "rgba(91,126,153,0.06)",
                border: "1px solid var(--qgi-border)",
                borderRadius: "5px",
              }}
            >
              {/* Headline */}
              <p
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--qgi-text)",
                  margin: "0 0 3px",
                  lineHeight: 1.35,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {title}
              </p>

              {/* Meta: domain · date */}
              <p
                style={{
                  fontSize: "10px",
                  color: "var(--qgi-text-dim)",
                  margin: 0,
                  lineHeight: 1,
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {displayDomain}
                {date ? ` · ${date}` : ""}
              </p>
            </a>
          );
        })}
      </div>
    </div>
  );
}
