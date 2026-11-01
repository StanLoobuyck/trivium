import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { proposeCourses, proposeMerges } from "./courses.js";
import { currentCluster, missingWeeks, parseRooster, parseSummary, proposeSemester, splitSemesters } from "./rooster.js";

describe("parseSummary", () => {
  it("leest code, naam, type en docent", () => {
    expect(parseSummary("H01L1a Digitale elektronica en processoren: hoorcollege, Marian Verhelst, Online", "01 College \nH01L1a"))
      .toMatchObject({ code: "H01L1a", name: "Digitale elektronica en processoren", type: "lecture", lecturers: ["Marian Verhelst"] });
  });

  it("houdt komma's in de naam als er geen type staat", () => {
    expect(parseSummary("A08C4a Religie, zingeving en levensbeschouwing, Pierre Van Hecke, 3Bbi", "01 College \nA08C4a_3Bbi"))
      .toMatchObject({ name: "Religie, zingeving en levensbeschouwing", lecturers: ["Pierre Van Hecke"], type: "lecture" });
  });

  it("houdt komma's in de naam als er wel een type staat", () => {
    expect(parseSummary("H0R38a Elektronische signalen, schakelingen en systemen: oefeningen, geen docent, 3Belt/B2", "02 Practicum"))
      .toMatchObject({ name: "Elektronische signalen, schakelingen en systemen", type: "exercise", lecturers: [] });
  });

  it("herkent meerdere docenten en groepen", () => {
    expect(parseSummary("H01L7a Digitale signaalverwerking: oefeningen, Jan Jansen, An Peeters, 3Bbmt/B1, 3Belt/B2", "02 Practicum").lecturers)
      .toEqual(["Jan Jansen", "An Peeters"]);
  });

  it.each([
    ["H01N4a Energieconversie: practica, geen docent, 3Belt/B2", "02 Practicum", "lab"],
    ["H06F3a Semiconductor Physics: Exercises and Laboratory Sessions, Bart Sorée, 3Belt/B2", "02 Practicum", "exercise"],
    ["H06F2a Semiconductor Physics: Lecture, Bart Sorée", "01 College", "lecture"],
    ["H01Q6a P&O: elektrotechniek, geen docent", "02 Practicum", "project"],
    ["H01X1a Iets: bezoek, geen docent", "07 Excursie", "excursion"],
  ])("%s", (summary, description, type) => {
    expect(parseSummary(summary, description).type).toBe(type);
  });
});

const anon = readFileSync(new URL("../../../../fixtures/rooster-anon.ics", import.meta.url), "utf8");

describe("geanonimiseerd rooster", () => {
  const events = parseRooster(anon);

  it("leest alle sessies en zet tijden om", () => {
    expect(events).toHaveLength(193);
    expect(new Date(events[0].start).toISOString()).toBe("2026-10-12T08:35:00.000Z");
  });

  it("vindt twee semesters", () => {
    const clusters = splitSemesters(events);
    expect(clusters).toHaveLength(2);
    expect(currentCluster(clusters, new Date("2026-11-01"))).toBe(clusters[0]);
    expect(currentCluster(clusters, new Date("2027-01-15"))).toBe(clusters[1]);
  });

  it("stelt de juiste vakken voor en zet P&O uit", () => {
    const first = splitSemesters(events)[0];
    const courses = proposeCourses(first);
    const po = courses.find((c) => c.name.startsWith("P&O"));
    expect(po.hidden).toBe(true);
    expect(courses.filter((c) => c.hidden)).toHaveLength(1);
    const ebs = courses.find((c) => c.name === "Elektronische basisschakelingen");
    expect(ebs.codes).toEqual(["H01M4a", "H01M3a"]);
    expect(ebs.minutesPerLecture).toBe(115);
  });

  it("stelt voor om EBS+ met EBS samen te voegen", () => {
    const first = splitSemesters(events)[0];
    expect(proposeMerges(proposeCourses(first), first)).toContainEqual([
      "Elektronische basisschakelingen",
      "Elektronische signalen, schakelingen en systemen",
    ]);
  });

  it("waarschuwt voor ontbrekende weken", () => {
    const first = splitSemesters(events)[0];
    const semester = proposeSemester(first);
    expect(semester.startDate).toBe("2026-09-21");
    expect(missingWeeks(semester.startDate, first)).toBe(3);
  });
});

const privateFile = new URL("../../../../fixtures/private/rooster.ics", import.meta.url);
describe.runIf(existsSync(privateFile))("echt rooster", () => {
  it("heeft geen sessies zonder code of naam", () => {
    const events = parseRooster(readFileSync(privateFile, "utf8"));
    expect(events).toHaveLength(193);
    expect(events.filter((e) => !e.code || !e.name)).toEqual([]);
  });
});
