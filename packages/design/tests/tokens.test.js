import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const read = (name) => readFileSync(new URL(`../${name}`, import.meta.url), "utf8");
const tokensCss = read("tokens.css");
const componentsCss = read("components.css");

const parseVars = (block) => Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
const between = (text, start) => {
  const from = text.indexOf("{", text.indexOf(start)) + 1;
  return text.slice(from, text.indexOf("}", from));
};

const light = parseVars(between(tokensCss, ":root {"));
const systemDark = parseVars(between(tokensCss, ':root:not([data-theme="light"])'));
const forcedDark = parseVars(between(tokensCss, ':root[data-theme="dark"]'));
const dark = { ...light, ...forcedDark };

function rgba(value) {
  if (value.startsWith("#")) {
    const n = parseInt(value.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255, 1];
  }
  return value.match(/[\d.]+/g).map(Number);
}
const over = (top, bottom) => {
  const [r, g, b, a] = rgba(top);
  const [br, bg, bb] = rgba(bottom);
  return `#${[r * a + br * (1 - a), g * a + bg * (1 - a), b * a + bb * (1 - a)]
    .map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
};
const luminance = (hex) => {
  const [r, g, b] = rgba(hex).map((c) => c / 255);
  const f = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

const courses = ["blue", "indigo", "purple", "pink", "red", "orange", "yellow", "green"];

describe.each([["licht", light], ["donker", dark]])("contrast %s", (_, t) => {
  it.each([["--text"], ["--text-2"], ["--accent-text"], ["--danger"]])("%s is leesbaar op achtergrond en kaart", (name) => {
    expect(contrast(t[name], t["--bg"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t[name], t["--card"])).toBeGreaterThanOrEqual(4.5);
  });

  it("de gekozen knop in een gesegmenteerde balk valt op", () => {
    expect(contrast(t["--text"], t["--segment-on"])).toBeGreaterThanOrEqual(4.5);
    expect(luminance(t["--segment-on"])).not.toBeCloseTo(luminance(over(t["--fill"], t["--card"])), 1);
  });

  it("tekst op accent en toast is leesbaar", () => {
    expect(contrast(t["--on-accent"], t["--accent"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--on-toast"], t["--toast"])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--toast-action"], t["--toast"])).toBeGreaterThanOrEqual(4.5);
  });

  it("tekst blijft leesbaar op de vulling van knoppen en de banner", () => {
    for (const layer of ["--fill", "--accent-tint"]) {
      for (const surface of ["--bg", "--card"]) {
        const fill = over(t[layer], t[surface]);
        expect(contrast(t["--text"], fill)).toBeGreaterThanOrEqual(4.5);
        expect(contrast(t["--accent-text"], fill)).toBeGreaterThanOrEqual(4.5);
        expect(contrast(t["--danger"], fill)).toBeGreaterThanOrEqual(4.5);
      }
    }
    expect(contrast(t["--text-2"], over(t["--fill"], t["--card"]))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(courses)("vakkleur %s", (name) => {
    const color = t[`--course-${name}`];
    // WCAG 1.4.11: grafische elementen minstens 3:1.
    expect(contrast(color, t["--card"])).toBeGreaterThanOrEqual(3);
    expect(contrast(t["--on-course"], color)).toBeGreaterThanOrEqual(3);
    const tinted = over(t[`--course-${name}-tint`], t["--bg"]);
    expect(contrast(t["--text"], tinted)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t["--text-2"], tinted)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("tokens", () => {
  it("heeft dezelfde donkere waarden voor systeem en keuze", () => {
    expect(systemDark).toEqual(forcedDark);
  });

  it("volgt de maten uit het plan", () => {
    expect(light["--bg"]).toBe("#F2F2F7");
    expect(dark["--bg"]).toBe("#000000");
    expect(light["--card"]).toBe("#FFFFFF");
    expect(dark["--card"]).toBe("#1C1C1E");
    expect(light["--radius-row"]).toBe("10px");
    expect(light["--radius-card"]).toBe("16px");
    expect(light["--radius-sheet"]).toBe("22px");
    expect(light["--row-min"]).toBe("44px");
  });

  it("gebruikt in components.css enkel bestaande tokens", () => {
    const used = [...componentsCss.matchAll(/var\((--[\w-]+)/g)].map((m) => m[1]);
    const local = new Set(["--tone", "--tone-tint", "--on-tone", "--value", "--size", "--app-height"]);
    const unknown = used.filter((name) => !(name in light) && !local.has(name));
    expect(unknown).toEqual([]);
  });

  it("heeft geen losse kleuren in components.css", () => {
    const withoutMask = componentsCss.replace(/#000 calc/g, "");
    expect(withoutMask.match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g)).toBeNull();
  });
});
