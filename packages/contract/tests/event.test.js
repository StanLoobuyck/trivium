import { readFileSync } from "node:fs";
import Ajv from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

const schema = JSON.parse(readFileSync(new URL("../schema/event.schema.json", import.meta.url)));
const ajv = new Ajv({ allErrors: true });
addFormats(ajv);
const validate = ajv.compile(schema);

const event = (type, payload, source = "velox") => ({
  id: "3f2b7c1e-8a44-4f0e-9d1a-2b6c5e7f9a10",
  type,
  source,
  occurredAt: "2026-10-13T14:02:00+02:00",
  payload: { recording: { courseCode: "H01L1A", recordedOn: "2026-10-13" }, ...payload },
});

describe("events", () => {
  it.each([
    ["recording.watched", { watchedFraction: 0.93 }],
    ["recording.progress", { positionSec: 2892 }],
    ["recording.downloaded", { fileName: "les-4.mp4" }],
  ])("%s is geldig", (type, payload) => {
    expect(validate(event(type, payload))).toBe(true);
  });

  it("notes.ready is geldig", () => {
    expect(validate(event("notes.ready", { kind: "notes", verbatimJob: "job-1" }, "verbatim"))).toBe(true);
  });

  it.each([
    ["onbekend type", event("recording.deleted", {})],
    ["bekeken onder 90%", event("recording.watched", { watchedFraction: 0.5 })],
    ["positie ontbreekt", event("recording.progress", {})],
    ["vakcode ontbreekt", { ...event("recording.progress", { positionSec: 1 }), payload: { recording: {}, positionSec: 1 } }],
  ])("%s wordt geweigerd", (_, value) => {
    expect(validate(value)).toBe(false);
  });

  it("laat nieuwe velden toe", () => {
    expect(validate(event("recording.progress", { positionSec: 1, playbackRate: 1.5 }))).toBe(true);
  });
});
