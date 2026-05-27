from django.db import models
from django.contrib.auth.models import AbstractUser


class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name


class Role(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    full_name = models.CharField(max_length=255)

    employee_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    can_manage_stock = models.BooleanField(
        default=False,
        verbose_name="Can Manage Stock Reports",
    )

    def __str__(self):
        return self.full_name or self.username