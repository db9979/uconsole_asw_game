"""Vektorisierte, kleine Audio-Synthese-Bausteine fuer Pygame."""

import math

import numpy as np


def tone(frequency_hz: float, duration_s: float, sample_rate: int,
         amplitude: float = 0.2, phase: float = 0.0) -> np.ndarray:
    """Erzeugt einen mono float32-Ton, sicher gegen Clipping."""
    count = max(1, int(duration_s * sample_rate))
    t = np.arange(count, dtype=np.float32) / sample_rate
    envelope = np.minimum(1.0, t * 40.0)
    envelope *= np.minimum(1.0, (duration_s - t) * 40.0)
    signal = np.sin(2.0 * math.pi * frequency_hz * t + phase)
    return np.clip(signal * amplitude * envelope, -1.0, 1.0).astype(np.float32)


def propeller_block(rpm: float, blade_count: int, sample_rate: int,
                     duration_s: float = 0.25, amplitude: float = 0.12,
                     cavitation: float = 0.0, phase: float = 0.0,
                     seed: int = 17,
                     rng: np.random.Generator | None = None,
                     filter_state: np.ndarray | None = None) -> np.ndarray:
    """Synthese aus Blattfrequenz, Obertoenen und gefilterter Kavitation.

    ``phase`` ist die Blattphasenlage am Blockanfang. Fuer lueckenlose Folgen
    wird sie je Block um ``2*pi*blade_hz*len(block)/sample_rate`` erhoeht.
    """
    count = max(1, int(duration_s * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    blade_hz = max(0.1, rpm / 60.0 * max(1, blade_count))
    blade_phase = 2.0 * math.pi * blade_hz * t + phase
    # Uneven harmonic strengths and slow loading variation sound less static
    # while every component remains phase-continuous at block boundaries.
    signal = np.sin(blade_phase)
    signal += 0.34 * np.sin(2.0 * blade_phase + 0.2)
    signal += 0.16 * np.sin(3.0 * blade_phase - 0.35)
    signal *= 0.92 + 0.08 * np.sin(blade_phase / max(1, blade_count) + 0.7)
    if cavitation > 0.0:
        taps = np.array([.08, .16, .24, .24, .16, .08])
        if rng is None:
            noise = np.random.default_rng(seed).normal(0.0, 1.0, count + 8)
            noise = np.convolve(noise, taps, mode="valid")[:count]
        else:
            raw = rng.normal(0.0, 1.0, count)
            history = np.zeros(taps.size - 1) if filter_state is None \
                else np.asarray(filter_state, dtype=np.float64)
            if history.shape != (taps.size - 1,):
                raise ValueError("filter_state has an incompatible shape")
            noise = np.convolve(np.concatenate((history, raw)), taps,
                                mode="valid")
            if filter_state is not None:
                filter_state[:] = raw[-history.size:]
        # A short FIR removes the brittle white-noise edge while retaining
        # the impulsive broadband character of cavitation.
        bursts = np.maximum(0.0, np.sin(blade_phase - 0.8)) ** 3
        signal += min(0.7, cavitation) * noise * (0.35 + 0.65 * bursts)
    # A fixed gain, rather than per-block normalization, preserves amplitude
    # and waveform continuity when adjacent blocks have different extrema.
    return np.clip(signal * amplitude / 1.75, -1.0, 1.0).astype(np.float32)


def fm_chirp(start_hz: float, end_hz: float, duration_s: float,
             sample_rate: int, amplitude: float = 0.2,
             modulation_hz: float = 0.0, modulation_depth_hz: float = 0.0,
             phase: float = 0.0) -> np.ndarray:
    """Erzeugt einen linearen Chirp mit optionaler sinusfoermiger FM."""
    count = max(1, int(duration_s * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    duration = max(count / sample_rate, float(duration_s))
    chirp_phase = 2 * np.pi * (start_hz * t + .5 * (end_hz - start_hz)
                               * t**2 / duration)
    if modulation_hz and modulation_depth_hz:
        chirp_phase += (modulation_depth_hz / modulation_hz) * (
            1 - np.cos(2 * np.pi * modulation_hz * t))
    edge = min(count // 2, max(1, round(.01 * sample_rate)))
    envelope = np.ones(count)
    envelope[:edge] = np.linspace(0, 1, edge)
    envelope[-edge:] *= np.linspace(1, 0, edge)
    signal = amplitude * envelope * np.sin(chirp_phase + phase)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


def filtered_noise_event(duration_s: float, sample_rate: int,
                         low_hz: float, high_hz: float,
                         amplitude: float = 0.2, seed: int = 0) -> np.ndarray:
    """Erzeugt ein deterministisches, weich ein-/ausgeblendetes Bandereignis."""
    count = max(1, int(duration_s * sample_rate))
    noise = np.random.default_rng(seed).normal(0, 1, count)
    frequencies = np.fft.rfftfreq(count, 1 / sample_rate)
    low = max(0.0, min(float(low_hz), sample_rate / 2))
    high = max(low, min(float(high_hz), sample_rate / 2))
    width = max(1.0, min(50.0, (high - low) * .2))
    mask = np.clip((frequencies - (low - width)) / width, 0, 1)
    mask *= np.clip(((high + width) - frequencies) / width, 0, 1)
    signal = np.fft.irfft(np.fft.rfft(noise) * mask, n=count)
    rms = float(np.sqrt(np.mean(signal**2)))
    if rms > 1e-12:
        signal *= amplitude / rms
    edge = min(count // 2, max(1, round(.02 * sample_rate)))
    envelope = np.ones(count)
    envelope[:edge] = np.linspace(0, 1, edge)
    envelope[-edge:] *= np.linspace(1, 0, edge)
    return np.clip(np.nan_to_num(signal * envelope), -1, 1).astype(np.float32)


def stereo_bearing(samples: np.ndarray, bearing_deg: float,
                   listener_bearing_deg: float = 0.0) -> np.ndarray:
    """Pannt ein Monosignal nach relativer Peilung mit konstanter Leistung."""
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim != 1:
        raise ValueError("samples must be mono")
    relative = math.radians((float(bearing_deg) - float(listener_bearing_deg)) % 360)
    pan = math.sin(relative)
    angle = (pan + 1.0) * math.pi / 4.0
    return np.column_stack((mono * math.cos(angle), mono * math.sin(angle))).astype(
        np.float32)
