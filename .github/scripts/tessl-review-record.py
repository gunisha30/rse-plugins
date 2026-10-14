#!/usr/bin/env python3
"""Turn raw `tessl review run quality --json` output into the review record that
render-eval-summary.py reads.

Usage:
    python tessl-review-record.py --skill plugins/x/skills/y \\
        --raw /tmp/tessl-raw.txt --exit-code 0 --output /tmp/review-results/y.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract_json(text: str) -> dict | None:
    """Return the first complete top-level JSON object in text, or None."""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            return obj
        start = text.find("{", start + 1)
    return None


def judge_percent(judge: dict | None) -> str:
    score = (judge or {}).get("normalizedScore")
    return "" if score is None else str(round(float(score) * 100))


def format_validation(validation: dict) -> str:
    lines = []
    for check in validation.get("checks") or []:
        line = f"[{check.get('status', '?')}] {check.get('name', '')}"
        if check.get("message"):
            line += f": {check['message']}"
        lines.append(line)
    return "\n".join(lines)


def format_judges(judges: dict) -> str:
    lines: list[str] = []
    for judge_id in sorted(judges):
        judge = judges[judge_id] or {}
        evaluation = judge.get("evaluation")
        lines.append(f"[{judge_id}]")
        if isinstance(evaluation, str):
            lines.append(evaluation)
            continue
        evaluation = evaluation or {}
        if evaluation.get("overall_assessment"):
            lines.append(evaluation["overall_assessment"])
        scale_max = (judge.get("scale") or {}).get("max")
        out_of = f"/{scale_max}" if scale_max is not None else ""
        for dim, val in (evaluation.get("scores") or {}).items():
            line = f"- {dim.replace('_', ' ')}: {val.get('score')}{out_of}"
            if val.get("reasoning"):
                line += f" — {val['reasoning']}"
            lines.append(line)
        for suggestion in evaluation.get("suggestions") or []:
            lines.append(f"- suggestion: {suggestion}")
    return "\n".join(lines)


def build_record(skill: str, raw: str, exit_code: int) -> dict:
    payload = extract_json(raw)
    if payload is None:
        message = raw.strip()[:500] or f"tessl exited with code {exit_code} and printed nothing"
        return {"skill": skill, "status": "error", "error": message}
    validation = payload.get("validation") or {}
    judges = payload.get("judges") or {}
    score = (payload.get("review") or {}).get("reviewScore")
    return {
        "skill": skill,
        "status": "reviewed",
        "validation": "PASSED" if validation.get("overallPassed") else "FAILED",
        "errors": str(validation.get("errorCount", "")),
        "warnings": str(validation.get("warningCount", "")),
        "review_score": "" if score is None else str(score),
        "description": judge_percent(judges.get("description")),
        "content": judge_percent(judges.get("content")),
        "validation_block": format_validation(validation),
        "judge_block": format_judges(judges),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, help="Skill directory, e.g. plugins/x/skills/y")
    parser.add_argument("--raw", required=True, help="File holding tessl's combined stdout and stderr")
    parser.add_argument("--exit-code", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    raw_path = Path(args.raw)
    raw = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.exists() else ""
    record = build_record(args.skill, raw, args.exit_code)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{args.skill}: {record['status']} {record.get('review_score', '')}".rstrip())


if __name__ == "__main__":
    main()
