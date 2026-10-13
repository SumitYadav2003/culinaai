from django.core.paginator import Paginator


def paginate(request, items, per_page):
    """
    One page of a long list. Returns the page and the rest of the query string
    (search and filters) so the page links keep them.
    """

    page = Paginator(items, per_page).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()
