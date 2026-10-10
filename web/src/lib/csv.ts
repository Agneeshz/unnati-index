/** CSV for the data downloads: RFC 4180 quoting, CRLF rows, and a UTF-8 byte-order mark so Excel
 * shows "₹" and "µg/m³" correctly. */

export type Cell = string | number | boolean | null | undefined;

export function csvCell(value: Cell): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "boolean" ? (value ? "yes" : "no") : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(header: string[], rows: Cell[][]): string {
  const lines = [header, ...rows].map((row) => row.map(csvCell).join(","));
  return `﻿${lines.join("\r\n")}\r\n`;
}

export function csvResponse(body: string, filename: string): Response {
  return new Response(body, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      // Data changes at most daily; the pipeline's revalidation doesn't reach the CDN copy.
      "Cache-Control": "public, max-age=3600, s-maxage=21600, stale-while-revalidate=86400",
    },
  });
}
