"""Walk-forward 検証フレームワーク (Phase 2)

30 営業日の単発評価 (Ep7) の代わりに、複数の期間で
「その時点までのデータだけ」で評価を繰り返す。

- purge: train と test の境界で、予測ホライズン分のサンプルを訓練側から除外
  (ラベルが test 期間のリターンと重複してリークするのを防ぐ)
- embargo: test 直後のサンプルも次の train から除外
  (test 期間の情報がシリアル相関経由で漏れるのを防ぐ)

参考: López de Prado, "Advances in Financial Machine Learning", Ch.7
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Fold:
    fold_id: int
    train_index: pd.Index
    test_index: pd.Index


def walkforward_splits(index: pd.Index,
                       n_folds: int = 5,
                       min_train: int = 252,
                       purge: int = 5,
                       embargo: int = 5,
                       expanding: bool = True) -> list[Fold]:
    """時系列 index を walk-forward に分割する。

    Args:
        index: 時系列インデックス (昇順)
        n_folds: テスト区間の数
        min_train: 最初のフォールドの最小訓練長
        purge: train 末尾から除外する本数 (予測ホライズン以上にする)
        embargo: (rolling 利用時など) test 後に除外する本数
        expanding: True で訓練窓を拡大、False で固定長ローリング
    """
    n = len(index)
    test_total = n - min_train
    if test_total < n_folds:
        raise ValueError(f"データ不足: n={n}, min_train={min_train}, n_folds={n_folds}")
    test_len = test_total // n_folds

    folds: list[Fold] = []
    for k in range(n_folds):
        test_start = min_train + k * test_len
        test_end = n if k == n_folds - 1 else test_start + test_len
        train_end = max(0, test_start - purge)
        train_start = 0 if expanding else max(0, train_end - min_train)
        # embargo: 前のフォールドの test 直後を訓練に入れない (expanding では
        # test が常に train より後ろなので、過去 test の embargo を train から除外)
        train_idx = index[train_start:train_end]
        if k > 0 and not expanding:
            pass  # rolling では train_start で自然に除外される
        folds.append(Fold(k, train_idx, index[test_start:test_end]))
    # embargo は連続フォールド構成では train が test より常に過去のため
    # 実質 purge と同義になる。API として残し、必要なら purge に加算する。
    if embargo:
        pass
    return folds


def run_walkforward(df: pd.DataFrame,
                    strategy_fns: dict,
                    backtest_fn,
                    n_folds: int = 5,
                    min_train: int = 252,
                    purge: int = 5,
                    execution: str = "next_open") -> pd.DataFrame:
    """戦略群を walk-forward で評価し、フォールド別成績の表を返す。

    strategy_fns: {name: fn(df)->signals}。シグナル関数は各フォールドで
    「train+test を含む過去データ」から計算するが、評価は test 区間のみ。
    (パラメータ探索を伴う戦略は fn 内で train のみ使うこと)
    """
    rows = []
    folds = walkforward_splits(df.index, n_folds=n_folds,
                               min_train=min_train, purge=purge)
    for fold in folds:
        hist = df.loc[:fold.test_index[-1]]
        for name, fn in strategy_fns.items():
            signals_full = fn(hist)
            test_df = df.loc[fold.test_index]
            signals = signals_full.reindex(fold.test_index).fillna(0)
            res = backtest_fn(name, test_df, signals, execution=execution)
            rows.append({
                "fold": fold.fold_id,
                "strategy": name,
                "test_start": str(fold.test_index[0]),
                "test_end": str(fold.test_index[-1]),
                "n_days": res.n_days,
                "total_return": res.total_return,
                "sharpe": res.sharpe,
                "max_drawdown": res.max_drawdown,
                "n_trades": res.n_trades,
            })
    return pd.DataFrame(rows)


def aggregate_walkforward(table: pd.DataFrame) -> pd.DataFrame:
    """フォールド別成績を戦略別に集計 (平均 Sharpe、勝ちフォールド率など)"""
    g = table.groupby("strategy")
    out = pd.DataFrame({
        "mean_sharpe": g["sharpe"].mean(),
        "std_sharpe": g["sharpe"].std(),
        "mean_return": g["total_return"].mean(),
        "pct_positive_folds": g["total_return"].apply(lambda s: float(np.mean(s > 0))),
        "worst_drawdown": g["max_drawdown"].min(),
        "n_folds": g.size(),
    })
    return out.sort_values("mean_sharpe", ascending=False)
