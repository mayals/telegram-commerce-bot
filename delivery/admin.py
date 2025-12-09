from django.contrib import admin
from .models import Delivery

@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "current_location", "eta", "updated_at")
    list_filter = ("status",)
    search_fields = ("order__id",)
