// One animation frame for every one-shot redraw. Data arrival (poll, stream,
// input) only marks a painter dirty; the frame then runs each dirty painter
// once, in the order they were first requested. Continuous animations (plot
// clock, weather, OPZ sweep) keep their own loops.
const dirty = new Map();
let frame = null;

function flush() {
  frame = null;
  const painters = [...dirty.values()];
  dirty.clear();
  for (const paint of painters) paint();
}

export function schedule(key, paint) {
  if (!dirty.has(key)) dirty.set(key, paint);
  if (frame === null) frame = requestAnimationFrame(flush);
}
