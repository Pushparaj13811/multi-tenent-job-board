from rest_framework.pagination import CursorPagination


class HireFlowCursorPagination(CursorPagination):
    """
    Cursor-based pagination for all list endpoints.
    Provides consistent results under concurrent writes and O(log n) performance.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    ordering = "-created_at"
