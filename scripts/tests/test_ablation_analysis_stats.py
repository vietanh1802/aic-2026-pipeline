# scripts/tests/test_ablation_analysis_stats.py
"""The statistics behind every table: checked against values worked out by hand, not against themselves."""
import math
import os
import sys

import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ablation_analysis import stats  # noqa: E402


def test_wilson_matches_hand_values() :
    low, high = stats.wilson(5, 10)        # p = 0.5, n = 10: (0.2366, 0.7634) by the closed form
    assert (round(low, 3), round(high, 3)) == (0.237, 0.763)
    low, high = stats.wilson(0, 28)        # never below 0; upper end z^2 / (n + z^2) = 3.84 / 31.84 = 0.1207
    assert low == 0.0 and round(high, 3) == 0.121
    assert math.isnan(stats.wilson(0, 0)[0])
    assert round(stats.half_width_at_half(86), 3) == 0.103   # 1.96 * sqrt(0.25 / 86 + 3.84 / (4 * 86^2)) / (1 + 3.84 / 86) = 0.1034
    assert round(stats.half_width_at_half(28), 3) == 0.174   # same formula at n = 28 gives 0.1737


def test_mcnemar_exact_is_the_two_sided_binomial_tail() :
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert stats.mcnemar_exact(0, 5) == pytest.approx(2 * (1 / 32))          # 2 * P(X = 0), n = 5
    assert stats.mcnemar_exact(1, 9) == pytest.approx(2 * (1 + 10) / 1024)   # 2 * P(X <= 1), n = 10
    assert stats.mcnemar_exact(9, 1) == stats.mcnemar_exact(1, 9)


def test_holm_step_down_and_monotone() :
    # Sorted p: 0.01, 0.02, 0.04; multipliers 3, 2, 1 -> 0.03, 0.04, 0.04 (kept monotone), input order kept.
    assert stats.holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    # Sorted p: 0.5, 0.9; multipliers 2, 1 -> min(1, 1.0) = 1.0, then max(1.0, 0.9) = 1.0.
    assert stats.holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    assert all(0 <= p <= 1 for p in stats.holm([0.001, 0.2, 0.9, 0.04]))


def test_bootstrap_is_deterministic_and_paired() :
    values = [1, 0, 1, 1, 0, 1, 0, 0, 1, 1] * 5
    assert stats.bootstrap_ci(values) == stats.bootstrap_ci(values)
    low, high = stats.bootstrap_ci(values)
    assert low < 0.6 < high
    delta, dlow, dhigh = stats.paired_bootstrap_diff(values, values)
    assert delta == 0 and dlow == 0 and dhigh == 0                           # identical samples: no difference at all
    a = [1] * 20 + [0] * 10
    b = [0] * 10 + [1] * 10 + [0] * 10
    delta, dlow, dhigh = stats.paired_bootstrap_diff(a, b)
    assert delta == pytest.approx(10 / 30) and dlow < delta < dhigh
    with pytest.raises(ValueError) :
        stats.paired_bootstrap_diff([1, 0], [1])


def test_rank_correlations_with_ties() :
    assert list(stats.rank_average([10, 20, 20, 30])) == [1.0, 2.5, 2.5, 4.0]
    assert stats.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert stats.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert math.isnan(stats.spearman([1, 1, 1], [1, 2, 3]))
    assert stats.kendall_tau([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    # (1,2,3,4) vs (1,3,2,4): 5 concordant, 1 discordant of 6 pairs -> tau = 4 / 6
    assert stats.kendall_tau([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(4 / 6)
    # tau-b with a tie in x: 6 pairs, 1 tied in x, none in y, 5 concordant -> 5 / sqrt(5 * 6)
    assert stats.kendall_tau([1, 1, 2, 3], [1, 2, 3, 4]) == pytest.approx(5 / math.sqrt(30))
