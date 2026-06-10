"""レジーム検出 (Phase 3b): 2 状態ガウシアン HMM

「市場全体を 1 つの分布」として扱うこと (非定常性の壁) への対処。
日次リターンを「静穏 (低ボラ)」「荒れ (高ボラ)」の 2 レジームの
隠れマルコフ過程としてモデル化し、現在のレジーム確率を推定する。

予測可能性との関係:
- レジーム自体には強い持続性がある (遷移確率の対角成分が大きい)
  → 「明日も今日と同じレジームである確率」は予測になる
- 戦略の条件付け (荒れレジームでは縮小/退避) に使う

依存を増やさないため EM (Baum-Welch) を numpy で自前実装。
スケーリング付き forward-backward で数値的に安定化している。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HMMResult:
    means: np.ndarray            # (2,)
    stds: np.ndarray             # (2,) 状態は std 昇順 (0=静穏, 1=荒れ)
    transition: np.ndarray       # (2,2) P(s_t+1 | s_t)
    smoothed_prob: pd.DataFrame  # 各時点の状態確率 (calm, turbulent)
    filtered_prob: pd.DataFrame  # forward のみ (リアルタイム推定に対応)
    log_likelihood: float
    n_iter: int


def _gauss_pdf(x: np.ndarray, mu: float, sd: float) -> np.ndarray:
    sd = max(sd, 1e-8)
    return np.exp(-0.5 * ((x - mu) / sd) ** 2) / (sd * np.sqrt(2 * np.pi))


def fit_regime_hmm(returns: pd.Series,
                   n_iter: int = 200,
                   tol: float = 1e-6,
                   seed: int = 0) -> HMMResult:
    """日次リターンに 2 状態ガウシアン HMM をフィットする。"""
    x = returns.dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 100:
        raise ValueError("returns too short for HMM (need >= 100)")

    # 初期値: 分位で低ボラ/高ボラに割る
    rng = np.random.default_rng(seed)
    mu = np.array([np.mean(x), np.mean(x)])
    sd = np.array([np.std(x) * 0.5, np.std(x) * 1.5])
    A = np.array([[0.95, 0.05], [0.05, 0.95]])
    pi = np.array([0.5, 0.5])
    _ = rng  # (将来の多スタート用に保持)

    prev_ll = -np.inf
    it = 0
    for it in range(1, n_iter + 1):
        B = np.column_stack([_gauss_pdf(x, mu[k], sd[k]) for k in range(2)])
        B = np.clip(B, 1e-300, None)

        # forward (scaled)
        alpha = np.zeros((n, 2))
        c = np.zeros(n)
        alpha[0] = pi * B[0]
        c[0] = alpha[0].sum()
        alpha[0] /= c[0]
        for t in range(1, n):
            alpha[t] = (alpha[t - 1] @ A) * B[t]
            c[t] = alpha[t].sum()
            alpha[t] /= c[t]
        ll = float(np.log(c).sum())

        # backward (scaled)
        beta = np.zeros((n, 2))
        beta[-1] = 1.0
        for t in range(n - 2, -1, -1):
            beta[t] = (A @ (B[t + 1] * beta[t + 1])) / c[t + 1]

        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)

        xi_sum = np.zeros((2, 2))
        for t in range(n - 1):
            xi = (alpha[t][:, None] * A * (B[t + 1] * beta[t + 1])[None, :])
            xi /= xi.sum()
            xi_sum += xi

        # M-step
        pi = gamma[0]
        A = xi_sum / xi_sum.sum(axis=1, keepdims=True)
        for k in range(2):
            w = gamma[:, k]
            mu[k] = np.average(x, weights=w)
            sd[k] = np.sqrt(max(np.average((x - mu[k]) ** 2, weights=w), 1e-12))

        if abs(ll - prev_ll) < tol:
            break
        prev_ll = ll

    # 状態 0 = 低ボラ (calm) に正規化
    order = np.argsort(sd)
    mu, sd = mu[order], sd[order]
    A = A[np.ix_(order, order)]
    gamma = gamma[:, order]
    alpha = alpha[:, order]

    idx = returns.dropna().index
    smoothed = pd.DataFrame(gamma, index=idx, columns=["calm", "turbulent"])
    filtered = pd.DataFrame(alpha, index=idx, columns=["calm", "turbulent"])
    return HMMResult(means=mu, stds=sd, transition=A,
                     smoothed_prob=smoothed, filtered_prob=filtered,
                     log_likelihood=ll, n_iter=it)


def regime_persistence(result: HMMResult) -> dict:
    """レジームの持続性指標。対角遷移確率と期待滞在日数。"""
    p_cc = float(result.transition[0, 0])
    p_tt = float(result.transition[1, 1])
    return {
        "p_stay_calm": p_cc,
        "p_stay_turbulent": p_tt,
        "expected_calm_duration_days": 1 / (1 - p_cc) if p_cc < 1 else np.inf,
        "expected_turbulent_duration_days": 1 / (1 - p_tt) if p_tt < 1 else np.inf,
        "vol_ratio_turbulent_to_calm": float(result.stds[1] / result.stds[0]),
    }
