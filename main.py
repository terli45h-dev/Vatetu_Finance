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

def get_market_summary():
    """Binance API üzerinden hızlı veri çeker."""
    try:
        btc_res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT").json()
        eth_res = requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT").json()
        
        btc_price = float(btc_res.get("lastPrice", 0))
        btc_change = float(btc_res.get("priceChangePercent", 0))
        eth_price = float(eth_res.get("lastPrice", 0))
        eth_change = float(eth_res.get("priceChangePercent", 0))
        
        return f"BTC: ${btc_price:,.2f} (\%{btc_change:+.2f}) \vert{} ETH:${eth_price:,.2f} (%{eth_change:+.2f})"
    except Exception as e:
        return f"Piyasa verisi çekilemedi: {e}"

def generate_vatetu_report():
    """Analist-Critic mantığı ile 2 saatlik periyodik rapor üretir."""
    market_data = get_market_summary()
    
    system_prompt = (
        "Sen Vatetü adında otonom bir AI Swing/Position Trading asistanısın. "
        "Kullanıcı için 4H/1D trendleri kapsayan 2 saatlik periyodik özet raporu hazırlıyorsun. "
        "Yalnızca HTML biçimlendirmesi kullan (<b>, <i>, <code>). Markdown (`*, _`) KESİNLİKLE KULLANMA. "
        "Raporda Analist görüşü ve Critic (risk) değerlendirmesi net olsun."
    )
    
    user_prompt = f"Canlı Piyasa Verileri: {market_data}. Lütfen 2 saatlik periyodik swing/macro durum raporunu ve risk uyarını hazırla."
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    response = llm.invoke(messages)
    return response.content

async def send_scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    """Her 2 saatte bir çalışan zamanlanmış görev."""
    job_chat_id = context.job.chat_id
    try:
        report = generate_vatetu_report()
        await context.bot.send_message(
            chat_id=job_chat_id,
            text=f"<b>🕒 VATETÜ 2 SAATLİK OTO-RAPOR</b>\n\n{report}",
            parse_mode="HTML"
        )
    except Exception as e:
        # HTML hatası olursa Düz Metin (Plain Text) Fallback
        report_plain = generate_vatetu_report().replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
        await context.bot.send_message(
            chat_id=job_chat_id,
            text=f"🕒 VATETÜ 2 SAATLİK OTO-RAPOR\n\n{report_plain}"
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start komutu verilince çalışır ve 2 saatlik zamanlayıcıyı başlatır."""
    chat_id = update.effective_chat.id
    
    # Mevcut zamanlanmış görevleri temizle (mükerrer çalışmayı önlemek için)
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()
    
    # 2 Saatte bir çalışacak görevi ekle (7200 saniye = 2 saat)
    context.job_queue.run_repeating(
        send_scheduled_report,
        interval=7200,
        first=10,  # Komuttan 10 saniye sonra ilk raporu atar
        chat_id=chat_id,
        name=str(chat_id)
    )
    
    await update.message.reply_text(
        "<b>✅ Vatetü Oto-Raporlama Aktif!</b>\n\n"
        "Her 2 saatte bir otomatik piyasa analizi ve risk raporu bu sohbet üzerinden tarafınıza iletilecektir, Telman Bey.",
        parse_mode="HTML"
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    
    print("✅ Vatetü Telegram'da canlıda ve 2 saatlik zamanlayıcı hazır!")
    app.run_polling()

if __name__ == "__main__":
    main()
    


