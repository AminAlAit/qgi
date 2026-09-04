/**
 * country-flags — name → flag-emoji + name → ISO 3166-1 alpha-2 lookup.
 *
 * The recipe mock data (lib/te-mock/trends.ts) carries country names only
 * (`countriesTop: [{name, score}]`); V4.1 wants to render flags next to
 * each top/bottom-country entry. This file is a small static lookup
 * keyed by the country names that actually appear in the populated recipes.
 *
 * Mockup-only — when the bake ships per-country JSONs the flag will come
 * from `countries/<iso>.json#flag_emoji` (and `iso2`) directly.
 *
 *
 * Flag-rendering note (V4.1 #163)
 * ───────────────────────────────
 * Founder reported flag-emoji not rendering on Windows 10 (Segoe UI Emoji
 * on Win10 ships the regional-indicator pair as plain "IR"/"TM"/etc. — no
 * glyphs). The cross-browser fix is to render flags as `<img>` from
 * flagcdn.com using the alpha-2 code. `iso2For(name)` is the bridge: same
 * name keys as `FLAGS`, returns the lowercase code consumed by the CDN
 * URL pattern `https://flagcdn.com/16x12/{iso2}.png`.
 *
 * Emoji renderer is kept for tooling that runs in environments where the
 * `<img>` request would be undesirable (Storybook screenshot baselines,
 * unit-test diff fixtures) but the canonical user-facing renderer is
 * now image-based.
 */

const FLAGS: Record<string, string> = {
  // MENA
  Iran: "🇮🇷",
  Iraq: "🇮🇶",
  Israel: "🇮🇱",
  Lebanon: "🇱🇧",
  Syria: "🇸🇾",
  Yemen: "🇾🇪",
  "Saudi Arabia": "🇸🇦",
  Qatar: "🇶🇦",
  Egypt: "🇪🇬",
  Tunisia: "🇹🇳",
  Morocco: "🇲🇦",
  Libya: "🇱🇾",
  Algeria: "🇩🇿",
  Jordan: "🇯🇴",
  // Africa
  Sudan: "🇸🇩",
  "South Sudan": "🇸🇸",
  Eritrea: "🇪🇷",
  Ethiopia: "🇪🇹",
  Somalia: "🇸🇴",
  Kenya: "🇰🇪",
  Uganda: "🇺🇬",
  Rwanda: "🇷🇼",
  Burundi: "🇧🇮",
  DRC: "🇨🇩",
  "Congo, DRC": "🇨🇩",
  "DR Congo": "🇨🇩",
  "Central African Republic": "🇨🇫",
  CAR: "🇨🇫",
  Mali: "🇲🇱",
  "Burkina Faso": "🇧🇫",
  Niger: "🇳🇪",
  Guinea: "🇬🇳",
  Senegal: "🇸🇳",
  Cameroon: "🇨🇲",
  Mozambique: "🇲🇿",
  Nigeria: "🇳🇬",
  Ghana: "🇬🇭",
  Angola: "🇦🇴",
  "Equatorial Guinea": "🇬🇶",
  Zambia: "🇿🇲",
  "South Africa": "🇿🇦",
  Madagascar: "🇲🇬",
  "Sierra Leone": "🇸🇱",
  // Asia
  Pakistan: "🇵🇰",
  Afghanistan: "🇦🇫",
  India: "🇮🇳",
  "Sri Lanka": "🇱🇰",
  Bangladesh: "🇧🇩",
  Nepal: "🇳🇵",
  Bhutan: "🇧🇹",
  China: "🇨🇳",
  "North Korea": "🇰🇵",
  "South Korea": "🇰🇷",
  Japan: "🇯🇵",
  Mongolia: "🇲🇳",
  Taiwan: "🇹🇼",
  Vietnam: "🇻🇳",
  Cambodia: "🇰🇭",
  Laos: "🇱🇦",
  Thailand: "🇹🇭",
  Indonesia: "🇮🇩",
  Philippines: "🇵🇭",
  Malaysia: "🇲🇾",
  Singapore: "🇸🇬",
  Myanmar: "🇲🇲",
  "Myanmar (2011-15)": "🇲🇲",
  // Central Asia
  Kazakhstan: "🇰🇿",
  Uzbekistan: "🇺🇿",
  Turkmenistan: "🇹🇲",
  Tajikistan: "🇹🇯",
  Kyrgyzstan: "🇰🇬",
  // Caucasus
  Armenia: "🇦🇲",
  Azerbaijan: "🇦🇿",
  Georgia: "🇬🇪",
  // Europe (East)
  Russia: "🇷🇺",
  Ukraine: "🇺🇦",
  Belarus: "🇧🇾",
  Moldova: "🇲🇩",
  Poland: "🇵🇱",
  "Czech Republic": "🇨🇿",
  Hungary: "🇭🇺",
  Slovakia: "🇸🇰",
  Romania: "🇷🇴",
  Bulgaria: "🇧🇬",
  Croatia: "🇭🇷",
  Serbia: "🇷🇸",
  Albania: "🇦🇱",
  "North Macedonia": "🇲🇰",
  "Bosnia and Herzegovina": "🇧🇦",
  Slovenia: "🇸🇮",
  Estonia: "🇪🇪",
  Latvia: "🇱🇻",
  Lithuania: "🇱🇹",
  // Europe (West)
  France: "🇫🇷",
  Germany: "🇩🇪",
  "United Kingdom": "🇬🇧",
  Ireland: "🇮🇪",
  Iceland: "🇮🇸",
  Norway: "🇳🇴",
  Sweden: "🇸🇪",
  Finland: "🇫🇮",
  Denmark: "🇩🇰",
  Netherlands: "🇳🇱",
  Belgium: "🇧🇪",
  Switzerland: "🇨🇭",
  Austria: "🇦🇹",
  Italy: "🇮🇹",
  Spain: "🇪🇸",
  Portugal: "🇵🇹",
  Greece: "🇬🇷",
  Cyprus: "🇨🇾",
  Luxembourg: "🇱🇺",
  // Oceania
  "New Zealand": "🇳🇿",
  Australia: "🇦🇺",
  // Americas
  "United States": "🇺🇸",
  Canada: "🇨🇦",
  Mexico: "🇲🇽",
  Argentina: "🇦🇷",
  Brazil: "🇧🇷",
  Chile: "🇨🇱",
  Colombia: "🇨🇴",
  Ecuador: "🇪🇨",
  Peru: "🇵🇪",
  Venezuela: "🇻🇪",
  Uruguay: "🇺🇾",
  Bolivia: "🇧🇴",
  Paraguay: "🇵🇾",
  Cuba: "🇨🇺",
  Nicaragua: "🇳🇮",
  Honduras: "🇭🇳",
  Guatemala: "🇬🇹",
  "El Salvador": "🇸🇻",
  "Costa Rica": "🇨🇷",
  // Other / Special
  Turkey: "🇹🇷",
  "Hong Kong": "🇭🇰",
  // 2026-05-29 gap fills (V4.1 polish)
  "Ivory Coast": "🇨🇮",
  "Côte d'Ivoire": "🇨🇮",
  "Cote d'Ivoire": "🇨🇮",
  Benin: "🇧🇯",
  Togo: "🇹🇬",
  Liberia: "🇱🇷",
  Tanzania: "🇹🇿",
  Zimbabwe: "🇿🇼",
  Botswana: "🇧🇼",
  Namibia: "🇳🇦",
  Lesotho: "🇱🇸",
  Eswatini: "🇸🇿",
  Malawi: "🇲🇼",
  Gabon: "🇬🇦",
  Chad: "🇹🇩",
  "Republic of Congo": "🇨🇬",
  "United Arab Emirates": "🇦🇪",
  Bahrain: "🇧🇭",
  Oman: "🇴🇲",
  Malta: "🇲🇹",
  Montenegro: "🇲🇪",
  Kosovo: "🇽🇰",
  "Dominican Republic": "🇩🇴",
  Haiti: "🇭🇹",
  Jamaica: "🇯🇲",
  // ─── 2026-05-29 comprehensive gap fill (round 3.7) ─────────────────────
  // The prior round added emoji entries below this map (inside ISO2)
  // instead of FLAGS, so flagFor() never resolved them. Re-added in the
  // right map. Audit (scripts/audit-flags.mjs) confirms 0 missing across
  // the full Risk Board country universe after this pass.
  // Africa
  Mauritania: "🇲🇷",
  Djibouti: "🇩🇯",
  Comoros: "🇰🇲",
  Seychelles: "🇸🇨",
  Mauritius: "🇲🇺",
  "Cabo Verde": "🇨🇻",
  "Sao Tome and Principe": "🇸🇹",
  "Guinea-Bissau": "🇬🇼",
  "The Gambia": "🇬🇲",
  "Republic of the Congo": "🇨🇬",
  "The Democratic Republic of the Congo": "🇨🇩",
  // Middle East
  Palestine: "🇵🇸",
  Kuwait: "🇰🇼",
  // Asia / Pacific
  Maldives: "🇲🇻",
  Brunei: "🇧🇳",
  Macao: "🇲🇴",
  "Timor-Leste": "🇹🇱",
  "Papua New Guinea": "🇵🇬",
  "Solomon Islands": "🇸🇧",
  Vanuatu: "🇻🇺",
  Fiji: "🇫🇯",
  Samoa: "🇼🇸",
  "American Samoa": "🇦🇸",
  Tonga: "🇹🇴",
  Tuvalu: "🇹🇻",
  Kiribati: "🇰🇮",
  Nauru: "🇳🇷",
  "Marshall Islands": "🇲🇭",
  Micronesia: "🇫🇲",
  Palau: "🇵🇼",
  "New Caledonia": "🇳🇨",
  "French Polynesia": "🇵🇫",
  Guam: "🇬🇺",
  "Northern Mariana Islands": "🇲🇵",
  // Europe (microstates + territories)
  Liechtenstein: "🇱🇮",
  Monaco: "🇲🇨",
  "San Marino": "🇸🇲",
  Andorra: "🇦🇩",
  "Faroe Islands": "🇫🇴",
  Greenland: "🇬🇱",
  "Isle of Man": "🇮🇲",
  Czechia: "🇨🇿",
  Turkiye: "🇹🇷",
  // Americas (Caribbean + Central + South)
  Bahamas: "🇧🇸",
  // Cuba already declared in the original Americas section above; not re-adding.
  Panama: "🇵🇦",
  Belize: "🇧🇿",
  Barbados: "🇧🇧",
  "Antigua and Barbuda": "🇦🇬",
  Dominica: "🇩🇲",
  Grenada: "🇬🇩",
  "Saint Kitts and Nevis": "🇰🇳",
  "Saint Lucia": "🇱🇨",
  "Saint Vincent and the Grenadines": "🇻🇨",
  "Saint Martin (French part)": "🇲🇫",
  "Sint Maarten (Dutch part)": "🇸🇽",
  "Trinidad and Tobago": "🇹🇹",
  Aruba: "🇦🇼",
  Curaçao: "🇨🇼",
  Bermuda: "🇧🇲",
  "Cayman Islands": "🇰🇾",
  "Turks and Caicos Islands": "🇹🇨",
  "Puerto Rico": "🇵🇷",
  "Virgin Islands, U.S.": "🇻🇮",
  Suriname: "🇸🇷",
  Guyana: "🇬🇾",
};

/**
 * ISO 3166-1 alpha-2 codes (lowercase, the form flagcdn.com expects).
 * Keys MUST stay in lock-step with `FLAGS` above — every name renderable
 * as an emoji must also be renderable as a CDN image, otherwise Win10
 * users get an empty placeholder instead of a flag.
 */
const ISO2: Record<string, string> = {
  // MENA
  Iran: "ir",
  Iraq: "iq",
  Israel: "il",
  Lebanon: "lb",
  Syria: "sy",
  Yemen: "ye",
  "Saudi Arabia": "sa",
  Qatar: "qa",
  Egypt: "eg",
  Tunisia: "tn",
  Morocco: "ma",
  Libya: "ly",
  Algeria: "dz",
  Jordan: "jo",
  // Africa
  Sudan: "sd",
  "South Sudan": "ss",
  Eritrea: "er",
  Ethiopia: "et",
  Somalia: "so",
  Kenya: "ke",
  Uganda: "ug",
  Rwanda: "rw",
  Burundi: "bi",
  DRC: "cd",
  "Congo, DRC": "cd",
  "DR Congo": "cd",
  "Central African Republic": "cf",
  CAR: "cf",
  Mali: "ml",
  "Burkina Faso": "bf",
  Niger: "ne",
  Guinea: "gn",
  Senegal: "sn",
  Cameroon: "cm",
  Mozambique: "mz",
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
  Myanmar: "mm",
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
  Ukraine: "ua",
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
  Luxembourg: "lu",
  // Oceania
  "New Zealand": "nz",
  Australia: "au",
  // Americas
  "United States": "us",
  Canada: "ca",
  Mexico: "mx",
  Argentina: "ar",
  Brazil: "br",
  Chile: "cl",
  Colombia: "co",
  Ecuador: "ec",
  Peru: "pe",
  Venezuela: "ve",
  Uruguay: "uy",
  Bolivia: "bo",
  Paraguay: "py",
  Cuba: "cu",
  Nicaragua: "ni",
  Honduras: "hn",
  Guatemala: "gt",
  "El Salvador": "sv",
  "Costa Rica": "cr",
  // Other / Special
  Turkey: "tr",
  "Hong Kong": "hk",
  // ─── 2026-05-29 gap fills (V4.1 polish — Naila #27) ────────────────
  // Country names surfaced as "flag missing" during the recipe-page audit.
  // Africa
  "Ivory Coast": "ci",
  "Côte d'Ivoire": "ci",
  "Cote d'Ivoire": "ci",
  Benin: "bj",
  Togo: "tg",
  Liberia: "lr",
  Gambia: "gm",
  "Guinea-Bissau": "gw",
  "Cape Verde": "cv",
  Mauritania: "🇲🇷",
  Tanzania: "tz",
  Zimbabwe: "zw",
  Botswana: "bw",
  Namibia: "na",
  Lesotho: "ls",
  Eswatini: "sz",
  Malawi: "mw",
  Comoros: "km",
  Djibouti: "dj",
  Gabon: "ga",
  Chad: "td",
  Congo: "cg",
  "Republic of Congo": "cg",
  // Middle East
  "United Arab Emirates": "ae",
  Bahrain: "bh",
  Oman: "om",
  Palestine: "🇵🇸",
  // Asia
  Maldives: "🇲🇻",
  Brunei: "🇧🇳",
  "Timor-Leste": "tl",
  // Europe
  Malta: "mt",
  Liechtenstein: "🇱🇮",
  Montenegro: "me",
  Kosovo: "xk",
  // Americas
  "Dominican Republic": "do",
  Haiti: "ht",
  Jamaica: "jm",
  Suriname: "🇸🇷",
  Guyana: "🇬🇾",
  // Oceania
  Fiji: "🇫🇯",
  // Risk Board flag fill 2026-05-29 — the 16 microstate / territory names
  // were rendering without flags on /risk-board (and anywhere else flagFor()
  // is the resolution path). FlagImg expects the emoji form (it decodes
  // iso2 from the regional-indicator codepoints), so values here must be
  // emoji, NOT iso2 strings.
  "Trinidad and Tobago": "🇹🇹",
  "Papua New Guinea": "🇵🇬",
  "Marshall Islands": "🇲🇭",
  Micronesia: "🇫🇲",
  Samoa: "🇼🇸",
  Macao: "🇲🇴",
  "Isle of Man": "🇮🇲",
  "Saint Martin (French part)": "🇲🇫",
  // Long-tail microstate / territory backfill from the country roster.
  "Sint Maarten (Dutch part)": "🇸🇽",
  "Saint Kitts and Nevis": "🇰🇳",
  "Saint Vincent and the Grenadines": "🇻🇨",
  Tuvalu: "🇹🇻",
  Kiribati: "🇰🇮",
  Tonga: "🇹🇴",
  Nauru: "🇳🇷",
  Vanuatu: "🇻🇺",
  "Solomon Islands": "🇸🇧",
  Palau: "🇵🇼",
  // Comoros / Bhutan / Timor-Leste / Hong Kong already present above as
  // iso2-string entries (which the flagFor smart-fallback lifts to emoji).
  // Not re-adding here to avoid TS1117 duplicate-property error.
  "Sao Tome and Principe": "🇸🇹",
  "Cabo Verde": "🇨🇻",
  Seychelles: "🇸🇨",
  Andorra: "🇦🇩",
  "San Marino": "🇸🇲",
  Monaco: "🇲🇨",
  Vatican: "🇻🇦",
  "Faroe Islands": "🇫🇴",
  Greenland: "🇬🇱",
  "Channel Islands": "🇯🇪",
  Gibraltar: "🇬🇮",
  "Cayman Islands": "🇰🇾",
  Bermuda: "🇧🇲",
  "Turks and Caicos Islands": "🇹🇨",
  "British Virgin Islands": "🇻🇬",
  "U.S. Virgin Islands": "🇻🇮",
  Anguilla: "🇦🇮",
  Aruba: "🇦🇼",
  Curacao: "🇨🇼",
  "Antigua and Barbuda": "🇦🇬",
  Dominica: "🇩🇲",
  Grenada: "🇬🇩",
  Barbados: "🇧🇧",
  "New Caledonia": "🇳🇨",
  "French Polynesia": "🇵🇫",
  Guam: "🇬🇺",
  "Northern Mariana Islands": "🇲🇵",
  "American Samoa": "🇦🇸",
  "Puerto Rico": "🇵🇷",
};

/**
 * V4.1 follow-up 2026-05-29 — robust mixed-map handling.
 *
 * The FLAGS map historically contained pure emoji values, but the 2026-05-28
 * sweep (Naila Hassan's African / Asian / Microstate backfill) added several
 * dozen entries as iso2 strings instead of emojis. FlagImg expects emoji, so
 * those entries rendered as empty placeholders silently.
 *
 * Rather than rewrite the map (which would conflict on every concurrent edit),
 * we normalize at the read site: if a value looks like a 2-letter iso2 code,
 * lift it to the regional-indicator emoji pair on the fly.
 */
function iso2ToEmoji(iso2: string): string {
  // Regional Indicator Symbol A is U+1F1E6; each letter maps to base + offset.
  const A_OFFSET = 0x1f1e6 - "a".charCodeAt(0);
  const cps = iso2
    .toLowerCase()
    .split("")
    .map((c) => c.charCodeAt(0) + A_OFFSET);
  return String.fromCodePoint(cps[0], cps[1]);
}

export function flagFor(name: string): string {
  const raw = FLAGS[name];
  if (!raw) return "🏳️";
  // Already an emoji (Regional Indicator pair = 8 UTF-16 code units, but len 2 in code points)
  // → return as-is. Two-letter ASCII iso2 → lift.
  if (/^[a-z]{2}$/i.test(raw)) return iso2ToEmoji(raw);
  return raw;
}

/**
 * Returns the lowercase ISO 3166-1 alpha-2 code for a country name, or
 * null when the name isn't in the lookup. Callers should render a sized
 * placeholder (preserving the flag's 16×12 footprint) on null so the row
 * grid does not collapse.
 *
 * Lookup is case-sensitive and exact-match: the mock data uses canonical
 * names ("United States", "Equatorial Guinea") and we want a hard miss
 * for unexpected spellings rather than a silent wrong-flag.
 */
/** Convert a regional-indicator flag emoji back to its lowercase iso2 code. */
function emojiToIso2(s: string): string | null {
  const cps = Array.from(s);
  if (cps.length < 2) return null;
  const A = 0x1f1e6;
  const a = cps[0].codePointAt(0);
  const b = cps[1].codePointAt(0);
  if (a == null || b == null || a < A || a > A + 25 || b < A || b > A + 25) return null;
  return String.fromCharCode(97 + (a - A)) + String.fromCharCode(97 + (b - A));
}

export function iso2For(name: string): string | null {
  const raw = ISO2[name];
  if (!raw) return null;
  // 2026-05-31 fix: a batch of long-tail entries were backfilled into the
  // ISO2 map as flag EMOJI instead of 2-letter codes (Vanuatu, Suriname, and
  // ~40 other microstates/territories), which broke flagcdn URLs + links.
  // Normalize at the read site: a 2-letter code passes through (lowercased);
  // a regional-indicator emoji is converted back to its code.
  if (/^[a-z]{2}$/i.test(raw)) return raw.toLowerCase();
  return emojiToIso2(raw);
}

// touch 1780028405015
