// Audio-thread capture: emit exactly 20 ms of mono PCM only while PTT is down.
class RadioCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.enabled = false;
    this.samples = new Int16Array(960);
    this.offset = 0;
    this.port.onmessage = ({data}) => {
      this.enabled = data === "down";
      this.offset = 0; // Discard the partial frame on both transitions.
    };
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!this.enabled || !channel) return true;
    for (const sample of channel) {
      const noisy = Math.max(-1, Math.min(1, sample + (Math.random() - 0.5) * 0.003));
      this.samples[this.offset++] = Math.round(noisy * 32767);
      if (this.offset === this.samples.length) {
        this.port.postMessage(this.samples.buffer, [this.samples.buffer]);
        this.samples = new Int16Array(960);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("radio-capture", RadioCapture);
