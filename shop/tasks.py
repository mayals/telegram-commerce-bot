# tasks.py
""" Your Celery task is calling an async Telegram bot function without awaiting it
Celery tasks are synchronous, but aiogram/telegram library uses async functions.
So Celery runs the task, but message is never actually sent."""
# FIX: Use asyncio.run() inside your Celery task

#  to start Celery  - in terminal use "celery -A core worker -l info --pool=solo"

# shop/tasks.py

# shop/tasks.py
import os
from celery import shared_task
from aiogram import Bot
from asgiref.sync import async_to_sync

# Telegram bot token
BOT_TOKEN = os.getenv("BOT_TOKEN")  # or set directly: BOT_TOKEN = "your_bot_token_here"
bot = Bot(token=BOT_TOKEN)

@shared_task
def send_telegram_message_task(chat_id, text):
    """
    Sends a Telegram message using aiogram in a synchronous Celery task.
    """
    try:
        async_to_sync(bot.send_message)(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        )
        print(f"Telegram message sent to {chat_id}")
        return {"ok": True}
    except Exception as e:
        print(f"Error sending Telegram message to {chat_id}: {e}")
        return {"ok": False, "error": str(e)}
