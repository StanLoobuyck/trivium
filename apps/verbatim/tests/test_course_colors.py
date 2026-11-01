from lecture import hub
from lecture.config import Course


def course(id, name, codes=()):
    return Course(id=id, name=name, codes=list(codes), language="nl", notes_language="nl")


def test_colours_follow_code_then_name(monkeypatch):
    monkeypatch.setattr(hub, "fetch_courses", lambda conf: [
        {"name": "Andere naam", "codes": ["h01"], "colorKey": "pink"},
        {"name": "P&O", "codes": [], "colorKey": "yellow"},
        {"name": "Onbekend", "codes": ["X"], "colorKey": "red"},
        {"name": "Oude hub", "codes": ["H02"]},
    ])
    courses = [course("a", "Digitale elektronica", ["H01"]), course("b", "p&o"), course("c", "Zonder", ["H02"])]
    assert hub.course_colors(None, courses) == {"a": "pink", "b": "yellow"}
