from django.contrib import admin, messages
from django.utils.html import format_html

from . import services
from .images import variants
from .models import Category, Image, Publication, PublicationRevision, PublicationSource


class SourceInline(admin.TabularInline):
    model = PublicationSource
    fields = ['position', 'publisher', 'title', 'url', 'published_at', 'is_independent']
    extra = 0


class RevisionInline(admin.TabularInline):
    model = PublicationRevision
    fields = ['revision', 'author', 'title', 'created_at']
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """The review queue: Status = Needs review. Publish or withdraw from the list, or edit the text first."""

    list_display = ['title', 'category', 'status', 'source_count', 'views', 'revision', 'published_at',
                    'created_at']
    list_filter = ['status', 'category', 'type']
    search_fields = ['title', 'external_id', 'slug']
    readonly_fields = ['external_id', 'revision', 'views', 'published_at', 'preview', 'photo', 'quality',
                       'image_queries', 'previous', 'created_at', 'updated_at']
    fields = ['status', 'category', 'type', 'title', 'slug', 'summary', 'body_md', 'event_at', 'preview', 'image',
              *[field for field in readonly_fields if field != 'preview']]
    raw_id_fields = ['image']
    inlines = [SourceInline, RevisionInline]
    actions = ['publish', 'withdraw']
    list_select_related = ['category']

    def has_add_permission(self, request):
        return False  # stories come from the pipeline

    @admin.display(description='sources')
    def source_count(self, publication):
        return publication.sources.count()

    @admin.display(description='as on the site')
    def preview(self, publication):
        return format_html('<div style="max-width: 46em; font-size: 15px; line-height: 1.5"><h2>{}</h2>'
                           '<p><b>{}</b></p>{}</div>', publication.title, publication.summary, publication.body_html)

    @admin.display(description='photo')
    def photo(self, publication):
        return image_preview(publication.image)

    def save_model(self, request, publication, form, change):
        services.save_admin_edit(publication)

    @admin.action(description='Publish selected')
    def publish(self, request, queryset):
        for publication in queryset.exclude(status=Publication.Status.PUBLISHED):
            publication.publish()
            publication.save(update_fields=['status', 'published_at', 'updated_at'])
        self.message_user(request, 'Published.', messages.SUCCESS)

    @admin.action(description='Withdraw selected (the pipeline cannot republish them)')
    def withdraw(self, request, queryset):
        queryset.update(status=Publication.Status.WITHDRAWN)
        self.message_user(request, 'Withdrawn.', messages.SUCCESS)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'position']
    prepopulated_fields = {'slug': ['name']}



@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['external_id', 'author', 'source', 'width', 'created_at']
    search_fields = ['external_id', 'author']
    readonly_fields = ['preview', 'external_id', 'source', 'author', 'author_url', 'page_url', 'width', 'height',
                       'created_at']

    def has_add_permission(self, request):
        return False  # images come from the pipeline

    @admin.display(description='preview')
    def preview(self, image):
        return image_preview(image)


def image_preview(image: Image | None) -> str:
    if image is None:
        return '— (the category cover)'
    return format_html('<a href="{}" target="_blank"><img src="{}" width="300" alt=""></a><br>{} · {}',
                       image.page_url, dict(variants(image))[600], image.author, image.get_source_display())
