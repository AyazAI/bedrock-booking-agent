from __future__ import annotations

import hashlib
import math
import re

_STOP = frozenset(
    "a an the you your are is do i me my we our what when where how can please "
    "of to for on at and or it this that with".split()
)


def tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if token not in _STOP and len(token) > 1
    ]


def embed(text: str, dims: int = 256) -> list[float]:
    """Signed feature hash. Offline stand-in for a hosted embedding model."""

    vector = [0.0] * dims
    for token in tokenize(text):
        digest = hashlib.blake2s(token.encode(), digest_size=8).digest()
        number = int.from_bytes(digest, "little")
        index = number % dims
        sign = 1.0 if (number >> 8) & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    return float(sum(a * b for a, b in zip(left, right, strict=True)))
