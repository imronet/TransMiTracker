"""Versioned local GTFS schedule catalog; no realtime or tracking."""


class CatalogError(ValueError):
    """An import or requested itinerary cannot be validated."""
