import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const screens = [["inhaal", "/inhaal/"], ["design", "/design/"], ["site", "/"]];

for (const scheme of ["light", "dark"]) {
  for (const [name, path] of screens) {
    test.describe(`${name} ${scheme}`, () => {
      test.use({ colorScheme: scheme });

      test("past op het scherm en is toegankelijk", async ({ page }, info) => {
        const errors = [];
        page.on("pageerror", (e) => errors.push(e.message));
        page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

        await page.goto(path);
        await page.evaluate(() => document.fonts.ready);
        await expect(page.locator("h1")).toBeVisible();

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow).toBeLessThanOrEqual(0);

        const small = await page.locator(".row, .chip, .btn:not(.btn-small), .check, .tab").evaluateAll((els) =>
          els.filter((e) => e.offsetParent && e.getBoundingClientRect().height < 44).map((e) => e.className));
        expect(small).toEqual([]);

        const clipped = await page.locator(".row-main > *").evaluateAll((els) =>
          els.filter((e) => e.offsetParent && e.getBoundingClientRect().right > e.parentElement.getBoundingClientRect().right + 1).length);
        expect(clipped).toBe(0);

        const { violations } = await new AxeBuilder({ page }).analyze();
        expect(violations.map((v) => `${v.id}: ${v.nodes[0].target}`)).toEqual([]);
        expect(errors).toEqual([]);

        await page.screenshot({ path: `test-results/shots/${name}-${info.project.name}-${scheme}.png`, fullPage: true });
      });
    });
  }
}

test("Inhaal is een PWA die zonder netwerk opent", async ({ page, context, browserName }) => {
  test.skip(browserName === "firefox", "offline-emulatie met service worker is onbetrouwbaar in Firefox");
  await page.goto("/inhaal/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  const manifest = await page.request.get("/inhaal/manifest.webmanifest");
  expect((await manifest.json()).display).toBe("standalone");

  await context.setOffline(true);
  await page.reload();
  await expect(page.locator("h1")).toBeVisible();
});

for (const scheme of ["light", "dark"]) {
  test.describe(`sheet en toast ${scheme}`, () => {
    test.use({ colorScheme: scheme });

    test("openen en sluiten", async ({ page }, info) => {
      await page.goto("/design/");
      await page.locator("#open-sheet").click();
      await expect(page.locator("#sheet")).toBeVisible();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `test-results/shots/sheet-${info.project.name}-${scheme}.png` });
      await page.keyboard.press("Escape");
      await expect(page.locator("#sheet")).toBeHidden();
      await expect(page.locator("#open-sheet")).toBeFocused();

      await page.locator(".btn[data-toast]").last().click();
      await expect(page.locator("#toast")).toBeVisible();
      await page.waitForTimeout(400);
      await page.screenshot({ path: `test-results/shots/toast-${info.project.name}-${scheme}.png` });
      await page.locator("#undo").click();
      await expect(page.locator("#toast")).toBeHidden();
    });
  });
}

for (const [locale, title] of [["nl-BE", "Inhalen"], ["en-GB", "Catch up"]]) {
  test.describe(locale, () => {
    test.use({ locale });

    test("Inhaal volgt de taal van het toestel", async ({ page }) => {
      await page.goto("/inhaal/");
      await expect(page.locator("h1")).toHaveText(title);
    });
  });
}
