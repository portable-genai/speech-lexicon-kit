# Adopting this kit

This repository is a **shared kernel**, not a service base. Eight repositories in this portfolio
pin it, and you adopt it the way you adopt any library: you depend on it, you bind its ports in
your own repo, and you keep your phrases out of it.

That last point is the whole design, so it is the first thing here rather than a footnote.

> Related reading: the [`faq/`](faq/) directory, [`../README.md`](../README.md) (the surface),
> [`../AGENTS.md`](../AGENTS.md) (the rules a change to this kit must hold).

---

## 1. The line: kernel here, lexicons in your repo

| Here | In your repo |
|---|---|
| Ports, transcript types, normalisation, matching, adherence, replay digests | The phrases themselves: disclosure wordings, scam cues, market-abuse lexicons, meeting-commitment cues |
| How a match is found and cited | Which requirement applies to which product, market and severity |
| That an unsatisfied step on a closed transcript is ABSENT | What an ABSENT step costs on a scorecard |

A required wording is reviewed vertical policy on a per-market schedule. If it lived here,
changing one disclosure would mean releasing a shared package and bumping every consumer. **If
you find yourself wanting to add a phrase to this kit, that is the signal you are about to make
eight repositories wait on your legal team.** Put it in a `Lexicon` in your own repo.

## 2. Depending on it

Pin it by COMMIT, not by tag, the way every consumer in this portfolio does:

```toml
dependencies = [
  "speech-lexicon-kit @ git+https://github.com/portable-genai/speech-lexicon-kit@<40-char-sha>",
]
```

A tag is movable, and a movable pin means the meaning of "was the disclosure read?" can change
under a repository that did not change. Recompile your lockfile after any bump.

## 3. What you have to supply

The kit carries no I/O and no clock. It is pure standard library with zero runtime dependencies,
which is what lets it install on an air-gapped host and run in an offline test profile.

1. **Adapters for the three ports.** `SpeechToTextPort`, `TextToSpeechPort` and
   `DiarizationPort` are `typing.Protocol`, and the adapters live in YOUR repo, in your own
   profile families. The kit never reaches a recogniser.
2. **Audio resolution.** Audio is referenced by `AudioRef`, a URI. Resolving it, and deciding
   what a caller may resolve, is yours.
3. **`as_of`, every time.** Every function that needs a time takes it from the caller. There is
   no clock in here, so replay is exact and a test never depends on when it ran.
4. **Your lexicons and requirements.** `Lexicon`, `PhraseSpec` and
   `PhraseSequenceRequirement` are the shapes; the contents are yours, and they are reviewed
   policy rather than code.

## 4. The decisions the kit deliberately leaves you

1. **Locale coverage.** `SUPPORTED_LOCALES` and `rules_for` decide how text is normalised before
   matching. The failure this kit exists to prevent is locale-shaped: a recogniser emitting
   full-width digits, or a language with no spaces to split on, makes a naive
   `text.lower().strip()` miss a disclosure that was actually read. Confirm the locales you
   operate in are covered before you rely on a match, and treat an unlisted locale as a gap
   rather than a default.
2. **Match mode.** `MatchMode` decides how strict a hit is. A substring match finds the
   disclosure inside `reinsurance`; a stricter mode does not. Choose per requirement, not once
   globally.
3. **What ABSENT costs.** The kit reports that an ordered step was not satisfied on a closed
   transcript. It does not decide whether that is a coaching note or a reportable breach.
4. **Redaction policy.** `RedactionSpan` and `redaction.py` carry the shapes for masking a
   transcript. WHICH spans must be masked, in which jurisdiction, is yours.
5. **Replay digests.** `replay.py` gives you a stable digest of a transcript and its matches, so
   a re-run can be shown to be the same run. Storing and comparing those digests is your
   pipeline's job.

## 5. Contributing back

Read [`../AGENTS.md`](../AGENTS.md) first. Two rules matter more than the rest:

- **No phrase, ever.** See section 1.
- **No clock and no I/O.** A single `datetime.now()` or file read in here would break the
  air-gapped install and make every consumer's replay non-deterministic.

The gate is `make gate`: ruff, format check, mypy strict over `src`, the test suite and the
golden replay. It runs offline, because the package has no runtime dependency, no network call
and no clock, so a green gate on a disconnected host means what it means anywhere else. Since
2026-09-01 it also runs in hosted CI, which it did not before: the kit is not a catalog system,
so nothing had registered it.

## 6. Adoption checklist

- [ ] Pinned by commit, not by tag, and recompiled your lockfile.
- [ ] Bound all three ports in your own adapter families.
- [ ] Confirmed your operating locales are in `SUPPORTED_LOCALES`.
- [ ] Chose a `MatchMode` per requirement rather than once globally.
- [ ] Kept every phrase and every requirement in your repo, not in a fork of this one.
- [ ] Decided what an ABSENT ordered step costs, in your scorecard and not here.
- [ ] Wired `as_of` from your caller everywhere, so replay stays exact.
