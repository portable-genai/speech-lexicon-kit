# speech-lexicon-kit

The shared **speech kernel** for hexagonal (ports-and-adapters) agent repos. One versioned
source of truth for the speech layer that every conversation-facing system re-implements: the
speech-to-text / text-to-speech / diarization ports, the transcript value types, locale-sensitive
deterministic normalisation and phrase matching, and ordered-phrase adherence primitives.

**Pure standard library. Zero runtime dependencies. No clock. No I/O.** Every function that needs
a time takes `as_of` from the caller, and audio is referenced by URI for an adapter to resolve, so
the kernel installs and runs on an air-gapped host and an offline test profile needs no network.

## Why it exists

Three systems already in this portfolio have to agree on what "the agent read the recording
disclosure at 00:12 of turn 4" means, and several more are coming. Left to itself, each of them
writes its own `text.lower().strip()`, its own turn record and its own "was it said?" check, and
they disagree: one finds the disclosure inside `reinsurance`, one misses it because the recogniser
emitted full-width digits, and the Japanese one misses it because there are no spaces to split on.
A compliance answer that depends on which repo asked is not an answer.

This package fixes the KERNEL and nothing above it. It carries the matching; it does not carry a
single phrase.

## The line: kernel here, lexicons in the consuming repo

| Here | In the consuming repo |
|---|---|
| Ports, transcript types, normalisation, matching, adherence, replay digests | The phrases themselves: disclosure wordings, scam cues, market-abuse lexicons, meeting-commitment cues |
| How a match is found and cited | Which requirement applies to which product, market and severity |
| That an unsatisfied step on a closed transcript is ABSENT | What an ABSENT step costs on a scorecard |

A required wording is reviewed vertical policy on a per-market schedule. If it lived here, changing
a disclosure would mean releasing a shared package and bumping every consumer. So it does not live
here, and the surface is designed so it never has to.

## What you get

```python
from speech_lexicon_kit import (
    # ports (typing.Protocol, runtime_checkable) - adapters live in your repo
    SpeechToTextPort, TextToSpeechPort, DiarizationPort,
    TranscriptionRequest, SpeechSynthesisRequest, DiarizationRequest, AudioRef,

    # transcript types
    Transcript, SpeakerTurn, WordOffset, ChannelRole, RedactionSpan, SpeakerSegment,
    span_timing, merge_diarization,

    # locale-sensitive normalisation
    normalise, rules_for, LocaleRules, NormalisedText, SUPPORTED_LOCALES,

    # phrase matching -> lexicon hits
    Lexicon, LexiconEntry, PhraseSpec, MatchMode, LexiconHit, find_hits, find_matches,

    # ordered-phrase adherence
    PhraseSequenceRequirement, AdherenceOutcome, evaluate_requirements, ordered_hit_chain,

    # replay mechanics
    canonical_json, digest,
)
```

```python
from datetime import UTC, datetime

lexicon = Lexicon(                       # YOUR phrases, from YOUR reviewed pack
    lexicon_id="example-disclosures",
    locale="en-SG",
    entries=(
        LexiconEntry("recording_notice", (PhraseSpec("p1", "this call may be recorded"),)),
        LexiconEntry("identity_check", (PhraseSpec("p1", "confirm your date of birth"),)),
    ),
)

hits = find_hits(transcript, lexicon, roles=[ChannelRole.AGENT])
report = evaluate_requirements(
    transcript,
    hits,
    [PhraseSequenceRequirement("R1", ("recording_notice", "identity_check"), deadline_ms=60_000)],
    as_of=datetime.now(UTC),             # the caller owns the clock, always
)
report.all_satisfied                     # False for an empty requirement set: fails closed
```

## Locale sensitivity is the point

Normalisation is a pure function of `(text, rules)`, and the rules differ by language in a way
that changes answers:

| | English (`en-*`) | Japanese (`ja-JP`) |
|---|---|---|
| Separators | runs collapse to one space; matches must land on token boundaries | removed entirely; matching is over the character run |
| Punctuation | becomes a separator, so `co-operate` and `co operate` agree | dropped outright |
| NFKC | folds full-width digits and forms | also folds half-width kana with their voicing marks |
| Extra folding | none | hiragana folded to katakana; dash-like characters folded to the prolonged sound mark |

So `insurance` does not match inside `reinsurance` in English, and would in Japanese if the same
rules were applied, which is why applying one language's rules to another is refused rather than
approximated. `rules_for` resolves by language subtag, so every English region shares one rule set;
an unregistered language raises.

Every normalised character keeps the half-open source range it came from, so a match found in
normalised space is reported as a character span in the **original** turn text. That is what makes
a hit citable.

## Adherence has six outcomes, and only one of them is a pass

`SATISFIED`, `LATE`, `OUT_OF_ORDER`, `ABSENT`, `PENDING`, `UNVERIFIABLE`.

The last two are why this is a shared primitive rather than three lines per repo:

- **`PENDING`** - the step has not happened, but the transcript is still open and its deadline has
  not passed as of the caller's `as_of`. Without it, a live copilot reports a breach in the first
  second of every call.
- **`UNVERIFIABLE`** - the sequence is present and in order, but a declared timing constraint
  cannot be checked because the transcript carries no word timings. Fail-closed: an unchecked
  deadline is never reported as a met one.

## Golden replay

`tests/golden/` holds the pinned expected hits and per-locale digests for a fixed set of synthetic
transcripts and lexicons, in every locale in scope. The replay proves three things: the same input
produces byte-identical output within a run, across runs, and in a fresh interpreter under a
different `PYTHONHASHSEED`; and that the locales genuinely differ where they should.

```sh
make eval                      # scripts/run_replay.py, the offline eval
python scripts/run_replay.py --regenerate    # only when a change to the output is intended
```

If normalisation is locale-sensitive, that replay is the whole point of the kit: it is the
artefact that lets a consumer say a quarter-old scorecard would reproduce today.

## Install

```sh
pip install speech-lexicon-kit
```

## Develop

```sh
pip install -e ".[dev]"
make gate      # ruff check + ruff format --check + mypy src + pytest -m 'not integration' + eval
```

The hard gate is ruff (lint) + ruff (format check, ruff pinned exactly) + mypy `--strict` (src
only) + pytest + the golden replay, on Python 3.12 and 3.13, entirely offline.

## Design invariants (do not "fix" these)

- **No clock.** Nothing reads the wall clock. `as_of` is a parameter and is recorded on the
  result, so a replay with the same `as_of` is byte-identical.
- **No I/O.** Audio is an `AudioRef`, never bytes read here. Adapters resolve URIs; this package
  never holds a credential and never persists a customer's voice.
- **No phrases.** Not one wording ships in this package, in code or in fixtures used as
  reference data. The test fixtures are obviously invented.
- **Spans cite the original text.** Matching runs on the original coordinates and redaction spans
  are declared over them too, so hits and redactions line up.
- **Fail closed.** An unknown language raises rather than borrowing English rules. A lexicon whose
  language no turn speaks raises rather than returning zero hits, because a false absence reads as
  a compliance breach. An empty requirement set is never `all_satisfied`.
- **Overlapping redactions are refused, not merged.** Two detectors disagreeing is a real
  condition for the caller to resolve.

## License

Apache-2.0.
