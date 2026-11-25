"""Shared test setup.

The mechanics tests place ships and submarines at fixed spots of a seed's
map and were written against the synthetic reference sea; they run in it.
A test marked ``real_sea`` sees the real depths and surface layer of the
sector (``src/world/real_ocean.py``), as the game does.
"""

import pytest

from src.world import real_ocean


@pytest.fixture(autouse=True)
def _reference_sea(request):
    if request.node.get_closest_marker("real_sea"):
        yield
        return
    with real_ocean.reference_sea():
        yield
