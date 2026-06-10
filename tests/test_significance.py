"""統計検定モジュール (code/stats/significance.py) のテスト"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from stats.significance import (  # noqa: E402
    binomial_directional_test,
    probabilistic_sharpe_ratio,
    deflated_sharpe_ratio,
    whites_reality_check,
)


# ---------------------------------------------------------------------------
# 二項検定
# ---------------------------------------------------------------------------
def test_binomial_ep2_like_accuracy_is_not_significant():
    """Ep2/Ep6 規模 (n=30 で 63%) は 50% と区別できない"""
    res = binomial_directional_test(19, 30)
    assert res["accuracy"] == pytest.approx(19 / 30)
    assert res["p_value"] > 0.05
    assert res["significant_5pct"] is False
    # 95% CI が 0.5 をまたぐ
    assert res["ci_low"] < 0.5 < res["ci_high"]


def test_binomial_large_sample_is_significant():
    """同じ 63% でも n=300 なら有意になる (検出力の問題だと分かる)"""
    res = binomial_directional_test(190, 300)
    assert res["p_value"] < 0.05
    assert res["significant_5pct"] is True


# ---------------------------------------------------------------------------
# PSR / DSR
# ---------------------------------------------------------------------------
def test_psr_zero_mean_returns_near_half():
    r = np.tile([0.01, -0.01], 500)  # 厳密に平均ゼロ
    res = probabilistic_sharpe_ratio(r)
    assert res["psr"] == pytest.approx(0.5, abs=0.02)


def test_psr_strong_positive_returns_high():
    rng = np.random.default_rng(1)
    r = rng.normal(0.001, 0.005, size=1000)
    res = probabilistic_sharpe_ratio(r)
    assert res["psr"] > 0.99


def test_dsr_deflates_lucky_best_of_many():
    """ノイズだけの戦略群から最良を選んでも DSR は有意にならない"""
    rng = np.random.default_rng(2)
    n_trials, n_obs = 50, 252
    rets = rng.normal(0.0, 0.01, size=(n_trials, n_obs))
    sharpes = rets.mean(axis=1) / rets.std(axis=1, ddof=1)
    best = int(np.argmax(sharpes))
    res = deflated_sharpe_ratio(rets[best], n_trials=n_trials,
                                all_trial_sharpes=list(sharpes))
    assert res["significant_5pct"] is False
    # 多重検定の閾値は 0 より大きいはず
    assert res["sr_threshold_expected_max"] > 0


def test_dsr_keeps_genuinely_good_strategy():
    rng = np.random.default_rng(3)
    n_trials, n_obs = 10, 1000
    noise = rng.normal(0.0, 0.01, size=(n_trials - 1, n_obs))
    good = rng.normal(0.002, 0.01, size=n_obs)  # 本物のエッジ
    sharpes = list(noise.mean(axis=1) / noise.std(axis=1, ddof=1))
    sharpes.append(good.mean() / good.std(ddof=1))
    res = deflated_sharpe_ratio(good, n_trials=n_trials,
                                all_trial_sharpes=sharpes)
    assert res["dsr"] > 0.95


# ---------------------------------------------------------------------------
# Reality Check
# ---------------------------------------------------------------------------
def test_reality_check_noise_strategies_not_significant():
    rng = np.random.default_rng(4)
    n = 252
    idx = pd.bdate_range("2024-01-01", periods=n)
    bench = pd.Series(rng.normal(0.0003, 0.01, n), index=idx)
    strats = pd.DataFrame(
        {f"s{i}": bench + rng.normal(0.0, 0.005, n) for i in range(8)},
        index=idx)
    res = whites_reality_check(strats, bench, n_boot=500)
    assert 0.0 <= res["p_value"] <= 1.0
    assert res["p_value"] > 0.05


def test_reality_check_detects_real_edge():
    rng = np.random.default_rng(5)
    n = 500
    idx = pd.bdate_range("2023-01-01", periods=n)
    bench = pd.Series(rng.normal(0.0, 0.01, n), index=idx)
    strats = pd.DataFrame(
        {f"s{i}": bench + rng.normal(0.0, 0.002, n) for i in range(5)},
        index=idx)
    strats["edge"] = bench + 0.002 + rng.normal(0.0, 0.002, n)  # 日次 +0.2%
    res = whites_reality_check(strats, bench, n_boot=500)
    assert res["best_strategy"] == "edge"
    assert res["p_value"] < 0.05
