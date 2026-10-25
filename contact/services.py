import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage

from .models import ContactMessage

logger = logging.getLogger(__name__)

SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def captcha_passed(token: str, ip: str) -> bool:
    """Checks a Cloudflare Turnstile token. Cloudflare down or a timeout counts as not passed."""
    data = urllib.parse.urlencode({'secret': settings.TURNSTILE_SECRET, 'response': token, 'remoteip': ip}).encode()
    try:
        with urllib.request.urlopen(SITEVERIFY_URL, data, timeout=5) as r:
            return json.load(r).get('success') is True
    except Exception:
        logger.warning('Turnstile siteverify failed', exc_info=True)
        return False


class ContactService:
    """Stores a message and emails it to CONTACT_EMAIL (never shown to visitors), Reply-To = the sender."""

    def submit(self, *, topic: str, email: str, page_url: str, message: str, ip: str, user_agent: str,
               user=None) -> ContactMessage:
        contact = ContactMessage.objects.create(topic=topic, email=email, page_url=page_url, message=message,
                                                ip=ip[:64], user_agent=user_agent[:500], user=user)
        if not settings.CONTACT_EMAIL:
            logger.warning('CONTACT_EMAIL is not set, message %s is only in the admin', contact.pk)
            return contact
        try:  # the message is saved; a mail failure must not become a 500 for the visitor
            self._email(contact).send()
        except Exception:
            logger.exception('Could not email contact message %s', contact.pk)
        return contact

    @staticmethod
    def _email(c: ContactMessage) -> EmailMessage:
        user = f'{c.user.pk} ({c.user.email})' if c.user else 'guest'
        body = '\n'.join([
            f'Topic: {c.get_topic_display()}',
            f'Email: {c.email}',
            f'Page: {c.page_url or "-"}',
            f'User: {user}',
            f'IP: {c.ip}',
            f'User-Agent: {c.user_agent}',
            f'Time (UTC): {c.created_at:%Y-%m-%d %H:%M:%S}',
            '',
            c.message,
        ])
        return EmailMessage(f'[{settings.SITE_NAME}] {c.get_topic_display()}: {c.email}', body, None,
                            [settings.CONTACT_EMAIL], reply_to=[c.email])  # None -> DEFAULT_FROM_EMAIL
