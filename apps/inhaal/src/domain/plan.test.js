import { describe, expect, it } from "vitest";
import { backlogByWeek, catchUpPlan } from "./plan.js";

const now = new Date("2026-11-02T12:00:00");

describe("inhaalplan", () => {
  it("verdeelt de tijd over de resterende weken", () => {
    const plan = catchUpPlan({ minutes: 4920, examStart: "2027-01-04", now });
    expect(plan.weeks).toBe(9);
    expect(plan.perWeekMinutes).toBeCloseTo(546.67, 1);
  });

  it("rekent met de afspeelsnelheid", () => {
    const plan = catchUpPlan({ minutes: 600, examStart: "2026-11-30", speed: 2, now });
    expect(plan.watchMinutes).toBe(300);
    expect(plan.perWeekMinutes).toBe(75);
  });

  it("telt een begonnen week als een hele", () => {
    expect(catchUpPlan({ minutes: 60, examStart: "2026-11-04", now }).weeks).toBe(1);
  });

  it("geeft geen tempo als de examens begonnen zijn", () => {
    expect(catchUpPlan({ minutes: 60, examStart: "2026-11-01", now })).toEqual({ watchMinutes: 60, weeks: 0, perWeekMinutes: null });
  });
});

describe("achterstand per week", () => {
  const session = (start, status = "upcoming") => ({ start, end: start, status });

  it("telt open lessen per lesweek en houdt lege weken", () => {
    const weeks = backlogByWeek([
      session("2026-10-05T10:00:00"), session("2026-10-11T10:00:00"), session("2026-10-20T10:00:00"),
      session("2026-10-21T10:00:00", "watched"),
    ], "2026-10-05", now);
    expect(weeks.map((w) => w.open)).toEqual([2, 0, 1, 0, 0]);
  });

  it("negeert lessen die nog moeten komen", () => {
    const weeks = backlogByWeek([session("2026-11-03T10:00:00")], "2026-11-02", now);
    expect(weeks.map((w) => w.open)).toEqual([0]);
  });
});
