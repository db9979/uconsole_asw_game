import { S } from "../state/store.js";
import { $, reasons } from "../core/base.js";
import { t, unit } from "../core/format.js";
import { sendBridgeOrder } from "../net/commands.js";
import { bridgeOrderAvailable } from "../state/availability.js";
import { renderDisabledReasons } from "./controls.js";
import { metrics } from "./dom.js";

export function renderBridgeOrders() {
  const panel = $("bridge-orders");
  panel.hidden = S.session?.station !== "bridge";
  if (panel.hidden) return;
  const navigation = S.v2State?.bridge?.navigation || {};
  metrics($("bridge-order-values"), [
    ["bridge_current_course", unit(navigation.course, "\u00b0", 0)],
    ["bridge_ordered_course", unit(navigation.target_course, "\u00b0", 0)],
    ["bridge_current_speed", unit(navigation.speed, "kn")],
    ["bridge_ordered_speed", unit(navigation.target_speed, "kn")],
  ]);
  $("bridge-course").disabled = $("bridge-course-submit").disabled = !bridgeOrderAvailable("course");
  $("bridge-speed").disabled = $("bridge-speed-submit").disabled = !bridgeOrderAvailable("speed");
  const telegraph = S.v2State?.bridge?.orders.telegraph;
  $("bridge-telegraph-up").disabled = !bridgeOrderAvailable("speed") || telegraph === "FLANK";
  $("bridge-telegraph-down").disabled = !bridgeOrderAvailable("speed") || telegraph === "ASTERN";
  const message = S.pending ? {key: S.pending.uncertain ? "bridge_order_uncertain" : "bridge_order_pending", status: "pending"} : S.commandMessage;
  const reason = Object.hasOwn(reasons, message?.reasoncode) ? t(reasons[message.reasoncode]) : t("reason_action_rejected");
  $("bridge-order-status").textContent = message ? t(message.key, {reason}) :
    S.v2State?.bridge?.orders.station_down ? t("bridge_down") : "";
  $("bridge-order-status").dataset.status = message?.status || "";
  renderDisabledReasons();
}
// Reads and validates the order form, then hands the number to the transport.
export function submitBridgeOrder(kind) {
  if (!bridgeOrderAvailable(kind)) return;
  if (!$(`bridge-${kind}-form`).reportValidity()) return;
  sendBridgeOrder(kind, $(`bridge-${kind}`).valueAsNumber);
}
