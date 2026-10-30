from rest_framework import serializers

from publications.images import variants

from . import coins
from publications.models import Category, Image, Publication, PublicationSource, Tag


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['slug', 'name']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['slug', 'name']


class TagPageSerializer(TagSerializer):
    """`indexed`: enough stories for search engines; the front adds noindex otherwise."""

    count = serializers.IntegerField()
    indexed = serializers.SerializerMethodField()

    class Meta(TagSerializer.Meta):
        fields = [*TagSerializer.Meta.fields, 'count', 'indexed']

    def get_indexed(self, tag) -> bool:
        return tag.count >= Tag.MIN_STORIES


class TrendingTagSerializer(TagSerializer):
    count = serializers.IntegerField(help_text='Stories of the last days')

    class Meta(TagSerializer.Meta):
        fields = [*TagSerializer.Meta.fields, 'count']


class StoryLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publication
        fields = ['slug', 'title', 'published_at']


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicationSource
        fields = ['title', 'url', 'publisher', 'published_at']


class ImageSerializer(serializers.ModelSerializer):
    """`src` is the largest variant (also for og:image), `srcset` all of them; the credit goes under the photo."""

    src = serializers.SerializerMethodField()
    srcset = serializers.SerializerMethodField()
    source = serializers.CharField(source='get_source_display')

    class Meta:
        model = Image
        fields = ['src', 'srcset', 'width', 'height', 'author', 'author_url', 'source', 'page_url']

    def get_src(self, image) -> str:
        return variants(image)[0][1]

    def get_srcset(self, image) -> str:
        return ', '.join(f'{url} {width}w' for width, url in reversed(variants(image)))


class PublicationListSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    source_count = serializers.IntegerField(read_only=True)
    publishers = serializers.SerializerMethodField()
    image = ImageSerializer(allow_null=True)

    class Meta:
        model = Publication
        fields = ['slug', 'type', 'category', 'title', 'summary', 'image', 'event_at', 'published_at',
                  'source_count', 'publishers', 'views']

    def get_publishers(self, publication) -> list[str]:
        """Who wrote the sources, each once, in the story's order: the card names them."""
        return list(dict.fromkeys(source.publisher for source in publication.sources.all()))


class PublicationDetailSerializer(PublicationListSerializer):
    sources = SourceSerializer(many=True)
    previous = serializers.SerializerMethodField()
    follow_ups = serializers.SerializerMethodField()
    coins = serializers.SerializerMethodField()
    tags = TagSerializer(many=True)

    class Meta(PublicationListSerializer.Meta):
        fields = [*PublicationListSerializer.Meta.fields, 'body_html', 'sources', 'previous', 'follow_ups',
                  'coins', 'tags', 'updated_at']

    def get_previous(self, publication) -> dict | None:
        previous = publication.previous
        if previous is None or not Publication.objects.published().filter(pk=previous.pk).exists():
            return None
        return StoryLinkSerializer(previous).data

    def get_follow_ups(self, publication) -> list[dict]:
        return StoryLinkSerializer(publication.follow_ups.published().order_by('published_at'), many=True).data

    def get_coins(self, publication) -> list[str]:
        """CoinGecko ids of the coins the story names: the front shows their prices (GET /prices)."""
        return coins.mentioned(publication.title, publication.summary, publication.body_md)


class SuggestionSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = Publication
        fields = ['slug', 'title', 'category']


class PriceSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="CoinGecko id, as in a story's `coins`")
    symbol = serializers.CharField()
    name = serializers.CharField()
    usd = serializers.FloatField()
    change_24h = serializers.FloatField(allow_null=True, help_text='Percent')


class HomeSectionSerializer(serializers.Serializer):
    category = CategorySerializer()
    stories = PublicationListSerializer(many=True)


class HomeSerializer(serializers.Serializer):
    lead = PublicationListSerializer(many=True, help_text='The top story first, then the ones beside it')
    latest = PublicationListSerializer(many=True)
    sections = HomeSectionSerializer(many=True, help_text='A block per category, without the stories above')
    most_read = PublicationListSerializer(many=True, help_text='Of the last days; empty while nobody reads')
