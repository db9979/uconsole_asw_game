"""Deterministic per-unit acoustic previews (reference clips, not recordings).

A preview drives a dedicated transient AcousticReceiver with the catalog
machine lines/broadband of one speed mode only: no own-ship layers, no
propagation path (flat spectral curve), full beam. The result is a bounded
float32 clip at the caller's output rate, identical across runs for the same
inputs.
"""

from __future__ import annotations

import hashlib
from typing import Mapping

import numpy as np

from src.audio.receiver import AcousticReceiver

PREVIEW_DURATION_S = 3.0
WARMUP_BLOCKS = 2
_FADE_IN_S = 0.12
_FADE_OUT_S = 0.15

_LINE_FIELDS = {"acoustic_cruise": "cruise_lines",
                "acoustic_high": "high_speed_lines"}
_BROADBAND_FIELDS = {"acoustic_cruise": "cruise_broadband",
                     "acoustic_high": "high_speed_broadband"}


def preview_seed(profile_key: str, salt: str = "") -> int:
    digest = hashlib.blake2b(digest_size=8)
    for part in ("u-jagd-unit-preview", str(profile_key), str(salt)):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return int.from_bytes(digest.digest(), "big")


def _field(machine, name: str):
    if isinstance(machine, Mapping):
        return machine.get(name)
    return getattr(machine, name, None)


def _lines_of(machine, field: str) -> list:
    raw = _field(machine, field)
    if not raw:
        return []
    lines = []
    for line in raw:
        if hasattr(line, "frequency_hz"):
            lines.append([line.frequency_hz, line.relative_level, line.width_hz])
        else:
            lines.append([float(line[0]), float(line[1]), float(line[2])])
    return lines


def _broadband_of(machine, field: str):
    raw = _field(machine, field)
    if raw is None:
        return None
    level, low, high = raw
    return [float(level), float(low), float(high)]


def preview_available(machine, mode: str) -> bool:
    """True when the speed mode carries tonal lines or a broadband interval."""
    return bool(_lines_of(machine, _LINE_FIELDS[mode])
                or _broadband_of(machine, _BROADBAND_FIELDS[mode]))


def unit_sonar_preview(profile_key: str, machine, mode: str, out_rate: int,
                       duration_s: float = PREVIEW_DURATION_S
                       ) -> np.ndarray | None:
    """Synthesize one bounded unit preview clip, or None when the mode is
    acoustically empty."""
    lines = _lines_of(machine, _LINE_FIELDS[mode])
    broadband = _broadband_of(machine, _BROADBAND_FIELDS[mode])
    if not lines and broadband is None:
        return None
    if not (isinstance(out_rate, int) and out_rate > 0):
        return None
    source = {
        "bearing": 0.0,
        "level": 1.0,
        "lines": lines,
        "seed": preview_seed(profile_key, mode) % (2**64),
    }
    if broadband is not None:
        source["broadband"] = {
            "level": broadband[0], "low_hz": broadband[1], "high_hz": broadband[2]}
    receiver = AcousticReceiver(seed=preview_seed(profile_key, mode + ":receiver"))
    blocks_per = max(1, int(round(duration_s / receiver.block_s)))
    blocks = []
    for _ in range(blocks_per + WARMUP_BLOCKS):
        receiver.update([source], bearing_deg=0.0, beam_width_deg=360.0,
                        own_noise=0.0, sea_state=0.0, own_speed=0.0,
                        own_cavitation=0.0)
        blocks.append(receiver.samples.copy())
    pcm_in = np.concatenate(blocks[WARMUP_BLOCKS:])
    rate_in = receiver.sample_rate
    target = int(round(pcm_in.size * out_rate / rate_in))
    positions = np.arange(target) * rate_in / out_rate
    pcm = np.interp(positions, np.arange(pcm_in.size), pcm_in).astype(np.float32)
    fade_in = min(int(_FADE_IN_S * out_rate), target // 3)
    fade_out = min(int(_FADE_OUT_S * out_rate), target // 3)
    if fade_in:
        pcm[:fade_in] *= np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out:
        pcm[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, dtype=np.float32)
    return pcm
