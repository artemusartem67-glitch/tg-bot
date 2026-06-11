import os
import json
import requests
from datetime import datetime, timedelta
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, PreCheckoutQueryHandler,
    CallbackQueryHandler
)

# ========================
# НАСТРОЙКИ
# ========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ADMIN_ID = os.getenv("ADMIN_ID", "5508691200")  # Вставь свой Telegram ID для получения уведомлений

AI_MODEL = "openrouter/auto"

# Цены
STARS_PRICE = 100       # Telegram Stars
RUBLES_PRICE = 50       # Рублей
YMONEY_WALLET = ""      # Вставь номер кошелька ЮMoney

# Бесплатные сообщения для незарегистрированных
FREE_MESSAGES = 5

# ========================
# ХРАНИЛИЩЕ ПОДПИСОК (файл)
# ========================
SUBS_FILE = "subscriptions.json"

def load_subs():
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_subs(subs):
    with open(SUBS_FILE, "w") as f:
        json.dump(subs, f)

def is_subscribed(user_id: int) -> bool:
    subs = load_subs()
    uid = str(user_id)
    if uid not in subs:
        return False
    expiry = datetime.fromisoformat(subs[uid])
    return expiry > datetime.now()

def add_subscription(user_id: int, days: int = 30):
    subs = load_subs()
    uid = str(user_id)
    if uid in subs and datetime.fromisoformat(subs[uid]) > datetime.now():
        expiry = datetime.fromisoformat(subs[uid]) + timedelta(days=days)
    else:
        expiry = datetime.now() + timedelta(days=days)
    subs[uid] = expiry.isoformat()
    save_subs(subs)
    return expiry

def get_expiry(user_id: int):
    subs = load_subs()
    uid = str(user_id)
    if uid in subs:
        return datetime.fromisoformat(subs[uid])
    return None

# ========================
# СЧЁТЧИК БЕСПЛАТНЫХ СООБЩЕНИЙ
# ========================
FREE_COUNTS_FILE = "free_counts.json"

def load_counts():
    if os.path.exists(FREE_COUNTS_FILE):
        with open(FREE_COUNTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_counts(counts):
    with open(FREE_COUNTS_FILE, "w") as f:
        json.dump(counts, f)

def get_free_count(user_id: int) -> int:
    counts = load_counts()
    return counts.get(str(user_id), 0)

def increment_free_count(user_id: int):
    counts = load_counts()
    uid = str(user_id)
    counts[uid] = counts.get(uid, 0) + 1
    save_counts(counts)

# ========================
# ИСТОРИЯ РАЗГОВОРОВ
# ========================
conversation_history: dict[int, list] = {}

SYSTEM_PROMPT = """Ты умный и дружелюбный AI-ассистент в Telegram.
Отвечай на русском языке, если пользователь пишет по-русски.
Будь лаконичным, полезным и вежливым."""

# ========================
# КОМАНДЫ
# ========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    user_id = update.effective_user.id
    subscribed = is_subscribed(user_id)
    free_used = get_free_count(user_id)
    free_left = max(0, FREE_MESSAGES - free_used)

    if subscribed:
        expiry = get_expiry(user_id)
        status = f"✅ Подписка активна до {expiry.strftime('%d.%m.%Y')}"
    else:
        status = f"🆓 Бесплатных сообщений осталось: {free_left}/{FREE_MESSAGES}"

    await update.message.reply_text(
        f"👋 Привет, {user_name}!\n\n"
        f"Я AI-ассистент на базе нейросети.\n\n"
        f"{status}\n\n"
        "📌 Команды:\n"
        "/start — начало\n"
        "/subscribe — купить подписку\n"
        "/status — статус подписки\n"
        "/clear — очистить историю\n"
        "/help — помощь"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Как пользоваться ботом:*\n\n"
        "• Напиши любое сообщение — отвечу!\n"
        "• Помню контекст разговора.\n"
        "• /clear — начать с чистого листа.\n"
        "• /subscribe — купить подписку.\n\n"
        "💎 *Подписка:* 50₽ или 100 Stars/месяц\n"
        "Без подписки — 5 бесплатных сообщений.",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        expiry = get_expiry(user_id)
        await update.message.reply_text(
            f"✅ Подписка активна!\n"
            f"📅 Действует до: {expiry.strftime('%d.%m.%Y %H:%M')}"
        )
    else:
        free_used = get_free_count(user_id)
        free_left = max(0, FREE_MESSAGES - free_used)
        await update.message.reply_text(
            f"❌ Подписка не активна.\n"
            f"🆓 Бесплатных сообщений осталось: {free_left}/{FREE_MESSAGES}\n\n"
            "Купи подписку: /subscribe"
        )

async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑️ История очищена!")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ 100 Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("💳 50₽ через ЮMoney", callback_data="pay_ymoney")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "💎 *Подписка на 30 дней*\n\n"
        "Выбери способ оплаты:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "pay_stars":
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Подписка на AI-бота",
            description="Доступ к AI-ассистенту на 30 дней",
            payload="subscription_30days",
            currency="XTR",
            prices=[LabeledPrice("Подписка 30 дней", STARS_PRICE)],
        )

    elif query.data == "pay_ymoney":
        if YMONEY_WALLET:
            link = f"https://yoomoney.ru/to/{YMONEY_WALLET}/{RUBLES_PRICE}"
            keyboard = [[InlineKeyboardButton("💳 Оплатить", url=link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                f"💳 *Оплата через ЮMoney*\n\n"
                f"Сумма: *{RUBLES_PRICE}₽*\n\n"
                f"После оплаты напиши /paid — я активирую подписку вручную.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                "💳 *Оплата через ЮMoney*\n\n"
                f"Переведи *{RUBLES_PRICE}₽* на кошелёк:\n"
                f"`{YMONEY_WALLET or 'Кошелёк не настроен'}`\n\n"
                "После оплаты напиши /paid с чеком.",
                parse_mode="Markdown"
            )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    expiry = add_subscription(user_id, 30)

    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n\n"
        f"🎉 Подписка активирована на 30 дней!\n"
        f"📅 Действует до: {expiry.strftime('%d.%m.%Y')}"
    )

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=f"💰 Новая оплата!\n"
                     f"👤 {user_name} (ID: {user_id})\n"
                     f"⭐ {STARS_PRICE} Stars\n"
                     f"📅 До: {expiry.strftime('%d.%m.%Y')}"
            )
        except:
            pass

async def paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    await update.message.reply_text(
        "✅ Заявка на активацию отправлена!\n"
        "Администратор проверит оплату и активирует подписку."
    )
    if ADMIN_ID:
        try:
            keyboard = [[InlineKeyboardButton(
                f"✅ Активировать {user_name}",
                callback_data=f"activate_{user_id}"
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=int(ADMIN_ID),
                text=f"💳 Запрос на активацию ЮMoney!\n"
                     f"👤 {user_name} (ID: {user_id})\n"
                     f"Сумма: {RUBLES_PRICE}₽\n\n"
                     f"Проверь оплату и активируй:",
                reply_markup=reply_markup
            )
        except:
            pass

async def activate_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("activate_"):
        target_id = int(query.data.split("_")[1])
        expiry = add_subscription(target_id, 30)
        await query.message.reply_text(f"✅ Подписка активирована для {target_id} до {expiry.strftime('%d.%m.%Y')}")
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"✅ Подписка активирована!\n📅 Действует до: {expiry.strftime('%d.%m.%Y')}"
            )
        except:
            pass

# ========================
# ОБРАБОТКА СООБЩЕНИЙ
# ========================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_subscribed(user_id):
        free_used = get_free_count(user_id)
        if free_used >= FREE_MESSAGES:
            keyboard = [[InlineKeyboardButton("💎 Купить подписку", callback_data="show_subscribe")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ У тебя закончились бесплатные сообщения!\n\n"
                "Купи подписку за 50₽ или 100 Stars на 30 дней:",
                reply_markup=reply_markup
            )
            return
        increment_free_count(user_id)
        free_left = FREE_MESSAGES - free_used - 1
        if free_left <= 2 and free_left > 0:
            await update.message.reply_text(f"⚠️ Осталось бесплатных сообщений: {free_left}. Купи подписку: /subscribe")

    user_text = update.message.text
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

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
        conversation_history[user_id].append({"role": "assistant", "content": ai_reply})
        await update.message.reply_text(ai_reply)

    except requests.Timeout:
        await update.message.reply_text("⏱️ Превышено время ожидания. Попробуй ещё раз.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {str(e)}")

async def show_subscribe_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⭐ 100 Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton("💳 50₽ через ЮMoney", callback_data="pay_ymoney")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(
        "💎 *Подписка на 30 дней*\n\nВыбери способ оплаты:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ========================
# ЗАПУСК
# ========================

def main():
    print("🤖 Запуск Telegram AI-бота с подпиской...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("paid", paid_command))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(activate_handler, pattern="^activate_"))
    app.add_handler(CallbackQueryHandler(show_subscribe_callback, pattern="^show_subscribe$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
