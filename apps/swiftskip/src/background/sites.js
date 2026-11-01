// Sites beyond the built-in ones (see shared/sites.js), enabled one at a time
// from the popup. The browser's permission list is the single source of
// truth: granting a site registers the content script there, removing it
// unregisters it. Also injects into already-open tabs, so SwiftSkip works
// without a page reload after installing, updating or enabling a site.

import { ext } from "../shared/ext.js";
import { inhaalMatch, inhaalPermission } from "../shared/inhaal.js";
import { LINK_KEY, getInhaalLink } from "./inhaal.js";

const SCRIPT_ID = "swiftskip-sites";
const BRIDGE_ID = "swiftskip-inhaal";
const BRIDGE = ["inhaal-bridge.js"];
const JS = ["content.js"];
const CSS = ["style.css"];

// Patterns the manifest's content script already covers.
function builtInPatterns() {
  return ext.runtime.getManifest().content_scripts.flatMap((script) => script.matches);
}

export async function enabledSites() {
  // Inhaal's address gets the small bridge, never the player script.
  const link = await getInhaalLink();
  const skipped = new Set([...builtInPatterns(), "*://*/*", "<all_urls>"]);
  if (link) skipped.add(inhaalPermission(link));
  const { origins = [] } = await ext.permissions.getAll();
  return origins.filter((origin) => !skipped.has(origin));
}

async function syncBridge() {
  const link = await getInhaalLink();
  const registered = await ext.scripting.getRegisteredContentScripts({ ids: [BRIDGE_ID] }).catch(() => []);
  if (registered.length) await ext.scripting.unregisterContentScripts({ ids: [BRIDGE_ID] });
  if (!link || !(await ext.permissions.contains({ origins: [inhaalPermission(link)] }))) return;
  const matches = [inhaalMatch(link)];
  await ext.scripting.registerContentScripts([
    { id: BRIDGE_ID, matches, js: BRIDGE, runAt: "document_idle", persistAcrossSessions: true },
  ]);
  const tabs = await ext.tabs.query({ url: matches }).catch(() => []);
  await Promise.all(
    tabs.map((tab) =>
      ext.scripting.executeScript({ target: { tabId: tab.id }, files: BRIDGE }).catch(() => {}),
    ),
  );
}

export async function syncSiteScripts() {
  await syncBridge();
  const sites = await enabledSites();
  const registered = await ext.scripting.getRegisteredContentScripts({ ids: [SCRIPT_ID] }).catch(() => []);
  if (registered.length) await ext.scripting.unregisterContentScripts({ ids: [SCRIPT_ID] });
  if (!sites.length) return;
  await ext.scripting.registerContentScripts([
    {
      id: SCRIPT_ID,
      matches: sites,
      js: JS,
      css: CSS,
      allFrames: true,
      runAt: "document_idle",
      persistAcrossSessions: true,
    },
  ]);
}

// Runs the content script in open tabs matching `patterns`. A copy that is
// already running there steps aside for the new one (see content.js).
export async function injectIntoOpenTabs(patterns) {
  if (!patterns.length) return;
  const tabs = await ext.tabs.query({ url: patterns }).catch(() => []);
  await Promise.all(
    tabs.map(async (tab) => {
      const target = { tabId: tab.id, allFrames: true };
      try {
        await ext.scripting.insertCSS({ target, files: CSS });
        await ext.scripting.executeScript({ target, files: JS });
      } catch {
        // Tab closed, discarded, or showing an error page — skip it.
      }
    }),
  );
}

export function startSiteManagement() {
  syncSiteScripts().catch((error) => console.error("SwiftSkip: registering sites failed:", error));

  ext.permissions.onAdded.addListener(async ({ origins = [] }) => {
    await syncSiteScripts().catch(() => {});
    const sites = new Set(await enabledSites());
    injectIntoOpenTabs(origins.filter((origin) => sites.has(origin)));
  });
  ext.permissions.onRemoved.addListener(() => {
    syncSiteScripts().catch(() => {});
  });

  ext.storage.onChanged.addListener((changes, area) => {
    if (area === "local" && LINK_KEY in changes) syncSiteScripts().catch(() => {});
  });

  // Chrome and Safari don't inject into tabs that were open before an
  // install/update (Firefox does for the manifest's content script).
  ext.runtime.onInstalled.addListener(async ({ reason }) => {
    if (reason !== "install" && reason !== "update") return;
    const sites = await enabledSites().catch(() => []);
    injectIntoOpenTabs(__BROWSER__ === "firefox" ? sites : [...builtInPatterns(), ...sites]);
  });
}
