import { describe, expect, it } from "vitest";
import { findSession, planRecordings, recordingKey } from "./recordings.js";

const now = new Date("2026-11-01T12:00:00+01:00");
const courses = [{ id: "c1", name: "DSV", codes: ["H01L6a"] }, { id: "c2", name: "DEP", codes: ["H01Z1a"] }];
const session = (id, start, fields = {}) => ({
  id, courseId: "c1", type: "lecture", start, end: start.replace("T08", "T10"), status: "upcoming", recordings: [], deletedAt: null, ...fields,
});
const sessions = [
  session("a", "2026-09-23T08:00:00Z"),
  session("b", "2026-09-30T08:00:00Z"),
  session("x", "2026-09-30T23:30:00Z", { type: "exercise" }),
  session("c", "2026-10-07T08:00:00Z", { courseId: "c2" }),
];
const numbers = new Map([["a", 1], ["b", 2], ["c", 1]]);
const context = { courses, sessions, numbers, now };
const recording = (fields) => ({ courseCode: "H01L6A", title: "Les", ...fields });
const event = (type, rec, payload = {}, occurredAt = "2026-11-01T10:00:00+01:00") => ({
  id: crypto.randomUUID(), type, source: "swiftskip", occurredAt, payload: { recording: rec, ...payload },
});
const watched = (rec, at) => event("recording.watched", rec, { watchedFraction: 0.95 }, at);
const progress = (rec, positionSec, at) => event("recording.progress", rec, { positionSec }, at);

describe("findSession", () => {
  it("vindt het vak hoofdletterongevoelig en de les op datum", () => {
    expect(findSession(recording({ recordedOn: "2026-09-30" }), context).session.id).toBe("b");
  });

  it("rekent de datum in Brussel, niet in UTC", () => {
    expect(findSession(recording({ recordedOn: "2026-10-01" }), context).session.id).toBe("x");
  });

  it("valt terug op het lesnummer als de datum niet klopt", () => {
    const old = recording({ recordedOn: "2025-09-30", lectureNumber: 2 });
    expect(findSession(old, context).session.id).toBe("b");
  });

  it("laat de gebruiker kiezen als niets past", () => {
    const result = findSession(recording({ recordedOn: "2025-09-30", lectureNumber: 8 }), context);
    expect(result.course.id).toBe("c1");
    expect(result.session).toBeNull();
  });

  it("kent geen onbekend vak", () => {
    expect(findSession(recording({ courseCode: "H99" }), context).course).toBeNull();
  });

  it("onthoudt een eerdere koppeling", () => {
    const rec = recording({ title: "Oud", lectureNumber: 8 });
    const linked = sessions.map((s) => (s.id === "b" ? { ...s, recordings: [{ key: recordingKey(rec) }] } : s));
    expect(findSession(rec, { ...context, sessions: linked }).session.id).toBe("b");
  });

  it("geeft twee opnames van dezelfde dag elk hun eigen les", () => {
    const day = [session("p", "2026-09-23T08:00:00Z"), session("q", "2026-09-23T10:30:00Z")];
    const plan = planRecordings([
      watched(recording({ title: "Les 1", recordedOn: "2026-09-23" }), "2026-11-01T10:00:00+01:00"),
      watched(recording({ title: "Les 2", recordedOn: "2026-09-23" }), "2026-11-01T11:00:00+01:00"),
    ], { ...context, sessions: day, numbers: new Map() });
    expect(plan.ticked).toEqual(["p", "q"]);
  });

  it("brengt meerdere delen van dezelfde les bij die les", () => {
    const list = sessions.map((s) => (s.id === "b" ? { ...s, recordings: [{ key: "ander deel" }] } : s));
    expect(findSession(recording({ title: "Les 2, part 3", lectureNumber: 2 }), { ...context, sessions: list }).session.id).toBe("b");
  });

  it("slaat een geschrapte les over", () => {
    const list = [session("a", "2026-09-23T08:00:00Z", { status: "cancelled" })];
    expect(findSession(recording({ recordedOn: "2026-09-23" }), { ...context, sessions: list }).session).toBeNull();
  });
});

describe("planRecordings", () => {
  const rec = recording({ recordedOn: "2026-09-23", url: "https://t/1" });

  it("vinkt af vanaf recording.watched en bewaart de opname", () => {
    const plan = planRecordings([watched(rec)], context);
    expect(plan.ticked).toEqual(["a"]);
    expect(plan.changes.get("a").recordings[0]).toMatchObject({ key: recordingKey(rec), url: "https://t/1" });
  });

  it("bewaart de positie als halverwege", () => {
    expect(planRecordings([progress(rec, 2892)], context).changes.get("a")).toMatchObject({ status: "inProgress", progressSec: 2892 });
  });

  it("verandert een afgewerkte les niet", () => {
    const done = sessions.map((s) => (s.id === "a" ? { ...s, status: "attended" } : s));
    const plan = planRecordings([watched(rec), progress(rec, 60)], { ...context, sessions: done });
    expect(plan.ticked).toEqual([]);
    expect(plan.changes.get("a").status).toBeUndefined();
  });

  it("laat bekeken winnen van een latere positie in dezelfde reeks", () => {
    const plan = planRecordings([progress(rec, 60, "2026-11-01T12:00:00+01:00"), watched(rec, "2026-11-01T11:00:00+01:00")], context);
    expect(plan.ticked).toEqual(["a"]);
    expect(plan.changes.get("a").status).toBeUndefined();
  });

  it("bewaart de bestandsnaam", () => {
    const plan = planRecordings([event("recording.downloaded", rec, { fileName: "les.mp4" })], context);
    expect(plan.changes.get("a").recordings[0].fileName).toBe("les.mp4");
    expect(plan.ticked).toEqual([]);
  });

  it("behoudt een manueel geplakte link alleen als aanvulling", () => {
    const list = sessions.map((s) => (s.id === "a" ? { ...s, recordings: [{ url: "https://eigen" }] } : s));
    const noUrl = recording({ recordedOn: "2026-09-23" });
    expect(planRecordings([watched(noUrl)], { ...context, sessions: list }).changes.get("a").recordings).toEqual([
      { url: "https://eigen", key: recordingKey(noUrl), title: "Les" },
    ]);
  });

  it("legt een opname zonder les opzij, met per type het nieuwste bericht", () => {
    const old = recording({ recordedOn: "2025-09-30", lectureNumber: 8 });
    const first = planRecordings([progress(old, 60)], context);
    const second = planRecordings([progress(old, 90), watched(old)], { ...context, unmatched: first.unmatched });
    expect(second.unmatched).toHaveLength(1);
    expect(second.unmatched[0].events.map((e) => e.type).sort()).toEqual(["recording.progress", "recording.watched"]);
    expect(second.changes.size).toBe(0);
  });

  it("past een opzijgelegde opname toe op de gekozen les", () => {
    const old = recording({ recordedOn: "2025-09-30", lectureNumber: 8 });
    const plan = planRecordings([watched(old)], { ...context, forced: { [recordingKey(old)]: "b" } });
    expect(plan.ticked).toEqual(["b"]);
    expect(plan.unmatched).toEqual([]);
  });

  it("negeert een onbekend vak", () => {
    const plan = planRecordings([watched(recording({ courseCode: "H99" }))], context);
    expect(plan.ticked).toEqual([]);
    expect(plan.unmatched).toEqual([]);
  });
});
