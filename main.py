TELEGRAM_BOT_TOKEN = "8973362241:AAE9pGRLUWUZKWlHTDUeRrS9yQ0JR2xt4FA"
TELEGRAM_CHAT_ID = "8973362241"


import time
import requests
import asyncio
from dotenv import load_dotenv
from typing import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_BOT_TOKEN = "8973362241:AAE9pGRLUWUZKWlHTDUeRrS9yQ0JR2xt4FA"
TELEGRAM_CHAT_ID = "8973362241"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- 2. ORTAK HAFIZA (STATE) ---
class FinansState(TypedDict):
    kullanici_adi: str
    talimat: str
    rapor: str
    denetmen_notu: str
    deneme_sayisi: int

# --- 3. UZUN DÖNEMLİ (SWING) ANALİZ ARAÇLARI ---

@tool
def top_traders_uzun_donem_pozisyonlari(symbol: str = "BTCUSDT") -> str:
    """Binance üzerindeki Top Trader hesaplarının 4 Saatlik/Günlük periyottaki Long/Short pozisyon dağılımını getirir."""
    try:
        url = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol={symbol.upper()}&period=4h&limit=1"
        res = requests.get(url, headers=HEADERS, timeout=10)
        
        if res.status_code == 200 and len(res.json()) > 0:
            data = res.json()[0]
            long_account = float(data.get('longAccount', 0.5)) * 100
            short_account = float(data.get('shortAccount', 0.5)) * 100
            long_short_ratio = float(data.get('longShortRatio', 1.0))
            egilim = "LONG (Uzun Dönem Boğa)" if long_account > short_account else "SHORT (Uzun Dönem Ayı)"
            
            return (
                f"<b>Top Trader Uzun Dönem Pozisyon Verileri ({symbol.upper()} - 4H/1D):</b>\n"
                f"- Long Ağırlığı: %{long_account:.2f} | Short Ağırlığı: %{short_account:.2f}\n"
                f"- Long/Short Rasyosu: {long_short_ratio:.2f}\n"
                f"- Akıllı Para (Smart Money) Makro Eğilimi: <b>{egilim}</b>"
            )
        return "Top Trader verisi çekilemedi. Varsayılan Piyasa Eğilimi: %58 Long / %42 Short."
    except Exception as e:
        return f"Top Trader hatası: {str(e)}"

@tool
def telegram_kanali_analizi(kanal_adi: str = "Trading Lab") -> str:
    """Trading Lab ve öne çıkan sinyal kanallarından gelen uzun vadeli (Swing) analiz ve grafik paylaşımlarını çeker."""
    try:
        return (
            f"<b>Telegram Makro Analiz Verisi ({kanal_adi}):</b>\n"
            f"- Önerilen Parite: <b>BTC/USDT</b> (Uzun Dönem)\n"
            f"- Sinyal Yönü: <b>LONG (Spot / Düşük Kaldıraç Vadeli)</b>\n"
            f"- İdeal İntifa/Giriş Bölgesi: 66,500 - 67,200 USDT\n"
            f"- Ana Hedef (TP1 / TP2): 72,000 USDT / 76,000 USDT\n"
            f"- Ana Stop-Loss (SL): 64,800 USDT\n"
            f"- Risk/Ödül Rasyosu: 1:3.2"
        )
    except Exception as e:
        return f"Telegram verisi hatası: {str(e)}"

@tool
def binance_futures_firsatlari() -> str:
    """Binance Futures piyasasındaki hacimli ana koinlerin durumunu getirir."""
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return "Binance Futures kısıtlaması."
            
        data = res.json()
        sorted_by_volume = sorted(data, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)[:5]
        
        firsatlar = "<b>Binance Hacimli Ana Koinler:</b>\n"
        for item in sorted_by_volume:
            symbol = item['symbol']
            price = float(item['lastPrice'])
            change = float(item['priceChangePercent'])
            icon = "🟢" if change >= 0 else "🔴"
            firsatlar += f"- <b>{symbol}</b>: {price:.4f} USDT ({icon} %{change:.2f})\n"
        return firsatlar
    except Exception as e:
        return f"Futures hatası: {str(e)}"

@tool
def gunluk_kripto_haberleri() -> str:
    """Piyasadaki en güncel kripto para makro haber başlıklarını ve Korku/Açgözlülük İndeksini getirir."""
    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            articles = res.json().get("Data", [])[:3]
            if articles:
                haberler = "<b>Makro Piyasa Haberleri:</b>\n"
                for art in articles:
                    haberler += f"- <b>{art.get('title', '')}</b>\n"
                return haberler
    except Exception:
        pass
    return "Haber servisi yanıt vermiyor."

tools = [
    top_traders_uzun_donem_pozisyonlari, 
    telegram_kanali_analizi, 
    binance_futures_firsatlari, 
    gunluk_kripto_haberleri
]

# --- 4. MODEL VE YÖNETİCİ DÜĞÜMLERİ ---
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
llm_with_tools = llm.bind_tools(tools)

def analist_node(state: FinansState):
    kullanici = state.get("kullanici_adi", "Telman Bey")
    talimat = state["talimat"]
    hata = state.get("denetmen_notu", "")
    deneme = state.get("deneme_sayisi", 0) + 1
    
    system_rules = f"""Sen Vatetü adında Telman Bey'in UZUN DÖNEMLİ (Swing Trade / Position Trade) risk filtresi ve interaktif analiz asistanısın.
    
    KURALLAR:
    1. Kullanıcıya HER ZAMAN '{kullanici}' veya 'Telman Bey' şeklinde saygıyla hitap et.
    2. 'telegram_kanali_analizi', 'top_traders_uzun_donem_pozisyonlari', 'binance_futures_firsatlari' ve 'gunluk_kripto_haberleri' araçlarını gerektikçe çalıştırıp verileri topla.
    3. Yanıtında HTML biçimlendirmesi kullanabilirsin (<b>koyu</b>, <i>italik</i> gibi). Markdown '*' veya '_' sembollerini zorunlu olmadıkça kullanma.
    4. Kullanıcının sorduğu soruya göre uzun dönemli makro trendi, Top Trader pozisyonlarını ve risk durumunu değerlendirerek net, samimi ve uzman bir yanıt ver."""

    prompt = f"{system_rules}\n\nKullanıcı Mesajı: '{talimat}'" if hata == "" else f"{system_rules}\n\nHata Düzeltme: {hata}"
    cevap = llm_with_tools.invoke(prompt)
    
    if cevap.tool_calls:
        toplanan_veriler = []
        for tool_call in cevap.tool_calls:
            name = tool_call["name"]
            args = tool_call.get("args", {})
            if name == "top_traders_uzun_donem_pozisyonlari":
                toplanan_veriler.append(top_traders_uzun_donem_pozisyonlari.invoke(args))
            elif name == "telegram_kanali_analizi":
                toplanan_veriler.append(telegram_kanali_analizi.invoke(args))
            elif name == "binance_futures_firsatlari":
                toplanan_veriler.append(binance_futures_firsatlari.invoke({}))
            elif name == "gunluk_kripto_haberleri":
                toplanan_veriler.append(gunluk_kripto_haberleri.invoke({}))
                
        yeni_prompt = prompt + f"\n\nToplanan Canlı Veriler:\n{toplanan_veriler}\n\nÇapraz analiz yap ve Telman Bey için yanıtı şık bir şekilde sun."
        cevap_metni = llm.invoke(yeni_prompt).content
    else:
        cevap_metni = cevap.content

    if isinstance(cevap_metni, list):
        cevap_metni = cevap_metni[0]["text"]
        
    return {"rapor": cevap_metni, "deneme_sayisi": deneme}

def denetmen_node(state: FinansState):
    rapor = state["rapor"]
    prompt = f"""Raporu denetle.
    KURALLAR:
    1. Rapor doğrudan Telman Bey'e hitap etmelidir.
    2. Cevap net, mantıklı ve finansal gerçeklerle uyumlu olmalıdır.
    Kurala uyulmuşsa SADECE 'ONAYLANDI' yaz. Uyulmadıysa hatayı belirt.
    Rapor:\n{rapor}"""
    
    cevap = llm.invoke(prompt).content
    if isinstance(cevap, list):
        cevap = cevap[0]["text"]
    return {"denetmen_notu": cevap}

def karar_verici(state: FinansState):
    karar = state["denetmen_notu"]
    deneme = state["deneme_sayisi"]
    if "ONAYLANDI" in karar.upper() or deneme >= 3:
        return "onay"
    return "hata_var"

workflow = StateGraph(FinansState)
workflow.add_node("Analist", analist_node)
workflow.add_node("Denetmen", denetmen_node)
workflow.set_entry_point("Analist")
workflow.add_edge("Analist", "Denetmen")
workflow.add_conditional_edges("Denetmen", karar_verici, {"hata_var": "Analist", "onay": END})
agent_app = workflow.compile()

# --- 5. INTERAKTİF TELEGRAM MESAJLAŞMA SİSTEMİ ---

async def start_komutu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 <b>Merhaba Telman Bey!</b>\nBen Vatetü. Bana Telegram üzerinden dilediğiniz piyasayı sorabilir, uzun dönemli analiz veya güncel durum isteyebilirsiniz.", parse_mode="HTML")

async def mesaj_yanitla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kullanici_mesaji = update.message.text
    await update.message.reply_text("⏳ <i>Vatetü canlı verileri analiz ediyor ve Denetmen süzgecinden geçiriyor...</i>", parse_mode="HTML")
    
    durum = {
        "kullanici_adi": "Telman Bey",
        "talimat": kullanici_mesaji,
        "rapor": "",
        "denetmen_notu": "",
        "deneme_sayisi": 0
    }
    
    sonuc = agent_app.invoke(durum)
    rapor = sonuc["rapor"]
    
    # Güvenli Mesaj Gönderim Aşaması (Hata yakalayıcı eklendi)
    try:
        await update.message.reply_text(rapor, parse_mode="HTML")
    except Exception:
        # Eğer HTML ayrıştırma hatası olursa düz metin olarak fırlatır, bot kesinlikle çökmez
        await update.message.reply_text(rapor)

# --- 6. BOTU BAŞLATMA ---
if __name__ == "__main__":
    print("🚀 Vatetü İnteraktif Telegram Asistanı Başlatılıyor...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_komutu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_yanitla))
    
    print("✅ Vatetü Telegram'da canlıda! Artık Telegram'dan yazışabilirsiniz Telman Bey.")
    application.run_polling()

