"""Shared helpers for paging, sorting and reading filter values.

Routes pass the raw text from the query string (e.g. ?page=2&per_page=20&sort=-qty);
these helpers check it and raise ValidationError with the field name if it is wrong.
"""
import math
from datetime import date

from app.extensions import db
from app.services.errors import ValidationError

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def parse_int(value, field, minimum=None, maximum=None, default=None):
    """Turn text into a whole number within limits. Empty text gives `default`."""
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a whole number.", field)
    if minimum is not None and number < minimum:
        raise ValidationError(f"{field} must be at least {minimum}.", field)
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field} must be at most {maximum}.", field)
    return number


def parse_date(value, field):
    """Turn YYYY-MM-DD text into a date. Empty text gives None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a date written as YYYY-MM-DD.", field)


def parse_choice(value, field, choices):
    """Accept only one of the allowed values. Empty text gives None."""
    if not value:
        return None
    if value not in choices:
        raise ValidationError(f"{field} must be one of: {', '.join(choices)}.", field)
    return value


def parse_sort(value, allowed, default):
    """Read ?sort=name or ?sort=-name (minus = descending).

    Returns (key, descending). Only keys listed in `allowed` are accepted, so a
    user can never sort by an arbitrary column.
    """
    value = value or default
    descending = value.startswith("-")
    key = value.lstrip("-")
    if key not in allowed:
        raise ValidationError(f"sort must be one of: {', '.join(sorted(allowed))} "
                              f"(add '-' in front for descending).", "sort")
    return key, descending


def page_params(page, per_page):
    """Check ?page and ?per_page and return them as numbers."""
    return (parse_int(page, "page", minimum=1, default=1),
            parse_int(per_page, "per_page", minimum=1, maximum=MAX_PER_PAGE, default=DEFAULT_PER_PAGE))


def _envelope(items, page, per_page, total):
    pages = max(1, math.ceil(total / per_page))
    return {"items": items, "page": page, "per_page": per_page, "total": total, "pages": pages,
            "has_prev": page > 1, "has_next": page < pages}


def paginate_list(items, page=None, per_page=None):
    """Page a list that is already in memory (used where Python builds the rows)."""
    page, per_page = page_params(page, per_page)
    start = (page - 1) * per_page
    return _envelope(items[start:start + per_page], page, per_page, len(items))


def paginate_query(query, to_dict, page=None, per_page=None):
    """Page a SELECT in the database (LIMIT/OFFSET) and turn each row into a dict."""
    page, per_page = page_params(page, per_page)
    total = db.session.scalar(db.select(db.func.count()).select_from(query.order_by(None).subquery()))
    rows = db.session.execute(query.limit(per_page).offset((page - 1) * per_page))
    return _envelope([to_dict(row) for row in rows], page, per_page, total)


def sort_list(items, key, descending):
    """Sort dict rows by one key; text sorts without caring about capitals."""
    def value(item):
        v = item[key]
        return (v is None, v.lower() if isinstance(v, str) else v)
    return sorted(items, key=value, reverse=descending)
