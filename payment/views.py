# payment/views.py
# Method You’re Using Now (Success URL Redirect Method)
# Don't need to use stripe webhook. Use "success_url" redirect instead (works on localhost)
# If the customer closes the browser before reaching the success URL, your server will never be notified.

# payment/views.py

import os
import stripe
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from shop.models import Order, OrderItem
from shop.tasks import send_telegram_message_task
from delivery.models import Delivery
from telegram import InlineKeyboardButton, InlineKeyboardMarkup



stripe.api_key = settings.STRIPE_SECRET_KEY
BOT_TOKEN = os.getenv("BOT_TOKEN")



# helper function -- build_payment_success_message -- will be used later in stripe_success function
def build_payment_success_message(order, amount, currency):
    """
    Returns (text, reply_markup_json)
    reply_markup_json is a JSON string ready to send to Telegram (reply_markup field).
    """
    text = (
        "🎉 *Payment Successful!*\n\n"
        f"🧾 *Order ID:* {order.id}\n"
        f"💵 *Amount:* {amount} {currency}\n"
        f"📦 *Status:* Paid\n\n"
        "You can continue shopping → /shop"
    )

    keyboard = [
        [InlineKeyboardButton("📦 Track Delivery", callback_data=f"track_{order.id}")],
        [InlineKeyboardButton("ℹ️ Order Info", callback_data=f"info_{order.id}")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    return text, reply_markup.to_json()


def build_payment_success_buttons(order_id):
    """
    Returns inline buttons for Telegram after payment success
    """
    return {
        "inline_keyboard": [
            [{"text": "Track Delivery 🚚", "callback_data": f"track_{order_id}"}],
            [{"text": "View Order Info 🧾", "callback_data": f"info_{order_id}"}],
            [{"text": "Continue Shopping 🛒", "url": f"{settings.BASE_URL}/shop"}]
        ]
    }




# ------------------ CREATE CHECKOUT SESSION ------------------
@csrf_exempt
def create_checkout_session(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    items = OrderItem.objects.filter(order=order)
    if not items:
        return JsonResponse({"error": "No items in order"}, status=400)

    line_items = []
    for item in items:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": item.product.name},
                "unit_amount": int(item.price * 100),
            },
            "quantity": item.quantity,
        })

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=line_items,
        success_url=f"{settings.BASE_URL}/payment/stripe-success/?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
        cancel_url=f"{settings.BASE_URL}/payment/stripe-cancel/?order_id={order.id}",
    )

    order.stripe_session_id = session.id
    order.save()

    return JsonResponse({"url": session.url, "id": session.id})


# ------------------ STRIPE SUCCESS ------------------
@csrf_exempt
def stripe_success(request):
    session_id = request.GET.get("session_id")
    order_id = request.GET.get("order_id")

    if not session_id or not order_id:
        return JsonResponse({"error": "Missing session_id or order_id"}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    session = stripe.checkout.Session.retrieve(session_id)
    payment_status = session.payment_status
    amount = session.amount_total / 100
    currency = session.currency.upper()

    # Update order status
    order.status = "done" if payment_status == "paid" else "pending"
    order.save()

    if order.chat_id and payment_status == "paid":
        # Create delivery if not exists
        Delivery.objects.get_or_create(
            order=order,
            defaults={"status": "preparing", "current_location": "Warehouse", "eta": None}
        )

        # Prepare Telegram message with HTML and buttons
        text = (
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"🧾 <b>Order ID:</b> {order.id}\n"
            f"💵 <b>Amount:</b> {amount} {currency}\n"
            f"📦 <b>Status:</b> Paid"
        )

        reply_markup = {
            "inline_keyboard": [
                [{"text": "Track Delivery 🚚", "callback_data": f"track_{order.id}"}],
                [{"text": "Continue Shopping 🛒", "callback_data": "shop"}]
            ]
        }

        send_telegram_message_task.delay(
            chat_id=order.chat_id,
            text=text,
            reply_markup=reply_markup
        )


    # send to display in browser as json
    return JsonResponse({
        "order_id": order.id,
        "payment_status": payment_status,
        "amount": amount,
        "currency": currency,
        "order_status": order.status,
        "session_id": session_id
    })
    
    
    
    
# ------------------ STRIPE CANCEL ------------------
@csrf_exempt
def stripe_cancel(request):
    order_id = request.GET.get("order_id")
    if not order_id:
        return JsonResponse({"error": "Missing order_id"}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    order.status = "cancelled"
    order.save()

    if order.chat_id:
        msg = (
            f"⚠️ *Payment Cancelled*\n\n"
            f"🧾 *Order ID:* {order.id}\n"
            f"Your payment was cancelled.\n"
            f"You can try again → /checkout"
        )
        # Send message asynchronously via Celery task
        send_telegram_message_task.delay(chat_id=order.chat_id, text=msg)


    # send to display in browser as json
    return JsonResponse({"status": "cancelled", "order_id": order.id})
