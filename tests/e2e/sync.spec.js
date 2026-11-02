import { expect, test } from "@playwright/test";

const HUB = "http://localhost:4174";
const CODE = "testcode-testcode-testcode-testcode";

test.use({ baseURL: HUB, locale: "nl-BE" });
test.beforeEach(async ({ page: _page }, info) => {
  test.skip(info.project.name !== "laptop-chromium", "de sync hangt niet van de browser af");
});

async function device(browser) {
  const context = await browser.newContext({ baseURL: HUB, locale: "nl-BE", serviceWorkers: "block" });
  const page = await context.newPage();
  await page.goto("/#/instellingen");
  await page.getByLabel("Koppelcode").fill(CODE);
  await page.getByRole("button", { name: "Koppelen" }).click();
  await expect(page.locator("#sync-status")).toContainText("Gesynchroniseerd");
  return page;
}

test("wijziging op het ene toestel verschijnt binnen 5 s op het andere, ook na offline", async ({ browser }) => {
  const phone = await device(browser);
  const laptop = await device(browser);

  await phone.goto("/#/");
  const chooser = phone.waitForEvent("filechooser");
  await phone.getByRole("button", { name: "Rooster uploaden" }).first().click();
  await (await chooser).setFiles("fixtures/rooster-anon.ics");
  await phone.getByRole("button", { name: "Start", exact: true }).click();
  const count = await phone.getByTestId("open-count").innerText();

  await laptop.goto("/#/");
  await expect(laptop.getByTestId("open-count")).toHaveText(count, { timeout: 15000 });

  await phone.getByRole("button", { name: "Bekeken", exact: true }).click();
  await expect(laptop.getByTestId("open-count")).toHaveText(String(+count - 1), { timeout: 5000 });

  await laptop.context().setOffline(true);
  await laptop.getByRole("button", { name: "Bekeken", exact: true }).click();
  await laptop.waitForTimeout(500);
  await expect(phone.getByTestId("open-count")).toHaveText(String(+count - 1));
  await laptop.context().setOffline(false);
  await expect(phone.getByTestId("open-count")).toHaveText(String(+count - 2), { timeout: 8000 });
});

test("een foute code wordt gemeld", async ({ browser }) => {
  const context = await browser.newContext({ baseURL: HUB, locale: "nl-BE", serviceWorkers: "block" });
  const page = await context.newPage();
  await page.goto("/#/instellingen");
  await page.getByLabel("Koppelcode").fill("fout");
  await page.getByRole("button", { name: "Koppelen" }).click();
  await expect(page.locator("#sync-status")).toContainText("klopt niet");
});

test("notities klaar van Verbatim verschijnen als badge, en de hub geeft de vakken", async ({ browser }) => {
  const laptop = await device(browser);
  await laptop.goto("/#/");
  await expect(laptop.getByTestId("open-count")).toBeVisible({ timeout: 15000 });
  const { day, code } = await laptop.evaluate(async () => {
    const open = indexedDB.open("sequo");
    const db = await new Promise((resolve) => { open.onsuccess = () => resolve(open.result); });
    const sessions = await new Promise((resolve) => { db.transaction("sessions").objectStore("sessions").getAll().onsuccess = (e) => resolve(e.target.result); });
    const session = sessions.filter((s) => s.type === "lecture" && s.code && s.status === "upcoming" && new Date(s.end) < new Date()).sort((a, b) => a.start.localeCompare(b.start))[0];
    return { day: new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Brussels" }).format(new Date(session.start)), code: session.code };
  });

  const headers = { Authorization: `Bearer ${CODE}` };
  const courses = await (await laptop.request.get(`${HUB}/api/courses`, { headers })).json();
  expect(courses.courses.some((c) => c.codes.includes(code))).toBe(true);
  const sent = await laptop.request.post(`${HUB}/api/events`, { headers, data: {
    id: "7f3c2a10-5b1e-4c7d-9a54-1f2e3d4c5b6a", type: "notes.ready", source: "verbatim", occurredAt: "2026-11-01T12:00:00+01:00",
    payload: { recording: { courseCode: code, title: "Les", recordedOn: day }, kind: "notes", verbatimJob: "job-1" },
  } });
  expect(sent.ok()).toBe(true);

  await laptop.getByRole("button", { name: "Lijst" }).click();
  await expect(laptop.getByText("Notities klaar").first()).toBeVisible({ timeout: 8000 });
});
