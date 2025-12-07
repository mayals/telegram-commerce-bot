#  payment/urls.py

from django.urls import path
from . import views


app_name = "payment"

urlpatterns = [
    path("create-checkout-session/<int:order_id>/", views.create_checkout_session, name="create-checkout-session"),
    path("stripe-success/", views.stripe_success, name="stripe-success"),
    path("stripe-cancel/", views.stripe_cancel, name="stripe-cancel"),
    path("stripe-webhook/", views.stripe_webhook, name="stripe-webhook"),
]

