"""Remote Crew by mouse: every key cap acts as its key, rows and lamps click.

Dominik (2026-10-06 18:38): "überprüfe die gesamte steuerung mit der maus, es
gibt einige dinge die nicht mit maus steuerbar sind". Package 6 of that plan
covers the browser: key caps that step a list, a telegraph or a page row are
real buttons pressing their key, a contact row on a station card selects its
contact, lamps and the boat's mode chips switch their mode, and every dialog
closes by its cross.
"""
import json
import re
from pathlib import Path

from commander_web import run_module_probe

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "data" / "commander" / "index.html").read_text(encoding="utf-8")


def test_list_and_page_keys_are_real_cap_buttons(tmp_path):
    probe = r"""
import { S } from "./js/state/store.js";
import { $ } from "./js/core/base.js";
import { markStationKeys } from "./js/input/station-keys.js";
const out = {};
const show = (element) => { for (let item = element; item; item = item.parentElement) item.hidden = false; };
S.language = "de";
S.v2State = {role: "engine"};
S.session = {station: "engine"};
show($("operations")); show($("engine-telegraph")); show($("engine-plant"));
const telegraph = $("engine-telegraph");
telegraph.replaceChildren(...["STOP", "SLOW", "HALF", "FULL"].map((value) => new Option(value, value)));
telegraph.selectedIndex = 1;
let sent = 0;
$("engine-telegraph-submit").addEventListener("click", () => sent++);
markStationKeys("engine");
const caps = [...document.querySelectorAll('label[for="engine-telegraph"] button.key-cap-button')];
out.telegraph_caps = caps.map((button) => button.textContent);
out.no_after_cap = document.querySelector('label[for="engine-telegraph"]').dataset.keycap ?? null;
caps.find((button) => button.dataset.capKey === "+").click();
out.telegraph = telegraph.value;
out.sent = sent;
// The plant list's G cap chooses the next plant and applies it.
let applied = 0;
$("engine-plant-apply").addEventListener("click", () => applied++);
$("engine-plant").selectedIndex = 0;
document.querySelector('label[for="engine-plant"] button.key-cap-button').click();
out.plant = $("engine-plant").value;
out.applied = applied;
// A second marking adds no second button.
markStationKeys("engine");
out.telegraph_cap_count = document.querySelectorAll('label[for="engine-telegraph"] button.key-cap-button').length;
// Leaving the station takes its buttons away.
markStationKeys("bridge");
out.after_leave = document.querySelectorAll('label[for="engine-telegraph"] button.key-cap-button').length;
// The sonar's page row: one cap per key; a page step never lands on a cap.
S.v2State = {role: "sonar"}; S.session = {station: "sonar"};
show($("sonar-page-tabs"));
markStationKeys("sonar");
const tabs = $("sonar-page-tabs");
out.page_caps = [...tabs.querySelectorAll("button.key-cap-button")].map((button) => button.dataset.capKey);
const pages = [...tabs.querySelectorAll("button:not(.key-cap)")];
pages.forEach((tab, index) => tab.setAttribute("aria-selected", String(index === 0)));
let clicked = null;
pages.forEach((tab, index) => tab.addEventListener("click", () => { clicked = index; }));
tabs.querySelector('button[data-cap-key="PageDown"]').click();
out.page_clicked = clicked;
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    result = json.loads(root["data-result"])
    assert result == {
        "telegraph_caps": ["+", "-"], "no_after_cap": None, "telegraph": "HALF", "sent": 1,
        "plant": "DIESEL", "applied": 1, "telegraph_cap_count": 2, "after_leave": 0,
        "page_caps": ["PageDown", "PageUp"], "page_clicked": 1}


def test_value_and_pair_caps_sit_where_the_key_acts(tmp_path):
    probe = r"""
import { S } from "./js/state/store.js";
import { $ } from "./js/core/base.js";
import { init, markStationKeys } from "./js/input/station-keys.js";
const out = {};
const show = (element) => { for (let item = element; item; item = item.parentElement) item.hidden = false; };
S.language = "en";
// The torpedo depth field: its cap is on the field's label, a click there focuses it.
S.v2State = {role: "weapons"}; S.session = {station: "weapons"};
show($("operations")); show($("weapons-fire-depth"));
markStationKeys("weapons");
const label = document.querySelector('label[for="weapons-fire-depth"]');
out.depth_cap = label.dataset.keycap;
out.depth_box = $("weapons-fire-depth").dataset.keycap ?? null;
label.click();
out.depth_focused = document.activeElement === $("weapons-fire-depth");
$("weapons-fire-depth").blur();
// The boat's radio room: the mast switch of the hidden ESM card is not the one P presses.
S.v2State = {role: "uboot_radio"}; S.session = {station: "uboot_radio"};
show($("station-uboot"));
for (const card of document.querySelectorAll("#station-uboot article")) card.hidden = !card.classList.contains("uboot-radio-card");
const masts = [...document.querySelectorAll('#station-uboot .uboot-radio-card [data-uboot-mode="uboot_mast"]')];
masts[0].setAttribute("aria-pressed", "false"); masts[1].setAttribute("aria-pressed", "true");
let pressed = null;
for (const button of document.querySelectorAll('[data-uboot-mode="uboot_mast"]'))
  button.addEventListener("click", () => { pressed = button.closest("article").classList.contains("uboot-radio-card") ? button.dataset.enabled : "hidden"; });
markStationKeys("uboot_radio");
// The cap sits on the button P presses now: raise the mast.
out.cap_on = masts[0].dataset.keycap ?? null;
out.cap_off = masts[1].dataset.keycap ?? null;
init();
document.body.dispatchEvent(new KeyboardEvent("keydown", {key: "p", bubbles: true}));
out.pressed = pressed;
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    assert json.loads(root["data-result"]) == {
        "depth_cap": "T", "depth_box": None, "depth_focused": True,
        "cap_on": "P", "cap_off": None, "pressed": "true"}


def test_rows_lamps_and_chips_click(tmp_path):
    probe = r"""
import { S } from "./js/state/store.js";
import { $ } from "./js/core/base.js";
import { on } from "./js/core/events.js";
import { stationRows } from "./js/views/dom.js";
import { modeSwitch, renderLamps } from "./js/views/console-kit.js";
const out = {};
S.language = "en";
S.catalog = {};
S.snapshot = {tracks: [{ref: "S-4"}]};
S.selected = null;
const picked = [];
on("track:select", (ref) => picked.push(ref));
const box = document.createElement("div");
document.body.append(box);
const button = document.createElement("button");
stationRows(box, [{ref: "S-4"}, {ref: "W-1"}], (row) => [["reference", row.ref]], "station_none",
  (row) => row.ref === "S-4" ? [button] : []);
const [contact, weapon] = box.children;
contact.querySelector("dl").click();
button.click();
weapon.click();
out.picked = picked;
out.selectable = [contact.dataset.trackRef ?? null, weapon.dataset.trackRef ?? null];
S.selected = "S-4";
stationRows(box, [{ref: "S-4"}, {ref: "W-1"}], (row) => [["reference", row.ref]]);
out.highlight = [...box.children].map((row) => row.classList.contains("track-selected"));
// A lamp of a mode presses the switch not pressed now.
const pair = document.createElement("div");
pair.innerHTML = '<button type="button" data-uboot-mode="uboot_silent" data-enabled="true" aria-pressed="true">on</button>' +
  '<button type="button" data-uboot-mode="uboot_silent" data-enabled="false" aria-pressed="false">off</button>';
document.body.append(pair);
let order = null;
for (const item of pair.children) item.addEventListener("click", () => { order = item.dataset.enabled; });
const lamps = document.createElement("div");
document.body.append(lamps);
renderLamps(lamps, [["silent", "Silent", "on", "on", modeSwitch("uboot_silent")], ["motor", "Motor", "on", "4 kn"]]);
out.lamp_roles = [...lamps.children].map((cell) => cell.getAttribute("role"));
lamps.children[0].click();
out.order = order;
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    assert json.loads(root["data-result"]) == {
        "picked": ["S-4"], "selectable": ["S-4", None], "highlight": [True, False],
        "lamp_roles": ["button", "listitem"], "order": "false"}


def test_every_dialog_has_a_close_cross():
    for match in re.finditer(r'<dialog id="([^"]+)".*?</dialog>', INDEX, re.S):
        body = match.group(0)
        assert 'class="dialog-close' in body, match.group(1)
        for target in re.findall(r'data-dialog-close="([^"]+)"', body):
            assert f'id="{target}"' in body, (match.group(1), target)


def test_helicopter_pages_step_both_ways():
    assert 'id="helicopter-visual-prev"' in INDEX and 'id="helicopter-visual-next"' in INDEX
    wiring = (ROOT / "data" / "commander" / "js" / "input" / "wiring.js").read_text(encoding="utf-8")
    assert '$("helicopter-visual-prev").addEventListener("click", () => stepHelicopterPage(-1));' in wiring
