"""Fetch and parse the official SC-500 study guide from Microsoft Learn.

The live guide is the source of truth. If it cannot be reached or parsed,
the app falls back to a dated local snapshot, and only when the user agrees
to an unverified practice set.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

GUIDE_URL = "https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-500"
SNAPSHOT = Path(__file__).parent / "guide_snapshot.json"
PCT = re.compile(r"\((\d+)\s*[–—-]\s*(\d+)\s*%\)")
HEADINGS = ["h1", "h2", "h3", "h4", "h5"]


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_guide(html: str) -> list[dict]:
    """Return [{name, low, high, sections:[{name, objectives:[...]}]}]."""
    soup = BeautifulSoup(html, "html.parser")
    areas: list[dict] = []
    area = None
    area_level = 0
    section = None
    for el in soup.find_all(HEADINGS + ["ul"]):
        if el.name in HEADINGS:
            level = int(el.name[1])
            text = _clean(el.get_text(" "))
            m = PCT.search(text)
            if m:
                area = {"name": _clean(PCT.sub("", text)), "low": int(m.group(1)),
                        "high": int(m.group(2)), "sections": []}
                areas.append(area)
                area_level, section = level, None
            elif area is not None and level > area_level:
                section = {"name": text, "objectives": []}
                area["sections"].append(section)
            elif area is not None:
                area, section = None, None  # left the skills list
        elif area is not None and el.find_parent("li") is None:
            if section is None:
                section = {"name": "General", "objectives": []}
                area["sections"].append(section)
            for li in el.find_all("li", recursive=False):
                text = _clean(li.get_text(" "))
                if text:
                    section["objectives"].append(text)
    for a in areas:
        a["sections"] = [s for s in a["sections"] if s["objectives"]]
    return [a for a in areas if a["sections"]]


def _valid(areas: list[dict]) -> bool:
    if len(areas) < 3:
        return False
    return all(sum(len(s["objectives"]) for s in a["sections"]) >= 3 for a in areas)


def load_snapshot() -> dict:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return {"verified": False, "source": "local snapshot", "url": GUIDE_URL,
            "checked_at": data["snapshot_date"], "areas": data["areas"], "error": None}


def load_guide(timeout: float = 15.0) -> dict:
    """Try the live guide. On any failure return the snapshot with verified=False."""
    try:
        r = httpx.get(GUIDE_URL, timeout=timeout, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (sc500-practice-sim; local study tool)"})
        r.raise_for_status()
        areas = parse_guide(r.text)
        if not _valid(areas):
            raise ValueError("The page loaded but the skills list could not be read.")
        return {"verified": True, "source": "Microsoft Learn (live)", "url": GUIDE_URL,
                "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "areas": areas, "error": None}
    except Exception as exc:  # network, HTTP or parse failure
        snap = load_snapshot()
        snap["error"] = f"{type(exc).__name__}: {exc}"
        return snap
