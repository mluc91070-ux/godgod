"""The statistics the experiment engine needs, implemented explicitly.

No SciPy: these are three formulas, and writing them out means the numbers in
a published result can be checked by reading this file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@dataclass(frozen=True)
class ProportionTest:
    rate_a: float
    rate_b: float
    difference: float
    z: float | None
    p_value: float | None
    n_a: int
    n_b: int

    @property
    def difference_pp(self) -> float:
        return round(self.difference * 100, 2)


def two_proportion_test(
    successes_a: int, n_a: int, successes_b: int, n_b: int
) -> ProportionTest:
    """Two-sided z-test on two proportions.

    Returns `z=None` when the pooled variance is zero or a group is empty:
    an undefined statistic is reported as undefined, not as 0.
    """
    if n_a <= 0 or n_b <= 0:
        return ProportionTest(0.0, 0.0, 0.0, None, None, n_a, n_b)

    rate_a = successes_a / n_a
    rate_b = successes_b / n_b
    difference = rate_a - rate_b

    pooled = (successes_a + successes_b) / (n_a + n_b)
    variance = pooled * (1 - pooled) * (1 / n_a + 1 / n_b)
    if variance <= 0:
        return ProportionTest(rate_a, rate_b, difference, None, None, n_a, n_b)

    z = difference / math.sqrt(variance)
    p_value = 2 * (1 - normal_cdf(abs(z)))
    return ProportionTest(
        rate_a=round(rate_a, 4),
        rate_b=round(rate_b, 4),
        difference=round(difference, 4),
        z=round(z, 4),
        p_value=round(p_value, 4),
        n_a=n_a,
        n_b=n_b,
    )


def cohens_h(rate_a: float, rate_b: float) -> float:
    """Effect size for two proportions. Independent of sample size."""
    phi = lambda rate: 2 * math.asin(math.sqrt(max(0.0, min(1.0, rate))))  # noqa: E731
    return round(phi(rate_a) - phi(rate_b), 4)
