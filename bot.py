# bot.py

import re
import os
import django
import logging
from decimal import Decimal
from io import BytesIO

import httpx
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)
from asgiref.sync import sync_to_async

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ Django Setup ------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from shop.models import Category, Product, Order, OrderItem




# ------------------ Globals ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")
user_carts = {}  # {chat_id: {product_id: qty}}




# ------------------ REGEX ------------------
PHONE_REGEX = re.compile(r"^\+?\d{7,15}$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME_REGEX = re.compile(r"^[A-Za-z\s]{2,}$")





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


async def safe_send_text(chat_id, context: ContextTypes.DEFAULT_TYPE, text, reply_markup=None, parse_mode=None):
    """Send text safely."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        logger.error("Failed to send message to %s: %s", chat_id, e)


async def send_cart_message(chat_id, message_obj, context):
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

    products = {}
    for pid in list(cart.keys()):
        try:
            products[pid] = await sync_to_async(Product.objects.get)(id=pid)
        except Product.DoesNotExist:
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


# ------------------ Delivery Helper ------------------
async def send_delivery_status(chat_id, order_id, context: ContextTypes.DEFAULT_TYPE):
    from delivery.models import Delivery
    try:
        delivery = await sync_to_async(Delivery.objects.get)(order_id=order_id)
        text = (
            f"📦 **Order #{order_id} Delivery Status**\n\n"
            f"Status: {delivery.status}\n"
            f"Current Location: {delivery.current_location}\n"
            f"ETA: {delivery.eta or 'Not available'}"
        )
        await safe_send_text(chat_id, context, text, parse_mode="Markdown")
    except Delivery.DoesNotExist:
        await safe_send_text(chat_id, context, f"🚨 Delivery info not found for Order #{order_id}")









# ------------------ Commands ------------------

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     await safe_send_text(update.message.chat.id, context, "👋 Welcome to ShopBot!\nUse /shop to browse categories.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    print("MERCHANT_CHAT_ID:", chat_id) 

    # ---------- 1) Send Shop Logo ----------
    logo_path = "static/images/logo.jpg"   # put your logo file in static/images folder

    try:
        if os.path.exists(logo_path):
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=open(logo_path, "rb")
            )
    except Exception as e:
        logger.error(f"Failed to send logo: {e}")

    # ---------- 2) Send Shop Description ----------
    description = (
    "🍏 **FreshMart – Your Daily Fresh Market!**\n\n"
    "We offer the freshest high-quality:\n"
    "🥬 Vegetables\n"
    "🍎 Fruits\n"
    "🥚 Eggs\n"
    "🥛 Milk\n"
    "🚰 Water & Beverages\n"
    "🍞 Bread\n"
    "🧀 Cheese & Dairy\n"
    "🍗 Fresh Chicken\n"
    "🥩 Fresh Meat\n"
    "🐟 Fish & Seafood\n"
    "🥫 Canned Goods\n"
    "🛒 Snacks & Biscuits\n"
    "🍯 Honey & Jams\n"
    "🍚 Rice, Grains & Pasta\n"
    "🧼 Home Essentials\n\n"
    "Always clean • Always fresh • Always delivered to you 🚚💚"
    )

    await safe_send_text(chat_id, context, description, parse_mode="Markdown")

    # ---------- 3) Invite user to start shopping ----------
    welcome = (
        "👋 *Welcome!* Thank you for visiting FreshMart.\n\n"
        "🛒 To begin shopping, simply click:\n"
        "👉 */start*\n"
        "or type */shop* to browse categories.\n\n"
        "Happy shopping! 🌿"
    )

    await safe_send_text(chat_id, context, welcome, parse_mode="Markdown")


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

# ------------------ Checkout Conversation ------------------
NAME, PHONE, ADDRESS, EMAIL, CONFIRM = range(5)

async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await safe_send_text(chat_id, context, "🛒 Your cart is empty. Add products first.")
        return ConversationHandler.END
    await safe_send_text(chat_id, context, "Please enter your *full name*:", parse_mode="Markdown")
    return NAME

async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()

    if not NAME_REGEX.match(name):
        await safe_send_text(
            update.message.chat.id,
            context,
            "❌ Invalid name.\nPlease enter a valid *full name* (letters only):",
            parse_mode="Markdown"
        )
        return NAME

    context.user_data["name"] = name
    await safe_send_text(update.message.chat.id, context, "📱 Please enter your phone number:")
    return PHONE




async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()

    if not PHONE_REGEX.match(phone):
        await safe_send_text(
            update.message.chat.id,
            context,
            "❌ Invalid phone number.\n"
            "Please enter a valid number.\n"
            "Example: +966501234567"
        )
        return PHONE

    context.user_data["phone"] = phone
    await safe_send_text(update.message.chat.id, context, "📍 Please enter your address:")
    return ADDRESS



async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()

    if len(address) < 5:
        await safe_send_text(
            update.message.chat.id,
            context,
            "❌ Address is too short.\nPlease enter a valid address:"
        )
        return ADDRESS

    context.user_data["address"] = address
    await safe_send_text(
        update.message.chat.id,
        context,
        "📧 (Optional) Enter your email or type /skip"
    )
    return EMAIL


async def checkout_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()

    if not EMAIL_REGEX.match(email):
        await safe_send_text(
            update.message.chat.id,
            context,
            "❌ Invalid email format.\nExample: user@example.com\nOr type /skip"
        )
        return EMAIL

    context.user_data["email"] = email
    return await checkout_confirm_msg(update, context)


async def skip_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = None
    return await checkout_confirm_msg(update, context)


async def checkout_confirm_msg(src, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    text = (
        "🧾 **Review Your Information**\n\n"
        f"👤 Name: {data['name']}\n"
        f"📱 Phone: {data['phone']}\n"
        f"📍 Address: {data['address']}\n"
        f"📧 Email: {data.get('email') or '—'}\n\n"
        "Is this information correct?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, proceed", callback_data="confirm_checkout"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_checkout")
        ]
    ])
    if isinstance(src, Update):
        await src.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await src.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    return CONFIRM






async def checkout_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = context.user_data
    cart = user_carts.get(chat_id, {})

    if not cart:
        await safe_send_text(chat_id, context, "Your cart is empty. Use /shop to start again.")
        return ConversationHandler.END

    # 1️⃣ Create Django Order
    order = await sync_to_async(Order.objects.create)(
        chat_id=chat_id,
        customer_name=data["name"],
        phone=data["phone"],
        address=data["address"],
        email=data.get("email")
    )

    total = Decimal("0.00")
    for pid, qty in list(cart.items()):
        try:
            product = await sync_to_async(Product.objects.get)(id=pid)
        except Product.DoesNotExist:
            continue
        subtotal = product.price * qty
        total += subtotal
        await sync_to_async(OrderItem.objects.create)(
            order=order, product=product, quantity=qty, price=product.price
        )

    order.total = total
    await sync_to_async(order.save)()
    user_carts[chat_id] = {}

    # 2️⃣ Call Django create_checkout_session (Stripe)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{SITE_URL}/payment/create-checkout-session/{order.id}/")
            resp.raise_for_status()
            data = resp.json()
            pay_url = data.get("url")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Pay Now", url=pay_url)]
            ])
        await safe_send_text(chat_id, context, f"🛒 Order #{order.id} created! Click below to pay:", reply_markup=keyboard)

    except Exception as e:
        await safe_send_text(chat_id, context, f"Payment initiation failed: {str(e)}")

    return ConversationHandler.END



async def checkout_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checkout cancelled.")
    return ConversationHandler.END





async def track_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id

    order = await sync_to_async(Order.objects.filter(chat_id=chat_id).order_by('-created_at').first)()

    if not order:
        return await update.message.reply_text("You don’t have any orders yet.")

    status_map = {
        "pending": "⏳ Waiting for confirmation",
        "accepted": "🧑‍🍳 Your order is being prepared",
        "shipped": "🚚 Your order is on the way",
        "done": "✅ Your order has been delivered",
        "cancelled": "❌ Your order was cancelled",
    }

    text = f"""
                📦 *Order Tracking*
                Order ID: `{order.id}`
                Status: {status_map.get(order.status, 'Unknown')}
                Total: {order.total} SAR
                Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}
            """

    await update.message.reply_text(text, parse_mode="Markdown")



async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    orders = await sync_to_async(Order.objects.filter)(chat_id=chat_id)

    if not orders.exists():
        return await update.message.reply_text("You have no orders yet.")

    msg = "📦 *Your Previous Orders:*\n\n"

    for order in orders.order_by('-created_at')[:10]:
        msg += f"""
                    🆔 Order ID: `{order.id}`
                    Status: {order.status}
                    Total: {order.total} SAR
                    Date: {order.created_at.strftime('%Y-%m-%d')}
                    --------------------------
                """

    await update.message.reply_text(msg, parse_mode="HTML")



# ------------------ Callback Handler ------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    # Category
    if data.startswith("cat_"):
        cat_id = data.split("_", 1)[1]
        products = await sync_to_async(list)(Product.objects.filter(category_id=cat_id, is_active=True))
        if not products:
            await query.edit_message_text("No products in this category.")
            return
        buttons = [[InlineKeyboardButton(f"{p.name} - ${p.price}", callback_data=f"prod_{p.id}")] for p in products]
        await query.edit_message_text("📦 Products in this category:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Product
    if data.startswith("prod_"):
        prod_id = data.split("_", 1)[1]
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        text = f"*{product.name}*\nPrice: ${product.price}\n\n{product.description or ''}"
        buttons = [
            [InlineKeyboardButton("➕ Add to cart", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("Back to categories", callback_data="back_cats")]
        ]
        if getattr(product.image, "path", None) and os.path.exists(product.image.path):
            bio = await resize_image_for_telegram(product.image.path)
            if bio:
                try:
                    await query.message.reply_photo(photo=bio, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                    return
                except Exception as e:
                    logger.debug("reply_photo failed: %s", e)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # Cart operations
    if data.startswith(("add_", "inc_", "dec_", "rm_")):
        op, prod_id = data.split("_", 1)
        prod_id = prod_id
        cart = user_carts.get(chat_id, {})
        if op == "add" or op == "inc":
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
        await safe_send_text(chat_id, context, "🛒 To finish checkout, please type /checkout")
        return

    if data == "back_cats":
        categories = await sync_to_async(list)(Category.objects.all())
        buttons = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in categories]
        await query.message.reply_text("Choose category:", reply_markup=InlineKeyboardMarkup(buttons))

    
    if data.startswith("track_"):
        order_id = data.split("_")[1]
        await send_delivery_status(chat_id, order_id, context)
        return






# ------------------ Startup ------------------

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("cart", cart_cmd))

    # Checkout conversation
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("checkout", checkout_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_name)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_address)],
            EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_email),
                CommandHandler("skip", skip_email)
            ],
            CONFIRM: [CallbackQueryHandler(checkout_confirm, pattern="^confirm_checkout$"),
                      CallbackQueryHandler(checkout_cancel, pattern="^cancel_checkout$")]
        },
        fallbacks=[CommandHandler("cancel", checkout_cancel)],
    )
    app.add_handler(conv_handler)

    # Callback
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
