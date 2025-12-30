# payment/urls.py

from django.urls import path
from . import views


app_name = "payment"

urlpatterns = [
    # create-checkout-session
    path("create-checkout-session/<int:order_id>/", views.create_checkout_session, name="create-checkout-session"),
    # bot
    path("stripe-success/", views.stripe_success, name="stripe-success"),
    path("stripe-cancel/", views.stripe_cancel, name="stripe-cancel"),
    # html page
    path("stripe-success-page/", views.stripe_success_page, name="stripe-success-page"),
    
    # while using webhook in production 
    # path("stripe-webhook/", views_with_webhook.stripe_webhook, name="stripe-webhook"),
]

