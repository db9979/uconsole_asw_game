"""State pushes leave a drop-down or button the operator is using alone.

Dominik saw the U-boat ESM classification list close again and again: every
state push rebuilt its options. Drop-downs now only change while not in use,
and row lists patch their elements in place instead of rebuilding them.
"""
import json

from commander_web import run_module_probe


def test_select_in_use_keeps_options_and_choice(tmp_path):
    probe = r"""
import { $ } from "./js/core/base.js";
import { fillFireTargets, patchChildren, setControlValue, setOptions } from "./js/views/dom.js";
const out = {};
// Stations start hidden; a hidden control cannot take focus.
const show = (element) => { for (let item = element; item; item = item.parentElement) item.hidden = false; };
const select = $("uboot-esm-class");
show(select);
setOptions(select, [["-1", "none"], ["0", "Radar A 50%"], ["1", "Radar B 20%"]]);
select.value = "1";
const first = select.options[1];
select.focus();
out.focused = document.activeElement === select;
out.rebuilt_in_use = setOptions(select, [["-1", "none"], ["0", "Radar A 55%"], ["1", "Radar B 25%"]]);
setControlValue(select, "-1");
out.same_node = select.options[1] === first;
out.value_in_use = select.value;
select.blur();
out.rebuilt_after = setOptions(select, [["-1", "none"], ["0", "Radar A 55%"], ["1", "Radar B 25%"]]);
out.value_after = select.value;
out.text_after = select.options[1].textContent;
out.rebuilt_same = setOptions(select, [["-1", "none"], ["0", "Radar A 55%"], ["1", "Radar B 25%"]]);

const target = $("uboot-fire-target");
show(target);
fillFireTargets("uboot-fire-target", [{ref: "C1", label: "S1", bearing: 10, range_nm: 2}]);
const option = target.options[1];
target.focus();
fillFireTargets("uboot-fire-target", [{ref: "C1", label: "S1", bearing: 12, range_nm: 1.8}, {ref: "C2", label: "S2", bearing: 90, range_nm: 4}]);
out.fire_same = target.options[1] === option && target.options.length === 2;
target.blur();
fillFireTargets("uboot-fire-target", [{ref: "C1", label: "S1", bearing: 12, range_nm: 1.8}, {ref: "C2", label: "S2", bearing: 90, range_nm: 4}]);
out.fire_after = target.options.length;

const list = document.createElement("div");
document.body.append(list);
const row = (key, text) => {
  const line = document.createElement("p");
  line.dataset.rowKey = key;
  const button = document.createElement("button");
  button.textContent = text;
  line.append(button);
  return line;
};
patchChildren(list, [row("a", "1"), row("b", "2")]);
const button = list.firstChild.firstChild;
patchChildren(list, [row("a", "3"), row("b", "4")]);
out.button_kept = list.firstChild.firstChild === button && button.textContent === "3";
patchChildren(list, [row("c", "5")]);
out.replaced = list.children.length === 1 && list.firstChild.firstChild !== button && list.textContent === "5";
document.documentElement.dataset.result = JSON.stringify(out);
"""
    root = run_module_probe(tmp_path, probe)
    assert "data-result" in root, root.get("data-failure")
    assert json.loads(root["data-result"]) == {
        "focused": True, "rebuilt_in_use": False, "same_node": True, "value_in_use": "1",
        "rebuilt_after": True, "value_after": "1", "text_after": "Radar A 55%", "rebuilt_same": False,
        "fire_same": True, "fire_after": 3, "button_kept": True, "replaced": True}
