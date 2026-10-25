"""Coin prices next to crypto stories: which coins a story names, and their USD price from CoinGecko.

One upstream call fetches every coin we know, cached for all workers (the file cache): the free API allows a few
calls a minute, and readers only need a price that is a couple of minutes fresh."""
import json
import logging
import re
import urllib.parse
import urllib.request

from django.core.cache import cache

log = logging.getLogger(__name__)

# (CoinGecko id, ticker, names). Tickers match in capitals only, names as written: "SOL", "Solana", not "sol".
# Stablecoins are left out: their price says nothing.
COINS = [
    ('bitcoin', 'BTC', ['Bitcoin']),
    ('ethereum', 'ETH', ['Ethereum', 'Ether']),
    ('ripple', 'XRP', ['Ripple']),
    ('binancecoin', 'BNB', []),
    ('solana', 'SOL', ['Solana']),
    ('tron', 'TRX', ['Tron', 'TRON']),
    ('dogecoin', 'DOGE', ['Dogecoin']),
    ('cardano', 'ADA', ['Cardano']),
    ('hyperliquid', 'HYPE', ['Hyperliquid']),
    ('chainlink', 'LINK', ['Chainlink']),
    ('stellar', 'XLM', ['Stellar']),
    ('sui', 'SUI', []),
    ('avalanche-2', 'AVAX', ['Avalanche']),
    ('litecoin', 'LTC', ['Litecoin']),
    ('the-open-network', 'TON', ['Toncoin']),
    ('shiba-inu', 'SHIB', ['Shiba Inu']),
    ('polkadot', 'DOT', ['Polkadot']),
    ('monero', 'XMR', ['Monero']),
    ('uniswap', 'UNI', ['Uniswap']),
]
NAMES = {coin_id: (names[0] if names else ticker) for coin_id, ticker, names in COINS}
TICKERS = {coin_id: ticker for coin_id, ticker, _ in COINS}

_PATTERNS = [(coin_id, re.compile(r'(?<![\w$])\$?(?:' + '|'.join(map(re.escape, [ticker, *names])) + r')(?!\w)'))
             for coin_id, ticker, names in COINS]

PRICE_URL = 'https://api.coingecko.com/api/v3/simple/price'
USER_AGENT = 'renews.me/1.0 (+https://renews.me)'
FRESH = 120  # seconds a price is served before asking CoinGecko again
STALE = 6 * 3600  # CoinGecko down: the last prices are still better than none, up to this age


def mentioned(*texts: str) -> list[str]:
    """CoinGecko ids of the coins named in the texts, in market-cap order (the order of COINS)."""
    text = '\n'.join(texts)
    return [coin_id for coin_id, pattern in _PATTERNS if pattern.search(text)]


def fetch() -> dict[str, dict]:
    query = urllib.parse.urlencode({'ids': ','.join(TICKERS), 'vs_currencies': 'usd', 'include_24hr_change': 'true'})
    request = urllib.request.Request(f'{PRICE_URL}?{query}', headers={'User-Agent': USER_AGENT,
                                                                     'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=5) as response:
        data = json.load(response)
    return {coin_id: {'id': coin_id, 'symbol': TICKERS[coin_id], 'name': NAMES[coin_id], 'usd': row['usd'],
                      'change_24h': row.get('usd_24h_change')}
            for coin_id in TICKERS if (row := data.get(coin_id)) and row.get('usd') is not None}


def prices() -> list[dict] | None:
    """Every known coin with a price, in market-cap order; None when CoinGecko is down and nothing is cached."""
    rows = cache.get('coins:fresh')
    if rows is None:
        try:
            rows = fetch()
        except (OSError, ValueError, KeyError, TypeError) as e:  # network, HTTP 429/5xx, broken JSON
            log.warning('CoinGecko prices: %s', e)
            rows = cache.get('coins:stale')
            if rows is None:
                return None
            cache.set('coins:fresh', rows, 30)  # do not hammer a failing API on every request
        else:
            cache.set('coins:fresh', rows, FRESH)
            cache.set('coins:stale', rows, STALE)
    return [rows[coin_id] for coin_id in TICKERS if coin_id in rows]
