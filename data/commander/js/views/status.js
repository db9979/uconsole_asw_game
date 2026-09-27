import { S } from "../state/store.js";
import { $ } from "../core/base.js";
import { t } from "../core/format.js";
import { ESCALATE_AFTER_FAILURES, NOTICE_AFTER_FAILURES } from "../state/shared.js";

export function renderConnection() {
  const displayState = S.linkState === "stale" && S.failures < NOTICE_AFTER_FAILURES
    ? "reconnecting" : S.linkState;
  $("connection").dataset.state = displayState;
  const age = S.lastSuccess ? Math.max(0, Math.floor((performance.now() - S.lastSuccess) / 1000)) : 0;
  const key = displayState === "stale" ? "connection_stale"
    : displayState === "protocol_error" ? "connection_protocol_error"
    : `connection_${displayState}`;
  let text = t(key, { age });
  if ((S.linkState === "stale" || S.linkState === "protocol_error") && S.failures >= ESCALATE_AFTER_FAILURES) {
    text += " " + t("connection_escalated_hint", { minutes: Math.max(1, Math.floor(age / 60)) });
  }
  $("connection").textContent = text;
  $("connection").title = text;
}
