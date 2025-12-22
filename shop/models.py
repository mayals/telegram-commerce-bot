# shop/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.conf import settings
# validation
import re
from django.core.exceptions import ValidationError




class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name



class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.price} SAR)"

    def clean(self):
        if self.price < 0:
            raise ValidationError({"price": "Price cannot be negative."})
        if self.stock < 0:
            raise ValidationError({"stock": "Stock cannot be negative."})
        if not self.name.strip():
            raise ValidationError({"name": "Product name cannot be empty."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)




class Cart(models.Model):
    chat_id = models.BigIntegerField(db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart {self.id} (chat_id={self.chat_id})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart,on_delete=models.CASCADE,related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    # snapshot of price at time of adding
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.quantity * self.price





class Order(models.Model):
    STATUS_CHOICES = [
        ('pending','Pending'),
        ('accepted','Accepted'),
        ('shipped','Shipped'),
        ('cancelled','Cancelled'),
        ('done','Done'),
    ]

    chat_id = models.BigIntegerField() 
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    customer_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True, null=True)  # Add this line

    # stripe fields
    stripe_session_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="Stripe Checkout Session ID"
    )
    stripe_payment_intent_id = models.CharField(
        max_length=255, blank=True, null=True, help_text="Stripe PaymentIntent ID"
    )
    
    def __str__(self):
        return f"Order #{self.id} - {self.status} - {self.total} SAR"


    def clean(self):
        # 1️⃣ Name validation (letters and spaces, min 2 chars)
        if self.customer_name:
            if not re.match(r"^[A-Za-z\s]{2,}$", self.customer_name):
                raise ValidationError({"customer_name": "Name must contain letters only and at least 2 characters."})

        # 2️⃣ Phone validation (7–15 digits, optional +)
        if self.phone:
            if not re.match(r"^\+?\d{7,15}$", self.phone):
                raise ValidationError({"phone": "Invalid phone number format."})

        # 3️⃣ Email validation (optional)
        if self.email:
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", self.email):
                raise ValidationError({"email": "Invalid email format."})

        # 4️⃣ Address validation (min 5 chars)
        if self.address and len(self.address.strip()) < 5:
            raise ValidationError({"address": "Address is too short."})

    def save(self, *args, **kwargs):
        # Ensure validation runs on save
        self.full_clean()
        super().save(*args, **kwargs)




class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} × {self.product.name} (Order #{self.order.id})"

    def clean(self):
        # Quantity must be at least 1
        if self.quantity < 1:
            raise ValidationError({"quantity": "Quantity must be at least 1."})
        
        # Price must be >= 0
        if self.price < 0:
            raise ValidationError({"price": "Price cannot be negative."})

        # Stock check
        if self.product and self.quantity > self.product.stock:
            raise ValidationError({"quantity": f"Quantity exceeds available stock ({self.product.stock})."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)