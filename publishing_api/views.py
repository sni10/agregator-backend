from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from publications import services
from publications.models import Publication

from .models import PublishAudit
from .permissions import HasPublishingKey
from .serializers import PublicationPayloadSerializer, PublicationStateSerializer

AUDIT_RESULT_LENGTH = 500
ACTIONS = {'POST': 'create', 'PUT': 'update', 'GET': 'get'}
KEY_ERROR = OpenApiResponse(description='Missing or invalid X-Api-Key, or publishing is off on the server')


class PublishingView(APIView):
    permission_classes = [HasPublishingKey]
    throttle_scope = 'publishing'

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        PublishAudit.objects.create(
            external_id=kwargs.get('external_id') or _external_id(request),
            request_id=request.headers.get('X-Request-Id', '')[:100],
            action=ACTIONS.get(request.method, request.method.lower()),
            status_code=response.status_code,
            result=str(getattr(response, 'data', '') or '')[:AUDIT_RESULT_LENGTH],
        )
        return response


class PublicationCreateView(PublishingView):
    @extend_schema(
        request=PublicationPayloadSerializer,
        responses={201: PublicationStateSerializer, 200: PublicationStateSerializer, 403: KEY_ERROR},
        description='Create a story. Idempotent by `external_id`: a repeat answers 200 with the existing story '
                    'unchanged. Changes go through PUT.',
    )
    def post(self, request):
        payload = PublicationPayloadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        publication, created = services.create(payload.validated_data)
        return _state(publication, status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PublicationDetailView(PublishingView):
    @extend_schema(responses={200: PublicationStateSerializer, 403: KEY_ERROR, 404: None})
    def get(self, request, external_id):
        return _state(get_object_or_404(Publication, external_id=external_id))

    @extend_schema(
        request=PublicationPayloadSerializer,
        parameters=[OpenApiParameter('If-Match', str, OpenApiParameter.HEADER, required=True,
                                     description='The revision this update is based on')],
        responses={200: PublicationStateSerializer, 403: KEY_ERROR, 404: None,
                   412: OpenApiResponse(description='The story has a newer revision (e.g. an admin edit)'),
                   428: OpenApiResponse(description='No If-Match header')},
        description='A new revision of the story. A withdrawn story stays withdrawn.',
    )
    def put(self, request, external_id):
        publication = get_object_or_404(Publication, external_id=external_id)
        expected = _revision(request.headers.get('If-Match'))
        if expected is None:
            return Response({'detail': 'If-Match: <revision> is required.'},
                            status=status.HTTP_428_PRECONDITION_REQUIRED)
        payload = PublicationPayloadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        if payload.validated_data['external_id'] != external_id:
            return Response({'external_id': ['Does not match the URL.']}, status=status.HTTP_400_BAD_REQUEST)
        try:
            publication = services.update(publication, payload.validated_data, expected)
        except services.RevisionConflict as exc:
            return Response({'detail': f'Revision {expected} is not current.', 'revision': exc.current},
                            status=status.HTTP_412_PRECONDITION_FAILED)
        return _state(publication)


def health(request):
    """For the pipeline and monitoring: the app answers and the database too."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
    return JsonResponse({'status': 'ok'})


def _state(publication: Publication, code: int = status.HTTP_200_OK) -> Response:
    response = Response(PublicationStateSerializer(publication).data, status=code)
    response['ETag'] = f'"{publication.revision}"'
    return response


def _revision(header: str | None) -> int | None:
    """If-Match: 3, "3" or W/"3"."""
    value = (header or '').strip().removeprefix('W/').strip('"')
    return int(value) if value.isdigit() else None


def _external_id(request) -> str:
    try:
        return str(request.data.get('external_id', ''))[:100]
    except Exception:  # an unparsable body: the response already says so
        return ''
