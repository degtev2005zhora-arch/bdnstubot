import os
import asyncio
import logging
import aiosqlite
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]
DB_FILE = "/tmp/users.db"  # Railway: /tmp сохраняется между перезапусками (частично)

# Токен вашего бота (замените на свой!)
#BOT_TOKEN = "8265553695:AAE9BLJhMSQZQgY4vYRSHw-FN1Zpwp4IpVo"

# Имя файла базы данных
#DB_FILE = "users.db"

# Интервал проверки уведомлений (в секундах)
#CHECK_INTERVAL = 10

# === Работа с базой данных ===

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                notification_status TEXT DEFAULT 'ожидание'
            )
        """)
        await db.commit()

# Замените на ваш реальный user_id
ADMIN_USER_ID = os.environ["ADMIN_USER_ID"]
#ADMIN_USER_ID = 1114301601  # ← ВАШ ID здесь

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ У вас нет прав на эту команду.")
        return

    if not context.args:
        await update.message.reply_text("UsageId: /delete_user <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id должен быть числом.")
        return

    # Удаляем из базы
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("DELETE FROM users WHERE user_id = ?", (target_user_id,))
        await db.commit()
        if cursor.rowcount > 0:
            await update.message.reply_text(f"✅ Пользователь {target_user_id} удалён.")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {target_user_id} не найден.")

async def add_or_update_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, notification_status)
            VALUES (?, ?, 'ожидание')
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """, (user_id, username))
        await db.commit()

async def get_users_to_notify():
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            SELECT user_id FROM users WHERE notification_status = 'ознакомить'
        """)
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def mark_notified(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            UPDATE users SET notification_status = 'отправлено'
            WHERE user_id = ?
        """, (user_id,))
        await db.commit()

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT user_id, username, notification_status FROM users")
        rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 База данных пуста.")
        return

    text = "📋 Список пользователей:\n\n"
    for user_id, username, status in rows:
        name = username or f"user{user_id}"
        text += f"ID: {user_id} | @{name} | {status}\n"

    # Telegram ограничивает длину сообщения (~4096 символов)
    # Если много пользователей — можно отправить файлом или по частям
    await update.message.reply_text(text[:4000])  # обрезаем на всякий случай

# === Обработчики команд ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await add_or_update_user(user.id, user.username or user.first_name)
    await update.message.reply_text(
        f"Привет, {user.first_name}! Ты добавлен в базу. "
        "Как только появится уведомление — я пришлю его."
    )

# === Фоновая задача для проверки уведомлений ===

async def notify_users(context: ContextTypes.DEFAULT_TYPE):
    user_ids = await get_users_to_notify()
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text="🔔 У вас новое уведомление!")
            await mark_notified(user_id)
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

# === Основная функция запуска ===

# async def main():
#     await init_db()

#     app = Application.builder().token(BOT_TOKEN).build()

#     # Команда /start
#     app.add_handler(CommandHandler("start", start))
#     app.add_handler(CommandHandler("delete_user", delete_user))
#     app.add_handler(CommandHandler("list_users", list_users))

#     # Запуск фоновой задачи каждые CHECK_INTERVAL секунд
#     job_queue = app.job_queue
#     job_queue.run_repeating(notify_users, interval=CHECK_INTERVAL, first=1)

#     # Запуск бота
#     await app.initialize()
#     await app.start()
#     await app.updater.start_polling()

#     # Ожидание завершения
#     try:
#         await asyncio.Event().wait()  # Бесконечное ожидание
#     finally:
#         await app.updater.stop()
#         await app.stop()
#         await app.shutdown()

# if __name__ == "__main__":
#     asyncio.run(main())

async def main():
    await init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete_user", delete_user))
    app.add_handler(CommandHandler("list_users", list_users))
    await app.bot.set_webhook(url=WEBHOOK_URL)
    await app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    asyncio.run(main())