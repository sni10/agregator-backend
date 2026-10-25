from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.throttling import IPScopedRateThrottle

from .models import ContactMessage
from .services import ContactService, captcha_passed

CAPTCHA_FAILED = 'The check did not pass, please try again.'


class ContactSerializer(serializers.Serializer):
    topic = serializers.ChoiceField(choices=ContactMessage.Topic.choices, default=ContactMessage.Topic.QUESTION)
    email = serializers.EmailField(max_length=254, help_text='Where to reply')
    pageUrl = serializers.URLField(max_length=500, required=False, allow_blank=True, default='',
                                   help_text='The story it is about, optional')
    message = serializers.CharField(min_length=10, max_length=5000, help_text='10 to 5000 characters')
    captcha = serializers.CharField(max_length=2048, help_text='Cloudflare Turnstile token, single use')


class ContactView(APIView):
    """Public: most writers have no account. A token, if sent, links the message to the user."""

    throttle_classes = [IPScopedRateThrottle]
    throttle_scope = 'contact'
    contact = ContactService()

    @extend_schema(
        summary='Message to the editors (contact form)', request=ContactSerializer,
        responses={
            204: OpenApiResponse(description='Received'),
            400: OpenApiResponse(description='Errors by field: topic/email/pageUrl/message/captcha '
                                             '(captcha: the token did not pass, get a new one)'),
            429: OpenApiResponse(description='More than 5 messages an hour from one IP'),
        },
    )
    def post(self, request):
        serializer = ContactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ip = IPScopedRateThrottle().get_ident(request)
        if not captcha_passed(data['captcha'], ip):
            raise ValidationError({'captcha': [CAPTCHA_FAILED]})
        self.contact.submit(
            topic=data['topic'], email=data['email'], page_url=data['pageUrl'], message=data['message'],
            ip=ip, user_agent=request.headers.get('User-Agent', ''),
            user=request.user if request.user.is_authenticated else None,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
