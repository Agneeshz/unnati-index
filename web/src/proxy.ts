import { NextResponse, type NextRequest } from "next/server";
import { isLocale, negotiateLocale } from "@/i18n/config";

/** Send paths without a locale prefix to the visitor's language, e.g. "/" -> "/en". */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (isLocale(pathname.split("/")[1])) return;

  const url = request.nextUrl.clone();
  const locale = negotiateLocale(request.headers.get("accept-language"));
  url.pathname = `/${locale}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Skip API routes, Next.js internals and files with an extension (icons, robots.txt, maps).
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
