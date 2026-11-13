from __future__ import annotations

import hashlib
import random
import re

from risk_app.content import CASES


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{3,31}$")


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def normalize_code(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch(normalize_email(value)))


def valid_code(value: str) -> bool:
    return bool(CODE_RE.fullmatch(normalize_code(value)))


def assign_cases(participant_code: str) -> list[int]:
    """Assign two distinct cases reproducibly from the participant code."""
    normalized = normalize_code(participant_code)
    seed = int.from_bytes(hashlib.sha256(normalized.encode("utf-8")).digest()[:8], "big")
    generator = random.Random(seed)
    return generator.sample(sorted(CASES), 2)

