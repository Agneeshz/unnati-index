import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// WCAG 2.1 AA checks with axe-core on the main page types, in light and dark mode (contrast differs).

const PAGES = [
  "/en",
  "/hi",
  "/en/rankings",
  "/en/states/keralam",
  "/en/indicators/infant-mortality-rate",
  "/en/pillars/health",
  "/en/indices/human-development",
  "/en/cities",
  "/en/cities/mumbai",
  "/en/compare?e=keralam,bihar",
  "/en/updates",
  "/en/sources",
  "/en/methodology",
  "/en/data",
  "/en/search?q=orissa",
];

for (const colorScheme of ["light", "dark"] as const) {
  test.describe(`${colorScheme} mode`, () => {
    test.use({ colorScheme });
    for (const path of PAGES) {
      test(`no accessibility violations on ${path}`, async ({ page }) => {
        await page.goto(path);
        await expect(page.locator("h1").first()).toBeVisible();
        const { violations } = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const summary = violations.map(
          (v) => `${v.id} (${v.impact}): ${v.help}\n${v.nodes.slice(0, 3).map((n) => `  ${n.target.join(" ")}`).join("\n")}`,
        );
        expect(summary, summary.join("\n")).toEqual([]);
      });
    }
  });
}
