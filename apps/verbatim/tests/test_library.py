"""Library order: lesson and part from the title, cleaner titles for raw file names, order and groups."""

import json
import time

from lecture import library as lib

RAW = "ABC - Aula 1 2026-10-13 10 - 53"
EBS = [{"date": "2026-09-21", "number": 1}, {"date": "2026-10-08", "number": 5}, {"date": "2026-10-13", "number": 6}]


def test_parse_lesson():
    assert lib.parse_lesson("Les 11 deel 3") == (11, 3)
    assert lib.parse_lesson("Lecture 05") == (5, None)
    assert lib.parse_lesson("Les van 13 okt") == (None, None)
    assert lib.parse_lesson(RAW) == (None, None)


def test_raw_title_gets_the_number_from_the_timetable():
    assert lib.display_title(RAW, RAW, "2026-10-13", EBS) == "Les 6"
    assert lib.display_title(RAW, RAW, "2026-10-13", EBS, "en") == "Lecture 6"


def test_without_a_number_the_date():
    assert lib.display_title(RAW, RAW, "2026-10-13", []) == "Les van 13 okt"
    assert lib.display_title(RAW, RAW, "2026-10-13", [], "en") == "Lecture of 13 Oct"
    # two lectures that day: no guess
    two = EBS + [{"date": "2026-10-13", "number": 7}]
    assert lib.display_title(RAW, RAW, "2026-10-13", two) == "Les van 13 okt"


def test_own_titles_stay():
    assert lib.display_title("Les  2", "rzl les 2", "2026-10-20", EBS) == "Les 2"  # only spaces tidied
    assert lib.display_title("Opampschakelingen", RAW, "2026-10-13", EBS) == "Opampschakelingen"  # renamed by hand
    assert lib.display_title(RAW, None, "2026-10-13", EBS) == RAW  # no file name known


def lec(title, day, course="dep"):
    return {"id": title + day, "title": title, "date": day, "course": course}


def test_order_by_lesson_then_part_and_semester():
    xs = [lec("Les 3", "2026-10-20"), lec("Les 1", "2026-10-20"), lec("Les 2 deel 2", "2026-10-20"),
          lec("Les 2 deel 1", "2026-10-20"), lec("Les 5", "2026-10-19"), lec("Les 13", "2023-04-12"),
          lec("Les van 22 okt", "2026-10-22")]
    lib.arrange(xs)
    order = [x["title"] for x in sorted(xs, key=lambda x: x["rank"])]
    # an older semester first; a lecture without a number after the numbered one on or before its date
    assert order == ["Les 13", "Les 1", "Les 2 deel 1", "Les 2 deel 2", "Les 3", "Les 5", "Les van 22 okt"]


def test_groups_only_for_parts_of_the_same_lesson():
    xs = [lec("Les 11 deel 1", "2026-11-02"), lec("Les 11 deel 2", "2026-11-02"), lec("Les 4", "2026-02-26"),
          lec("Les 11 deel 1", "2023-04-12"), lec("Les 11 deel 1", "2026-11-02", "ebs")]
    lib.arrange(xs)
    g = [x["group"] for x in xs]
    assert g[0] == g[1] and g[2] is None
    assert len({g[0], g[3], g[4]}) == 3  # other semester, other course: other group


class C:
    def __init__(self, id, name, codes):
        self.id, self.name, self.codes = id, name, codes


def test_lessons_from_hub_match_code_then_name():
    courses = [C("ebs", "Een vak", ["H00X1A"]), C("rzl", "RZL", [])]
    entries = [{"name": "Vak", "codes": ["H00X1a"], "lectures": EBS}, {"name": "rzl", "codes": [], "lectures": EBS[:1]},
               {"name": "Onbekend", "codes": ["X"], "lectures": EBS}]
    assert lib.lessons_from_hub(entries, courses) == {"ebs": EBS, "rzl": EBS[:1]}


def test_cache_is_used_and_refreshed_in_the_background(tmp_path):
    cache = tmp_path / "hub_lessons.json"
    cache.write_text(json.dumps({"at": time.time(), "lessons": {"ebs": EBS}}))
    assert lib.cached_lessons(cache, lambda: 1 / 0) == {"ebs": EBS}  # fresh: no refresh
    cache.write_text(json.dumps({"at": 0, "lessons": {"ebs": EBS}}))
    assert lib.cached_lessons(cache, lambda: {"ebs": []}) == {"ebs": EBS}  # old answer now, new one later
    for _ in range(50):
        if json.loads(cache.read_text())["lessons"] == {"ebs": []}:
            break
        time.sleep(0.02)
    assert json.loads(cache.read_text())["lessons"] == {"ebs": []}
    cache.write_text(json.dumps({"at": 0, "lessons": {"ebs": EBS}}))
    assert lib.cached_lessons(cache, lambda: 1 / 0) == {"ebs": EBS}  # offline: keeps what it had
    time.sleep(0.1)
    assert json.loads(cache.read_text())["lessons"] == {"ebs": EBS}
