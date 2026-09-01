# FAQ index

Answers to the questions different teams ask about this kit. It is a **shared kernel** pinned by
eight repositories, not a service you deploy, so these pages are shorter and narrower than the
equivalents in a service repo: most of what a reviewer wants to know about a deployment is a
question for the repo that binds this, not for this.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | what this touches, what it never touches, redaction, supply chain |
| [portability-faq.md](portability-faq.md) | Architecture | zero dependencies, no clock, no I/O, and why that is enforced |
| [features-faq.md](features-faq.md) | Product / compliance | what it decides, what it refuses to decide, the kernel-versus-lexicon line |
| [adoption-faq.md](adoption-faq.md) | Engineering leads consuming it | pinning, binding, locales, contributing back |
| [compliance-faq.md](compliance-faq.md) | Compliance / second line | what a match means, what ABSENT means, and what neither means |

**The one thing to read first** is the kernel-versus-lexicon line in
[`../ADOPTING.md`](../ADOPTING.md). This package carries the matching and not a single phrase,
and almost every question about it resolves to which side of that line something sits on.

Authority order: [`../../README.md`](../../README.md), then [`../../AGENTS.md`](../../AGENTS.md).
These pages restate; they do not decide.
