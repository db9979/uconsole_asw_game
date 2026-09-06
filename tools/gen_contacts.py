"""Erzeugt data/contacts/*.json aus dem eingebauten Katalog.

Ausführung:  python tools/gen_contacts.py [--out DIR] [--check]

--check: schreibt nichts, vergleicht die JSON-Dateien mit dem eingebauten
Katalog und meldet Abweichungen (z.B. nach Hand-Edits).
Schema: docs/contacts-db.md
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.catalog import build_catalog, load_catalog, CIVIL_CATEGORIES  # noqa: E402
from src.data import fingerprint as fp  # noqa: E402


def _sig_dict(s):
    return {
        "label": s.label,
        "propulsion": s.propulsion,
        "blades": list(s.blade_counts),
        "rpm_range": list(s.rpm_range),
        "tonal_band_hz": list(s.tonal_band_hz),
        "cavitation_tendency": s.cavitation_tendency,
        "category": s.category,
        "secondary_tonals": [list(t) for t in s.secondary_tonals],
        "broadband": list(s.broadband) if s.broadband else None,
        "signature_text": s.signature_text,
    }


def _write(path, version, entries):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": version, "entries": entries}, f,
                  ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  {path} ({len(entries)} Eintraege)")


def generate(out_dir: str) -> None:
    cat = build_catalog()
    os.makedirs(out_dir, exist_ok=True)

    subs = []
    for p in cat.subs.values():
        subs.append({
            "key": p.key, "name": p.name,
            "speed_kn": list(p.speed_kn),
            "max_depth_m": p.max_depth_m, "torpedoes": p.torpedoes,
            "quiet": p.quiet, "aggression": p.aggression,
            "spawn_weight": p.spawn_weight,
            "acoustic": _sig_dict(p.acoustic),
        })
    _write(os.path.join(out_dir, "subs.json"), 1, subs)

    warships = []
    for p in cat.hostile_surfaces:
        warships.append(_surface_dict(p))
    _write(os.path.join(out_dir, "warships.json"), 1, warships)

    civilians = []
    for p in cat.civilian_surfaces:
        civilians.append(_surface_dict(p))
    _write(os.path.join(out_dir, "civilians.json"), 1, civilians)

    aircraft = [{
        "key": a.key, "name": a.name, "nation": a.nation, "kind": a.kind,
        "speed_kn": a.speed_kn, "esm": a.esm,
        "esm_range_nm": a.esm_range_nm,
        "loiter_nm": list(a.loiter_nm),
        "spawn_weight": a.spawn_weight,
        "signature_text": a.signature_text,
    } for a in cat.aircraft.values()]
    _write(os.path.join(out_dir, "aircraft.json"), 1, aircraft)

    animals = [{
        "key": a.key, "name": a.name,
        "depth_min": a.depth_min, "depth_max": a.depth_max,
        "speed_kn": a.speed_kn, "quiet": a.quiet, "size_nm": a.size_nm,
        "spawn_weight": a.spawn_weight,
        "lines": [list(t) for t in a.lines],
        "signature_text": a.signature_text,
    } for a in cat.animals.values()]
    _write(os.path.join(out_dir, "animals.json"), 1, animals)

    torpedoes = []
    for t in cat.torpedoes.values():
        d = {"key": t.key, "name": t.name, "used_by": t.used_by,
             "speed_kn": t.speed_kn, "range_nm": t.range_nm,
             "hit_dist_nm": t.hit_dist_nm}
        if t.acoustic is not None:
            d["acoustic"] = _sig_dict(t.acoustic)
        torpedoes.append(d)
    _write(os.path.join(out_dir, "torpedoes.json"), 1, torpedoes)

    decoys = [{
        "key": d.key, "name": d.name, "life_s": d.life_s,
        "speed_kn": d.speed_kn, "cooldown_s": d.cooldown_s,
        "chance": d.chance,
        "lines": [list(t) for t in d.lines],
        "signature_text": d.signature_text,
    } for d in cat.decoys.values()]
    _write(os.path.join(out_dir, "decoys.json"), 1, decoys)

    n = len(cat.acoustic_profiles)
    print(f"fertig: {n} Akustik-Profile "
          f"({sum(1 for s in cat.acoustic_profiles if s.category != 'BIOLOGISCH')}"
          f" Plattformen)")


def _surface_dict(p):
    return {
        "key": p.key, "name": p.name, "category": p.category,
        "hostile": p.hostile,
        "speed_kn": list(p.speed_kn),
        "callsigns": list(p.callsigns),
        "esm_prob": p.esm_prob,
        "asm_salvo": list(p.asm_salvo),
        "asm_cooldown_s": p.asm_cooldown_s,
        "loiter_nm": p.loiter_nm,
        "spawn_weight": p.spawn_weight,
        "acoustic": _sig_dict(p.acoustic),
    }


def check(base_dir: str) -> int:
    """Vergleicht JSON-DB mit eingebautem Katalog; 0 = identisch."""
    diff = 0
    cat_json = load_catalog(base_dir, quiet=True)
    cat_builtin = build_catalog()
    for field in ("subs", "surfaces", "aircraft", "animals", "torpedoes",
                  "decoys"):
        a = getattr(cat_json, field)
        b = getattr(cat_builtin, field)
        for key in sorted(set(a) | set(b)):
            if key not in a:
                print(f"  fehlt in DB: {field}/{key}")
                diff += 1
            elif key not in b:
                print(f"  nur in DB: {field}/{key}")
                diff += 1
            elif a[key] != b[key]:
                print(f"  Abweichung: {field}/{key}")
                diff += 1
    if diff == 0:
        print("DB und eingebauter Katalog sind identisch.")
    return 1 if diff else 0


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "contacts")
    if "--check" in sys.argv:
        sys.exit(check(out_dir))
    if "--out" in sys.argv:
        out_dir = sys.argv[sys.argv.index("--out") + 1]
    print(f"erzeuge Kontakt-DB unter {out_dir} ...")
    generate(out_dir)
    print("Tipp: nach Hand-Edits mit `python tools/gen_contacts.py --check` "
          "vergleichen.")


if __name__ == "__main__":
    main()
