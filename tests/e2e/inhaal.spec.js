import { readFileSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

const NOW = new Date("2026-11-01T12:00:00+01:00");
const ROOSTER = "fixtures/rooster-anon.ics";
const OPEN_BEFORE = 35;

test.use({ locale: "nl-BE" });

async function upload(page, files = ROOSTER, button = page.getByRole("button", { name: "Rooster uploaden" }).first()) {
  const chooser = page.waitForEvent("filechooser");
  await button.click();
  await (await chooser).setFiles(files);
}

async function setup(page) {
  await page.clock.setFixedTime(NOW);
  await page.goto("/inhaal/");
  await upload(page);
  await expect(page.getByRole("dialog")).toContainText("Controleer je vakken");
}

async function start(page) {
  await setup(page);
  await page.getByRole("button", { name: "Samenvoegen" }).first().click();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect(page.getByTestId("open-count")).toBeVisible();
}

const openCount = (page) => page.getByTestId("open-count");
const courseLink = (page, name) => page.locator("#view").getByRole("link", { name });

test("rooster geeft vakken en voorbije lessen op in te halen, P&O uit", async ({ page }) => {
  await setup(page);
  await expect(page.getByRole("switch", { name: "P&O tonen" })).not.toBeChecked();
  await expect(page.getByRole("dialog")).toContainText("lijkt het vervolg van");
  await page.getByRole("button", { name: "Samenvoegen" }).first().click();
  await page.getByRole("button", { name: "Start", exact: true }).click();

  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE));
  await expect(page.locator("#view")).not.toContainText("P&O");
  await expect(courseLink(page, /Elektronische basisschakelingen/)).toBeVisible();
  await expect(page.locator("#view")).not.toContainText("Elektronische signalen");
  await expect(page.locator("#view")).toContainText("Je rooster start 3 weken na de start");
});

test("afvinken met undo, en de rij schuift naar Afgewerkt", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  const first = page.getByRole("checkbox").first();
  const label = await first.getAttribute("aria-label");
  await first.click();
  await expect(page.locator("#toast")).toContainText("afgevinkt");
  await page.locator("#toast button").click();
  await expect(page.getByRole("checkbox", { name: label })).not.toBeChecked();

  await page.getByRole("checkbox", { name: label }).click();
  await expect(page.getByText("Afgewerkt (1)")).toBeVisible();
  await page.goto("/inhaal/#/");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE - 1));
});

test("de knop Bekeken op de kaart Volgende telt af en overleeft herladen", async ({ page }) => {
  await start(page);
  await page.getByRole("button", { name: "Bekeken", exact: true }).click();
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE - 1));
  await page.waitForTimeout(200);
  await page.reload();
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE - 1));
});

test("nummering klopt na een geschrapte les", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await expect(page.locator("#view")).toContainText("Les 2 · wo 21 okt");
  await page.getByRole("button", { name: /^Les 1 / }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Geschrapt" }).click();
  await expect(page.locator("#view")).toContainText("geschrapt");
  await expect(page.getByRole("button", { name: /^Les 1 .* 21 okt/ })).toBeVisible();
});

test("een vak dat nog moet starten krijgt geen vinkje", async ({ page }) => {
  await setup(page);
  await page.getByRole("button", { name: "Start", exact: true }).click();
  const later = courseLink(page, /Elektronische signalen/);
  await expect(later).not.toHaveClass(/is-done/);
});

const touch = (page, selector, steps) => page.evaluate(([sel, moves]) => {
  const target = document.querySelector(sel);
  const fire = (type, x) => target.dispatchEvent(new PointerEvent(type, { bubbles: true, pointerType: "touch", clientX: x, clientY: 100 }));
  moves.forEach(([type, x]) => fire(type, x));
}, [selector, steps]);

test("swipe naar rechts vinkt af en de volgende tik werkt nog", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await page.getByRole("checkbox").first().waitFor();
  await touch(page, "[data-swipe] .row-link", [["pointerdown", 50], ["pointermove", 80], ["pointermove", 180], ["pointerup", 180]]);
  await expect(page.locator("#toast")).toContainText("afgevinkt");
  await page.waitForTimeout(450);
  await page.locator("[data-options]").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("swipe naar links opent de opties", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await page.getByRole("checkbox").first().waitFor();
  await touch(page, "[data-swipe] .row-link", [["pointerdown", 200], ["pointermove", 170], ["pointermove", 60], ["pointerup", 60]]);
  await expect(page.getByRole("dialog")).toContainText("Status");
});

test("een afgevinkte rij schuift meteen door, en undo geldt voor de hele reeks", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await page.getByRole("checkbox").first().waitFor();
  await page.getByRole("checkbox").nth(0).click();
  await expect(page.getByText("Afgewerkt (1)")).toBeVisible({ timeout: 600 });
  await expect(page.locator("#view section .list .row").first()).toBeVisible();
  await page.getByRole("checkbox").nth(0).click();
  await expect(page.locator("#toast")).toContainText("2 sessies afgevinkt");
  await expect(page.getByText("Afgewerkt (2)")).toBeVisible({ timeout: 600 });
  await page.locator("#toast button").click();
  await expect(page.getByText(/Afgewerkt/)).toHaveCount(0);
});

test("razendsnel tikken vinkt elke tik een andere les af en telt juist", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale elektronica/).click();
  await page.getByRole("checkbox").first().waitFor();
  const ticks = await page.evaluate(() => {
    const started = performance.now();
    for (let i = 0; i < 5; i += 1) document.querySelector(".check[data-tick]").click();
    return performance.now() - started;
  });
  expect(ticks).toBeLessThan(100);
  await expect(page.getByText("Afgewerkt (5)")).toBeVisible();
  await expect(page.locator("#toast")).toContainText("5 sessies afgevinkt");
  await page.waitForTimeout(200);
  await page.reload();
  await expect(page.getByText("Afgewerkt (5)")).toBeVisible();
});

test("inhaalplan rekent met de afspeelsnelheid en de grafiek toont de weken", async ({ page }) => {
  await start(page);
  await expect(page.locator("#view")).toContainText("weken tot de examens");
  const before = await page.getByText("per week").innerText();
  await page.getByRole("button", { name: "2×" }).click();
  await expect(page.getByRole("button", { name: "2×" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("per week")).not.toHaveText(before);
  await expect(page.locator(".bar-slot").first()).toHaveAttribute("title", /Week van/);
  expect(await page.locator(".bar-slot").count()).toBeGreaterThan(5);
  await expect(page.locator("#view")).toContainText("lessen die nog komen");
  await page.locator(".bar-slot").nth(4).dispatchEvent("pointerdown");
  await page.locator(".bar-slot").last().click();
  await expect(page.locator("#bars-readout")).toContainText("Week van");
  await expect(page.locator(".bar-slot.is-active")).toHaveCount(1);
});

test("sneltoetsen: vak kiezen, bewegen, afvinken, ongedaan maken", async ({ page }, info) => {
  test.skip(info.project.name === "iphone-chromium", "alleen op de laptop");
  await start(page);
  await page.keyboard.press("3");
  await expect(page.locator("h1")).toContainText("Digitale signaalverwerking");
  await page.getByRole("checkbox").first().waitFor();
  await page.keyboard.press("j");
  await page.keyboard.press("j");
  await page.keyboard.press("x");
  await expect(page.getByText("Afgewerkt (1)")).toBeVisible();
  await page.keyboard.press("x");
  await expect(page.getByText("Afgewerkt (2)")).toBeVisible();
  await page.keyboard.press("z");
  await expect(page.getByText(/Afgewerkt/)).toHaveCount(0);
  await page.keyboard.press("n");
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("de menubalk wordt breder als de + verdwijnt", async ({ page }, info) => {
  test.skip(info.project.name !== "iphone-chromium", "alleen op iPhone-formaat");
  await start(page);
  const width = () => page.locator(".tabbar").evaluate((e) => e.getBoundingClientRect().width);
  await page.waitForTimeout(400);
  const before = await width();
  await page.goto("/inhaal/#/instellingen");
  await expect(page.locator("#fab")).toBeHidden();
  await expect.poll(width).toBeGreaterThan(before + 40);
  await expect(page.locator(".tab[aria-current]")).toContainText("Instellingen");
});

test("naar beneden vegen sluit de sheet", async ({ page, browserName }) => {
  test.skip(browserName !== "chromium", "aangemaakte touch-events werken alleen in Chromium");
  await start(page);
  await page.goto("/inhaal/#/instellingen");
  await page.getByRole("button", { name: "Notes-lijst plakken" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await page.waitForTimeout(350);
  const swipe = (dy) => page.evaluate(async (distance) => {
    const target = document.querySelector("#sheet h2");
    const fire = (type, y, list = true) => {
      const touch = new Touch({ identifier: 1, target, clientX: 100, clientY: y });
      target.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: list ? [touch] : [], changedTouches: [touch] }));
    };
    fire("touchstart", 300); fire("touchmove", 310); fire("touchmove", 300 + distance);
    await new Promise((done) => { setTimeout(done, 300); });
    fire("touchend", 300 + distance, false);
  }, dy);
  await page.waitForTimeout(100);
  await swipe(40);
  await page.waitForTimeout(100);
  await expect(sheet).toBeVisible();
  await page.waitForTimeout(400);
  await swipe(200);
  await expect(sheet).toBeHidden();
});

test("de strook onder de statusbalk bevat geen titel", async ({ page }) => {
  await start(page);
  await expect(page.locator(".topbar")).toHaveText("");
});

test("niets schuift de app uit beeld en onder de keuzeknop staat ruimte", async ({ page }) => {
  await start(page);
  await expect(page.locator("h1")).toBeVisible();
  const gap = await page.evaluate(() => {
    const control = document.querySelector("#view .segmented").getBoundingClientRect();
    return document.querySelector("#view .list").getBoundingClientRect().top - control.bottom;
  });
  expect(gap).toBeGreaterThanOrEqual(12);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await expect(page.getByRole("button", { name: "Selecteer" })).toBeVisible();
  const top = await page.evaluate(() => [document.querySelector("#stage").scrollTop, document.querySelector("#view h1").getBoundingClientRect().top]);
  expect(top[0]).toBe(0);
  expect(top[1]).toBeGreaterThan(0);
});

test("weergave kiezen blijft bewaard", async ({ page }) => {
  await start(page);
  await page.goto("/inhaal/#/instellingen");
  await page.getByRole("button", { name: "Donker" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Donker" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Systeem" }).click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
});

test("manueel toevoegen via de sheet", async ({ page }) => {
  await start(page);
  await page.locator(".fab:visible, .side-add:visible").click();
  const sheet = page.getByRole("dialog");
  await sheet.getByRole("button", { name: "vandaag" }).click();
  await sheet.getByRole("button", { name: "Voeg 1 toe" }).click();
  await expect(page.locator("#toast")).toContainText("1 toegevoegd");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE + 1));
});

test("meerdere tegelijk afvinken", async ({ page }) => {
  await start(page);
  await courseLink(page, /Digitale signaalverwerking/).click();
  await page.getByRole("button", { name: "Selecteer" }).click();
  await page.getByRole("checkbox").nth(0).click();
  await page.getByRole("checkbox").nth(1).click();
  await page.getByRole("button", { name: "Vink 2 af" }).click();
  await expect(page.getByText("Afgewerkt (2)")).toBeVisible();
});

test("opnieuw uploaden maakt geen dubbels", async ({ page }) => {
  await start(page);
  await page.goto("/inhaal/#/instellingen");
  await upload(page, ROOSTER, page.getByRole("button", { name: "Rooster uploaden" }));
  await expect(page.locator("#toast")).toContainText("0 nieuw, 0 gewijzigd");
  await page.goto("/inhaal/#/");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE));
});

test("een aanvulling vult de ontbrekende weken", async ({ page }, info) => {
  await start(page);
  const file = info.outputPath("aanvulling.ics");
  writeFileSync(file, `BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:test\r\nBEGIN:VEVENT\r\nDTSTART:20260923T063000Z\r\nDTEND:20260923T082500Z\r\nUID:extra-1\r\nDTSTAMP:20261101T000000Z\r\nSUMMARY:H01L6a Digitale signaalverwerking: hoorcollege\\, Docent C\r\nDESCRIPTION:01 College\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n`);
  await upload(page, file, page.locator("#view").getByRole("button", { name: "Rooster uploaden" }));
  await expect(page.locator("#toast")).toContainText("1 nieuw");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE + 1));
});

test("een verdwenen les wordt een voorstel, geen stille verwijdering", async ({ page }, info) => {
  await start(page);
  const text = readFileSync(ROOSTER, "utf8").replace(/\r\n/g, "\n");
  const blocks = text.split("BEGIN:VEVENT\n");
  const target = blocks.findIndex((b) => b.includes("H01L6a") && b.includes("DTSTART:20261021"));
  blocks.splice(target, 1);
  const file = info.outputPath("rooster.ics");
  writeFileSync(file, blocks.join("BEGIN:VEVENT\n"));
  await page.goto("/inhaal/#/instellingen");
  await upload(page, file, page.getByRole("button", { name: "Rooster uploaden" }));
  await expect(page.getByRole("dialog")).toContainText("Verdwenen uit je rooster");
  await page.getByRole("button", { name: "Markeer als geschrapt" }).click();
  await page.goto("/inhaal/#/");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE - 1));
});

test("Notes plakken zonder dubbels", async ({ page }) => {
  await start(page);
  await page.goto("/inhaal/#/instellingen");
  await page.getByRole("button", { name: "Notes-lijst plakken" }).click();
  await page.getByRole("dialog").getByRole("textbox").fill("Hoorcolleges\nDigitale signaalverwerking:\n- [x] 14/10\n- [ ] 21/10\n- [ ] 30/09\n");
  await page.getByRole("button", { name: "Controleer" }).click();
  await expect(page.locator("#notes-result")).toContainText("2 gekoppeld, 1 nieuw");
  await page.getByRole("button", { name: "Importeren" }).click();
  await page.goto("/inhaal/#/");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE));
});

test("back-up exporteren en herstellen", async ({ page }, info) => {
  await start(page);
  await page.getByRole("button", { name: "Bekeken", exact: true }).click();
  await page.goto("/inhaal/#/instellingen");
  const saved = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporteer back-up" }).click();
  const file = info.outputPath("backup.json");
  await (await saved).saveAs(file);

  await page.getByRole("button", { name: "Alles wissen" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Alles wissen" }).click();
  await page.goto("/inhaal/#/");
  await expect(page.getByText("Nog geen rooster")).toBeVisible();

  await page.goto("/inhaal/#/instellingen");
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Herstel back-up" }).click();
  await (await chooser).setFiles(file);
  await page.getByRole("dialog").getByRole("button", { name: "Herstellen" }).click();
  await page.goto("/inhaal/#/");
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE - 1));
});

test("back-upherinnering na een maand", async ({ page }) => {
  await start(page);
  await expect(page.locator("#view")).not.toContainText("Tijd voor een back-up");
  await page.clock.setFixedTime(new Date("2026-12-05T12:00:00+01:00"));
  await page.reload();
  await expect(page.locator("#view")).toContainText("Tijd voor een back-up");
});

test("taal wisselen naar Engels", async ({ page }) => {
  await start(page);
  await page.goto("/inhaal/#/instellingen");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("h1")).toHaveText("Settings");
  await page.goto("/inhaal/#/");
  await expect(page.locator("h1")).toHaveText("Catch up");
});

test("data blijft beschikbaar zonder netwerk", async ({ page, context, browserName }) => {
  test.skip(browserName === "firefox", "offline-emulatie met service worker is onbetrouwbaar in Firefox");
  await start(page);
  await page.evaluate(() => navigator.serviceWorker.ready);
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await context.setOffline(true);
  await page.reload();
  await expect(openCount(page)).toHaveText(String(OPEN_BEFORE));
});
