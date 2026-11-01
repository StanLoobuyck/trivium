import { describe, expect, it } from "vitest";
import { matchCourse, parseNotes, planNotesImport, toNotes } from "./notes.js";

const NOTES = `Hoorcolleges
Elektrische Basisschakelingen:
- [ ] 29/09
- [x] 02/10

Digitale signaalverwerking:
- [ ] 30/09

Oefenzittingen
Elektrische Basischakelingen:
- [ ] 05/10

Sterrenkunde:
- [ ] 01/10
`;

const courses = [
  { id: "ebs", name: "Elektronische basisschakelingen", shortName: "EB", minutesPerLecture: 115, minutesPerExercise: 145 },
  { id: "dsv", name: "Digitale signaalverwerking", shortName: "DS", minutesPerLecture: 115, minutesPerExercise: 145 },
];
const session = (id, courseId, type, start) => ({ id, courseId, type, start, end: start, status: "upcoming" });
const semester = { startDate: "2026-09-21" };

describe("Notes-import", () => {
  it("leest koppen, vakken en vinkjes", () => {
    const items = parseNotes(NOTES);
    expect(items).toHaveLength(5);
    expect(items[1]).toMatchObject({ type: "lecture", day: 2, month: 10, checked: true });
    expect(items[3]).toMatchObject({ type: "exercise" });
  });

  it("vangt tikfouten in vaknamen op", () => {
    expect(matchCourse("Elektrische Basischakelingen", courses).id).toBe("ebs");
    expect(matchCourse("Sterrenkunde", courses)).toBeNull();
  });

  it("koppelt aan bestaande lessen zonder dubbels", () => {
    const sessions = [
      session("a", "ebs", "lecture", "2026-09-29T08:35:00.000Z"),
      session("b", "ebs", "lecture", "2026-10-02T12:00:00.000Z"),
      session("c", "ebs", "exercise", "2026-10-05T08:35:00.000Z"),
    ];
    const plan = planNotesImport(parseNotes(NOTES), courses, sessions, semester);
    expect(plan.link).toEqual([{ id: "a", checked: false }, { id: "b", checked: true }, { id: "c", checked: false }]);
    expect(plan.create).toHaveLength(1);
    expect(plan.create[0]).toMatchObject({ courseId: "dsv", type: "lecture" });
    expect(plan.unknown).toEqual(["Sterrenkunde"]);
  });

  it("zet een datum in januari in het volgende jaar", () => {
    const plan = planNotesImport(parseNotes("Hoorcolleges\nDigitale signaalverwerking:\n- [ ] 05/01"), courses, [], semester);
    expect(new Date(plan.create[0].start).getFullYear()).toBe(2027);
  });
});

describe("Notes-export", () => {
  it("schrijft hetzelfde formaat", () => {
    const now = new Date("2026-10-20T12:00:00Z");
    const text = toNotes(courses, [
      { ...session("a", "ebs", "lecture", "2026-09-29T08:35:00.000Z"), end: "2026-09-29T10:30:00.000Z" },
      { ...session("b", "ebs", "lecture", "2026-10-02T12:00:00.000Z"), end: "2026-10-02T14:00:00.000Z", status: "watched" },
      { ...session("c", "ebs", "lecture", "2026-11-02T12:00:00.000Z"), end: "2026-11-02T14:00:00.000Z" },
    ], now);
    expect(text).toBe("Hoorcolleges\nElektronische basisschakelingen:\n- [ ] 29/09\n- [x] 02/10");
    expect(parseNotes(text)).toHaveLength(2);
  });
});
