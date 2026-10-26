"""Stories on the site. They arrive from the local pipeline (publishing_api) and are read by the front (public_api).
Source texts and embeddings stay on the owner's PC: here only what the site shows."""
from django.conf import settings
from django.contrib.postgres.indexes import GinIndex, OpClass
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


class Image(models.Model):
    """A stock photo, stored as WebP variants (publications/images.py). The pipeline picks and uploads it."""

    class Source(models.TextChoices):
        PIXABAY = 'pixabay', 'Pixabay'

    external_id = models.CharField(max_length=100, unique=True, help_text="The stock site's id, e.g. pixabay-195893")
    source = models.CharField(max_length=20, choices=Source)
    author = models.CharField(max_length=200)
    author_url = models.URLField(max_length=500, blank=True)
    page_url = models.URLField(max_length=500, help_text='The photo on the stock site')
    width = models.PositiveIntegerField(help_text='Of the largest variant')
    height = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.external_id

    def file_name(self, width: int) -> str:
        return f'images/{self.external_id}-{width}.webp'


class Tag(models.Model):
    """A subject that runs through many stories: a company, a product, a coin, a topic. The pipeline sets them."""

    MIN_STORIES = 3  # a tag page with fewer is kept out of search engines (noindex, not in the sitemap)

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

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
    image_queries = models.JSONField(default=list, blank=True, help_text='Stock photo searches from the writer')
    image = models.ForeignKey(Image, null=True, blank=True, on_delete=models.SET_NULL, related_name='publications',
                              help_text='None: the front shows the category cover')
    tags = models.ManyToManyField(Tag, blank=True, related_name='publications')
    views = models.PositiveIntegerField(default=0, editable=False,
                                        help_text='Readers who opened it, once a day per IP; bots mostly left out')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublicationQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        indexes = [
            GinIndex(SearchVector('title', 'summary', 'body_md', config='english'), name='publication_search'),
            # typo-tolerant search and suggestions (pg_trgm word similarity on titles)
            GinIndex(OpClass('title', name='gin_trgm_ops'), name='publication_title_trgm'),
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


class Favorite(models.Model):
    """A story in a reader's favorites. Deleting the story or the user deletes the record."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'publication'], name='unique_favorite_per_user')]
        indexes = [models.Index(fields=['user', '-created_at'], name='favorite_user_recent')]

    def __str__(self):
        return f'{self.user} / {self.publication}'
