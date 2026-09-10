"""performance_summary は入力によらず同じキーを返す。

2026-09-07〜09 の Paper Trading (daily) は、初日（履歴1件）で
`current_equity` が返らず KeyError で落ちていた。落ちる場所が
state.save() の後・commit の前だったため状態が保存されず、
翌日も履歴1件から始まって同じ所で落ちる、という自己再生産になっていた。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "paper"))

from paper_trader import PaperState, performance_summary  # noqa: E402

REQUIRED = {"n_days", "total_return", "max_drawdown", "frozen",
            "kill_reason", "current_equity"}


def test_keys_are_identical_regardless_of_history_length():
    for hist in ([],
                 [{"date": "2026-09-01", "equity": 1_000_000.0}],
                 [{"date": "2026-09-01", "equity": 1_000_000.0},
                  {"date": "2026-09-02", "equity": 1_010_000.0}]):
        s = PaperState(cash=1_000_000.0, equity_history=list(hist))
        got = performance_summary(s)
        assert REQUIRED <= set(got), f"履歴 {len(hist)} 件で欠けたキー: {REQUIRED - set(got)}"


def test_first_day_reports_current_equity():
    s = PaperState(cash=1_000_000.0,
                   equity_history=[{"date": "2026-09-01", "equity": 987_654.0}])
    got = performance_summary(s)
    assert got["current_equity"] == 987_654.0
    assert got["n_days"] == 1
    # 2点無いと定義できないので 0.0。n_days で「まだ判定できない」と分かる
    assert got["total_return"] == 0.0


def test_empty_history_falls_back_to_cash():
    s = PaperState(cash=1_000_000.0)
    assert performance_summary(s)["current_equity"] == 1_000_000.0
