import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "render-eval-summary.py"
SKILL = "plugins/demo/skills/demo-skill"
REVIEW = {
    "skill": SKILL, "status": "reviewed", "validation": "PASSED", "errors": "0", "warnings": "1",
    "review_score": "85", "description": "70", "content": "90",
    "validation_block": "[passed] frontmatter", "judge_block": "[content]\n- actionability: 3/3",
}


def eval_row(mode, rate, passed, total, model="gpt-5.4-mini"):
    return {"skill": SKILL, "model": model, "mode": mode, "pass_rate": rate, "passed": passed,
            "total": total, "total_tokens": "1234", "total_time": "12", "results": []}


def run(tmp_path, reviews, evals, *extra):
    rdir, edir, out = tmp_path / "reviews", tmp_path / "evals", tmp_path / "summary.md"
    rdir.mkdir()
    edir.mkdir()
    for i, r in enumerate(reviews):
        (rdir / f"r{i}.json").write_text(json.dumps(r), encoding="utf-8")
    for i, e in enumerate(evals):
        (edir / f"e{i}.json").write_text(json.dumps(e), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), "--reviews-dir", str(rdir), "--evals-dir", str(edir),
                    "--threshold", "80", "--output", str(out), *extra], check=True)
    return out.read_text(encoding="utf-8")


def test_eval_table_row_compares_baseline_and_skill(tmp_path):
    md = run(tmp_path, [REVIEW], [eval_row("baseline", "50.0", "1", "2"), eval_row("skill", "100.0", "2", "2")])
    assert "# demo :: demo-skill" in md
    assert "| `gpt-5.4-mini` | ❌ 50.0% (1/2) | ✅ 100.0% (2/2) | +50.0pp | 1,234 |" in md
    assert "## ✅ PASSED LLM Judge Evaluation" in md


def test_tessl_disabled_prints_note_and_no_review_sections(tmp_path):
    md = run(tmp_path, [], [eval_row("skill", "100.0", "2", "2")], "--tessl-enabled", "false")
    assert "Tessl review skipped" in md
    assert "Validation Checks" not in md
    assert "LLM Judge Evaluation" not in md
    assert "# demo :: demo-skill" in md


def test_error_record_is_reported(tmp_path):
    err = {"skill": SKILL, "status": "error", "error": "This command requires you to be logged in."}
    md = run(tmp_path, [err], [])
    assert "## ❌ Tessl Review Error" in md
    assert "requires you to be logged in" in md


def test_missing_review_is_reported_when_tessl_enabled(tmp_path):
    md = run(tmp_path, [], [eval_row("skill", "100.0", "2", "2")])
    assert "## ❌ Tessl Review Missing" in md


def test_backticks_in_judge_output_do_not_break_the_fence(tmp_path):
    review = {**REVIEW, "judge_block": "- suggestion: add a ```bash example"}
    md = run(tmp_path, [review], [])
    assert "````\n- suggestion: add a ```bash example\n````" in md


def test_summary_stays_under_step_summary_limit(tmp_path):
    reviews = [{**REVIEW, "skill": f"plugins/p{i}/skills/s{i}", "judge_block": "x" * 30_000,
                "validation_block": "y" * 10_000} for i in range(76)]
    md = run(tmp_path, reviews, [])
    assert len(md.encode("utf-8")) <= 1_000_000
    assert "truncated" in md
    assert md.count("# p75 :: s75") == 1


def test_no_results_message(tmp_path):
    assert run(tmp_path, [], []) == "No evaluation results found.\n"
