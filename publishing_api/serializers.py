from rest_framework import serializers

from publications.models import Category, Image, Publication

EXTERNAL_ID = r'^[A-Za-z0-9][A-Za-z0-9._-]*$'


class SourcePayloadSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=500)
    url = serializers.URLField(max_length=1000)
    publisher = serializers.CharField(max_length=200)
    published_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    is_independent = serializers.BooleanField(default=True)

    def validate_url(self, url):
        if not url.startswith(('http://', 'https://')):
            raise serializers.ValidationError('Only http(s) links.')
        return url


class PublicationPayloadSerializer(serializers.Serializer):
    """What the pipeline sends. Markdown only: the server renders and sanitizes the HTML itself."""

    external_id = serializers.RegexField(EXTERNAL_ID, max_length=100)
    category = serializers.SlugRelatedField(slug_field='slug', queryset=Category.objects.all())
    type = serializers.ChoiceField(choices=Publication.Type.choices, default=Publication.Type.EVENT)
    # The pipeline asks; the server decides (a withdrawn story stays withdrawn)
    status = serializers.ChoiceField(choices=[Publication.Status.PUBLISHED, Publication.Status.REVIEW])
    title = serializers.CharField(max_length=300)
    summary = serializers.CharField(max_length=1000)
    body_md = serializers.CharField(max_length=20000)
    sources = SourcePayloadSerializer(many=True, min_length=1, max_length=30)
    previous_external_id = serializers.CharField(max_length=100, required=False, allow_null=True, default=None)
    event_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    quality = serializers.DictField(required=False, default=dict)
    image_queries = serializers.ListField(child=serializers.CharField(max_length=100), max_length=5, required=False,
                                          default=list)

    def validate(self, data):
        previous_id = data.pop('previous_external_id')
        data['previous'] = None
        if previous_id:
            data['previous'] = Publication.objects.filter(external_id=previous_id).first()
            if data['previous'] is None:
                raise serializers.ValidationError({'previous_external_id': 'No publication with this external_id.'})
        return data


class ImageUploadSerializer(serializers.Serializer):
    """A stock photo for a story (multipart). The file is checked and converted by publications/images.py."""

    MAX_BYTES = 15 * 1024 * 1024

    file = serializers.FileField()
    external_id = serializers.RegexField(EXTERNAL_ID, max_length=100)
    source = serializers.ChoiceField(choices=Image.Source.choices)
    author = serializers.CharField(max_length=200)
    author_url = serializers.URLField(max_length=500, required=False, allow_blank=True, default='')
    page_url = serializers.URLField(max_length=500)

    def validate_file(self, file):
        if file.size > self.MAX_BYTES:
            raise serializers.ValidationError(f'Larger than {self.MAX_BYTES // 1024 // 1024} MB.')
        return file

    def validate(self, data):
        for field in ('author_url', 'page_url'):
            if data[field] and not data[field].startswith('https://'):
                raise serializers.ValidationError({field: 'Only https links.'})
        return data


class TagsPayloadSerializer(serializers.Serializer):
    tags = serializers.ListField(child=serializers.CharField(max_length=60), max_length=8)


class PublicationStateSerializer(serializers.ModelSerializer):
    """What the pipeline gets back: enough to know where the story stands."""

    image = serializers.SlugRelatedField(slug_field='external_id', read_only=True)
    tags = serializers.SlugRelatedField(slug_field='name', many=True, read_only=True)

    class Meta:
        model = Publication
        fields = ['external_id', 'slug', 'status', 'revision', 'image', 'tags', 'published_at', 'updated_at']
