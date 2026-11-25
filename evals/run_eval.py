"""Question-quality eval: writes one question for each of the 20 fixed objectives and scores them.

Run from the repo root:
    python3 evals/run_eval.py              # model from ANTHROPIC_MODEL, as the app uses
    ANTHROPIC_MODEL=claude-opus-5-5 python3 evals/run_eval.py
    SC500_MOCK=1 python3 evals/run_eval.py # no API calls, no judge: checks the script itself

Metrics:
    format_pass_rate     questions that pass the app's own format checks (agent._shape), first try, no retry
    exact_link_rate      passing questions whose doc_query resolves to an exact Learn page (docs.resolve)
    answer_accuracy      judged correct / (correct + incorrect). A second model call checks the answer key
                         against the text of that Learn page. Questions with no exact page, or a page that
                         does not cover the point, are counted but left out of the rate.
    tokens_per_question  question-writing tokens (input + output) per passing question. Judge tokens are separate.

Each run is saved to evals/results/<timestamp>_<model>.json and compared with the previous run.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _load_env():
    """Same .env rules as app.py. Must run before agent is imported, because agent reads ANTHROPIC_MODEL."""
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
sys.path.insert(0, str(ROOT))
import httpx  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

import agent  # noqa: E402
import docs  # noqa: E402

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-opus-5-5")
JUDGE_TOOL = {
    "name": "submit_verdict",
    "description": "Submit your verdict on the practice question's answer key.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["correct", "incorrect", "not_covered"],
                        "description": "correct: the page supports the answer key. incorrect: the page contradicts it, "
                                       "or shows another option is right. not_covered: the page does not say enough to decide."},
            "reason": {"type": "string", "description": "One or two sentences, citing what the page says."},
        },
        "required": ["verdict", "reason"],
        "additionalProperties": False,
    },
}
JUDGE_SYSTEM = ("You check the answer keys of Microsoft certification practice questions. Judge only against the "
                "Microsoft Learn page you are given, not against memory. Return your verdict by calling the "
                "submit_verdict tool exactly once.")


# ---------- writing ----------

def plan() -> list[dict]:
    items = json.loads((HERE / "objectives.json").read_text(encoding="utf-8"))["objectives"]
    return [{**it, "slot": n} for n, it in enumerate(items, start=1)]


def write_batch(items: list[dict]) -> list[dict]:
    """One model call per batch, like the app. No retry, so the format rate is first-try."""
    try:
        raw = ([agent._mock_question(it) for it in items] if agent.MOCK
               else agent._call(agent.TOOL, agent._brief(items), 16000).get("questions", []))
    except Exception as exc:  # API, auth or network error: not a format failure, so the run is not saved
        print(f"  [eval] batch failed: {type(exc).__name__}: {exc}", flush=True)
        return [{"slot": it["slot"], "error": f"{type(exc).__name__}: {exc}"} for it in items]
    by_slot = {r["slot"]: r for r in raw if isinstance(r, dict) and isinstance(r.get("slot"), int)}
    out = []
    for it in items:
        q = agent._shape(it, by_slot.get(it["slot"], {}))
        out.append({"slot": it["slot"], "objective": it["objective"], "type": it["type"],
                    "format_ok": q is not None, "question": q})
    return out


# ---------- judging ----------

def page_text(url: str) -> str:
    resp = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "sc500-eval"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup.body or soup
    return " ".join(main.get_text(" ").split())


def render(q: dict) -> str:
    opts = "\n".join(f"{o['label']}. {o['text']}" for o in q["options"])
    key = ("Correct sequence: " if q["type"] == "ordering" else "Answer key: ") + ", ".join(q["correct"])
    return f"Format: {q['type']}\n\n{q['stem']}\n\n{opts}\n\n{key}\n\nExplanation: {q['explanation']}"


def judge(q: dict, url: str) -> dict:
    """Ask a second model whether the Learn page supports the answer key."""
    try:
        text = page_text(url)
    except Exception as exc:
        return {"verdict": "no_page", "reason": f"Fetch failed: {type(exc).__name__}: {exc}", "in": 0, "out": 0}
    user = (f"<learn_page url=\"{url}\">\n{text}\n</learn_page>\n\n<question>\n{render(q)}\n</question>\n\n"
            "Is the answer key right, according to this page?")
    resp = agent.client().beta.messages.create(
        model=JUDGE_MODEL, max_tokens=16000, system=JUDGE_SYSTEM, tools=[JUDGE_TOOL],
        tool_choice={"type": "auto"},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",  # re-run on another model if declined
        messages=[{"role": "user", "content": user}],
    )
    usage = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
    if resp.stop_reason == "refusal":
        return {"verdict": "error", "reason": "The judge declined.", **usage}
    for block in resp.content:
        if block.type == "tool_use" and block.name == JUDGE_TOOL["name"]:
            return {"verdict": block.input["verdict"], "reason": block.input["reason"], **usage}
    return {"verdict": "error", "reason": "The judge returned no verdict.", **usage}


def check(row: dict) -> dict:
    q = row["question"]
    link = docs.resolve(q["doc_query"])
    row["doc_query"], row["link"], row["exact_link"] = q["doc_query"], link["url"], link["exact"]
    if agent.MOCK:
        row["judge"] = {"verdict": "skipped", "reason": "Mock mode.", "in": 0, "out": 0}
    elif not link["exact"]:
        row["judge"] = {"verdict": "no_page", "reason": "No exact Learn page to judge against.", "in": 0, "out": 0}
    else:
        row["judge"] = judge(q, link["url"])
    return row


# ---------- scoring and comparison ----------

def score(rows: list[dict], write_tokens: dict) -> dict:
    ok = [r for r in rows if r["format_ok"]]
    verdicts = [r["judge"]["verdict"] for r in ok]
    right, wrong = verdicts.count("correct"), verdicts.count("incorrect")
    rate = lambda a, b: round(a / b, 3) if b else None  # noqa: E731
    return {
        "format_pass_rate": rate(len(ok), len(rows)),
        "exact_link_rate": rate(sum(r["exact_link"] for r in ok), len(ok)),
        "answer_accuracy": rate(right, right + wrong),
        "tokens_per_question": round((write_tokens["input"] + write_tokens["output"]) / len(ok)) if ok else None,
        "counts": {"objectives": len(rows), "format_ok": len(ok), "correct": right, "incorrect": wrong,
                   "not_covered": verdicts.count("not_covered"), "no_page": verdicts.count("no_page"),
                   "judge_error": verdicts.count("error")},
        "write_tokens": write_tokens,
        "judge_tokens": {"input": sum(r["judge"]["in"] for r in ok), "output": sum(r["judge"]["out"] for r in ok)},
    }


def previous(mock: bool) -> dict | None:
    """The latest saved run of the same kind (mock runs are only compared with mock runs)."""
    runs = []
    for f in RESULTS.glob("*.json"):
        try:
            run = json.loads(f.read_text(encoding="utf-8"))
            if run.get("mock") == mock:
                runs.append(run)
        except ValueError:
            pass
    return max(runs, key=lambda r: r["date"]) if runs else None


def compare(now: dict, last: dict | None) -> str:
    names = ["format_pass_rate", "exact_link_rate", "answer_accuracy", "tokens_per_question"]
    lines = [f"Model {now['model']} (judge {now['judge_model']}), {now['date']}"]
    if last:
        lines.append(f"Last run: model {last['model']} (judge {last['judge_model']}), {last['date']}")
    lines.append(f"\n{'metric':<22}{'last':>10}{'now':>10}{'change':>10}")
    for n in names:
        a, b = (last or {}).get("metrics", {}).get(n), now["metrics"].get(n)
        fmt = (lambda v: "-" if v is None else f"{v:,}") if n == "tokens_per_question" else \
              (lambda v: "-" if v is None else f"{v:.0%}")
        diff = "-" if a is None or b is None else (f"{b - a:+,}" if n == "tokens_per_question" else f"{(b - a) * 100:+.0f} pts")
        lines.append(f"{n:<22}{fmt(a):>10}{fmt(b):>10}{diff:>10}")
    c = now["metrics"]["counts"]
    lines.append(f"\n{c['format_ok']}/{c['objectives']} passed format. Judged: {c['correct']} correct, {c['incorrect']} incorrect, "
                 f"{c['not_covered']} not covered by the page, {c['no_page']} with no exact page, {c['judge_error']} judge errors.")
    return "\n".join(lines)


def main() -> int:
    items = plan()
    start = dict(agent.USAGE)
    batches = [items[i:i + agent.BATCH] for i in range(0, len(items), agent.BATCH)]
    with ThreadPoolExecutor(max_workers=5) as pool:
        rows = [r for batch in pool.map(write_batch, batches) for r in batch]
    write_tokens = {"input": agent.USAGE["input"] - start["input"], "output": agent.USAGE["output"] - start["output"]}
    failed = [r for r in rows if "error" in r]
    if failed:
        print(f"\n{len(failed)} of {len(rows)} questions hit an API error (first: {failed[0]['error']}). "
              "Nothing saved, so the comparison with earlier runs stays clean. Fix the error and run again.")
        return 1

    with ThreadPoolExecutor(max_workers=5) as pool:
        checked = list(pool.map(check, [r for r in rows if r["format_ok"]]))
    by_slot = {r["slot"]: r for r in checked}
    rows = [by_slot.get(r["slot"], r) for r in rows]

    now = datetime.now(timezone.utc)
    result = {"model": agent.MODEL, "judge_model": JUDGE_MODEL, "date": now.isoformat(timespec="microseconds"),
              "mock": agent.MOCK, "metrics": score(rows, write_tokens), "questions": rows}
    last = previous(agent.MOCK)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{now:%Y-%m-%dT%H%M%S.%fZ}_{agent.MODEL}{'_mock' if agent.MOCK else ''}.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n" + compare(result, last) + f"\n\nSaved {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
