/**
 * Tiny stats helpers for the frontend (#125).
 *
 * The QGI pipeline computes Pearson r for every SCDI but doesn't persist a
 * p-value. We compute it on the fly here from (r, n) using the standard
 * Student-t approximation. This mirrors the logic in scdi-finder's
 * pearson_pvalues_vectorized but in pure TypeScript with no scipy.
 */

/**
 * Two-tailed p-value for a Pearson correlation coefficient.
 * @param r Pearson correlation coefficient (-1..1)
 * @param n Number of observations the correlation was computed over
 * @returns Two-tailed p-value in [0, 1], or NaN if inputs are degenerate
 */
export function pearsonPValue(r: number, n: number): number {
  if (!Number.isFinite(r) || !Number.isFinite(n)) return NaN;
  if (n <= 2) return NaN;
  // Clamp to avoid divide-by-zero at |r| == 1
  const rSafe = Math.max(-0.9999999, Math.min(0.9999999, r));
  const df = n - 2;
  const t = rSafe * Math.sqrt(df / (1 - rSafe * rSafe));
  // Two-tailed survival function of Student-t at |t|
  return 2 * studentTSF(Math.abs(t), df);
}

/**
 * Student-t survival function (1 - CDF) at x for `df` degrees of freedom.
 * Closed-form via the regularized incomplete beta function. This is what
 * scipy.stats.t.sf does under the hood; we approximate with a continued-
 * fraction expansion of the incomplete beta. Accurate to ~1e-10 for the
 * df ranges QGI cares about (df = 1..1000).
 */
function studentTSF(x: number, df: number): number {
  // sf(x) = 0.5 * I_{df/(df+x^2)}(df/2, 1/2)
  const xt = df / (df + x * x);
  return 0.5 * regularizedIncompleteBeta(xt, df / 2, 0.5);
}

/**
 * Regularized incomplete beta function I_x(a, b) via Lentz's continued
 * fraction. Adapted from Numerical Recipes 6.4.
 */
function regularizedIncompleteBeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lnBeta =
    logGamma(a + b) - logGamma(a) - logGamma(b) + a * Math.log(x) + b * Math.log(1 - x);
  if (x < (a + 1) / (a + b + 2)) {
    return (Math.exp(lnBeta) * betacf(x, a, b)) / a;
  }
  return 1 - (Math.exp(lnBeta) * betacf(1 - x, b, a)) / b;
}

function betacf(x: number, a: number, b: number): number {
  const MAXIT = 200;
  const EPS = 3e-15;
  const FPMIN = 1e-300;
  const qab = a + b;
  const qap = a + 1;
  const qam = a - 1;
  let c = 1;
  let d = 1 - (qab * x) / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= MAXIT; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}

/** Lanczos approximation of ln(Γ(x)) — accurate to ~1e-15. */
function logGamma(x: number): number {
  const cof = [
    76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155,
    0.001208650973866179, -5.395239384953e-6,
  ];
  let y = x;
  let tmp = x + 5.5;
  tmp -= (x + 0.5) * Math.log(tmp);
  let ser = 1.000000000190015;
  for (let j = 0; j < 6; j++) ser += cof[j] / ++y;
  return -tmp + Math.log((2.5066282746310005 * ser) / x);
}

/**
 * Format a p-value for display: scientific notation under 1e-3, fixed
 * decimals otherwise.
 */
export function formatPValue(p: number): string {
  if (!Number.isFinite(p)) return "—";
  if (p < 1e-15) return "< 1e-15";
  if (p < 1e-3) return p.toExponential(1);
  return p.toFixed(3);
}

/**
 * Significance label for a p-value.
 */
export function significanceLabel(p: number): "***" | "**" | "*" | "ns" | "—" {
  if (!Number.isFinite(p)) return "—";
  if (p < 0.001) return "***";
  if (p < 0.01) return "**";
  if (p < 0.05) return "*";
  return "ns";
}

/**
 * Pearson correlation between two arrays of numbers, ignoring positions
 * where either side is NaN/null/undefined. Returns the (r, n) pair so that
 * downstream code can compute p-values via pearsonPValue.
 */
export function pearsonCorrelation(
  a: ReadonlyArray<number | null | undefined>,
  b: ReadonlyArray<number | null | undefined>
): { r: number; n: number } {
  const n = Math.min(a.length, b.length);
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < n; i++) {
    const x = a[i];
    const y = b[i];
    if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) continue;
    xs.push(x);
    ys.push(y);
  }
  const m = xs.length;
  if (m < 2) return { r: NaN, n: m };
  let sx = 0;
  let sy = 0;
  for (let i = 0; i < m; i++) {
    sx += xs[i];
    sy += ys[i];
  }
  const mx = sx / m;
  const my = sy / m;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (let i = 0; i < m; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  const denom = Math.sqrt(sxx * syy);
  if (denom === 0) return { r: NaN, n: m };
  return { r: sxy / denom, n: m };
}
