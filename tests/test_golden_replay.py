"""The golden replay: byte-identical hits across runs, across processes, across locales.

This is the proof the kit exists to carry. Every consumer inherits an obligation to answer
"would this scorecard reproduce next quarter?", and the answer is only worth anything if the
kernel underneath it is pinned. So the fixtures in ``replay_fixtures`` are replayed here
against ``tests/golden/replay.json`` and asserted three ways: identical within a run,
identical in a fresh interpreter under a different hash seed, and identical across the
regions of a language while genuinely DIFFERENT across languages.

The last test in this file is the control. A golden comparison that cannot go red is a
ritual, so the comparator is run against a deliberately tampered pin and must report it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import replay_fixtures as fixtures
from speech_lexicon_kit import SUPPORTED_LOCALES, canonical_bytes

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_the_golden_file_exists_and_declares_its_schema():
    golden = fixtures.load_golden()
    assert golden["schema"] == fixtures.GOLDEN_SCHEMA
    assert golden["locales"] == list(SUPPORTED_LOCALES)


def test_the_replay_matches_the_pinned_golden():
    problems = fixtures.compare(fixtures.load_golden(), fixtures.replay_payload())
    assert problems == (), "\n".join(problems)


def test_two_runs_in_one_process_are_byte_identical():
    assert canonical_bytes(fixtures.replay_payload()) == canonical_bytes(fixtures.replay_payload())


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_each_locale_reproduces_its_pinned_digest(locale):
    pinned = fixtures.load_golden()["cases"][locale]["case_digest"]
    assert fixtures.case_payload(locale)["case_digest"] == pinned


def test_every_english_region_produces_identical_output():
    # They resolve to one rule set, so the digests MUST agree. If they ever stop agreeing,
    # normalisation has quietly become region-dependent.
    digests = {
        locale: fixtures.case_payload(locale)["case_digest"]
        for locale in SUPPORTED_LOCALES
        if fixtures.language_of(locale) == "en"
    }
    assert len(set(digests.values())) == 1, digests


def test_japanese_produces_different_output_from_english():
    # The whole reason normalisation is locale-sensitive. If these ever matched, one language
    # would be being scored with the other's folding rules.
    english = fixtures.case_payload("en-SG")["case_digest"]
    japanese = fixtures.case_payload("ja-JP")["case_digest"]
    assert english != japanese


@pytest.mark.parametrize("hash_seed", ["0", "1", "12345"])
def test_a_fresh_interpreter_under_a_different_hash_seed_agrees(hash_seed):
    # Set iteration and string hashing are the classic sources of run-to-run drift, and they
    # only vary across PROCESSES, so an in-process comparison cannot catch them.
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT / "src"), str(REPO_ROOT / "tests"), env.get("PYTHONPATH", "")]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, replay_fixtures as f; "
            "p = f.replay_payload(); "
            "print(json.dumps({k: v['case_digest'] for k, v in p['cases'].items()} "
            "| {'overall': p['overall_digest']}))",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    produced = json.loads(completed.stdout)
    golden = fixtures.load_golden()
    assert produced["overall"] == golden["overall_digest"]
    for locale in SUPPORTED_LOCALES:
        assert produced[locale] == golden["cases"][locale]["case_digest"]


def test_every_adherence_outcome_is_exercised_by_the_fixtures():
    # A replay that only ever pins SATISFIED would pin almost nothing. Each outcome has its
    # own code path and its own way of being wrong, so each appears in the golden.
    golden = fixtures.load_golden()
    outcomes: set[str] = set()
    for detail in golden["details"].values():
        for section in ("closed_adherence", "live_adherence"):
            outcomes.update(result["outcome"] for result in detail[section]["results"])
    assert outcomes == {
        "satisfied",
        "late",
        "out_of_order",
        "absent",
        "pending",
        "unverifiable",
    }


def test_the_replay_script_passes_offline():
    completed = subprocess.run(
        [sys.executable, "scripts/run_replay.py"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "REPLAY: PASS" in completed.stdout


def test_the_comparator_goes_red_on_a_tampered_pin():
    # The control. Prove the checker can fail before trusting that it passed.
    actual = fixtures.replay_payload()
    assert fixtures.compare(deepcopy(actual), actual) == ()

    tampered = deepcopy(actual)
    tampered["cases"]["ja-JP"]["case_digest"] = "sha256:" + "0" * 64
    problems = fixtures.compare(tampered, actual)
    assert any(line.startswith("ja-JP: digest drift") for line in problems)

    tampered = deepcopy(actual)
    tampered["details"]["en"]["closed_hits"][0]["matched_text"] = "something else entirely"
    problems = fixtures.compare(tampered, actual)
    assert any("section 'closed_hits' differs" in line for line in problems)

    tampered = deepcopy(actual)
    tampered["overall_digest"] = "sha256:" + "0" * 64
    assert any(line.startswith("overall digest") for line in fixtures.compare(tampered, actual))

    tampered = deepcopy(actual)
    del tampered["cases"]["en-AU"]
    problems = fixtures.compare(tampered, actual)
    assert any(line.startswith("en-AU: no pinned case") for line in problems)


def test_a_changed_fixture_moves_the_digest():
    # The other half of the control: the digest has to be sensitive to the INPUT, not just
    # stable. A pin that never moves is indistinguishable from a constant.
    baseline = fixtures.case_payload("en-SG")["case_digest"]
    original = fixtures.AS_OF
    try:
        fixtures.AS_OF = original.replace(hour=13)
        assert fixtures.case_payload("en-SG")["case_digest"] != baseline
    finally:
        fixtures.AS_OF = original
    assert fixtures.case_payload("en-SG")["case_digest"] == baseline
