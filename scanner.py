"""
Crypto Structural Breakout Scanner
==================================
Scans USDT pairs for real, calculable structural breakout setups
(trend + momentum + volume + price-action + volatility expansion),
then sends an alert two ways:
  1. Email  -> via Gmail SMTP (App Password)
  2. Phone app -> via Firebase Cloud Messaging push notification

This intentionally contains ONLY real math (ported from the original
TechnicalIndicatorEngine / BreakoutEngine). There is no random/fake
"institutional score" or hardcoded "BUY" signal anywhere in this file.
"""

import os
import json
import time
import smtplib
import logging
from email.mime.text import MIMEText
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import ccxt
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleAuthRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("breakout_scanner")

# =========================================================================
# CONFIG - everything is read from environment variables / GitHub Secrets
# so no secrets are ever hardcoded in this file.
# =========================================================================
TIMEFRAME          = os.getenv("TIMEFRAME", "1h")          # e.g. "15m", "1h", "4h"
QUOTE_CURRENCY     = os.getenv("QUOTE_CURRENCY", "USDT")

# EXCHANGE_ID is now optional. If set, only that exchange is used.
# If NOT set, the scanner tries a priority list of exchanges in order and
# uses the first one that actually responds from the runner's IP.
# This fixes the "CloudFront blocks your country" / 451 / geo-block issue
# without changing any strategy logic - it's purely a connection fallback.
EXCHANGE_ID         = os.getenv("EXCHANGE_ID", "")          # leave blank to auto-fallback
EXCHANGE_FALLBACK_LIST = ["okx", "kucoin", "gateio", "bybit", "mexc"]

TOP_N_COINS        = int(os.getenv("TOP_N_COINS", "60"))    # scan top N pairs by volume
CANDLE_LIMIT       = int(os.getenv("CANDLE_LIMIT", "300"))

RVOL_THRESHOLD       = float(os.getenv("RVOL_THRESHOLD", "2.0"))
RSI_THRESHOLD        = float(os.getenv("RSI_THRESHOLD", "60.0"))
ADX_THRESHOLD        = float(os.getenv("ADX_THRESHOLD", "25.0"))
EXTENSION_THRESHOLD  = float(os.getenv("EXTENSION_THRESHOLD", "0.10"))

GMAIL_ADDRESS       = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD")
ALERT_TO_EMAIL      = os.getenv("ALERT_TO_EMAIL", GMAIL_ADDRESS)

FCM_PROJECT_ID          = os.getenv("FCM_PROJECT_ID")
FCM_SERVICE_ACCOUNT_JSON = os.getenv("FCM_SERVICE_ACCOUNT_JSON")   # full JSON string (from GitHub Secret)
FCM_DEVICE_TOKEN        = os.getenv("FCM_DEVICE_TOKEN")            # copied once from the app after install

SEEN_ALERTS_FILE = "seen_alerts.json"

# =========================================================================
# 1. TECHNICAL INDICATORS (real math only, ported from TechnicalIndicatorEngine)
# =========================================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for p in (20, 50, 100, 200):
        df[f"ema_{p}"] = df["close"].ewm(span=p, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    fast = df["close"].ewm(span=12, adjust=False).mean()
    slow = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = fast - slow
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    plus_dm = df["high"].diff()
    minus_dm = df["low"].diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    tr_smooth = tr.ewm(alpha=1 / 14, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / tr_smooth.replace(0, np.nan))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1 / 14, adjust=False).mean() / tr_smooth.replace(0, np.nan))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["plus_di"] = plus_di.fillna(0)
    df["minus_di"] = minus_di.fillna(0)
    df["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean().fillna(0)

    df["vma_20"] = df["volume"].rolling(20).mean()
    df["rvol"] = df["volume"] / df["vma_20"].replace(0, np.nan)

    df["atr"] = tr.rolling(14).mean()
    df["atr"] = df["atr"].fillna(tr.ewm(span=14, adjust=False).mean())

    bb_mid = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid.replace(0, np.nan)

    # Supertrend
    hl2 = (df["high"] + df["low"]) / 2
    upper_b = (hl2 + 3.0 * df["atr"]).to_numpy()
    lower_b = (hl2 - 3.0 * df["atr"]).to_numpy()
    close_arr = df["close"].to_numpy()
    direction = np.ones(len(df))
    for i in range(1, len(df)):
        if close_arr[i - 1] <= upper_b[i - 1]:
            upper_b[i] = min(upper_b[i], upper_b[i - 1])
        if close_arr[i - 1] >= lower_b[i - 1]:
            lower_b[i] = max(lower_b[i], lower_b[i - 1])
        if close_arr[i] > upper_b[i - 1]:
            direction[i] = 1
        elif close_arr[i] < lower_b[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    df["supertrend_dir"] = direction

    return df


# =========================================================================
# 2. BREAKOUT DETECTION (real logic only, ported from BreakoutEngine)
# =========================================================================
def detect_breakout(df: pd.DataFrame) -> bool:
    """Evaluates the LAST FULLY CLOSED candle (index -2) so we never act
    on an in-progress candle."""
    if len(df) < 60:
        return False

    row = df.iloc[-2]
    prev = df.iloc[-3]

    trend_ok = (
        row["ema_20"] > row["ema_50"] > row["ema_200"]
        and row["close"] > row["ema_20"]
        and row["supertrend_dir"] == 1
    )
    mom_ok = (
        row["rsi"] > RSI_THRESHOLD
        and row["macd"] > row["macd_signal"]
        and row["adx"] > ADX_THRESHOLD
        and row["plus_di"] > row["minus_di"]
    )
    vol_ok = row["rvol"] >= RVOL_THRESHOLD and row["volume"] > row["vma_20"]

    highest_20 = df["high"].iloc[-22:-2].max()
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return False
    close_in_range = (row["close"] - row["low"]) / total_range
    body_pct = abs(row["close"] - row["open"]) / total_range
    upper_wick_pct = (row["high"] - max(row["open"], row["close"])) / total_range
    pa_ok = (
        row["close"] > highest_20
        and close_in_range >= 0.80
        and body_pct >= 0.60
        and upper_wick_pct <= 0.20
    )

    volatility_ok = row["bb_width"] > prev["bb_width"] and row["atr"] > prev["atr"]

    extended_too_far = (
        (row["close"] - row["ema_20"]) / row["ema_20"] > EXTENSION_THRESHOLD
        if row["ema_20"] else False
    )

    return trend_ok and mom_ok and vol_ok and pa_ok and volatility_ok and not extended_too_far


# =========================================================================
# 3. MARKET DATA / EXCHANGE CONNECTION
# =========================================================================
def build_exchange() -> ccxt.Exchange:
    """
    Connects to a working exchange from the current runner's IP.

    Why this exists: some exchanges (Bybit, Binance) block requests from
    certain cloud/datacenter IP ranges via CloudFront/WAF rules (403/451
    errors), and GitHub Actions runner IPs rotate and can land in a
    blocked range on any given run. This tries a priority list of
    exchanges and uses the first one that actually responds, so the
    scanner keeps working regardless of which country/IP the runner
    happens to get. No strategy logic is touched - this only affects
    where OHLCV candles come from.
    """
    candidates = [EXCHANGE_ID] if EXCHANGE_ID else EXCHANGE_FALLBACK_LIST

    last_error = None
    for ex_id in candidates:
        if not ex_id:
            continue
        try:
            exchange_class = getattr(ccxt, ex_id)
            exchange = exchange_class({"enableRateLimit": True})
            # cheap connectivity check - forces a real request now instead
            # of failing later mid-scan
            exchange.load_markets()
            logger.info(f"Connected successfully to exchange: {ex_id}")
            return exchange
        except Exception as e:
            logger.warning(f"Exchange '{ex_id}' unavailable from this runner ({e}). Trying next...")
            last_error = e
            continue

    raise RuntimeError(
        f"No exchange in the fallback list was reachable from this runner. "
        f"Last error: {last_error}"
    )


def get_top_symbols(exchange: ccxt.Exchange, n: int) -> list:
    markets = exchange.load_markets()
    tickers = exchange.fetch_tickers()
    usdt_pairs = [
        s for s in markets
        if markets[s].get("quote") == QUOTE_CURRENCY
        and markets[s].get("active", True)
        and markets[s].get("spot", True)
    ]
    ranked = sorted(
        usdt_pairs,
        key=lambda s: tickers.get(s, {}).get("quoteVolume") or 0,
        reverse=True,
    )
    return ranked[:n]


def fetch_ohlcv_df(exchange: ccxt.Exchange, symbol: str) -> pd.DataFrame:
    raw = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


# =========================================================================
# 4. ALERTS
# =========================================================================
def send_email_alert(symbol: str, row: pd.Series) -> None:
    if not (GMAIL_ADDRESS and GMAIL_APP_PASSWORD and ALERT_TO_EMAIL):
        logger.warning("Gmail credentials not set - skipping email alert.")
        return

    subject = f"Breakout Alert: {symbol}"
    body = (
        f"Structural breakout detected on {symbol} ({TIMEFRAME})\n\n"
        f"Close:  {row['close']:.6f}\n"
        f"RSI:    {row['rsi']:.2f}\n"
        f"ADX:    {row['adx']:.2f}\n"
        f"RVOL:   {row['rvol']:.2f}\n"
        f"Time:   {datetime.now(timezone.utc).isoformat()}\n\n"
        f"This is an automated technical alert, not financial advice."
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = ALERT_TO_EMAIL

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [ALERT_TO_EMAIL], msg.as_string())
    logger.info(f"Email alert sent for {symbol}")


def _get_fcm_access_token() -> str:
    creds_info = json.loads(FCM_SERVICE_ACCOUNT_JSON)
    scopes = ["https://www.googleapis.com/auth/firebase.messaging"]
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
    credentials.refresh(GoogleAuthRequest())
    return credentials.token


def send_app_push_alert(symbol: str, row: pd.Series) -> None:
    if not (FCM_PROJECT_ID and FCM_SERVICE_ACCOUNT_JSON and FCM_DEVICE_TOKEN):
        logger.warning("Firebase credentials not set - skipping app push alert.")
        return

    access_token = _get_fcm_access_token()
    url = f"https://fcm.googleapis.com/v1/projects/{FCM_PROJECT_ID}/messages:send"
    payload = {
        "message": {
            "token": FCM_DEVICE_TOKEN,
            "notification": {
                "title": f"Breakout: {symbol}",
                "body": f"Close {row['close']:.4f} | RSI {row['rsi']:.1f} | RVOL {row['rvol']:.1f}",
            },
            "data": {
                "symbol": symbol,
                "close": str(row["close"]),
                "rsi": str(row["rsi"]),
                "adx": str(row["adx"]),
                "rvol": str(row["rvol"]),
                "time": datetime.now(timezone.utc).isoformat(),
            },
        }
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; UTF-8",
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    if resp.status_code == 200:
        logger.info(f"App push alert sent for {symbol}")
    else:
        logger.error(f"FCM push failed for {symbol}: {resp.status_code} {resp.text}")


# =========================================================================
# 5. DEDUPLICATION (don't spam the same candle repeatedly)
# =========================================================================
def load_seen_alerts() -> dict:
    if os.path.exists(SEEN_ALERTS_FILE):
        with open(SEEN_ALERTS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen_alerts(seen: dict) -> None:
    with open(SEEN_ALERTS_FILE, "w") as f:
        json.dump(seen, f)


# =========================================================================
# 6. MAIN SCAN
# =========================================================================
def run_scan() -> None:
    exchange = build_exchange()
    seen = load_seen_alerts()

    symbols = get_top_symbols(exchange, TOP_N_COINS)
    logger.info(f"Scanning {len(symbols)} {QUOTE_CURRENCY} pairs on {TIMEFRAME} timeframe...")

    for symbol in symbols:
        try:
            df = fetch_ohlcv_df(exchange, symbol)
            if len(df) < 60:
                continue
            df = calculate_indicators(df)

            if detect_breakout(df):
                candle_ts = str(df.iloc[-2]["timestamp"])
                key = f"{symbol}_{candle_ts}"
                if seen.get(key):
                    continue  # already alerted for this exact candle

                row = df.iloc[-2]
                logger.info(f"BREAKOUT: {symbol} at {candle_ts}")
                send_email_alert(symbol, row)
                send_app_push_alert(symbol, row)

                seen[key] = True

        except ccxt.BaseError as e:
            logger.warning(f"Exchange error on {symbol}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error on {symbol}: {e}")

        time.sleep(exchange.rateLimit / 1000)

    # keep the seen-alerts file from growing forever
    if len(seen) > 5000:
        seen = dict(list(seen.items())[-2000:])
    save_seen_alerts(seen)

    logger.info("Scan complete.")


if __name__ == "__main__":
    run_scan()
