import json

PAYLOAD = {
    "review": {"reviewScore": 85},
    "validation": {
        "overallPassed": True,
        "errorCount": 0,
        "warningCount": 1,
        "checks": [{"name": "frontmatter", "status": "passed"}, {"name": "length", "status": "warning", "message": "long body"}],
    },
    "judges": {
        "description": {"normalizedScore": 0.7, "scale": {"max": 3}, "evaluation": {"scores": {"trigger_clarity": {"score": 2, "reasoning": "vague"}}}},
        "content": {
            "normalizedScore": 0.9,
            "scale": {"max": 3},
            "evaluation": {"overall_assessment": "Solid.", "scores": {"actionability": {"score": 3}}, "suggestions": ["Add a ```bash example"]},
        },
    },
}


def test_reviewed_record_from_noisy_output(record):
    raw = "Resolving workspace...\n" + json.dumps(PAYLOAD) + "\nDone.\n"
    rec = record.build_record("plugins/p/skills/s", raw, 0)
    assert rec["status"] == "reviewed"
    assert rec["review_score"] == "85"
    assert rec["validation"] == "PASSED"
    assert (rec["errors"], rec["warnings"]) == ("0", "1")
    assert (rec["description"], rec["content"]) == ("70", "90")
    assert "[warning] length: long body" in rec["validation_block"]
    assert "- trigger clarity: 2/3 — vague" in rec["judge_block"]
    assert "- suggestion: Add a ```bash example" in rec["judge_block"]


def test_failed_validation_still_records_score(record):
    payload = {**PAYLOAD, "validation": {"overallPassed": False, "errorCount": 2, "warningCount": 0, "checks": []}}
    rec = record.build_record("plugins/p/skills/s", json.dumps(payload), 1)
    assert (rec["status"], rec["validation"], rec["errors"]) == ("reviewed", "FAILED", "2")


def test_auth_failure_becomes_error_record(record):
    raw = "Error: This command requires you to be logged in. Run `tessl login`.\n"
    rec = record.build_record("plugins/p/skills/s", raw, 1)
    assert rec == {"skill": "plugins/p/skills/s", "status": "error", "error": raw.strip()}


def test_empty_output_names_the_exit_code(record):
    rec = record.build_record("plugins/p/skills/s", "", 127)
    assert rec["status"] == "error"
    assert "127" in rec["error"]


def test_null_review_score_is_blank(record):
    payload = {"review": {"reviewScore": None}, "validation": {"overallPassed": True}}
    rec = record.build_record("plugins/p/skills/s", json.dumps(payload), 0)
    assert rec["review_score"] == ""
    assert rec["description"] == ""


def test_string_evaluation_is_kept_verbatim(record):
    payload = {"review": {"reviewScore": 50}, "judges": {"content": {"evaluation": "Needs work."}}}
    rec = record.build_record("plugins/p/skills/s", json.dumps(payload), 0)
    assert rec["judge_block"] == "[content]\nNeeds work."
