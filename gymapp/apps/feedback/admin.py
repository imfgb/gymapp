from django.contrib import admin

from .models import BugReport


@admin.register(BugReport)
class BugReportAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "reporter", "status", "page_area", "created_at")
    list_filter = ("status",)
    search_fields = ("subject", "description", "page_area", "reporter__email")
    autocomplete_fields = ("reporter",)
    date_hierarchy = "created_at"
