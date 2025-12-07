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

from shop.models import Order, OrderItem  # adjust if your app name differs

logger = logging.getLogger(__name__)

# -----------------------
# Stripe config
# -----------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET") or getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
BASE_URL = os.getenv("BASE_URL") or getattr(settings, "BASE_URL", "http://localhost:8000")
print("BASE_URL=",BASE_URL)
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
    """
    Create a Stripe Checkout session for an existing Order.
    Expects POST. Returns JSON with {'url': session.url} on success.
    """
    # Get order
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    # Compute total
    total = Decimal(order.total or 0)
    if total == 0:
        items = OrderItem.objects.filter(order=order)
        total = sum((Decimal(item.price) * item.quantity for item in items), Decimal("0.00"))

    if total <= 0:
        return JsonResponse({"error": "Order has zero total"}, status=400)

    # Stripe expects integer amount in cents
    unit_amount = int((Decimal(str(total)) * Decimal("100")).quantize(Decimal("1")))

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": CURRENCY,
                        "product_data": {"name": f"Order #{order.id}"},
                        "unit_amount": unit_amount,
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{BASE_URL}/payment/stripe-success/?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
            cancel_url=f"{BASE_URL}/payment/stripe-cancel/?order_id={order.id}",
            metadata={"order_id": str(order.id)},
        )
    except Exception as e:
        logger.exception("Stripe Checkout Session creation failed: %s", e)
        return JsonResponse({"error": "Failed to create Stripe Checkout session", "details": str(e)}, status=500)

    # Optional: save session ID on order
    if hasattr(order, "stripe_session_id"):
        order.stripe_session_id = session.id
        order.save(update_fields=["stripe_session_id"])

    return JsonResponse({"url": session.url, "id": session.id})


# -----------------------
# Success / Cancel views
# -----------------------
def stripe_success(request):
    session_id = request.GET.get("session_id")
    order_id = request.GET.get("order_id")
    return JsonResponse({"status": "success", "session_id": session_id, "order_id": order_id})


def stripe_cancel(request):
    order_id = request.GET.get("order_id")
    return JsonResponse({"status": "cancelled", "order_id": order_id})


# -----------------------
# Stripe Webhook
# -----------------------
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    # Verify signature
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=STRIPE_WEBHOOK_SECRET
            )
            logger.info("Stripe webhook received: %s", event["type"])
        except ValueError:
            logger.error("Invalid payload")
            return HttpResponseBadRequest("Invalid payload")
        except stripe.error.SignatureVerificationError:
            logger.error("Invalid signature")
            return HttpResponseForbidden("Invalid signature")
    else:
        # For local testing only (unverified)
        try:
            event = json.loads(payload)
            logger.warning("Running webhook in UNVERIFIED mode")
        except Exception:
            logger.exception("Invalid JSON payload")
            return HttpResponseBadRequest("Invalid JSON payload")

    data = event.get("data", {}).get("object", {})
    event_type = event.get("type")

    # Checkout completed
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

        if data.get("payment_status") == "paid":
            order.status = "done"
        else:
            order.status = "pending"

        order.save()
        logger.info("Order %s updated to %s", order_id, order.status)

        # Notify Telegram user
        try:
            from telegram import Bot
            bot = Bot(token=settings.BOT_TOKEN)
            bot.send_message(
                chat_id=order.chat_id,
                text=f"🎉 Payment confirmed!\nYour order #{order.id} is paid successfully."
            )
        except Exception as e:
            logger.error("Failed to notify Telegram user: %s", e)

    return HttpResponse(status=200)
