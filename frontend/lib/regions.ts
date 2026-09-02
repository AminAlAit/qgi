/**
 * Static country-to-region mapping for the Signals page.
 *
 * Maps ISO 3166-1 alpha-2 codes to one of 6 macro-regions.
 * Covers all 126 countries currently in country-risks.json.
 * Add new entries here when new countries appear in the scoring output.
 */

export type Region = "Africa" | "Americas" | "Asia" | "Europe" | "MENA" | "Oceania";

export const REGIONS: Region[] = [
  "Africa",
  "Americas",
  "Asia",
  "Europe",
  "MENA",
  "Oceania",
];

export const COUNTRY_REGIONS: Record<string, Region> = {
  // ── Africa ────────────────────────────────────────────────────────────
  AO: "Africa", // Angola
  CF: "Africa", // Central African Republic
  CI: "Africa", // Cote d'Ivoire
  CM: "Africa", // Cameroon
  ER: "Africa", // Eritrea
  ET: "Africa", // Ethiopia
  GH: "Africa", // Ghana
  KE: "Africa", // Kenya
  MG: "Africa", // Madagascar
  ML: "Africa", // Mali
  MR: "Africa", // Mauritania
  MZ: "Africa", // Mozambique
  NG: "Africa", // Nigeria
  SO: "Africa", // Somalia
  SD: "Africa", // Sudan
  TD: "Africa", // Chad
  ZA: "Africa", // South Africa

  // ── Americas ──────────────────────────────────────────────────────────
  AR: "Americas", // Argentina
  BO: "Americas", // Bolivia
  BR: "Americas", // Brazil
  CA: "Americas", // Canada
  CL: "Americas", // Chile
  CO: "Americas", // Colombia
  CR: "Americas", // Costa Rica
  CU: "Americas", // Cuba
  DO: "Americas", // Dominican Republic
  EC: "Americas", // Ecuador
  GT: "Americas", // Guatemala
  HN: "Americas", // Honduras
  HT: "Americas", // Haiti
  JM: "Americas", // Jamaica
  MX: "Americas", // Mexico
  NI: "Americas", // Nicaragua
  PE: "Americas", // Peru
  SV: "Americas", // El Salvador
  US: "Americas", // United States

  // ── Asia ──────────────────────────────────────────────────────────────
  AF: "Asia", // Afghanistan
  BD: "Asia", // Bangladesh
  BN: "Asia", // Brunei
  CN: "Asia", // China
  ID: "Asia", // Indonesia
  IN: "Asia", // India
  JP: "Asia", // Japan
  KG: "Asia", // Kyrgyzstan
  KH: "Asia", // Cambodia
  KP: "Asia", // North Korea
  KR: "Asia", // South Korea
  KZ: "Asia", // Kazakhstan
  LA: "Asia", // Laos
  LK: "Asia", // Sri Lanka
  MM: "Asia", // Myanmar
  MN: "Asia", // Mongolia
  MV: "Asia", // Maldives
  MY: "Asia", // Malaysia
  NP: "Asia", // Nepal
  PH: "Asia", // Philippines
  PK: "Asia", // Pakistan
  SG: "Asia", // Singapore
  TH: "Asia", // Thailand
  TJ: "Asia", // Tajikistan
  TM: "Asia", // Turkmenistan
  UZ: "Asia", // Uzbekistan
  VN: "Asia", // Vietnam

  // ── Europe ────────────────────────────────────────────────────────────
  AL: "Europe", // Albania
  AM: "Europe", // Armenia
  AT: "Europe", // Austria
  AZ: "Europe", // Azerbaijan
  BA: "Europe", // Bosnia and Herzegovina
  BE: "Europe", // Belgium
  BG: "Europe", // Bulgaria
  BY: "Europe", // Belarus
  CH: "Europe", // Switzerland
  CY: "Europe", // Cyprus
  CZ: "Europe", // Czech Republic
  DE: "Europe", // Germany
  DK: "Europe", // Denmark
  EE: "Europe", // Estonia
  ES: "Europe", // Spain
  FI: "Europe", // Finland
  FR: "Europe", // France
  GB: "Europe", // United Kingdom
  GE: "Europe", // Georgia
  GR: "Europe", // Greece
  HR: "Europe", // Croatia
  HU: "Europe", // Hungary
  IE: "Europe", // Ireland
  IS: "Europe", // Iceland
  IT: "Europe", // Italy
  LT: "Europe", // Lithuania
  LU: "Europe", // Luxembourg
  LV: "Europe", // Latvia
  MD: "Europe", // Moldova
  ME: "Europe", // Montenegro
  MK: "Europe", // North Macedonia
  MT: "Europe", // Malta
  NL: "Europe", // Netherlands
  NO: "Europe", // Norway
  PL: "Europe", // Poland
  PT: "Europe", // Portugal
  RO: "Europe", // Romania
  RU: "Europe", // Russia
  SE: "Europe", // Sweden
  SI: "Europe", // Slovenia
  SK: "Europe", // Slovakia
  TR: "Europe", // Turkey
  UA: "Europe", // Ukraine

  // ── MENA (Middle East & North Africa) ─────────────────────────────────
  AE: "MENA", // United Arab Emirates
  BH: "MENA", // Bahrain
  DZ: "MENA", // Algeria
  EG: "MENA", // Egypt
  IL: "MENA", // Israel
  IQ: "MENA", // Iraq
  IR: "MENA", // Iran
  JO: "MENA", // Jordan
  KW: "MENA", // Kuwait
  LB: "MENA", // Lebanon
  LY: "MENA", // Libya
  MA: "MENA", // Morocco
  OM: "MENA", // Oman
  PS: "MENA", // Palestine
  QA: "MENA", // Qatar
  SA: "MENA", // Saudi Arabia
  SY: "MENA", // Syria
  TN: "MENA", // Tunisia
  YE: "MENA", // Yemen

  // ── Oceania ───────────────────────────────────────────────────────────
  AU: "Oceania", // Australia
  NZ: "Oceania", // New Zealand
};

/** Get the region for an alpha-2 code. Returns undefined if not mapped. */
export function getRegion(alpha2: string): Region | undefined {
  return COUNTRY_REGIONS[alpha2?.toUpperCase()];
}
