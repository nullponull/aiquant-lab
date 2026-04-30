"""期限切れの claim を検証 (T = T0 + horizon)"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from db import get_pending_verifications, insert_verification
from snapshot import fetch_price


# 仮想投資額 (yen)
HYPOTHETICAL_INVESTMENT_JPY = 10000

# WIN/LOSS 判定の閾値 (directional return %)
WIN_THRESHOLD = 1.0   # +1% 超で勝ち
LOSS_THRESHOLD = -1.0  # -1% 未満で負け

# USD/JPY 簡易レート (将来は動的取得)
USD_JPY_FALLBACK = 155.0


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("verifier")


def usd_to_jpy(usd: float) -> float:
    """USD → JPY 換算（簡易）"""
    try:
        rate = fetch_price("USDJPY=X")
        if rate and rate.get("price"):
            return usd * float(rate["price"])
    except Exception:
        pass
    return usd * USD_JPY_FALLBACK


def verify_claim(claim: dict) -> dict | None:
    """1 つの claim を検証して結果 dict を返す"""
    asset = claim["asset"]
    snap = fetch_price(asset)
    if snap is None:
        logger.warning(f"  [verify] {asset}: 価格取得失敗")
        return None

    exit_price = float(snap["price"])
    entry_price = float(claim["entry_snapshot_price"])

    if entry_price <= 0:
        logger.warning(f"  [verify] {asset}: エントリー価格不正 ({entry_price})")
        return None

    raw_return_pct = (exit_price - entry_price) / entry_price * 100.0

    # 方向を考慮した実効リターン
    if claim["direction"] == "LONG":
        directional = raw_return_pct
    elif claim["direction"] == "SHORT":
        directional = -raw_return_pct
    else:  # NEUTRAL
        directional = -abs(raw_return_pct)  # 動いたら負け

    # ¥10,000 投資の P/L
    gain_ratio = directional / 100.0
    pl_jpy_raw = HYPOTHETICAL_INVESTMENT_JPY * gain_ratio

    # 主張時の通貨を JPY に揃える (entry_currency)
    if claim.get("entry_currency") == "USD":
        # 為替変動も無視 = price 変化率のみで計算
        pass  # gain_ratio はすでに % なので通貨非依存
    elif claim.get("entry_currency") == "JPY":
        pass

    # 判定
    if directional >= WIN_THRESHOLD:
        outcome = "WIN"
    elif directional <= LOSS_THRESHOLD:
        outcome = "LOSS"
    else:
        outcome = "NEUTRAL"

    # ターゲット達成判定
    target_hit = None
    if claim.get("target_pct") is not None:
        if claim["direction"] == "LONG":
            target_hit = directional >= claim["target_pct"]
        elif claim["direction"] == "SHORT":
            target_hit = directional >= claim["target_pct"]
        else:
            target_hit = directional >= -1 * abs(claim["target_pct"])

    return {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "exit_price": exit_price,
        "raw_return_pct": round(raw_return_pct, 4),
        "directional_return_pct": round(directional, 4),
        "hypothetical_jpy_pl": int(round(pl_jpy_raw)),
        "outcome": outcome,
        "target_hit": target_hit,
        "notes": f"entry={entry_price:.4f} exit={exit_price:.4f}",
    }


def main():
    pending = get_pending_verifications()
    logger.info(f"=== 検証対象: {len(pending)} 件 ===")

    if not pending:
        return 0

    success = 0
    for claim in pending:
        logger.info(f"  [{claim['id']}] {claim['asset']} {claim['direction']} "
                    f"(horizon {claim['horizon_hours']}h, source={claim['source_name']})")
        result = verify_claim(claim)
        if result:
            insert_verification(claim["id"], result)
            success += 1
            logger.info(f"    → {result['outcome']} (return {result['directional_return_pct']:+.2f}%, P/L ¥{result['hypothetical_jpy_pl']:+,})")
        else:
            logger.warning(f"    → 検証失敗")

    logger.info(f"検証完了: {success}/{len(pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
