# shop/signals.py

import os
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Order, OrderItem
from telegram import Bot



try:
    bot = Bot(token=settings.BOT_TOKEN)
except Exception:
    bot = None



@receiver(post_save, sender=Order)
def notify_merchant_on_order(sender, instance: Order, created, **kwargs):
    """
    When an order is created, notify merchant chat ID with order summary.
    """
    if not created:
        return

    merchant_chat = getattr(settings, "MERCHANT_CHAT_ID", None)
    if not merchant_chat or not bot:
        return

    # Build message text
    items = OrderItem.objects.filter(order=instance)
    lines = [f"🆕 New Order #{instance.id}"]
    lines.append(f"Customer: {instance.customer_name or '—'}")
    lines.append(f"Phone: {instance.phone or '—'}")
    lines.append(f"Address: {instance.address or '—'}")
    lines.append(f"Total: {instance.total}")
    lines.append("Items:")
    for it in items:
        lines.append(f"- {it.product.name} x{it.quantity} @ {it.price}")

    message = "\n".join(lines)

    try:
        bot.send_message(chat_id=merchant_chat, text=message)
    except Exception as e:
        # optional: log or pass
        print("Failed to notify merchant:", e)
        
        
        
        


bot = Bot(token=settings.BOT_TOKEN)

@receiver(post_save, sender=Order)
def send_status_update(sender, instance, **kwargs):
    
    """Whenever admin changes order status in Django admin →  Telegram bot sends message automatically."""
   
    status_text = {
        "pending": "⏳ Your order is waiting for confirmation.",
        "accepted": "🧑‍🍳 Your order is now being prepared.",
        "shipped": "🚚 Your order is on the way to you.",
        "done": "✅ Your order has been delivered. Thank you!",
        "cancelled": "❌ Your order was cancelled.",
    }

    bot.send_message(
        chat_id=instance.chat_id,
        text=f"🔔 *Order Update*\nOrder #{instance.id}\n{status_text.get(instance.status, '')}",
        parse_mode="Markdown"
    )

