from django.contrib import admin

from apps.bookings.models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "court",
        "club",
        "customer_name",
        "customer_phone",
        "start_time",
        "end_time",
        "total_price",
        "status",
        "source",
        "created_by",
    )
    list_filter = ("status", "source", "club", "court")
    search_fields = (
        "customer_name",
        "customer_phone",
        "court__name",
        "club__name",
    )
    date_hierarchy = "start_time"
    readonly_fields = ("total_price", "created_by", "created", "modified")
