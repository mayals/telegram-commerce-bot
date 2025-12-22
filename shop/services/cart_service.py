from shop.models import Cart,CartItem, Product
from asgiref.sync import sync_to_async



# Get or create active cart
@sync_to_async
def get_or_create_active_cart(chat_id):
    cart = Cart.objects.filter(chat_id=chat_id, is_active=True).first()
    if cart:
        return cart
    return Cart.objects.create(chat_id=chat_id)





# Add a product to the cart
@sync_to_async
def add_product_to_cart(cart, product_id, qty=1):
    product = Product.objects.get(id=product_id, is_active=True)
    item = CartItem.objects.filter(cart=cart, product=product).first()
    if item:
        item.quantity += qty
        item.save()
    else:
        CartItem.objects.create(cart=cart, product=product, quantity=qty, price=product.price)







# Change product quantity
# @sync_to_async
# @transaction.atomic
# def change_product_quantity(cart, product_id, delta):
#     item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
#     if not item:
#         return
#     item.quantity += delta
#     if item.quantity <= 0:
#         item.delete()
#     else:
#         item.save()






# Remove product from cart
@sync_to_async
def remove_from_cart(cart, product_id):
    item = CartItem.objects.filter(cart=cart, product_id=product_id).first()
    if item:
        item.delete()




@sync_to_async
def get_cart_item(cart, product_id):
    return CartItem.objects.filter(cart=cart, product_id=product_id).first()


# @sync_to_async
# def get_cart_items(cart):
#     return list(CartItem.objects.filter(cart=cart))