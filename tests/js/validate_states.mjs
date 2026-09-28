// Runs the browser's own validators (data/commander/js/state) over role states
// and charts the host published. Reads JSON {states: [{role, state, chart}]}
// from stdin and prints one line per rejected state. Browser globals the
// imported modules touch at load time are stubbed; nothing is rendered.
globalThis.window = globalThis;
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
globalThis.document = {
  querySelector() { return null; }, getElementById() { return null; },
  documentElement: { lang: "en", dataset: {} }, addEventListener() {},
};
globalThis.location = { host: "localhost", protocol: "http:", search: "", reload() {} };

const root = new URL("../../data/commander/js/", import.meta.url);
const model = await import(new URL("state/display-model.js", root));
const { S } = await import(new URL("state/store.js", root));

let input = "";
for await (const chunk of process.stdin) input += chunk;
const rows = JSON.parse(input).states;
const failures = [];
for (const [index, row] of rows.entries()) {
  try {
    // The client validates the state of the station its session holds.
    S.session = { station: row.role };
    model.validateState(row.state);
    if (row.chart !== null) model.validateChart(row.chart, row.state);
  } catch (error) {
    failures.push(`${index} ${row.label} ${row.role}: ${error.message}`);
  }
}
console.log(JSON.stringify({ checked: rows.length, failures }));
