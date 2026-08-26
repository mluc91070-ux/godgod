"""Deterministic checks every model-written sentence must survive.

A model is allowed to choose words. It is not allowed to choose facts. These
checks run on the model's output before anything is stored, and a draft that
fails them is not saved — it is recorded as a failed run with the reasons.

The important one is `ungrounded_numbers`: every number in a draft must appear
in the row it claims to describe. That is the mechanical form of the project's
one rule, and it does not depend on the model behaving.

**Register is not policed here; claims are.** Slang, jokes and crypto-native
phrasing pass. "bullish", a price target and "you should buy" do not, because
those assert something no experiment ran. The line is not how it sounds — it is
whether the sentence claims more than the data supports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_DRAFT_CHARS = 280
"""One post. Longer than this is not a draft, it is an essay."""

MARKET_CLAIMS = (
    "bullish",
    "bearish",
    "to the moon",
    "moon shot",
    "next 100x",
    "100x",
    "guaranteed",
    "price target",
    "buy now",
    "sell now",
    "financial advice",
    "not financial advice",
)
"""Claims about where a price is going, or advice about acting on it.

Banned regardless of register. These are not style — each one asserts
something no experiment here has ever tested, and a disclaimer glued to the end
does not make the sentence true.
"""

VOICE_FAILURES = (
    "as an ai",
    "as a language model",
    "hey everyone",
    "in conclusion",
    "it is important to note",
)
"""Not slang — the opposite. An assistant apologising for existing."""

ADVICE_PATTERNS = (
    re.compile(r"\byou should (buy|sell|hold|swap|ape)\b", re.I),
    re.compile(r"\b(will|going to) (pump|dump|moon|crash)\b", re.I),
    re.compile(r"\bprice (will|should|could) (go|reach|hit)\b", re.I),
)

LINK = re.compile(r"https?://|\bwww\.", re.I)

CERTAINTY = (
    re.compile(r"\bprove[sdn]?\b", re.I),
    re.compile(r"\bconfirms?\b", re.I),
    re.compile(r"\bcertain(ly)?\b", re.I),
    re.compile(r"\balways\b", re.I),
    re.compile(r"\bnever fails\b", re.I),
)
"""An INCONCLUSIVE result described with certainty is a fabricated finding."""

NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> list[str]:
    """Every numeric token, normalised so 1,234 and 1234 compare equal."""
    return [match.group(0).replace(",", "") for match in NUMBER.finditer(text)]


def _variants(value: object) -> set[str]:
    """The written forms a number may legitimately take in a sentence."""
    forms: set[str] = set()
    if isinstance(value, bool) or value is None:
        return forms
    if isinstance(value, int | float):
        number = float(value)
        for candidate in (number, abs(number)):
            forms.add(f"{candidate:g}")
            for places in (0, 1, 2, 3, 4):
                forms.add(f"{candidate:.{places}f}")
        # A rate of 0.42 is honestly written as 42%. Two decimals included
        # because the check exists to catch invented numbers, not real ones
        # stated more precisely — 0.911764 written as 91.18% is the truth, and
        # rejecting it taught the writer to be vaguer than the data.
        if 0.0 <= abs(number) <= 1.0:
            for places in (0, 1, 2):
                forms.add(f"{abs(number) * 100:.{places}f}")
        forms.add(f"{round(number)}")
    else:
        forms.update(numbers_in(str(value)))
    return {form.rstrip(".") for form in forms}


def grounded_forms(facts: dict[str, object]) -> set[str]:
    """Every number the draft is allowed to contain."""
    allowed: set[str] = set()
    for value in facts.values():
        if isinstance(value, dict):
            allowed |= grounded_forms(value)
        elif isinstance(value, list | tuple):
            allowed |= grounded_forms(dict(enumerate(value)))
        else:
            allowed |= _variants(value)
    return allowed


def ungrounded_numbers(text: str, facts: dict[str, object]) -> list[str]:
    """Numbers in the draft that do not appear in the row it describes."""
    allowed = grounded_forms(facts)
    missing = []
    for token in numbers_in(text):
        normalised = token.rstrip(".")
        if normalised in allowed:
            continue
        try:
            if f"{float(normalised):g}" in allowed:
                continue
        except ValueError:
            pass
        missing.append(token)
    return missing


@dataclass
class DraftCheck:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reasons": self.reasons}


def check_draft(text: str, facts: dict[str, object], *, outcome: str | None = None) -> DraftCheck:
    """Everything that can be checked without asking anyone's opinion."""
    reasons: list[str] = []
    stripped = text.strip()

    if not stripped:
        reasons.append("the draft is empty")
    if len(stripped) > MAX_DRAFT_CHARS:
        reasons.append(f"{len(stripped)} characters, over the {MAX_DRAFT_CHARS} limit")

    lowered = f" {stripped.lower()} "
    for phrase in MARKET_CLAIMS:
        if phrase in lowered:
            reasons.append(f"claims something about price: {phrase.strip()!r}")
    for phrase in VOICE_FAILURES:
        if phrase in lowered:
            reasons.append(f"reads as an assistant, not as itself: {phrase.strip()!r}")

    for pattern in ADVICE_PATTERNS:
        if pattern.search(stripped):
            reasons.append("reads as financial advice or a price prediction")
            break

    if LINK.search(stripped):
        reasons.append("contains a link; drafts cite rows, not urls")

    ungrounded = ungrounded_numbers(stripped, facts)
    if ungrounded:
        reasons.append(f"numbers not present in the result: {', '.join(ungrounded)}")

    if outcome in {"INCONCLUSIVE", "REJECTED"}:
        for pattern in CERTAINTY:
            if pattern.search(stripped):
                reasons.append(
                    f"claims certainty about a result recorded as {outcome.lower()}"
                )
                break

    if stripped != stripped.lower():
        # The voice is lowercase. This is cosmetic, and it is also the cheapest
        # signal that the model ignored its instructions.
        reasons.append("contains uppercase; the voice is lowercase")

    return DraftCheck(ok=not reasons, reasons=reasons)
