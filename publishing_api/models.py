from django.db import models


class PublishAudit(models.Model):
    """One row per publishing API request: what the pipeline asked and what it got."""

    external_id = models.CharField(max_length=100, blank=True, db_index=True)
    request_id = models.CharField(max_length=100, blank=True, help_text='X-Request-Id from the pipeline')
    action = models.CharField(max_length=10)  # create / update / get / image
    status_code = models.PositiveSmallIntegerField()
    result = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} {self.external_id}: {self.status_code}'
