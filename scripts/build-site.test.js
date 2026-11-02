import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { fillLanding, newestVelox } from "./build-site.mjs";

const link = (v) => `https://github.com/StanLoobuyck/trivium/releases/download/swiftskip-v${v}/swiftskip-firefox.xpi`;
const updates = (...versions) => JSON.stringify({ addons: { x: { updates: versions.map((v) => ({ version: v, update_link: link(v) })) } } });

describe("landingspagina", () => {
  it("neemt de hoogste Velox-versie, ook als 4.10 na 4.9 komt", () => {
    const v = newestVelox(updates("4.9.0", "4.10.0", "4.2.1"));
    expect(v.version).toBe("4.10.0");
    expect(v.zip).toBe(link("4.10.0").replace("firefox.xpi", "chrome.zip"));
  });

  it("vult elke plaatshouder van de echte pagina in", () => {
    const html = fillLanding(readFileSync("site/index.html", "utf8"), newestVelox(readFileSync("site/swiftskip/updates.json", "utf8")));
    expect(html).not.toContain("%%");
    expect(html).toContain("swiftskip-chrome.zip");
  });

  it("weigert een pagina met een onbekende plaatshouder", () => {
    expect(() => fillLanding("%%NIEUW%%", newestVelox(updates("1.0.0")))).toThrow();
  });
});
