// The host shows its pairing code as "482 KMT". People type it with the space,
// in lower case, or mix up look-alikes (0/O, 1/I/L, 2/Z, 5/S, 6/G, 8/B); the
// code is always three digits and three capital letters, so each position
// says which one was meant. Anything else (spaces, invisible characters a
// phone keyboard may add) is dropped; full-width digits count as digits.
const DIGIT_FOR = {O: "0", D: "0", Q: "0", I: "1", L: "1", Z: "2", S: "5", G: "6", B: "8"};
const LETTER_FOR = {0: "O", 1: "I", 2: "Z", 5: "S", 6: "G", 8: "B"};

export function normalizePairCode(raw) {
  const text = String(raw || "").normalize("NFKC").toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 6);
  const digits = text.slice(0, 3).replace(/[A-Z]/g, (char) => DIGIT_FOR[char] || char);
  const letters = text.slice(3).replace(/[0-9]/g, (char) => LETTER_FOR[char] || char);
  return digits + letters;
}

// Rewrite the field while typing, keeping the caret at the end.
export function wirePairCodeInput(input) {
  input.addEventListener("input", () => {
    const code = normalizePairCode(input.value);
    if (code !== input.value) input.value = code;
  });
}
