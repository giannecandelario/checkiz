function cameraCapture(onFile, options = {}) {
  const fallback = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.setAttribute("capture", "environment");
    input.addEventListener("change", () => {
      if (input.files[0]) onFile(input.files[0]);
    }, { once: true });
    input.click();
  };

  if (!navigator.mediaDevices?.getUserMedia) {
    fallback();
    return;
  }

  navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } },
    audio: false
  }).then(stream => {
    const backdrop = document.createElement("div");
    backdrop.className = "camera-dialog-backdrop";
    const dialog = document.createElement("section");
    dialog.className = "camera-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", options.title || "Use your camera");

    const heading = document.createElement("h2");
    heading.textContent = options.title || "Take a photo";
    const video = document.createElement("video");
    video.autoplay = true;
    video.playsInline = true;
    video.muted = true;
    video.srcObject = stream;

    const hint = document.createElement("p");
    hint.className = "camera-error";
    hint.textContent = options.live && "BarcodeDetector" in window
      ? "Point your camera at the QR code, or capture a photo."
      : "Frame the receipt or QR clearly, then capture.";

    const actions = document.createElement("div");
    actions.className = "camera-dialog-actions";
    const cancel = document.createElement("button");
    cancel.className = "button button-secondary";
    cancel.type = "button";
    cancel.textContent = "Cancel";
    const capture = document.createElement("button");
    capture.className = "button button-primary";
    capture.type = "button";
    capture.textContent = "Capture";
    actions.append(cancel, capture);
    dialog.append(heading, video, hint, actions);
    backdrop.append(dialog);
    document.body.append(backdrop);

    let timer = null;
    let isClosed = false;
    function onKeyDown(event) {
      if (event.key === "Escape" && !isClosed) close();
    }
    const close = () => {
      if (isClosed) return;
      isClosed = true;
      window.clearInterval(timer);
      document.removeEventListener("keydown", onKeyDown);
      stream.getTracks().forEach(track => track.stop());
      backdrop.remove();
    };
    cancel.addEventListener("click", close);
    backdrop.addEventListener("click", event => {
      if (event.target === backdrop) close();
    });
    document.addEventListener("keydown", onKeyDown);
    capture.addEventListener("click", () => {
      if (!video.videoWidth || !video.videoHeight) {
        hint.textContent = "Camera is still starting. Wait a moment, then capture.";
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext("2d");
      if (!context) {
        hint.textContent = "Could not capture from this camera. Try uploading an image instead.";
        return;
      }
      context.drawImage(video, 0, 0);
      canvas.toBlob(blob => {
        if (!blob) {
          hint.textContent = "Could not capture this image. Try again or upload a file.";
          return;
        }
        close();
        onFile(new File([blob], "camera-capture.jpg", { type: "image/jpeg" }));
      }, "image/jpeg", 0.92);
    });

    if (options.live && "BarcodeDetector" in window) {
      const detector = new BarcodeDetector({ formats: ["qr_code"] });
      timer = window.setInterval(async () => {
        try {
          const codes = await detector.detect(video);
          if (codes.length && !isClosed) {
            close();
            options.live(codes[0].rawValue);
          }
        } catch (error) {
          window.clearInterval(timer);
          timer = null;
          hint.textContent = "Could not scan live. Capture the QR image or upload a photo instead.";
        }
      }, 350);
    }
    capture.focus();
  }).catch(error => {
    console.warn("Camera unavailable; opening the device image picker.", error);
    fallback();
  });
}
