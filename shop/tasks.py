# tasks.py
""" Your Celery task is calling an async Telegram bot function without awaiting it
Celery tasks are synchronous, but aiogram/telegram library uses async functions.
So Celery runs the task, but message is never actually sent."""
# FIX: Use asyncio.run() inside your Celery task
""" Make sure Celery never imports your bot.py
Celery must NOT import ApplicationBuilder or async handlers.
Bot = async
Celery = sync
If Celery imports bot.py → event loop breaks."""

# name of project   core 
#  to start Celery  - in terminal use "celery -A core worker -l info --pool=solo"




# shop/tasks.py
import requests
from celery import shared_task
from django.conf import settings
import requests
import json
import html


# TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def send_telegram_message_task(self, chat_id, text, reply_markup=None):
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        # ✅ DO NOT json.dumps
        if reply_markup:
            payload["reply_markup"] = reply_markup

        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

        resp = requests.post(url, json=payload, timeout=30)
        print("send_telegram_message_task-resp:", resp)


        # 🔍 LOG TELEGRAM ERROR MESSAGE
        if resp.status_code != 200:
            print("Telegram response-resp.test:", resp.text)

        resp.raise_for_status()
        return resp.json()

    except requests.exceptions.RequestException as e:
        raise self.retry(exc=e)
    
    
    
    
@shared_task
def notify_merchant_task(text):
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": settings.MERCHANT_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    response = requests.post(url, json=payload)
    print("notify_merchant_task response:", response.json())




