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

describe("privacypagina", () => {
  const privacy = readFileSync("site/privacy/index.html", "utf8");
  const landing = readFileSync("site/index.html", "utf8");

  it("heeft elk stuk waar de landingspagina naar linkt, in beide talen", () => {
    const anchors = [...landing.matchAll(/href="\.\/privacy\/#([a-z]+)"/g)].map((m) => m[1]);
    expect(anchors).toEqual(["sequo", "velox", "verbatim"]);
    for (const id of anchors) {
      expect(privacy).toContain(`id="${id}"`);
      expect(privacy).toContain(`id="${id}-en"`);
    }
  });

  it("heeft een Nederlands en een Engels stuk", () => {
    expect(privacy).toContain('data-lang="nl"');
    expect(privacy).toContain('data-lang="en"');
  });
});
