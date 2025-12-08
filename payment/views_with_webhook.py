# payment/views.py
# Recommended Production Method → Stripe Webhooks
# Stripe webhooks send payment status to your server even if user closes the browser.
# need webhook so need server not work on localhost 

import os
import json
import logging
from decimal import Decimal

import stripe
import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from shop.models import Order, OrderItem

logger = logging.getLogger(__name__)

# ----------------- Stripe Config -----------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET") or getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
BASE_URL = os.getenv("BASE_URL") or getattr(settings, "BASE_URL", "http://localhost:8000")
CURRENCY = os.getenv("PAYMENT_CURRENCY", "usd")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
else:
    logger.warning("STRIPE_SECRET_KEY is not set. Stripe calls will fail.")

# ----------------- Create Checkout Session -----------------
@require_POST
@csrf_exempt
def create_checkout_session(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    # Build line_items for Stripe
    line_items = []
    total = Decimal("0.00")
    items = OrderItem.objects.filter(order=order)
    for item in items:
        total += item.price * item.quantity
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

    if not line_items:
        return JsonResponse({"error": "No items in order"}, status=400)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=line_items,
            success_url=f"{BASE_URL}/payment/stripe-success/?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
            cancel_url=f"{BASE_URL}/payment/stripe-cancel/?order_id={order.id}",
            metadata={"order_id": str(order.id)},
        )
    except Exception as e:
        logger.exception("Stripe Checkout Session creation failed: %s", e)
        return JsonResponse({"error": "Failed to create Stripe Checkout session", "details": str(e)}, status=500)

    order.stripe_session_id = session.id
    order.save(update_fields=["stripe_session_id"])

    return JsonResponse({"url": session.url, "id": session.id})


# ----------------- Stripe Success -----------------
def stripe_success(request):
    """
    Called when Stripe redirects after successful payment.
    Returns JSON with full order/payment details.
    """
    session_id = request.GET.get("session_id")
    order_id = request.GET.get("order_id")

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"status": "error", "error": "Order not found"}, status=404)

    # Fetch Stripe session/payment details
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)
    except Exception as e:
        return JsonResponse({"status": "error", "error": f"Stripe retrieval failed: {str(e)}"}, status=500)

    items = OrderItem.objects.filter(order=order)
    order_items = [
        {
            "product_name": item.product.name,
            "description": item.product.description or "",
            "quantity": item.quantity,
            "price": float(item.price)
        }
        for item in items
    ]

    return JsonResponse({
        "status": "success",
        "order_id": order.id,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "email": order.email,
        "address": order.address,
        "total": float(order.total),
        "payment_status": order.status,
        "stripe_session_id": order.stripe_session_id,
        "stripe_payment_intent_id": order.stripe_payment_intent_id,
        "items": order_items,
        "stripe_payment_details": {
            "amount_received": payment_intent.amount_received / 100.0,
            "currency": payment_intent.currency,
            "payment_method": payment_intent.payment_method_types,
            "status": payment_intent.status
        }
    })


# ----------------- Stripe Cancel -----------------
def stripe_cancel(request):
    """
    Called when Stripe redirects after cancelled payment.
    Returns JSON with order info and guidance.
    """
    order_id = request.GET.get("order_id")
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"status": "cancelled", "error": "Order not found"}, status=404)

    items = OrderItem.objects.filter(order=order)
    order_items = [
        {
            "product_name": item.product.name,
            "quantity": item.quantity,
            "price": float(item.price)
        }
        for item in items
    ]

    return JsonResponse({
        "status": "cancelled",
        "order_id": order.id,
        "customer_name": order.customer_name,
        "total": float(order.total),
        "items": order_items,
        "message": "Payment was cancelled. You can retry using /checkout or browse /shop"
    })


# ----------------- Stripe Webhook -----------------
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    # Verify Stripe webhook
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=STRIPE_WEBHOOK_SECRET
            )
            logger.info("Webhook verified: %s", event["type"])
        except ValueError:
            return HttpResponseBadRequest("Invalid payload")
        except stripe.error.SignatureVerificationError:
            return HttpResponseForbidden("Invalid signature")
    else:
        try:
            event = json.loads(payload)
            logger.warning("Webhook running in UNVERIFIED mode")
        except Exception:
            return HttpResponseBadRequest("Invalid JSON payload")

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        order_id = data.get("metadata", {}).get("order_id")
        if not order_id:
            return HttpResponse(status=200)

        order = Order.objects.filter(id=order_id).first()
        if not order:
            return HttpResponse(status=200)

        order.stripe_session_id = data.get("id")
        order.stripe_payment_intent_id = data.get("payment_intent")

        # Payment status and message
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

        order.save()

        # Send Telegram message
        try:
            telegram_token = settings.BOT_TOKEN
            chat_id = order.chat_id
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            response = requests.post(url, data={"chat_id": chat_id, "text": msg_text})
            logger.info("Telegram message sent, response=%s", response.text)
        except Exception as e:
            logger.error("Failed to send Telegram message: %s", e)

    return HttpResponse(status=200)
