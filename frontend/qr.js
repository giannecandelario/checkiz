(() => {
  "use strict";

  const C = window.Chekiz;
  const $ = id => document.getElementById(id);
  const MAX_FILE_SIZE = 8 * 1024 * 1024;
  const sellerFile = $("sellerQrFile");
  let sellerRegistered = false;

  function setNotice(message, kind = "") {
    const notice = $("qrNotice");
    notice.hidden = !message;
    notice.className = `notice${kind ? ` is-${kind}` : ""}`;
    notice.textContent = message || "";
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value.replace(" ", "T") + (value.endsWith("Z") ? "" : "Z"));
    return Number.isNaN(date.getTime())
      ? String(value)
      : new Intl.DateTimeFormat("en-PH", { hour: "numeric", minute: "2-digit" }).format(date);
  }

  function validateImage(file) {
    if (!file) return false;
    const imageType = file.type ? file.type.startsWith("image/") : /\.(png|jpe?g|webp|gif|bmp|heic|heif)$/i.test(file.name);
    if (!imageType) {
      C.setFeedback($("sellerFeedback"), "That file is not an image. Choose a photo of your QR Ph.", "error");
      return false;
    }
    if (file.size > MAX_FILE_SIZE) {
      C.setFeedback($("sellerFeedback"), "This image is too large. Choose a file under 8 MB.", "error");
      return false;
    }
    return true;
  }

  function renderSeller(result) {
    const root = $("sellerStatus");
    if (!result.registered || !result.info) {
      sellerRegistered = false;
      root.innerHTML = `<span class="seller-info">No receive-money QR registered yet.</span>`;
      $("generateButton").disabled = true;
      return;
    }
    sellerRegistered = true;
    const name = result.info.merchant_name || "Wallet QR";
    const city = result.info.merchant_city ? ` · ${result.info.merchant_city}` : "";
    root.innerHTML = `<span class="seller-registered"><span class="status-icon is-paid">${C.statusIconMarkup("VERIFIED")}</span><strong>QR registered</strong><span class="seller-info">${C.escapeHtml(name + city)}</span></span>`;
    $("generateButton").disabled = false;
  }

  async function loadSeller() {
    try {
      const result = await C.request("/qr/seller");
      renderSeller(result);
      C.setConnection($("connectionState"), "online", "Connected");
    } catch (error) {
      $("sellerStatus").textContent = C.errorText(error);
      $("generateButton").disabled = true;
      setNotice(C.errorText(error), "error");
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else {
        C.setConnection($("connectionState"), "offline", "Server unavailable");
      }
    }
  }

  async function registerPayload(payload) {
    if (!payload) {
      C.setFeedback($("sellerFeedback"), "No QR code found. Try a closer, flatter photo.", "error");
      return;
    }
    C.setFeedback($("sellerFeedback"), "Checking this QR Ph…");
    try {
      const result = await C.jsonRequest("/qr/register", { payload });
      renderSeller(result);
      C.setFeedback($("sellerFeedback"), "Wallet QR registered on this Checkiz server.", "success");
      setNotice("Your receive-money QR is ready for new orders.", "success");
      await loadOrders();
    } catch (error) {
      C.setFeedback($("sellerFeedback"), C.errorText(error), "error");
      setNotice(C.errorText(error), "error");
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else if (error instanceof TypeError) {
        C.setConnection($("connectionState"), "offline", "Server unavailable");
      }
    }
  }

  async function decodeImage(file) {
    if (!validateImage(file)) return;
    C.setFeedback($("sellerFeedback"), "Reading QR code…");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await C.request("/qr/decode", { method: "POST", body: formData });
      if (!result.payload) throw new C.ApiError(result.message || "No QR code found. Retake the photo closer and flatter.", 400);
      await registerPayload(result.payload);
    } catch (error) {
      C.setFeedback($("sellerFeedback"), C.errorText(error), "error");
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else if (error instanceof TypeError) {
        C.setConnection($("connectionState"), "offline", "Server unavailable");
      }
    } finally {
      sellerFile.value = "";
    }
  }

  function appendQrOutput(result) {
    const output = $("qrOutput");
    output.replaceChildren();
    const wrapper = document.createElement("div");
    wrapper.className = "generated-qr";
    const image = document.createElement("img");
    image.alt = `QR Ph payment code for order ${result.order_id}`;
    image.src = result.png;
    const title = document.createElement("strong");
    title.textContent = `Order #${result.order_id} · ${C.formatPeso(result.amount)}`;
    const note = document.createElement("p");
    note.textContent = "Ask the buyer to pay this exact amount. The QR image is generated for this order.";
    const download = document.createElement("a");
    download.className = "button button-secondary qr-download";
    download.href = result.png;
    download.download = `order-${String(result.order_id).replace(/[^a-z0-9_-]/gi, "-")}.png`;
    download.textContent = "Download QR PNG";
    wrapper.append(image, title, note, download);
    output.append(wrapper);
  }

  async function generateOrder(event) {
    event.preventDefault();
    const orderId = $("qrOrderId").value.trim();
    const amount = Number($("qrAmount").value);
    const errorNode = $("generateError");
    errorNode.hidden = true;
    if (!orderId) {
      errorNode.textContent = "Enter an order ID.";
      errorNode.hidden = false;
      $("qrOrderId").focus();
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0 || amount > 1000000) {
      errorNode.textContent = "Enter an amount greater than ₱0.00 and no more than ₱1,000,000.00.";
      errorNode.hidden = false;
      $("qrAmount").focus();
      return;
    }
    const button = $("generateButton");
    button.disabled = true;
    button.textContent = "Making order QR…";
    try {
      const result = await C.jsonRequest("/qr/generate", {
        order_id: orderId,
        amount,
        centavo_code: $("centavoCode").checked
      });
      if (typeof result.png !== "string" || !result.png.startsWith("data:image/png;base64,")) {
        throw new Error("The server returned an invalid QR image.");
      }
      appendQrOutput(result);
      setNotice(`QR ready for Order #${result.order_id} at ${C.formatPeso(result.amount)}.`, "success");
      await loadOrders();
    } catch (error) {
      errorNode.textContent = C.errorText(error);
      errorNode.hidden = false;
      setNotice(C.errorText(error), "error");
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else if (error instanceof TypeError) {
        C.setConnection($("connectionState"), "offline", "Server unavailable");
      }
    } finally {
      button.disabled = !sellerRegistered;
      button.textContent = "Generate order QR";
    }
  }

  async function loadOrders() {
    const root = $("qrOrders");
    try {
      const orders = await C.request("/orders");
      const rows = Array.isArray(orders) ? orders : [];
      root.innerHTML = rows.length
        ? rows.slice(0, 12).map(order => {
          const status = String(order.status).toUpperCase() === "PAID" ? "VERIFIED" : "OPEN";
          const note = order.paid_ref ? `Ref ${C.escapeHtml(order.paid_ref)}` : (order.created_at ? C.escapeHtml(formatDate(order.created_at)) : "Awaiting payment");
          return `<div class="qr-order-row"><div class="qr-order-identity"><strong>Order #${C.escapeHtml(order.order_id || "—")}</strong><small>${note}</small></div><span class="pending-amount">${C.escapeHtml(C.formatPeso(order.amount))}</span>${C.statusMarkup(status)}</div>`;
        }).join("")
        : `<p class="empty-row">No QR orders yet. Register your wallet QR, then make an order QR.</p>`;
      C.setConnection($("connectionState"), "online", "Connected");
    } catch (error) {
      root.innerHTML = `<p class="empty-row">${C.escapeHtml(C.errorText(error))}</p>`;
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else {
        C.setConnection($("connectionState"), "offline", "Server unavailable");
      }
    }
  }

  $("scanSellerQr").addEventListener("click", () => {
    cameraCapture(
      file => void decodeImage(file),
      { title: "Scan your receive-money QR", live: payload => void registerPayload(payload) }
    );
  });
  sellerFile.addEventListener("change", () => {
    if (sellerFile.files[0]) void decodeImage(sellerFile.files[0]);
  });
  $("generateForm").addEventListener("submit", generateOrder);
  $("refreshQrOrders").addEventListener("click", () => void loadOrders());
  $("keyForm").addEventListener("submit", event => {
    event.preventDefault();
    try {
      C.setApiKey($("apiKey").value.trim());
      C.setFeedback($("keyFeedback"), "API key saved in this browser.", "success");
      setNotice("");
      void loadSeller();
      void loadOrders();
    } catch (error) {
      C.setFeedback($("keyFeedback"), `Could not save the key: ${C.errorText(error)}`, "error");
    }
  });
  $("clearKey").addEventListener("click", () => {
    try {
      C.setApiKey("");
      $("apiKey").value = "";
      C.setFeedback($("keyFeedback"), "Saved API key cleared from this browser.", "success");
      void loadSeller();
      void loadOrders();
    } catch (error) {
      C.setFeedback($("keyFeedback"), `Could not clear the key: ${C.errorText(error)}`, "error");
    }
  });

  try {
    $("apiKey").value = C.getApiKey();
  } catch (error) {
    setNotice(`Browser storage is unavailable, so the API key cannot be saved: ${C.errorText(error)}`, "error");
  }
  void loadSeller();
  void loadOrders();
})();
