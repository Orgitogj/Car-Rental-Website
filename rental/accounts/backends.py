from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class UsernameOrEmailBackend(ModelBackend):
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        user_model = get_user_model()

        if username is None:
            username = kwargs.get(user_model.USERNAME_FIELD)
        if not username or not password:
            return None

        identifier = username.strip()
        candidates = user_model._default_manager.filter(
            Q(**{f"{user_model.USERNAME_FIELD}__iexact": identifier})
            | Q(email__iexact=identifier)
        ).order_by("pk")

        for user in candidates:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        if not candidates:
            user_model().set_password(password)

        return None
