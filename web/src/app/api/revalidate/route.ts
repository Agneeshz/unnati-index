import { revalidateTag } from "next/cache";
import { isAuthorised, parseTags } from "@/lib/revalidate";

/**
 * Called by the data pipeline after it loads new data:
 *   POST /api/revalidate  Authorization: Bearer $REVALIDATE_SECRET  {"tags": ["indicator:imr"]}
 * Pages using those tags are served stale once, then regenerate in the background.
 */
export async function POST(request: Request) {
  if (!isAuthorised(request.headers.get("authorization"), process.env.REVALIDATE_SECRET)) {
    return Response.json({ error: "unauthorised" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "body must be JSON" }, { status: 400 });
  }
  const tags = parseTags(body);
  if (!tags) {
    return Response.json(
      { error: 'body must be {"tags": [...]} with 1-100 lower-case tags such as "indicator:imr"' },
      { status: 400 },
    );
  }
  for (const tag of tags) revalidateTag(tag, "max");
  return Response.json({ revalidated: tags });
}
