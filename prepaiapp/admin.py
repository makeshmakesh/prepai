# pylint:disable=all
from django.contrib import admin
from .models import EarlyAccessEmail


@admin.register(EarlyAccessEmail)
class EarlyAccessEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("email",)
