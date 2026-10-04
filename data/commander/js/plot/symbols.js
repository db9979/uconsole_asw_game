import { ctx } from "../views/canvases.js";

// NATO-style symbol, same geometry as the uConsole (src/ui/nato_symbols.py):
// the frame shows the operator's affiliation (hostile diamond, neutral
// square, friend wide rectangle, unknown: no frame), the glyph the domain.
export function drawNatoSymbol(context, x, y, affiliation, domain, color, size) {
  const half = Math.max(5, size), height = Math.max(6, size * 1.3), glyph = Math.max(3, size * .5);
  context.strokeStyle = color; context.lineWidth = 2; context.beginPath();
  if (affiliation === "HOSTILE") {
    context.moveTo(x, y - height); context.lineTo(x + half, y); context.lineTo(x, y + height); context.lineTo(x - half, y); context.closePath();
  } else if (affiliation === "NEUTRAL") {
    context.rect(x - half, y - height, half * 2, height * 2);
  } else if (affiliation === "FRIEND") {
    context.rect(x - half - 2, y - height, half * 2 + 4, height * 2);
  }
  // Unknown affiliation: no frame, only the domain glyph (colour marks it).
  context.stroke();
  context.lineWidth = 1.6; context.beginPath();
  if (domain === "AIR") {
    context.moveTo(x - glyph, y + glyph * .7); context.lineTo(x, y - glyph * .7); context.lineTo(x + glyph, y + glyph * .7);
  } else if (domain === "ROTARY") {
    // Rotary wing (APP-6 / MIL-STD-2525 helicopter icon): a bow tie of two
    // rotor blades meeting at the hub, as on the uConsole.
    const g = Math.max(4, half - 2);
    context.moveTo(x - g, y - g / 2); context.lineTo(x, y); context.lineTo(x - g, y + g / 2); context.closePath();
    context.moveTo(x + g, y - g / 2); context.lineTo(x, y); context.lineTo(x + g, y + g / 2); context.closePath();
  } else if (domain === "MISSILE") {
    context.moveTo(x, y + glyph); context.lineTo(x, y - glyph); context.moveTo(x - glyph * .7, y - glyph * .2);
    context.lineTo(x, y - glyph); context.lineTo(x + glyph * .7, y - glyph * .2);
  } else if (domain === "SUBSURFACE") {
    context.arc(x, y + glyph * .3, glyph * 1.2, Math.PI, Math.PI * 2);
    context.moveTo(x - glyph * .4, y + glyph * .3); context.lineTo(x - glyph * .4, y - glyph * .4); context.lineTo(x + glyph * .4, y - glyph * .4);
  } else if (domain === "UNDERWATER_WEAPON") {
    context.moveTo(x - glyph, y); context.lineTo(x + glyph, y); context.moveTo(x + glyph * .4, y - glyph * .4);
    context.lineTo(x + glyph, y); context.lineTo(x + glyph * .4, y + glyph * .4);
  } else if (domain === "SURFACE") {
    context.moveTo(x - glyph * 1.2, y + glyph * .4); context.lineTo(x + glyph * 1.2, y + glyph * .4);
    context.moveTo(x + glyph * 1.2, y + glyph * .4); context.arc(x, y + glyph * .4, glyph * 1.2, 0, Math.PI, true);
  } else {
    context.arc(x, y, Math.max(1.5, glyph * .4), 0, Math.PI * 2);
  }
  context.stroke();
}
export function drawSymbolOn(context, x, y, domain, color, size, affiliation = "UNKNOWN") {
  drawNatoSymbol(context, x, y, affiliation, domain, color, size);
}
export function drawSymbol(x, y, domain, color, size, affiliation = "UNKNOWN") {
  drawNatoSymbol(ctx, x, y, affiliation, domain, color, size);
}
