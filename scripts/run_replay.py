#!/usr/bin/env python3
"""The offline eval: replay the golden fixtures and refuse any drift.

This is the kit's `make eval`. It is not a smoke test of "does it run": it recomputes every
locale in scope from the fixtures and compares each per-locale digest and the overall digest
against the pinned expectations in `tests/golden/replay.json`. Any difference is a failure
that names the locale and the section that moved.

    python scripts/run_replay.py               # check (exit 1 on drift)
    python scripts/run_replay.py --regenerate  # rewrite the pins, only when intended

Regeneration is a separate, explicit flag rather than an automatic fix-up, because a golden
file that rewrites itself when it disagrees proves nothing at all.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _path in (_ROOT / "src", _ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from replay_fixtures import (  # noqa: E402
    GOLDEN_PATH,
    compare,
    load_golden,
    replay_payload,
    write_golden,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="rewrite tests/golden/replay.json from the current behaviour",
    )
    args = parser.parse_args(argv)

    payload = replay_payload()

    if args.regenerate:
        write_golden(payload)
        print(f"golden replay regenerated: {GOLDEN_PATH}")
        print(f"  overall digest: {payload['overall_digest']}")
        return 0

    if not GOLDEN_PATH.exists():
        print(f"FAIL: no golden file at {GOLDEN_PATH}; run with --regenerate to create it")
        return 1

    problems = compare(load_golden(), payload)

    print("Golden replay  (speech-lexicon-kit)")
    print(f"  locales : {len(payload['locales'])}")
    print(f"  as_of   : {payload['as_of']}\n")
    width = max(len(locale) for locale in payload["locales"])
    for locale in payload["locales"]:
        case = payload["cases"][locale]
        drifted = any(line.startswith(f"{locale}:") for line in problems)
        print(
            f"  {locale.ljust(width)}   {case['case_digest'][:23]}...   "
            f"{'DRIFT' if drifted else 'OK'}"
        )
    print(f"\n  overall : {payload['overall_digest']}")

    if problems:
        print("\n  REPLAY: FAIL")
        for line in problems:
            print(f"    - {line}")
        return 1
    print("\n  REPLAY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
