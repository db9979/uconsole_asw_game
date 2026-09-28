// The phone's line of sight from DeviceOrientation (W3C: R = Rz(alpha) Rx(beta)
// Ry(gamma)).  The camera looks out of the back of the phone, so the line of
// sight is the device's -z axis; heading 0 is the device frame's "north"
// (compass on iOS, arbitrary on many Android browsers) and the view calibrates
// it against the bow.  Display only: nothing here is sent but the trained bearing.
const RAD = Math.PI / 180;

export const wrap360 = (value) => ((value % 360) + 360) % 360;
export const wrap180 = (value) => wrap360(value + 180) - 180;

// ``{heading, elevation}`` in degrees for the back camera, or null.
export function lineOfSight(alpha, beta, gamma) {
  if (![alpha, beta, gamma].every(Number.isFinite)) return null;
  const a = alpha * RAD, b = beta * RAD, g = gamma * RAD;
  const east = -Math.cos(a) * Math.sin(g) - Math.sin(a) * Math.sin(b) * Math.cos(g);
  const north = -Math.sin(a) * Math.sin(g) + Math.cos(a) * Math.sin(b) * Math.cos(g);
  const up = -Math.cos(b) * Math.cos(g);
  if (Math.hypot(east, north) < 1e-6) return null;      // looking straight up or down
  return {heading: wrap360(Math.atan2(east, north) / RAD), elevation: Math.asin(Math.max(-1, Math.min(1, up))) / RAD};
}
