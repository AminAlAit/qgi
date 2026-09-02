/**
 * country-iso2 — name → ISO-3166-1 alpha-2 (lowercase) lookup.
 *
 * Companion to country-flags.ts. We keep the emoji codepoint in mock data
 * (used for ARIA / fallback), but the visible flag on the page is an
 * <img src="https://flagcdn.com/16x12/<iso2>.png" /> — Windows 10 ships no
 * font that renders regional-indicator pairs as actual flags, and falling
 * back to "UA"/"YE"/"SD" letter pairs looked broken on the founder's
 * browser (#162 part B, 2026-05-27).
 *
 * Lowercase to match flagcdn.com's path convention.
 *
 * Mockup-only — when the bake ships per-country JSONs the ISO code will
 * come from `countries/<iso>.json#iso2` directly.
 *
 * — Daniyar Bekmurat, Comparative Historical Pattern Matching
 */

const ISO2: Record<string, string> = {
  // Events that actually appear in precedents-corpus-mock.ts ──────────────
  Ukraine: "ua",
  Yemen: "ye",
  Syria: "sy",
  Libya: "ly",
  "Central African Republic": "cf",
  Sudan: "sd",
  Niger: "ne",
  Lebanon: "lb",
  Mali: "ml",
  "Burkina Faso": "bf",
  Ethiopia: "et",
  Myanmar: "mm",
  Mozambique: "mz",
  Chile: "cl",
  Tunisia: "tn",
  Kenya: "ke",
  Bolivia: "bo",

  // Broader roster — keep aligned with country-flags.ts so the same util
  // can be reused by adjacent panels if they later switch to img flags.
  // MENA
  Iran: "ir",
  Iraq: "iq",
  Israel: "il",
  "Saudi Arabia": "sa",
  Qatar: "qa",
  Egypt: "eg",
  Morocco: "ma",
  Algeria: "dz",
  Jordan: "jo",
  Turkey: "tr",
  // Africa
  "South Sudan": "ss",
  Eritrea: "er",
  Somalia: "so",
  Uganda: "ug",
  Rwanda: "rw",
  Burundi: "bi",
  DRC: "cd",
  "Congo, DRC": "cd",
  CAR: "cf",
  Guinea: "gn",
  Senegal: "sn",
  Cameroon: "cm",
  Nigeria: "ng",
  Ghana: "gh",
  Angola: "ao",
  "Equatorial Guinea": "gq",
  Zambia: "zm",
  "South Africa": "za",
  Madagascar: "mg",
  "Sierra Leone": "sl",
  // Asia
  Pakistan: "pk",
  Afghanistan: "af",
  India: "in",
  "Sri Lanka": "lk",
  Bangladesh: "bd",
  Nepal: "np",
  Bhutan: "bt",
  China: "cn",
  "North Korea": "kp",
  "South Korea": "kr",
  Japan: "jp",
  Mongolia: "mn",
  Taiwan: "tw",
  Vietnam: "vn",
  Cambodia: "kh",
  Laos: "la",
  Thailand: "th",
  Indonesia: "id",
  Philippines: "ph",
  Malaysia: "my",
  Singapore: "sg",
  "Myanmar (2011-15)": "mm",
  // Central Asia
  Kazakhstan: "kz",
  Uzbekistan: "uz",
  Turkmenistan: "tm",
  Tajikistan: "tj",
  Kyrgyzstan: "kg",
  // Caucasus
  Armenia: "am",
  Azerbaijan: "az",
  Georgia: "ge",
  // Europe (East)
  Russia: "ru",
  Belarus: "by",
  Moldova: "md",
  Poland: "pl",
  "Czech Republic": "cz",
  Hungary: "hu",
  Slovakia: "sk",
  Romania: "ro",
  Bulgaria: "bg",
  Croatia: "hr",
  Serbia: "rs",
  Albania: "al",
  "North Macedonia": "mk",
  "Bosnia and Herzegovina": "ba",
  Slovenia: "si",
  Estonia: "ee",
  Latvia: "lv",
  Lithuania: "lt",
  // Europe (West)
  France: "fr",
  Germany: "de",
  "United Kingdom": "gb",
  Ireland: "ie",
  Iceland: "is",
  Norway: "no",
  Sweden: "se",
  Finland: "fi",
  Denmark: "dk",
  Netherlands: "nl",
  Belgium: "be",
  Switzerland: "ch",
  Austria: "at",
  Italy: "it",
  Spain: "es",
  Portugal: "pt",
  Greece: "gr",
  Cyprus: "cy",
  // Americas
  "United States": "us",
  Canada: "ca",
  Mexico: "mx",
  Argentina: "ar",
  Brazil: "br",
  Colombia: "co",
  Ecuador: "ec",
  Peru: "pe",
  Venezuela: "ve",
  Uruguay: "uy",
  Paraguay: "py",
  Cuba: "cu",
  Nicaragua: "ni",
  Honduras: "hn",
  Guatemala: "gt",
  "El Salvador": "sv",
  "Costa Rica": "cr",
  // Other / Special
  "Hong Kong": "hk",
};

// Additional entries to cover TE sample-10 country corpus + flag gaps
// surfaced during the V4.1 polish pass (2026-05-29 — founder #27).
Object.assign(ISO2, {
  "Trinidad And Tobago": "tt",
  "Papua New Guinea": "pg",
  "North Korea": "kp",
  Kuwait: "kw",
  "Trinidad and Tobago": "tt",
  // ─── Africa: missing gaps ────────────────────────────────────────────
  "Ivory Coast": "ci",
  "Côte d'Ivoire": "ci",
  "Cote d'Ivoire": "ci",
  Benin: "bj",
  Togo: "tg",
  Liberia: "lr",
  Gambia: "gm",
  "Guinea-Bissau": "gw",
  "Cape Verde": "cv",
  "Cabo Verde": "cv",
  Mauritania: "mr",
  Tanzania: "tz",
  Mozambique: "mz",
  Zimbabwe: "zw",
  Botswana: "bw",
  Namibia: "na",
  Lesotho: "ls",
  Eswatini: "sz",
  Malawi: "mw",
  Comoros: "km",
  Djibouti: "dj",
  "São Tomé and Príncipe": "st",
  "Sao Tome and Principe": "st",
  Mauritius: "mu",
  Seychelles: "sc",
  Gabon: "ga",
  Chad: "td",
  "Republic of Congo": "cg",
  "Republic of the Congo": "cg",
  Congo: "cg",
  "Central African Republic": "cf",
  Mali: "ml",
  "Burkina Faso": "bf",
  Niger: "ne",
  // ─── Middle East: missing gaps ───────────────────────────────────────
  "United Arab Emirates": "ae",
  Bahrain: "bh",
  Oman: "om",
  Yemen: "ye",
  Palestine: "ps",
  "West Bank and Gaza": "ps",
  // ─── Asia: missing gaps ──────────────────────────────────────────────
  Maldives: "mv",
  Bhutan: "bt",
  Brunei: "bn",
  "Timor-Leste": "tl",
  "East Timor": "tl",
  Myanmar: "mm",
  // ─── Europe: missing gaps ────────────────────────────────────────────
  Luxembourg: "lu",
  Malta: "mt",
  Liechtenstein: "li",
  Monaco: "mc",
  "San Marino": "sm",
  "Vatican City": "va",
  Andorra: "ad",
  Ukraine: "ua",
  Montenegro: "me",
  Kosovo: "xk",
  // ─── Americas: missing gaps ──────────────────────────────────────────
  Bolivia: "bo",
  Chile: "cl",
  Suriname: "sr",
  Guyana: "gy",
  "Dominican Republic": "do",
  Haiti: "ht",
  Jamaica: "jm",
  Barbados: "bb",
  Belize: "bz",
  Panama: "pa",
  Bahamas: "bs",
  "The Bahamas": "bs",
  // ─── Oceania ─────────────────────────────────────────────────────────
  Australia: "au",
  "New Zealand": "nz",
  Fiji: "fj",
  Samoa: "ws",
  Tonga: "to",
  Vanuatu: "vu",
  // ─── Other / Special ────────────────────────────────────────────────
  Tunisia: "tn",
  Algeria: "dz",
  Morocco: "ma",
  Libya: "ly",
  Egypt: "eg",
});

/**
 * Resolve a country display-name to its ISO-3166-1 alpha-2 code
 * (lowercase, matching flagcdn.com's path convention). Returns
 * empty string for unknown names so callers can branch on falsy.
 */
export function iso2For(name: string): string {
  return ISO2[name] ?? "";
}

/**
 * Map of lowercased country name → iso2 code.
 * Used by precedents-corpus-mock.ts and other adapters for fast lookup.
 */
export const NAME_TO_ISO2 = new Map<string, string>(
  Object.entries(ISO2).map(([name, code]) => [name.toLowerCase(), code])
);

/**
 * Derive a flag emoji from an ISO-3166-1 alpha-2 code (lowercase).
 * Formula: regional indicator symbol letters = code.charCodeAt(i) - 97 + 0x1F1E6.
 */
export function flagFromIso2(iso2: string): string {
  if (!iso2 || iso2.length < 2) return "";
  const a = iso2.charCodeAt(0) - 97 + 0x1f1e6;
  const b = iso2.charCodeAt(1) - 97 + 0x1f1e6;
  return String.fromCodePoint(a, b);
}
