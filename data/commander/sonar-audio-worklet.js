/* Protocol v2 live audio. This processor receives only detached 4096 Hz PCM.
 *
 * Elastic playback: the queue is steered towards TARGET_S by reading the
 * 4096 Hz stream at most RATE_MAX faster or slower, so host/browser clock
 * drift and network jitter never drain or overflow it. An underrun plays a
 * non-periodic granular stand-in built from the last half second and refills
 * to REFILL_BLOCKS before fresh audio resumes; after STALE_S without data a
 * low neutral noise marks the stream stale. Crossfades are applied only at
 * real discontinuities, never at ordinary block joins.
 *
 * The two-second lead (PRIME_BLOCKS, TARGET_S) outlasts a Wi-Fi power-save
 * hiccup, a browser main-thread stall and the host's bounded catch-up after
 * a slow frame; MAX_BLOCKS bounds the delay when a tab resumes. */
const BLOCK = 1024;
const SOURCE_RATE = 4096;
const PRIME_BLOCKS = 8;
const MAX_BLOCKS = 24;
const REFILL_BLOCKS = 4;
const TARGET_S = 2.0;
const RATE_MAX = .02;
const RATE_STEP = .0025;
const RATE_GAIN = .05;
const LEVEL_SMOOTHING = .05;
const STALE_S = 3;
const GRAIN = 512;

class SonarAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.window = new Float32Array(GRAIN);
    for (let i = 0; i < GRAIN; i++) this.window[i] = Math.sin(Math.PI * (i + .5) / GRAIN);
    this.gaps = 0;
    this.evictions = 0;
    this.dropped = 0;
    this.concealed = 0;
    this.outputFrames = 0;
    this.noise = 0x5a17;
    this.grainSeed = 0x2f6b;
    this.resetStream();
    this.port.onmessage = ({data}) => {
      if (data?.type === "reset") { this.resetStream(); return; }
      if (data?.type !== "pcm" || !(data.bytes instanceof ArrayBuffer) ||
          data.bytes.byteLength !== 2048 || !Number.isSafeInteger(data.sequence) || data.sequence < 1) return;
      // Sequences never go backwards within a host run: an old or repeated
      // number is a duplicate (a reconnect re-sent it) and is counted, not played.
      if (this.lastSequence !== null && data.sequence <= this.lastSequence) { this.dropped++; return; }
      const gap = this.lastSequence !== null && data.sequence !== this.lastSequence + 1;
      if (gap) this.gaps++;
      this.lastSequence = data.sequence;
      const pcm = new Int16Array(data.bytes);
      const samples = new Float32Array(BLOCK);
      for (let i = 0; i < BLOCK; i++) samples[i] = pcm[i] / 32768;
      // Bound delay even if a browser tab resumes after a long suspension.
      if (this.blocks.length >= MAX_BLOCKS) {
        this.blocks.shift();
        this.evictions++;
        if (this.blocks.length) this.blocks[0].join = true;
      }
      this.blocks.push({samples, join: gap});
    };
  }

  resetStream() {
    this.blocks = [];
    this.current = null;
    this.cursor = 0;
    this.tail = 0;
    this.history = [];
    this.lastSequence = null;
    this.primed = false;
    this.refilling = false;
    this.concealing = false;
    this.neutral = false;
    this.stale = false;
    this.sinceFresh = 0;
    this.fade = 0;
    this.previous = 0;
    this.rate = 1;
    this.levelEma = null;
  }

  steer() {
    // Queue level at a block switch, in seconds of not yet started audio.
    const level = this.blocks.length * BLOCK / SOURCE_RATE;
    this.levelEma = this.levelEma === null ? level : this.levelEma + LEVEL_SMOOTHING * (level - this.levelEma);
    let adjust = Math.max(-RATE_MAX, Math.min(RATE_MAX, RATE_GAIN * (this.levelEma - TARGET_S)));
    adjust = Math.round(adjust / RATE_STEP) * RATE_STEP;
    const previous = this.rate - 1;
    adjust = Math.max(previous - RATE_STEP, Math.min(previous + RATE_STEP, adjust));
    this.rate = 1 + adjust;
  }

  conceal() {
    let source = this.history[0];
    if (this.history.length === 2) {
      source = new Float32Array(2 * BLOCK);
      source.set(this.history[0]);
      source.set(this.history[1], BLOCK);
    }
    const output = new Float32Array(BLOCK + 2 * GRAIN);
    for (let start = 0; start <= BLOCK + GRAIN; start += GRAIN / 2) {
      this.grainSeed = (Math.imul(this.grainSeed, 1664525) + 1013904223) >>> 0;
      const offset = this.grainSeed % (source.length - GRAIN + 1);
      for (let i = 0; i < GRAIN; i++) output[start + i] += source[offset + i] * this.window[i];
    }
    return output.subarray(GRAIN, GRAIN + BLOCK);
  }

  startCrossfade() {
    this.fade = Math.max(1, Math.round(sampleRate * .01));
  }

  nextBlock() {
    if (!this.primed) {
      if (this.blocks.length < PRIME_BLOCKS) return;
      this.primed = true;
    }
    if (this.refilling && this.blocks.length >= REFILL_BLOCKS) this.refilling = false;
    const wasSubstitute = this.concealing || this.neutral || !this.current;
    if (this.blocks.length && !this.refilling) {
      const block = this.blocks.shift();
      if (block.join || wasSubstitute) this.startCrossfade();
      this.current = block.samples;
      this.history.push(block.samples);
      if (this.history.length > 2) this.history.shift();
      this.concealing = false;
      this.neutral = false;
      this.sinceFresh = 0;
      if (this.stale) { this.stale = false; this.port.postMessage({type: "stale", value: false}); }
      this.steer();
    } else if (this.history.length && this.sinceFresh < sampleRate * STALE_S) {
      if (!this.concealing) this.startCrossfade();
      this.current = this.conceal();
      this.concealing = true;
      this.refilling = true;
      this.neutral = false;
      this.concealed++;
      this.rate = 1;
      this.levelEma = null;
    } else {
      if (!this.neutral) this.startCrossfade();
      this.current = null;
      this.history = [];
      this.concealing = false;
      this.neutral = true;
      this.refilling = true;
      if (!this.stale) { this.stale = true; this.port.postMessage({type: "stale", value: true}); }
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    const step = SOURCE_RATE / sampleRate;
    for (let index = 0; index < output.length; index++) {
      if (this.current ? this.cursor >= BLOCK
          : this.primed ? this.neutral && this.blocks.length >= REFILL_BLOCKS
          : this.blocks.length >= PRIME_BLOCKS) {
        if (this.current) {
          this.tail = this.current[BLOCK - 1];
          this.cursor -= BLOCK;
        } else this.cursor = 0;
        this.nextBlock();
      }
      let value;
      if (this.current) {
        // One-sample delayed linear interpolation: continuous across blocks.
        const left = Math.floor(this.cursor);
        const fraction = this.cursor - left;
        const a = left === 0 ? this.tail : this.current[left - 1];
        value = a + (this.current[left] - a) * fraction;
        this.cursor += step * this.rate;
      } else if (this.primed) {
        // Low level neutral noise remains audible after two seconds without data.
        this.noise = (Math.imul(this.noise, 1664525) + 1013904223) >>> 0;
        value = ((this.noise / 0xffffffff) * 2 - 1) * .006;
      } else value = 0;
      if (this.primed) this.sinceFresh++;
      if (this.fade > 0) {
        const fraction = 1 - this.fade / Math.max(1, Math.round(sampleRate * .01));
        value = this.previous * (1 - fraction) + value * fraction;
        this.fade--;
      }
      output[index] = value;
      this.previous = value;
    }
    this.outputFrames += output.length;
    if (this.outputFrames >= sampleRate) {
      this.outputFrames -= sampleRate;
      this.port.postMessage({type: "metrics", buffered: this.blocks.length + (this.current ? 1 - this.cursor / BLOCK : 0),
        gaps: this.gaps, evictions: this.evictions, dropped: this.dropped, concealed: this.concealed,
        rate: this.rate, stale: this.stale});
    }
    return true;
  }
}
registerProcessor("sonar-audio-v2", SonarAudioProcessor);
