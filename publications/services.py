"""Create and update stories from the pipeline's payload (validated by publishing_api's serializer)."""
from django.db import IntegrityError, transaction
from django.utils.text import slugify

from common.markdown import render

from .models import Publication, PublicationRevision, PublicationSource

SLUG_LENGTH = 100


class RevisionConflict(Exception):
    """The pipeline updated a revision that is no longer the current one (an admin edit happened in between)."""

    def __init__(self, current: int):
        super().__init__(f'current revision is {current}')
        self.current = current


def create(data: dict) -> tuple[Publication, bool]:
    """A new story, or the existing one with this external_id untouched (a repeated POST changes nothing)."""
    if existing := Publication.objects.filter(external_id=data['external_id']).first():
        return existing, False
    try:
        with transaction.atomic():
            publication = Publication(external_id=data['external_id'], slug=unique_slug(data['title']))
            _apply(publication, data)
            publication.save()
            _save_sources(publication, data['sources'])
            _save_revision(publication, PublicationRevision.Author.PIPELINE)
    except IntegrityError:  # the same POST twice at once: the other one won
        return Publication.objects.get(external_id=data['external_id']), False
    return publication, True


def update(publication: Publication, data: dict, expected_revision: int) -> Publication:
    """A new revision. The slug stays, so links keep working. A withdrawn story stays withdrawn."""
    with transaction.atomic():
        publication = Publication.objects.select_for_update().get(pk=publication.pk)
        if publication.revision != expected_revision:
            raise RevisionConflict(publication.revision)
        _apply(publication, data)
        publication.revision += 1
        publication.save()
        publication.sources.all().delete()
        _save_sources(publication, data['sources'])
        _save_revision(publication, PublicationRevision.Author.PIPELINE)
    return publication


def save_admin_edit(publication: Publication) -> None:
    """An edit in the admin: re-render the text and keep it as a revision of its own."""
    publication.body_html = render(publication.body_md)
    publication.revision += 1
    if publication.status == Publication.Status.PUBLISHED:
        publication.publish()
    publication.save()
    _save_revision(publication, PublicationRevision.Author.ADMIN)


def unique_slug(title: str) -> str:
    base = slugify(title)[:SLUG_LENGTH].strip('-') or 'story'
    slug, number = base, 1
    while Publication.objects.filter(slug=slug).exists():
        number += 1
        slug = f'{base[:SLUG_LENGTH - 4]}-{number}'
    return slug


def _apply(publication: Publication, data: dict) -> None:
    for field in ('category', 'type', 'title', 'summary', 'body_md', 'event_at', 'quality', 'image_queries'):
        setattr(publication, field, data[field])
    publication.previous = data['previous']
    publication.body_html = render(publication.body_md)
    if publication.status == Publication.Status.WITHDRAWN:
        return
    if data['status'] == Publication.Status.PUBLISHED:
        publication.publish()
    else:
        publication.status = Publication.Status.REVIEW


def _save_sources(publication: Publication, sources: list[dict]) -> None:
    PublicationSource.objects.bulk_create(
        PublicationSource(publication=publication, position=position, **source)
        for position, source in enumerate(sources)
    )


def _save_revision(publication: Publication, author: str) -> None:
    PublicationRevision.objects.create(
        publication=publication, revision=publication.revision, title=publication.title, summary=publication.summary,
        body_md=publication.body_md, quality=publication.quality, author=author,
    )
