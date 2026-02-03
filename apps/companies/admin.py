from django.contrib import admin
from django.utils import timezone

from .models import Company, CompanyMember


class CompanyMemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name", "slug", "domain", "domain_verified",
        "verification_status", "industry", "size",
    )
    list_filter = ("domain_verified", "verification_status", "size", "industry")
    search_fields = ("name", "slug", "domain")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [CompanyMemberInline]
    readonly_fields = ("verified_at", "verified_by")
    actions = ["approve_verification", "reject_verification"]

    @admin.action(description="Approve selected companies")
    def approve_verification(self, request, queryset):
        count = queryset.filter(verification_status="pending").update(
            verification_status="verified",
            verified_at=timezone.now(),
            verified_by=request.user,
        )
        self.message_user(request, f"{count} company(ies) approved.")

    @admin.action(description="Reject selected companies")
    def reject_verification(self, request, queryset):
        count = queryset.filter(verification_status="pending").update(
            verification_status="rejected",
        )
        self.message_user(request, f"{count} company(ies) rejected.")


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role")
    list_filter = ("role",)
