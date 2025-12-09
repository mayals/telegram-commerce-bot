from rest_framework import serializers
from .models import Delivery

class DeliverySerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)

    class Meta:
        model = Delivery
        fields = ["order_id", "status", "current_location", "estimated_delivery_time", "updated_at"]
