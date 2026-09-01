# Adoption FAQ

The full walkthrough is [`../ADOPTING.md`](../ADOPTING.md); this answers what comes up first.

### How do we depend on it?

Pin by commit, never by tag:

```toml
"speech-lexicon-kit @ git+https://github.com/portable-genai/speech-lexicon-kit@<40-char-sha>"
```

A tag is movable, and a movable pin lets the meaning of "was the disclosure read?" change under a
repository that did not change. Recompile your lockfile after any bump.

### Can we add our phrases here?

No, and the surface is designed so you never have to. A required wording is reviewed policy on a
per-market schedule; here it would make eight repositories wait on one legal team every time a
disclosure changed. Put phrases in a `Lexicon` in your repo.

### What do we have to build?

Adapters for the three ports, audio resolution behind `AudioRef`, your lexicons and
requirements, and an `as_of` from your caller on every call that needs a time.

### Our locale is not in SUPPORTED_LOCALES. Now what?

Treat it as a gap, not a default. Locale handling is the whole reason this kernel exists: a naive
lowercase-and-strip misses a disclosure that was genuinely read when the recogniser emits
full-width digits, or when the language has no spaces to split on. Add the locale rules here (the
rules are kernel, unlike phrases) with tests, or do not claim coverage for that market.

### Which MatchMode should we use?

Per requirement, not once globally. A substring match finds the disclosure inside `reinsurance`.

### Does the gate run for a fork?

`make gate` runs offline anywhere. Hosted CI is registered for THIS repository in
`org-metadata/ci/gcp/repository-policy.json`; a fork gets no trigger and no required check unless
it is registered too, and nothing reports the omission.

### What is still open?

The kit is complete for what it claims. The honest caveat is coverage rather than correctness:
`SUPPORTED_LOCALES` is a finite list, and a market outside it is unserved rather than
approximated.
