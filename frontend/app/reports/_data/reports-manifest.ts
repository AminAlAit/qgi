export const SECTION_LABEL = "QGI Reports";

export type ReportStatus = "live" | "disabled" | "placeholder";

export type ReportCategory = "Country Analysis" | "Sovereign Credit Note" | "Thematic";

export type Report = {
  slug: string;
  title: string;
  summary: string;
  category: ReportCategory;
  publishedAt: string;
  status: ReportStatus;
  format: "brief" | "deep-dive";
  ogImagePath?: string;
  href?: string;
  eyestat?: {
    primary: string;
    label: string;
    secondary?: string;
    countryLabel?: string;
  };
  clusterKey?: string;
  countryCodes?: string[];
  relatedSlugs?: string[];
  readingTime?: number;
  image?: string;
  imageCredit?: string;
};

export const REPORTS: Report[] = [
  {
    slug: "pakistan-profile",
    title:
      "Five Models, One Country: What QGI's Structural Scan Finds in Pakistan That Macro Analysis Misses",
    summary:
      "Pakistan ranks in the top 8 to 20 globally across five independent structural models simultaneously. Its nearest self-analogue is Pakistan 2011, match score 0.9712. The same structural configuration that preceded Raymond Davis, Abbottabad, and Salala.",
    category: "Country Analysis",
    format: "deep-dive",
    publishedAt: "2026-06-20",
    status: "live",
    image: "/reports/thumbs/pakistan-profile.jpg",
    countryCodes: ["PAK"],
    eyestat: {
      primary: "Top 8-20",
      label: "Across 5 structural models",
      secondary: "self-analogue: Pakistan 2011 (0.9712)",
      countryLabel: "Pakistan",
    },
    readingTime: 18,
    relatedSlugs: ["uk-currency-crisis", "india-pakistan-mirror"],
  },
  {
    slug: "uk-currency-crisis",
    title:
      "The Judiciary Doesn't Rate-Set, But It's Topping QGI's Currency-Crisis Leaderboard",
    summary:
      "QGI's pattern engine scores the United Kingdom #1 of 157 countries on its Currency-Crisis recipe, with its closest structural analogue its own 1992 ERM exit at 0.975 cosine resemblance.",
    category: "Thematic",
    format: "deep-dive",
    publishedAt: "2026-06-19",
    status: "live",
    countryCodes: ["GBR"],
    eyestat: {
      primary: "#1 of 157",
      label: "Currency-crisis resemblance",
      secondary: "nearest analogue: its own 1992 (0.975)",
      countryLabel: "United Kingdom",
    },
    readingTime: 15,
    image: "/reports/thumbs/uk-currency-crisis.jpg",
    imageCredit: "Leo / Unsplash",
  },
  {
    slug: "niger-burkina-divergence",
    title:
      "The Junta That Cannot Stay Isolated: Niger's Structural Divergence Inside the AES Bloc",
    summary:
      "QGI places Niger at #4 of 58 on its Multilateral Agreement recipe at 94/100. Its closest structural peer, Burkina Faso (95% cosine similarity), sits at #57 with 2/100. The two AES juntas are on opposite structural paths.",
    category: "Country Analysis",
    format: "deep-dive",
    publishedAt: "2026-05-21",
    status: "live",
    countryCodes: ["NER", "BFA"],
    image: "/reports/thumbs/niger-burkina-divergence.jpg",
    imageCredit: "Pfc. Luke Steward, U.S. Army / DVIDS",
  },
  {
    slug: "india-pakistan-mirror",
    title:
      "India and Pakistan Are 99% the Same Risk, and Neither Risk Framework Wants to Hear It",
    summary:
      "QGI places India and Pakistan at 99% cosine similarity, each other's #1 structural peer in the 156-country cohort. Civil War & Insurgency recipe fires on both with the same fingerprint. The convergence is recent, not decades-embedded.",
    category: "Country Analysis",
    format: "deep-dive",
    publishedAt: "2026-05-21",
    status: "live",
    countryCodes: ["IND", "PAK"],
    image: "/reports/thumbs/india-pakistan-mirror.jpg",
    imageCredit: "NASA / ISS Crew Earth Observations",
  },
  {
    slug: "ukraine-bosnia-mirror",
    title:
      "Ukraine's Structural Mirror: What Bosnia 1996 Tells the Credit Desk About Ukraine 2027",
    summary:
      "QGI places Ukraine's closest structural twin at Bosnia and Herzegovina (81% cosine, 16-point gap above the next-closest cluster). A falsifiable structural-credit thesis: Multilateral Agreement crossing 70/100 is the entry trigger, 60/100 floor with no CI narrowing is the exit.",
    category: "Sovereign Credit Note",
    format: "deep-dive",
    publishedAt: "2026-05-21",
    status: "live",
    countryCodes: ["UKR", "BIH"],
    image: "/reports/thumbs/ukraine-bosnia-mirror.jpg",
    imageCredit: "Sandin Redzo / Pexels",
  },
  {
    slug: "ghana-mauritania-mirror",
    title:
      "Ghana's Double Signal: The Ballot Box, the Barracks, and the Country Nobody Expected",
    summary:
      "QGI places Ghana at the 99th percentile of global election-stress in its April 2026 scoring run. Its closest structural peer is Mauritania at 99% cosine similarity, not Mali, not Burkina Faso. What that structural resemblance means for the six-month forward call.",
    category: "Country Analysis",
    format: "deep-dive",
    publishedAt: "2026-05-19",
    status: "live",
    countryCodes: ["GHA", "MRT"],
  },
  {
    slug: "fsi-qgi-report",
    title: "FSI x QGI: Fragile-State Pattern Overlay",
    summary:
      "How QGI's structural-analogue patterns align with Fund for Peace's Fragile States Index, where they diverge, and what the divergence flags for analysts.",
    category: "Thematic",
    format: "brief",
    publishedAt: "2026-04-24",
    status: "live",
    countryCodes: [],
  },
  {
    slug: "burkina-faso-mali-car-mirror",
    title: "Burkina Faso's risk signature mirrors Mali 2010-2012 and CAR 2011-2013",
    summary:
      "Five risk domains light up together on Burkina Faso in our current bake. The same combination preceded the 2012 Mali coup and the 2013 Central African Republic collapse. What that structural resemblance means, and what it does not.",
    category: "Country Analysis",
    format: "deep-dive",
    publishedAt: "2026-05-15",
    status: "disabled",
    countryCodes: ["BFA", "MLI", "CAF"],
  },
];

// publishedAt is YYYY-MM-DD ISO date; lexicographic sort is correct iff this invariant holds.
export function getDisplayableReports(): Report[] {
  return REPORTS.filter((r) => r.status === "live").sort((a, b) =>
    b.publishedAt.localeCompare(a.publishedAt)
  );
}

export function getLatestForRail(): Report[] {
  return REPORTS.filter((r) => r.status === "live")
    .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))
    .slice(0, 2);
}

export function getLiveStats(): { reportCount: number; countryCount: number } {
  const live = REPORTS.filter((r) => r.status === "live");
  const codes = new Set<string>();
  for (const r of live) {
    for (const c of r.countryCodes ?? []) {
      if (c) codes.add(c);
    }
  }
  return { reportCount: live.length, countryCount: codes.size };
}

export function getRelatedReports(slug: string, n = 2): Report[] {
  const report = REPORTS.find((r) => r.slug === slug);
  if (!report) return [];

  // First try explicit relatedSlugs
  if (report.relatedSlugs && report.relatedSlugs.length > 0) {
    const bySlug = report.relatedSlugs
      .map((s) => REPORTS.find((r) => r.slug === s && r.status === "live"))
      .filter((r): r is Report => r !== undefined)
      .slice(0, n);
    if (bySlug.length > 0) return bySlug;
  }

  // Fall back: same category, live, excluding self, sorted by date
  return REPORTS.filter(
    (r) => r.slug !== slug && r.status === "live" && r.category === report.category
  )
    .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))
    .slice(0, n);
}

export function formatPublishedDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
