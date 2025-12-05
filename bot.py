# telegram-commerce-bot/bot.py

import os
import django
import warnings
from decimal import Decimal
from io import BytesIO

import requests
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from asgiref.sync import sync_to_async

# ------------------ Django Setup ------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()
from shop.models import Category, Product, Order, OrderItem

# ------------------ Global Variables ------------------
user_carts = {}  # In-memory cart: {chat_id: {product_id: qty}}

# Suppress large image warnings
warnings.simplefilter("ignore", Image.DecompressionBombWarning)

# ------------------ Helper Functions ------------------

async def resize_image_for_telegram(image_path):
    """Resize image to a safe size for Telegram."""
    try:
        img = Image.open(image_path)
        min_size, max_size = 200, 2000
        w, h = img.size
        if w < min_size or h < min_size:
            scale = max(min_size / w, min_size / h)
            img = img.resize((int(w*scale), int(h*scale)))
        if w > max_size or h > max_size:
            img.thumbnail((max_size, max_size))
        bio = BytesIO()
        img.convert("RGB").save(bio, format="JPEG")
        bio.seek(0)
        return bio
    except Exception:
        return None

async def send_safe_message(chat_id, context, text, reply_markup=None, parse_mode=None):
    """Send message safely with exception handling."""
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        print(f"Failed to send message: {e}")

async def send_cart_message(chat_id, message_obj, context):
    """Render and send the cart contents."""
    cart = user_carts.get(chat_id, {})
    if not cart:
        try:
            await message_obj.edit_text("🛒 Your cart is empty.")
        except:
            await send_safe_message(chat_id, context, "🛒 Your cart is empty.")
        return

    lines = []
    total = Decimal("0.00")
    keyboard = []

    products = {}
    for pid in cart.keys():
        try:
            products[pid] = await sync_to_async(Product.objects.get)(id=pid)
        except Product.DoesNotExist:
            continue

    for pid, qty in cart.items():
        product = products.get(pid)
        if not product:
            continue
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
        await send_safe_message(chat_id, context, text, reply_markup=markup, parse_mode="Markdown")

# ------------------ Command Handlers ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_safe_message(update.message.chat.id, context, "👋 Welcome to ShopBot!\nUse /shop to browse categories.")

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cats = await sync_to_async(list)(Category.objects.all())
    if not cats:
        await send_safe_message(update.message.chat.id, context, "No categories available yet.")
        return
    buttons = [[InlineKeyboardButton(c.name, callback_data=f"cat_{c.id}")] for c in cats]
    await send_safe_message(update.message.chat.id, context, "Choose category:", reply_markup=InlineKeyboardMarkup(buttons))

async def cart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await send_safe_message(chat_id, context, "🛒 Your cart is empty.")
        return
    msg = await update.message.reply_text("Loading cart...")
    await send_cart_message(chat_id, msg, context)

async def checkout_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await send_safe_message(chat_id, context, "Your cart is empty.")
        return

    try:
        _, raw = update.message.text.split(" ", 1)
        parts = [x.strip() for x in raw.split(";")]
        if len(parts) == 3:
            name, phone, address = parts
            email = None
        elif len(parts) == 4:
            name, phone, address, email = parts
        else:
            raise ValueError
    except Exception:
        await send_safe_message(chat_id, context, "Wrong format. Use:\n/checkout Name;Phone;Address[;Email]")
        return

    order = await sync_to_async(Order.objects.create)(
        chat_id=chat_id,
        customer_name=name,
        phone=phone,
        address=address,
        email=email
    )

    total = Decimal("0.00")
    for pid, qty in cart.items():
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

    # ------------------ MyFatoorah Payment ------------------
    try:
        MF_API_TOKEN = os.getenv("MYFATOORAH_TEST_TOKEN")
        MF_API_URL = "https://apitest.myfatoorah.com/v2/ExecutePayment"

        # Validate token first
        if not MF_API_TOKEN:
            raise ValueError("MyFatoorah token not set in environment variables.")

        payload = {
            "CustomerName": name,
            "CustomerEmail": email or "",
            "CustomerMobile": phone,
            "InvoiceValue": float(total),
            "DisplayCurrencyIso": "USD",
            "CallBackUrl": "https://example.com/success",
            "ErrorUrl": "https://example.com/error",
            "NotificationOption": "Lnk"
        }
        headers = {
            "Authorization": f"Bearer {MF_API_TOKEN}",
            "Content-Type": "application/json"
        }

        response = requests.post(MF_API_URL, json=payload, headers=headers, timeout=10)
        try:
            data = response.json()
        except Exception:
            data = {}

        pay_url = data.get("Data", {}).get("InvoiceURL") if data else None
        if pay_url:
            await send_safe_message(chat_id, context,
                f"✅ Order #{order.id} placed! Total: ${total}\nPay here: {pay_url}")
        else:
            error_message = data.get("Message") if data else "No valid response from MyFatoorah"
            await send_safe_message(chat_id, context,
                f"✅ Order #{order.id} placed! Total: ${total}\nPayment link could not be generated.\nError: {error_message}")
    except Exception as e:
        await send_safe_message(chat_id, context,
            f"✅ Order #{order.id} placed! Total: ${total}\nPayment request failed.\nError: {str(e)}")

# ------------------ Callback Handler ------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    # --- Category selected ---
    if data.startswith("cat_"):
        cat_id = int(data.split("_", 1)[1])
        products = await sync_to_async(list)(Product.objects.filter(category_id=cat_id, is_active=True))
        if not products:
            await query.edit_message_text("No products in this category.")
            return
        buttons = [[InlineKeyboardButton(f"{p.name} — ${p.price}", callback_data=f"prod_{p.id}")] for p in products]
        await query.edit_message_text("Products:", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # --- Product selected ---
    if data.startswith("prod_"):
        prod_id = int(data.split("_", 1)[1])
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        text = f"*{product.name}*\nPrice: ${product.price}\n\n{product.description or ''}"
        buttons = [
            [InlineKeyboardButton("➕ Add to cart", callback_data=f"add_{prod_id}")],
            [InlineKeyboardButton("Back to categories", callback_data="back_cats")]
        ]
        if product.image and os.path.exists(product.image.path):
            bio = await resize_image_for_telegram(product.image.path)
            if bio:
                await query.message.reply_photo(photo=bio, caption=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
                return
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # --- Add to cart ---
    if data.startswith("add_"):
        prod_id = int(data.split("_", 1)[1])
        cart = user_carts.get(chat_id, {})
        cart[prod_id] = cart.get(prod_id, 0) + 1
        user_carts[chat_id] = cart
        await query.answer("Added to cart ✅")
        await send_safe_message(chat_id, context, "🛒 Item added to cart! Use /cart to view it.")
        return

    # --- Cart operations ---
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

    # --- Checkout ---
    if data == "checkout_now":
        await send_safe_message(chat_id, context, "To finish, send:\n/checkout Name;Phone;Address[;Email]")
        return

# --- Back to categories ---
async def back_to_categories_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    categories = await sync_to_async(list)(Category.objects.all())
    buttons = [[InlineKeyboardButton(cat.name, callback_data=f"cat_{cat.id}")] for cat in categories]
    await query.message.reply_text("Choose category:", reply_markup=InlineKeyboardMarkup(buttons))

# ------------------ Bot Startup ------------------

def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("BOT_TOKEN not found in environment variables")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("cart", cart_cmd))
    app.add_handler(CommandHandler("checkout", checkout_cmd))

    # Callback Handlers
    app.add_handler(CallbackQueryHandler(back_to_categories_handler, pattern="^back_cats$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
