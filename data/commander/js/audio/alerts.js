import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";

export function renderSound() {
  $("sound").textContent = t(S.soundEnabled ? "sound_on" : "sound_off");
  $("sound").setAttribute("aria-pressed", String(S.soundEnabled));
}
export function playAlert() {
  if (!S.soundEnabled || !S.audio || S.audio.state !== "running" || document.hidden) return;
  const volume = Number($("volume").value) / 100;
  if (!volume) return;
  const oscillator = S.audio.createOscillator();
  const gain = S.audio.createGain();
  const now = S.audio.currentTime;
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(660, now);
  oscillator.frequency.setValueAtTime(880, now + .12);
  gain.gain.setValueAtTime(0, now);
  gain.gain.linearRampToValueAtTime(volume * .12, now + .015);
  gain.gain.setValueAtTime(volume * .12, now + .18);
  gain.gain.linearRampToValueAtTime(0, now + .26);
  oscillator.connect(gain);
  gain.connect(S.audio.destination);
  oscillator.start(now);
  oscillator.stop(now + .28);
  oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
}
