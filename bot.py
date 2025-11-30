import os
import django
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from asgiref.sync import sync_to_async




# -------------------- Django setup --------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from shop.models import Category, Product, Order, OrderItem




# -------------------- In-memory user carts --------------------
user_carts = {}  # chat_id -> {product_id: quantity}





# -------------------- Bot commands --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to ShopBot!\nUse /shop to browse categories."
    )



# Show categories
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories = await sync_to_async(list)(Category.objects.all())
    if not categories:
        await update.message.reply_text("No categories available.")
        return

    buttons = [
        [InlineKeyboardButton(cat.name, callback_data=f"category_{cat.id}")]
        for cat in categories
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select a category:", reply_markup=reply_markup)





# Handle button clicks (category -> products -> add to cart)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data = query.data

    # ---------------- CATEGORY selected ----------------
    if data.startswith("category_"):
        cat_id = int(data.split("_")[1])
        products = await sync_to_async(list)(Product.objects.filter(category_id=cat_id, is_active=True))
        if not products:
            await query.edit_message_text("No products in this category.")
            return

        buttons = [
            [InlineKeyboardButton(f"{p.name} - ${p.price}", callback_data=f"product_{p.id}")]
            for p in products
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("Select a product:", reply_markup=reply_markup)

    # ---------------- PRODUCT selected ----------------
    elif data.startswith("product_"):
        prod_id = int(data.split("_")[1])
        product = await sync_to_async(Product.objects.get)(id=prod_id)

        # Add to cart
        cart = user_carts.get(chat_id, {})
        cart[prod_id] = cart.get(prod_id, 0) + 1
        user_carts[chat_id] = cart

        await query.edit_message_text(f"✅ Added {product.name} to cart.\nUse /cart to view your cart.")





# Show cart and allow checkout
async def cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return

    text = "🛒 Your Cart:\n\n"
    total = 0
    for prod_id, qty in cart.items():
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        subtotal = product.price * qty
        total += subtotal
        text += f"{product.name} x{qty} = ${subtotal}\n"
    text += f"\nTotal: ${total}"
    text += "\n\nUse /checkout <name>;<phone>;<address> to place order.\nExample: /checkout John Doe;123456789;Street 123"

    await update.message.reply_text(text)





# Checkout
async def checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    cart = user_carts.get(chat_id, {})
    if not cart:
        await update.message.reply_text("Your cart is empty.")
        return

    try:
        # Expecting: /checkout Name;Phone;Address
        args = update.message.text.split(" ", 1)[1]
        name, phone, address = [x.strip() for x in args.split(";")]
    except Exception:
        await update.message.reply_text(
            "Invalid format! Use /checkout Name;Phone;Address"
        )
        return

    total = 0
    order = await sync_to_async(Order.objects.create)(
        chat_id=chat_id, customer_name=name, phone=phone, address=address
    )

    for prod_id, qty in cart.items():
        product = await sync_to_async(Product.objects.get)(id=prod_id)
        subtotal = product.price * qty
        total += subtotal
        await sync_to_async(OrderItem.objects.create)(
            order=order, product=product, quantity=qty, price=product.price
        )

    order.total = total
    await sync_to_async(order.save)()

    # Clear cart
    user_carts[chat_id] = {}

    await update.message.reply_text(f"✅ Order placed! Total: ${total}\nWe will contact you soon.")





# -------------------- Main --------------------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        print("BOT_TOKEN not found in .env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("cart", cart))
    app.add_handler(CommandHandler("checkout", checkout))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
