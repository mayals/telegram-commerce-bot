from rest_framework import serializers
from shop.models import Order, OrderItem, Product





# ---------------- Product Serializer ----------------
class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'stock', 'is_active']

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError("Stock cannot be negative.")
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Product name cannot be empty.")
        return value





# ---------------- OrderItem Serializer ----------------
class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True), source='product'
    )

    class Meta:
        model = OrderItem
        fields = ['product_id', 'quantity', 'price']

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        product = self.initial_data.get('product_id')
        if product:
            product_obj = Product.objects.get(pk=product)
            if value > product_obj.stock:
                raise serializers.ValidationError(f"Quantity exceeds available stock ({product_obj.stock}).")
        return value

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value





# ---------------- Order Serializer ----------------
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'chat_id', 'customer_name', 'phone', 'address', 'email', 'status', 'total', 'items']

    # Field-level validations
    def validate_customer_name(self, value):
        import re
        if not re.match(r'^[A-Za-z\s]{2,}$', value):
            raise serializers.ValidationError("Enter a valid full name (letters and spaces only).")
        return value

    def validate_phone(self, value):
        import re
        if not re.match(r'^\+?\d{7,15}$', value):
            raise serializers.ValidationError("Enter a valid phone number (7–15 digits, optional +).")
        return value

    def validate_address(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Address is too short.")
        return value

    def validate_email(self, value):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        if value:
            try:
                validate_email(value)
            except ValidationError:
                raise serializers.ValidationError("Enter a valid email address.")
        return value

    # Create method to save nested OrderItems
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        total = 0
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            price = item_data['price']
            OrderItem.objects.create(order=order, product=product, quantity=quantity, price=price)
            total += price * quantity
        order.total = total
        order.save()
        return order
