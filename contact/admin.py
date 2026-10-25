from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'topic', 'email', 'page_url', 'handled']
    list_filter = ['handled', 'topic']
    search_fields = ['email', 'message', 'page_url']
    readonly_fields = ['topic', 'email', 'page_url', 'message', 'ip', 'user_agent', 'user', 'created_at']
    fields = ['handled', *readonly_fields]

    def has_add_permission(self, request):
        return False  # messages come from the form
