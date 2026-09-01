# Features FAQ

### What does it actually do?

Five things, and nothing above them:

1. **Ports** for speech-to-text, text-to-speech and diarization, as `typing.Protocol`. Adapters
   live in the consuming repo; the kit never reaches a recogniser.
2. **Transcript types**: `Transcript`, `SpeakerTurn`, `WordOffset`, `ChannelRole`,
   `SpeakerSegment`, plus `span_timing` and `merge_diarization`.
3. **Locale-sensitive normalisation**: `normalise`, `rules_for`, `SUPPORTED_LOCALES`.
4. **Phrase matching**: `Lexicon`, `PhraseSpec`, `MatchMode`, `find_hits`, `find_matches`, each
   hit carrying where in the transcript it was found.
5. **Ordered-phrase adherence**: `PhraseSequenceRequirement`, `evaluate_requirements`,
   `ordered_hit_chain`, and a replay digest so a re-run can be shown to be the same run.

### Why does it exist at all?

Because three systems already had to agree on what "the agent read the recording disclosure at
00:12 of turn 4" means, and several more are coming. Left alone, each writes its own
`text.lower().strip()` and they disagree: one finds the disclosure inside `reinsurance`, one
misses it because the recogniser emitted full-width digits, and the Japanese one misses it
because there are no spaces to split on. **A compliance answer that depends on which repo asked
is not an answer.**

### What will it refuse to do?

- **Carry a phrase.** Not one. A required wording is reviewed vertical policy on a per-market
  schedule; here it would make eight repositories wait on one legal team.
- **Decide which requirement applies** to which product, market or severity.
- **Decide what an ABSENT step costs.** It reports that an ordered step was not satisfied on a
  closed transcript. Whether that is a coaching note or a reportable breach is the consumer's.
- **Read a clock or perform I/O.** Every function that needs a time takes `as_of` from the
  caller, and audio is referenced by URI for an adapter to resolve.

### What does a "hit" mean, exactly?

That the normalised phrase was found in the normalised transcript under the `MatchMode` you
chose, at a cited position. It does not mean the phrase was *understood*, that it was said by the
right party unless you constrained the channel, or that it satisfied a regulator. The citation is
the point: a hit you cannot locate in the transcript is not evidence.

### Who uses it?

Eight repositories pin it today. Conversation-facing systems are the natural consumers: contact
centre, conversation QA, trade communications surveillance, meeting capture.
