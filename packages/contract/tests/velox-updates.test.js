import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Firefox leest dit bestand om Velox bij te werken. Een fout hier stopt stil de updates van echte gebruikers.
const manifest = JSON.parse(readFileSync("site/velox/updates.json", "utf8"));
const updates = manifest.addons["velox@stanloobuyck.github.io"].updates;
const parts = (version) => version.split(".").map(Number);

describe("Velox updates.json", () => {
  it("bevat alleen de add-on van Velox", () => {
    expect(Object.keys(manifest.addons)).toEqual(["velox@stanloobuyck.github.io"]);
  });

  it("geeft elke versie een ondertekend bestand op GitHub en een sha256", () => {
    for (const { version, update_link, update_hash } of updates) {
      expect(version).toMatch(/^\d+\.\d+\.\d+$/);
      expect(update_link).toMatch(/^https:\/\/github\.com\/StanLoobuyck\/[^/]+\/releases\/download\/[^/]+\/velox-firefox\.xpi$/);
      expect(update_link).toContain(version);
      expect(update_hash).toMatch(/^sha256:[0-9a-f]{64}$/);
    }
  });

  it("staat oplopend, want Firefox neemt de hoogste versie", () => {
    for (let i = 1; i < updates.length; i++) {
      const [a, b] = [parts(updates[i - 1].version), parts(updates[i].version)];
      const first = a.findIndex((value, index) => value !== b[index]);
      expect(a[first]).toBeLessThan(b[first]);
    }
  });
});
