"""SC-500 practice exam simulator. Local web app.

Run:  python app.py     then open http://127.0.0.1:8500
"""
import json
import os
import random
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

BASE = Path(__file__).parent


def _load_env():
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import agent  # noqa: E402
import docs  # noqa: E402
import guide as guide_mod  # noqa: E402

PASS_MARK = 700
MODES = {"full": 50, "quick": 12, "case": 6, "practice": 10}
# Hosted settings (Azure App Service). All are off on your own machine.
ON = ("1", "true", "yes")
HOSTED = os.environ.get("SC500_HOSTED", "").lower() in ON
REQUIRE_AUTH = os.environ.get("SC500_REQUIRE_AUTH", "").lower() in ON
ALLOWED_USERS = [u.strip().lower() for u in os.environ.get("SC500_ALLOWED_USERS", "").split(",") if u.strip()]
DATA = Path(os.environ.get("SC500_DATA_DIR") or BASE)  # where saved exams and the question bank live
SESSIONS = DATA / "sessions"
SESSIONS.mkdir(parents=True, exist_ok=True)
docs.init(DATA)
LOCK = threading.Lock()
EXAMS: dict[str, dict] = {}

app = FastAPI(title="SC-500 Practice Exam Simulator")


@app.middleware("http")
async def signed_in_only(request: Request, call_next):
    """When hosted, serve only users that App Service Authentication has signed in.

    App Service Authentication is the real gate. This is a second check: it blocks the app
    if sign-in was never set up, and it limits access to the names in SC500_ALLOWED_USERS.
    """
    if REQUIRE_AUTH:
        user = request.headers.get("x-ms-client-principal-name", "").strip()
        if not user:
            return PlainTextResponse("Sign-in is not set up. In the Azure portal, open this web app, then "
                                     "Authentication, and add Microsoft as the identity provider.", status_code=401)
        if ALLOWED_USERS and user.lower() not in ALLOWED_USERS:
            return PlainTextResponse(f"You are signed in as {user}. That account is not on the allowed list "
                                     "(app setting SC500_ALLOWED_USERS).", status_code=403)
    return await call_next(request)


# ---------- storage ----------

def _save(exam: dict):
    (SESSIONS / f"{exam['id']}.json").write_text(json.dumps(exam), encoding="utf-8")


def _get(exam_id: str) -> dict:
    with LOCK:
        if exam_id in EXAMS:
            return EXAMS[exam_id]
        path = SESSIONS / f"{exam_id}.json"
        if exam_id.isalnum() and path.exists():
            EXAMS[exam_id] = json.loads(path.read_text(encoding="utf-8"))
            return EXAMS[exam_id]
    raise HTTPException(404, "Exam not found.")


def _question(exam: dict, qid: int) -> dict:
    for q in exam["questions"]:
        if q["id"] == qid:
            return q
    raise HTTPException(404, "Question not found.")


# ---------- question bank (saved questions, reused at no token cost) ----------

BANK = DATA / "bank.json"
KEEP = ("area", "section", "objective", "doc_query", "type", "stem", "options", "correct", "required", "explanation")


def _bank() -> dict:
    # When hosted, start from the bank.json that was deployed with the code, if there is one.
    for path in (BANK, BASE / "bank.json"):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return {"questions": [], "cases": []}


def _bank_add(case, questions: list[dict]):
    """Save freshly written questions so later exams can reuse them."""
    with LOCK:
        bank = _bank()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        items = [{**{k: q.get(k) for k in KEEP}, "model": agent.MODEL, "added": stamp} for q in questions]
        if case:
            bank["cases"].append({"case": case, "questions": items, "model": agent.MODEL, "added": stamp})
        else:
            seen = {q["stem"] for q in bank["questions"]}
            bank["questions"] += [q for q in items if q["stem"] not in seen]
        BANK.write_text(json.dumps(bank), encoding="utf-8")


def _reshuffle(q: dict) -> dict:
    """Copy a saved question with its options in a new order, so you cannot learn positions."""
    q = {k: q.get(k) for k in KEEP}
    if q["type"] == "solution":
        return q
    old = q["options"]
    order = list(range(len(old)))
    random.shuffle(order)
    labels = [o["label"] for o in old]
    move = {old[src]["label"]: labels[pos] for pos, src in enumerate(order)}
    q["options"] = [{"label": labels[pos], "text": old[src]["text"]} for pos, src in enumerate(order)]
    q["correct"] = [move[x] for x in q["correct"]] if q["type"] == "ordering" else sorted(move[x] for x in q["correct"])
    return q


def _from_bank(mode: str, areas: list[dict], total: int):
    bank = _bank()
    valid = {(a["name"], s["name"], o) for a in areas for s in a["sections"] for o in s["objectives"]}
    if mode == "case":
        cases = [c for c in bank["cases"] if all((q["area"], q["section"], q["objective"]) in valid for q in c["questions"])]
        if not cases:
            raise HTTPException(400, "No saved case study yet. Write a new one first.")
        pick = random.choice(cases)
        return pick["case"], [_reshuffle(q) for q in pick["questions"]]
    pool = [q for q in bank["questions"] if (q["area"], q["section"], q["objective"]) in valid]
    if len(pool) < total:
        raise HTTPException(400, f"Only {len(pool)} saved questions fit this choice and it needs {total}. Write new questions first.")
    random.shuffle(pool)
    chosen, rest = [], []
    for area, want in zip(areas, agent.allocate(total, areas)):   # keep the study guide weighting
        mine = [q for q in pool if q["area"] == area["name"]]
        chosen += mine[:want]
        rest += mine[want:]
    random.shuffle(rest)
    chosen += rest[: total - len(chosen)]
    random.shuffle(chosen)
    return None, [_reshuffle(q) for q in chosen]


def _bank_stats() -> dict:
    bank = _bank()
    by_section: dict[str, int] = {}
    for q in bank["questions"]:
        by_section[q["section"]] = by_section.get(q["section"], 0) + 1
    return {"questions": len(bank["questions"]), "cases": len(bank["cases"]), "by_section": by_section}


# ---------- views ----------

def _status(exam: dict) -> dict:
    qs = exam["questions"]
    answered = sum(1 for q in qs if q["answer"])
    return {"total": len(qs), "answered": answered, "unanswered": len(qs) - answered,
            "flagged": sum(1 for q in qs if q["flagged"]),
            "changed": sum(1 for q in qs if q["changes"] > 0),
            "remaining": len(qs) - answered}


def _doc(q: dict) -> dict:
    """The Microsoft Learn page for this question's topic. Falls back to a Learn search link."""
    return docs.resolve(q.get("doc_query") or q["objective"])


def _feedback(q: dict) -> dict:
    return {"correct": q["correct"], "is_correct": _is_correct(q), "explanation": q["explanation"],
            "area": q["area"], "section": q["section"], "objective": q["objective"], "doc": _doc(q)}


def _public(exam: dict) -> dict:
    """Exam state with no answer key, explanation or objective. Safe to send mid-exam."""
    return {
        "id": exam["id"], "mode": exam["mode"], "submitted": exam["submitted"],
        "verified": exam["verified"], "guide_checked_at": exam["guide_checked_at"],
        "mock": exam.get("mock", False), "case": exam.get("case"), "status": _status(exam),
        "section": exam.get("section"), "source": exam.get("source", "new"), "model": exam.get("model"),
        "questions": [{"id": q["id"], "type": q["type"], "stem": q["stem"], "options": q["options"],
                       "required": q["required"], "answer": q["answer"], "flagged": q["flagged"],
                       # Practice Mode only: feedback for questions the user has already checked.
                       "feedback": _feedback(q) if q.get("checked") else None}
                      for q in exam["questions"]],
        "guide_url": guide_mod.GUIDE_URL,
    }


def _is_correct(q: dict) -> bool:
    if not q["answer"]:
        return False
    if q["type"] == "ordering":
        return q["answer"] == q["correct"]
    return sorted(q["answer"]) == sorted(q["correct"])  # all selections needed, no partial credit


def _results(exam: dict) -> dict:
    qs = exam["questions"]
    total = len(qs)
    right = sum(1 for q in qs if _is_correct(q))
    score = round(1000 * right / total)
    areas: dict[str, dict] = {}
    for name in exam["area_names"]:
        areas[name] = {"area": name, "correct": 0, "total": 0}
    missed: dict[tuple, dict] = {}
    # Look up the Learn pages for every question at once, so the review page loads fast.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_doc, qs))
    review = []
    for q in qs:
        ok = _is_correct(q)
        a = areas.setdefault(q["area"], {"area": q["area"], "correct": 0, "total": 0})
        a["total"] += 1
        a["correct"] += int(ok)
        if not ok:
            key = (q["area"], q["section"], q["objective"])
            m = missed.setdefault(key, {"area": q["area"], "section": q["section"],
                                        "objective": q["objective"], "questions": []})
            m["questions"].append(q["id"])
        review.append({"id": q["id"], "type": q["type"], "stem": q["stem"], "options": q["options"],
                       "answer": q["answer"], "correct": q["correct"], "is_correct": ok,
                       "flagged": q["flagged"], "explanation": q["explanation"], "doc": _doc(q),
                       "area": q["area"], "section": q["section"], "objective": q["objective"]})
    by_area = []
    for a in areas.values():
        if a["total"]:
            a["percent"] = round(100 * a["correct"] / a["total"])
            by_area.append(a)
    recs = []
    for a in sorted(by_area, key=lambda x: x["percent"]):
        items = [m for m in missed.values() if m["area"] == a["area"]]
        if not items:
            continue
        sections: dict[str, list] = {}
        for m in items:
            sections.setdefault(m["section"], []).append(
                {"objective": m["objective"], "questions": m["questions"],
                 "search": "https://learn.microsoft.com/en-us/search/?terms=" + quote(m["objective"])})
        recs.append({"area": a["area"], "percent": a["percent"],
                     "sections": [{"section": s, "objectives": o} for s, o in sections.items()]})
    return {"score": score, "pass_mark": PASS_MARK, "passed": score >= PASS_MARK,
            "correct": right, "total": total, "by_area": by_area, "review": review,
            "missed_count": len(missed), "recommendations": recs, "guide_url": guide_mod.GUIDE_URL,
            "verified": exam["verified"], "case": exam.get("case"),
            "note": "This is a practice score: correct answers divided by total, scaled to 1000. "
                    "Microsoft's official exam uses its own scaled scoring, so this number is a guide only."}


# ---------- API ----------

class NewExam(BaseModel):
    mode: str
    allow_unverified: bool = False
    section: str | None = None  # limit questions to one skill group (used by the Labs page)
    source: str = "new"         # "new" = Claude writes questions (uses tokens). "bank" = reuse saved ones (free)


class LabSelection(BaseModel):
    enabled_labs: list[str]
    deploy_firewall: bool = False


class Answer(BaseModel):
    qid: int
    answer: list[str] | None = None


class Flag(BaseModel):
    qid: int
    flagged: bool


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


# ---------- labs ----------

TFVARS = BASE / "terraform" / "terraform.tfvars"
LAB_LINE = re.compile(r"^enabled_labs\s*=.*$", re.M)
FW_LINE = re.compile(r"^deploy_firewall\s*=.*$", re.M)


def _labs() -> dict:
    return json.loads((BASE / "labs.json").read_text(encoding="utf-8"))


def _selection() -> dict:
    text = TFVARS.read_text(encoding="utf-8") if TFVARS.exists() else ""
    m, f = LAB_LINE.search(text), FW_LINE.search(text)
    return {"enabled_labs": re.findall(r'"([a-z]+)"', m.group(0)) if m else [],
            "deploy_firewall": bool(f and "true" in f.group(0))}


@app.get("/labs")
def labs_page():
    return FileResponse(BASE / "static" / "labs.html")


@app.get("/api/labs")
def labs():
    data = _labs()
    data["selection"] = _selection()
    data["hosted"] = HOSTED
    data["terraform_dir"] = "~/sc500-exam-simulator/terraform" if HOSTED else str(BASE / "terraform")
    return data


@app.post("/api/labs/selection")
def save_selection(body: LabSelection):
    """Write the chosen labs into terraform/terraform.tfvars. Nothing is deployed here."""
    if HOSTED:
        raise HTTPException(403, "This copy runs in Azure. Edit terraform.tfvars on your own computer.")
    valid = [lab["id"] for lab in _labs()["labs"]]
    chosen = [x for x in valid if x in body.enabled_labs]
    if len(chosen) != len(set(body.enabled_labs)):
        raise HTTPException(400, "Unknown lab name.")
    if not TFVARS.exists():
        example = TFVARS.with_name("terraform.tfvars.example")
        if not example.exists():
            raise HTTPException(404, "terraform/terraform.tfvars is missing.")
        TFVARS.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    text = TFVARS.read_text(encoding="utf-8")
    lab_line = "enabled_labs = [" + ", ".join(f'"{x}"' for x in chosen) + "]"
    fw_line = "deploy_firewall = " + ("true" if body.deploy_firewall and "network" in chosen else "false")
    text = LAB_LINE.sub(lab_line, text) if LAB_LINE.search(text) else text.rstrip() + "\n" + lab_line + "\n"
    text = FW_LINE.sub(fw_line, text) if FW_LINE.search(text) else text.rstrip() + "\n" + fw_line + "\n"
    TFVARS.write_text(text, encoding="utf-8")
    return _selection()


@app.get("/api/doclink")
def doclink(q: str):
    """Check which Microsoft Learn page a search term resolves to. exact=false means it fell back to search."""
    return docs.resolve(q)


@app.get("/api/config")
def config():
    return {"mock": agent.MOCK, "model": agent.MODEL, "modes": MODES, "pass_mark": PASS_MARK, "bank": _bank_stats(),
            "has_key": bool(os.environ.get("ANTHROPIC_API_KEY")), "guide_url": guide_mod.GUIDE_URL}


@app.post("/api/exams")
def create_exam(body: NewExam):
    if body.mode not in MODES:
        raise HTTPException(400, "Unknown mode.")
    use_bank = body.source == "bank"
    if not use_bank and not agent.MOCK and not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(400, "No ANTHROPIC_API_KEY found. Add it to the .env file and restart the app.")
    # Source of truth: check the official study guide before every new exam.
    g = guide_mod.load_guide()
    if not g["verified"] and not body.allow_unverified:
        return {"needs_confirmation": True, "snapshot_date": g["checked_at"], "error": g["error"],
                "message": "The official SC-500 study guide could not be reached, so the current exam "
                           "scope cannot be verified. You can continue with an UNVERIFIED practice set "
                           f"built from a saved copy of the guide dated {g['checked_at']}."}
    total = MODES[body.mode]
    areas = g["areas"]
    if body.section:
        areas = [{**a, "sections": [s for s in a["sections"] if s["name"] == body.section]} for a in areas]
        areas = [a for a in areas if a["sections"]]
        if not areas:
            raise HTTPException(404, "That skill group is not in the current study guide.")
    case = None
    if use_bank:
        case, written = _from_bank(body.mode, areas, total)
    else:
        plan = agent.build_plan(total, areas, allow_ordering=body.mode != "case")
    try:
        if use_bank:
            pass
        elif body.mode == "case":
            case, written = agent.write_case_study(plan)
        else:
            written = agent.write_questions(plan)
    except Exception as exc:
        raise HTTPException(502, f"Question writing failed: {exc}")
    questions = []
    for i, q in enumerate(written, start=1):
        q.pop("slot", None)
        q.update({"id": i, "answer": None, "flagged": False, "changes": 0})
        questions.append(q)
    if not use_bank and not agent.MOCK:
        _bank_add(case, questions)
    exam = {"id": uuid.uuid4().hex, "mode": body.mode, "submitted": False,
            "created": datetime.now(timezone.utc).isoformat(), "verified": g["verified"],
            "guide_checked_at": g["checked_at"], "mock": agent.MOCK, "case": case,
            "section": body.section, "source": "bank" if use_bank else "new",
            "model": "saved questions (no tokens)" if use_bank else ("mock (no tokens)" if agent.MOCK else agent.MODEL),
            "area_names": [a["name"] for a in g["areas"]], "questions": questions}
    with LOCK:
        EXAMS[exam["id"]] = exam
        _save(exam)
    return _public(exam)


@app.get("/api/exams/{exam_id}")
def get_exam(exam_id: str):
    return _public(_get(exam_id))


@app.post("/api/exams/{exam_id}/answer")
def answer(exam_id: str, body: Answer, check: bool = False):
    exam = _get(exam_id)
    if exam["submitted"]:
        raise HTTPException(409, "This exam is already submitted.")
    q = _question(exam, body.qid)
    if q.get("checked"):
        raise HTTPException(409, "You already checked this question.")
    if check and exam["mode"] != "practice":
        raise HTTPException(403, "Answers and explanations are available after you submit the exam.")
    if check and not body.answer:
        raise HTTPException(400, "Enter an answer first.")
    labels = [o["label"] for o in q["options"]]
    new = None
    if body.answer:
        new = [str(x).upper() for x in body.answer]
        if any(x not in labels for x in new) or len(set(new)) != len(new):
            raise HTTPException(400, "Invalid answer.")
        if q["type"] in ("single", "solution") and len(new) != 1:
            raise HTTPException(400, "Select one answer.")
        if q["type"] == "multiple":
            if len(new) != q["required"]:
                raise HTTPException(400, f"Select exactly {q['required']} answers.")
            new = sorted(new)
        if q["type"] == "ordering" and len(new) != len(labels):
            raise HTTPException(400, "Place every action in the sequence.")
    with LOCK:
        if q["answer"] and new != q["answer"]:
            q["changes"] += 1
        q["answer"] = new
        if check:
            q["checked"] = True
        _save(exam)
    out = {"status": _status(exam)}
    if check:
        out["feedback"] = _feedback(q)
    return out


@app.post("/api/exams/{exam_id}/flag")
def flag(exam_id: str, body: Flag):
    exam = _get(exam_id)
    if exam["submitted"]:
        raise HTTPException(409, "This exam is already submitted.")
    q = _question(exam, body.qid)
    with LOCK:
        q["flagged"] = body.flagged
        _save(exam)
    return {"status": _status(exam)}


@app.post("/api/exams/{exam_id}/submit")
def submit(exam_id: str):
    exam = _get(exam_id)
    with LOCK:
        exam["submitted"] = True
        _save(exam)
    return _results(exam)


@app.get("/api/exams/{exam_id}/results")
def results(exam_id: str):
    exam = _get(exam_id)
    if not exam["submitted"]:
        raise HTTPException(403, "Answers and explanations are available after you submit the exam.")
    return _results(exam)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SC500_PORT", "8500"))
    print(f"\n  SC-500 practice exam simulator: http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
