"""Shared helper for list pages that can be searched, filtered, sorted and paged.

Every filter, sort and page number lives in the address (e.g. /central?search=cola&sort=-qty&page=2),
so the pages work without JavaScript, can be bookmarked, and the browser's Back button works.
"""
from flask import request

from app.services.errors import ValidationError


def run_listing(list_function, per_page, default_sort=None, **filters):
    """Call a services list function with the filters from the address.

    Returns (result, sort, error):
    - result: the services page envelope (items, page, total, pages, ...)
    - sort:   the sort actually used, for the column headers
    - error:  None, or a message when a value in the address was not valid; the
              list is then shown unfiltered so the page still works (the error state).
    """
    sort = request.args.get("sort") or default_sort
    kwargs = dict(filters, page=request.args.get("page"), per_page=per_page)
    if default_sort is not None:
        kwargs["sort"] = sort
    try:
        return list_function(**kwargs), sort or "", None
    except ValidationError as error:
        fallback = {"per_page": per_page}
        if default_sort is not None:
            fallback["sort"] = default_sort
        return list_function(**fallback), default_sort or "", error.message
