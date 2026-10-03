import { timingSafeEqual } from "node:crypto";

// Cache tags look like "indicator:infant-mortality-rate", "state:kerala" or "home".
const TAG = /^[a-z0-9][a-z0-9:_-]{0,127}$/;
const MAX_TAGS = 100;

/** Constant-time check of an "Authorization: Bearer <secret>" header. */
export function isAuthorised(header: string | null, secret: string | undefined): boolean {
  if (!secret || !header?.startsWith("Bearer ")) return false;
  const given = Buffer.from(header.slice("Bearer ".length));
  const expected = Buffer.from(secret);
  return given.length === expected.length && timingSafeEqual(given, expected);
}

/** Validate a `{"tags": [...]}` body; returns the tags, or null if the body is malformed. */
export function parseTags(body: unknown): string[] | null {
  if (typeof body !== "object" || body === null) return null;
  const tags = (body as { tags?: unknown }).tags;
  if (!Array.isArray(tags) || tags.length === 0 || tags.length > MAX_TAGS) return null;
  if (!tags.every((tag): tag is string => typeof tag === "string" && TAG.test(tag))) return null;
  return [...new Set(tags)];
}
