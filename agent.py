"""The question-writing agent.

The app decides WHAT each question covers (one objective from the study guide)
and its format. Claude writes the question, the answer key and the explanation.
The answer key never leaves the server until the exam is submitted.
"""
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MOCK = os.environ.get("SC500_MOCK", "") not in ("", "0", "false")
BATCH = 5
LABELS = "ABCDEFGH"

SYSTEM = """You write practice questions for Microsoft exam SC-500: Implementing End-to-End Security Controls for Cloud and AI Workloads.

Rules:
- Each question tests exactly the objective assigned to it. Stay inside the official SC-500 scope. Do not speculate about real exam content.
- Write in the style of Microsoft certification exams: a short company scenario (Contoso, Fabrikam, Litware, Adatum, Northwind Traders, Tailwind Traders), named resources (Sub1, RG1, VM1, storage1, KV1, Workspace1), a stated need, and one or more constraints such as "The solution must follow the principle of least privilege" or "The solution must minimize administrative effort". The constraint should be what separates the best answer from answers that only work.
- Test applied security decisions, not trivia. Wrong options must be real, plausible Microsoft features that fail for a specific reason.
- Use accurate, current Microsoft product names and portal terms. Only rely on product behaviour you are confident is correct. Never invent features, roles or settings.
- Do not hint at the answer in the stem. Keep option length and style even.
- Explanations are concise (2 to 4 sentences): why the answer is right and why the main wrong options fail.

Formats:
- single: exactly 4 options, exactly 1 correct index.
- multiple: exactly 5 options, 2 or 3 correct indices. End the stem with "Each correct answer presents part of the solution. (Choose two.)" or "(Choose three.)" to match the count.
- solution: the stem gives a scenario and goal, then a line starting "Solution:", then ends with "Does this meet the goal?". Options are exactly ["Yes", "No"].
- ordering: the stem asks which actions to perform in sequence. Give 4 or 5 options, every one part of the sequence, listed IN THE CORRECT ORDER. Set correct_indices to [0, 1, 2, ...]. The app shuffles them.

For single, multiple and ordering the app shuffles option order, so never write "all of the above" or refer to options by letter."""

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "slot": {"type": "integer", "description": "The slot number this question was assigned."},
        "stem": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "correct_indices": {"type": "array", "items": {"type": "integer"}},
        "explanation": {"type": "string"},
        "doc_query": {"type": "string", "description": "3 to 7 words that match the title of the one Microsoft Learn article that best explains the correct answer. Use the product name and the feature, for example 'Configure Azure Key Vault networking settings' or 'Microsoft Foundry guardrails and controls'. No question wording."},
    },
    "required": ["slot", "stem", "options", "correct_indices", "explanation", "doc_query"],
}
TOOL = {
    "name": "submit_questions",
    "description": "Submit the finished practice questions.",
    "input_schema": {"type": "object",
                     "properties": {"questions": {"type": "array", "items": QUESTION_SCHEMA}},
                     "required": ["questions"]},
}
CASE_TOOL = {
    "name": "submit_case_study",
    "description": "Submit the finished case study and its linked questions.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "overview": {"type": "string", "description": "Company overview, 1 short paragraph."},
            "existing_environment": {"type": "string", "description": "Identity, Azure, network, workloads, AI use. Plain text with line breaks."},
            "problem_statements": {"type": "string"},
            "requirements": {"type": "string", "description": "Planned changes, security and compliance requirements."},
            "questions": {"type": "array", "items": QUESTION_SCHEMA},
        },
        "required": ["title", "overview", "existing_environment", "problem_statements", "requirements", "questions"],
    },
}


# ---------- planning (done in code, so every question maps to the guide) ----------

def allocate(total: int, areas: list[dict]) -> list[int]:
    """Split questions across areas by the midpoint of each published weight."""
    mids = [(a["low"] + a["high"]) / 2 for a in areas]
    raw = [total * m / sum(mids) for m in mids]
    counts = [int(x) for x in raw]
    order = sorted(range(len(areas)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in order[: total - sum(counts)]:
        counts[i] += 1
    return counts


def format_mix(total: int, allow_ordering: bool = True) -> list[str]:
    shares = [("single", 0.5), ("multiple", 0.25), ("solution", 0.15), ("ordering", 0.10)]
    if not allow_ordering:
        shares = [("single", 0.55), ("multiple", 0.3), ("solution", 0.15)]
    out: list[str] = []
    for name, share in shares[1:]:
        out += [name] * max(1, round(total * share))
    out = out[: max(0, total - 1)]
    out += ["single"] * (total - len(out))
    random.shuffle(out)
    return out


def build_plan(total: int, areas: list[dict], allow_ordering: bool = True) -> list[dict]:
    plan = []
    for area, n in zip(areas, allocate(total, areas)):
        pool = [(s["name"], o) for s in area["sections"] for o in s["objectives"]]
        random.shuffle(pool)
        picks = [pool[i % len(pool)] for i in range(n)]
        for section, objective in picks:
            plan.append({"area": area["name"], "section": section, "objective": objective})
    random.shuffle(plan)
    for slot, (item, fmt) in enumerate(zip(plan, format_mix(total, allow_ordering)), start=1):
        item["slot"], item["type"] = slot, fmt
    return plan


# ---------- validation and shaping ----------

def _shape(item: dict, raw: dict) -> dict | None:
    """Validate one model-written question and turn it into a stored question."""
    try:
        stem = str(raw["stem"]).strip()
        options = [str(o).strip() for o in raw["options"]]
        correct = sorted({int(i) for i in raw["correct_indices"]})
        explanation = str(raw["explanation"]).strip()
    except (KeyError, TypeError, ValueError):
        return None
    kind, n = item["type"], len(options)
    if not stem or not explanation or any(not o for o in options) or len(set(options)) != n:
        return None
    if kind == "ordering":
        if not 3 <= n <= 6:
            return None
        order = list(range(n))
        shuffled = order[:]
        while shuffled == order:
            random.shuffle(shuffled)
        opts = [{"label": LABELS[pos], "text": options[src]} for pos, src in enumerate(shuffled)]
        key = [LABELS[shuffled.index(src)] for src in order]  # labels in the right sequence
    else:
        if any(i < 0 or i >= n for i in correct):
            return None
        if kind == "single" and (n != 4 or len(correct) != 1):
            return None
        if kind == "multiple" and (n != 5 or len(correct) not in (2, 3)):
            return None
        if kind == "solution":
            if [o.lower() for o in options] != ["yes", "no"] or len(correct) != 1:
                return None
            shuffled = [0, 1]
        else:
            shuffled = list(range(n))
            random.shuffle(shuffled)
        opts = [{"label": LABELS[pos], "text": options[src]} for pos, src in enumerate(shuffled)]
        key = sorted(LABELS[shuffled.index(src)] for src in correct)
    return {"area": item["area"], "section": item["section"], "objective": item["objective"],
            "doc_query": str(raw.get("doc_query") or "").strip()[:120],
            "type": kind, "stem": stem, "options": opts, "correct": key,
            "required": len(key), "explanation": explanation}


def _brief(items: list[dict]) -> str:
    lines = ["Write one question for each slot below.\n"]
    for it in items:
        lines.append(f"Slot {it['slot']} | format: {it['type']} | area: {it['area']} | "
                     f"skill group: {it['section']} | objective: {it['objective']}")
    return "\n".join(lines)


# ---------- model calls ----------

_client = None
_usage_lock = threading.Lock()
USAGE = {"calls": 0, "input": 0, "output": 0}


def _track(resp):
    """Print token use for each model call, plus the running total since the app started."""
    u = getattr(resp, "usage", None)
    if u is None:
        return
    i, o = getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0
    with _usage_lock:
        USAGE["calls"] += 1
        USAGE["input"] += i
        USAGE["output"] += o
        print(f"  [tokens] model {getattr(resp, 'model', MODEL)} | call {USAGE['calls']}: in {i:,} / out {o:,}   |   "
              f"total: in {USAGE['input']:,} / out {USAGE['output']:,}", flush=True)


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _call(tool: dict, user: str, max_tokens: int) -> dict:
    # Some models reject a forced tool_choice, so ask for the tool call in the prompt instead.
    user = (user + f"\n\nReturn your work by calling the {tool['name']} tool exactly once. "
            "Do not reply with plain text.")
    for _ in range(2):
        resp = client().messages.create(
            model=MODEL, max_tokens=max_tokens, system=SYSTEM, tools=[tool],
            tool_choice={"type": "auto"},
            messages=[{"role": "user", "content": user}],
        )
        _track(resp)
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                return block.input
    raise RuntimeError("The model returned no questions.")


def _mock_question(it: dict) -> dict:
    kind = it["type"]
    stem = f"[MOCK QUESTION, no AI used] Objective: {it['objective']}."
    if kind == "single":
        return {"slot": it["slot"], "stem": stem, "options": ["Right answer", "Wrong 1", "Wrong 2", "Wrong 3"],
                "correct_indices": [0], "explanation": "Mock explanation.", "doc_query": "Azure RBAC least privilege"}
    if kind == "multiple":
        return {"slot": it["slot"], "stem": stem + " Each correct answer presents part of the solution. (Choose two.)",
                "options": ["Right 1", "Right 2", "Wrong 1", "Wrong 2", "Wrong 3"],
                "correct_indices": [0, 1], "explanation": "Mock explanation."}
    if kind == "solution":
        return {"slot": it["slot"], "stem": stem + "\n\nSolution: You do the right thing.\n\nDoes this meet the goal?",
                "options": ["Yes", "No"], "correct_indices": [0], "explanation": "Mock explanation."}
    return {"slot": it["slot"], "stem": stem + " Which four actions should you perform in sequence?",
            "options": ["Step 1", "Step 2", "Step 3", "Step 4"],
            "correct_indices": [0, 1, 2, 3], "explanation": "Mock explanation."}


def _write_batch(items: list[dict]) -> list[dict]:
    if MOCK:
        raw = [_mock_question(it) for it in items]
    else:
        raw = _call(TOOL, _brief(items), 16000).get("questions", [])
    by_slot = {}
    for r in raw:
        if isinstance(r, dict) and isinstance(r.get("slot"), int):
            by_slot[r["slot"]] = r
    done = []
    for it in items:
        q = _shape(it, by_slot.get(it["slot"], {}))
        if q:
            q["slot"] = it["slot"]
            done.append(q)
    return done


def write_questions(plan: list[dict]) -> list[dict]:
    """Write all questions in parallel batches. Retry failed slots once."""
    def run(items):
        batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]
        out, errors = [], []
        with ThreadPoolExecutor(max_workers=5) as pool:
            for fut in [pool.submit(_write_batch, b) for b in batches]:
                try:
                    out += fut.result()
                except Exception as exc:
                    errors.append(exc)
        return out, errors

    done, errors = run(plan)
    missing = [it for it in plan if it["slot"] not in {q["slot"] for q in done}]
    if missing:
        more, errors2 = run(missing)
        done += more
        errors += errors2
    if not done:
        raise RuntimeError(str(errors[0]) if errors else "No valid questions were produced.")
    done.sort(key=lambda q: q["slot"])
    return done


def write_case_study(plan: list[dict]) -> tuple[dict, list[dict]]:
    if MOCK:
        data = {"title": "Mock case study: Contoso", "overview": "Mock overview.",
                "existing_environment": "Mock environment.", "problem_statements": "Mock problems.",
                "requirements": "Mock requirements.", "questions": [_mock_question(it) for it in plan]}
    else:
        user = ("Write one realistic SC-500 case study in the Microsoft exam style, then the linked questions. "
                "The case text must hold the facts each question needs (resource names, tables of users or "
                "resources written as plain text lines, requirements). Each question must depend on the case "
                "and must not repeat the case text.\n\n" + _brief(plan))
        data = _call(CASE_TOOL, user, 20000)
    case = {k: str(data.get(k, "")).strip() for k in
            ("title", "overview", "existing_environment", "problem_statements", "requirements")}
    by_slot = {r.get("slot"): r for r in data.get("questions", []) if isinstance(r, dict)}
    done = []
    for it in plan:
        q = _shape(it, by_slot.get(it["slot"], {}))
        if q:
            q["slot"] = it["slot"]
            done.append(q)
    if not done:
        raise RuntimeError("No valid case study questions were produced.")
    return case, done
