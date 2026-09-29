// The host shows its pairing code as "482 KMT". People type it with the space,
// in lower case, or mix up 0/O and 1/I/L; the code itself is always three
// digits and three capital letters, so those are unambiguous by position.
export function normalizePairCode(raw) {
  const text = String(raw || "").toUpperCase().replace(/[^0-9A-Z]/g, "").slice(0, 6);
  const digits = text.slice(0, 3).replace(/O/g, "0").replace(/[IL]/g, "1");
  const letters = text.slice(3).replace(/0/g, "O").replace(/1/g, "I");
  return digits + letters;
}

// Rewrite the field while typing, keeping the caret at the end.
export function wirePairCodeInput(input) {
  input.addEventListener("input", () => {
    const code = normalizePairCode(input.value);
    if (code !== input.value) input.value = code;
  });
}
