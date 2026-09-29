import { S } from "../state/store.js";
import { renderSound } from "../audio/alerts.js";
import { $, prefix } from "./base.js";
import { chartMatches, t } from "./format.js";
import { request } from "../net/request.js";
import { renderContactAnalysis } from "../views/analyzer.js";
import { renderLobby } from "../views/lobby.js";
import { renderSnapshot } from "../views/render.js";
import { renderConnection } from "../views/status.js";

export async function loadLanguage(nextLanguage) {
  const serial = ++S.languageRequest;
  $("language").disabled = $("language-switch").disabled = true;
  try {
    const translations = await request(`/ui?lang=${nextLanguage}`, { auth: false });
    if (serial !== S.languageRequest) return false;
    if (!translations || typeof translations[prefix + "pair_title"] !== "string" ||
        Object.entries(translations).some(([key, value]) => !key.startsWith(prefix) || typeof value !== "string")) throw new Error("catalog");
    S.catalog = translations;
    S.language = nextLanguage;
    document.documentElement.lang = S.language;
    $("language").value = S.language;
    $("guide-manual-link").href = `/manual-${S.language}`;
    window.dispatchEvent(new CustomEvent("u-jagd-language", {
      detail: {language: S.language, translations}
    }));
    for (const element of document.querySelectorAll("[data-i18n]")) element.textContent = t(element.dataset.i18n);
    for (const element of document.querySelectorAll("[data-i18n-aria]")) element.setAttribute("aria-label", t(element.dataset.i18nAria));
    for (const element of document.querySelectorAll("[data-i18n-placeholder]")) element.placeholder = t(element.dataset.i18nPlaceholder);
    // The visible switch names the other language, in that language.
    const other = S.language === "de" ? "en" : "de";
    $("language-switch").textContent = t(other === "de" ? "german" : "english");
    $("language-switch").lang = other;
    $("language-switch").dataset.language = other;
    if (!$("name").value) $("name").value = t("pair_name_default").slice(0, 32);
    $("bootstrap").hidden = true;
    $("shell").hidden = false;
    renderConnection();
    renderSound();
    if (S.snapshot && chartMatches(S.snapshot)) renderSnapshot();
    renderContactAnalysis();
    renderLobby();
    return true;
  } catch (_) {
    $("language").value = S.language;
    if (Object.keys(S.catalog).length) $("connection").textContent = t("language_failed");
    return false;
  } finally {
    if (serial === S.languageRequest) $("language").disabled = $("language-switch").disabled = false;
  }
}
