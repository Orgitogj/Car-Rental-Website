from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator


def paginate(request, queryset, per_page=12, param="page"):
    paginator = Paginator(queryset, per_page)
    raw = request.GET.get(param)

    try:
        return paginator.page(raw)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


def querystring(request, **overrides):

    data = request.GET.copy()
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    encoded = data.urlencode()
    return f"?{encoded}" if encoded else ""


def is_ajax(request):
   
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.headers.get("Accept", "").startswith("application/json")
    )
