import assert from "node:assert/strict";
import { test } from "node:test";
import {
  courseCodeFrom,
  isSlideUrl,
  slideContentId,
  slideFilename,
  slideType,
} from "../src/shared/slides.js";

test("slideType reads the row label, then the title", () => {
  assert.equal(slideType("PDF, Slides Hoofdstuk 2", "Slides Hoofdstuk 2"), "pdf");
  assert.equal(slideType("PowerPoint, Les 3", "Les 3"), "pptx");
  assert.equal(slideType("Microsoft PowerPoint, Les 3", "Les 3"), "pptx");
  assert.equal(slideType("Bestand, Les 3.PPTX", "Les 3.PPTX"), "pptx");
  assert.equal(slideType("Map, Lesopnames", "Lesopnames"), null);
  assert.equal(slideType("Discussie, Hoofdstukken 1-5", "Hoofdstukken 1-5"), null);
  assert.equal(slideType("Word, Opgave", "Opgave.docx"), null);
});

test("slideFilename never doubles the extension and stays a safe name", () => {
  assert.equal(slideFilename("Slides Hoofdstuk 2", "pdf"), "Slides Hoofdstuk 2.pdf");
  assert.equal(slideFilename("Les 3.PDF", "pdf"), "Les 3.pdf");
  assert.equal(slideFilename("a/b: c", "pptx"), "a_b - c.pptx");
});

test("slideContentId takes the id from the row link", () => {
  assert.equal(slideContentId("https://x/ultra/courses/_1_1/file/_12_1?courseId=_1_1"), "_12_1");
  assert.equal(slideContentId("https://x/ultra/courses/_1_1/outline"), null);
});

test("courseCodeFrom finds the code in the headings", () => {
  assert.equal(courseCodeFrom(["Inhoud", "Digitale signaalverwerking [H01L6a]"]), "H01L6a");
  assert.equal(courseCodeFrom(["Inhoud"]), null);
});

test("isSlideUrl only allows Toledo's file store on the same site", () => {
  const page = "https://toledo.example/ultra/courses/_1_1/outline";
  assert.equal(isSlideUrl("https://toledo.example/bbcswebdav/pid-1/xid-1", page), true);
  assert.equal(isSlideUrl("https://other.example/bbcswebdav/pid-1/xid-1", page), false);
  assert.equal(isSlideUrl("https://toledo.example/learn/api/secret", page), false);
  assert.equal(isSlideUrl("not a url", page), false);
});
