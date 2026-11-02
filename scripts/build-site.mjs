// Stelt _site/ samen voor GitHub Pages: site/ + Inhaal-build + designpakket.
// De landingspagina krijgt de nieuwste Velox-versie en downloads uit site/swiftskip/updates.json.
import { cpSync, readFileSync, rmSync, writeFileSync } from "node:fs";

const noTests = (path) => !/\/(tests|node_modules)(\/|$)|package\.json$/.test(path);

export function newestVelox(updatesJson) {
  const [addon] = Object.values(JSON.parse(updatesJson).addons);
  const byVersion = (a, b) => a.version.localeCompare(b.version, "en", { numeric: true });
  const { version, update_link: xpi } = [...addon.updates].sort(byVersion).at(-1);
  return { version, xpi, zip: xpi.replace(/swiftskip-firefox\.xpi$/, "swiftskip-chrome.zip") };
}

export function fillLanding(html, velox) {
  const out = html.replaceAll("%%VELOX_VERSION%%", velox.version).replaceAll("%%VELOX_XPI%%", velox.xpi)
    .replaceAll("%%VELOX_ZIP%%", velox.zip);
  if (out.includes("%%")) throw new Error("landingspagina heeft nog een lege plaatshouder");
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  rmSync("_site", { recursive: true, force: true });
  cpSync("site", "_site", { recursive: true });
  cpSync("apps/inhaal/dist", "_site/inhaal", { recursive: true });
  cpSync("packages/design", "_site/design", { recursive: true, filter: noTests });
  const velox = newestVelox(readFileSync("site/swiftskip/updates.json", "utf8"));
  writeFileSync("_site/index.html", fillLanding(readFileSync("site/index.html", "utf8"), velox));
  console.log(`landingspagina: Velox ${velox.version}`);
}
