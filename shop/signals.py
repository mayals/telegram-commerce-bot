# shop/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from telegram import Bot

from .models import Order
from .tasks import notify_merchant_task


# --------------------------------------------------
# Create Telegram Bot ONCE
# --------------------------------------------------
try:
    bot = Bot(token=settings.BOT_TOKEN)
except Exception as e:
    bot = None
    print("❌ Telegram bot init failed:", e)


# --------------------------------------------------
# Order status change handler
# --------------------------------------------------
@receiver(post_save, sender=Order)
def order_status_changed(sender, instance: Order, created, **kwargs):
    """
    Fires on every Order save.
    - If created: do nothing
    - If updated:
        • Notify customer about status
        • Notify merchant ONLY when payment is successful (status='done')
    """

    if created:
        return

    print(f"🔄 Order #{instance.id} updated → status = {instance.status}")

    # --------------------------------------------------
    # 1️⃣ Notify CUSTOMER about status update
    # --------------------------------------------------
    status_text = {
        "pending": "⏳ Your order is waiting for confirmation.",
        "accepted": "🧑‍🍳 Your order is now being prepared.",
        "shipped": "🚚 Your order is on the way to you.",
        "done": "✅ Your order has been delivered. Thank you!",
        "cancelled": "❌ Your order was cancelled.",
    }

    if bot and instance.chat_id:
        try:
            bot.send_message(
                chat_id=instance.chat_id,
                text=(
                    f"🔔 <b>Order Update</b>\n\n"
                    f"🧾 <b>Order ID:</b> {instance.id}\n"
                    f"{status_text.get(instance.status, '')}"
                ),
                parse_mode="HTML"
            )
            print("✅ Customer notified")
        except Exception as e:
            print("❌ Failed to notify customer:", e)

    # --------------------------------------------------
    # 2️⃣ Notify MERCHANT only when PAID
    # --------------------------------------------------
    if instance.status == "done":
        print("📤 Sending PAID order to merchant")

        lines = [
            f"💰 <b>PAID ORDER #{instance.id}</b>",
            f"👤 Customer: {instance.customer_name or '—'}",
            f"📞 Phone: {instance.phone or '—'}",
            f"📍 Address: {instance.address or '—'}",
            f"💵 Total: {instance.total}",
            "",
            "🧾 <b>Items:</b>"
        ]

        for item in instance.items.all():
            lines.append(f"- {item.product.name} x{item.quantity}")

        notify_merchant_task.delay("\n".join(lines))
