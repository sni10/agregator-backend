from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    """A message from the /contact form. Kept even if the email to the editors was not sent."""

    class Topic(models.TextChoices):
        QUESTION = 'question', 'Question or feedback'
        CORRECTION = 'correction', 'Error in a story'
        COPYRIGHT = 'copyright', 'Copyright'
        OTHER = 'other', 'Other'

    topic = models.CharField(max_length=20, choices=Topic, default=Topic.QUESTION)
    email = models.EmailField(help_text='Reply here')
    page_url = models.CharField(max_length=500, blank=True, help_text='The story it is about, if any')
    message = models.TextField()
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_topic_display()}: {self.email}'
