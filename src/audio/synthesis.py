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


def active_sonar_ping(frequency_hz: float, sample_rate: int,
                      amplitude: float = 0.32) -> np.ndarray:
    """Short naval sonar pulse with a metallic onset and decaying reverb."""
    duration_s = .62
    count = max(1, int(duration_s * sample_rate))
    signal = np.zeros(count, dtype=np.float64)
    pulse = fm_chirp(frequency_hz * .76, frequency_hz * 1.08, .22,
                     sample_rate, amplitude, modulation_hz=8.0,
                     modulation_depth_hz=14.0).astype(np.float64)
    signal[:pulse.size] += pulse
    # Quiet, progressively darker replicas suggest hull/water reverberation
    # without pretending to encode a gameplay range or a real returned echo.
    for delay_s, gain in ((.075, .28), (.145, .15), (.245, .07)):
        delay = round(delay_s * sample_rate)
        end = min(count, delay + pulse.size)
        if end > delay:
            signal[delay:end] += pulse[:end - delay] * gain
    t = np.arange(count, dtype=np.float64) / sample_rate
    ring = np.sin(2 * np.pi * frequency_hz * .48 * t + .6)
    ring *= np.exp(-8.0 * t) * min(amplitude, .2) * .2
    signal += ring
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


ECHO_PULSES = ("CW", "LFM")


def sonar_echo(frequency_hz: float, pulse: str, level: float,
               sample_rate: int, amplitude: float = 0.30) -> np.ndarray:
    """Returned active-sonar echo as heard on the operator's speaker.

    ``level`` (0..1) is the measured echo strength. A CW return is a soft,
    slightly smeared tone on the carrier; an LFM return is a short sweep
    across the 100 Hz band. Weak returns sit in band-limited reverberation
    noise, so a faint echo is heard as a tone emerging from the hiss.
    """
    pulse = pulse if pulse in ECHO_PULSES else "CW"
    level = float(np.clip(level, 0.0, 1.0))
    duration_s = .55 if pulse == "CW" else .32
    count = max(1, int(duration_s * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    if pulse == "CW":
        # Target motion and multipath spread the return a little in pitch.
        phase = 2 * np.pi * (frequency_hz * t + 1.5 * np.sin(2 * np.pi * 3.0 * t) / (2 * np.pi * 3.0))
        body = np.sin(phase) + .35 * np.sin(1.003 * phase + .7)
        attack, release = .05, .22
    else:
        sweep = 100.0 / duration_s
        body = np.sin(2 * np.pi * ((frequency_hz - 50.0) * t + .5 * sweep * t * t))
        attack, release = .015, .08
    envelope = np.ones(count)
    rise = max(1, round(attack * sample_rate))
    fall = max(1, round(release * sample_rate))
    envelope[:rise] = np.linspace(0.0, 1.0, rise)
    envelope[-fall:] *= np.exp(-np.linspace(0.0, 4.0, fall))
    body = body / np.max(np.abs(body)) * envelope
    noise = filtered_noise_event(duration_s, sample_rate, frequency_hz * .55,
                                 frequency_hz * 1.6, 1.0,
                                 seed=int(frequency_hz) * 7 + len(pulse))[:count]
    signal = amplitude * ((.25 + .75 * level) * body + (.45 - .3 * level) * noise)
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


def telegraph_bell(sample_rate: int, amplitude: float = .28) -> np.ndarray:
    """The engine telegraph's double ring as the handle drops into its new
    order: two strokes of a small bell (inharmonic partials, long decay)."""
    duration = 1.2
    count = max(1, int(duration * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    signal = np.zeros(count)
    for onset_s, gain in ((0.0, 1.0), (.22, .8)):
        local = t - onset_s
        ring = np.where(local >= 0.0, np.exp(-4.5 * np.maximum(local, 0.0)), 0.0)
        for partial, weight in ((1.0, 1.0), (2.76, .45), (5.40, .2)):
            signal += gain * weight * ring * np.sin(2 * np.pi * 1180.0 * partial * np.maximum(local, 0.0))
    signal *= amplitude * .45
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


def thunder_roll(sample_rate: int, amplitude: float = .28) -> np.ndarray:
    """A thunderclap far off: a short crack, then a low rumble rolling in
    slow swells (band-limited noise, deterministic)."""
    duration = 2.8
    count = max(1, int(duration * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    rumble = filtered_noise_event(duration, sample_rate, 22.0, 320.0, amplitude, 503)[:count]
    crack = filtered_noise_event(duration, sample_rate, 400.0, 2600.0, amplitude, 509)[:count]
    swell = (.55 + .45 * np.sin(2 * np.pi * 1.3 * t) * np.sin(2 * np.pi * .55 * t + .8)) \
        * np.minimum(1.0, t * 6.0) * np.exp(-1.1 * t)
    signal = 2.2 * rumble * swell + .9 * crack * np.exp(-14.0 * t)
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


def combat_effect(kind: str, sample_rate: int,
                  amplitude: float = .28) -> np.ndarray:
    """Deterministic layered one-shot effects for local shipboard events."""
    if kind == "telegraph":
        return telegraph_bell(sample_rate, amplitude)
    if kind == "thunder":
        return thunder_roll(sample_rate, amplitude)
    profiles = {
        "torpedo_launch": (.72, 35.0, 900.0, 181, 72.0, 23.0),
        "missile_launch": (.95, 90.0, 5200.0, 223, 180.0, 820.0),
        "gunfire": (.62, 70.0, 4300.0, 277, 105.0, 47.0),
        "explosion": (1.20, 25.0, 1600.0, 331, 54.0, 19.0),
        "water_entry": (.58, 120.0, 3400.0, 389, 240.0, 82.0),
    }
    duration, low, high, seed, body_hz, tail_hz = profiles.get(
        kind, profiles["explosion"])
    count = max(1, int(duration * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    noise = filtered_noise_event(duration, sample_rate, low, high,
                                 amplitude, seed).astype(np.float64)
    if kind == "gunfire":
        envelope = np.zeros(count)
        burst_len = max(1, round(.055 * sample_rate))
        for onset_s, gain in ((0.0, 1.0), (.115, .85), (.23, .72), (.345, .58)):
            onset = round(onset_s * sample_rate)
            end = min(count, onset + burst_len)
            if end > onset:
                local_t = np.arange(end - onset) / sample_rate
                envelope[onset:end] += gain * np.exp(-42.0 * local_t)
        signal = noise * envelope * 2.5
        signal += amplitude * .45 * np.sin(2 * np.pi * body_hz * t) * envelope
    else:
        attack = np.minimum(1.0, t * (90.0 if kind != "water_entry" else 28.0))
        decay = np.exp(-(3.2 if kind == "explosion" else 5.0) * t)
        envelope = attack * decay
        signal = noise * envelope
        signal += amplitude * .65 * np.sin(2 * np.pi * body_hz * t) * envelope
        signal += amplitude * .25 * np.sin(2 * np.pi * tail_hz * t + .4) \
            * np.exp(-7.0 * t)
        if kind == "missile_launch":
            sweep = 420.0 + 1250.0 * t / max(duration, 1e-6)
            signal += amplitude * .22 * np.sin(2 * np.pi * sweep * t) * envelope
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


def boat_effect(kind: str, sample_rate: int, amplitude: float = .28) -> np.ndarray:
    """Deterministic atmosphere cues heard inside the crewed boat: the hull
    creaking deep down, a hull failure's crack, near/distant detonations and
    a hunter's ping on the hull."""
    if kind == "thunder":
        return thunder_roll(sample_rate, amplitude * .6)
    if kind == "hull_creak":
        duration = 1.8
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        noise = filtered_noise_event(duration, sample_rate, 60.0, 420.0,
                                     amplitude, 433).astype(np.float64)
        # A slow groan: a low tone sagging in pitch under a rasping band.
        phase = 2 * np.pi * (88.0 * t - 9.0 * t * t)
        rasp = 1.0 + .6 * np.sin(2 * np.pi * 11.0 * t)
        envelope = np.sin(np.pi * np.minimum(1.0, t / duration)) ** 1.5
        signal = envelope * (.55 * noise * rasp + amplitude * .5 * np.sin(phase))
    elif kind == "hull_crack":
        duration = .9
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        noise = filtered_noise_event(duration, sample_rate, 300.0, 5200.0,
                                     amplitude, 457).astype(np.float64)
        signal = noise * 2.2 * np.exp(-30.0 * t)
        signal += amplitude * .8 * np.sin(2 * np.pi * 46.0 * t) * np.exp(-6.0 * t)
    elif kind == "torpedo_seeker":
        # A homing torpedo's seeker pulse: short and high, a little ringing.
        duration = .22
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        envelope = np.where(t < .06, 1.0, np.exp(-28.0 * (t - .06)))
        signal = amplitude * .7 * envelope * np.sin(2 * np.pi * 2600.0 * t)
    elif kind in ("crew_clank", "crew_transient"):
        # Metal on metal: a dropped tool or a slammed hatch, inharmonic and
        # short; heard from the enemy it is farther, duller and quieter.
        far = kind == "crew_transient"
        duration = .5 if far else .35
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        decay = 9.0 if far else 16.0
        partials = ((310.0, 1.0), (847.0, .55), (1523.0, .3)) if far else (
            (523.0, 1.0), (1377.0, .6), (2213.0, .4), (3170.0, .25))
        signal = sum(weight * np.sin(2 * np.pi * freq * t) for freq, weight in partials)
        signal = amplitude * (.35 if far else .6) * signal / 2.0 * np.exp(-decay * t)
        click = np.exp(-400.0 * t) * (1.0 - 2.0 * ((np.arange(count) * 7919) % 97) / 96.0)
        signal += amplitude * (.1 if far else .3) * click
    elif kind == "dive_alarm":
        # The crash-dive alarm: a rattling klaxon, three bursts.
        duration = 2.1
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        tone = np.sign(np.sin(2 * np.pi * 410.0 * t)) * .6 + .4 * np.sin(2 * np.pi * 820.0 * t)
        rattle = .55 + .45 * np.sign(np.sin(2 * np.pi * 28.0 * t))
        bursts = (np.mod(t, .7) < .55).astype(np.float64)
        signal = amplitude * .45 * tone * rattle * bursts
    elif kind == "ping_heard":
        # A hunter's ping through the hull: a hard tone and its ringing tail.
        duration = 1.2
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        envelope = np.where(t < .35, 1.0, np.exp(-7.0 * (t - .35)))
        signal = amplitude * .8 * envelope * np.sin(2 * np.pi * 1300.0 * t)
    else:
        near = kind == "detonation_near"
        duration = 1.6 if near else 2.4
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        noise = filtered_noise_event(duration, sample_rate, 20.0,
                                     1400.0 if near else 260.0,
                                     amplitude * (1.0 if near else .55),
                                     461 if near else 463).astype(np.float64)
        envelope = np.minimum(1.0, t * (120.0 if near else 18.0)) \
            * np.exp(-(2.6 if near else 1.6) * t)
        signal = noise * envelope
        signal += amplitude * (.7 if near else .35) * np.sin(2 * np.pi * 38.0 * t) * envelope
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


ATMOSPHERE_KINDS = ("general_alarm", "alarm_bell", "fans_down", "fans_up")


def atmosphere_effect(kind: str, sample_rate: int, amplitude: float = .28) -> np.ndarray:
    """Deterministic shipboard atmosphere: the frigate's general alarm (an
    electric bell ringing through the ship), the boat's quiet alarm bell and its ventilation fans running down or up
    for silent running."""
    if kind in ("general_alarm", "alarm_bell"):
        # An electric bell: fast hammer strokes on an inharmonic gong.
        duration = 2.6 if kind == "general_alarm" else 1.2
        rate = 16.0 if kind == "general_alarm" else 20.0
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        stroke = np.exp(-18.0 * ((t * rate) % 1.0) / rate)
        base = 1180.0 if kind == "general_alarm" else 1650.0
        body = sum(weight * np.sin(2 * np.pi * base * ratio * t)
                   for ratio, weight in ((1.0, 1.0), (2.76, .5), (5.4, .25)))
        envelope = np.minimum(1.0, t * 40.0) * np.minimum(1.0, (duration - t) * 8.0)
        gain = amplitude * (.55 if kind == "general_alarm" else .3)
        signal = gain * stroke * envelope * body / 1.75
    else:
        # Fans: a hum with blade tone whose speed runs down (or up).
        duration = 2.4
        count = int(duration * sample_rate)
        t = np.arange(count, dtype=np.float64) / sample_rate
        fraction = t / duration
        speed = 1.0 - fraction if kind == "fans_down" else fraction
        speed = speed * speed * (3.0 - 2.0 * speed)
        phase = 2 * np.pi * np.cumsum(40.0 + 180.0 * speed) / sample_rate
        noise = filtered_noise_event(duration, sample_rate, 180.0, 1400.0,
                                     amplitude, 499).astype(np.float64)
        signal = (.35 + .65 * speed) * speed * (amplitude * .5 * np.sin(phase) + .4 * noise)
    edge = min(count // 2, max(1, round(.006 * sample_rate)))
    signal[:edge] *= np.linspace(0.0, 1.0, edge)
    signal[-edge:] *= np.linspace(1.0, 0.0, edge)
    return np.clip(np.nan_to_num(signal), -1, 1).astype(np.float32)


PAN_STEPS = 8


def bearing_pan(bearing_deg: float, heading_deg: float) -> float:
    """Left/right position of a sound heard on ``bearing_deg`` by a listener
    facing ``heading_deg``: -1 port, 0 ahead or astern, +1 starboard, in
    steps of ``1 / PAN_STEPS`` so the cached one-shot sounds stay few."""
    relative = math.radians((float(bearing_deg) - float(heading_deg)) % 360.0)
    return round(math.sin(relative) * PAN_STEPS) / PAN_STEPS + 0.0


def stereo_pan(samples: np.ndarray, pan: float) -> np.ndarray:
    """Place a mono signal at ``pan`` (-1..+1) with constant power."""
    mono = np.asarray(samples, dtype=np.float32)
    if mono.ndim != 1:
        raise ValueError("samples must be mono")
    angle = (min(1.0, max(-1.0, float(pan))) + 1.0) * math.pi / 4.0
    return np.column_stack((mono * math.cos(angle), mono * math.sin(angle))).astype(
        np.float32)


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
