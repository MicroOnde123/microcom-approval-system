from django.contrib import admin
from .models import MaterialCategory, Material


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "category",
        "unit",
        "is_active",
        "stock_quantity",
        "minimum_stock_level",
        "is_active",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "code", "description")