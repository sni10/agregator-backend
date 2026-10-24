from django.contrib import admin

from .models import PublishAudit


@admin.register(PublishAudit)
class PublishAuditAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'action', 'external_id', 'status_code', 'request_id']
    list_filter = ['action', 'status_code']
    search_fields = ['external_id', 'request_id']
    readonly_fields = ['created_at', 'action', 'external_id', 'status_code', 'request_id', 'result']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
