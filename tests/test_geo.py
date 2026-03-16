import pytest
from app.services.geo import haversine_distance, is_within_range


class TestHaversineDistance:
    def test_same_location_is_zero(self):
        d = haversine_distance(-0.3031, 36.0800, -0.3031, 36.0800)
        assert d == 0.0

    def test_known_distance(self):
        # ~111km per degree latitude
        d = haversine_distance(0, 0, 1, 0)
        assert 111_000 < d < 112_000

    def test_short_distance(self):
        # Two points ~30m apart
        d = haversine_distance(-0.30310, 36.08000, -0.30337, 36.08000)
        assert 25 < d < 35


class TestIsWithinRange:
    def test_within_range(self):
        # Same location — should be within any range
        within, dist = is_within_range(-0.3031, 36.08, -0.3031, 36.08, 50)
        assert within is True
        assert dist == 0.0

    def test_outside_range(self):
        # ~300m away — outside 50m limit
        within, dist = is_within_range(-0.3031, 36.08, -0.3058, 36.08, 50)
        assert within is False
        assert dist > 50

    def test_boundary_exact(self):
        # Just inside
        within, dist = is_within_range(0, 0, 0, 0, 0)
        assert within is True
