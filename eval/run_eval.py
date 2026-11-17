"""The eval on Nordavo's 10 labelled examples: python -m eval.run_eval [--repeat N]

It runs the same decision code as the agent (agent/decide.py) and sends nothing.
The labels come only from Nordavo. Ten examples is a small set: one ticket is 10 points."""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime

from agent import config
from agent.config import ROOT, load_settings
from agent.decide import TicketDecision, decide_ticket
from agent.helpdesk import Helpdesk
from agent.llm import LLM, ProviderConfigError, ProviderUnavailable, Usage
from agent.prompts import Faq
from agent.redact import mask

FIELDS = ("language", "category", "priority", "action")
RESULTS = ROOT / "eval" / "results"


def score(example: dict, decision: TicketDecision) -> dict:
    """Compare one decision with Nordavo's label."""
    label = example.get("label") or {}
    got = {"language": decision.body["language"], "category": decision.body["category"],
           "priority": decision.body["priority"], "action": decision.action}
    row = {
        "id": example.get("id"),
        "expected": {name: label.get(name) for name in FIELDS},
        "got": got,
        "match": {name: got[name] == label.get(name) for name in FIELDS},
        "priority_within_one": _within_one(got["priority"], label.get("priority")),
        "missed_handoff": label.get("action") == "handoff" and got["action"] != "handoff",
        "needless_handoff": label.get("action") != "handoff" and got["action"] == "handoff",
        "expected_reason": label.get("reason"),
        "got_reason": decision.body.get("reason"),
        "faq_ids": decision.log.get("faq_ids"),
        "override": decision.log.get("override"),
        "checks": decision.log.get("checks"),
        "back_translation": decision.log.get("back_translation"),
    }
    if label.get("action") == "reply":
        named = set(re.findall(r"F\d{2}", label.get("reason") or ""))
        row["cites_their_faq"] = bool(named & set(row["faq_ids"] or [])) if named else None
    return row


def _within_one(got: str, expected: str | None) -> bool:
    try:
        return abs(int(got[1]) - int(expected[1])) <= 1
    except (TypeError, ValueError, IndexError):
        return False


def summarize(rows: list[dict]) -> dict:
    return {
        "examples": len(rows),
        "missed_handoffs": [row["id"] for row in rows if row["missed_handoff"]],
        "needless_handoffs": [row["id"] for row in rows if row["needless_handoff"]],
        **{name: sum(row["match"][name] for row in rows) for name in FIELDS},
        "priority_within_one": sum(row["priority_within_one"] for row in rows),
    }


def print_run(number: int, rows: list[dict], summary: dict) -> None:
    n = summary["examples"]
    print(f"\n=== Run {number} ===")
    print(f"Missed handoffs (their label: handoff; we did not): {summary['missed_handoffs'] or 'none'}")
    print(f"Needless handoffs (we handed off; their label did not): {summary['needless_handoffs'] or 'none'}")
    for name in FIELDS:
        print(f"{name:>9}: {summary[name]}/{n}")
    print(f"priority within one level: {summary['priority_within_one']}/{n}")
    for row in rows:
        wrong = [name for name in FIELDS if not row["match"][name]]
        if not wrong:
            continue
        print(f"\n{row['id']}: wrong {', '.join(wrong)}")
        for name in wrong:
            print(f"  {name}: expected {row['expected'][name]}, got {row['got'][name]}")
        print(f"  their reason: {row['expected_reason']}")
        print(f"  our reason:   {row['got_reason']}")


def commit_id() -> str:
    """The git commit the eval ran on, with '-dirty' if there were uncommitted changes."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    try:
        return git("rev-parse", "--short", "HEAD") + ("-dirty" if git("status", "--porcelain") else "")
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the agent on Nordavo's labelled examples.")
    parser.add_argument("--repeat", type=int, default=1, help="run the set N times, to see if the score is stable")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a Windows console may not print every character
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    settings = load_settings()
    helpdesk, llm, faq = Helpdesk(settings), LLM(settings), Faq.load()
    examples = helpdesk.examples()
    print(f"{len(examples)} examples, model {settings.llm_model}, prompt {config.PROMPT_VERSION}")

    usage, runs = Usage(), []
    try:
        for number in range(1, args.repeat + 1):
            rows = []
            for example in examples:
                decision = decide_ticket(example, faq, llm)
                usage.add(decision.usage)
                rows.append(score(example, decision))
            summary = summarize(rows)
            print_run(number, rows, summary)
            runs.append({"summary": summary, "rows": rows})
    except (ProviderUnavailable, ProviderConfigError) as error:
        print(f"\nStopped: {error}")

    decided = sum(len(run["rows"]) for run in runs)
    per_100 = usage.cost_usd() / decided * 100 if decided else 0.0
    print(f"\nTokens: {usage.input_tokens} in, {usage.output_tokens} out, {usage.calls} calls. "
          f"Cost per 100 tickets: about ${per_100:.4f}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y-%m-%d_%H%M%S}-{commit_id()}.json"
    result = {"model": settings.llm_model, "prompt_version": config.PROMPT_VERSION, "usage": vars(usage),
              "cost_per_100_tickets_usd": round(per_100, 4), "runs": runs}
    path.write_text(mask(json.dumps(result, indent=2, ensure_ascii=False))[0], encoding="utf-8")
    print(f"Saved {path.relative_to(ROOT)}")
    return 0 if runs else 1


if __name__ == "__main__":
    sys.exit(main())
