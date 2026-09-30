"""Chart labels step aside instead of covering each other."""

import pygame

from src.ui import label_layout


def test_second_label_moves_off_the_first():
    field = label_layout.LabelField((0, 0, 400, 300))
    first = field.place((40, 16), label_layout.around((100, 100), (40, 16)))
    second = field.place((40, 16), label_layout.around((102, 101), (40, 16)))
    assert first.topleft == (100, 100)
    assert not first.colliderect(second)


def test_label_stays_inside_the_chart():
    field = label_layout.LabelField((10, 10, 200, 100))
    rect = field.place((60, 16), label_layout.around((190, 0), (60, 16)))
    assert pygame.Rect(10, 10, 200, 100).contains(rect)


def test_reserved_symbol_is_kept_free():
    field = label_layout.LabelField((0, 0, 400, 300))
    field.reserve((95, 95, 30, 30))
    rect = field.place((40, 16), label_layout.around((100, 100), (40, 16)))
    assert not rect.colliderect(pygame.Rect(95, 95, 30, 30))


def test_crowded_label_is_never_dropped_and_placement_is_deterministic():
    def run():
        field = label_layout.LabelField((0, 0, 120, 40))
        return [field.place((50, 16), label_layout.around((30, 10), (50, 16))).topleft
                for _ in range(12)]
    first = run()
    assert len(first) == 12
    assert first == run()


def test_bearing_labels_slide_along_their_line():
    field = label_layout.LabelField((0, 0, 600, 600))
    origin, unit = (300, 300), (0.0, -1.0)
    a = field.place((30, 16), label_layout.along(origin, unit, (90, 125, 160), (30, 16)))
    b = field.place((30, 16), label_layout.along(origin, unit, (90, 125, 160), (30, 16)))
    assert not a.colliderect(b)


def test_map_label_uses_the_active_scope():
    from types import SimpleNamespace
    from src.ui.map_view import _map_label
    pygame.font.init()
    surface = pygame.Surface((400, 300))
    game = SimpleNamespace(font=pygame.font.Font(None, 18))
    with label_layout.label_scope((0, 0, 400, 300)) as field:
        _map_label(surface, game, "K02", (100, 100), (255, 255, 255), (0, 0, 400, 300))
        _map_label(surface, game, "K06", (101, 100), (255, 255, 255), (0, 0, 400, 300))
    assert len(field.rects) == 2
    assert not field.rects[0].colliderect(field.rects[1])
