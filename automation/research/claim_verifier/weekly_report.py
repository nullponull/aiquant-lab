"""週次レポート: 検証済み主張の集計を markdown で生成

SKU 6「AI投資主張のリアルタイム精度ダッシュボード」の月次更新の元データ。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from db import stats_summary, get_conn

OUTPUT_DIR = Path("/home/sol/aiquant-lab/data/claims/reports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_report(days_back: int = 7) -> str:
    """週次集計を markdown で生成"""
    stats = stats_summary(days_back=days_back)
    today = datetime.now().strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(f"# AI 投資主張 検証レポート ({today})")
    lines.append("")
    lines.append(f"対象期間: 過去 {days_back} 日")
    lines.append(f"生成: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")

    if stats["total"] == 0:
        lines.append("> 検証済み主張がまだありません。")
        return "\n".join(lines)

    # 全体サマリー
    lines.append("## 全体サマリー")
    lines.append("")
    lines.append(f"- **検証済み主張数**: {stats['total']} 件")
    lines.append(f"- **勝率 (WIN/全体)**: {stats['win_rate']*100:.1f}%")
    lines.append(f"- **平均リターン (方向考慮)**: {stats['avg_return_pct']:+.2f}%")
    lines.append(f"- **¥10,000/件 仮想投資の累計 P/L**: ¥{stats['total_pl_jpy']:+,}")
    lines.append("")
    lines.append("**ベンチマーク比較** (S&P500 buy-and-hold 同期間想定):")
    lines.append(f"- 単純な指数連動なら期間中 ~+{0.02 * days_back * 100:.2f}% 想定 (年率 5% 仮定)")
    lines.append("")

    # ソース別
    if stats["by_source"]:
        lines.append("## ソース別 勝率")
        lines.append("")
        sorted_src = sorted(stats["by_source"].items(), key=lambda x: -x[1]["win_rate"])
        for src, agg in sorted_src:
            n = agg["n"]
            wr = agg["win_rate"] * 100
            avg_r = agg["avg_return_pct"]
            pl = agg["total_pl_jpy"]
            lines.append(f"- **{src}** ({n} 件): 勝率 {wr:.1f}%, 平均 {avg_r:+.2f}%, P/L ¥{pl:+,}")
        lines.append("")

    # 資産クラス別
    if stats["by_asset_class"]:
        lines.append("## 資産クラス別 勝率")
        lines.append("")
        for cls, agg in stats["by_asset_class"].items():
            n = agg["n"]
            wr = agg["win_rate"] * 100
            avg_r = agg["avg_return_pct"]
            lines.append(f"- **{cls}** ({n} 件): 勝率 {wr:.1f}%, 平均 {avg_r:+.2f}%")
        lines.append("")

    # 個別の WIN/LOSS Top 例
    with get_conn() as conn:
        wins = conn.execute(
            """
            SELECT c.asset, c.direction, c.source_name, c.source_author,
                   c.horizon_hours, c.target_pct, c.raw_text,
                   v.directional_return_pct, v.hypothetical_jpy_pl, v.outcome
            FROM verifications v JOIN claims c ON c.id = v.claim_id
            WHERE v.verified_at >= datetime('now', ?)
            ORDER BY v.directional_return_pct DESC
            LIMIT 5
            """,
            (f"-{days_back} days",),
        ).fetchall()
        losses = conn.execute(
            """
            SELECT c.asset, c.direction, c.source_name, c.source_author,
                   c.horizon_hours, c.target_pct, c.raw_text,
                   v.directional_return_pct, v.hypothetical_jpy_pl, v.outcome
            FROM verifications v JOIN claims c ON c.id = v.claim_id
            WHERE v.verified_at >= datetime('now', ?)
            ORDER BY v.directional_return_pct ASC
            LIMIT 5
            """,
            (f"-{days_back} days",),
        ).fetchall()

    if wins:
        lines.append("## 期間内 ベスト 5 (リターン降順)")
        lines.append("")
        for r in wins:
            lines.append(f"- {r['asset']} {r['direction']} ({r['horizon_hours']:.0f}h): "
                         f"**{r['directional_return_pct']:+.2f}%** | "
                         f"P/L ¥{r['hypothetical_jpy_pl']:+,} | "
                         f"出典: {r['source_name']}{' / ' + r['source_author'] if r['source_author'] else ''}")
            target = f", target {r['target_pct']:+.0f}%" if r['target_pct'] else ""
            snippet = (r['raw_text'] or '')[:100].replace('\n', ' ')
            lines.append(f"  > {snippet}...")
        lines.append("")

    if losses:
        lines.append("## 期間内 ワースト 5 (リターン昇順)")
        lines.append("")
        for r in losses:
            lines.append(f"- {r['asset']} {r['direction']} ({r['horizon_hours']:.0f}h): "
                         f"**{r['directional_return_pct']:+.2f}%** | "
                         f"P/L ¥{r['hypothetical_jpy_pl']:+,} | "
                         f"出典: {r['source_name']}{' / ' + r['source_author'] if r['source_author'] else ''}")
            snippet = (r['raw_text'] or '')[:100].replace('\n', ' ')
            lines.append(f"  > {snippet}...")
        lines.append("")

    # 教訓
    lines.append("## 教訓")
    lines.append("")
    lines.append("- 短期予測の検証は「実装で確かめる」連載の第 2 壁・第 3 壁の素材")
    lines.append("- 勝率 50% 周辺なら、ノイズと統計的有意差を検定する必要")
    lines.append("- ¥10,000/件は仮想投資、実取引ではない (連載の透明性原則)")
    lines.append("")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    md = generate_report(days_back=args.days)

    if args.out:
        out_path = Path(args.out)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        out_path = OUTPUT_DIR / f"weekly_{today}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"レポート出力: {out_path}")
    print(md[:600])
    print("...")


if __name__ == "__main__":
    main()
