import os
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

load_dotenv()

# Sabit Değişkenler
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8973362241:AAE9pGRLUWUZKWlHTDUeRrS9yQ0JR2xt4FA")
CHAT_ID = os.getenv("CHAT_ID", "8973362241")
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6IJLQdwobWNdB_nq5RIN3naVbuWkKBQ6Ebax-SiJ50vuw")

# Gemini LLM Yapılandırması
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash-lite",
    google_api_key=GEMINI_API_KEY,
    temperature=0.3
)

def get_crypto_summary():
    """Binance API üzerinden hızlı kripto verisi çeker."""
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT", timeout=5).json()
        eth_res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT", timeout=5).json()
        
        btc_price = float(btc_res.get("lastPrice", 0))
        btc_change = float(btc_res.get("priceChangePercent", 0))
        eth_price = float(eth_res.get("lastPrice", 0))
        eth_change = float(eth_res.get("priceChangePercent", 0))
        
        return f"BTC: ${btc_price:,.2f} (%{btc_change:+.2f}) | ETH: ${eth_price:,.2f} (%{eth_change:+.2f})"
    except Exception:
        return "Kripto verisi anlık alınamadı."

def generate_global_vatetu_report():
    """Kripto, Hisse Senetleri (ABD/BIST), Emtia, Fonlar ve Makro Piyasa Raporu üretir."""
    crypto_data = get_crypto_summary()
    
    system_prompt = (
        "Sen Vatetü adında evrensel bir AI Finansal Analist ve Swing Trading asistanısın. "
        "Görevin SADECE kripto paralarla sınırlı DEĞİLDİR. Global piyasalardaki tüm varlık sınıflarını kapsarsın:\n"
        "- Kripto Piyasası (BTC, ETH, Altcoinler)\n"
        "- Küresel Hisse Senetleri (S&P500, Nasdaq, BIST 100, Teknoloji Hisseleri)\n"
        "- Emtialar ve Döviz (Altın, Dolar/Euro, Brent Petrol)\n"
        "- Makro Trendler, Fonlar ve Likidite Akışları\n\n"
        "Yalnızca HTML biçimlendirmesi kullan (<b>, <i>, <code>). Markdown (*, _) KESİNLİKLE KULLANMA.\n"
        "Raporunda Analist öngörünü ve Critic (Risk/Eleştirmen) değerlendirmesini açıkça belirt."
    )
    
    user_prompt = (
        f"Anlık Kripto Özeti: {crypto_data}\n\n"
        "Lütfen son 2 saatlik küresel piyasa durumunu değerlendir. "
        "Kripto, ABD/BIST Hisseleri, Altın/Petrol emtiaları ve fon akışlarını kapsayan "
        "makro özet swing analizini ve risk uyarını hazırla."
    )
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    response = llm.invoke(messages)
    return response.content

async def send_scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """Her 2 saatte bir çalışan küresel küme zamanlanmış görevi."""
    job_chat_id = context.job.chat_id
    try:
        report = generate_global_vatetu_report()
        await context.bot.send_message(
            chat_id=job_chat_id,
            text=f"<b>🌐 VATETÜ KÜRESEL PİYASA RAPORU (2 SAATLİK)</b>\n\n{report}",
            parse_mode="HTML"
        )
    except Exception:
        # HTML hatası durumunda Düz Metin Fallback
        report_plain = generate_global_vatetu_report().replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
        await context.bot.send_message(
            chat_id=job_chat_id,
            text=f"🌐 VATETÜ KÜRESEL PİYASA RAPORU (2 SAATLİK)\n\n{report_plain}"
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu verilince 2 saatlik küresel raporlama zamanlayıcısını başlatır."""
    chat_id = update.effective_chat.id
    
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()
    
    context.job_queue.run_repeating(
        send_scheduled_report,
        interval=7200,  # 2 Saat
        first=10,
        chat_id=chat_id,
        name=str(chat_id)
    )
    
    await update.message.reply_text(
        "<b>🌐 Vatetü Küresel Piyasa Raporlaması Aktif!</b>\n\n"
        "Kripto, Hisse Senetleri (ABD/BIST), Altın, Petrol ve Fon akışlarını içeren "
        "2 saatlik otonom analiziniz başlatılmıştır, Telman Bey.",
        parse_mode="HTML"
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    
    print("✅ Vatetü Küresel Finans Moduyla Canlıda!")
    app.run_polling()

if __name__ == "__main__":
    main()
