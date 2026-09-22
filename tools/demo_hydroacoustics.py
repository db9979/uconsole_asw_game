"""Standalone synthetic hydroacoustics demonstration; never imported by runtime."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.audio.hydroacoustics import (  # noqa: E402
    AcousticSignature, HydroacousticChannel, analyze_demon, analyze_lofar,
)


def simulate(frame_count: int = 64) -> tuple[np.ndarray, np.ndarray, object, object]:
    """Return concatenated PCM, frame gains, LOFAR, and DEMON results."""
    sample_rate, frame_size = 32_768, 2048
    source = AcousticSignature(sample_rate=sample_rate, frame_size=frame_size,
                               rpm=120.0, blades=7, seed=1207)
    channel = HydroacousticChannel(sample_rate=sample_rate, distance_m=4_000.0,
                                   source_depth_m=20.0, receiver_depth_m=20.0,
                                   thermocline_depth_m=50.0)
    frames, gains = [], []
    for index in range(frame_count):
        fraction = index / max(1, frame_count - 1)
        distance = 4_000.0 + (500.0 - 4_000.0) * fraction
        source_depth = 20.0 + 60.0 * fraction
        raw = source.render_frame()
        received = channel.process_frame(raw, distance_m=distance,
                                         source_depth_m=source_depth)
        frames.append(received)
        gains.append(float(np.sqrt(np.mean(received.astype(np.float64) ** 2))))
    pcm = np.concatenate(frames)
    # One recording-wide analysis gain preserves all frame-to-frame attenuation.
    analysis_pcm = pcm / max(float(np.max(np.abs(pcm))), 1e-12)
    return (pcm, np.asarray(gains), analyze_lofar(analysis_pcm, sample_rate),
            analyze_demon(analysis_pcm, sample_rate))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the optional plot")
    parser.add_argument("--no-show", action="store_true", help="do not open a plot window")
    parser.add_argument("--smoke", action="store_true", help="run analysis without plotting")
    args = parser.parse_args(argv)
    pcm, gains, lofar, demon = simulate()
    if args.smoke:
        print(f"hydroacoustics smoke: {pcm.size} samples, "
              f"DEMON modulation={demon.modulation_peak_hz!r} Hz "
              f"(scenario expected 14 Hz)")
        return 0
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("plotting requires optional matplotlib; use --smoke for no-plot mode",
              file=sys.stderr)
        return 2
    figure, axes = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True)
    time = np.arange(pcm.size) / 32_768
    axes[0].plot(time, pcm, linewidth=.45)
    axes[0].set(title="Synthetic received waveform", xlabel="s", ylabel="amplitude")
    axes[0].plot(np.linspace(0, time[-1], gains.size), gains, linewidth=1.2)
    axes[1].imshow(20 * np.log10(lofar.magnitude.T + 1e-8), origin="lower",
                   aspect="auto", extent=(lofar.times_s[0], lofar.times_s[-1],
                                           lofar.frequencies_hz[0],
                                           lofar.frequencies_hz[-1]))
    axes[1].set(title="LOFAR waterfall", xlabel="s", ylabel="Hz")
    axes[2].plot(demon.frequencies_hz, demon.magnitude)
    axes[2].set(title="DEMON envelope spectrum", xlabel="Hz", ylabel="amplitude")
    if args.output:
        figure.savefig(args.output)
    if not args.no_show:
        plt.show()
    plt.close(figure)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
