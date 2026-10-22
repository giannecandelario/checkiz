// Shared camera helper.
// cameraCapture(onFile, { live: onPayload }):
//  - opens the rear camera with a Capture button and passes the photo to onFile(File)
//  - if the browser has BarcodeDetector and `live` is given, QR codes are detected
//    continuously and passed to live(rawText) (the camera then closes)
//  - falls back to the phone's native camera via <input capture> when getUserMedia
//    is unavailable (it needs https or localhost) or permission is denied.
function cameraCapture(onFile, opts = {}) {
  const fallback = () => {
    const i = document.createElement("input");
    i.type = "file"; i.accept = "image/*"; i.setAttribute("capture", "environment");
    i.onchange = () => i.files[0] && onFile(i.files[0]);
    i.click();
  };
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return fallback();

  navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
    .then(stream => {
      const box = document.createElement("div");
      box.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.85);display:flex;flex-direction:column;" +
        "align-items:center;justify-content:center;gap:12px;z-index:99;color:#fff;font-family:system-ui,sans-serif";
      const video = document.createElement("video");
      video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = stream;
      video.style.cssText = "max-width:92vw;max-height:68vh;border-radius:10px";
      const hint = document.createElement("div");
      hint.textContent = opts.live && "BarcodeDetector" in window ? "Point at the QR code..." : "Frame it, then tap Capture";
      const row = document.createElement("div");
      const btn = (t, fn) => { const b = document.createElement("button"); b.textContent = t; b.onclick = fn;
        b.style.cssText = "padding:10px 18px;margin:0 6px;font-size:16px;border-radius:8px;border:0;cursor:pointer"; return b; };
      let timer = null;
      const close = () => { clearInterval(timer); stream.getTracks().forEach(t => t.stop()); box.remove(); };
      row.append(
        btn("Capture", () => {
          const c = document.createElement("canvas");
          c.width = video.videoWidth; c.height = video.videoHeight;
          c.getContext("2d").drawImage(video, 0, 0);
          c.toBlob(b => { close(); onFile(new File([b], "capture.jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.92);
        }),
        btn("Cancel", close));
      box.append(video, hint, row); document.body.append(box);

      if (opts.live && "BarcodeDetector" in window) {
        const det = new BarcodeDetector({ formats: ["qr_code"] });
        timer = setInterval(async () => {
          try { const f = await det.detect(video); if (f.length) { close(); opts.live(f[0].rawValue); } } catch (e) {}
        }, 300);
      }
    })
    .catch(fallback);
}
