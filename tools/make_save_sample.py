"""Write frozen save samples of the current format for the migration tests.

Run this on the release *before* a save-format change (or check out that
release in a worktree and run it there with ``--out``): it plays a frigate
mission (s2, two submarines) and a crewed-submarine mission (s7) for a short
while and stores both save documents under ``tests/data/saves/`` as
``v<format>-frigate.json.xz`` and ``v<format>-uboot.json.xz``.

The catalog snapshot is the bulk of a save and rarely changes, so it is stored
once per distinct content as ``catalog-<sha256 prefix>.json.xz`` and the
sample keeps ``{"$catalog": "<prefix>"}`` in its place.
``tests/test_save_migrate.py`` puts it back before loading, so every sample
still loads with the exact catalog its release wrote.

    python tools/make_save_sample.py            # current tree
    python tools/make_save_sample.py --pack old.json --name frigate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "data" / "saves"
CATALOG_REF = "$catalog"


def _dumps(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _write_xz(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(lzma.compress(payload, preset=9 | lzma.PRESET_EXTREME))
    os.replace(temporary, path)


def pack(document: dict, name: str, out: Path = SAMPLES) -> Path:
    """Store one save document as a sample with its catalog split off."""
    document = dict(document)
    catalog = _dumps(document["catalog_snapshot"])
    digest = hashlib.sha256(catalog).hexdigest()[:16]
    catalog_path = out / f"catalog-{digest}.json.xz"
    if not catalog_path.exists():
        _write_xz(catalog_path, catalog)
    document["catalog_snapshot"] = {CATALOG_REF: digest}
    path = out / f"v{document['version']}-{name}.json.xz"
    _write_xz(path, _dumps(document))
    return path


def unpack(path: Path) -> dict:
    """A sample as the save document its release wrote."""
    document = json.loads(lzma.decompress(Path(path).read_bytes()))
    reference = document["catalog_snapshot"][CATALOG_REF]
    catalog_path = Path(path).parent / f"catalog-{reference}.json.xz"
    document["catalog_snapshot"] = json.loads(lzma.decompress(catalog_path.read_bytes()))
    return document


def play(frigate_updates: int = 150, boat_updates: int = 100) -> dict:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    sys.path.insert(0, str(ROOT))
    from src.core.game import Game
    frigate = Game(seed=7, start_menu=False, audio_enabled=False, language="en")
    frigate.reset(7, "s2_doppeljagd")
    for _ in range(frigate_updates):
        frigate.update(0.1)
    boat = Game(seed=61, start_menu=False, audio_enabled=False, language="en")
    boat.reset(61, "s7_geleitzug")
    boat.local_side = "uboot"
    boat._update(0.05)
    for _ in range(boat_updates):
        boat.update(0.1)
    return {"frigate": frigate.save_state(), "uboot": boat.save_state()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=SAMPLES)
    parser.add_argument("--pack", type=Path, help="pack an existing save JSON (.json or .json.gz)")
    parser.add_argument("--name", default="frigate")
    args = parser.parse_args(argv)
    if args.pack is not None:
        import gzip
        opener = gzip.open if args.pack.suffix == ".gz" else open
        with opener(args.pack, "rb") as stream:
            print(pack(json.loads(stream.read()), args.name, args.out))
        return 0
    for name, document in play().items():
        print(pack(document, name, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
