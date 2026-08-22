"""Locale-sensitive deterministic normalisation, with an exact map back to the source.

This is the module the rest of the package is built on, and the reason the package exists as
a shared kit rather than a snippet per repo. Matching a required phrase against a speech
transcript is not string equality: the recogniser emits full-width digits, stray punctuation,
inconsistent casing, and in Japanese no spaces at all and an unstable choice between hiragana
and katakana. Every consumer that writes its own ``text.lower().replace(...)`` gets a
slightly different answer, and "did the agent read the disclosure?" then depends on which
repo asked.

Two properties make the output usable as evidence:

* **Determinism.** Normalisation is a pure function of ``(text, rules)``. No clock, no
  locale-dependent library call, no dictionary iteration order. The same input yields the
  same output byte for byte, on any host, under any hash seed.
* **Traceability.** :class:`NormalisedText` carries, for every normalised character, the
  half-open source range it came from. A match found in normalised space therefore reports a
  character span in the ORIGINAL turn text, which is what a citation has to be.

Locale resolution fails closed on an unknown LANGUAGE (``zh``, ``ko``, ``th`` need
segmentation rules this package does not have) but resolves any region of a known language,
because English rules genuinely do apply to ``en-NZ``. A consumer with its own language can
construct a :class:`LocaleRules` and pass it directly; it is never guessed.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

__all__ = [
    "ENGLISH_RULES",
    "JAPANESE_RULES",
    "SUPPORTED_LOCALES",
    "LocaleRules",
    "NormalisedText",
    "UnsupportedLocaleError",
    "canonical_locale",
    "normalise",
    "rules_for",
]

_LOCALE_RE = re.compile(
    r"^(?P<lang>[A-Za-z]{2,3})"
    r"(?:-(?P<script>[A-Za-z]{4}))?"
    r"(?:-(?P<region>[A-Za-z]{2}|[0-9]{3}))?$"
)

# Half-width voiced / semi-voiced sound marks. They are not combining characters by
# unicodedata's reckoning, yet NFKC composes them with the preceding kana, so they must be
# grouped with their base or the mapping back to the source splits a single glyph in two.
_HALFWIDTH_VOICING = frozenset("ﾞﾟ")

# Typographic dashes a recogniser substitutes for the katakana prolonged sound mark. Folded to
# U+30FC under Japanese rules only; in English they are ordinary punctuation.
#
# ASCII hyphen-minus is deliberately NOT in this set. It is the separator inside a phone
# number or a reference code, so folding it would turn "03-1234-5678" into a katakana string;
# left out, it is dropped as punctuation like any other separator. The full-width and
# half-width forms are absent for a different reason: NFKC has already resolved them by the
# time this map is applied.
#
# The prolonged mark itself is KEPT rather than dropped, even though its presence is the
# unstable thing. Dropping it would collide genuinely different words (biru / biiru), and a
# matcher that silently equates two different words is worse than one that misses a
# mis-transcription.
#
# Written as escapes rather than literals: these code points are data, and several of them are
# visually indistinguishable from each other and from the ASCII hyphen in an editor.
# U+2010 hyphen, U+2011 non-breaking hyphen, U+2012 figure dash, U+2013 en dash, U+2014 em
# dash, U+2015 horizontal bar, U+2212 minus sign.
_PROLONGED_SOURCES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_PROLONGED_MAP = {ord(ch): "ー" for ch in _PROLONGED_SOURCES}

# Hiragana U+3041..U+3096 map to katakana by a fixed +0x60 offset, and the two iteration
# marks by the same offset. Folding one way (to katakana) makes the choice arbitrary but
# fixed, which is all determinism needs.
_KANA_MAP: dict[int, str] = {cp: chr(cp + 0x60) for cp in range(0x3041, 0x3097)}
_KANA_MAP.update({0x309D: "ヽ", 0x309E: "ヾ"})


class UnsupportedLocaleError(LookupError):
    """Raised when no normalisation rules are registered for a locale's language."""


@dataclass(frozen=True, slots=True)
class LocaleRules:
    """How one language's text is folded before matching.

    ``word_separated`` is the consequential flag. In a word-separated language a phrase match
    must land on token boundaries, so "insurance" must not match inside "reinsurance", and
    dropped punctuation becomes a separator so "co-operate" and "co operate" agree. In a
    language written without spaces, boundary checking would reject every true match, so
    separators are removed entirely and matching is over the character run.
    """

    language: str
    word_separated: bool
    casefold: bool = True
    fold_kana: bool = False
    fold_prolonged_sound_marks: bool = False
    drop_punctuation: bool = True

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("LocaleRules.language must be non-empty")


ENGLISH_RULES = LocaleRules(language="en", word_separated=True)
"""Rules for English in any region: NFKC, casefold, punctuation to separators, token boundaries."""

JAPANESE_RULES = LocaleRules(
    language="ja",
    word_separated=False,
    fold_kana=True,
    fold_prolonged_sound_marks=True,
)
"""Rules for Japanese: NFKC (which folds half-width kana and full-width digits), hiragana
folded to katakana, dash-like characters folded to the prolonged sound mark, and all
separators removed because whitespace in a Japanese transcript is recogniser noise rather
than a token boundary."""

_RULES_BY_LANGUAGE: dict[str, LocaleRules] = {
    "en": ENGLISH_RULES,
    "ja": JAPANESE_RULES,
}

SUPPORTED_LOCALES: tuple[str, ...] = (
    "en-AU",
    "en-GB",
    "en-HK",
    "en-IN",
    "en-SG",
    "en-US",
    "ja-JP",
)
"""The locale tags in scope for this release, and the ones the golden replay pins.

Any other region of a supported language resolves to the same language rules; an unsupported
language raises rather than silently borrowing English behaviour.
"""


def canonical_locale(tag: str) -> str:
    """Return ``tag`` in canonical BCP 47 casing (``ja_jp`` and ``JA-jp`` both give ``ja-JP``).

    Raises :class:`UnsupportedLocaleError` on a malformed tag, so a typo is a boot failure
    rather than a locale that quietly matches nothing.
    """
    cleaned = tag.strip().replace("_", "-")
    match = _LOCALE_RE.match(cleaned)
    if match is None:
        raise UnsupportedLocaleError(
            f"{tag!r} is not a well-formed locale tag (expected forms like 'en-SG' or 'ja-JP')"
        )
    parts = [match.group("lang").lower()]
    script = match.group("script")
    if script:
        parts.append(script.title())
    region = match.group("region")
    if region:
        parts.append(region.upper())
    return "-".join(parts)


def rules_for(locale: str) -> LocaleRules:
    """Resolve the normalisation rules for a locale tag.

    Resolution is by LANGUAGE subtag, so every English region shares one rule set. An
    unregistered language raises: normalising Korean or Thai with English rules would produce
    matches that look plausible and are not, and a wrong hit in a compliance scorecard is
    worse than a refusal.
    """
    canonical = canonical_locale(locale)
    language = canonical.split("-", 1)[0]
    rules = _RULES_BY_LANGUAGE.get(language)
    if rules is None:
        known = ", ".join(sorted(_RULES_BY_LANGUAGE))
        raise UnsupportedLocaleError(
            f"no normalisation rules for language {language!r} (from locale {locale!r}); "
            f"registered languages are: {known}. Construct a LocaleRules and pass it "
            f"explicitly rather than borrowing another language's folding."
        )
    return rules


@dataclass(frozen=True, slots=True)
class NormalisedText:
    """Normalised text plus the exact source range behind each normalised character.

    ``source_starts[i]`` and ``source_ends[i]`` bracket the characters of the ORIGINAL string
    that produced normalised character ``i``. One source character may produce several
    normalised ones (NFKC expansion, casefolding) and several may produce one (a run of
    whitespace collapsing to a single separator), so a per-character pair is the only mapping
    that stays exact in both directions.
    """

    text: str
    source_starts: tuple[int, ...]
    source_ends: tuple[int, ...]
    source_length: int
    rules: LocaleRules

    def __post_init__(self) -> None:
        if len(self.source_starts) != len(self.text) or len(self.source_ends) != len(self.text):
            raise ValueError(
                "NormalisedText offset tables must have one entry per normalised character"
            )

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a half-open span in normalised space back to the original text.

        An empty span maps to a zero-width point at the corresponding source position, which
        keeps the result a valid span rather than an inverted one.
        """
        if start < 0 or end < start or end > len(self.text):
            raise ValueError(
                f"span [{start}, {end}) is out of range for {len(self.text)} normalised characters"
            )
        if start == end:
            point = self.source_starts[start] if start < len(self.text) else self.source_length
            return (point, point)
        return (self.source_starts[start], self.source_ends[end - 1])

    def is_boundary(self, position: int) -> bool:
        """True when ``position`` is a token boundary under these rules.

        In a language without word separators every position is a boundary, which is the
        deliberate consequence of there being no tokens to bound.
        """
        if not self.rules.word_separated:
            return True
        if position <= 0 or position >= len(self.text):
            return True
        return self.text[position - 1] == " " or self.text[position] == " "


def _clusters(text: str) -> list[tuple[str, int, int]]:
    """Split ``text`` into base-plus-marks clusters, each with its source range.

    NFKC is applied per cluster rather than to the whole string so that the mapping back to
    the source stays exact. Grouping combining marks (and the half-width voicing marks) with
    their base is what makes that safe: half-width KA followed by a voicing mark is one glyph
    to NFKC, and normalising it in isolation from its base would leave a stray mark behind.
    """
    out: list[tuple[str, int, int]] = []
    length = len(text)
    index = 0
    while index < length:
        end = index + 1
        while end < length and (
            unicodedata.combining(text[end]) != 0 or text[end] in _HALFWIDTH_VOICING
        ):
            end += 1
        out.append((text[index:end], index, end))
        index = end
    return out


def _is_separator(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch).startswith("Z")


def _is_droppable_punctuation(ch: str) -> bool:
    return unicodedata.category(ch)[0] in {"P", "S"}


def normalise(text: str, locale: str | LocaleRules) -> NormalisedText:
    """Fold ``text`` for matching under ``locale``, keeping an exact map to the source.

    The pipeline, in fixed order: cluster the source, NFKC each cluster, casefold, fold kana
    and prolonged sound marks where the rules ask for it, then reduce separators. Punctuation
    becomes a separator in a word-separated language (so it cannot weld two tokens together)
    and is dropped outright otherwise. Leading and trailing separators are removed and runs
    collapse to a single space, so a phrase normalised by this same function can be found by
    plain substring search.
    """
    rules = locale if isinstance(locale, LocaleRules) else rules_for(locale)
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    pending: tuple[int, int] | None = None

    for cluster, cluster_start, cluster_end in _clusters(text):
        piece = unicodedata.normalize("NFKC", cluster)
        if rules.casefold:
            piece = piece.casefold()
        if rules.fold_prolonged_sound_marks:
            piece = piece.translate(_PROLONGED_MAP)
        if rules.fold_kana:
            piece = piece.translate(_KANA_MAP)
        for ch in piece:
            separator = _is_separator(ch) or (
                rules.drop_punctuation and _is_droppable_punctuation(ch)
            )
            if separator:
                if pending is None:
                    pending = (cluster_start, cluster_end)
                continue
            if pending is not None:
                if chars and rules.word_separated:
                    chars.append(" ")
                    starts.append(pending[0])
                    ends.append(pending[1])
                pending = None
            chars.append(ch)
            starts.append(cluster_start)
            ends.append(cluster_end)

    return NormalisedText(
        text="".join(chars),
        source_starts=tuple(starts),
        source_ends=tuple(ends),
        source_length=len(text),
        rules=rules,
    )
