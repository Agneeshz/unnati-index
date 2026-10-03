import type { Locale } from "@/i18n/config";

const LAKH = 1e5;
const CRORE = 1e7;

const UNITS: Record<Locale, { lakh: string; crore: string }> = {
  en: { lakh: "lakh", crore: "crore" },
  hi: { lakh: "लाख", crore: "करोड़" },
};

function intlLocale(locale: Locale): string {
  return locale === "hi" ? "hi-IN" : "en-IN";
}

/** Group digits the Indian way: 1234567 -> "12,34,567". */
export function formatNumber(value: number, decimals = 0, locale: Locale = "en"): string {
  return new Intl.NumberFormat(intlLocale(locale), {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Large values in lakh/crore: 45600000 -> "4.56 crore", 123000 -> "1.23 lakh". */
export function formatCompact(value: number, locale: Locale = "en", decimals = 2): string {
  const abs = Math.abs(value);
  const units = UNITS[locale];
  if (abs >= CRORE) return `${formatNumber(value / CRORE, decimals, locale)} ${units.crore}`;
  if (abs >= LAKH) return `${formatNumber(value / LAKH, decimals, locale)} ${units.lakh}`;
  return formatNumber(value, 0, locale);
}

export function formatPercent(value: number, decimals = 1, locale: Locale = "en"): string {
  return `${formatNumber(value, decimals, locale)}%`;
}
