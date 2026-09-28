from django.contrib import admin
from .models import Item


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "quantity", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "description")
