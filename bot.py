# telegram-commerce-bot/bot.py

from PIL import Image
from io import BytesIO
import os
import django
from decimal import Decimal
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from asgiref.sync import sync_to_async
from django.conf import settings

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from shop.models import Category, Product, Order, OrderItem

# In-memory carts: {chat_id: {product_id: qty}}
user_carts = {}

# ------------------ Helpers ------------------

async def get_full_image_url(product):
    if not product.image:
        return None
    url = product.image.url
    site = getattr(settings, "SITE_URL", None)
    if site and url.startswith("/"):
        return site.rstrip("/") + url
    return url

async def resize_image_for_telegram(image_path):
    img = Image.open(image_path)
    min_size, max_size = 200, 2000

    w, h = img.size

    if w < min_size or h < min_size:
        scale = max(min_size / w, min_size / h)
        img = img.resize((int(w*scale), int(h*scale)))

    w, h = img.size
    if w > max_size or h > max_size:
        img.thumbnail((max_size, max_size))

    bio = BytesIO()
    img.convert("RGB").save(bio, format="JPEG")
    bio.seek(0)
    return bio

# ------------------ Commands ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to ShopBot!\nUse /shop to browse categories."
    )

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = await sync_to_async(list)(Category.objects.all())
    if not cats:
        await update.message.reply_text("No categories yet.")
        return
    buttons = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in cats]
    await update.message.reply_text("Choose category:", reply_markup=InlineKeyboardMarkup(buttons))


# ------------------ FIX 1: ADD TO CART HANDLER ------------------

async def add_to_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    product_id = query.data.split("_")[2]
    product = await sync_to_async(Product.objects.get)(id=product_id)

    cart = context.user_data.get("cart", [])
    cart.append(product.id)
    context.user_data["cart"] = cart

    await query.message.reply_text("🛒 Item added to cart. Use /cart to view it.")


# ------------------ FIX 2: BACK TO CATEGORIES HANDLER ------------------

async def back_to_categories_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    categories = await sync_to_async(list)(Category.objects.all())
    buttons = [
        [InlineKeyboardButton(cat.name, callback_data=f"cat_{cat.id}")]
        for cat in categories
    ]

    # Send NEW text message (not editing a photo)
    await query.message.reply_text(
        "Choose category:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ------------------ Callback Handler ------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    # -------- Category --------
    if data.startswith("cat_"):
        cat_id = int(data.split("_", 1)[1])
        products = await sync_to_async(list)(Product.objects.filter(category_id=cat_id, is_active=True))
        if not products:
            await query.edit_message_text("No products in this category.")
            return
        buttons = [[InlineKeyboardButton(f"{p.name} — ${p.price}", callback_data=f"prod_{p.id}")] for p in products]
        await query.edit_message_text("Products:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # -------- Product --------
    if data.startswith("prod_"):
        prod_id = int(data.split("_", 1)[1])
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        text = f"*{product.name}*\n\nPrice: ${product.price}\n\n{product.description or ''}"
        buttons = [
            [InlineKeyboardButton("➕ Add to cart", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("Back to categories", callback_data="back_cats")]
        ]

        if product.image and os.path.exists(product.image.path):
            bio = await resize_image_for_telegram(product.image.path)
            await query.message.reply_photo(
                photo=bio,
                caption=text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # -------- Add to Cart --------
    if data.startswith("add_"):
        prod_id = int(data.split("_", 1)[1])
        cart = user_carts.get(chat_id, {})
        cart[prod_id] = cart.get(prod_id, 0) + 1
        user_carts[chat_id] = cart
        await query.answer("Added to cart ✅")

        # Send separate message (not editing photo)
        await query.message.reply_text("🛒 Item added to cart! Use /cart to view it.")
        return

    # -------- Cart Controls --------
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
        await query.answer()
        await query.message.reply_text("To finish, send:\n/checkout Name;Phone;Address")
        return


# ------------------ Cart Helper ------------------

async def send_cart_message(chat_id, message_obj, context):
    cart = user_carts.get(chat_id, {})
    if not cart:
        try:
            await message_obj.edit_text("🛒 Your cart is empty.")
        except:
            await context.bot.send_message(chat_id=chat_id, text="🛒 Your cart is empty.")
        return

    lines = []
    total = Decimal("0.00")
    keyboard = []
    for pid, qty in cart.items():
        product = await sync_to_async(Product.objects.get)(id=pid)
        subtotal = product.price * qty
        total += subtotal
        lines.append(f"{product.name} x{qty} = ${subtotal}")
        keyboard.append([
            InlineKeyboardButton("➕", callback_data=f"inc_{pid}"),
            InlineKeyboardButton("➖", callback_data=f"dec_{pid}"),
            InlineKeyboardButton("Remove", callback_data=f"rm_{pid}")
        ])
    lines.append(f"\n*Total:* ${total}")
    keyboard.append([InlineKeyboardButton("Checkout", callback_data="checkout_now")])
    markup = InlineKeyboardMarkup(keyboard)
    text = "🛒 *Your Cart:*\n\n" + "\n".join(lines)
    try:
        await message_obj.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except:
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=markup)


# ------------------ Commands ------------------

async def cart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await update.message.reply_text("🛒 Your cart is empty.")
        return
    msg = await update.message.reply_text("Loading cart...")
    await send_cart_message(chat_id, msg, context)

async def checkout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return
    try:
        _, raw = update.message.text.split(" ", 1)
        name, phone, address = [x.strip() for x in raw.split(";")]
    except:
        await update.message.reply_text("Wrong format. Use:\n/checkout Name;Phone;Address")
        return

    order = await sync_to_async(Order.objects.create)(
        chat_id=chat_id, customer_name=name, phone=phone, address=address
    )
    total = Decimal("0.00")
    for pid, qty in cart.items():
        product = await sync_to_async(Product.objects.get)(id=pid)
        subtotal = product.price * qty
        total += subtotal
        await sync_to_async(OrderItem.objects.create)(
            order=order, product=product, quantity=qty, price=product.price
        )
    order.total = total
    await sync_to_async(order.save)()
    user_carts[chat_id] = {}
    await update.message.reply_text(f"✅ Order placed! Order #{order.id} — Total: ${total}\nMerchant has been notified.")


# ------------------ Bot Startup ------------------

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("BOT_TOKEN not found in env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("cart", cart_cmd))
    app.add_handler(CommandHandler("checkout", checkout_cmd))

    # FIXED CALLBACKS
    app.add_handler(CallbackQueryHandler(back_to_categories_handler, pattern="^back_cats$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
