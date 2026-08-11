import logging
from ..models import AuditLog

logger = logging.getLogger("rental.audit")


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def actor_label(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return "anonymous"
    return (user.get_full_name() or user.username or "").strip() or f"user#{user.pk}"


def record(
    action,
    *,
    request=None,
    actor=None,
    company=None,
    entity=None,
    entity_type="",
    entity_id="",
    description="",
    metadata=None,
):
    
    if actor is None and request is not None:
        actor = getattr(request, "user", None)
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None

    if entity is not None:
        entity_type = entity_type or entity.__class__.__name__
        entity_id = entity_id or str(entity.pk)

    try:
        return AuditLog.objects.create(
            actor=actor,
            actor_label=actor_label(getattr(request, "user", None) if request else actor),
            action=action,
            description=description[:255],
            entity_type=entity_type[:50],
            entity_id=str(entity_id)[:50],
            company=company,
            ip_address=client_ip(request),
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("Failed to write audit entry for action %s", action)
        return None


def record_denied_action(request, description=""):
    context = getattr(request, "company_context", None)
    company = getattr(context, "company", None) if context else None
    return record(
        AuditLog.Action.ACCESS_DENIED,
        request=request,
        company=company,
        description=f"Blocked: {description}",
        metadata={"path": request.path, "method": request.method},
    )
