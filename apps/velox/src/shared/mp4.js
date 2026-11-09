// Fragmented MP4 (what mux.js makes) → ordinary MP4 — pure, unit-tested.
//
// mux.js writes fragments (moof + mdat) with "duration unknown" (0xFFFFFFFF) in
// the header. QuickTime/AVFoundation can't play such a file from disk: it shows
// a 27 h video and a black picture. An ordinary MP4 (one moov with full sample
// tables, then one mdat) plays everywhere, so we rebuild one from the sample
// lists in the fragments. Sample data is kept as Blobs (not on the JS heap).
//
// Layout: ftyp · moov · mdat (64-bit size). One chunk per fragment per track.

const CONTAINERS = new Set(["moov", "trak", "mdia", "minf", "stbl", "edts", "dinf"]);

function view(bytes) {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

// Top-level boxes in bytes[start, end): [{ type, start, end }].
export function readBoxes(bytes, start = 0, end = bytes.length) {
  const v = view(bytes);
  const found = [];
  let offset = start;
  while (offset + 8 <= end) {
    let size = v.getUint32(offset);
    let header = 8;
    if (size === 1) {
      size = Number(v.getBigUint64(offset + 8));
      header = 16;
    } else if (size === 0) size = end - offset;
    if (size < header || offset + size > end) break;
    const type = String.fromCharCode(...bytes.subarray(offset + 4, offset + 8));
    found.push({ type, start: offset, end: offset + size, header });
    offset += size;
  }
  return found;
}

function children(bytes, box) {
  return readBoxes(bytes, box.start + box.header, box.end);
}

function box(type, ...parts) {
  const size = 8 + parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(size);
  view(out).setUint32(0, size);
  for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i);
  let offset = 8;
  for (const p of parts) {
    out.set(p, offset);
    offset += p.length;
  }
  return out;
}

// A full box: version + flags, then 32-bit (or 64-bit) fields.
function fullBox(type, version, values, wide = false) {
  const width = wide ? 8 : 4;
  const out = new Uint8Array(4 + values.length * width);
  const v = view(out);
  v.setUint32(0, version << 24);
  values.forEach((value, i) => {
    if (wide) v.setBigUint64(4 + i * 8, BigInt(value));
    else v.setUint32(4 + i * 4, value >>> 0);
  });
  return box(type, out);
}

// ─── Reading fragments ────────────────────────────────────────────────────────

function newTrack(id) {
  return {
    id,
    durations: [],
    sizes: [],
    sync: [],
    offsets: [],
    chunks: [],
    start: null,
    hasCto: false,
    allSync: true,
  };
}

// Adds the samples of one transmuxer output (one or more moof + mdat pairs) to
// `tracks` (Map trackId → track) and returns the sample bytes, in order, as
// [{ trackId, bytes }]: one chunk per moof.
export function readFragments(data, tracks) {
  const chunks = [];
  const v = view(data);
  for (const moof of readBoxes(data).filter((b) => b.type === "moof")) {
    for (const traf of children(data, moof).filter((b) => b.type === "traf")) {
      const parts = children(data, traf);
      const tfhd = parts.find((b) => b.type === "tfhd");
      if (!tfhd) continue;
      const tfhdFlags = v.getUint32(tfhd.start + 8) & 0xffffff;
      const trackId = v.getUint32(tfhd.start + 12);
      let pos = tfhd.start + 16;
      let base = moof.start; // no base-data-offset: relative to the moof
      if (tfhdFlags & 0x01) {
        base = Number(v.getBigUint64(pos));
        pos += 8;
      }
      if (tfhdFlags & 0x02) pos += 4;
      const defaultDuration = tfhdFlags & 0x08 ? v.getUint32(pos) : 0;
      if (tfhdFlags & 0x08) pos += 4;
      const defaultSize = tfhdFlags & 0x10 ? v.getUint32(pos) : 0;
      if (tfhdFlags & 0x10) pos += 4;
      const defaultFlags = tfhdFlags & 0x20 ? v.getUint32(pos) : 0;

      if (!tracks.has(trackId)) tracks.set(trackId, newTrack(trackId));
      const track = tracks.get(trackId);
      const tfdt = parts.find((b) => b.type === "tfdt");
      if (track.start === null && tfdt) {
        track.start =
          data[tfdt.start + 8] === 1 ? Number(v.getBigUint64(tfdt.start + 12)) : v.getUint32(tfdt.start + 12);
      }

      for (const trun of parts.filter((b) => b.type === "trun")) {
        const flags = v.getUint32(trun.start + 8) & 0xffffff;
        const count = v.getUint32(trun.start + 12);
        let p = trun.start + 16;
        let dataStart = base;
        if (flags & 0x01) {
          dataStart = base + v.getInt32(p);
          p += 4;
        }
        let firstFlags = null;
        if (flags & 0x04) {
          firstFlags = v.getUint32(p);
          p += 4;
        }
        let length = 0;
        for (let i = 0; i < count; i++) {
          const duration = flags & 0x100 ? v.getUint32((p += 4) - 4) : defaultDuration;
          const size = flags & 0x200 ? v.getUint32((p += 4) - 4) : defaultSize;
          let sampleFlags = flags & 0x400 ? v.getUint32((p += 4) - 4) : defaultFlags;
          if (i === 0 && firstFlags !== null) sampleFlags = firstFlags;
          const offset = flags & 0x800 ? v.getInt32((p += 4) - 4) : 0;
          const sync = (sampleFlags & 0x10000) === 0; // sample_is_non_sync_sample
          track.durations.push(duration);
          track.sizes.push(size);
          track.sync.push(sync);
          track.offsets.push(offset);
          if (offset) track.hasCto = true;
          if (!sync) track.allSync = false;
          length += size;
        }
        track.chunks.push(count);
        chunks.push({ trackId, bytes: data.subarray(dataStart, dataStart + length) });
      }
    }
  }
  return chunks;
}

// ─── Writing the header ───────────────────────────────────────────────────────

function runLengths(values) {
  const runs = [];
  for (const value of values) {
    const last = runs[runs.length - 1];
    if (last && last[1] === value) last[0]++;
    else runs.push([1, value]);
  }
  return runs;
}

function sampleTable(stsd, track, chunkOffsets) {
  const tables = [stsd];
  const stts = runLengths(track.durations);
  tables.push(fullBox("stts", 0, [stts.length, ...stts.flat()]));
  if (track.hasCto) {
    const runs = runLengths(track.offsets);
    const negative = track.offsets.some((o) => o < 0);
    tables.push(fullBox("ctts", negative ? 1 : 0, [runs.length, ...runs.flat()]));
  }
  if (!track.allSync) {
    const syncSamples = track.sync.flatMap((s, i) => (s ? [i + 1] : []));
    tables.push(fullBox("stss", 0, [syncSamples.length, ...syncSamples]));
  }
  const stsc = [];
  track.chunks.forEach((count, i) => {
    if (stsc.length === 0 || stsc[stsc.length - 1][1] !== count) stsc.push([i + 1, count, 1]);
  });
  tables.push(fullBox("stsc", 0, [stsc.length, ...stsc.flat()]));
  tables.push(fullBox("stsz", 0, [0, track.sizes.length, ...track.sizes]));
  // co64: 64-bit offsets, so lectures over 4 GB work too.
  const co64 = new Uint8Array(8 + chunkOffsets.length * 8);
  const v = view(co64);
  v.setUint32(4, chunkOffsets.length);
  chunkOffsets.forEach((o, i) => v.setBigUint64(8 + i * 8, BigInt(o)));
  tables.push(box("co64", co64));
  return box("stbl", ...tables);
}

// Rebuilds a box from `init`, replacing descendants through `edit(type, bytes, box)`,
// which returns new bytes, null (drop it) or undefined (keep, recurse into containers).
function rebuild(init, b, edit) {
  const result = edit(b.type, init.subarray(b.start, b.end), b);
  if (result !== undefined) return result;
  if (!CONTAINERS.has(b.type)) return init.slice(b.start, b.end);
  const parts = children(init, b)
    .map((c) => rebuild(init, c, edit))
    .filter(Boolean);
  return box(b.type, ...parts);
}

function readUint(bytes, offset, wide) {
  const v = view(bytes);
  return wide ? Number(v.getBigUint64(offset)) : v.getUint32(offset);
}

function setUint(bytes, offset, value, wide) {
  const v = view(bytes);
  if (wide) v.setBigUint64(offset, BigInt(value));
  else v.setUint32(offset, Math.min(value, 0xffffffff));
}

function buildMoov(init, tracks, offsetsFor) {
  const [moov] = readBoxes(init).filter((b) => b.type === "moov");
  const mvhdBox = children(init, moov).find((b) => b.type === "mvhd");
  const mvhdWide = init[mvhdBox.start + 8] === 1;
  const movieScale = readUint(init, mvhdBox.start + (mvhdWide ? 28 : 20), false);
  let movieDuration = 0;

  const traks = [];
  for (const trak of children(init, moov).filter((b) => b.type === "trak")) {
    const tkhd = children(init, trak).find((b) => b.type === "tkhd");
    const tkhdWide = init[tkhd.start + 8] === 1;
    const track = tracks.get(readUint(init, tkhd.start + (tkhdWide ? 28 : 20), false));
    if (!track || track.sizes.length === 0) continue;
    const mdia = children(init, trak).find((b) => b.type === "mdia");
    const mdhd = children(init, mdia).find((b) => b.type === "mdhd");
    const mdhdWide = init[mdhd.start + 8] === 1;
    const trackScale = readUint(init, mdhd.start + (mdhdWide ? 28 : 20), false);
    const ticks = track.durations.reduce((a, b) => a + b, 0);
    const movieTicks = Math.round((ticks / trackScale) * movieScale);
    // A track that starts later (audio a few ms after video) keeps that gap: an empty edit first.
    const delay = Math.round(((track.start || 0) / trackScale) * movieScale);
    movieDuration = Math.max(movieDuration, delay + movieTicks);

    traks.push(
      rebuild(init, trak, (type, bytes, b) => {
        if (type === "tkhd") {
          const out = bytes.slice();
          setUint(out, tkhdWide ? 36 : 28, delay + movieTicks, tkhdWide);
          if (delay <= 0) return out;
          // elst: segment_duration, media_time (-1 = empty), media_rate 1.0 — then the media from 0.
          const elst = fullBox("elst", 0, [2, delay, 0xffffffff, 0x00010000, movieTicks, 0, 0x00010000]);
          const edts = box("edts", elst);
          const both = new Uint8Array(out.length + edts.length);
          both.set(out);
          both.set(edts, out.length);
          return both;
        }
        if (type === "edts") return null;
        if (type === "mdhd") {
          const out = bytes.slice();
          setUint(out, mdhdWide ? 32 : 24, ticks, mdhdWide);
          return out;
        }
        if (type === "stbl") {
          const stsd = children(init, b).find((c) => c.type === "stsd");
          return sampleTable(init.slice(stsd.start, stsd.end), track, offsetsFor(track.id));
        }
        return undefined;
      }),
    );
  }

  const mvhd = init.slice(mvhdBox.start, mvhdBox.end);
  setUint(mvhd, mvhdWide ? 32 : 24, movieDuration, mvhdWide);
  return box("moov", mvhd, ...traks);
}

// ─── Writer ───────────────────────────────────────────────────────────────────

// Feed every transmuxer output with add(initSegment, data); finish() → Blob.
export function createMp4Writer() {
  let init = null;
  const tracks = new Map();
  const chunks = []; // { trackId, blob, length }

  return {
    add(initSegment, data) {
      if (!init) init = initSegment;
      for (const { trackId, bytes } of readFragments(data, tracks)) {
        chunks.push({ trackId, blob: new Blob([bytes]), length: bytes.length });
      }
    },

    get hasMedia() {
      return init !== null && chunks.length > 0;
    },

    finish(type = "video/mp4") {
      const ftypBox = readBoxes(init).find((b) => b.type === "ftyp");
      const ftyp = ftypBox ? init.slice(ftypBox.start, ftypBox.end) : new Uint8Array(0);
      // The tables have the same size whatever the offsets: build once to measure, then for real.
      const offsetsFrom = (dataStart) => {
        const perTrack = new Map();
        let position = dataStart;
        for (const c of chunks) {
          if (!perTrack.has(c.trackId)) perTrack.set(c.trackId, []);
          perTrack.get(c.trackId).push(position);
          position += c.length;
        }
        return (trackId) => perTrack.get(trackId) || [];
      };
      const headerLength = ftyp.length + buildMoov(init, tracks, offsetsFrom(0)).length + 16;
      const moov = buildMoov(init, tracks, offsetsFrom(headerLength));

      const payload = chunks.reduce((n, c) => n + c.length, 0);
      const mdatHeader = new Uint8Array(16);
      const v = view(mdatHeader);
      v.setUint32(0, 1); // 64-bit size follows
      mdatHeader.set([0x6d, 0x64, 0x61, 0x74], 4); // "mdat"
      v.setBigUint64(8, BigInt(16 + payload));
      return new Blob([ftyp, moov, mdatHeader, ...chunks.map((c) => c.blob)], { type });
    },
  };
}
