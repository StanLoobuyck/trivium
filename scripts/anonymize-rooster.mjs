// Maakt fixtures/rooster-anon.ics uit het echte rooster: docenten, lokalen en id's verdwijnen, de structuur blijft.
import { readFileSync, writeFileSync } from "node:fs";

const unfolded = readFileSync("fixtures/private/rooster.ics", "utf8").replace(/\r\n[ \t]/g, "");
const lecturers = new Map();
const lecturer = (name) => {
  if (!lecturers.has(name)) lecturers.set(name, `Docent ${String.fromCharCode(65 + lecturers.size)}`);
  return lecturers.get(name);
};

let uid = 1000;
const output = unfolded.split("\r\n").filter((line) => !/^(X-WR-|X-PUBLISHED)/.test(line)).map((line) => {
  if (line.startsWith("UID:")) return `UID:${uid++}-1-0@timeedit.example`;
  if (line.startsWith("LOCATION:")) return line.includes("Online") ? "LOCATION:Online ONL.00.0001" : "LOCATION:Lokaal";
  if (line.startsWith("DESCRIPTION:")) return `${line.split("\\n")[0]}`;
  if (!line.startsWith("SUMMARY:")) return line;
  const colon = line.indexOf(": ");
  const parts = line.split("\\, ");
  const named = (part) => /^\p{Lu}\p{L}+ (\p{Lu}|van |de )/u.test(part) && !/^(Religie|Technische)/.test(part);
  if (colon > 0) {
    const head = line.slice(0, colon + 2);
    return head + line.slice(colon + 2).split("\\, ").map((p) => (named(p) ? lecturer(p) : p)).join("\\, ");
  }
  return parts.map((p, i) => (i > 0 && named(p) ? lecturer(p) : p)).join("\\, ");
});
writeFileSync("fixtures/rooster-anon.ics", output.join("\r\n"));
console.log(`${uid - 1000} sessies, ${lecturers.size} docenten vervangen`);
