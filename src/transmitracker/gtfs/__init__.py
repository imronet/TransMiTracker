"""Small feed readers; not a catalog service or a full GTFS validator."""


class FeedError(ValueError):
    """The payload cannot be interpreted as the expected GTFS format."""
