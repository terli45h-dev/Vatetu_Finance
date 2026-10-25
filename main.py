#!/usr/bin/env python3
"""
BINANCE FUTURES TOP 10 TARAYICI - GELİŞMİŞ V4
- Binance Futures API kullanır.
- Başlangıçta ve belirli aralıklarla hacme göre Top 10 coinini seçer.
- LONG: EMA200 üstü + Fibo (0.382-0.618) + Bullish FVG + Hacim.
- SHORT: EMA200 altı + Fibo (0.5-0.618) + Bearish FVG + Hacim.
- Telegram'a anlık sinyal gönderir.
"""

import os
import csv
import time
import html
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True, encoding="utf-8-sig")

# ══════════════ AYARLAR ══════════════
INTERVAL      = "4h"
LIMIT         = 300           
SCAN_SEC      = 300           # 5 dakikada bir tarama
START_BALANCE = 1000.0
TOP_N_COINS   = 10            # Taranacak coin sayısı (İstersen 20 yapabilirsin)

# BINANCE FUTURES API URL'LERİ
FUTURES_BASE_URL = "https://fapi.binance.com"
KLINES_URL       = f"{FUTURES_BASE_URL}/fapi/v1/klines"
TICKER_24H_URL   = f"{FUTURES_BASE_URL}/fapi/v1/ticker/24hr"

# RİSK YÖNETİMİ (Paper Trading için)
RISK_PER_TRADE_PCT = 0.02     
MAX_MARGIN_PCT     = 0.50     

# İNDİKATÖR AYARLARI
ATR_PERIOD    = 14
SL_ATR_MULT   = 1.5           
TP_ATR_MULT   = 3.0           
VOLUME_MA_LEN = 20            
VOLUME_MULT   = 1.2           

FEE           = 0.001
SUMMARY_EVERY = 12            
TRADE_LOG     = Path(__file__).resolve().parent / "paper_trades_futures.csv"

TG_TOKEN   = os.getenv("8973362241:AAE9pGRLUWUZKWlHTDUeRrS9yQ0JR2xt4FA")
TG_CHAT_ID = os.getenv("7718824545")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("paper_bot_futures.log", encoding="utf-8")],
)
log = logging.getLogger("futures_scanner")

ALLOW_SHORT = True

# ══════════════ TELEGRAM ══════════════
def tg_send(text: str):
    if not (TG_TOKEN and TG_CHAT_ID):
        log.warning("Telegram Token veya Chat ID eksik!")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Telegram hatası: {e}")

# ══════════════ TOP 10 COIN BULUCU ══════════════
def get_top_futures_symbols(limit=10) -> list:
    """Binance Futures'ta 24 saatlik hacme göre en yüksek coinleri döndürür."""
    try:
        r = requests.get(TICKER_24H_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        # Sadece USDT paritelerini al
        usdt_pairs = [d for d in data if d['symbol'].endswith('USDT')]
        # Hacme (quoteVolume) göre büyükten küçüğe sırala
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        symbols = [d['symbol'] for d in sorted_pairs[:limit]]
        log.info(f"Güncel Top {limit} Coin: {symbols}")
        return symbols
    except Exception as e:
        log.error(f"Top coin çekilemedi: {e}")
        # Hata olursa varsayılan popüler coinler
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]

# ══════════════ MATEMATİKSEL HESAPLAMALAR ══════════════
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.ewm(alpha=1/period, adjust=False).mean()

def find_recent_swings(df: pd.DataFrame, lookback: int = 20, window: int = 3):
    recent_df = df.tail(lookback)
    local_max = recent_df['high'][(recent_df['high'].shift(window) < recent_df['high']) & 
                                  (recent_df['high'].shift(-window) < recent_df['high'])]
    local_min = recent_df['low'][(recent_df['low'].shift(window) > recent_df['low']) & 
                                 (recent_df['low'].shift(-window) > recent_df['low'])]
    swing_high = local_max.max() if not local_max.empty else recent_df['high'].max()
    swing_low = local_min.min() if not local_min.empty else recent_df['low'].min()
    return swing_high, swing_low

def get_bullish_fvg(df: pd.DataFrame, lookback: int = 15) -> dict | None:
    recent = df.tail(lookback)
    for i in range(len(recent)-3, 0, -1):
        c1_high = recent['high'].iloc[i]
        c3_low = recent['low'].iloc[i+2]
        if c1_high < c3_low:
            fvg_top = c3_low
            fvg_bottom = c1_high
            if recent['low'].iloc[i+3:].min() <= fvg_top:
                return {"top": fvg_top, "bottom": fvg_bottom}
    return None

def get_bearish_fvg(df: pd.DataFrame, lookback: int = 15) -> dict | None:
    recent = df.tail(lookback)
    for i in range(len(recent)-3, 0, -1):
        c1_low = recent['low'].iloc[i]
        c3_high = recent['high'].iloc[i+2]
        if c1_low > c3_high:
            fvg_top = c1_low
            fvg_bottom = c3_high
            if recent['high'].iloc[i+3:].max() >= fvg_bottom:
                return {"top": fvg_top, "bottom": fvg_bottom}
    return None

# ══════════════ VERİ & SİNYAL ══════════════
def fetch_klines(symbol: str) -> pd.DataFrame | None:
    try:
        r = requests.get(KLINES_URL, params={"symbol": symbol, "interval": INTERVAL, "limit": LIMIT}, timeout=10)
        r.raise_for_status()
        df = pd.DataFrame(r.json(), columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "trades", "tbbav", "tbqav", "ignore",
        ])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df.index = pd.to_datetime(df["open_time"], unit="ms")
        return df[["open", "high", "low", "close", "volume"]]
    except Exception as e:
        log.error(f"{symbol} veri hatası: {e}")
        return None

def compute_signal(df: pd.DataFrame) -> dict | None:
    if len(df) < 250: return None
    
    current_price = float(df["close"].iloc[-1])
    c = df["close"]
    
    e200 = c.ewm(span=200, adjust=False).mean().iloc[-1]
    is_uptrend = current_price > e200
    is_downtrend = current_price < e200
    
    if not (is_uptrend or is_downtrend): return None

    vol_ma = df['volume'].rolling(window=VOLUME_MA_LEN).mean().iloc[-1]
    current_vol = df['volume'].iloc[-1]
    volume_spike = current_vol > (vol_ma * VOLUME_MULT)
    if not volume_spike: return None

    sh, sl_val = find_recent_swings(df)
    fib_range = sh - sl_val
    if fib_range <= 0: return None
    
    fib_382_long = sh - (fib_range * 0.382)
    fib_618_long = sh - (fib_range * 0.618)
    
    fib_500_short = sl_val + (fib_range * 0.500)
    fib_618_short = sl_val + (fib_range * 0.618)

    atr = calculate_atr(df, ATR_PERIOD).iloc[-1]

    if is_uptrend:
        in_fib_zone = (fib_618_long <= current_price <= fib_382_long)
        fvg = get_bullish_fvg(df)
        in_fvg = (fvg['bottom'] * 0.998 <= current_price <= fvg['top'] * 1.002) if fvg else False
        if in_fib_zone and in_fvg:
            return {
                "direction": "LONG", "price": current_price, "atr": atr, "sl_val": sl_val,
                "reasons": ["EMA200 Trend Yukarı", f"Hacim (x{VOLUME_MULT})", "Fibo Discount (0.382-0.618)", "Bullish FVG"], 
                "candle": df.index[-1]
            }

    if ALLOW_SHORT and is_downtrend:
        in_fib_short_zone = (fib_500_short <= current_price <= fib_618_short * 1.002)
        fvg_bear = get_bearish_fvg(df)
        in_fvg_bear = (fvg_bear['bottom'] * 0.998 <= current_price <= fvg_bear['top'] * 1.002) if fvg_bear else False

        if in_fib_short_zone and in_fvg_bear:
            return {
                "direction": "SHORT", "price": current_price, "atr": atr, "sl_val": sh,
                "reasons": ["EMA200 Trend Aşağı", f"Hacim (x{VOLUME_MULT})", "Fibo Premium (0.5-0.618)", "Bearish FVG"], 
                "candle": df.index[-1]
            }
    
    return None

# ══════════════ BROKER (SANAL İŞLEM) ══════════════
class PaperBroker:
    def __init__(self):
        self.cash = START_BALANCE
        self.positions: dict[str, dict] = {}
        if not TRADE_LOG.exists():
            with open(TRADE_LOG, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "opened", "closed", "symbol", "side", "entry", "exit", "result",
                    "hours", "max_up_pct", "max_down_pct", "pnl_usd", "pnl_pct",
                    "balance_after", "entry_reasons", "explanation",
                ])

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for sym, p in self.positions.items():
            total += p["margin"]
            if sym in prices:
                sign = 1 if p["side"] == "LONG" else -1
                total += sign * p["qty"] * (prices[sym] - p["entry"])
        return total

    def open(self, sym: str, sig: dict) -> str | None:
        if sym in self.positions: return None
        
        price = sig["price"]
        atr = sig["atr"]
        is_long = sig["direction"] == "LONG"
        
        if is_long:
            sl_atr = price - (atr * SL_ATR_MULT)
            sl_swing = sig["sl_val"] * 0.995
            sl = max(sl_atr, sl_swing)
            tp = price + (atr * TP_ATR_MULT)
        else:
            sl_atr = price + (atr * SL_ATR_MULT)
            sl_swing = sig["sl_val"] * 1.005
            sl = min(sl_atr, sl_swing)
            tp = price - (atr * TP_ATR_MULT)
            
        risk_amount = self.equity({}) * RISK_PER_TRADE_PCT
        risk_per_unit = abs(price - sl)
        if risk_per_unit <= 0: return None
        
        qty = risk_amount / risk_per_unit
        size = qty * price 
        
        max_size = self.equity({}) * MAX_MARGIN_PCT
        if size > max_size:
            size = max_size
            qty = size / price
            risk_amount = qty * risk_per_unit

        fee = size * FEE
        if self.cash < size + fee: return None

        self.cash -= size + fee
        breakeven_price = price + (price * FEE * 2) if is_long else price - (price * FEE * 2)

        self.positions[sym] = {
            "side": sig["direction"], "entry": price, "qty": qty,
            "margin": size, "fee": fee, "sl": sl, "tp": tp,
            "initial_sl": sl, "breakeven_price": breakeven_price,
            "opened": datetime.now(), "hi": price, "lo": price,
            "reasons": sig["reasons"], "trailing_activated": False
        }

        reasons_txt = "\n".join(f"  ✅ {r}" for r in sig["reasons"])
        return (
            f"🚨 <b>AVANTAJ BULUNDU — {html.escape(sym)}</b> 🚨\n"
            f"<b>Yön:</b> {sig['direction']}\n"
            f"<b>Gerekçeler:</b>\n{html.escape(reasons_txt)}\n\n"
            f"Giriş Fiyatı: <code>{price:.6g}</code>\n"
            f"Stop-Loss: <code>{sl:.6g}</code>\n"
            f"Take-Profit: <code>{tp:.6g}</code>\n\n"
            f"<i>(Bu bir sanal işlem sinyalidir, yatırım tavsiyesi değildir.)</i>"
        )

    def track(self, sym: str, high: float, low: float):
        p = self.positions.get(sym)
        if not p: return
        p["hi"] = max(p["hi"], high)
        p["lo"] = min(p["lo"], low)

        if not p["trailing_activated"]:
            if p["side"] == "LONG":
                one_r_level = p["entry"] + (p["entry"] - p["initial_sl"])
                if p["hi"] >= one_r_level:
                    p["sl"] = p["breakeven_price"]
                    p["trailing_activated"] = True
            else:
                one_r_level = p["entry"] - (p["initial_sl"] - p["entry"])
                if p["lo"] <= one_r_level:
                    p["sl"] = p["breakeven_price"]
                    p["trailing_activated"] = True

    def check_exit(self, sym: str, high: float, low: float) -> str | None:
        p = self.positions.get(sym)
        if not p: return None
        if p["side"] == "LONG":
            if low <= p["sl"]: return self._close(sym, p["sl"], "STOP" if not p["trailing_activated"] else "BREAKEVEN")
            if high >= p["tp"]: return self._close(sym, p["tp"], "TP")
        else:
            if high >= p["sl"]: return self._close(sym, p["sl"], "STOP" if not p["trailing_activated"] else "BREAKEVEN")
            if low <= p["tp"]: return self._close(sym, p["tp"], "TP")
        return None

    def _close(self, sym: str, price: float, result: str) -> str:
        p = self.positions.pop(sym)
        now = datetime.now()
        is_long = p["side"] == "LONG"
        
        sign = 1 if is_long else -1
        gross = p["qty"] * (price - p["entry"]) * sign
        exit_fee = p["qty"] * price * FEE
        self.cash += p["margin"] + gross - exit_fee
        net = gross - exit_fee - p["fee"]
        pct = net / p["margin"]
        
        if is_long:
            max_up = (p["hi"] - p["entry"]) / p["entry"] * 100
            max_down = (p["lo"] - p["entry"]) / p["entry"] * 100
        else:
            max_up = (p["entry"] - p["lo"]) / p["entry"] * 100
            max_down = (p["entry"] - p["hi"]) / p["entry"] * 100

        if result == "TP": why = "Hedefe ulaşıldı, kâr alındı."
        elif result == "BREAKEVEN": why = "1R'ye ulaşıldı, stop maliyete çekildi."
        else: why = "Stop seviyesi kırıldı."

        emoji = "✅" if net > 0 else "❌"
        title = "KÂR" if net > 0 else "ZARAR"
        return (
            f"{emoji} <b>İŞLEM KAPANDI — {html.escape(sym)} ({title})</b>\n"
            f"Yön: {p['side']} | Sonuç: {result}\n"
            f"Net Kâr/Zarar: <b>{net:+.2f} USDT (%{pct*100:+.2f})</b>\n"
            f"Neden: {why}"
        )

# ══════════════ ANA DÖNGÜ ══════════════
def main():
    broker = PaperBroker()
    last_candle: dict[str, object] = {}
    scan_no = 0
    symbols = get_top_futures_symbols(TOP_N_COINS)

    tg_send(f"🤖 <b>FUTURES TOP {TOP_N_COINS} TARAYICI BAŞLADI</b>\n"
            f"Taranan Coinler: {', '.join(symbols)}\n"
            f"Strateji: EMA200 + Fibo + FVG + Hacim")

    try:
        while True:
            scan_no += 1
            prices = {}
            
            # Her 12 taramada bir (1 saatte bir) Top 10 listesini güncelle
            if scan_no % SUMMARY_EVERY == 0:
                symbols = get_top_futures_symbols(TOP_N_COINS)

            for sym in symbols:
                try:
                    df = fetch_klines(sym)
                    if df is None or len(df) < 250: continue
                    
                    forming = df.iloc[-1]
                    prices[sym] = float(forming["close"])

                    broker.track(sym, forming["high"], forming["low"])
                    msg = broker.check_exit(sym, forming["high"], forming["low"])
                    if msg: tg_send(msg)

                    sig = compute_signal(df.iloc[:-1])
                    if sig and last_candle.get(sym) != sig["candle"]:
                        msg = broker.open(sym, sig)
                        if msg:
                            last_candle[sym] = sig["candle"]
                            tg_send(msg)
                            log.info(f"SİNYAL YAKALANDI: {sym} {sig['direction']}")
                            
                except Exception as e:
                    log.error(f"{sym} taranırken hata: {e}")
                
                # API Rate limit'e takılmamak için her coinden sonra 0.5 saniye bekle
                time.sleep(0.5)

            if scan_no % SUMMARY_EVERY == 0:
                eq = broker.equity(prices)
                tg_send(f"📊 <b>Saatlik Özet</b>\nSanal Bakiye: {eq:.2f} USDT\nAçık Pozisyon: {len(broker.positions)}")

            log.info(f"Tarama tamamlandı. {SCAN_SEC} saniye bekleniyor...")
            time.sleep(SCAN_SEC)
            
    except KeyboardInterrupt:
        log.info("Bot durduruldu.")

if __name__ == "__main__":
    main()
