// The host names its version on every API response (X-U-Jagd-Version) and in
// the page it served (<meta name="u-jagd-version">). A page that outlived a
// host update runs the old client against a new host, so it reloads itself
// once to fetch the matching client. Both come from the same host process
// and are never cached (no-store), so a reload cannot loop. The page layer
// (main.js) reads the meta tag and hands it over; transport never reads the page.
let pageVersion = null;
let reloading = false;

export function setPageVersion(version) {
  pageVersion = typeof version === "string" && version && version.length <= 32 ? version : null;
}

export function clientVersion() {
  return pageVersion;
}

export function checkHostVersion(hostVersion) {
  if (reloading || !pageVersion || typeof hostVersion !== "string" || !hostVersion ||
      hostVersion.length > 32 || hostVersion === pageVersion) return false;
  reloading = true;
  location.reload();
  return true;
}
