import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return the great-circle distance in **metres** between two GPS coordinates
    using the Haversine formula.
    """
    R = 6_371_000  # Earth radius in metres

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def is_within_range(
    lecturer_lat: float,
    lecturer_lon: float,
    student_lat: float,
    student_lon: float,
    max_distance_meters: float,
) -> tuple[bool, float]:
    """
    Returns (is_within_range, distance_in_metres).
    """
    distance = haversine_distance(lecturer_lat, lecturer_lon, student_lat, student_lon)
    return distance <= max_distance_meters, distance
