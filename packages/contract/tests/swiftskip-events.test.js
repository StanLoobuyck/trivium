import { readFileSync } from "node:fs";
import Ajv from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";
import { buildRecording, createEvent } from "../../../apps/swiftskip/src/shared/inhaal.js";

const ajv = new Ajv({ allErrors: true });
addFormats(ajv);
const validate = ajv.compile(JSON.parse(readFileSync("packages/contract/schema/event.schema.json", "utf8")));
const meta = { id: "7f3c2a10-5b1e-4c7d-9a54-1f2e3d4c5b6a", occurredAt: "2026-11-01T12:00:00+01:00" };
const recording = buildRecording({ code: "H01L6A", lecture: "Les 1 (2026-09-23): intro", url: "https://toledo.kuleuven.be/x" });

describe("events van SwiftSkip volgen het contract", () => {
  it.each([
    ["recording.watched", { watchedFraction: 0.93 }],
    ["recording.progress", { positionSec: 2892 }],
    ["recording.downloaded", { fileName: "les.mp4" }],
  ])("%s", (type, payload) => {
    const event = createEvent(type, recording, payload, meta);
    expect(validate(event), JSON.stringify(validate.errors)).toBe(true);
  });
});
