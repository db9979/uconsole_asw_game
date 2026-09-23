/* Protocol v2 live audio. This processor receives only detached 4096 Hz PCM. */
class SonarAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.blocks = [];
    this.current = null;
    this.cursor = 0;
    this.last = null;
    this.previous = 0;
    this.lastSequence = null;
    this.gaps = 0;
    this.evictions = 0;
    this.repeats = 0;
    this.freshFrames = 0;
    this.outputFrames = 0;
    this.fade = 0;
    this.stale = false;
    this.primed = false;
    this.neutral = false;
    this.noise = 0x5a17;
    this.port.onmessage = ({data}) => {
      if (data?.type === "reset") {
        this.blocks = []; this.current = null; this.last = null;
        this.cursor = 0; this.lastSequence = null; this.primed = false;
        this.freshFrames = 0; this.stale = false; this.fade = 0; this.neutral = false;
        return;
      }
      if (data?.type !== "pcm" || !(data.bytes instanceof ArrayBuffer) ||
          data.bytes.byteLength !== 2048 || !Number.isSafeInteger(data.sequence) || data.sequence < 1) return;
      if (this.lastSequence !== null && data.sequence <= this.lastSequence) return;
      if (this.lastSequence !== null && data.sequence !== this.lastSequence + 1) this.gaps++;
      this.lastSequence = data.sequence;
      // Bound delay even if a browser tab resumes after a long suspension.
      if (this.blocks.length >= 8) { this.blocks.shift(); this.evictions++; }
      this.blocks.push(new Int16Array(data.bytes));
    };
  }

  nextBlock() {
    if (!this.primed && this.blocks.length < 4) return null;
    this.primed = true;
    if (this.blocks.length) {
      this.current = this.blocks.shift();
      this.neutral = false;
      this.last = this.current;
      this.freshFrames = 0;
      if (this.stale) { this.stale = false; this.port.postMessage({type: "stale", value: false}); }
    } else if (this.last && this.freshFrames < sampleRate * 2) {
      this.current = this.last;
      this.repeats++;
    } else {
      this.current = null;
      this.neutral = true;
      if (!this.stale) { this.stale = true; this.port.postMessage({type: "stale", value: true}); }
    }
    this.cursor = 0;
    this.fade = Math.max(1, Math.round(sampleRate * .01));
    return this.current;
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    for (let index = 0; index < output.length; index++) {
      if (this.current && this.cursor >= 1024 || !this.current &&
          (!this.primed && this.blocks.length >= 4 || this.neutral && this.blocks.length))
        this.nextBlock();
      let value;
      if (this.current) {
        const left = Math.min(1023, Math.floor(this.cursor));
        const right = Math.min(1023, left + 1);
        const fraction = this.cursor - left;
        value = (this.current[left] * (1 - fraction) + this.current[right] * fraction) / 32768;
        this.cursor += 4096 / sampleRate;
        this.freshFrames++;
      } else if (this.primed) {
        // Low level neutral noise remains audible after two seconds without data.
        this.noise = (Math.imul(this.noise, 1664525) + 1013904223) >>> 0;
        value = ((this.noise / 0xffffffff) * 2 - 1) * .006;
      } else value = 0;
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
      this.port.postMessage({type: "metrics", buffered: this.blocks.length + (this.current ? 1 - this.cursor / 1024 : 0),
        gaps: this.gaps, evictions: this.evictions,
        repeats: this.repeats, stale: this.stale});
    }
    return true;
  }
}
registerProcessor("sonar-audio-v2", SonarAudioProcessor);
