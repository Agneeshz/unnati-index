import { expect, type Page, test } from "@playwright/test";

// Browser checks for what unit tests can't see: pages render, map labels don't collide, search
// works with the keyboard, and nothing scrolls sideways on a phone.

const PAGES = [
  "/en",
  "/hi",
  "/en/rankings",
  "/en/states/keralam",
  "/hi/states/keralam",
  "/en/indicators/infant-mortality-rate",
  "/en/pillars/health",
  "/en/indices/human-development",
  "/en/cities",
  "/en/cities/mumbai",
  "/en/compare?e=keralam,bihar",
  "/en/updates",
  "/en/methodology",
  "/en/search?q=orissa",
];

for (const path of PAGES) {
  test(`renders ${path}`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.locator("h1").first()).toBeVisible();
  });
}

/** For every city map on the page: overlapping label pairs, and cities named nowhere. */
async function labelProblems(page: Page) {
  return page.evaluate(() => {
    const figures = [...document.querySelectorAll("figure")].filter((f) => f.querySelector("svg a"));
    return figures.map((figure) => {
      const svgs = [...figure.querySelectorAll("svg[role=img]")];
      const overlaps: string[] = [];
      for (const svg of svgs) {
        const labels = [...svg.querySelectorAll("text")].filter((t) => !/^\d$/.test(t.textContent ?? ""));
        const boxes = labels.map((t) => ({ name: t.textContent, r: t.getBoundingClientRect() }));
        for (let i = 0; i < boxes.length; i++)
          for (let j = i + 1; j < boxes.length; j++) {
            const a = boxes[i].r;
            const b = boxes[j].r;
            const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
            const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
            if (w > 1 && h > 1) overlaps.push(`${boxes[i].name} / ${boxes[j].name}`);
          }
      }
      // Each dot is a link whose label starts with the city's name; it must be named somewhere.
      const named = new Set([...figure.querySelectorAll("svg text")].map((t) => t.textContent));
      const cities = [...figure.querySelectorAll("svg a")].map((a) => a.getAttribute("aria-label")?.split(" · ")[0]);
      const unnamed = [...new Set(cities)].filter((c) => c && !named.has(c));
      return { title: figure.querySelector("figcaption")?.textContent ?? "", overlaps, unnamed };
    });
  });
}

for (const path of ["/en/states/maharashtra", "/en/states/west-bengal", "/en/states/uttar-pradesh", "/hi/states/maharashtra", "/en/cities/delhi-city"]) {
  test(`city map labels on ${path}`, async ({ page }) => {
    await page.goto(path);
    const maps = await labelProblems(page);
    expect(maps.length).toBeGreaterThan(0);
    for (const map of maps) {
      expect(map.overlaps, `overlapping labels in "${map.title}"`).toEqual([]);
      expect(map.unnamed, `unnamed cities in "${map.title}"`).toEqual([]);
    }
  });
}

test("search finds a state by its former name, from the keyboard", async ({ page }) => {
  await page.goto("/en/rankings");
  await page.keyboard.press("/");
  const box = page.getByRole("combobox");
  await expect(box).toBeFocused();
  await box.fill("orissa");
  await expect(page.getByRole("option", { name: /Odisha/ })).toBeVisible();
  await box.press("ArrowDown");
  await box.press("Enter");
  await expect(page).toHaveURL(/\/en\/states\/odisha$/);
});

test("search page works without the search box", async ({ page }) => {
  await page.goto("/hi/search?q=gurgaon");
  await expect(page.getByRole("link", { name: /गुरुग्राम/ })).toBeVisible();
});

test("no sideways scrolling on a phone", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 375, height: 800 } });
  const page = await context.newPage();
  for (const path of ["/en", "/en/states/maharashtra", "/en/cities", "/en/compare?e=keralam,bihar"]) {
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${path} scrolls sideways`).toBeLessThanOrEqual(1);
  }
  await context.close();
});

test("a report card ranks a state within its peer group", async ({ page }) => {
  // 18 large states: the count once included the thematic indices' scores (107).
  await page.goto("/en/states/keralam");
  await expect(page.getByText(/#\d+ of 18 in Large states/)).toBeVisible();
});
