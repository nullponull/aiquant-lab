"""ペーパートレーディング基盤 (Phase 4)

バックテストで生き残った仮説を「未来のデータ」で検証するための
模擬運用。実発注は行わない (実弾運用・第三者提供は金商法上の論点が
あるため、本プロジェクトは自己研究としての模擬運用に留める)。

設計:
- 状態は JSON で永続化 (GitHub Actions の日次 cron でコミットする想定)
- 約定は当日始値 + 片道コスト (commission + slippage)
- リスク管理:
  - 1 銘柄あたり最大ウェイト
  - 最大ドローダウンでキルスイッチ (全ポジション解消・凍結)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

COMMISSION = 0.0005
SLIPPAGE = 0.0005
PER_SIDE_COST = COMMISSION + SLIPPAGE


@dataclass
class PaperState:
    cash: float
    positions: dict = field(default_factory=dict)   # ticker -> units
    equity_history: list = field(default_factory=list)  # [{date, equity}]
    frozen: bool = False
    kill_reason: str | None = None

    @classmethod
    def new(cls, initial_cash: float = 1_000_000.0) -> "PaperState":
        return cls(cash=initial_cash)

    @classmethod
    def load(cls, path: Path) -> "PaperState":
        d = json.loads(Path(path).read_text())
        return cls(**d)

    def save(self, path: Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.__dict__, ensure_ascii=False,
                                         indent=2, default=str))

    def equity(self, prices: dict) -> float:
        pos_value = sum(units * prices[t] for t, units in self.positions.items()
                        if t in prices)
        return self.cash + pos_value

    def peak_equity(self) -> float:
        if not self.equity_history:
            return self.cash
        return max(e["equity"] for e in self.equity_history)


def rebalance(state: PaperState,
              target_weights: dict,
              prices: dict,
              as_of: str | None = None,
              max_weight: float = 0.25,
              max_drawdown: float = -0.20) -> PaperState:
    """目標ウェイトへリバランスする。

    Args:
        target_weights: {ticker: weight} 合計 <= 1.0 (残りは現金)
        prices: {ticker: 約定価格 (当日始値を想定)}
        max_weight: 1 銘柄の最大ウェイト (超過分は切り詰め)
        max_drawdown: ピーク比でこれを下回ったら全解消して凍結
    """
    as_of = as_of or date.today().isoformat()

    eq_before = state.equity(prices)

    # --- キルスイッチ判定 (リバランス前の評価で) ---
    peak = max(state.peak_equity(), eq_before)
    dd = eq_before / peak - 1 if peak > 0 else 0.0
    if state.frozen:
        state.equity_history.append({"date": as_of, "equity": eq_before,
                                     "note": "frozen"})
        return state
    if dd <= max_drawdown:
        # 全ポジション解消
        for t, units in list(state.positions.items()):
            if t in prices and units != 0:
                state.cash += units * prices[t] * (1 - PER_SIDE_COST)
        state.positions = {}
        state.frozen = True
        state.kill_reason = (f"max_drawdown breached: {dd:.1%} <= "
                             f"{max_drawdown:.0%} on {as_of}")
        state.equity_history.append({"date": as_of, "equity": state.cash,
                                     "note": "KILL_SWITCH"})
        return state

    # --- ウェイト制限 ---
    weights = {t: min(w, max_weight) for t, w in target_weights.items()
               if t in prices and w > 0}
    total_w = sum(weights.values())
    if total_w > 1.0:
        weights = {t: w / total_w for t, w in weights.items()}

    # --- リバランス (差分のみ約定しコストを払う) ---
    eq = eq_before
    all_tickers = set(state.positions) | set(weights)
    for t in sorted(all_tickers):
        px = prices.get(t)
        if px is None or px <= 0:
            continue
        cur_units = state.positions.get(t, 0.0)
        tgt_units = eq * weights.get(t, 0.0) / px
        delta = tgt_units - cur_units
        if abs(delta * px) < 1e-9:
            continue
        cost = abs(delta) * px * PER_SIDE_COST
        state.cash -= delta * px + cost
        if abs(tgt_units) < 1e-12:
            state.positions.pop(t, None)
        else:
            state.positions[t] = tgt_units

    eq_after = state.equity(prices)
    state.equity_history.append({"date": as_of, "equity": eq_after})
    return state


def performance_summary(state: PaperState) -> dict:
    """常に同じキーを返す。

    [2026-09-10] 以前は履歴が 2 件未満のとき
    `{"n_days", "total_return"}` だけを返していた。呼び出し側は
    `summary["current_equity"]` を無条件に読むので **初日は必ず KeyError で落ちる**。

    そして落ちる場所が悪かった。`state.save()` の後・`git commit` の前で落ちるため、
    ワークフローの "Commit state" ステップに到達せず**状態が保存されない**。
    翌日また履歴 1 件から始まり、同じ所で落ちる——**失敗が自分を再生産していた**
    （2026-09-07 / 08 / 09 と毎日同じ形で失敗）。

    戻り値の形が入力で変わる関数は、呼び出し側の分岐を増やすか、こうして落ちる。
    **形は常に一つにして、値の方で「まだ分からない」を表す。**
    """
    eq = pd.Series({e["date"]: e["equity"] for e in state.equity_history},
                   dtype=float).sort_index()

    # 履歴が無いときの現在値は保有評価額が取れないので現金で代用する
    current = float(eq.iloc[-1]) if len(eq) else float(state.cash)
    # 収益率と最大ドローダウンは 2 点以上ないと定義できない。0 ではなく「まだ無い」
    # を表したいが、表示側が数値を前提にしているので 0.0 を入れ、n_days で判別させる。
    ret = float(eq.iloc[-1] / eq.iloc[0] - 1) if len(eq) >= 2 else 0.0
    dd = float((eq / eq.cummax() - 1).min()) if len(eq) >= 2 else 0.0

    return {
        "n_days": int(len(eq)),
        "total_return": ret,
        "max_drawdown": dd,
        "frozen": state.frozen,
        "kill_reason": state.kill_reason,
        "current_equity": current,
    }
