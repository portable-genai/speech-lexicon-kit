# Compliance FAQ

### What does a match prove?

That the normalised phrase was found in the normalised transcript, under the `MatchMode` the
consumer chose, at a **cited** position. That is all, and the citation is the load-bearing part:
a hit that cannot be located in the transcript is not evidence.

It does not prove the phrase was understood, that it was said by the right party unless the
channel was constrained, or that a regulator would accept it.

### What does ABSENT mean?

That an ordered step in a `PhraseSequenceRequirement` was not satisfied on a **closed**
transcript. Closed matters: an unsatisfied step on an open transcript is not yet a finding.

What ABSENT COSTS is deliberately not decided here. Whether it is a coaching note or a reportable
breach is vertical policy in the consuming repo.

### Who owns the required wordings?

You do. This package carries the matching and not a single phrase, precisely so that changing a
disclosure is a change in one vertical rather than a shared release that eight repositories wait
on.

### Is a result reproducible?

Yes, and that is enforced structurally rather than promised. There is no clock in this package:
every function that needs a time takes `as_of` from the caller. `replay.py` gives a stable digest
of a transcript and its matches, so a re-run can be shown to be the same run. Storing and
comparing those digests is the consumer's pipeline.

### What about personal data in transcripts?

`RedactionSpan` carries the shape for masking. The policy, which spans and which jurisdiction, is
yours. Nothing here persists a transcript.

### What model risk is there?

None in this package: it contains no model. Normalisation and matching are deterministic text
processing. The model risk in a conversation-facing system lives in the recogniser behind
`SpeechToTextPort` and in whatever the consuming repo does with the result. A recogniser that
mis-transcribes produces a correct match against wrong text, and this kit cannot detect that.
