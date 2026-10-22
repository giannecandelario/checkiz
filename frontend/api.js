// One rule for where the API lives, shared by the dashboard, the QR page and the
// overlay. Before this, each page guessed a port, so an unrelated program
// holding 8000 made Checkiz look broken and gave no way to tell the difference.
//   ?api=...              wins - a phone pointed at a machine on the network
//   this page's own origin - the normal case: the backend serves these pages too
//   http://localhost:8000  - a page opened straight from disk (file://)
const CHECKIZ_API = (() => {
  const override = new URLSearchParams(location.search).get("api");
  if (override) return override.replace(/\/$/, "");
  if (location.protocol === "http:" || location.protocol === "https:") return location.origin;
  return "http://localhost:8000";
})();

// Says what actually went wrong, and only what the response itself proves. `res` is
// a Response when something answered wrongly; `err` is the exception when nothing
// answered at all. Who is answering is checkizWho()'s job: Checkiz's own crash comes
// back as text/plain too, and this page used to call that "another server".
function checkizProblem(res, err) {
  if (err) return `Nothing answered at ${CHECKIZ_API} (${err.message || err}). ` +
    `Start the server, or name it with ?api=http://its-address:8000.`;
  const type = (res.headers.get("content-type") || "").split(";")[0];
  const isData = type.includes("json") || type.includes("csv");
  if (res.status === 401 || res.status === 403)
    return `${CHECKIZ_API} refused the request (HTTP ${res.status}). That server sets ` +
      `CHECKIZ_API_KEY - type it in the key box above.`;
  if (!isData)
    return `${CHECKIZ_API} answered HTTP ${res.status} with ${type || "no content type"} ` +
      `instead of the JSON a Checkiz request returns.`;
  return `${CHECKIZ_API} returned HTTP ${res.status}.`;
}

// The only kind of failure the "the server is down" banner is for: the port is
// answering with something that is not Checkiz-shaped, or not answering at all. A
// parsed 400 from Checkiz itself is an answer, not an outage, and must not
// overwrite the connection warning.
function checkizIsUnreachable(res, err) {
  if (err) return true;
  const type = (res.headers.get("content-type") || "").split(";")[0];
  return !(type.includes("json") || type.includes("csv"));
}

// Asks the server what it is. Only call this when a normal request already failed:
// it is a diagnosis, not a health check the seller has to read. This is where the
// "wrong port" conclusion belongs, because /health is what proves it.
async function checkizWho() {
  try {
    const res = await fetch(CHECKIZ_API + "/health");
    const body = await res.json().catch(() => null);
    if (body && body.name === "checkiz") {
      const where = body.ui ? `${CHECKIZ_API} is Checkiz, with the pages served from it`
                            : `${CHECKIZ_API} is Checkiz, but it cannot find frontend/ - set CHECKIZ_FRONTEND`;
      return body.ocr ? `${where}.`
        : `${where}, and it has no OCR engine: Tesseract is not installed on that machine, ` +
          `so no receipt can be read until it is (the Docker image has it).`;
    }
    // The dashboard branch added `name`. Until then /health answered {"ok": true},
    // which is what main still returns, so a real Checkiz running one branch behind
    // used to be reported as some other program squatting on the port.
    if (body && body.ok === true)
      return `${CHECKIZ_API} answered /health as {"ok": true} - that is Checkiz on a branch ` +
        `from before /health named itself, so it does not serve these pages and may not have ` +
        `Tesseract. Restart it from the branch that has them, or point this page at that ` +
        `server with ?api=`;
    return `${CHECKIZ_API} is not Checkiz` +
      (body && body.status ? ` (its /health says "${body.status}")` : "") +
      `. Another program holding that port is the usual reason - run Checkiz on a free ` +
      `port and point this page at it with ?api=`;
  } catch (e) {
    return `Nothing answered at ${CHECKIZ_API}/health (${e.message || e}).`;
  }
}

// Saves bytes as a file, from a Blob or a data: URL. A <a download> on a data: URL
// is refused by Chrome and Safari, and revoking an object URL in the same tick as
// the click can drop the download before it starts - which is why the QR PNG and
// the packing CSV both looked like a button that did nothing.
async function checkizDownload(src, filename) {
  const blob = src instanceof Blob ? src : await (await fetch(src)).blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
