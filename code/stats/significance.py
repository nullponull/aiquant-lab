"""戦略評価の統計的有意性検定

連載の実験で不足していた「その数字は偶然と区別できるのか」を定量化する。

実装している検定:

1. binomial_directional_test
   方向精度 (例: 30 イベント中 19 正解 = 63%) が「コイン投げ (50%)」と
   有意に異なるかの両側二項検定。Ep2/Ep6 の方向精度の評価に使う。
   注意: 予測ホライズンが重複している場合 (5 営業日先を毎日予測など) は
   標本が独立でないため、この検定は楽観側に歪む。非重複イベントで使うこと。

2. probabilistic_sharpe_ratio (PSR)
   Bailey & López de Prado (2012)。観測 Sharpe が、リターンの歪度・尖度と
   標本数を考慮した上で、基準値 (通常 0) を上回っている確率。

3. deflated_sharpe_ratio (DSR)
   Bailey & López de Prado (2014)。N 個の戦略を試して最良を選ぶ行為
   (= 多重検定) を補正した PSR。10 戦略から生存戦略を選ぶ Ep7-10 の
   設定はまさにこれが必要。

4. whites_reality_check
   White (2000)。複数戦略の超過リターンに対し、stationary bootstrap で
   「最良戦略がベンチマークに勝っているのは偶然か」の p 値を出す。

参考文献:
- Bailey, D.H. & López de Prado, M. (2012) "The Sharpe Ratio Efficient Frontier"
- Bailey, D.H. & López de Prado, M. (2014) "The Deflated Sharpe Ratio"
- White, H. (2000) "A Reality Check for Data Snooping", Econometrica
- Politis, D.N. & Romano, J.P. (1994) "The Stationary Bootstrap"
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# 1. 方向精度の二項検定
# ---------------------------------------------------------------------------
def binomial_directional_test(n_correct: int, n_total: int,
                              p_null: float = 0.5) -> dict:
    """方向精度が偶然 (p_null) と区別できるかの両側二項検定。

    Returns:
        dict(accuracy, p_value, significant_5pct, ci_low, ci_high)
        ci は Wilson スコア区間 (95%)。
    """
    if n_total <= 0:
        raise ValueError("n_total must be positive")
    res = stats.binomtest(n_correct, n_total, p_null, alternative="two-sided")
    ci = res.proportion_ci(confidence_level=0.95, method="wilson")
    return {
        "n_correct": n_correct,
        "n_total": n_total,
        "accuracy": n_correct / n_total,
        "p_value": float(res.pvalue),
        "significant_5pct": bool(res.pvalue < 0.05),
        "ci_low": float(ci.low),
        "ci_high": float(ci.high),
    }


# ---------------------------------------------------------------------------
# 2. Probabilistic Sharpe Ratio
# ---------------------------------------------------------------------------
def probabilistic_sharpe_ratio(returns: np.ndarray | pd.Series,
                               sr_benchmark: float = 0.0) -> dict:
    """PSR: 観測 Sharpe (非年率) が sr_benchmark を上回っている確率。

    歪度・尖度・標本数による Sharpe 推定誤差を考慮する。
    """
    r = pd.Series(returns).dropna().to_numpy(dtype=float)
    n = len(r)
    if n < 10:
        raise ValueError("returns too short for PSR (need >= 10)")
    sd = r.std(ddof=1)
    if sd == 0:
        raise ValueError("zero-variance returns")
    sr = r.mean() / sd                      # 1 期間あたり (非年率)
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))  # 正規分布で 3
    denom = math.sqrt(max(1e-12,
                          (1 - skew * sr + (kurt - 1) / 4 * sr ** 2) / (n - 1)))
    z = (sr - sr_benchmark) / denom
    psr = float(stats.norm.cdf(z))
    return {"sharpe_per_period": float(sr), "n_obs": n, "skew": skew,
            "kurtosis": kurt, "psr": psr, "z": float(z)}


# ---------------------------------------------------------------------------
# 3. Deflated Sharpe Ratio
# ---------------------------------------------------------------------------
def deflated_sharpe_ratio(returns: np.ndarray | pd.Series,
                          n_trials: int,
                          sr_variance_across_trials: float | None = None,
                          all_trial_sharpes: list[float] | None = None) -> dict:
    """DSR: N 個の戦略を試して選んだ最良戦略の Sharpe を多重検定補正する。

    Args:
        returns: 選ばれた (最良) 戦略の期間リターン系列
        n_trials: 試した戦略の総数 (グリッドサーチの組合せ数も含む!)
        sr_variance_across_trials: 試行間の Sharpe 分散 (非年率)。
            未指定なら all_trial_sharpes から計算する。
        all_trial_sharpes: 全試行の Sharpe (非年率) のリスト (任意)
    """
    if all_trial_sharpes is not None and len(all_trial_sharpes) >= 2:
        sr_var = float(np.var(all_trial_sharpes, ddof=1))
    elif sr_variance_across_trials is not None:
        sr_var = sr_variance_across_trials
    else:
        raise ValueError("sr_variance_across_trials か all_trial_sharpes が必要")

    n_trials = max(2, int(n_trials))
    emc = 0.5772156649015329  # Euler-Mascheroni
    maxz = ((1 - emc) * stats.norm.ppf(1 - 1.0 / n_trials)
            + emc * stats.norm.ppf(1 - 1.0 / (n_trials * math.e)))
    sr0 = math.sqrt(sr_var) * maxz          # 「N 回試せば偶然出る Sharpe」の期待最大値
    out = probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)
    out["n_trials"] = n_trials
    out["sr_threshold_expected_max"] = float(sr0)
    out["dsr"] = out.pop("psr")
    out["significant_5pct"] = bool(out["dsr"] > 0.95)
    return out


# ---------------------------------------------------------------------------
# 4. White's Reality Check (stationary bootstrap)
# ---------------------------------------------------------------------------
def _stationary_bootstrap_indices(n: int, avg_block: float,
                                  rng: np.random.Generator) -> np.ndarray:
    """Politis & Romano (1994) の stationary bootstrap インデックス生成"""
    p = 1.0 / avg_block
    idx = np.empty(n, dtype=int)
    idx[0] = rng.integers(n)
    for t in range(1, n):
        if rng.random() < p:
            idx[t] = rng.integers(n)
        else:
            idx[t] = (idx[t - 1] + 1) % n
    return idx


def whites_reality_check(strategy_returns: pd.DataFrame,
                         benchmark_returns: pd.Series,
                         n_boot: int = 2000,
                         avg_block: float = 5.0,
                         seed: int = 42) -> dict:
    """White (2000) Reality Check。

    H0: 「どの戦略もベンチマークに (期待値で) 勝っていない」。
    p 値が小さいほど、最良戦略の超過リターンがデータスヌーピングでは
    説明できないことを示す。

    Args:
        strategy_returns: 各列が戦略の日次リターン (コスト控除後)
        benchmark_returns: ベンチマーク (例: Buy-and-Hold) の日次リターン
    """
    bench = benchmark_returns.reindex(strategy_returns.index).fillna(0)
    excess = strategy_returns.sub(bench, axis=0).dropna(how="all").fillna(0)
    n, k = excess.shape
    if n < 20:
        raise ValueError("returns too short for reality check (need >= 20)")

    means = excess.mean(axis=0).to_numpy()
    stat_obs = math.sqrt(n) * means.max()

    rng = np.random.default_rng(seed)
    x = excess.to_numpy()
    centered = x - x.mean(axis=0, keepdims=True)
    count = 0
    for _ in range(n_boot):
        idx = _stationary_bootstrap_indices(n, avg_block, rng)
        boot_means = centered[idx].mean(axis=0)
        stat_boot = math.sqrt(n) * boot_means.max()
        if stat_boot >= stat_obs:
            count += 1
    p_value = (count + 1) / (n_boot + 1)

    best = excess.mean(axis=0).idxmax()
    return {
        "best_strategy": str(best),
        "best_mean_daily_excess": float(means.max()),
        "statistic": float(stat_obs),
        "p_value": float(p_value),
        "significant_5pct": bool(p_value < 0.05),
        "n_obs": n,
        "n_strategies": k,
        "n_boot": n_boot,
    }
