from django.apps import AppConfig

class ShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shop'

    def ready(self):
        # import signals
        try:
            import shop.signals  # noqa: F401
        except Exception as e:
            print("Error importing shop.signals:", e)
