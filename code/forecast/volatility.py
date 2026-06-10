"""ボラティリティ予測 (Phase 3a)

「市場の方向」は当てられないが「変動の大きさ」には強い予測可能性がある
(ボラティリティ・クラスタリング)。これは学術的に最も確立した
市場の予測可能性であり、本プロジェクトの「予測可能な形」の出発点。

実装:
- ewma_variance: RiskMetrics 型 EWMA (λ=0.94)
- har_rv_forecast: HAR-RV (Corsi 2009) の日次プロキシ版。
  日次・週次・月次の実現分散で翌日分散を OLS 予測。
- evaluate_vol_forecasts: ベースライン (拡大窓の定数分散) と比較し、
  QLIKE / MSE で評価。プロキシは翌日の二乗リターン。

QLIKE は分散予測の標準的損失で、プロキシノイズに頑健:
    QLIKE(h, σ²) = σ²/h - ln(σ²/h) - 1   (h: 予測分散, σ²: 実現プロキシ)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def ewma_variance(returns: pd.Series, lam: float = 0.94) -> pd.Series:
    """EWMA 分散。h(t) は t-1 までの情報のみで計算 (1-step-ahead 予測)。"""
    r = returns.fillna(0).to_numpy(dtype=float)
    n = len(r)
    h = np.empty(n)
    h[0] = np.var(r[: min(20, n)]) if n > 1 else 1e-8
    for t in range(1, n):
        h[t] = lam * h[t - 1] + (1 - lam) * r[t - 1] ** 2
    return pd.Series(h, index=returns.index)


def har_rv_forecast(returns: pd.Series, min_train: int = 100) -> pd.Series:
    """HAR-RV (日次プロキシ版) による翌日分散の 1-step-ahead 予測。

    特徴量: RV_d(t-1)=r²、RV_w=直近5日平均、RV_m=直近22日平均。
    各時点 t で「t-1 までのデータ」で OLS を学習し、t の分散を予測する
    (拡大窓・完全 out-of-sample)。
    """
    r2 = (returns.fillna(0) ** 2).to_numpy(dtype=float)
    n = len(r2)
    rv_d = pd.Series(r2, index=returns.index)
    rv_w = rv_d.rolling(5).mean()
    rv_m = rv_d.rolling(22).mean()
    X_all = pd.DataFrame({"d": rv_d.shift(1), "w": rv_w.shift(1),
                          "m": rv_m.shift(1)})
    y_all = rv_d

    preds = np.full(n, np.nan)
    Xv = X_all.to_numpy()
    yv = y_all.to_numpy()
    for t in range(min_train, n):
        mask = ~np.isnan(Xv[:t]).any(axis=1)
        Xt = Xv[:t][mask]
        yt = yv[:t][mask]
        if len(yt) < 30 or np.isnan(Xv[t]).any():
            continue
        A = np.column_stack([np.ones(len(Xt)), Xt])
        beta, *_ = np.linalg.lstsq(A, yt, rcond=None)
        pred = beta[0] + Xv[t] @ beta[1:]
        preds[t] = max(pred, 1e-10)  # 分散は正
    return pd.Series(preds, index=returns.index)


def constant_variance_baseline(returns: pd.Series,
                               min_train: int = 100) -> pd.Series:
    """ベースライン: t-1 までの全標本分散 (拡大窓)。"""
    r = returns.fillna(0)
    var = (r ** 2).expanding().mean().shift(1)
    out = var.copy()
    out.iloc[:min_train] = np.nan
    return out


def qlike(h: pd.Series, proxy: pd.Series) -> pd.Series:
    """QLIKE 損失 (小さいほど良い)。proxy は実現分散プロキシ (r²)。"""
    h = h.clip(lower=1e-12)
    p = proxy.clip(lower=1e-12)
    ratio = p / h
    return ratio - np.log(ratio) - 1


def evaluate_vol_forecasts(returns: pd.Series,
                           min_train: int = 100) -> pd.DataFrame:
    """EWMA / HAR / 定数ベースラインを QLIKE と MSE で比較する。

    Returns:
        index=モデル名, columns=[qlike, mse, n_obs, qlike_improvement_vs_const]
    """
    proxy = returns.fillna(0) ** 2
    models = {
        "constant_baseline": constant_variance_baseline(returns, min_train),
        "ewma_0.94": ewma_variance(returns).shift(0),  # 既に 1-step-ahead
        "har_rv": har_rv_forecast(returns, min_train),
    }
    # 共通の評価可能期間に揃える
    valid = pd.concat(models.values(), axis=1).notna().all(axis=1)
    valid.iloc[:min_train] = False

    rows = {}
    for name, h in models.items():
        q = qlike(h[valid], proxy[valid]).mean()
        mse = ((h[valid] - proxy[valid]) ** 2).mean()
        rows[name] = {"qlike": float(q), "mse": float(mse),
                      "n_obs": int(valid.sum())}
    out = pd.DataFrame(rows).T
    base_q = out.loc["constant_baseline", "qlike"]
    out["qlike_improvement_vs_const"] = 1 - out["qlike"] / base_q
    return out
