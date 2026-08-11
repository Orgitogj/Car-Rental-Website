from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AuditLog,
    Booking,
    BookingExtra,
    Car,
    CarImage,
    Company,
    CompanyContract,
    CompanyDocument,
    ContactMessage,
    ContractTemplate,
    Customer,
    Extra,
    MaintenanceRecord,
)


class CarImageInline(admin.TabularInline):
    model = CarImage
    extra = 0
    fields = ("preview", "image_name", "is_main", "created_at")
    readonly_fields = ("preview", "image_name", "created_at")

    def preview(self, obj):
        if not obj.pk or not obj.image:
            return "—"
        return format_html(
            '<img src="{}" style="height:48px;border-radius:6px">', obj.url
        )


class ExtraInline(admin.TabularInline):
    model = Extra
    extra = 0
    fields = ("name", "price_per_day", "is_active", "sort_order")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "email", "city", "owner", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "email", "city", "owner__username")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [ExtraInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("owner")


@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company",
        "car_type",
        "price_per_day",
        "year",
        "is_active",
        "popularity",
    )
    list_filter = ("is_active", "car_type", "fuel", "gear", "company")
    search_fields = ("name", "brand", "company__name")
    list_select_related = ("company",)
    inlines = [CarImageInline]


class BookingExtraInline(admin.TabularInline):
    model = BookingExtra
    extra = 0
    readonly_fields = ("name", "price_per_day", "total")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "company",
        "car",
        "full_name",
        "start_date",
        "end_date",
        "total_price",
        "status",
    )
    list_filter = ("status", "company", "start_date")
    search_fields = ("reference", "full_name", "email", "phone")
    readonly_fields = ("reference", "created_at", "updated_at")
    list_select_related = ("company", "car")
    date_hierarchy = "start_date"
    inlines = [BookingExtraInline]


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "company", "phone", "last_booked_at")
    list_filter = ("company",)
    search_fields = ("full_name", "email", "phone")
    list_select_related = ("company",)


@admin.register(Extra)
class ExtraAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "price_per_day", "is_active", "sort_order")
    list_filter = ("company", "is_active")
    search_fields = ("name",)


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("car", "company", "kind", "status", "scheduled_for", "cost")
    list_filter = ("status", "kind", "company")
    list_select_related = ("car", "company")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "subject", "email", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("full_name", "email", "subject")


@admin.register(ContractTemplate)
class ContractTemplateAdmin(admin.ModelAdmin):
    list_display = ("version", "title", "is_active", "published_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("version", "title")
    readonly_fields = ("created_at",)

    def get_readonly_fields(self, request, obj=None):
        # A version somebody has signed is frozen; the model refuses the write
        # anyway, and greying the fields explains why before the error.
        if obj is not None and obj.is_locked:
            return self.readonly_fields + ContractTemplate.LOCKED_FIELDS
        return self.readonly_fields


@admin.register(CompanyContract)
class CompanyContractAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "company",
        "version",
        "status",
        "created_at",
        "signed_at",
        "signer_name",
    )
    list_filter = ("status", "version")
    search_fields = ("reference", "company__name", "signer_name", "signer_email")
    list_select_related = ("company", "signed_by")
    readonly_fields = [f.name for f in CompanyContract._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "content_type", "size", "uploaded_at")
    list_filter = ("company",)
    search_fields = ("name", "company__name")
    readonly_fields = ("uploaded_at", "size", "content_type")
    exclude = ("data",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_label", "action", "company", "description")
    list_filter = ("action", "company", "created_at")
    search_fields = ("actor_label", "description", "entity_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    list_select_related = ("company", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
