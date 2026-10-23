(() => {
  "use strict";

  const KEY_STORAGE = "chekiz.apiKey";
  const config = window.CHEKIZ_CONFIG || {};
  const apiBaseUrl = String(config.apiBaseUrl || "").replace(/\/+$/, "");

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  function getApiKey() {
    return localStorage.getItem(KEY_STORAGE) || "";
  }

  function setApiKey(value) {
    if (value) localStorage.setItem(KEY_STORAGE, value);
    else localStorage.removeItem(KEY_STORAGE);
  }

  function makeHeaders(extra = {}) {
    const headers = new Headers(extra);
    const key = getApiKey();
    if (key && !headers.has("X-API-Key")) headers.set("X-API-Key", key);
    return headers;
  }

  async function request(path, options = {}, baseUrl = apiBaseUrl) {
    if (!baseUrl) throw new ApiError("Set the API base URL in config.js.", 0);
    const { timeoutMs = 15000, ...fetchOptions } = options;
    const headers = makeHeaders(options.headers || {});
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${baseUrl}${path}`, { ...fetchOptions, headers, signal: controller.signal });
      const bodyText = await response.text();
      let body = bodyText;
      if (bodyText) {
        try {
          body = JSON.parse(bodyText);
        } catch {
          body = bodyText;
        }
      }
      if (!response.ok) {
        const detail = body && typeof body === "object" ? body.detail || body.message : body;
        const message = response.status === 401
          ? "Wrong or missing API key. Check your key in Connection settings."
          : detail || `Request failed (${response.status}).`;
        throw new ApiError(String(message), response.status);
      }
      return body;
    } catch (error) {
      if (controller.signal.aborted) {
        throw new ApiError("The Checkiz server did not respond in time. Try again.", 408);
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function jsonRequest(path, body, method = "POST") {
    return request(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function formatPeso(value) {
    if (value === null || value === undefined || value === "") return "—";
    const amount = Number(value);
    if (!Number.isFinite(amount)) return "—";
    return new Intl.NumberFormat("en-PH", {
      style: "currency",
      currency: "PHP",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(amount);
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[char]);
  }

  function statusInfo(status) {
    const statuses = {
      VERIFIED: { label: "Paid", next: "Safe to pack", short: "Paid", icon: "paid", className: "is-paid" },
      OPEN: { label: "Open", next: "Waiting for payment", short: "Open", icon: "pending", className: "is-pending" },
      PENDING_MATCH: { label: "Pending match", next: "Hold for the payment alert", short: "Pending", icon: "pending", className: "is-pending" },
      SUSPECTED_FAKE: { label: "Suspected fake", next: "Stop — do not pack", short: "Suspected fake", icon: "fake", className: "is-fake" },
      DUPLICATE: { label: "Duplicate receipt", next: "Stop — this payment was used", short: "Duplicate", icon: "duplicate", className: "is-duplicate" }
    };
    return statuses[status] || { label: "Needs review", next: "Check in your wallet app", short: "Needs review", icon: "confirm", className: "is-confirm" };
  }

  function statusIconMarkup(status, confirm = false) {
    const icon = confirm ? "confirm" : statusInfo(status).icon;
    const shapes = {
      paid: '<path d="m5 12 4 4L19 6"/>',
      pending: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/>',
      fake: '<circle cx="12" cy="12" r="8"/><path d="M12 7v5m0 3.5v.5"/>',
      duplicate: '<path d="M7 7h8a4 4 0 0 1 0 8h-1"/><path d="m10 4-3 3 3 3"/><path d="M17 17H9a4 4 0 0 1 0-8h1"/><path d="m14 20 3-3-3-3"/>',
      confirm: '<circle cx="12" cy="12" r="8"/><path d="M12 11v5m0-8h.01"/>'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${shapes[icon] || shapes.confirm}</svg>`;
  }

  function statusMarkup(status, warning = false) {
    const info = statusInfo(status);
    const isConfirm = warning && status === "VERIFIED";
    const label = isConfirm ? "Confirm in app" : info.short;
    const className = isConfirm ? "is-confirm" : info.className;
    return `<span class="status-label ${className}"><span class="status-icon">${statusIconMarkup(status, isConfirm)}</span>${label}</span>`;
  }

  function setConnection(element, state, text) {
    if (!element) return;
    element.className = `connection-state is-${state}`;
    const label = element.querySelector("span:last-child");
    if (label) label.textContent = text;
  }

  function setFeedback(element, message, kind = "") {
    if (!element) return;
    element.textContent = message || "";
    element.className = `inline-feedback${kind ? ` is-${kind}` : ""}`;
  }

  function errorText(error) {
    if (error instanceof ApiError) {
      if (error.status === 0) return error.message;
      if (error.status === 408) return "The Checkiz server did not respond in time. Try again.";
      if (error.status === 413) return "This image is too large. Choose an image under 8 MB.";
      if (error.status === 415) return "That file is not an image. Choose a PNG, JPG, or WebP receipt.";
      return error.message;
    }
    if (error instanceof TypeError) return "Could not reach the Checkiz server. Check the API address and your connection.";
    return error instanceof Error ? error.message : "Something went wrong. Please try again.";
  }

  window.Chekiz = Object.freeze({
    ApiError,
    apiBaseUrl,
    escapeHtml,
    errorText,
    formatPeso,
    getApiKey,
    jsonRequest,
    request,
    setApiKey,
    setConnection,
    setFeedback,
    statusIconMarkup,
    statusInfo,
    statusMarkup
  });
})();
