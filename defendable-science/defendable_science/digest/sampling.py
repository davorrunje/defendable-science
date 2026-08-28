"""Which papers the human checks — deterministically (spec §8, §3.5).

Extraction's honesty claim rests on one thing: a human verified a sample of the
extracted cells against the actual sources. That check is only worth anything if
the sample cannot be steered, so selection is **seeded from the batch itself**:
the same set of citekeys always draws the same papers, in this process and in
every future one. A freshly-random draw per run would let anyone re-roll until
an easy sample came up, and the run would look identical from the outside.

The seed is a SHA-256 of the sorted citekeys, never Python's `hash()`:
`hash()` on a `str` is salted per interpreter (``PYTHONHASHSEED``), so a
`hash()`-seeded draw changes on every invocation while passing every
same-process test. That failure mode is silent, which is precisely why it is
ruled out here rather than left to review.

Pure: no filesystem, no clock, no config. Membership of the batch is resolved by
the caller (``digest extract sample``); this module only draws from it.
"""

from __future__ import annotations

import hashlib
import random
from math import ceil

from defendable_science.digest.extraction import ExtractionError

#: Floor on the sample size. A convention, not a statistical guarantee — the
#: spec says so plainly (§14), and `digest extract sample --size` exists so a
#: real survey can calibrate it rather than inherit this guess.
MIN_SAMPLE_SIZE = 3

#: The batch fraction sampled above the floor: ``max(3, 10%)``.
SAMPLE_DIVISOR = 10


def default_size(n: int) -> int:
    """Return the conventional sample size for a batch of `n` papers.

    ``max(3, 10%)``, never more than the batch itself.

    :param n: How many papers are in the batch.
    :returns: The number of papers to draw.
    """
    return min(n, max(MIN_SAMPLE_SIZE, ceil(n / SAMPLE_DIVISOR)))


def _seed(citekeys: list[str]) -> int:
    """Derive the draw's seed from an already-sorted, de-duplicated batch.

    :param citekeys: The batch, sorted and unique.
    :returns: The seed for `random.Random`.
    """
    return int.from_bytes(
        hashlib.sha256("\n".join(citekeys).encode("utf-8")).digest(), "big"
    )


def select_sample(citekeys: list[str], size: int) -> list[str]:
    """Draw the batch's checked sample — the same papers, every time.

    Duplicates are collapsed and the population is sorted before seeding, so the
    draw depends on the *set* of papers and nothing else: not the order they
    were listed in, not the process they were drawn in.

    :param citekeys: The batch's citekeys, in any order.
    :param size: How many to draw; clamped to the batch size, so a batch smaller
        than the sample is checked whole.
    :returns: The drawn citekeys, sorted for a stable report.
    :raises ExtractionError: If the batch is empty, or `size` is below one —
        either would report "sampled, nothing to check" for a run in which
        nothing was checked, which is the one thing this command must never say.
    """
    population = sorted(set(citekeys))
    if not population:
        raise ExtractionError(
            "an empty batch has no sample; there is nothing to check — name the "
            "papers with --citekey, or extract some first"
        )
    if size < 1:
        raise ExtractionError(
            f"sample size must be at least 1, got {size} — a sample of none is "
            "an unchecked batch, not a checked one"
        )
    # Deterministic by design: this PRNG is a reproducible selector, not a
    # source of unpredictability.
    drawn = random.Random(_seed(population)).sample(
        population, min(size, len(population))
    )
    return sorted(drawn)
