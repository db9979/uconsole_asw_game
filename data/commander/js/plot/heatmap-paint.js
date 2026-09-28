// The waterfall painter shared by the main thread and the raster worker. It
// reads only the packed job (typed arrays and numbers), so a worker can run it
// on a transferred copy without the page's state.
export function paintHeatmap(pixels, job) {
  const {width, rasterHeight, headroom, pixelsPerSecond, historyS, xmax, count,
    black, contrast, colors, anchor, cellHeight, stamps, offsets, bins, frequencies} = job;
  pixels.fill(colors[0]);
  for (let row = 0; row < stamps.length; row++) {
    const age = anchor - stamps[row];
    const y0 = Math.floor(headroom + age * pixelsPerSecond);
    if (y0 < 0 || y0 >= rasterHeight) continue;
    const y1 = Math.min(rasterHeight, y0 + cellHeight);
    const persistence = Math.exp(-age / Math.max(8, historyS * .8));
    const first = offsets[row], length = offsets[row + 1] - first;
    for (let x = 0; x < length; x++) {
      const raw = Math.max(0, Math.min(1, bins[first + x]));
      const level = Math.max(0, Math.min(1, (raw - black) / Math.max(.01, 1 - black) * contrast * persistence));
      const start = frequencies ? frequencies[x] / xmax : x / count;
      const end = frequencies ? (frequencies[x + 1] ?? xmax) / xmax : (x + 1) / count;
      const x0 = Math.min(width - 1, Math.max(0, Math.floor(start * width)));
      const x1 = Math.min(width, Math.max(x0 + 1, Math.floor(end * width)));
      const color = colors[Math.round(level * 255)];
      for (let y = y0; y < y1; y++) pixels.fill(color, y * width + x0, y * width + x1);
    }
  }
}
