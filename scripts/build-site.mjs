// Stelt _site/ samen voor GitHub Pages: site/ + Inhaal-build + designpakket.
import { cpSync, rmSync } from "node:fs";

const noTests = (path) => !/\/(tests|node_modules)(\/|$)|package\.json$/.test(path);

rmSync("_site", { recursive: true, force: true });
cpSync("site", "_site", { recursive: true });
cpSync("apps/inhaal/dist", "_site/inhaal", { recursive: true });
cpSync("packages/design", "_site/design", { recursive: true, filter: noTests });
