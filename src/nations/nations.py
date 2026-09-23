"""Public chart and platform reference for the N overlay.

Live entities do not belong here: they could reveal unobserved contacts.
"""

from src.data.catalog import CIVIL_CATEGORIES


def reference_summary(coast, catalog):
    """Summarize known geography and catalog profiles deterministically."""
    metadata = coast.metadata or {}
    countries = metadata.get("countries")
    if countries is None:
        countries = [land.nation for land in coast.landmasses]
    surfaces = tuple(catalog.surfaces.values())
    return {
        "countries": tuple(sorted(set(countries))),
        "friendly": tuple(sorted(p.name for p in surfaces
                                 if p.default_faction == "FREUND")),
        "hostile_subs": tuple(sorted(p.name for p in catalog.subs.values()
                                     if p.default_faction == "FEIND")),
        "hostile_surfaces": tuple(sorted(p.name for p in surfaces
                                         if p.default_faction == "FEIND")),
        "neutral_military": sum(p.category == "KAMPFSCHIFF"
                                and p.default_faction == "NEUTRAL"
                                for p in surfaces),
        "civilian": sum(p.category in CIVIL_CATEGORIES for p in surfaces),
    }
