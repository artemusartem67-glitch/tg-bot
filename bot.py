import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ========================
# НАСТРОЙКИ
# ========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Бесплатная модель (можно менять)
# Другие бесплатные: "mistralai/mistral-7b-instruct", "google/gemma-2-9b-it:free"
AI_MODEL = "openrouter/auto"

# История разговоров
conversation_history: dict[int, list] = {}

SYSTEM_PROMPT = """Ты умный и дружелюбный AI-ассистент в Telegram.
Отвечай на русском языке, если пользователь пишет по-русски.
Будь лаконичным, полезным и вежливым."""

# ========================
# КОМАНДЫ
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Привет, {user_name}!\n\n"
        "Я AI-ассистент на базе Llama 3. Просто напиши мне что-нибудь!\n\n"
        "📌 Команды:\n"
        "/start — начало\n"
        "/clear — очистить историю чата\n"
        "/help — помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Как пользоваться ботом:*\n\n"
        "• Напиши любое сообщение — я отвечу!\n"
        "• Я помню контекст нашего разговора.\n"
        "• /clear — начать разговор с чистого листа.\n\n"
        "Powered by Llama 3 (OpenRouter) 🧠",
        parse_mode="Markdown"
    )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑️ История очищена! Начинаем с чистого листа.")

# ========================
# ОБРАБОТКА СООБЩЕНИЙ
# ========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({
        "role": "user",
        "content": user_text
    })

    # Ограничиваем историю 20 сообщениями
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *conversation_history[user_id]
                ],
                "max_tokens": 1024,
            },
            timeout=30
        )

        data = response.json()

        if "error" in data:
            await update.message.reply_text(f"❌ Ошибка API: {data['error'].get('message', 'Неизвестная ошибка')}")
            return

        ai_reply = data["choices"][0]["message"]["content"]

        conversation_history[user_id].append({
            "role": "assistant",
            "content": ai_reply
        })

        await update.message.reply_text(ai_reply)

    except requests.Timeout:
        await update.message.reply_text("⏱️ Превышено время ожидания. Попробуй ещё раз.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

# ========================
# ЗАПУСК
# ========================

def main():
    print("🤖 Запуск Telegram AI-бота (OpenRouter)...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен! Нажми Ctrl+C для остановки.")
    app.run_polling()

if __name__ == "__main__":
    main()
