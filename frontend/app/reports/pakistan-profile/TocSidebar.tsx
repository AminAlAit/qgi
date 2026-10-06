"use client";

import { useEffect, useState } from "react";

const TOC_ENTRIES = [
  { id: "intro", label: "Introduction" },
  { id: "five-models", label: "Five Models, Five Rankings" },
  { id: "lead-signals", label: "The Primary Driver" },
  { id: "self-analogue", label: "The 2011 Self-Analogue" },
  { id: "news-vs-structure", label: "News vs Structure" },
  { id: "methodology-footnote", label: "Methodology" },
];

export default function TocSidebar() {
  const [activeId, setActiveId] = useState<string>("");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      {
        rootMargin: "-20% 0px -60% 0px",
        threshold: 0,
      }
    );

    for (const entry of TOC_ENTRIES) {
      const el = document.getElementById(entry.id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, []);

  return (
    <aside className="hidden xl:block fixed left-0 top-16 w-56 h-[calc(100vh-4rem)] overflow-y-auto px-4 py-8 print:hidden">
      <div
        className="text-[9px] tracking-[0.2em] uppercase mb-4 font-semibold"
        style={{ color: "var(--qgi-accent)" }}
      >
        Contents
      </div>
      <nav className="space-y-1">
        {TOC_ENTRIES.map((entry) => (
          <a
            key={entry.id}
            href={`#${entry.id}`}
            className="block text-[11px] leading-snug py-1 transition-colors hover:text-[var(--qgi-accent)]"
            style={{
              color: activeId === entry.id ? "var(--qgi-accent)" : "var(--qgi-text-dim)",
              fontWeight: activeId === entry.id ? 600 : 400,
            }}
          >
            {entry.label}
          </a>
        ))}
      </nav>
    </aside>
  );
}
