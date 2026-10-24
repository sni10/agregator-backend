from rest_framework import serializers

from publications.models import Category, Publication, PublicationSource


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['slug', 'name']


class StoryLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publication
        fields = ['slug', 'title', 'published_at']


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicationSource
        fields = ['title', 'url', 'publisher', 'published_at']


class PublicationListSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    source_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Publication
        fields = ['slug', 'type', 'category', 'title', 'summary', 'event_at', 'published_at', 'source_count']


class PublicationDetailSerializer(PublicationListSerializer):
    sources = SourceSerializer(many=True)
    previous = serializers.SerializerMethodField()
    follow_ups = serializers.SerializerMethodField()

    class Meta(PublicationListSerializer.Meta):
        fields = [*PublicationListSerializer.Meta.fields, 'body_html', 'sources', 'previous', 'follow_ups',
                  'updated_at']

    def get_previous(self, publication) -> dict | None:
        previous = publication.previous
        if previous is None or not Publication.objects.published().filter(pk=previous.pk).exists():
            return None
        return StoryLinkSerializer(previous).data

    def get_follow_ups(self, publication) -> list[dict]:
        return StoryLinkSerializer(publication.follow_ups.published().order_by('published_at'), many=True).data
