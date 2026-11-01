// Kopieert packages/design naar Verbatim. Verbatim heeft geen buildstap en draait los van de monorepo, dus de bestanden
// staan er letterlijk; packages/design/tests/synced.test.js faalt zodra de kopie afwijkt. SwiftSkip kopieert bij het bouwen.
import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const from = join(root, "packages/design");
const to = join(root, "apps/verbatim/src/lecture/web/design");

await rm(to, { recursive: true, force: true });
await mkdir(join(to, "fonts"), { recursive: true });
for (const file of ["tokens.css", "components.css", "icons.js", "fonts/Inter.woff2", "fonts/OFL.txt"]) {
  await cp(join(from, file), join(to, file));
}
console.log("packages/design → apps/verbatim/src/lecture/web/design");
