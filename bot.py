# bot.py
import os
import django
import warnings
import logging
from decimal import Decimal
from io import BytesIO

import stripe
from PIL import Image
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from asgiref.sync import sync_to_async

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Django Setup ------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from shop.models import Category, Product, Order, OrderItem

# ------------------ Stripe Setup ------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
# print("STRIPE_SECRET_KEY=", STRIPE_SECRET_KEY )

SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")  # used for success/cancel urls
if not STRIPE_SECRET_KEY:
    logger.warning("STRIPE_SECRET_KEY not found in env; Stripe payments WILL fail until set.")
else:
    stripe.api_key = STRIPE_SECRET_KEY



# ------------------ Globals ------------------
user_carts = {}  # {chat_id: {product_id: qty}}

# Suppress PIL DecompressionBomb warnings if desired
warnings.simplefilter("ignore", Image.DecompressionBombWarning)




# ------------------ Helpers ------------------

async def resize_image_for_telegram(image_path):
    """Return a BytesIO JPEG suitable for Telegram (or None on failure)."""
    try:
        with Image.open(image_path) as img:
            min_size, max_size = 200, 2000
            w, h = img.size
            if w < min_size or h < min_size:
                scale = max(min_size / max(w, 1), min_size / max(h, 1))
                img = img.resize((int(w * scale), int(h * scale)))
            if w > max_size or h > max_size:
                img.thumbnail((max_size, max_size))
            bio = BytesIO()
            img.convert("RGB").save(bio, format="JPEG")
            bio.seek(0)
            return bio
    except Exception as e:
        logger.debug("resize_image_for_telegram failed: %s", e)
        return None

async def safe_send_text(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, parse_mode=None):
    """Send a text message, catching & logging errors (async)."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error("Failed to send message to %s: %s", chat_id, e)

async def send_cart_message(chat_id: int, message_obj, context):
    """Compose and send/edit cart message."""
    cart = user_carts.get(chat_id, {})
    if not cart:
        try:
            await message_obj.edit_text("🛒 Your cart is empty.")
        except Exception:
            await safe_send_text(chat_id, context, "🛒 Your cart is empty.")
        return

    lines = []
    total = Decimal("0.00")
    keyboard = []

    # load product objects
    products = {}
    for pid in list(cart.keys()):
        try:
            products[pid] = await sync_to_async(Product.objects.get)(id=pid)
        except Product.DoesNotExist:
            logger.warning("Product %s not found while building cart for %s", pid, chat_id)
            cart.pop(pid, None)

    for pid, qty in cart.items():
        product = products.get(pid)
        if not product:
            continue
        subtotal = product.price * qty
        total += subtotal
        lines.append(f"{product.name} x{qty} = ${subtotal:.2f}")
        keyboard.append([
            InlineKeyboardButton("➕", callback_data=f"inc_{pid}"),
            InlineKeyboardButton("➖", callback_data=f"dec_{pid}"),
            InlineKeyboardButton("Remove", callback_data=f"rm_{pid}")
        ])

    lines.append(f"\n*Total:* ${total:.2f}")
    keyboard.append([InlineKeyboardButton("Checkout", callback_data="checkout_now")])
    markup = InlineKeyboardMarkup(keyboard)
    text = "🛒 *Your Cart:*\n\n" + "\n".join(lines)

    try:
        await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except Exception:
        await safe_send_text(chat_id, context, text, reply_markup=markup, parse_mode="Markdown")

# ------------------ Commands ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send_text(update.message.chat.id, context, "👋 Welcome to ShopBot!\nUse /shop to browse categories.")

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = await sync_to_async(list)(Category.objects.all())
    if not cats:
        await safe_send_text(update.message.chat.id, context, "No categories available yet.")
        return
    buttons = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in cats]
    await safe_send_text(update.message.chat.id, context, "Choose category:", reply_markup=InlineKeyboardMarkup(buttons))

async def cart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await safe_send_text(chat_id, context, "🛒 Your cart is empty.")
        return
    msg = await update.message.reply_text("Loading cart...")
    await send_cart_message(chat_id, msg, context)

async def checkout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /checkout Name;Phone;Address[;Email]
    This command creates an Order in Django, creates Stripe CheckoutSession, and returns session.url
    """
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await safe_send_text(chat_id, context, "Your cart is empty.")
        return

    try:
        # split command text after /checkout
        _, raw = update.message.text.split(" ", 1)
        parts = [x.strip() for x in raw.split(";")]
        if len(parts) == 3:
            name, phone, address = parts
            email = None
        elif len(parts) == 4:
            name, phone, address, email = parts
        else:
            raise ValueError("Invalid parts")
    except Exception:
        await safe_send_text(chat_id, context, "Wrong format. Use:\n/checkout Name;Phone;Address[;Email]")
        return

    # create order (sync in thread)
    order = await sync_to_async(Order.objects.create)(
        chat_id=chat_id, customer_name=name, phone=phone, address=address, email=email
    )

    # create order items
    total = Decimal("0.00")
    line_items = []
    for pid, qty in list(cart.items()):
        try:
            product = await sync_to_async(Product.objects.get)(id=pid)
        except Product.DoesNotExist:
            logger.warning("Product %s not found during checkout", pid)
            continue
        subtotal = product.price * qty
        total += subtotal
        await sync_to_async(OrderItem.objects.create)(
            order=order, product=product, quantity=qty, price=product.price
        )

        # Prepare Stripe line_item
        # Stripe expects amounts in cents (integer)
        unit_amount = int((product.price * Decimal("100")).quantize(Decimal("1")))
        line_items.append({
            "price_data": {
                "currency": "usd",  # change if needed
                "product_data": {"name": product.name, "description": product.description or ""},
                "unit_amount": unit_amount,
            },
            "quantity": qty,
        })

    # save total
    order.total = total
    await sync_to_async(order.save)()

    # Empty cart locally (we will update order status from webhook)
    user_carts[chat_id] = {}

    # Create Stripe Checkout Session (run blocking stripe call in thread)
    if not STRIPE_SECRET_KEY:
        await safe_send_text(chat_id, context, f"✅ Order #{order.id} placed! Total: ${total:.2f}\nBut payments are not configured (STRIPE_SECRET_KEY missing).")
        return

    try:
        def create_session():
            return stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=f"{SITE_URL.rstrip('/')}/payment/stripe-success?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}",
                cancel_url=f"{SITE_URL.rstrip('/')}/payment/stripe-cancel?order_id={order.id}",
                metadata={"order_id": str(order.id)},
            )

        session = await sync_to_async(create_session)()

        # Save IDs in the order
        order.stripe_session_id = session.id
        order.stripe_payment_intent_id = session.payment_intent
        await sync_to_async(order.save)()

        # send session url
        pay_url = session.url
        await safe_send_text(chat_id, context, f"💳 Pay your order #{order.id}: {pay_url}")

    except Exception as e:
        logger.exception("Unexpected Stripe error")
        await safe_send_text(chat_id, context, f"Payment error: {str(e)}")





# ------------------ Callback Handler ------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    # Category listing
    if data.startswith("cat_"):
        cat_id = int(data.split("_", 1)[1])
        products = await sync_to_async(list)(Product.objects.filter(category_id=cat_id, is_active=True))
        if not products:
            await query.edit_message_text("No products in this category.")
            return
        buttons = [[InlineKeyboardButton(f"{p.name} — ${p.price}", callback_data=f"prod_{p.id}")] for p in products]
        await query.edit_message_text("Products:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Product detail
    if data.startswith("prod_"):
        prod_id = int(data.split("_", 1)[1])
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        text = f"*{product.name}*\nPrice: ${product.price}\n\n{product.description or ''}"
        buttons = [
            [InlineKeyboardButton("➕ Add to cart", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("Back to categories", callback_data="back_cats")]
        ]
        if product.image and getattr(product.image, "path", None) and os.path.exists(product.image.path):
            bio = await resize_image_for_telegram(product.image.path)
            if bio:
                try:
                    await query.message.reply_photo(photo=bio, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                    return
                except Exception as e:
                    logger.debug("reply_photo failed: %s", e)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Add to cart
    if data.startswith("add_"):
        prod_id = int(data.split("_", 1)[1])
        cart = user_carts.get(chat_id, {})
        cart[prod_id] = cart.get(prod_id, 0) + 1
        user_carts[chat_id] = cart
        await query.answer("Added to cart ✅")
        await safe_send_text(chat_id, context, "🛒 Item added to cart! Use /cart to view it.")
        return

    # Cart ops
    if data.startswith(("inc_", "dec_", "rm_")):
        op, prod_id = data.split("_", 1)
        prod_id = int(prod_id)
        cart = user_carts.get(chat_id, {})
        if op == "inc":
            cart[prod_id] = cart.get(prod_id, 0) + 1
        elif op == "dec":
            if cart.get(prod_id, 0) > 1:
                cart[prod_id] -= 1
            else:
                cart.pop(prod_id, None)
        elif op == "rm":
            cart.pop(prod_id, None)
        user_carts[chat_id] = cart
        await send_cart_message(chat_id, query.message, context)
        return

    if data == "checkout_now":
        await safe_send_text(chat_id, context, "To finish, send:\n/checkout Name;Phone;Address[;Email]")
        return

# Back to categories
async def back_to_categories_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    categories = await sync_to_async(list)(Category.objects.all())
    buttons = [[InlineKeyboardButton(cat.name, callback_data=f"cat_{cat.id}")] for cat in categories]
    await query.message.reply_text("Choose category:", reply_markup=InlineKeyboardMarkup(buttons))




# ------------------ Startup ------------------

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables. Set BOT_TOKEN and restart.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("cart", cart_cmd))
    app.add_handler(CommandHandler("checkout", checkout_cmd))

    # callbacks
    app.add_handler(CallbackQueryHandler(back_to_categories_handler, pattern="^back_cats$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
