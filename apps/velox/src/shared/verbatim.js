// Verbatim on this computer (its local app on port 7861): Velox then saves downloads where Verbatim picks them
// up, without the user having to find that setting. Only while the user never chose it themselves.

import { VERBATIM_PORT } from "./sites.js";

const PAGE = `http://127.0.0.1:${VERBATIM_PORT}/`;

// True when Verbatim's own page answers (not just anything on that port).
export async function verbatimRunning(fetchFn = fetch) {
  try {
    const response = await fetchFn(PAGE, { signal: AbortSignal.timeout(1500), cache: "no-store" });
    return response.ok && (await response.text()).includes("<title>Verbatim</title>");
  } catch {
    return false;
  }
}

// The setting to use for a download: turned on once when Verbatim runs here and the user never chose.
// `load` reads the settings again after the probe: a choice made meanwhile wins.
export async function autoVerbatim(settings, save, probe = verbatimRunning, load = async () => settings) {
  if (settings.downloadsToVerbatim || settings.downloadsToVerbatimChosen) return settings.downloadsToVerbatim;
  if (!(await probe())) return false;
  const now = await load();
  if (now.downloadsToVerbatimChosen) return now.downloadsToVerbatim;
  await save({ downloadsToVerbatim: true });
  return true;
}
