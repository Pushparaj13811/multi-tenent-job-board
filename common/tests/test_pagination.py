"""
Tests for HireFlowCursorPagination.
"""

from common.pagination import HireFlowCursorPagination


class TestHireFlowCursorPagination:
    def test_default_page_size_is_20(self):
        """Default page size should be 20."""
        pagination = HireFlowCursorPagination()
        assert pagination.page_size == 20

    def test_max_page_size_is_100(self):
        """Maximum allowed page size should be 100."""
        pagination = HireFlowCursorPagination()
        assert pagination.max_page_size == 100

    def test_default_ordering_is_minus_created_at(self):
        """Default ordering should be newest first (-created_at)."""
        pagination = HireFlowCursorPagination()
        assert pagination.ordering == "-created_at"
