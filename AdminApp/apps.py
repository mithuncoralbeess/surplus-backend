from django.apps import AppConfig


class AdminappConfig(AppConfig):
    name = 'AdminApp'

    def ready(self):
        try:
            import AdminApp.signals  # noqa: F401
        except Exception:
            pass
