// Shared camera helper.
// cameraCapture(onFile, { live: onPayload }):
//  - opens the rear camera with a Capture button and passes the photo to onFile(File)
//  - if the browser has BarcodeDetector and `live` is given, QR codes are detected
//    continuously and passed to live(rawText) (the camera then closes)
//  - when the camera is not available it says why, then uses the phone's native
//    camera through <input capture>, which needs no browser permission
function cameraCapture(onFile, opts = {}) {
  const tell = msg => {
    const bar = document.createElement("div");
    bar.style.cssText = "position:fixed;left:0;right:0;bottom:0;background:#5d4037;color:#fff;" +
      "padding:12px 14px;z-index:100;font:14px system-ui,sans-serif;display:flex;gap:12px;" +
      "align-items:center;justify-content:space-between";
    const text = document.createElement("span");
    text.textContent = msg;
    const off = document.createElement("button");
    off.textContent = "Dismiss";
    off.style.cssText = "padding:6px 12px;border:0;border-radius:6px;background:#fff3e0;cursor:pointer";
    off.onclick = () => bar.remove();
    bar.append(text, off);
    document.body.append(bar);
    setTimeout(() => bar.remove(), 12000);
  };
  const fallback = why => {
    if (why) tell(why);
    const i = document.createElement("input");
    i.type = "file"; i.accept = "image/*"; i.setAttribute("capture", "environment");
    i.onchange = () => i.files[0] && onFile(i.files[0]);
    document.body.append(i);   // a detached input is ignored by some browsers
    i.click();
    setTimeout(() => i.remove(), 60000);
  };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
    return fallback("This browser cannot show the camera in the page. Choose or take the photo below.");
  // Over plain http on a LAN address the browser refuses the camera outright, and the
  // error it throws says only "Permission denied". A seller on a phone needs to know
  // the page is at fault, not the phone.
  if (!window.isSecureContext)
    return fallback(`In-page camera needs https or localhost; this page is served at ` +
      `${location.host} over ${location.protocol}. Choosing a photo works the same.`);

  const REASON = {
    NotAllowedError: "Camera permission was refused. Allow the camera for this site (a remembered " +
      "'Block' is cleared at the lock icon in the address bar), or choose a photo below.",
    SecurityError: "The browser blocked the camera for security reasons. Choose a photo below.",
    NotFoundError: "No camera found on this device. Choose a photo below.",
    OverconstrainedError: "No rear camera here. Choose a photo below.",
    NotReadableError: "Another app is using the camera. Close it and try again, or choose a photo below.",
  };

  navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
    .then(stream => {
      const box = document.createElement("div");
      box.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;flex-direction:column;" +
        "align-items:center;justify-content:center;gap:12px;z-index:99;color:#fff;font-family:system-ui,sans-serif";
      const video = document.createElement("video");
      video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = stream;
      video.style.cssText = "max-width:92vw;max-height:68vh;border-radius:10px";
      const hint = document.createElement("div");
      const row = document.createElement("div");
      const btn = (t, fn) => { const b = document.createElement("button"); b.textContent = t; b.onclick = fn;
        b.style.cssText = "padding:10px 18px;margin:0 6px;font-size:16px;border-radius:8px;border:0;cursor:pointer"; return b; };
      let timer = null;
      const close = () => { clearInterval(timer); stream.getTracks().forEach(t => t.stop()); box.remove(); };
      video.onerror = () => { close(); fallback("The camera preview failed to start. Choose a photo below."); };
      row.append(
        btn("Capture", () => {
          // The stream is granted before the first frame arrives, so the video is
          // still 0x0 for a moment after permission; drawing then makes a blank
          // file that the server reads as an unreadable image.
          if (!video.videoWidth || !video.videoHeight) {
            hint.textContent = "Camera is still starting - tap Capture again in a second.";
            return;
          }
          const c = document.createElement("canvas");
          c.width = video.videoWidth; c.height = video.videoHeight;
          c.getContext("2d").drawImage(video, 0, 0);
          c.toBlob(b => { close(); onFile(new File([b], "capture.jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.92);
        }),
        btn("Cancel", close));
      box.append(video, hint, row); document.body.append(box);

      let det = null;
      if (opts.live && "BarcodeDetector" in window) {
        try { det = new BarcodeDetector({ formats: ["qr_code"] }); } catch (e) { det = null; }
      }
      hint.textContent = det ? "Point at the QR code..." : "Frame it, then tap Capture";
      if (det) {
        timer = setInterval(async () => {
          try { const f = await det.detect(video); if (f.length) { close(); opts.live(f[0].rawValue); } } catch (e) {}
        }, 300);
      }
      // Permission granted then revoked (or the tab hidden) leaves a stream with no
      // live track; say so instead of showing a black frame forever.
      if (!stream.getVideoTracks().length) {
        close();
        fallback("The camera closed again straight away. Choose a photo below.");
      }
    })
    .catch(err => fallback(REASON[err && err.name] ||
      `The camera could not open (${(err && err.name) || err}). Choose a photo below.`));
}
