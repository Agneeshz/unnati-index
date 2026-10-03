"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Locale } from "@/i18n/config";

/** Link to the same page in the other language. */
export function LocaleSwitcher({ current, label, title }: { current: Locale; label: string; title: string }) {
  const pathname = usePathname();
  const target: Locale = current === "en" ? "hi" : "en";
  const rest = pathname.split("/").slice(2).join("/");
  return (
    <Link
      href={`/${target}${rest ? `/${rest}` : ""}`}
      hrefLang={target}
      lang={target}
      title={title}
      className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent"
    >
      {label}
    </Link>
  );
}
