# Portability FAQ

### What is the lock-in surface?

None. **Pure standard library, zero runtime dependencies, no clock, no I/O.** That is not an
aspiration in a README, it is the reason the package installs and runs on an air-gapped host and
an offline test profile needs no network.

### How is that enforced rather than described?

`make gate` runs ruff, format check, mypy strict over `src`, the suite and the golden replay,
entirely offline. A dependency, a `datetime.now()` or a file read would have to survive that gate
and the review of `AGENTS.md`, which names both rules explicitly.

Since 2026-09-01 the gate also runs in hosted CI. It did not before: the kit is not a catalog
system, so it had no policy entry and nothing ran its 162 tests.

### Why does every function take `as_of`?

So replay is exact. A kernel that read a clock would make every consumer's replay digest depend
on when it ran, and the digest exists precisely so a re-run can be shown to be the same run.

### Why is audio a URI rather than bytes?

Because resolving it, and deciding who may resolve it, is the consuming repo's decision and its
security boundary. `AudioRef` keeps this package from ever holding media or credentials.

### How do we stop depending on it?

Copy the modules you use. It is standard library only, so there is nothing to unpick: the ports
are Protocols, the types are dataclasses, and the matching is text processing. That is a
deliberate property of a shared kernel, not an accident.
