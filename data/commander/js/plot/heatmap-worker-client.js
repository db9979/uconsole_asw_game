// Waterfall rasters are painted in a worker when the browser offers
// OffscreenCanvas there; otherwise (or after any worker failure) heatmap.js
// keeps painting on the main thread. <html data-heatmap-worker> reports which.
//
// Headless Chromium's virtual time never advances while a worker exists, so
// the page's many --virtual-time-budget probes would hang; headless pages paint
// on the main thread unless a probe sets globalThis.uJagdHeatmapWorker = true.
let client;

function mark(state) {
  document.documentElement.dataset.heatmapWorker = state;
}

export function heatmapWorker() {
  if (client !== undefined) return client;
  client = null;
  if (typeof Worker !== "function" || typeof OffscreenCanvas !== "function") {
    mark("off");
    return null;
  }
  if (globalThis.uJagdHeatmapWorker !== true && /HeadlessChrome/.test(navigator.userAgent)) {
    mark("headless");
    return null;
  }
  try {
    client = workerClient(new Worker(new URL("./heatmap-worker.js", import.meta.url), {type: "module"}));
    mark("on");
  } catch {
    client = null;
    mark("off");
  }
  return client;
}

function workerClient(worker) {
  // One job in flight per plot; a newer job while it runs replaces the
  // waiting one, so a slow worker drops stale rasters instead of queueing.
  const plots = new Map();
  let sequence = 0;
  const send = (id, job, done) => {
    const seq = ++sequence;
    plots.set(id, {seq, done, waiting: null});
    worker.postMessage({id, seq, job}, [job.stamps.buffer, job.offsets.buffer, job.bins.buffer]);
  };
  worker.onmessage = ({data}) => {
    const plot = plots.get(data.id);
    if (!plot || plot.seq !== data.seq) { data.bitmap?.close?.(); return; }
    plot.done(data.bitmap, data.anchor);
    if (plot.waiting) send(data.id, plot.waiting.job, plot.waiting.done);
    else plots.delete(data.id);
  };
  const fail = () => {
    worker.terminate();
    plots.clear();
    client = null;
    mark("off");
  };
  worker.onerror = fail;
  worker.onmessageerror = fail;
  return {
    render(id, job, done) {
      const plot = plots.get(id);
      if (plot) plot.waiting = {job, done};
      else send(id, job, done);
    },
  };
}
