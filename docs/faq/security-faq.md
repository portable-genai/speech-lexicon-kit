# Security FAQ

### What does this package touch?

Text, in memory, that the caller hands it. It holds no credentials, opens no sockets, reads no
files and constructs no clients. Audio is a URI (`AudioRef`) for the consumer's adapter to
resolve.

### So where is the security surface?

Almost entirely in the consuming repo: who may resolve an `AudioRef`, who may read a transcript,
and what the adapters authenticate as. The kit's own surface is the correctness of normalisation
and matching, which is a **compliance** risk more than a confidentiality one: a missed disclosure
is a wrong answer, not a leak.

### What about personal data?

Transcripts contain it, so `RedactionSpan` and `redaction.py` carry the shapes for masking one.
The kit provides the mechanism; WHICH spans must be masked, in which jurisdiction, is the
consumer's policy. Nothing here writes a transcript anywhere, so there is no store to protect.

### What about supply chain?

Zero runtime dependencies is the strongest form of the answer: there is no transitive tree to
audit. The dev extra is pinned in `requirements-dev.lock` and `make lock` recompiles it.
Consumers pin this package by COMMIT rather than by tag, because a movable pin would let the
meaning of "was the disclosure read?" change under a repository that did not change.

### What is deliberately out of scope?

Recognition, synthesis, diarization, storage, transport, identity and authorisation. All of them
are ports or the consumer's job.
