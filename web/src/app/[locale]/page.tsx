import { getDictionary, type Dictionary } from "@/i18n/dictionaries";

const PILLARS: (keyof Dictionary["pillars"])[] = [
  "economy-jobs",
  "health",
  "education",
  "safety-justice",
  "governance-fiscal",
  "infrastructure-digital",
  "environment",
  "inclusion",
];

export default async function HomePage() {
  const dict = await getDictionary();

  return (
    <div className="mx-auto max-w-5xl px-4">
      <section className="py-12 sm:py-16">
        <h1 className="max-w-3xl text-3xl font-bold tracking-tight text-balance sm:text-5xl">
          {dict.site.tagline}
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">{dict.site.description}</p>
        <p role="status" className="mt-6 inline-block rounded-md bg-accent-soft px-3 py-2 text-sm">
          {dict.home.status}
        </p>
      </section>

      <section aria-labelledby="pillars" className="border-t border-border py-10">
        <h2 id="pillars" className="text-2xl font-semibold">
          {dict.home.pillarsTitle}
        </h2>
        <p className="mt-2 max-w-3xl text-muted">{dict.home.pillarsIntro}</p>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PILLARS.map((id, index) => (
            <li key={id} className="rounded-lg border border-border bg-surface p-4">
              <span className="text-sm font-medium text-accent">{index + 1}</span>
              <h3 className="mt-1 font-semibold">{dict.pillars[id].name}</h3>
              <p className="mt-1 text-sm text-muted">{dict.pillars[id].description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="principles" className="border-t border-border py-10">
        <h2 id="principles" className="text-2xl font-semibold">
          {dict.home.principlesTitle}
        </h2>
        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
          {dict.home.principles.map((principle) => (
            <div key={principle.title}>
              <dt className="font-semibold">{principle.title}</dt>
              <dd className="mt-1 text-muted">{principle.body}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
