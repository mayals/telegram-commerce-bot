# telegram-commerce-bot/bot.py

import os
import django
from decimal import Decimal
import requests
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from asgiref.sync import sync_to_async

# ======================
# Django Init
# ======================
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from shop.models import Category, Product, Order, OrderItem

# ======================
# Telegram + MyFatoorah Config
# ======================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

MYFATOORAH_TOKEN = "SK_TEST_XXXX"   # API v3 key
MF_API_URL = "https://apitest.myfatoorah.com/v2"   # v2+ endpoint (supports v3)

CALLBACK_URL = "https://YOUR_DOMAIN.com/payment/callback/"


# ======================================================================
# 🔍 Validate MyFatoorah API Token at startup (AUTO-DETECT INVALID TOKENS)
# ======================================================================
def validate_myfatoorah_token():
    url = f"{MF_API_URL}/GetPaymentStatus"
    headers = {"Authorization": f"Bearer {MYFATOORAH_TOKEN}", "Content-Type": "application/json"}

    # Using invalid InvoiceId on purpose — just to test authorization
    payload = {"Key": "123456", "KeyType": "invoiceId"}

    try:
        response = requests.post(url, json=payload, headers=headers)
    except:
        print("❌ Cannot reach MyFatoorah servers.")
        return False

    if response.status_code == 401:
        print("❌ ERROR: Invalid MyFatoorah API Token!")
        return False

    print("✅ MyFatoorah Token is valid.")
    return True


validate_myfatoorah_token()


# ======================
# Helper Functions
# ======================

@sync_to_async
def get_categories():
    return list(Category.objects.all())


@sync_to_async
def get_products(category_id):
    return list(Product.objects.filter(category_id=category_id))


@sync_to_async
def create_order(user_id, items):
    order = Order.objects.create(user_id=user_id)

    for product, qty in items:
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=qty,
            price=product.price
        )
    return order


# ======================================================================
# 🧾 MyFatoorah API v3 Payment Request
# ======================================================================
def create_myfatoorah_payment(order_id, amount, customer_name):
    url = f"{MF_API_URL}/ExecutePayment"
    headers = {
        "Authorization": f"Bearer {MYFATOORAH_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "PaymentMethodId": 1,   # KNET / Check MyFatoorah dashboard
        "CustomerName": customer_name,
        "InvoiceValue": float(amount),
        "DisplayCurrencyIso": "USD",
        "CallBackUrl": CALLBACK_URL,
        "ErrorUrl": CALLBACK_URL,
        "CustomerReference": str(order_id),
        "UserDefinedField": str(order_id)
    }

    try:
        resp = requests.post(url, json=payload, headers=headers)
    except Exception as e:
        return None, f"Request failed: {e}"

    data = resp.json()

    if resp.status_code != 200 or "Data" not in data:
        return None, f"MyFatoorah Error: {data.get('Message', 'Unknown error')}"

    return data["Data"]["PaymentURL"], None


# ======================
# Telegram Bot Handlers
# ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to ShopBot!\nUse /shop to browse categories."
    )


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = await get_categories()

    keyboard = [
        [InlineKeyboardButton(cat.name, callback_data=f"cat_{cat.id}")]
        for cat in categories
    ]

    await update.message.reply_text(
        "🛍 Select a category:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cat_id = query.data.split("_")[1]
    products = await get_products(cat_id)

    keyboard = [
        [InlineKeyboardButton(f"{p.name} — ${p.price}", callback_data=f"prod_{p.id}")]
        for p in products
    ]

    await query.message.reply_text(
        "📦 Choose a product:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def product_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    prod_id = query.data.split("_")[1]

    product = await sync_to_async(Product.objects.get)(id=prod_id)

    context.user_data["cart"] = [(product, 1)]

    await query.message.reply_text(
        f"🛒 Added to cart: *{product.name}*\nPrice: ${product.price}\n\nPress pay:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Pay Now", callback_data="pay_now")]
        ]),
        parse_mode="Markdown"
    )


async def pay_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cart = context.user_data.get("cart", [])

    if not cart:
        await query.message.reply_text("Your cart is empty.")
        return

    total = sum(p.price * qty for p, qty in cart)

    order = await create_order(
        user_id=query.from_user.id,
        items=cart
    )

    await query.message.reply_text(f"✅ Order #{order.id} placed! Total: ${total}")

    # Create MyFatoorah payment
    payment_url, error = create_myfatoorah_payment(
        order_id=order.id,
        amount=total,
        customer_name=query.from_user.full_name
    )

    if error:
        await query.message.reply_text(f"❌ Payment Error:\n{error}")
        return

    await query.message.reply_text(
        f"💳 Click to complete payment:\n{payment_url}"
    )


# ======================
# Run Bot
# ======================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))

    app.add_handler(CallbackQueryHandler(category_selected, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(product_selected, pattern="^prod_"))
    app.add_handler(CallbackQueryHandler(pay_now, pattern="^pay_now$"))

    print("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
