"""Browser stations take the uConsole's keys and show them as key caps.

Dominik (2026-10-05): the browser should be operated like the uConsole, with
every key visible on its control, empty values shown quietly and the chart's
country names in the page's language, once per country.
"""
import json

from commander_web import run_module_probe


def test_station_keys_press_the_matching_control(tmp_path):
    probe = r"""
import { S } from "./js/state/store.js";
import { $ } from "./js/core/base.js";
import { init, keyLabel } from "./js/input/station-keys.js";
import { metrics } from "./js/views/dom.js";
import { countryName } from "./js/core/format.js";
const out = {};
const show = (element) => { for (let item = element; item; item = item.parentElement) item.hidden = false; };
S.language = "de";
S.catalog = {"commander.web.country_denmark": "Dänemark", "commander.web.station_none": "Keine Daten veröffentlicht.",
  "commander.web.station_course": "Kurs"};
S.v2State = {role: "bridge"};
S.session = {station: "bridge"};
show($("operations")); show($("bridge-course")); show($("role-map-zoom-in"));
init();
out.cap_course = $("bridge-course-submit").dataset.keycap;
out.cap_zoom = $("role-map-zoom-in").dataset.keycap;
out.label_fire = keyLabel("Ctrl+Enter", "de");
out.label_page = keyLabel("PageDown", "en");
document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "c", bubbles: true}));
out.course_focused = document.activeElement === $("bridge-course");
// A key typed into a field stays in the field.
$("bridge-course").dispatchEvent(new KeyboardEvent("keydown", {key: "v", bubbles: true}));
out.speed_after_typing = document.activeElement === $("bridge-speed");
$("bridge-course").blur();
let zoomed = 0;
$("role-map-zoom-in").addEventListener("click", () => zoomed++);
document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "e", bubbles: true}));
out.zoomed = zoomed;
// Another station's key does nothing here.
document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "D", bubbles: true}));
out.depth_focused = document.activeElement === $("uboot-depth");
const dl = document.createElement("dl");
metrics(dl, [["station_course", "Keine Daten veröffentlicht."]]);
out.empty_text = dl.querySelector("dd").textContent;
out.empty_flag = dl.querySelector("dd").dataset.empty;
metrics(dl, [["station_course", "300 °"]]);
out.value_text = dl.querySelector("dd").textContent;
out.value_flag = dl.querySelector("dd").dataset.empty ?? null;
out.country = countryName("Denmark");
out.region = countryName("Britannia");
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    assert json.loads(root["data-result"]) == {
        "cap_course": "C", "cap_zoom": "E", "label_fire": "Strg+Enter", "label_page": "PgDn",
        "course_focused": True, "speed_after_typing": False, "zoomed": 1, "depth_focused": False,
        "empty_text": "—", "empty_flag": "true", "value_text": "300 °", "value_flag": None,
        "country": "Dänemark", "region": "Britannia"}
