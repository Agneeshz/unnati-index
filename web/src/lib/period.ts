/**
 * Period labels for display. The database keeps one English label per period ("Apr 2026",
 * "2012-13 to 2014-15", "Apr–Aug 2026 (FY 2026-27 to date)", "2024-01-01"), which pages also use
 * to line up series, so labels are translated only when shown.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_HI = [
  "जनवरी",
  "फ़रवरी",
  "मार्च",
  "अप्रैल",
  "मई",
  "जून",
  "जुलाई",
  "अगस्त",
  "सितंबर",
  "अक्टूबर",
  "नवंबर",
  "दिसंबर",
];
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const MONTH = new RegExp(`\\b(${MONTHS.join("|")})\\b`, "g");

export function formatPeriod(label: string, locale: string): string {
  const hi = locale === "hi";
  const date = ISO_DATE.exec(label);
  if (date) {
    const [, y, m, d] = date;
    return `${Number(d)} ${(hi ? MONTHS_HI : MONTHS)[Number(m) - 1]} ${y}`;
  }
  if (!hi) return label;
  return label
    .replace(/\(FY (\S+) to date\)/, "(वित्त वर्ष $1, अब तक)")
    .replace(/^(\S+) to (\S+)$/, "$1 से $2 तक")
    .replace(/^SS /, "स्वच्छ सर्वेक्षण ")
    .replace(MONTH, (m) => MONTHS_HI[MONTHS.indexOf(m)]);
}
