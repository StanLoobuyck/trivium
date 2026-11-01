import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const design = join(here, "..");
const apps = join(here, "../../../apps");

function darkTokens() {
  const css = readFileSync(join(design, "tokens.css"), "utf8");
  const block = css.slice(css.indexOf(':root[data-theme="dark"]'));
  return Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim().toLowerCase()]));
}

describe("één look: de apps gebruiken packages/design", () => {
  it.each(["tokens.css", "components.css", "icons.js"])("Verbatim heeft een exacte kopie van %s", (file) => {
    const copy = readFileSync(join(apps, "verbatim/src/lecture/web/design", file), "utf8");
    expect(copy, "draai: node scripts/sync-design.mjs").toBe(readFileSync(join(design, file), "utf8"));
  });

  it("Verbatim laadt de gedeelde stijl en geen eigen tokens", () => {
    const html = readFileSync(join(apps, "verbatim/src/lecture/web/index.html"), "utf8");
    expect(html).toContain("/static/design/tokens.css");
    expect(html).toContain("/static/design/components.css");
    expect(html).toContain('class="sidebar"');
  });

  it.each(["popup/popup.html", "options/options.html", "welcome/welcome.html"])("SwiftSkip %s laadt de gedeelde stijl", (file) => {
    const html = readFileSync(join(apps, "swiftskip/src", file), "utf8");
    expect(html).toContain('href="tokens.css"');
    expect(html).toContain('href="components.css"');
  });

  it("de speler-overlay gebruikt de donkere waarden van de tokens", () => {
    const css = readFileSync(join(apps, "swiftskip/src/content/style.css"), "utf8");
    const dark = darkTokens();
    const value = (name) => css.match(new RegExp(`${name}:\\s*([^;]+);`))[1].trim().toLowerCase();
    expect(value("--ss-card")).toBe(dark["--card"]);
    expect(value("--ss-text-2")).toBe(dark["--text-2"]);
    expect(value("--ss-accent")).toBe(dark["--accent"]);
    expect(value("--ss-accent-text")).toBe(dark["--accent-text"]);
    expect(value("--ss-toast-action")).toBe(dark["--toast-action"]);
    expect(value("--ss-separator")).toBe(dark["--separator"]);
  });
});
