from django.db import models
from shop.models import Order


# eta - estimated_delivery_time
class Delivery(models.Model):
    STATUS_CHOICES = [
        ("preparing", "Preparing"),
        ("shipped", "Shipped"),
        ("on_the_way", "On the Way"),
        ("delivered", "Delivered")
    ]
    order = models.OneToOneField(Order, on_delete=models.CASCADE,null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="preparing",null=True)
    current_location = models.CharField(max_length=255, blank=True,null=True)
    eta = models.CharField(max_length=100, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True,null=True)

    def __str__(self):
        return f"Delivery for Order #{self.order.id} - {self.status}"