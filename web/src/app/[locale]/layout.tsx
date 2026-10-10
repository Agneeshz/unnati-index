import type { Metadata } from "next";
import { Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import Link from "next/link";
import { locale } from "next/root-params";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { SearchBox } from "@/components/search-box";
import { isLocale, locales } from "@/i18n/config";
import { getDictionary } from "@/i18n/dictionaries";
import "../globals.css";

const latin = Noto_Sans({ subsets: ["latin"], variable: "--font-latin", display: "swap" });
const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  variable: "--font-devanagari",
  display: "swap",
});

const REPO_URL = "https://github.com/Agneeshz/unnati-index";

export async function generateStaticParams() {
  return locales.map((value) => ({ locale: value }));
}

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary();
  return {
    title: { default: `${dict.site.name}: ${dict.site.tagline}`, template: `%s · ${dict.site.name}` },
    description: dict.site.description,
    metadataBase: new URL(process.env.SITE_URL ?? "https://unnati-index.vercel.app"),
    openGraph: { siteName: dict.site.name, type: "website" },
  };
}

export default async function RootLayout({ children }: LayoutProps<"/[locale]">) {
  const lang = await locale();
  const dict = await getDictionary();
  const current = isLocale(lang) ? lang : "en";

  return (
    <html lang={current} className={`${latin.variable} ${devanagari.variable}`}>
      <body className="flex min-h-dvh flex-col bg-bg font-sans text-fg antialiased">
        <header className="border-b border-border bg-surface">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 pt-2">
            <Link href={`/${current}`} className="flex items-center gap-2 font-semibold">
              <svg aria-hidden="true" viewBox="0 0 32 32" className="size-7">
                <rect width="32" height="32" rx="7" className="fill-accent" />
                <rect x="7" y="17" width="4" height="8" rx="1" className="fill-surface" />
                <rect x="14" y="12" width="4" height="13" rx="1" className="fill-surface" />
                <rect x="21" y="7" width="4" height="18" rx="1" className="fill-surface" />
              </svg>
              {dict.site.name}
            </Link>
            <SearchBox
              locale={current}
              labels={{
                label: dict.ui.search.label,
                placeholder: dict.ui.search.placeholder,
                seeAll: dict.ui.search.seeAll,
                hint: dict.ui.search.hint,
                types: dict.ui.search.types,
              }}
            />
          </div>
          <div className="mx-auto max-w-6xl px-4 pb-1">
            <nav aria-label="Main" className="-mx-2 flex items-center gap-1 overflow-x-auto text-sm">
              {(["rankings", "cities", "compare", "indices", "indicators", "updates", "data", "methodology", "sources"] as const).map((key) => (
                <Link
                  key={key}
                  href={`/${current}/${key}`}
                  className="rounded-md px-2 py-1.5 whitespace-nowrap hover:bg-accent-soft"
                >
                  {dict.ui.nav[key]}
                </Link>
              ))}
              <LocaleSwitcher current={current} label={dict.nav.language} title={dict.nav.languageLabel} />
            </nav>
          </div>
        </header>

        <main className="flex-1">{children}</main>

        <footer className="border-t border-border bg-surface">
          <div className="mx-auto max-w-5xl space-y-2 px-4 py-6 text-sm text-muted">
            <p>{dict.footer.disclaimer}</p>
            <p>
              {dict.footer.license} ·{" "}
              <a href={REPO_URL} className="underline underline-offset-2 hover:text-fg">
                {dict.footer.source}
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
