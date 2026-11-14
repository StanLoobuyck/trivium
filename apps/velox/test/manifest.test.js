import assert from "node:assert/strict";
import { test } from "node:test";
import { buildManifest } from "../scripts/manifest.js";

const opts = { version: "1.2.3", dev: false };

test("firefox manifest is MV2 with a persistent background and a gecko id", () => {
  const m = buildManifest("firefox", opts);
  assert.equal(m.manifest_version, 2);
  assert.equal(m.background.persistent, true);
  assert.equal(m.browser_specific_settings.gecko.id, "velox@stanloobuyck.github.io");
  assert.ok(m.browser_action);
});

test("chrome manifest is MV3 with a service worker and the offscreen permission", () => {
  const m = buildManifest("chrome", opts);
  assert.equal(m.manifest_version, 3);
  assert.equal(m.background.service_worker, "background.js");
  assert.ok(m.permissions.includes("offscreen"));
  assert.ok(m.action);
});

test("safari manifest has no downloads permission (unsupported there)", () => {
  const m = buildManifest("safari", opts);
  assert.equal(m.manifest_version, 3);
  assert.ok(!m.permissions.includes("downloads"));
});

test("safari manifest has a 1024 px icon for the App Store app; others stop at 128", () => {
  assert.equal(buildManifest("safari", opts).icons[1024], "icons/icon1024.png");
  assert.equal(buildManifest("chrome", opts).icons[1024], undefined);
});

test("dev builds are labelled so they're distinguishable from the release", () => {
  assert.equal(buildManifest("chrome", { ...opts, dev: true }).name, "Velox (dev)");
  assert.equal(buildManifest("chrome", opts).version, "1.2.3");
});

test("no build asks for all websites up front; other sites are optional", () => {
  for (const target of ["firefox", "chrome", "safari"]) {
    const m = buildManifest(target, opts);
    const upfront = [...m.permissions, ...(m.host_permissions || [])];
    assert.ok(!upfront.includes("<all_urls>") && !upfront.includes("*://*/*"), target);
    assert.deepEqual(m.content_scripts[0].matches, [
      "*://*.kuleuven.be/*",
      "*://*.kuleuven.cloud/*",
      "*://*.kaltura.com/*",
      "http://127.0.0.1/*", // Verbatim (content.js only stays on its port)
      "http://localhost/*",
      "https://*.ts.net/share/*", // lectures shared from someone's Verbatim hub
    ]);
    assert.deepEqual(m.optional_permissions || m.optional_host_permissions, ["*://*/*"]);
  }
});

test("every build covers local pages: Verbatim's in release builds (content.js checks the port)", () => {
  for (const dev of [true, false]) {
    const matches = buildManifest("chrome", { ...opts, dev }).content_scripts[0].matches;
    assert.ok(matches.includes("http://localhost/*") && matches.includes("http://127.0.0.1/*"));
  }
});

test("release Firefox builds point to the self-hosted update manifest; dev builds don't", () => {
  const release = buildManifest("firefox", opts).browser_specific_settings.gecko;
  assert.equal(release.update_url, "https://stanloobuyck.github.io/trivium/velox/updates.json");
  assert.equal(
    buildManifest("firefox", { ...opts, dev: true }).browser_specific_settings.gecko.update_url,
    undefined,
  );
});

test("web_accessible_resources only lists origins (Chrome refuses the extension for a path like /share/*)", () => {
  for (const target of ["chrome", "safari"]) {
    const { matches } = buildManifest(target, opts).web_accessible_resources[0];
    assert.ok(
      matches.every((m) => /^[^:]+:\/\/[^/]+\/\*$/.test(m)),
      `${target}: ${matches}`,
    );
    assert.ok(matches.includes("https://*.ts.net/*"));
  }
});
