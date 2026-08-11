from django.db import models


class ContactMessageQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(is_read=False)


class ContactMessage(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()

    reply = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    replied_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = ContactMessageQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.full_name} – {self.subject}"

    @property
    def is_replied(self):
        return bool(self.reply)
