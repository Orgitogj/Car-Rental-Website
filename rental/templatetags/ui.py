import json
from decimal import Decimal, InvalidOperation
from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
register = template.Library()


@register.filter
def to_json(value):
    return json.dumps(value, default=str, separators=(",", ":"))
@register.simple_tag
def icon(name, css="", size=None):
    """Render a sprite icon.

    Always carries the `icon` class, which supplies a default size. Contexts
    that want their own override it (`.btn svg`, `.sidebar__link svg`, …);
    without the class, an icon in a context nobody styled falls back to the
    SVG default of 300x150. An explicit `size` is written as an inline style
    rather than width/height attributes, since a stylesheet beats presentation
    attributes but not inline styles.
    """
    classes = f"icon {css}".strip()
    style = f' style="width:{size}px;height:{size}px"' if size else ""
    return mark_safe(
        f'<svg class="{classes}"{style} aria-hidden="true" focusable="false">'
        f'<use href="#i-{name}"></use></svg>'
    )


@register.simple_tag
def flag(code, css=""):
    
    code = (code or "").split("-")[0].lower()
    if code not in FLAGS:
        return icon("globe", css=f"flag {css}".strip())

    classes = f"flag {css}".strip()
    return mark_safe(
        f'<svg class="{classes}" viewBox="0 0 60 40" aria-hidden="true" '
        f'focusable="false"><use href="#f-{code}"></use></svg>'
    )

FLAGS = {"sq", "en", "it", "de"}


@register.simple_tag
def money(value, symbol=None):
    currency = symbol or settings.DEFAULT_CURRENCY_SYMBOL
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal(0)
    return format_html("{}{}", currency, f"{amount:,.2f}")


@register.filter
def money_plain(value):
    try:
        amount = Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal(0)
    return f"{settings.DEFAULT_CURRENCY_SYMBOL}{amount:,.2f}"


@register.filter
def compact_number(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return value

    for limit, suffix in ((1_000_000_000, "b"), (1_000_000, "m"), (1_000, "k")):
        if abs(number) >= limit:
            trimmed = number / limit
            return f"{trimmed:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{int(number):,}"


@register.simple_tag
def page_window(page_obj, radius=2):

    if page_obj is None:
        return []

    current = page_obj.number
    total = page_obj.paginator.num_pages

    if total <= 7 + radius:
        return list(range(1, total + 1))

    pages = {1, total}
    pages.update(range(max(1, current - radius), min(total, current + radius) + 1))

    ordered = sorted(pages)
    output = []
    previous = 0
    for number in ordered:
        if previous and number - previous > 1:
            output.append(None)
        output.append(number)
        previous = number
    return output


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs):
    
    request = context.get("request")
    if request is None:
        return ""

    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()


@register.filter
def status_tone(value):
   
    return {
        "confirmed": "success",
        "active": "success",
        "completed": "success",
        "pending": "warning",
        "scheduled": "warning",
        "in_progress": "info",
        "cancelled": "danger",
        "suspended": "danger",
    }.get(str(value).lower(), "neutral")


@register.filter
def percentage_of(part, whole):
    
    try:
        part = float(part or 0)
        whole = float(whole or 0)
    except (TypeError, ValueError):
        return 0
    if not whole:
        return 0
    return round(part / whole * 100)


@register.inclusion_tag("components/field.html")
def field(bound_field, **kwargs):

    return {
        "field": bound_field,
        "wide": kwargs.get("wide", False),
        "placeholder": kwargs.get("placeholder", ""),
        "icon_name": kwargs.get("icon_name", ""),
        "toggle": kwargs.get("toggle", False),
        "optional_hint": kwargs.get("optional_hint", False),
    }


@register.inclusion_tag("components/empty_state.html")
def empty_state(title, text="", icon_name="inbox", action_url="", action_label="", compact=False):
    return {
        "title": title,
        "text": text,
        "icon_name": icon_name,
        "action_url": action_url,
        "action_label": action_label,
        "compact": compact,
    }


@register.inclusion_tag("components/restricted_action.html")
def restricted_action(
    label="",
    icon_name="",
    base="btn",
    variant="",
    size="",
    aria_label="",
    reason="",
):
    return {
        "label": label,
        "icon_name": icon_name,
        "base": base,
        "variant": variant,
        "size": size,
        "aria_label": aria_label or label,
        "reason": reason
        or _("This action is not available from the SuperAdmin site."),
    }


@register.inclusion_tag("components/pagination.html", takes_context=True)
def pagination(context, page_obj):
    return {
        "page_obj": page_obj,
        "request": context.get("request"),
    }


TONE_BY_LEVEL = {
    "debug": "info",
    "info": "info",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}


@register.simple_tag
def messages_payload(messages):
   
    return [
        {"message": str(message), "tone": TONE_BY_LEVEL.get(message.level_tag, "info")}
        for message in messages
    ]


@register.filter
def get_item(mapping, key):
    
    try:
        return mapping.get(key)
    except AttributeError:
        return None
