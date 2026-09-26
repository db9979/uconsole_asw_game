"""Layering of the Remote Crew web client (data/commander/js)."""
import re

from commander_web import ASSET_DIR, run_module_probe

JS = ASSET_DIR / "js"
IMPORT = re.compile(r'^import (?:\{[^}]*\} from )?"([^"]+)";', re.M)


def _imports(path):
    return [(path.parent / target).resolve().relative_to(JS.resolve()).as_posix()
            for target in IMPORT.findall(path.read_text(encoding="utf-8"))]


def test_transport_never_touches_the_page():
    """net/* only talks HTTP/WebSocket and updates the store; views follow topics."""
    for path in sorted((JS / "net").glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for forbidden in ("$(", "getElementById", "querySelector", "innerHTML",
                          "textContent", "classList", "dataset", "addEventListener(\"click\""):
            assert forbidden not in text, (path.name, forbidden)
        for target in _imports(path):
            assert target.split("/")[0] in {"core", "state", "net"}, (path.name, target)


def test_state_layer_is_page_free():
    for path in sorted((JS / "state").glob("*.js")):
        text = path.read_text(encoding="utf-8")
        assert "$(" not in text and "getElementById" not in text, path.name
        for target in _imports(path):
            assert target.split("/")[0] in {"core", "state"}, (path.name, target)


def test_every_module_is_reachable_from_the_entry_point():
    seen, stack = set(), ["main.js"]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(_imports(JS / name))
    assert seen == {path.relative_to(JS).as_posix() for path in JS.rglob("*.js")}


def test_scheduler_coalesces_redraws_into_one_frame(tmp_path):
    # Headless dump-dom does not render frames reliably; a timer-driven frame
    # keeps the test deterministic (the scheduler looks the function up per call).
    probe = r"""
globalThis.requestAnimationFrame = (callback) => setTimeout(() => callback(performance.now()), 16);
import { schedule } from "./js/core/scheduler.js";
import { emit, on } from "./js/core/events.js";
const calls = [];
schedule("a", () => calls.push("a1"));
schedule("b", () => calls.push("b"));
schedule("a", () => calls.push("a2"));
const order = [];
on("topic", (value) => order.push(["first", value]));
on("topic", (value) => order.push(["second", value]));
emit("topic", 7);
requestAnimationFrame(() => requestAnimationFrame(() => {
  schedule("c", () => calls.push("c"));
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.dataset.result = JSON.stringify({calls, order});
  }));
}));
"""
    import json
    root = run_module_probe(tmp_path, probe)
    assert json.loads(root["data-result"]) == {
        "calls": ["a1", "b", "c"], "order": [["first", 7], ["second", 7]]}
