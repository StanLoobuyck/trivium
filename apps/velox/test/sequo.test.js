import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LINK_HASH,
  addToQueue,
  buildRecording,
  createEvent,
  sequoMatch,
  sequoPermission,
  isWatched,
  normalizeSequoUrl,
  parseLinkHash,
  verbatimFolder,
} from "../src/shared/sequo.js";

const hash = (value) => LINK_HASH + encodeURIComponent(value);
const meta = (id) => ({ id, occurredAt: "2026-11-01T12:00:00+01:00" });
const recording = { courseCode: "H01L6A", title: "Les 1" };
const progress = (id, positionSec, rec = recording) =>
  createEvent("recording.progress", rec, { positionSec }, meta(id));

test("the link address must be https, or http on this computer", () => {
  assert.equal(parseLinkHash(hash("https://a.ts.net/")), "https://a.ts.net/");
  assert.equal(parseLinkHash(hash("https://a.github.io/x/sequo")), "https://a.github.io/x/sequo/");
  assert.equal(parseLinkHash(hash("http://localhost:4173/sequo/")), "http://localhost:4173/sequo/");
  assert.equal(parseLinkHash(hash("http://a.ts.net/")), null);
  assert.equal(parseLinkHash(hash("https://user:pw@a.ts.net/")), null);
  assert.equal(parseLinkHash(hash("javascript:alert(1)")), null);
  assert.equal(parseLinkHash("#anders"), null);
  assert.equal(parseLinkHash(`${LINK_HASH}%E0%A4%A`), null);
  assert.equal(normalizeSequoUrl("geen adres"), null);
});

test("permission covers the host, the script only Sequo's own path", () => {
  const address = "https://a.github.io/x/sequo/";
  assert.equal(sequoPermission(address), "https://a.github.io/*");
  assert.equal(sequoMatch(address), "https://a.github.io/x/sequo/*");
  assert.equal(sequoMatch("http://localhost:4173/"), "http://localhost/*");
});

test("recording: date and number come from the Toledo title", () => {
  assert.deepEqual(
    buildRecording({ code: "H01L6A", lecture: "Les 12 (2026-09-23): intro", url: "https://t/x" }),
    {
      courseCode: "H01L6A",
      title: "Les 12 (2026-09-23): intro",
      recordedOn: "2026-09-23",
      lectureNumber: 12,
      url: "https://t/x",
    },
  );
  assert.deepEqual(buildRecording({ code: "H01L6A", lecture: "Gastcollege" }), {
    courseCode: "H01L6A",
    title: "Gastcollege",
  });
  assert.equal(buildRecording({ code: null, lecture: "Les 1" }), null);
  assert.equal(buildRecording({ code: "H01L6A", lecture: null }), null);
});

test("recording: without a Toledo title, the Kaltura name identifies it", () => {
  assert.deepEqual(buildRecording({ code: "H06F2A", lecture: "", recording: "DEP Les7, deel2" }), {
    courseCode: "H06F2A",
    title: "DEP Les7, deel2",
    lectureNumber: 7,
    part: 2,
  });
  assert.equal(buildRecording({ code: "H06F2A", lecture: "Les 1", recording: "x" }).title, "Les 1");
});

test("recording: part numbers come from the title", () => {
  const part = (lecture) => buildRecording({ code: "H01L6A", lecture }).part;
  assert.equal(part("DEP Les 6, part 3 - March 14th 2023"), 3);
  assert.equal(part("Les7, deel4 - March 16th 2023"), 4);
  assert.equal(part("Les 7"), undefined);
});

test("queue keeps one position per recording, and none after watched", () => {
  let queue = addToQueue([], progress("a", 60));
  queue = addToQueue(queue, progress("b", 120));
  queue = addToQueue(queue, progress("c", 30, { ...recording, title: "Les 2" }));
  assert.deepEqual(
    queue.map((e) => e.id),
    ["b", "c"],
  );
  const watched = createEvent("recording.watched", recording, { watchedFraction: 0.95 }, meta("d"));
  queue = addToQueue(queue, watched);
  assert.deepEqual(
    queue.map((e) => e.id),
    ["c", "d"],
  );
  assert.equal(addToQueue(queue, progress("e", 10)), queue);
  const download = createEvent("recording.downloaded", recording, { fileName: "a.mp4" }, meta("f"));
  assert.equal(addToQueue(queue, download).length, 3);
});

test("queue stays bounded", () => {
  let queue = [];
  for (let i = 0; i < 250; i++)
    queue = addToQueue(queue, progress(`${i}`, 60, { ...recording, title: `${i}` }));
  assert.equal(queue.length, 200);
  assert.equal(queue.at(-1).id, "249");
});

test("Verbatim folder only for a clean course code", () => {
  assert.equal(verbatimFolder("H06F2a"), "Verbatim/H06F2A");
  assert.equal(verbatimFolder("../x"), null);
  assert.equal(verbatimFolder(null), null);
});

test("watched from 90%", () => {
  assert.equal(isWatched(89, 100), false);
  assert.equal(isWatched(90, 100), true);
  assert.equal(isWatched(10, NaN), false);
  assert.equal(isWatched(10, 0), false);
});
