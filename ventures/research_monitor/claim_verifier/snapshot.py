"""銘柄価格スナップショット (T=0 と T=horizon)

サポート資産:
- crypto: BTC, ETH, SOL, ... (yfinance via -USD pair)
- us_stock: SPY, QQQ, AAPL, NVDA, ...
- jp_stock: 7203.T, 9984.T, ... (yfinance with .T suffix)
- fx: USDJPY=X, EURUSD=X, ...
"""

from __future__ import annotations

from typing import Optional


CRYPTO_TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "BNB": "BNB-USD",
    "ADA": "ADA-USD",
    "MATIC": "MATIC-USD",
    "AVAX": "AVAX-USD",
}

US_STOCK_TICKERS = {
    "SPY", "QQQ", "DIA", "IWM",  # ETFs
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "NOBL", "VOO", "VTI", "VXUS",
    "BRK-B", "JPM", "BAC",
}


def normalize_ticker(asset: str) -> tuple[str, str]:
    """主張中の銘柄名を yfinance 用ティッカーに正規化

    Returns: (yfinance_ticker, asset_class)
    """
    asset_upper = asset.upper().strip()

    # クリプト
    if asset_upper in CRYPTO_TICKERS:
        return CRYPTO_TICKERS[asset_upper], "crypto"
    if asset_upper.endswith("-USD"):
        return asset_upper, "crypto"

    # 米国株
    if asset_upper in US_STOCK_TICKERS:
        return asset_upper, "us_stock"

    # 日本株（数字のみ → .T 付与）
    if asset_upper.isdigit() and len(asset_upper) == 4:
        return f"{asset_upper}.T", "jp_stock"
    if asset_upper.endswith(".T"):
        return asset_upper, "jp_stock"

    # FX (=X)
    if asset_upper.endswith("=X"):
        return asset_upper, "fx"
    if "USD" in asset_upper or "JPY" in asset_upper or "EUR" in asset_upper:
        if not asset_upper.endswith("=X"):
            return f"{asset_upper}=X", "fx"

    # 不明 → そのまま株扱い
    return asset_upper, "us_stock"


def fetch_price(asset: str) -> Optional[dict]:
    """現在価格を取得

    Returns: {"price": float, "currency": str, "ticker": str, "asset_class": str}
             または None (取得失敗)
    """
    try:
        import yfinance as yf
    except ImportError:
        print("[snapshot] yfinance not available")
        return None

    ticker, asset_class = normalize_ticker(asset)
    try:
        t = yf.Ticker(ticker)
        # 直近の終値 + 現在の場合 fast_info を使う
        try:
            info = t.fast_info
            price = info.get("last_price") or info.get("lastPrice") or info.get("regularMarketPrice")
        except Exception:
            price = None

        if price is None:
            hist = t.history(period="2d", auto_adjust=True)
            if hist.empty:
                return None
            price = float(hist["Close"].iloc[-1])

        # 通貨判定
        currency = "USD"
        if asset_class == "jp_stock":
            currency = "JPY"
        elif asset_class == "fx":
            # USDJPY=X は JPY 単位、EURUSD=X は USD 単位、簡易判定
            if "JPY" in ticker.upper():
                currency = "JPY"

        return {
            "price": float(price),
            "currency": currency,
            "ticker": ticker,
            "asset_class": asset_class,
        }
    except Exception as e:
        print(f"[snapshot] error for {asset}: {e}")
        return None


if __name__ == "__main__":
    import sys
    asset = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    result = fetch_price(asset)
    print(result)
