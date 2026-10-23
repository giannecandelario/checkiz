(() => {
  "use strict";

  const C = window.Chekiz;
  const $ = id => document.getElementById(id);
  const byStatus = status => C.statusInfo(status);
  const MAX_FILE_SIZE = 8 * 1024 * 1024;
  const refreshButton = $("refreshButton");
  const globalNotice = $("globalNotice");
  const receiptInput = $("receiptFile");
  const uploadZone = $("uploadZone");
  let selectedFile = null;
  let refreshTimer = null;

  function setNotice(message, kind = "") {
    globalNotice.hidden = !message;
    globalNotice.className = `notice${kind ? ` is-${kind}` : ""}`;
    globalNotice.textContent = message || "";
  }

  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value.replace(" ", "T") + (value.endsWith("Z") ? "" : "Z"));
    return Number.isNaN(date.getTime())
      ? String(value)
      : new Intl.DateTimeFormat("en-PH", { hour: "numeric", minute: "2-digit" }).format(date);
  }

  function setUploadError(message) {
    const error = $("uploadError");
    error.hidden = !message;
    error.textContent = message || "";
  }

  function clearFileSelection() {
    selectedFile = null;
    receiptInput.value = "";
    $("fileName").textContent = "Choose a receipt screenshot";
    $("fileHint").textContent = "or take a photo · PNG, JPG · up to 8 MB";
    uploadZone.classList.remove("has-file");
    $("verifyButton").disabled = true;
  }

  function checkFile(file) {
    if (!file) return false;
    const hasImageType = file.type ? file.type.startsWith("image/") : /\.(png|jpe?g|webp|gif|bmp|heic|heif)$/i.test(file.name);
    if (!hasImageType) {
      setUploadError("That file is not an image. Choose a PNG, JPG, or WebP receipt.");
      clearFileSelection();
      return false;
    }
    if (file.size > MAX_FILE_SIZE) {
      setUploadError("This image is too large. Choose a file under 8 MB.");
      clearFileSelection();
      return false;
    }
    selectedFile = file;
    $("fileName").textContent = file.name;
    $("fileHint").textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB · ready to check`;
    uploadZone.classList.add("has-file");
    $("verifyButton").disabled = false;
    setUploadError("");
    return true;
  }

  function showVerdictLoading() {
    const result = $("verdictResult");
    result.className = "verdict-result is-loading";
    result.innerHTML = `<span class="verdict-symbol">${C.statusIconMarkup("PENDING_MATCH")}</span><div class="verdict-copy"><strong>Checking receipt…</strong><p>Reading payment details and checking for signs of edits.</p></div>`;
    $("verdictSubhead").textContent = "Keep this screen open for the result.";
    result.scrollIntoView({ block: "nearest" });
  }

  function renderVerdict(result) {
    const info = byStatus(result.status);
    const warning = Boolean(result.warning || result.needs_app_check);
    const needsConfirm = result.status === "VERIFIED" && warning;
    const root = $("verdictResult");
    const className = needsConfirm ? "is-confirm" : info.className;
    const title = needsConfirm ? "Confirm in app before packing" : `${info.label} · ${info.next}`;
    root.className = `verdict-result ${className}`;
    root.innerHTML = `<span class="verdict-symbol">${C.statusIconMarkup(result.status, needsConfirm)}</span><div class="verdict-copy"><strong>${C.escapeHtml(title)}</strong><p>${C.escapeHtml(result.message || "")}</p></div>`;
    root.scrollIntoView({ block: "nearest" });
    $("verdictSubhead").textContent = `Order ${result.order_id ? `#${result.order_id}` : ""}`.trim();

    const fields = result.fields || {};
    const forensic = result.forensics || {};
    $("resultAmount").textContent = C.formatPeso(fields.amount);
    $("resultReference").textContent = fields.ref || "Not found";
    $("resultForensics").textContent = typeof forensic.flagged === "boolean"
      ? (forensic.flagged ? "Flagged for review" : "No edit flags")
      : "Not available";
    $("resultElapsed").textContent = Number.isFinite(Number(result.elapsed_ms))
      ? `${Math.round(Number(result.elapsed_ms))} ms`
      : "—";

    const detail = $("forensicDetail");
    const measurements = [];
    if (forensic.ela !== undefined && forensic.ela !== null) measurements.push(`ELA ${forensic.ela}`);
    if (forensic.sharpness !== undefined && forensic.sharpness !== null) measurements.push(`Sharpness ${forensic.sharpness}`);
    const notes = [];
    if (result.warning) notes.push(`Confirm in the wallet app: ${result.warning}`);
    if (measurements.length) notes.push(`Image measurements: ${measurements.join(" · ")}.`);
    if (forensic.flagged) notes.push("A forensic flag is a review signal, not proof by itself.");
    detail.textContent = notes.join(" ");
    detail.hidden = !notes.length;

    if (result.status === "VERIFIED" && !warning) setNotice("Payment matched. This order is paid and safe to pack.", "success");
    else if (result.status === "VERIFIED" && warning) setNotice("Payment matched, but confirm it in the wallet app before packing.", "warning");
    else if (result.status === "PENDING_MATCH") setNotice("Receipt looks valid, but no payment alert matches yet. Hold this order.", "warning");
    else setNotice(`${info.label}. Stop before packing this order.`, "error");
  }

  function showVerifyError(error) {
    const result = $("verdictResult");
    result.className = "verdict-result is-error";
    result.innerHTML = `<span class="verdict-symbol" aria-hidden="true">!</span><div class="verdict-copy"><strong>Could not check this receipt</strong><p>${C.escapeHtml(C.errorText(error))}</p></div>`;
    $("verdictSubhead").textContent = "No verdict was recorded.";
    $("resultAmount").textContent = "—";
    $("resultReference").textContent = "—";
    $("resultForensics").textContent = "—";
    $("resultElapsed").textContent = "—";
    $("forensicDetail").hidden = true;
    setNotice(C.errorText(error), "error");
  }

  async function verifyReceipt(event) {
    event.preventDefault();
    setUploadError("");
    const orderId = $("orderId").value.trim();
    if (!orderId) {
      setUploadError("Enter an order ID before checking the receipt.");
      $("orderId").focus();
      return;
    }
    if (!selectedFile && !checkFile(receiptInput.files[0])) {
      setUploadError("Choose or take a receipt screenshot first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("order_id", orderId);
    $("verifyButton").disabled = true;
    $("verifyButton").innerHTML = `<span aria-hidden="true">…</span> Checking…`;
    showVerdictLoading();
    setNotice("");
    try {
      const result = await C.request("/verify", { method: "POST", body: formData, timeoutMs: 30000 });
      renderVerdict(result);
      void refreshData();
    } catch (error) {
      showVerifyError(error);
    } finally {
      clearFileSelection();
      $("verifyButton").innerHTML = `<svg class="button-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m5 12 4 4L19 6"/></svg> Verify payment`;
    }
  }

  function renderOrderRow(order, paid) {
    const orderId = C.escapeHtml(order.order_id || "—");
    const amount = C.formatPeso(order.amount);
    const status = paid ? "VERIFIED" : "OPEN";
    const extra = paid && order.paid_ref
      ? `<small>Ref ${C.escapeHtml(order.paid_ref)}</small>`
      : `<small>${C.escapeHtml(order.created_at ? formatDate(order.created_at) : "Awaiting payment alert")}</small>`;
    return `<div class="order-row"><div class="order-identity"><strong>Order #${orderId}</strong>${extra}</div><span class="order-amount">${C.escapeHtml(amount)}</span>${C.statusMarkup(status)}</div>`;
  }

  function renderOrders(rows) {
    const orders = Array.isArray(rows) ? rows : [];
    const open = orders.filter(order => String(order.status).toUpperCase() === "OPEN");
    const paid = orders.filter(order => String(order.status).toUpperCase() === "PAID");
    $("openCount").textContent = String(open.length);
    $("paidCount").textContent = String(paid.length);
    $("openOrders").innerHTML = open.length
      ? open.slice(0, 5).map(order => renderOrderRow(order, false)).join("")
      : `<p class="empty-row">No open orders. Make a QR for your next buyer.</p>`;
    $("paidOrders").innerHTML = paid.length
      ? paid.slice(0, 5).map(order => renderOrderRow(order, true)).join("")
      : `<p class="empty-row">No paid QR orders yet.</p>`;
  }

  function renderPending(rows) {
    const pending = Array.isArray(rows) ? rows : [];
    $("pendingCount").textContent = String(pending.length);
    $("pendingList").innerHTML = pending.length
      ? pending.slice(0, 8).map(item => `<div class="pending-row"><div class="pending-order"><strong>Order #${C.escapeHtml(item.order_id || "—")}</strong><small>${C.escapeHtml(formatDate(item.created_at) || "Waiting for wallet alert")}</small></div><span class="pending-reference">Ref ${C.escapeHtml(item.ref || "—")}</span><span class="pending-amount">${C.escapeHtml(C.formatPeso(item.amount))}</span>${C.statusMarkup("PENDING_MATCH")}</div>`).join("")
      : `<p class="empty-row">No receipts are waiting for a payment alert.</p>`;
  }

  function renderHistory(rows) {
    const history = Array.isArray(rows) ? rows : [];
    $("historyCount").textContent = `${history.length} shown`;
    $("historyRows").innerHTML = history.length
      ? history.slice(0, 20).map(item => {
        const info = byStatus(item.status);
        const amount = C.formatPeso(item.amount);
        const elapsed = item.elapsed_ms === null || item.elapsed_ms === undefined ? "—" : `${Math.round(Number(item.elapsed_ms))} ms`;
        const message = item.message ? `<small>${C.escapeHtml(item.message)}</small>` : "";
        return `<tr><td data-label="Order">#${C.escapeHtml(item.order_id || "—")}${message}</td><td data-label="Result">${C.statusMarkup(item.status)}</td><td data-label="Reference"><span class="table-ref">${C.escapeHtml(item.ref || "—")}</span></td><td class="numeric" data-label="Amount">${C.escapeHtml(amount)}</td><td class="numeric" data-label="Time">${C.escapeHtml(elapsed)}</td></tr>`;
      }).join("")
      : `<tr><td colspan="5" class="empty-row">No receipt checks yet. The next result will appear here.</td></tr>`;
  }

  function renderStats(stats) {
    const counts = stats.by_status || {};
    $("statPaid").textContent = String(counts.VERIFIED || 0);
    $("statPending").textContent = String(counts.PENDING_MATCH || 0);
    $("statFake").textContent = String(counts.SUSPECTED_FAKE || 0);
    $("statDuplicate").textContent = String(counts.DUPLICATE || 0);
    $("statAverage").textContent = stats.avg_elapsed_ms === null || stats.avg_elapsed_ms === undefined
      ? "—"
      : `${Math.round(Number(stats.avg_elapsed_ms))} ms`;
    $("statsUpdated").textContent = `Updated ${new Intl.DateTimeFormat("en-PH", { hour: "numeric", minute: "2-digit" }).format(new Date())}`;
  }

  function renderBlockError(target, message, retryLabel) {
    const retry = `<button class="button button-quiet retry-button" type="button">${C.escapeHtml(retryLabel)}</button>`;
    if (target.id === "statsStrip") {
      ["statPaid", "statPending", "statFake", "statDuplicate", "statAverage"].forEach(id => { $(id).textContent = "—"; });
      $("statsUpdated").textContent = message;
      $("statsUpdated").insertAdjacentHTML("beforeend", ` ${retry}`);
      return;
    }
    if (target.tagName === "TBODY") {
      target.innerHTML = `<tr><td colspan="5" class="empty-row">${C.escapeHtml(message)} ${retry}</td></tr>`;
      return;
    }
    target.innerHTML = `<p class="empty-row">${C.escapeHtml(message)} ${retry}</p>`;
  }

  async function refreshData() {
    refreshButton.disabled = true;
    refreshButton.querySelector("span").textContent = "↻";
    const jobs = [
      { id: "orders", path: "/orders", render: renderOrders, target: $("openOrders") },
      { id: "pending", path: "/pending", render: renderPending, target: $("pendingList") },
      { id: "history", path: "/history", render: renderHistory, target: $("historyRows") },
      { id: "stats", path: "/stats", render: renderStats, target: $("statsStrip") }
    ];
    const outcomes = await Promise.allSettled(jobs.map(job => C.request(job.path)));
    const errors = [];
    let hasKeyError = false;
    let offline = false;
    outcomes.forEach((outcome, index) => {
      const job = jobs[index];
      if (outcome.status === "fulfilled") {
        job.render(outcome.value);
      } else {
        const error = outcome.reason;
        errors.push(error);
        hasKeyError ||= error instanceof C.ApiError && error.status === 401;
        offline ||= error instanceof TypeError;
        const text = C.errorText(error);
        renderBlockError(job.target, text, "Retry");
        job.target.querySelector(".retry-button")?.addEventListener("click", () => void refreshData(), { once: true });
      }
    });
    if (hasKeyError) {
      C.setConnection($("connectionState"), "error", "API key needed");
      setNotice("The server rejected the API key. Open Connection settings, update the key, then refresh.", "error");
      $("connectionSettings").open = true;
    } else if (offline) {
      C.setConnection($("connectionState"), "offline", "Server offline");
      setNotice("Could not reach the Checkiz server. Check that the backend is running and config.js points to it.", "error");
    } else if (errors.length) {
      C.setConnection($("connectionState"), "error", "Some data unavailable");
      if (!globalNotice.textContent) setNotice("Some payment desk data could not be loaded. Retry the affected section.", "error");
    } else {
      C.setConnection($("connectionState"), "online", "Connected");
      if (globalNotice.textContent.startsWith("Could not reach") || globalNotice.textContent.startsWith("The server rejected")) setNotice("");
    }
    refreshButton.disabled = false;
  }

  function renderAlertResult(result) {
    const match = result.resolved || result.settled;
    if (match) {
      const info = byStatus(match.status);
      if (result.needs_app_check || match.needs_app_check) {
        return `Alert added · Order #${match.order_id} matched. Confirm in the wallet app before packing.`;
      }
      return `Alert added · Order #${match.order_id}: ${info.short}.`;
    }
    return `Alert added for ${C.formatPeso(result.amount)}. No open order matched yet.`;
  }

  $("verifyForm").addEventListener("submit", verifyReceipt);
  receiptInput.addEventListener("change", () => checkFile(receiptInput.files[0]));
  uploadZone.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      receiptInput.click();
    }
  });
  ["dragenter", "dragover"].forEach(type => uploadZone.addEventListener(type, event => {
    event.preventDefault();
    uploadZone.classList.add("is-over");
  }));
  ["dragleave", "drop"].forEach(type => uploadZone.addEventListener(type, event => {
    event.preventDefault();
    uploadZone.classList.remove("is-over");
  }));
  uploadZone.addEventListener("drop", event => {
    const file = event.dataTransfer.files[0];
    if (checkFile(file)) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      receiptInput.files = transfer.files;
    }
  });

  $("cameraButton").addEventListener("click", () => {
    cameraCapture(file => {
      checkFile(file);
      if (!selectedFile) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      receiptInput.files = transfer.files;
    }, { title: "Take a receipt photo" });
  });

  $("alertForm").addEventListener("submit", async event => {
    event.preventDefault();
    const text = $("alertText").value.trim();
    if (!text) {
      $("alertText").focus();
      C.setFeedback($("alertFeedback"), "Paste a payment alert first.", "error");
      return;
    }
    const button = $("addAlertButton");
    button.disabled = true;
    button.textContent = "Adding alert…";
    C.setFeedback($("alertFeedback"), "");
    try {
      const result = await C.jsonRequest("/ledger/sms", { text, source: "paste" });
      $("alertText").value = "";
      C.setFeedback($("alertFeedback"), renderAlertResult(result), "success");
      setNotice(result.resolved || result.settled ? renderAlertResult(result) : "", result.resolved || result.settled ? "success" : "");
      await refreshData();
    } catch (error) {
      C.setFeedback($("alertFeedback"), C.errorText(error), "error");
      if (error instanceof C.ApiError && error.status === 401) {
        C.setConnection($("connectionState"), "error", "API key needed");
        $("connectionSettings").open = true;
      } else if (error instanceof TypeError) {
        C.setConnection($("connectionState"), "offline", "Server offline");
      }
    } finally {
      button.disabled = false;
      button.textContent = "Add payment alert";
    }
  });

  $("keyForm").addEventListener("submit", event => {
    event.preventDefault();
    try {
      C.setApiKey($("apiKey").value.trim());
      C.setFeedback($("keyFeedback"), "API key saved in this browser.", "success");
      setNotice("");
      void refreshData();
    } catch (error) {
      C.setFeedback($("keyFeedback"), `Could not save the key: ${C.errorText(error)}`, "error");
    }
  });
  $("clearKey").addEventListener("click", () => {
    try {
      C.setApiKey("");
      $("apiKey").value = "";
      C.setFeedback($("keyFeedback"), "Saved API key cleared from this browser.", "success");
      void refreshData();
    } catch (error) {
      C.setFeedback($("keyFeedback"), `Could not clear the key: ${C.errorText(error)}`, "error");
    }
  });
  refreshButton.addEventListener("click", () => void refreshData());

  try {
    $("apiKey").value = C.getApiKey();
  } catch (error) {
    setNotice(`Browser storage is unavailable, so the API key cannot be saved: ${C.errorText(error)}`, "error");
  }
  void refreshData();
  refreshTimer = window.setInterval(() => void refreshData(), 10000);
  window.addEventListener("pagehide", () => window.clearInterval(refreshTimer), { once: true });
})();
