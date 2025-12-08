# payment/views.py

import os
import json
import logging
from decimal import Decimal

import stripe
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings

from shop.models import Order, OrderItem

logger = logging.getLogger(__name__)

# -----------------------
# Stripe config
# -----------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET") or getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
BASE_URL = os.getenv("BASE_URL") or getattr(settings, "BASE_URL", "http://localhost:8000")
CURRENCY = os.getenv("PAYMENT_CURRENCY", "usd")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY is not set. Stripe calls will fail.")


# -----------------------
# Create Checkout Session
# -----------------------
@require_POST
@csrf_exempt
def create_checkout_session(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    items = OrderItem.objects.filter(order=order)
    if not items.exists():
        return JsonResponse({"error": "Order has no items"}, status=400)

    line_items = []
    total = Decimal("0.00")
    for item in items:
        subtotal = item.price * item.quantity
        total += subtotal
        unit_amount = int((item.price * Decimal("100")).quantize(Decimal("1")))
        line_items.append({
            "price_data": {
                "currency": CURRENCY,
                "product_data": {
                    "name": item.product.name,
                    "description": item.product.description or "",
                },
                "unit_amount": unit_amount,
            },
            "quantity": item.quantity,
        })

    order.total = total
    order.save(update_fields=["total"])

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=line_items,
            success_url=f"{BASE_URL}/payment/stripe-success/?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
            cancel_url=f"{BASE_URL}/payment/stripe-cancel/?order_id={order.id}",
            metadata={"order_id": str(order.id)},
        )
        if hasattr(order, "stripe_session_id"):
            order.stripe_session_id = session.id
            order.save(update_fields=["stripe_session_id"])
    except Exception as e:
        logger.exception("Stripe Checkout Session creation failed: %s", e)
        return JsonResponse({"error": "Failed to create Stripe Checkout session", "details": str(e)}, status=500)

    return JsonResponse({"url": session.url, "id": session.id})


# -----------------------
# Stripe Webhook
# -----------------------
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except ValueError:
            return HttpResponseBadRequest("Invalid payload")
        except stripe.error.SignatureVerificationError:
            return HttpResponseForbidden("Invalid signature")
    else:
        try:
            event = json.loads(payload)
            logger.warning("Running webhook in UNVERIFIED mode")
        except Exception:
            return HttpResponseBadRequest("Invalid JSON payload")

    data = event.get("data", {}).get("object", {})
    event_type = event.get("type")

    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {})
        order_id = metadata.get("order_id")
        if not order_id:
            logger.error("No order_id in metadata")
            return HttpResponse(status=200)

        order = Order.objects.filter(id=order_id).first()
        if not order:
            logger.error("Order %s not found", order_id)
            return HttpResponse(status=200)

        order.stripe_session_id = data.get("id")
        order.stripe_payment_intent_id = data.get("payment_intent")

        # Telegram notification
        try:
            from telegram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            chat_id = order.chat_id

            if data.get("payment_status") == "paid":
                order.status = "done"
                msg_text = (
                    f"🎉 Payment Success!\n"
                    f"Your order #{order.id} has been paid successfully.\n"
                    f"You can continue shopping → /shop"
                )
            else:
                order.status = "pending"
                msg_text = (
                    f"⚠️ Payment Failed / Cancelled\n"
                    f"Don’t worry, you can try again using /checkout\n"
                    f"Or return to browsing → /shop"
                )

            order.save(update_fields=["status"])
            bot.send_message(chat_id=chat_id, text=msg_text)
        except Exception as e:
            logger.error("Failed to notify Telegram user: %s", e)

    return HttpResponse(status=200)


# -----------------------
# Success / Cancel endpoints (for browser testing)
# -----------------------
def stripe_success(request):
    session_id = request.GET.get("session_id")
    order_id = request.GET.get("order_id")
    return JsonResponse({"status": "success", "session_id": session_id, "order_id": order_id})

def stripe_cancel(request):
    order_id = request.GET.get("order_id")
    return JsonResponse({"status": "cancelled", "order_id": order_id})
