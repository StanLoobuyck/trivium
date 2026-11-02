import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const screens = [["sequo", "/sequo/"], ["design", "/design/"], ["site", "/"]];

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
          els.filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.9).map((e) => e.className));
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

test("Sequo is een PWA die zonder netwerk opent", async ({ page, context, browserName }) => {
  test.skip(browserName === "firefox", "offline-emulatie met service worker is onbetrouwbaar in Firefox");
  await page.goto("/sequo/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  const manifest = await page.request.get("/sequo/manifest.webmanifest");
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

for (const [locale, title] of [["nl-BE", "Overzicht"], ["en-GB", "Overview"]]) {
  test.describe(locale, () => {
    test.use({ locale });

    test("Sequo volgt de taal van het toestel", async ({ page }) => {
      await page.goto("/sequo/");
      await expect(page.locator("h1")).toHaveText(title);
    });
  });
}

const IN_APP = [["overzicht", "/sequo/#/"], ["lijst", "/sequo/#/", "Lijst"], ["instellingen", "/sequo/#/instellingen"], ["vak", "vak"]];

for (const scheme of ["light", "dark"]) {
  test.describe(`gevulde app ${scheme}`, () => {
    test.use({ colorScheme: scheme, locale: "nl-BE" });

    test("alle schermen en sheets", async ({ page }, info) => {
      await page.clock.setFixedTime(new Date("2026-11-01T12:00:00+01:00"));
      await page.goto("/sequo/");
      const chooser = page.waitForEvent("filechooser");
      await page.getByRole("button", { name: "Rooster uploaden" }).first().click();
      await (await chooser).setFiles("fixtures/rooster-anon.ics");
      await page.waitForTimeout(400);
      const shot = (name) => page.screenshot({ path: `test-results/shots/app-${name}-${info.project.name}-${scheme}.png` });
      await shot("controle");
      await page.getByRole("button", { name: "Start", exact: true }).click();

      const check = async () => {
        const overflow = await page.evaluate(() => {
          const view = document.querySelector("#view");
          return Math.max(document.documentElement.scrollWidth - window.innerWidth, view.scrollWidth - view.clientWidth);
        });
        expect(overflow).toBeLessThanOrEqual(0);
        const small = await page.locator(".row, .chip, .btn:not(.btn-small), .check, .tab").evaluateAll((els) =>
          els.filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.9).map((e) => e.className));
        expect(small).toEqual([]);
        const { violations } = await new AxeBuilder({ page }).analyze();
        expect(violations.map((v) => `${v.id}: ${v.nodes[0].target}`)).toEqual([]);
      };

      for (const [name, path, button] of IN_APP) {
        if (path === "vak") {
          await page.goto("/sequo/#/");
          await page.getByRole("button", { name: "Per vak" }).click();
          await page.locator("#view a.row").first().click();
        }
        else await page.goto(path);
        if (button) await page.getByRole("button", { name: button }).click();
        await page.waitForTimeout(350);
        await check();
        await shot(name);
      }

      await page.getByRole("button", { name: /^Les 1 / }).click();
      await page.waitForTimeout(400);
      await check();
      await shot("opties");
      await page.keyboard.press("Escape");

      await page.locator(".fab:visible, .side-add:visible").click();
      await page.waitForTimeout(400);
      await check();
      await shot("toevoegen");
    });
  });
}

for (const [name, path] of screens) {
  test(`${name} staat niet in zoekmachines`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  });
}
