/** Site search: entries and ranking (pure; used by the search box and the /search page). */

export type SearchType = "state" | "ut" | "city" | "pillar" | "index" | "indicator" | "page";

export type SearchEntry = {
  type: SearchType;
  title: string;
  subtitle?: string;
  href: string;
  /** Normalised names, in both languages. */
  names: string[];
  /** Normalised other names: former names, source spellings ("orissa", "gurgaon"). */
  aliases?: string[];
  /** Normalised description, matched only when nothing better does. */
  text?: string;
};

export type SearchResult = SearchEntry & { score: number };

/**
 * Lowercase, Latin accents removed, "&" spelt out, punctuation to spaces. Devanagari is kept as
 * it is (its vowel signs are combining marks, so only Latin ones are stripped).
 */
export function normalize(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9ऀ-ॿ]+/g, " ")
    .trim();
}

/** Edit distance, stopping early once it exceeds `limit`. */
function within(a: string, b: string, limit: number): boolean {
  if (Math.abs(a.length - b.length) > limit) return false;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      best = Math.min(best, current[j]);
    }
    if (best > limit) return false;
    previous = current;
  }
  return previous[b.length] <= limit;
}

function scoreTerm(term: string, query: string, tokens: string[], substrings = true): number {
  if (term === query) return 100;
  if (term.startsWith(query)) return 80;
  const words = term.split(" ");
  if (words.some((w) => w.startsWith(query))) return 60;
  if (tokens.length > 1 && tokens.every((t) => words.some((w) => w.startsWith(t)))) return 50;
  // Inside a word only for longer queries on real names ("air" must not find "Port Blair").
  if (substrings && query.length >= 4 && term.includes(query)) return 30;
  // One typo in a longer word ("bhubneshwar", "hydrabad").
  if (query.length >= 5 && words.some((w) => within(w, query, 1))) return 25;
  return 0;
}

const TYPE_BONUS: Record<SearchType, number> = {
  state: 5,
  ut: 5,
  city: 3,
  pillar: 4,
  index: 2,
  indicator: 0,
  page: -2,
};

export function search(entries: SearchEntry[], raw: string, limit = 8): SearchResult[] {
  const query = normalize(raw);
  if (!query) return [];
  const tokens = query.split(" ");
  const results: SearchResult[] = [];
  for (const entry of entries) {
    let score = Math.max(0, ...entry.names.map((n) => scoreTerm(n, query, tokens)));
    if (entry.aliases?.length) {
      score = Math.max(score, ...entry.aliases.map((a) => scoreTerm(a, query, tokens, false) * 0.9));
    }
    // Descriptions count only for whole-word starts ("air" finds "air quality", not "fair").
    if (!score && entry.text && query.length >= 3) {
      const words = entry.text.split(" ");
      if (tokens.every((t) => words.some((w) => w.startsWith(t)))) score = 10;
    }
    if (score) results.push({ ...entry, score: score + TYPE_BONUS[entry.type] });
  }
  return results
    .sort((a, b) => b.score - a.score || a.title.length - b.title.length || a.title.localeCompare(b.title))
    .slice(0, limit);
}
