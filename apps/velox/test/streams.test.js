import assert from "node:assert/strict";
import { test } from "node:test";
import { trackStreams } from "../src/shared/streams.js";

const manifest = (entry, rest = "a.m3u8") =>
  `https://cfvod.kaltura.com/p/1/playManifest/entryId/${entry}/format/applehttp/${rest}`;
const empty = { main: null, companion: null };

test("the first playlist is the main stream; its variants change nothing", () => {
  const first = trackStreams(empty, manifest("1_slides"));
  assert.equal(first.change, "main");
  assert.equal(first.streams.main.entry, "1_slides");
  assert.equal(trackStreams(first.streams, manifest("1_slides", "b.m3u8")).change, null);
  assert.equal(trackStreams(first.streams, "https://x/not-a-playlist.js").change, null);
});

test("a second picture playing at the same time is the companion, not another lecture", () => {
  const { streams } = trackStreams(empty, manifest("1_slides"));
  const next = trackStreams(streams, manifest("1_webcam"), { videoCount: 2 });
  assert.equal(next.change, "companion");
  assert.equal(next.streams.main.entry, "1_slides");
  assert.equal(next.streams.companion.entry, "1_webcam");
  assert.equal(trackStreams(next.streams, manifest("1_webcam", "v2.m3u8"), { videoCount: 2 }).change, null);
});

test("the frame's entry is the main picture, also when the webcam's playlist loads first", () => {
  const { streams } = trackStreams(empty, manifest("1_webcam"), { frameEntry: "1_slides" });
  const next = trackStreams(streams, manifest("1_slides"), { frameEntry: "1_slides", videoCount: 2 });
  assert.equal(next.change, "swap");
  assert.equal(next.streams.main.entry, "1_slides");
  assert.equal(next.streams.companion.entry, "1_webcam");
});

test("the frame's entry still playing makes another entry the companion, even before its video exists", () => {
  const { streams } = trackStreams(empty, manifest("1_slides"), { frameEntry: "1_slides" });
  const next = trackStreams(streams, manifest("1_webcam"), { frameEntry: "1_slides", videoCount: 1 });
  assert.equal(next.change, "companion");
});

test("another entry with one picture is another lecture", () => {
  const { streams } = trackStreams(empty, manifest("1_les4"));
  const next = trackStreams(streams, manifest("1_les5"), { videoCount: 1 });
  assert.equal(next.change, "switch");
  assert.deepEqual(next.streams, { main: { url: manifest("1_les5"), entry: "1_les5" }, companion: null });
});

test("a third entry after a pair is another lecture", () => {
  let { streams } = trackStreams(empty, manifest("1_slides"));
  ({ streams } = trackStreams(streams, manifest("1_webcam"), { videoCount: 2 }));
  const next = trackStreams(streams, manifest("1_les5"), { videoCount: 2 });
  assert.equal(next.change, "switch");
  assert.equal(next.streams.companion, null);
});
