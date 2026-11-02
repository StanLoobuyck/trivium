import { describe, expect, it } from "vitest";
import { computeNumbers, effectiveStatus, needsBackupReminder, summarize } from "./sessions.js";
import { mergeRooster } from "./merge.js";
import { readBackup, toBackup } from "./backup.js";

const course = { id: "c", name: "Vak", order: 0, minutesPerLecture: 120, minutesPerExercise: 150, hidden: false };
const session = (id, day, extra = {}) => ({
  id, courseId: "c", type: "lecture", status: "upcoming", source: "rooster",
  start: `2026-10-${day}T08:00:00.000Z`, end: `2026-10-${day}T10:00:00.000Z`, ...extra,
});
const now = new Date("2026-10-20T12:00:00Z");

describe("status", () => {
  it("wordt gemist zodra de les voorbij is", () => {
    expect(effectiveStatus(session("a", "19"), now)).toBe("missed");
    expect(effectiveStatus(session("a", "20"), new Date("2026-10-20T09:59:00Z"))).toBe("upcoming");
    expect(effectiveStatus(session("a", "20"), new Date("2026-10-20T10:00:00Z"))).toBe("missed");
  });
});

describe("nummering", () => {
  it("telt per type en slaat geschrapte lessen over", () => {
    const numbers = computeNumbers([
      session("a", "12"), session("b", "13", { status: "cancelled" }), session("c", "14"),
      session("d", "15", { type: "exercise" }),
    ]);
    expect(numbers.get("a")).toBe(1);
    expect(numbers.has("b")).toBe(false);
    expect(numbers.get("c")).toBe(2);
    expect(numbers.get("d")).toBe(1);
  });

  it("negeert verwijderde lessen", () => {
    const numbers = computeNumbers([session("a", "12", { deletedAt: "x" }), session("b", "13")]);
    expect(numbers.get("b")).toBe(1);
  });
});

describe("samenvatting", () => {
  it("telt open lessen, minuten en de volgende", () => {
    const result = summarize([course], [
      session("a", "12"), session("b", "13", { status: "watched" }), session("c", "14", { status: "cancelled" }),
      session("d", "15", { type: "exercise" }), session("e", "28"), session("f", "16", { status: "inProgress", progressSec: 1800 }),
    ], now);
    expect(result.open).toBe(3);
    expect(result.minutes).toBe(120 + 150 + 90);
    expect(result.next.id).toBe("a");
    expect(result.progress).toBeCloseTo(0.25);
    expect(result.perCourse[0]).toMatchObject({ lecture: 2, exercise: 1 });
  });

  it("negeert verborgen vakken", () => {
    expect(summarize([{ ...course, hidden: true }], [session("a", "12")], now).open).toBe(0);
  });

  it("zet vakken op alfabet, ook zonder open lessen", () => {
    const first = { ...course, id: "a", name: "algebra", order: 2 };
    const last = { ...course, id: "z", name: "Zonnepanelen", order: 0 };
    const result = summarize([last, first], [session("x", "12", { courseId: "z" })], now);
    expect(result.perCourse.map((p) => p.course.id)).toEqual(["a", "z"]);
  });
});

describe("rooster samenvoegen", () => {
  const event = (uid, day, extra = {}) => ({ uid, start: `2026-10-${day}T08:00:00.000Z`, end: `2026-10-${day}T10:00:00.000Z`, location: "", ...extra });

  it("maakt geen dubbels en bewaart status", () => {
    const { add, update } = mergeRooster([session("a", "12", { status: "watched", location: "" })], [event("a", "12"), event("b", "13")]);
    expect(add.map((e) => e.uid)).toEqual(["b"]);
    expect(update).toEqual([]);
  });

  it("volgt een verplaatste les", () => {
    const { update } = mergeRooster([session("a", "12", { location: "" })], [event("a", "14")]);
    expect(update).toHaveLength(1);
    expect(update[0].start).toContain("10-14");
  });

  it("stelt voor te schrappen wat binnen de periode verdween", () => {
    const { vanished } = mergeRooster([session("b", "13", { location: "" })], [event("a", "12"), event("c", "14")]);
    expect(vanished.map((s) => s.id)).toEqual(["b"]);
  });

  it("raakt lessen buiten de periode van het bestand niet aan", () => {
    const { vanished } = mergeRooster([session("old", "01", { location: "" })], [event("a", "12")]);
    expect(vanished).toEqual([]);
  });
});

describe("back-up", () => {
  it("gaat heen en terug", () => {
    const data = { semesters: [{ id: "s" }], courses: [course], sessions: [session("a", "12")] };
    expect(readBackup(JSON.stringify(toBackup(data, now)))).toEqual(data);
  });

  it.each(["niet json", "{}", '{"app":"inhaal","version":99}'])("weigert %s", (text) => {
    expect(() => readBackup(text)).toThrow();
  });

  it("herinnert maandelijks", () => {
    const start = "2026-09-25T00:00:00Z";
    expect(needsBackupReminder(null, start, new Date("2026-10-10"))).toBe(false);
    expect(needsBackupReminder(null, start, new Date("2026-10-26"))).toBe(true);
    expect(needsBackupReminder("2026-10-25T00:00:00Z", start, new Date("2026-10-26"))).toBe(false);
  });
});
