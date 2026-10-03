import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { finite, hasPosition, number, t, unit } from "../core/format.js";
import { colors, palette } from "../core/palette.js";
import { lookoutRanges, lookoutView, view } from "../state/shared.js";
import { chartGeometry, queueDraw, resizeCanvas } from "./chart.js";
import { node } from "./dom.js";
import { schedule } from "../core/scheduler.js";
import { canvas, lookoutCanvas, lookoutCtx } from "./canvases.js";

export function renderLookoutStatus() {
  const environment = S.snapshot?.environment;
  $("lookout-sea").textContent = finite(environment?.sea_state) ? number(environment.sea_state, 0) : t("unavailable");
  $("lookout-light").textContent = typeof environment?.is_night === "boolean" ? t(environment.is_night ? "night" : "day") : t("unavailable");
  $("lookout-range").textContent = t("lookout_range", { distance: number(lookoutView.rangeNm, 0) });
  $("lookout-scope").dataset.light = environment?.is_night === true ? "night" : environment?.is_night === false ? "day" : "unknown";
  $("lookout-own").textContent = t("lookout_own_course", { course: unit(S.snapshot?.ownship?.course, "\u00b0", 0) });
  if (!$("panel-lookout").hidden) {
    $("lookout-observations").replaceChildren(...(S.snapshot?.tracks || []).map((track) => node(
      "li", `${String(track.label ?? "")}: ${t(hasPosition(track) ? "lookout_positioned" : "lookout_bearing_report")} / ${unit(track.bearing, "\u00b0", 0)} / ${unit(track.range_nm, "NM")}`)));
  }
}
export function queueLookoutDraw() {
  schedule("lookout", drawLookout);
}
function drawLookout() {
  if (!S.snapshot || $("panel-lookout").hidden) return;
  const width = lookoutCanvas.clientWidth;
  const height = lookoutCanvas.clientHeight;
  if (!width || !height) return;
  resizeCanvas(lookoutCanvas, lookoutCtx, width, height);
  const environment = S.snapshot.environment;
  lookoutCtx.fillStyle = environment?.is_night === true ? palette().scopeBg : environment?.is_night === false ? palette().panel : palette().bg;
  lookoutCtx.fillRect(0, 0, width, height);
  const own = S.snapshot.ownship;
  if (!hasPosition(own)) return;
  const fontSize = Math.max(11, parseFloat(getComputedStyle(document.documentElement).fontSize) * .7);
  lookoutCtx.font = `${fontSize}px ui-monospace, monospace`;
  lookoutCtx.lineWidth = 1;
  const centerX = width / 2;
  const centerY = height / 2;
  const compact = height < 120;
  const radius = Math.max(8, Math.min(width, height) / 2 - (compact ? 3 : Math.max(24, fontSize * 2.4)));
  const scale = radius / lookoutView.rangeNm;
  lookoutCtx.strokeStyle = environment?.is_night === true ? palette().line : palette().lineStrong;
  lookoutCtx.fillStyle = environment?.is_night === true ? palette().faint : palette().muted;
  for (const fraction of compact ? [.5, 1] : [.25, .5, .75, 1]) {
    const ringRadius = radius * fraction;
    lookoutCtx.beginPath();
    lookoutCtx.arc(centerX, centerY, ringRadius, 0, Math.PI * 2);
    lookoutCtx.stroke();
    if (!compact) {
      const label = `${number(lookoutView.rangeNm * fraction, lookoutView.rangeNm < 10 ? 1 : 0)} NM`;
      const labelWidth = lookoutCtx.measureText(label).width;
      lookoutCtx.fillText(label, Math.max(2, centerX - labelWidth / 2), Math.max(fontSize, centerY - ringRadius + fontSize));
    }
  }
  // All geometry below is derived from the current detached snapshot only.
  for (const track of S.snapshot.tracks) {
    const color = colors[track.affiliation] || colors.UNKNOWN;
    lookoutCtx.strokeStyle = color;
    lookoutCtx.fillStyle = color;
    if (finite(track.x) && finite(track.y)) {
      const dx = track.x - own.x;
      const dy = track.y - own.y;
      if (Math.hypot(dx, dy) > lookoutView.rangeNm) continue;
      const x = centerX + dx * scale;
      const y = centerY + dy * scale;
      lookoutCtx.beginPath();
      lookoutCtx.arc(x, y, compact ? 2 : 4, 0, Math.PI * 2);
      lookoutCtx.fill();
      const label = String(track.label ?? "");
      if (!compact && label && x + 9 < width - 2) lookoutCtx.fillText(label, x + 8, Math.max(fontSize, Math.min(height - 3, y - 7)), Math.max(0, width - x - 11));
      continue;
    }
    if (!finite(track.bearing)) continue;
    const angle = track.bearing * Math.PI / 180 - Math.PI / 2;
    const x = centerX + Math.cos(angle) * radius;
    const y = centerY + Math.sin(angle) * radius;
    const uncertainty = finite(track.bearing_uncertainty_deg) ? Math.min(180, Math.max(0, track.bearing_uncertainty_deg)) * Math.PI / 180 : 0;
    if (uncertainty) {
      lookoutCtx.globalAlpha = .35;
      lookoutCtx.beginPath();
      lookoutCtx.arc(centerX, centerY, radius, angle - uncertainty, angle + uncertainty);
      lookoutCtx.stroke();
      lookoutCtx.globalAlpha = 1;
    }
    lookoutCtx.save();
    lookoutCtx.translate(x, y);
    lookoutCtx.rotate(angle + Math.PI / 2);
    lookoutCtx.beginPath();
    const marker = compact ? 4 : 9;
    lookoutCtx.moveTo(0, marker);
    lookoutCtx.lineTo(-marker * .67, -marker / 3);
    lookoutCtx.lineTo(marker * .67, -marker / 3);
    lookoutCtx.closePath();
    lookoutCtx.fill();
    lookoutCtx.restore();
  }
  lookoutCtx.save();
  lookoutCtx.translate(centerX, centerY);
  lookoutCtx.strokeStyle = palette().accent;
  lookoutCtx.fillStyle = palette().raised;
  lookoutCtx.lineWidth = 2;
  if (finite(own.course)) {
    lookoutCtx.rotate(own.course * Math.PI / 180);
    lookoutCtx.beginPath();
    const shipSize = compact ? 4 : 12;
    lookoutCtx.moveTo(0, -shipSize);
    lookoutCtx.lineTo(shipSize * .58, shipSize * .67);
    lookoutCtx.lineTo(-shipSize * .58, shipSize * .67);
    lookoutCtx.closePath();
    lookoutCtx.fill();
    lookoutCtx.stroke();
    lookoutCtx.beginPath();
    lookoutCtx.moveTo(0, -(compact ? 5 : 15));
    lookoutCtx.lineTo(0, -Math.min(compact ? 12 : 48, radius * .55));
    lookoutCtx.stroke();
  } else {
    lookoutCtx.beginPath();
    lookoutCtx.arc(0, 0, compact ? 3 : 8, 0, Math.PI * 2);
    lookoutCtx.stroke();
  }
  lookoutCtx.restore();
  if (!compact) {
    lookoutCtx.fillStyle = palette().text;
    lookoutCtx.fillText(t("north"), width - Math.max(18, lookoutCtx.measureText(t("north")).width + 6), fontSize + 5);
  }
}
export function changeLookoutRange(direction) {
  const current = lookoutRanges.indexOf(lookoutView.rangeNm);
  const index = Math.max(0, Math.min(lookoutRanges.length - 1, current + direction));
  lookoutView.rangeNm = lookoutRanges[index];
  renderLookoutStatus();
  queueLookoutDraw();
}
export function zoom(factor, px = canvas.clientWidth / 2, py = canvas.clientHeight / 2) {
  if (!S.chart || !S.snapshot) return;
  const before = chartGeometry();
  const newZoom = Math.max(.5, Math.min(256, view.zoom * factor));
  if (!view.follow) {
    view.x += (px - before.width / 2) / before.scale * (1 - view.zoom / newZoom);
    view.y += (py - before.height / 2) / before.scale * (1 - view.zoom / newZoom);
  }
  view.zoom = newZoom;
  queueDraw();
}
