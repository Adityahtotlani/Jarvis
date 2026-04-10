"""Market data skill — stock and crypto prices from free APIs."""

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def get_stock(symbol: str) -> str:
    """Fetch a stock quote from Yahoo Finance (no API key required)."""
    if not _HAS_REQUESTS:
        return "Stock lookups require the requests library, sir."

    symbol = symbol.strip().upper()
    if not symbol:
        return "Please specify a ticker symbol, sir."

    try:
        resp = _requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (Jarvis-Assistant)"},
        )
        resp.raise_for_status()
        data = resp.json()

        result = data.get("chart", {}).get("result")
        if not result:
            return f"I couldn't find a quote for {symbol}, sir."

        meta        = result[0]["meta"]
        price       = meta["regularMarketPrice"]
        prev_close  = meta.get("chartPreviousClose", price)
        currency    = meta.get("currency", "USD")
        name        = meta.get("longName", meta.get("shortName", symbol))

        change      = price - prev_close
        change_pct  = (change / prev_close * 100) if prev_close else 0
        direction   = "up" if change >= 0 else "down"

        return (
            f"{name} is trading at {price:,.2f} {currency}, "
            f"{direction} {abs(change):,.2f} or {abs(change_pct):.2f} percent "
            f"on the day, sir."
        )
    except Exception:
        return f"I couldn't retrieve a quote for {symbol}, sir."


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

_COIN_IDS: dict[str, str] = {
    "btc":   "bitcoin",
    "eth":   "ethereum",
    "sol":   "solana",
    "doge":  "dogecoin",
    "ada":   "cardano",
    "dot":   "polkadot",
    "matic": "matic-network",
    "link":  "chainlink",
    "avax":  "avalanche-2",
    "xrp":   "ripple",
    "bnb":   "binancecoin",
    "ltc":   "litecoin",
    "shib":  "shiba-inu",
    "trx":   "tron",
    "atom":  "cosmos",
    "algo":  "algorand",
    "near":  "near",
    "apt":   "aptos",
    "arb":   "arbitrum",
    "op":    "optimism",
}


def get_crypto(coin: str) -> str:
    """Fetch crypto price from CoinGecko (no API key required)."""
    if not _HAS_REQUESTS:
        return "Crypto lookups require the requests library, sir."

    raw = coin.strip().lower()
    if not raw:
        return "Please specify a coin, sir."

    coin_id = _COIN_IDS.get(raw, raw)

    try:
        resp = _requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids":                coin_id,
                "vs_currencies":      "usd",
                "include_24hr_change": "true",
            },
            timeout=8,
            headers={"User-Agent": "Jarvis-Assistant/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        if coin_id not in data:
            return f"I couldn't find pricing data for {coin}, sir."

        info    = data[coin_id]
        price   = info["usd"]
        change  = info.get("usd_24h_change", 0) or 0
        direction = "up" if change >= 0 else "down"

        price_str = f"{price:,.2f}" if price >= 1 else f"{price:.6f}".rstrip("0")

        return (
            f"{raw.upper()} is trading at {price_str} US dollars, "
            f"{direction} {abs(change):.2f} percent over the past 24 hours, sir."
        )
    except Exception:
        return f"I couldn't retrieve pricing for {coin}, sir."
