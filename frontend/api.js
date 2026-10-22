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

// Says what actually went wrong, in the order a seller can act on it. `res` is a
// Response when something answered wrongly; `err` is the exception when nothing
// answered at all.
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
      `instead of Checkiz's JSON. Something else is listening on that port - another dev ` +
      `server is the usual reason. Run Checkiz on a free port and point this page at it.`;
  return `${CHECKIZ_API} returned HTTP ${res.status}.`;
}

// The only kind of failure the "the server is down" banner is for: the port is
// answering with something that is not Checkiz, or not answering at all. A parsed
// 400 from Checkiz itself is an answer, not an outage, and must not overwrite the
// connection warning.
function checkizIsUnreachable(res, err) {
  if (err) return true;
  const type = (res.headers.get("content-type") || "").split(";")[0];
  return !(type.includes("json") || type.includes("csv"));
}

// Asks the server what it is. Only call this when a normal request already
// failed: it is a diagnosis, not a health check the seller has to read.
async function checkizWho() {
  try {
    const res = await fetch(CHECKIZ_API + "/health");
    const body = await res.json().catch(() => null);
    if (body && body.name === "checkiz")
      return body.ui ? `${CHECKIZ_API} is Checkiz, with the pages served from it.`
                     : `${CHECKIZ_API} is Checkiz, but it cannot find frontend/ - set CHECKIZ_FRONTEND.`;
    return `${CHECKIZ_API} answered /health without saying it is Checkiz` +
      (body && body.status ? ` (it says "${body.status}")` : "") + `.`;
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
