// Which HLS streams belong to the lecture in this frame — pure, unit-tested in test/streams.test.js.
//
// A Kaltura recording can have two pictures (slides and webcam): two entries, each with its own playlist, played
// side by side by the dual-screen player. The "main" entry is the one the player was opened for (its id is in the
// frame's URL); by default the player shows it big, and on Toledo that is the slides. The other is the "companion".
// A playlist of yet another entry, while no second picture is playing, means the player moved to another lecture.

import { isLectureManifestUrl } from "./hls.js";
import { kalturaEntryId } from "./playback.js";

// streams: { main: { url, entry } | null, companion: { url, entry } | null }
// Returns { streams, change } with change one of "main" | "companion" | "swap" | "switch" | null.
export function trackStreams(streams, url, { frameEntry = null, videoCount = 1 } = {}) {
  const none = { streams, change: null };
  if (!isLectureManifestUrl(url)) return none;
  const entry = kalturaEntryId(url);
  const stream = { url, entry };
  const { main, companion } = streams;
  if (!main) return { streams: { main: stream, companion: null }, change: "main" };
  // Variant playlists of a stream we already have.
  if (!entry || entry === main.entry || entry === companion?.entry) return none;

  const secondPicture = videoCount >= 2 || (frameEntry && frameEntry === main.entry);
  if (!companion && frameEntry && entry === frameEntry) {
    // The companion's playlist came first; the frame says this one is the main picture.
    return { streams: { main: stream, companion: main }, change: "swap" };
  }
  if (!companion && secondPicture) return { streams: { main, companion: stream }, change: "companion" };
  return { streams: { main: stream, companion: null }, change: "switch" };
}
