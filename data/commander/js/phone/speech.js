// Spoken sighting reports: "Schiff Peilung 040, Entfernung 5 Meilen" or
// "aircraft starboard 30, range 8 miles".  ``parseReport`` is pure (tests
// call it); ``createListener`` wraps the browser's speech recognition, which
// the phone's own speech service performs.  Nothing but the parsed call leaves
// the page.
import { wrap360 } from "./orientation.js";

// Most specific first: "U-Boot" before "Boot", "Kriegsschiff" before "Schiff".
const CATEGORY_WORDS = [
  ["torpedo", ["torpedo", "torpedos", "torpedoes", "blasenbahn", "laufbahn"]],
  ["submarine", ["u-boot", "u boot", "uboot", "unterseeboot", "sehrohr", "periskop", "submarine", "periscope"]],
  ["aircraft", ["flugzeug", "flieger", "hubschrauber", "helikopter", "heli", "aircraft", "airplane", "plane", "helicopter", "helo", "jet"]],
  ["warship", ["kriegsschiff", "zerstörer", "zerstoerer", "fregatte", "korvette", "kreuzer", "warship", "destroyer", "frigate", "corvette", "cruiser", "man of war"]],
  ["merchant", ["handelsschiff", "frachter", "tanker", "fischer", "fischkutter", "kutter", "containerschiff", "fähre", "faehre", "merchant", "freighter", "cargo", "fishing", "trawler", "ferry", "container ship"]],
  ["ship", ["schiff", "boot", "segler", "ship", "vessel", "boat", "sail"]],
  ["contact", ["kontakt", "sichtung", "objekt", "contact", "sighting", "object", "target"]],
];
const DIGIT_WORDS = {
  null: 0, zero: 0, oh: 0, eins: 1, ein: 1, one: 1, zwei: 2, zwo: 2, two: 2, drei: 3, three: 3,
  vier: 4, four: 4, fünf: 5, fuenf: 5, five: 5, sechs: 6, six: 6, sieben: 7, seven: 7,
  acht: 8, eight: 8, neun: 9, nine: 9, niner: 9,
};
const BEARING_WORDS = ["peilung", "richtung", "bearing", "direction"];
const STARBOARD_WORDS = ["steuerbord", "stb", "starboard"];
const PORT_WORDS = ["backbord", "bb", "port"];
const AHEAD_WORDS = ["voraus", "ahead", "dead ahead", "bow"];
const ASTERN_WORDS = ["achteraus", "astern"];
const RANGE_WORDS = ["entfernung", "distanz", "abstand", "range", "distance"];
const MILE_WORDS = ["seemeilen", "seemeile", "meilen", "meile", "sm", "nm", "miles", "mile", "nautical"];
const CABLE_WORDS = ["kabellängen", "kabellänge", "kabel", "cables", "cable"];
export const RANGE_MAX_NM = 60;

function normalize(text) {
  return ` ${String(text).toLowerCase().replace(/[°º]/g, " ").replace(/(\d),(\d)/g, "$1.$2")
    .replace(/[^\p{L}\p{N}.\- ]+/gu, " ").replace(/\s+/g, " ").trim()} `;
}
const has = (text, word) => text.includes(` ${word} `) || text.includes(` ${word}-`);

// The number starting at token ``index``: digits ("040", "5.5", "0 4 0") or
// up to three spoken digits ("null vier null").
function numberAt(tokens, index) {
  const token = tokens[index];
  if (token === undefined) return null;
  if (/^\d$/.test(token)) {
    let digits = token;
    for (let at = index + 1; at < tokens.length && digits.length < 3 && /^\d$/.test(tokens[at]); at++) digits += tokens[at];
    return Number(digits);
  }
  if (/^\d+(\.\d+)?$/.test(token)) return Number(token);
  let digits = "";
  for (let at = index; at < tokens.length && digits.length < 3 && Object.hasOwn(DIGIT_WORDS, tokens[at]); at++)
    digits += String(DIGIT_WORDS[tokens[at]]);
  return digits ? Number(digits) : null;
}

// ``[value, index]`` of the first number within three tokens after any of
// ``words`` (a word may be two tokens: "dead ahead"), or null.
function numberAfter(tokens, words) {
  for (let index = 0; index < tokens.length; index++) {
    for (const word of words) {
      const parts = word.split(" ");
      if (parts.some((part, offset) => tokens[index + offset] !== part)) continue;
      for (let at = index + parts.length; at < Math.min(tokens.length, index + parts.length + 3); at++) {
        const value = numberAt(tokens, at);
        if (value !== null) return [value, at];
      }
    }
  }
  return null;
}

// ``{category, bearing, range_nm, explicit}`` from one heard sentence, or null
// when it names neither a category nor a bearing.  ``course`` is own course
// (for "Steuerbord 30"), ``viewBearing`` the eyepiece's line of sight (the
// default bearing).
export function parseReport(text, {course, viewBearing}) {
  const line = normalize(text), tokens = line.trim().split(" ");
  const found = CATEGORY_WORDS.find(([, words]) => words.some((word) => has(line, word)));
  let bearing = null;
  const value = (hit) => (hit === null ? null : hit[0]);
  const absolute = value(numberAfter(tokens, BEARING_WORDS));
  const starboard = value(numberAfter(tokens, STARBOARD_WORDS)), port = value(numberAfter(tokens, PORT_WORDS));
  if (absolute !== null && absolute <= 360) bearing = wrap360(absolute);
  else if (starboard !== null && starboard <= 180) bearing = wrap360(course + starboard);
  else if (port !== null && port <= 180) bearing = wrap360(course - port);
  else if (STARBOARD_WORDS.some((word) => has(line, word))) bearing = wrap360(course + 90);
  else if (PORT_WORDS.some((word) => has(line, word))) bearing = wrap360(course - 90);
  else if (ASTERN_WORDS.some((word) => has(line, word))) bearing = wrap360(course + 180);
  else if (AHEAD_WORDS.some((word) => has(line, word))) bearing = wrap360(course);
  if (!found && bearing === null) return null;
  let range = numberAfter(tokens, RANGE_WORDS);
  if (range === null) {
    const unit = tokens.findIndex((token, index) => index > 0 && [...MILE_WORDS, ...CABLE_WORDS].includes(token));
    const hit = unit > 0 ? numberAt(tokens, unit - 1) : null;
    if (hit !== null) range = [hit, unit - 1];
  }
  let rangeNm = null;
  if (range !== null) {
    // "5 Kabel" / "5 cables": tenths of a mile.
    const unit = tokens.slice(range[1] + 1, range[1] + 3);
    rangeNm = unit.some((token) => CABLE_WORDS.includes(token)) ? range[0] / 10 : range[0];
    if (!(rangeNm > 0 && rangeNm <= RANGE_MAX_NM)) rangeNm = null;
  }
  return {category: found ? found[0] : "contact", bearing: bearing ?? wrap360(viewBearing),
    range_nm: rangeNm, explicit: bearing !== null};
}

export const speechAvailable = () => typeof window !== "undefined" &&
  Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);

// One push-to-talk listener: ``onHeard(alternatives)`` with the transcripts
// (best first), ``onEnd()`` when it stops.
export function createListener({language, onHeard, onEnd, onError}) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new Recognition();
  recognition.lang = language === "de" ? "de-DE" : "en-US";
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.maxAlternatives = 3;
  recognition.onresult = (event) => {
    const result = event.results[event.results.length - 1];
    onHeard(Array.from({length: result.length}, (_, index) => result[index].transcript));
  };
  recognition.onerror = (event) => onError(event.error);
  recognition.onend = () => onEnd();
  recognition.start();
  return recognition;
}
