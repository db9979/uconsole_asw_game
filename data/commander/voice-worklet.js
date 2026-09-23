// Capture 20 ms PCM frames only while the local push-to-talk gate is open.
class CrewVoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.transmitting = false;
    this.frame = new Int16Array(960);
    this.offset = 0;
    this.port.onmessage = ({data}) => {
      this.transmitting = data === "down";
      this.offset = 0;
    };
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!this.transmitting || !channel) return true;
    for (const value of channel) {
      const sample = Math.max(-1, Math.min(1, value + (Math.random() - .5) * .003));
      this.frame[this.offset++] = Math.round(sample * 32767);
      if (this.offset === 960) {
        this.port.postMessage(this.frame.buffer, [this.frame.buffer]);
        this.frame = new Int16Array(960);
        this.offset = 0;
      }
    }
    return true;
  }
}
registerProcessor("crew-voice-capture", CrewVoiceCapture);
