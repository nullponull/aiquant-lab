"""Phase 2-4 モジュールのテスト

- walk-forward: 分割境界・purge・リークなし
- volatility: ボラクラスタのある合成データで EWMA/HAR が定数に勝つ
- regime: 合成 2 レジームデータの復元
- ranking: 仕込んだクロスセクション効果を Rank IC が検出する
- paper trader: リバランス・コスト・キルスイッチ
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from validation.walkforward import walkforward_splits  # noqa: E402
from forecast.volatility import evaluate_vol_forecasts  # noqa: E402
from forecast.regime import fit_regime_hmm, regime_persistence  # noqa: E402
from crosssect.ranking import (  # noqa: E402
    momentum_12_1, evaluate_signal, newey_west_tstat)
from paper.paper_trader import (  # noqa: E402
    PaperState, rebalance, PER_SIDE_COST, performance_summary)


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------
def test_walkforward_no_overlap_and_purge():
    idx = pd.bdate_range("2018-01-01", periods=1000)
    folds = walkforward_splits(idx, n_folds=4, min_train=400, purge=5)
    assert len(folds) == 4
    for f in folds:
        # train は test より厳密に過去、かつ purge 分のギャップ
        assert f.train_index[-1] < f.test_index[0]
        gap = idx.get_loc(f.test_index[0]) - idx.get_loc(f.train_index[-1])
        assert gap >= 5 + 1
    # test 区間同士は重複しない
    all_test = [d for f in folds for d in f.test_index]
    assert len(all_test) == len(set(all_test))
    # 最終フォールドはデータ末尾まで使う
    assert folds[-1].test_index[-1] == idx[-1]


def test_walkforward_insufficient_data_raises():
    idx = pd.bdate_range("2024-01-01", periods=100)
    with pytest.raises(ValueError):
        walkforward_splits(idx, n_folds=5, min_train=99)


# ---------------------------------------------------------------------------
# ボラティリティ予測
# ---------------------------------------------------------------------------
def make_garch_like(n=1500, seed=7):
    """ボラクラスタのある合成リターン (GARCH(1,1) 風)"""
    rng = np.random.default_rng(seed)
    h = np.empty(n)
    r = np.empty(n)
    h[0] = 1e-4
    omega, alpha, beta = 2e-6, 0.08, 0.90
    for t in range(n):
        if t > 0:
            h[t] = omega + alpha * r[t - 1] ** 2 + beta * h[t - 1]
        r[t] = np.sqrt(h[t]) * rng.standard_normal()
    idx = pd.bdate_range("2019-01-01", periods=n)
    return pd.Series(r, index=idx)


def test_vol_forecasts_beat_constant_on_clustered_data():
    ret = make_garch_like()
    res = evaluate_vol_forecasts(ret, min_train=252)
    assert res.loc["ewma_0.94", "qlike"] < res.loc["constant_baseline", "qlike"]
    assert res.loc["har_rv", "qlike"] < res.loc["constant_baseline", "qlike"]
    # 「分散は予測できる」が再現される (改善 5% 以上)
    assert res.loc["ewma_0.94", "qlike_improvement_vs_const"] > 0.05


def test_vol_forecast_is_out_of_sample():
    """予測値が同時点の実現値 r² を使っていない (相関はあるが一致しない)"""
    ret = make_garch_like(n=600)
    res = evaluate_vol_forecasts(ret, min_train=252)
    # 完全一致なら MSE=0 になるはずがない
    assert res.loc["ewma_0.94", "mse"] > 0
    assert res.loc["har_rv", "mse"] > 0


# ---------------------------------------------------------------------------
# レジーム検出
# ---------------------------------------------------------------------------
def make_two_regime(n=1200, seed=11):
    rng = np.random.default_rng(seed)
    states = np.empty(n, dtype=int)
    states[0] = 0
    for t in range(1, n):
        p_stay = 0.97 if states[t - 1] == 0 else 0.94
        states[t] = states[t - 1] if rng.random() < p_stay else 1 - states[t - 1]
    sd = np.where(states == 0, 0.006, 0.020)
    r = rng.standard_normal(n) * sd
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.Series(r, index=idx), states


def test_hmm_recovers_two_regimes():
    ret, true_states = make_two_regime()
    res = fit_regime_hmm(ret)
    # ボラ推定が真値 (0.6% / 2.0%) に近い
    assert res.stds[0] == pytest.approx(0.006, rel=0.35)
    assert res.stds[1] == pytest.approx(0.020, rel=0.35)
    # 状態判定の一致率 (smoothed argmax vs 真の状態)
    pred = (res.smoothed_prob["turbulent"] > 0.5).astype(int).to_numpy()
    acc = (pred == true_states).mean()
    assert acc > 0.85
    # 持続性が検出される
    p = regime_persistence(res)
    assert p["p_stay_calm"] > 0.9
    assert p["p_stay_turbulent"] > 0.85


# ---------------------------------------------------------------------------
# クロスセクショナル Rank IC
# ---------------------------------------------------------------------------
def make_panel_with_momentum(n_days=1300, n_names=40, seed=13, strength=0.25):
    """過去 252 日リターンが将来リターンに効く合成パネル"""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n_days)
    # 銘柄ごとに持続的なドリフト (モメンタムの源泉)
    drift = rng.normal(0.0, 0.0008, size=n_names)
    rets = rng.normal(0.0, 0.015, size=(n_days, n_names)) + drift
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)),
                          index=idx, columns=[f"T{i}" for i in range(n_names)])
    _ = strength
    return prices


def test_rank_ic_detects_planted_momentum():
    prices = make_panel_with_momentum()
    res = evaluate_signal(prices, momentum_12_1, horizon=21)
    assert res["mean_ic"] > 0.05
    assert res["significant_5pct"] is True


def test_rank_ic_near_zero_on_pure_noise():
    rng = np.random.default_rng(17)
    idx = pd.bdate_range("2019-01-01", periods=1300)
    rets = rng.normal(0.0, 0.015, size=(1300, 40))
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=idx,
                          columns=[f"T{i}" for i in range(40)])
    res = evaluate_signal(prices, momentum_12_1, horizon=21)
    assert abs(res["mean_ic"]) < 0.08
    assert res["significant_5pct"] is False


def test_newey_west_tstat_sane():
    rng = np.random.default_rng(19)
    x = pd.Series(rng.normal(0.5, 1.0, 200))
    t = newey_west_tstat(x)
    assert t > 3  # 明確に正の平均は検出される


# ---------------------------------------------------------------------------
# ペーパートレーダー
# ---------------------------------------------------------------------------
def test_rebalance_costs_and_units():
    state = PaperState.new(1_000_000.0)
    state = rebalance(state, {"SPY": 0.5}, {"SPY": 500.0},
                      as_of="2026-01-05", max_weight=1.0)
    units = state.positions["SPY"]
    assert units == pytest.approx(1_000_000 * 0.5 / 500.0, rel=1e-9)
    # コスト分だけ equity が目減り
    eq = state.equity({"SPY": 500.0})
    assert eq == pytest.approx(1_000_000 - 500_000 * PER_SIDE_COST, rel=1e-9)


def test_kill_switch_triggers_and_freezes():
    state = PaperState.new(1_000_000.0)
    state = rebalance(state, {"SPY": 1.0}, {"SPY": 500.0},
                      as_of="2026-01-05", max_weight=1.0)
    # 25% 急落 → キルスイッチ
    state = rebalance(state, {"SPY": 1.0}, {"SPY": 375.0},
                      as_of="2026-01-06", max_weight=1.0, max_drawdown=-0.20)
    assert state.frozen is True
    assert state.positions == {}
    assert "max_drawdown" in (state.kill_reason or "")
    # 凍結後はリバランスしない
    state = rebalance(state, {"SPY": 1.0}, {"SPY": 600.0}, as_of="2026-01-07")
    assert state.positions == {}
    s = performance_summary(state)
    assert s["frozen"] is True


def test_max_weight_cap():
    state = PaperState.new(1_000_000.0)
    state = rebalance(state, {"AAA": 0.9}, {"AAA": 100.0},
                      as_of="2026-01-05", max_weight=0.25)
    eq = state.equity({"AAA": 100.0})
    weight = state.positions["AAA"] * 100.0 / eq
    assert weight <= 0.26
