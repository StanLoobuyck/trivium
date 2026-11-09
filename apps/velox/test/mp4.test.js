import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { test } from "node:test";
import { remuxToMp4 } from "../src/shared/downloader.js";
import { readBoxes } from "../src/shared/mp4.js";

const HLS = new URL("./fixtures/media/hls/", import.meta.url);

// The 12 test segments (2 min, 640×360 + AAC) through Velox's TS → MP4 path.
async function remuxFixture() {
  const names = (await readdir(HLS)).filter((n) => n.endsWith(".ts")).sort();
  const blobs = await Promise.all(names.map(async (n) => new Blob([await readFile(new URL(n, HLS))])));
  return new Uint8Array(await (await remuxToMp4(blobs, new AbortController().signal)).arrayBuffer());
}

const CONTAINERS = new Set(["moov", "trak", "mdia", "minf", "stbl"]);
function find(bytes, path, start = 0, end = bytes.length) {
  const [type, ...rest] = path;
  return readBoxes(bytes, start, end)
    .filter((b) => b.type === type)
    .flatMap((b) =>
      rest.length ? (CONTAINERS.has(type) ? find(bytes, rest, b.start + b.header, b.end) : []) : [b],
    );
}
const u32 = (bytes, offset) => new DataView(bytes.buffer, bytes.byteOffset).getUint32(offset);

test("remuxToMp4 writes an ordinary MP4 (one moov with sample tables, one mdat), not fragments", async () => {
  const mp4 = await remuxFixture();
  const top = readBoxes(mp4).map((b) => b.type);
  assert.deepEqual(top, ["ftyp", "moov", "mdat"]);
  assert.equal(find(mp4, ["moov", "mvex"]).length, 0);

  // Sample counts per track: 3000 video frames (25 fps · 120 s), 5169 AAC frames.
  const counts = find(mp4, ["moov", "trak", "mdia", "minf", "stbl", "stsz"]).map((b) =>
    u32(mp4, b.start + 16),
  );
  assert.deepEqual(counts.sort(), [3000, 5169].sort());
  // Every chunk offset points inside the mdat.
  const [mdat] = find(mp4, ["mdat"]);
  for (const co64 of find(mp4, ["moov", "trak", "mdia", "minf", "stbl", "co64"])) {
    const view = new DataView(mp4.buffer);
    const n = view.getUint32(co64.start + 12);
    assert.ok(n > 0);
    for (let i = 0; i < n; i++) {
      const offset = Number(view.getBigUint64(co64.start + 16 + i * 8));
      assert.ok(offset >= mdat.start + 16 && offset < mdat.end, `chunk ${i} at ${offset}`);
    }
  }
});

test("remuxToMp4 writes the real duration, not mux.js's 'unknown' (QuickTime showed 27 h)", async () => {
  const mp4 = await remuxFixture();
  const [mvhd] = find(mp4, ["moov", "mvhd"]);
  const seconds = u32(mp4, mvhd.start + 24) / u32(mp4, mvhd.start + 20);
  assert.ok(Math.abs(seconds - 120.1) < 0.2, `${seconds} s`);
  for (const mdhd of find(mp4, ["moov", "trak", "mdia", "mdhd"])) {
    const trackSeconds = u32(mp4, mdhd.start + 24) / u32(mp4, mdhd.start + 20);
    assert.ok(Math.abs(trackSeconds - 120) < 0.2, `${trackSeconds} s`);
  }
});

test("the audio track keeps its later start as an edit list (stays in sync with the video)", async () => {
  const mp4 = await remuxFixture();
  const elst = find(mp4, ["moov", "trak", "edts"]);
  assert.equal(elst.length, 1); // only audio starts later (57 ms) in the fixture
});
