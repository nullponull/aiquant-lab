"""分布予測 (Phase 3d) のテスト

「分布は当たる・方向は当たらない」がテストとして再現されることを保証する。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

from forecast.distribution import (  # noqa: E402
    fit_t_df, forecast_distribution, pit_values, evaluate_calibration)


def make_garch_t(n=2000, df=6.0, seed=23):
    """ファットテール + ボラクラスタの合成リターン (GARCH-t)"""
    rng = np.random.default_rng(seed)
    h = np.empty(n)
    r = np.empty(n)
    h[0] = 1e-4
    omega, alpha, beta = 2e-6, 0.08, 0.90
    s = np.sqrt((df - 2) / df)
    for t in range(n):
        if t > 0:
            h[t] = omega + alpha * r[t - 1] ** 2 + beta * h[t - 1]
        r[t] = np.sqrt(h[t]) * stats_t_rvs(rng, df) * s
    idx = pd.bdate_range("2017-01-01", periods=n)
    return pd.Series(r, index=idx)


def stats_t_rvs(rng, df):
    # scipy を介さず t 乱数 (正規 / sqrt(chi2/df))
    return rng.standard_normal() / np.sqrt(rng.chisquare(df) / df)


def test_fit_t_df_recovers_tails():
    rng = np.random.default_rng(29)
    df_true = 5.0
    s = np.sqrt((df_true - 2) / df_true)
    z = (rng.standard_normal(5000) /
         np.sqrt(rng.chisquare(df_true, 5000) / df_true)) * s / s
    est = fit_t_df(z)
    assert 3.5 <= est <= 8.0  # ファットテールとして検出


def test_model_is_calibrated_on_garch_t():
    ret = make_garch_t()
    res = evaluate_calibration(ret, min_train=252)
    m, b = res["model"], res["baseline_const_gaussian"]
    # 分布予測は較正に合格する
    assert m["calibrated_5pct"] is True
    # 95% 区間カバレッジが名目に近い
    assert abs(m["coverage"]["95%"] - 0.95) < 0.02
    # 対数スコアでベースラインに明確に勝つ
    assert res["log_score_improvement"] > 0.02
    # ベースライン (定数分散ガウシアン) は較正に落ちる
    assert b["calibrated_5pct"] is False


def test_direction_is_not_predictable_and_we_say_so():
    """方向 Brier は 0.5 予測とほぼ同じ = 方向は予測できないことを明示"""
    ret = make_garch_t(seed=31)
    res = evaluate_calibration(ret, min_train=252)
    assert res["direction_predictable"] is False
    assert abs(res["direction_brier"] - res["direction_brier_coin"]) < 0.01


def test_forecast_is_out_of_sample():
    """予測は t-1 までの情報のみ: 末尾の値を改変しても過去の予測は不変"""
    ret = make_garch_t(n=800, seed=37)
    fc1 = forecast_distribution(ret, min_train=252)
    ret2 = ret.copy()
    ret2.iloc[-1] = 0.25  # 大暴騰に改変
    fc2 = forecast_distribution(ret2, min_train=252)
    pd.testing.assert_frame_equal(fc1.iloc[:-1], fc2.iloc[:-1])


def test_pit_values_in_unit_interval():
    ret = make_garch_t(n=600, seed=41)
    fc = forecast_distribution(ret, min_train=252)
    u = pit_values(ret, fc)
    assert ((u >= 0) & (u <= 1)).all()
    assert len(u) == fc["scale"].notna().sum()
