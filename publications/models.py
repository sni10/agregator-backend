"""Stories on the site. They arrive from the local pipeline (publishing_api) and are read by the front (public_api).
Source texts and embeddings stay on the owner's PC: here only what the site shows."""
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector
from django.db import models
from django.utils import timezone


class Category(models.Model):
    slug = models.SlugField(unique=True)  # it, ai, crypto
    name = models.CharField(max_length=50)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['position', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class PublicationQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Publication.Status.PUBLISHED, published_at__lte=timezone.now())


class Publication(models.Model):
    class Type(models.TextChoices):
        EVENT = 'event', 'Event'
        DIGEST = 'digest', 'Weekly digest'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'Needs review'  # the pipeline was not sure: a human publishes or withdraws it
        PUBLISHED = 'published', 'Published'
        WITHDRAWN = 'withdrawn', 'Withdrawn'  # taken down by a human; the pipeline cannot bring it back

    external_id = models.CharField(max_length=100, unique=True, help_text="The pipeline's id: idempotency key")
    slug = models.SlugField(max_length=120, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='publications')
    type = models.CharField(max_length=10, choices=Type, default=Type.EVENT)
    title = models.CharField(max_length=300)
    summary = models.TextField()
    body_md = models.TextField(help_text='Markdown as sent by the pipeline or edited in the admin')
    body_html = models.TextField(editable=False, help_text='Rendered from body_md and sanitized (nh3)')
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT, db_index=True)
    revision = models.PositiveIntegerField(default=1)
    previous = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='follow_ups',
                                 help_text='The story this one follows up')
    event_at = models.DateTimeField(null=True, blank=True, help_text='When it happened (earliest source)')
    published_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                        help_text='Set by the server the first time it is published')
    quality = models.JSONField(default=dict, blank=True, help_text="The pipeline's report: not a proof of anything")
    image_queries = models.JSONField(default=list, blank=True, help_text='Stock photo searches (images come later)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublicationQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [
            GinIndex(SearchVector('title', 'summary', 'body_md', config='english'), name='publication_search'),
        ]

    def __str__(self):
        return self.title

    def publish(self) -> None:
        self.status = self.Status.PUBLISHED
        self.published_at = self.published_at or timezone.now()


class PublicationSource(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='sources')
    position = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000)
    publisher = models.CharField(max_length=200)
    published_at = models.DateTimeField(null=True, blank=True)
    is_independent = models.BooleanField(default=True, help_text='False for a reprint of the same press release')

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.publisher}: {self.title}'


class PublicationRevision(models.Model):
    """Every version of a story's text, from the pipeline or the admin."""

    class Author(models.TextChoices):
        PIPELINE = 'pipeline', 'Pipeline'
        ADMIN = 'admin', 'Admin'

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='revisions')
    revision = models.PositiveIntegerField()
    title = models.CharField(max_length=300)
    summary = models.TextField()
    body_md = models.TextField()
    quality = models.JSONField(default=dict, blank=True)
    author = models.CharField(max_length=10, choices=Author)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-revision']
        constraints = [models.UniqueConstraint(fields=['publication', 'revision'], name='unique_publication_revision')]

    def __str__(self):
        return f'{self.publication} r{self.revision}'
