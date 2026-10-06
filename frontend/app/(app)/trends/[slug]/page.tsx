import type { Metadata } from "next";
import Link from "next/link";
import type { Route } from "next";
import { notFound } from "next/navigation";
import { HowToReadButton } from "@/components/te-v4-shared/HowToReadButton";
import {
  getAllRecipes,
  getRecipe,
  getMock,
  isDemoGraduated,
} from "@/lib/te-mock/recipes";
import {
  getRecipeV4Extras,
  getFallbackExtras,
  getCountriesFull,
} from "@/lib/te-mock/recipe-v4-1-mock";
import { statusLabel } from "@/lib/te-mock/country-families";
import { getShapeData } from "@/lib/te-mock/recipe-shape-mock";
import {
  getCorpusEvents,
  getTotalEventsInCorpus,
  getWindowExample,
} from "@/lib/te-mock/precedents-corpus-mock";
import { getPattern } from "@/lib/te-mock/patterns-v4-data";
import {
  loadCardV3,
  loadScores,
  FLEET_RUN_1_RECIPE_IDS,
} from "@/lib/te-data-contract/load";
import recipeTracker from "@/data/recipe-tracker.json";
import { cleanProseCopy } from "@/lib/clean-text";

import { PageLayout } from "@/components/precedents-v4-1/PageLayout";
import { familyColor as familyColorFn } from "@/lib/te-mock/l1-families";
import {
  IndicatorSetPanel,
  WindowPanel,
  DiscriminationPanel,
} from "@/components/precedents-v4-1/MinorPanels";
import { CalibrationPanel } from "@/components/precedents-v4-1/CalibrationPanel";
import { CountriesPanel } from "@/components/precedents-v4-1/CountriesPanel";
import { ReliabilityPanel } from "@/components/precedents-v4-1/ReliabilityPanel";
import { ScoreDistributionPanel } from "@/components/precedents-v4-1/ScoreDistributionPanel";
import { PrecedentsTimelinePanel } from "@/components/precedents-v4-1/PrecedentsTimelinePanel";
import { PatternAlignmentPanel } from "@/components/precedents-v4-1/PatternAlignmentPanel";
import { IndicatorSensitivityPanel } from "@/components/precedents-v4-1/IndicatorSensitivityPanel";
import {
  TrendNewsSignalPanel,
  TrendNewsComingSoonPanel,
} from "@/components/precedents-v4-1/TrendNewsSignalPanel";
import { getTrendNewsSignal } from "@/lib/hf/trend-signal";
import { ExpandableShell } from "@/components/te-v4-shared/ExpandableShell";

interface Params {
  params: Promise<{ slug: string }>;
}

interface RawTrackerRow {
  recipe_id: string;
  description_compelling?: string;
}

/**
 * Index `description_compelling` from the raw tracker JSON. Built at module
 * load so each detail render is a single Map lookup. Cascade-era recipes
 * carry the field directly on the row; TE recipes don't have a tracker row
 * (the tracker file pre-dates TE), so they fall through to the in-mock
 * definition. This is fine — TE recipes have hand-curated definitions in
 * CASCADE_MOCK_DATA where it matters and a generic fallback otherwise.
 */
const COMPELLING_BY_ID = new Map<string, string>();
for (const row of (recipeTracker as { recipes: RawTrackerRow[] }).recipes) {
  if (row.description_compelling) {
    COMPELLING_BY_ID.set(row.recipe_id, row.description_compelling);
  }
}

export async function generateStaticParams() {
  return getAllRecipes().map((r) => ({ slug: r.recipe_id }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { slug } = await params;
  const recipe = getRecipe(slug);
  return {
    title: recipe
      ? `${recipe.label} · Trends · QG Intelligence`
      : "Trend not found · QG Intelligence",
    description: recipe
      ? `${recipe.label} trend report card: the signals that move with it, precedents, validation, results.`
      : "Trend not found.",
  };
}

export default async function RecipeDetailV41Page({ params }: Params) {
  const { slug } = await params;
  const recipe = getRecipe(slug);
  if (!recipe) notFound();

  const mock = getMock(recipe);
  const extras = getRecipeV4Extras(slug) ?? getFallbackExtras(slug);
  const countriesFull = getCountriesFull(slug);
  const shapeData = getShapeData(slug);
  const corpusEvents = getCorpusEvents(slug);
  const totalEventsInCorpus = getTotalEventsInCorpus(slug);

  // News layer (HF merge step 3): the trend's primary theme x covered
  // countries. Null for news-blind trends -> the panel simply absent.
  const newsSignal = getTrendNewsSignal(slug);

  const demo = isDemoGraduated(recipe);
  const effectiveStatus = demo ? "graduated" : recipe.status;
  // V4.1 §0 (confidence-first) + #25: the Countries / Score-distribution /
  // Precedents panels should render whenever real scoring data exists, not
  // gate on `effectiveStatus === "graduated"`. A recipe that's "In play"
  // still has scored countries — withholding them undermines confidence.
  const showResults =
    effectiveStatus === "graduated" || (mock.countriesTop?.length ?? 0) > 0;
  const familyColor = familyColorFn(recipe.l1_id, recipe.l1_color);
  const hasTrajectory = !!getPattern(slug);

  // V4.1 §4: V4.1 status chip. Replaces "Tested, did not hold up" /
  // "Walked, not graduated" with "In play" — confident, true, not exposing.
  const v41StatusLabel = statusLabel(effectiveStatus);
  const v41StatusColor =
    v41StatusLabel.tone === "deployed"
      ? "#3FBF8F"
      : v41StatusLabel.tone === "failed"
        ? "#5B7E99"
        : v41StatusLabel.label === "Coming soon" ||
            v41StatusLabel.label === "Prior version"
          ? "#7A8FA0"
          : "#5B7E99";
  // 2026-05-30: chip JSX retired (founder ask). Kept the label + color
  // derivation above so the chip can drop back in here if a future
  // status (e.g., retired) needs surfacing. Suppress unused-var lint.
  void v41StatusColor;

  // V4.1 round-3 (2026-05-29): /recipe-tracker route deleted. The demo
  // pointer now lands on /blog/trend-tracker (renamed 2026-06-05) — the
  // audience-facing status board that preserves the corrections-log
  // narrative for the foreign_intervention vacate.
  const demoDisclosure = demo ? (
    <div
      data-tour="demo-disclosure"
      style={{
        padding: "8px 12px",
        border: `1px dashed ${familyColor}`,
        background: `${familyColor}11`,
        borderRadius: "4px",
        fontSize: "11.5px",
        lineHeight: 1.5,
        color: "var(--qgi-text-muted)",
        fontFamily: "ui-monospace, monospace",
        maxWidth: "780px",
      }}
    >
      Demo render of the fully-populated detail page. Latest program status lives on{" "}
      <Link href={"/blog/trend-tracker" as Route} style={{ color: familyColor }}>
        the Trend Tracker
      </Link>
      .
    </div>
  ) : null;

  // LOCO-AUC + CI for the discrimination panel.
  // Source: real card stats (ci95_lo / ci95_hi). Fleet-run-1 recipes carry
  // bootstrap CI from the pipeline bake. Cascade-only / queued recipes have
  // no card — render the point estimate only (honest empty state).
  const isTeRecipe = FLEET_RUN_1_RECIPE_IDS.includes(slug);
  let locoAuc: number | null = recipe.stats?.loco_auc ?? null;
  let ciLow: number | undefined;
  let ciHigh: number | undefined;
  // Round-2: 5-fold CV AUC from scores file top-level.
  let cvAucFull: number | null = null;
  // Window search range for WindowPanel: min/max of windows searched in the
  // greedy walk history. Not present on cascade-only recipes (undefined →
  // WindowPanel renders without the "Chosen from X–Y years" caption).
  let windowSearchMin: number | undefined;
  let windowSearchMax: number | undefined;
  // V4.1 §B.4: real Expected Calibration Error (run-2 bakes it; undefined on
  // older vintages / cascade-only recipes -> panel stays in its pending state).
  let calibrationEce: number | null | undefined;
  if (isTeRecipe) {
    try {
      const card = loadCardV3(slug);
      locoAuc = card.stats.loco_auc;
      ciLow = card.stats.ci95_lo;
      ciHigh = card.stats.ci95_hi;
      const windows = card.greedy_walk.history.map((h) => h.window);
      if (windows.length > 0) {
        windowSearchMin = Math.min(...windows);
        windowSearchMax = Math.max(...windows);
      }
      calibrationEce = (card as { calibration?: { ece?: number | null } }).calibration
        ?.ece;
    } catch {
      // Card unavailable — point estimate only; window range stays undefined.
    }
    try {
      const sf = loadScores(slug);
      cvAucFull = sf.cv_auc_full ?? null;
    } catch {
      // Scores unavailable — cvAucFull stays null.
    }
  }

  const enrichedIndicators =
    extras.indicators.length > 0
      ? extras.indicators
      : mock.indicators.map((i) => ({
          ...i,
          shapWeightPct: 100 / Math.max(1, mock.indicators.length),
          aucDrop: 0,
        }));

  const recipeWithColor = { ...recipe, l1_color: familyColor };

  // V4.1 §A1 — prefer the compelling description; fall through to the
  // dry mock definition for back-compat (TE recipes without a tracker row).
  const heroDefinition = cleanProseCopy(COMPELLING_BY_ID.get(slug) ?? mock.definition);

  return (
    <PageLayout
      recipe={recipeWithColor}
      // 2026-05-30: status chip removed from the recipe header (founder
      // ask). The chip + tone-color logic above stays in case we want to
      // re-attach somewhere subtler in the page later. PageLayout now
      // omits the chip slot entirely when statusChip is null.
      statusChip={null}
      subtitle={`${enrichedIndicators.length} signals · ${mock.window}y window`}
      definition={heroDefinition}
      demoDisclosure={demoDisclosure}
      headerRightSlot={<HowToReadButton routeKey="recipes-v4.1-detail" />}
    >
      {/*
        Panel order (rows at the 3-column desktop width):
          1. STRUCTURE   What is driving this trend (wide) · Optimal Window
          2. PRECEDENTS  the real events this trend was built from
                         (full-width, expanded by default)
          3. RESULTS     Countries · Score Distribution · Trajectory Alignment
          4. VALIDATION  Indicator Sensitivity · Discrimination · Reliability
          5. CALIBRATION Calibration

        2026-06-04 (founder): Identity Card removed; row order reworked so the
        results lead the lower half and Calibration closes the page.
      */}

      {/* 1. STRUCTURE */}
      <IndicatorSetPanel familyColor={familyColor} indicators={enrichedIndicators} wide />
      <WindowPanel
        familyColor={familyColor}
        windowYears={mock.window}
        trendName={recipe.label}
        example={getWindowExample(slug)}
        ciLow={windowSearchMin}
        ciHigh={windowSearchMax}
      />

      {/* 2. PRECEDENTS — the real-world events that built this trend, led with
          and expanded by default so the human anchor reads early. */}
      <ExpandableShell familyColor={familyColor} label="Precedents" defaultExpanded>
        <PrecedentsTimelinePanel
          familyColor={familyColor}
          events={corpusEvents}
          totalEventsInCorpus={totalEventsInCorpus || (mock.nPositives ?? 0)}
        />
      </ExpandableShell>

      {/* 2b. NEWS SIGNAL: where the news is running with this trend right
          now (HF merge step 3). Absent for news-blind trends. Coming-soon
          trends (no native GDELT feed yet) get the compact placeholder
          instead of the XY quadrant / news-only list. */}
      {newsSignal &&
        (newsSignal.status === "coming_soon" ? (
          <TrendNewsComingSoonPanel key={`news-soon-${slug}`} trendLabel={recipe.label} />
        ) : (
          <TrendNewsSignalPanel
            key={`news-${slug}`}
            slug={slug}
            trendLabel={recipe.label}
            signal={newsSignal}
          />
        ))}

      {/* 3. RESULTS (what does it find) + the shape it aligns to */}
      <CountriesPanel
        familyColor={familyColor}
        countriesTop={mock.countriesTop}
        countriesBottom={extras.countriesBottom}
        countriesFull={countriesFull}
        showResults={showResults}
        recipeId={recipe.recipe_id}
      />
      <ExpandableShell familyColor={familyColor} label="Score Distribution">
        <ScoreDistributionPanel
          familyColor={familyColor}
          histogram={extras.distribution.histogram}
          median={extras.distribution.median}
          p90={extras.distribution.p90}
          p99={extras.distribution.p99}
          max={extras.distribution.max}
          countriesFull={countriesFull}
        />
      </ExpandableShell>
      <ExpandableShell familyColor={familyColor} label="Trajectory Alignment">
        <PatternAlignmentPanel
          familyColor={familyColor}
          recipeId={recipe.recipe_id}
          windowYears={mock.window}
          indicators={enrichedIndicators}
          shapeData={shapeData}
          hasTrajectory={hasTrajectory}
        />
      </ExpandableShell>

      {/* 4. VALIDATION (does it work) */}
      <ExpandableShell familyColor={familyColor} label="Indicator Sensitivity">
        <IndicatorSensitivityPanel
          familyColor={familyColor}
          indicators={enrichedIndicators.map((i) => ({
            code: i.code,
            name: i.name,
            provider: i.provider,
            aucDrop: i.aucDrop,
          }))}
        />
      </ExpandableShell>
      <DiscriminationPanel
        familyColor={familyColor}
        locoAuc={locoAuc}
        ciLow={ciLow}
        ciHigh={ciHigh}
        showResults={showResults}
        cvAucFull={cvAucFull}
      />
      <ReliabilityPanel
        familyColor={familyColor}
        v1SeparationPp={extras.reliability.v1SeparationPp}
        v4OotRecallPct={extras.reliability.v4OotRecallPct}
        walksCompleted={extras.reliability.walksCompleted}
        verdict={extras.reliability.verdict}
      />

      {/* 5. CALIBRATION */}
      <CalibrationPanel
        familyColor={familyColor}
        showCalibrationData={typeof calibrationEce === "number"}
        ece={calibrationEce ?? undefined}
      />
    </PageLayout>
  );
}
