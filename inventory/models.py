from django.db import models


class MaterialCategory(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Material categories"

    def __str__(self):
        return self.name


class Material(models.Model):
    category = models.ForeignKey(
        MaterialCategory,
        on_delete=models.PROTECT,
        related_name="materials"
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        stock = f"{self.stock_quantity:g}" if self.stock_quantity is not None else "0"
        Unit = self.unit or ""
        return f"{self.name} | Code: {self.code} | Category: {self.category.name} | Stock: {stock} {Unit}"
    
