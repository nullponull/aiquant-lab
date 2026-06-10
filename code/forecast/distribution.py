"""分布予測 (Phase 3d): 「市場を予測可能な形にする」の実装

主張を明確にする:
- 「明日の方向」の点予測は当てられない (本リポジトリの監査で確認済み)
- しかし「明日のリターンの確率分布」は予測でき、しかも当たっているか
  どうかを客観的に検定できる。これがこのプロジェクトの言う
  「予測可能な形」の実装である。

モデル: r(t) | 情報(t-1) ~ Student-t(ν, loc=0, scale = σ(t)·√((ν-2)/ν))
  - σ²(t): EWMA 分散 (1-step-ahead、t-1 までの情報のみ)
  - ν: 標準化残差への MLE (拡大窓、グリッド探索)

「当たっているか」の検定:
1. PIT (Probability Integral Transform): u(t) = F_t(r(t))。
   分布予測が正しければ u は一様分布になる → KS 検定。
2. 区間カバレッジ: 90/95/99% 予測区間に実現値が入る頻度が名目通りか。
3. 対数スコア: ベースライン (拡大窓・定数分散の正規分布) との比較。
4. 方向確率の Brier スコア: P(r>0) の較正。
   ※ ここは改善しないことが「正直な」期待値 (平均は予測できない)。
   分布 (幅・尾) は当たるが方向は当たらない、の対比を示すのが目的。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from forecast.volatility import ewma_variance, constant_variance_baseline


# ---------------------------------------------------------------------------
# ν (自由度) の推定
# ---------------------------------------------------------------------------
def fit_t_df(z: np.ndarray, grid: np.ndarray | None = None) -> float:
    """標準化残差 z (分散 1 を想定) に Student-t の自由度を MLE フィット。

    scale は分散 1 になるよう ν に連動 (s=√((ν-2)/ν))。
    """
    z = z[np.isfinite(z)]
    if grid is None:
        grid = np.concatenate([np.arange(3.0, 12.0, 0.5),
                               np.arange(12.0, 31.0, 2.0), [50.0, 100.0]])
    best_df, best_ll = 10.0, -np.inf
    for df in grid:
        s = np.sqrt((df - 2) / df)
        ll = stats.t.logpdf(z, df=df, loc=0.0, scale=s).sum()
        if ll > best_ll:
            best_ll, best_df = ll, float(df)
    return best_df


# ---------------------------------------------------------------------------
# 分布予測 (1-step-ahead)
# ---------------------------------------------------------------------------
def forecast_distribution(returns: pd.Series,
                          min_train: int = 252,
                          refit_every: int = 63) -> pd.DataFrame:
    """各 t について t-1 までの情報で r(t) の分布を予測する。

    Returns:
        DataFrame(index=日付): columns = [vol, df, scale]
        分布は Student-t(df, loc=0, scale)。min_train 以前は NaN。
    """
    r = returns.fillna(0)
    h = ewma_variance(r)               # 1-step-ahead 分散
    vol = np.sqrt(h)

    n = len(r)
    dfs = np.full(n, np.nan)
    cur_df = np.nan
    rv = r.to_numpy()
    vv = vol.to_numpy()
    for t in range(min_train, n):
        if np.isnan(cur_df) or (t - min_train) % refit_every == 0:
            z = rv[:t] / np.clip(vv[:t], 1e-10, None)
            cur_df = fit_t_df(z[20:])  # EWMA 初期化区間を除外
        dfs[t] = cur_df

    out = pd.DataFrame(index=returns.index)
    out["vol"] = vol
    out["df"] = dfs
    out["scale"] = out["vol"] * np.sqrt((out["df"] - 2) / out["df"])
    out.loc[out.index[:min_train], ["vol", "df", "scale"]] = np.nan
    return out


def pit_values(returns: pd.Series, fc: pd.DataFrame) -> pd.Series:
    """PIT u(t) = F_t(r(t))"""
    valid = fc["scale"].notna()
    u = stats.t.cdf(returns[valid], df=fc.loc[valid, "df"],
                    loc=0.0, scale=fc.loc[valid, "scale"])
    return pd.Series(u, index=returns.index[valid])


def direction_probability(fc: pd.DataFrame) -> pd.Series:
    """P(r > 0) (loc=0 モデルでは常に 0.5。拡張モデル用に API として用意)"""
    valid = fc["scale"].notna()
    p = 1 - stats.t.cdf(0.0, df=fc.loc[valid, "df"], loc=0.0,
                        scale=fc.loc[valid, "scale"])
    return pd.Series(p, index=fc.index[valid])


# ---------------------------------------------------------------------------
# 較正の評価
# ---------------------------------------------------------------------------
def evaluate_calibration(returns: pd.Series,
                         min_train: int = 252) -> dict:
    """t+EWMA 分布予測 vs 定数分散ガウシアンの較正比較。

    Returns dict:
        model/baseline それぞれの ks_pvalue, coverage_90/95/99,
        mean_log_score と、direction Brier (vs 0.5)。
    """
    r = returns.fillna(0)
    fc = forecast_distribution(r, min_train=min_train)
    valid = fc["scale"].notna()
    rv = r[valid]

    # --- モデル ---
    u = pit_values(r, fc)
    ks_p = float(stats.kstest(u, "uniform").pvalue)
    logsc = stats.t.logpdf(rv, df=fc.loc[valid, "df"], loc=0.0,
                           scale=fc.loc[valid, "scale"])
    cov = {}
    for lvl in (0.90, 0.95, 0.99):
        q = stats.t.ppf(0.5 + lvl / 2, df=fc.loc[valid, "df"]) \
            * fc.loc[valid, "scale"]
        cov[lvl] = float((rv.abs() <= q).mean())

    # --- ベースライン: 拡大窓定数分散の正規分布 ---
    var_const = constant_variance_baseline(r, min_train=min_train)[valid]
    sd_const = np.sqrt(var_const.clip(lower=1e-12))
    u_b = pd.Series(stats.norm.cdf(rv, loc=0.0, scale=sd_const),
                    index=rv.index)
    ks_p_b = float(stats.kstest(u_b, "uniform").pvalue)
    logsc_b = stats.norm.logpdf(rv, loc=0.0, scale=sd_const)
    cov_b = {}
    for lvl in (0.90, 0.95, 0.99):
        q = stats.norm.ppf(0.5 + lvl / 2) * sd_const
        cov_b[lvl] = float((rv.abs() <= q).mean())

    # --- 方向確率 Brier (loc=0 → 0.5 予測。改善しないことの確認) ---
    y = (rv > 0).astype(float)
    p_dir = direction_probability(fc)
    brier = float(((p_dir - y) ** 2).mean())
    brier_coin = float(((0.5 - y) ** 2).mean())

    return {
        "n_obs": int(valid.sum()),
        "model": {
            "ks_pvalue": ks_p,
            "calibrated_5pct": bool(ks_p > 0.05),
            "coverage": {f"{int(k*100)}%": v for k, v in cov.items()},
            "mean_log_score": float(np.mean(logsc)),
            "fitted_df_last": float(fc["df"].dropna().iloc[-1]),
        },
        "baseline_const_gaussian": {
            "ks_pvalue": ks_p_b,
            "calibrated_5pct": bool(ks_p_b > 0.05),
            "coverage": {f"{int(k*100)}%": v for k, v in cov_b.items()},
            "mean_log_score": float(np.mean(logsc_b)),
        },
        "log_score_improvement": float(np.mean(logsc) - np.mean(logsc_b)),
        "direction_brier": brier,
        "direction_brier_coin": brier_coin,
        "direction_predictable": bool(brier < brier_coin - 1e-4),
    }
