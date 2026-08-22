# speech-lexicon-kit

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

`speech-lexicon-kit` is the **speech kernel** for hexagonal (ports-and-adapters) agent repos,
packaged once: the STT / TTS / diarization ports, the transcript value types, locale-sensitive
deterministic normalisation and phrase matching, ordered-phrase adherence primitives, and the
replay digest mechanics. A consuming application supplies its own phrases and its own adapters;
this package supplies the kernel around them.

Consumers designed for, not just the first one: E3 (`conversation-qa-scorecard`), E1
(`contact-centre-conversations`), E5 (`proactive-service-outreach`), G3
(`app-fraud-interdiction`), Cmp1 (`trade-comms-surveillance`), H6
(`meeting-knowledge-capture`) and F5 (`control-room-handover`, TTS brief only).

## Commands

A venv exists at `.venv`. Setup from scratch:

```sh
pip install -e ".[dev]"        # ruff (pinned) + mypy + pytest; no runtime deps at all
```

The hard gate, in order (all five must pass, and all run offline):

```sh
make gate
# ruff check src tests scripts
# ruff format --check src tests scripts   # ruff pinned EXACTLY so formatting never drifts
# mypy src                                # strict; src only
# pytest -m 'not integration'
# python scripts/run_replay.py            # the golden replay, this repo's eval
```

Run one thing:

```sh
pytest tests/test_normalisation.py -q
pytest tests/test_golden_replay.py -k hash_seed -q
make regenerate-golden          # ONLY when a change to the output is intended
```

## Hard constraints

- **Zero runtime dependencies.** Everything is stdlib. Do not add a dependency, not even an
  optional one: the kernel has to install and import on an air-gapped host.
- **No clock.** Nothing may call `datetime.now`, `time.*` or any other clock. A function that
  needs a time takes `as_of` from the caller and records it on its result. `tests/test_ports.py`
  fails the build if any module imports `time`, `os`, `random`, `uuid`, `socket`, `urllib`,
  `subprocess` or friends.
- **No I/O.** Audio is an `AudioRef` (a URI plus media type), never bytes read here. Adapters
  resolve URIs, in the consuming repo.
- **No phrases.** Not one disclosure wording, cue list or vertical lexicon ships in `src/`. A
  required wording is reviewed policy on a per-market schedule; if it lived here, changing it
  would mean releasing this package and bumping every consumer. The test fixtures are invented
  for the fixtures.
- **Python >=3.12**, mypy `strict = true`, ruff line-length 100 with `E,F,I,UP,B,SIM`.
- **Fail closed**, in these specific directions: an unknown LANGUAGE raises rather than
  borrowing English rules; a lexicon whose language no turn speaks raises rather than returning
  zero hits (a false absence reads as a compliance breach); a timing constraint that cannot be
  checked is `UNVERIFIABLE`, never `SATISFIED`; an empty requirement set is never
  `all_satisfied`; overlapping redaction spans are refused rather than merged.

## Architecture

Seven modules in `src/speech_lexicon_kit/`, re-exported flat from `__init__.py`:

- **transcript.py** - `ChannelRole`, `WordOffset`, `RedactionSpan`, `SpeakerTurn`, `Transcript`,
  `SpeakerSegment`, plus `span_timing` and `merge_diarization`. Everything frozen and validated
  at construction; a turn's `index` must equal its position so a citation resolves.
- **normalisation.py** - `LocaleRules`, `rules_for`, `normalise`, `NormalisedText`. Per-character
  source offsets are what make a match citable back to the original text. Read the module
  docstring before changing a folding rule: each one is a deliberate trade-off with a test.
- **matching.py** - `Lexicon` / `LexiconEntry` / `PhraseSpec` / `MatchMode` in, `TextMatch` and
  `LexiconHit` out. `find_matches` for plain strings (chat, email), `find_hits` for transcripts.
- **adherence.py** - `PhraseSequenceRequirement` and the six `AdherenceOutcome` values. `PENDING`
  and `UNVERIFIABLE` are the two that make this shared rather than per-repo.
- **redaction.py** - applies spans right to left; detection belongs to `pii-kit`, not here.
- **ports.py** - the three protocols and their request/result types.
- **replay.py** - `canonical_json` / `digest`: the encoding a replay proof is measured with.

## The golden replay is the point

`tests/golden/replay.json` pins, per locale in scope, the normalisation probes, the lexicon
hits and the adherence outcomes for the fixtures in `tests/replay_fixtures.py`. Both
`tests/test_golden_replay.py` and `scripts/run_replay.py` drive the same fixtures, so the test
and the eval cannot drift.

What it asserts, and why each one matters:

1. Two runs in one process are byte-identical.
2. A fresh interpreter under a different `PYTHONHASHSEED` agrees (set iteration and string
   hashing only vary across processes, so an in-process check cannot catch that class).
3. Every English region digests identically, and Japanese does not. Locale sensitivity is real
   and asserted in both directions.
4. All six adherence outcomes appear in the pinned output, so the replay pins the branches
   rather than only the happy path.
5. The comparator itself goes red on a tampered pin, and the digest moves when the input moves.
   A golden check that cannot fail is a ritual.

If you change behaviour deliberately, regenerate the golden IN THE SAME COMMIT as the change and
say in the message what moved and why. Never regenerate to make a red gate green.
