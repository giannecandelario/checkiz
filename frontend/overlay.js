(() => {
  "use strict";

  const C = window.Chekiz;
  const query = new URLSearchParams(window.location.search);
  const apiOverride = query.get("api");
  const apiBase = apiOverride ? apiOverride.replace(/\/+$/, "") : C.apiBaseUrl;
  const queryKey = query.get("key");
  const card = document.getElementById("overlayCard");
  const connection = document.getElementById("overlayConnection");
  let latestId = null;
  let timeoutId = null;
  let stopped = false;

  function setConnection(message, isError = false) {
    connection.textContent = message;
    connection.classList.toggle("is-error", isError);
    connection.hidden = !isError;
  }

  function renderVerdict(result) {
    const info = C.statusInfo(result.status);
    const warning = Boolean(result.warning || result.needs_app_check);
    const isConfirm = result.status === "VERIFIED" && warning;
    const label = isConfirm ? "Confirm in app before packing" : `${info.label} · ${info.next}`;
    card.dataset.status = isConfirm ? "CONFIRM" : result.status;
    document.getElementById("overlaySymbol").innerHTML = C.statusIconMarkup(result.status, isConfirm);
    document.getElementById("overlayStatusLabel").textContent = isConfirm ? "Confirm in your wallet" : info.label;
    document.getElementById("overlayTitle").textContent = `Order #${result.order_id || "—"} · ${label}`;
    document.getElementById("overlayMessage").textContent = result.message || info.next;
    const order = document.getElementById("overlayOrder");
    order.textContent = result.amount === null || result.amount === undefined ? "" : C.formatPeso(result.amount);
    order.hidden = !order.textContent;
    const warningNode = document.getElementById("overlayWarning");
    warningNode.textContent = warning
      ? `Confirm in the GCash or Maya app before packing. ${result.warning || ""}`.trim()
      : "";
    warningNode.hidden = !warning;
  }

  async function poll() {
    if (stopped) return;
    try {
      const headers = queryKey ? { "X-API-Key": queryKey } : {};
      const rows = await C.request("/history?limit=1", { headers }, apiBase);
      if (!Array.isArray(rows)) throw new Error("The history endpoint returned an unexpected response.");
      const [result] = rows;
      if (result) {
        const identity = result.id ?? `${result.order_id}:${result.status}:${result.created_at || ""}`;
        if (identity !== latestId) {
          latestId = identity;
          renderVerdict(result);
        }
        setConnection(`Connected · refreshed ${new Intl.DateTimeFormat("en-PH", { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(new Date())}`);
      } else {
        setConnection("Connected · waiting for the first receipt check");
      }
    } catch (error) {
      setConnection(C.errorText(error), true);
      if (error instanceof C.ApiError && error.status === 401) {
        document.getElementById("overlayTitle").textContent = "API key required";
        document.getElementById("overlayMessage").textContent = "Add a valid key with ?key=… or save it in the payment desk.";
      } else if (!latestId) {
        document.getElementById("overlayTitle").textContent = "Waiting for the payment desk";
        document.getElementById("overlayMessage").textContent = C.errorText(error);
      }
    } finally {
      if (!stopped) timeoutId = window.setTimeout(poll, 2500);
    }
  }

  window.addEventListener("pagehide", () => {
    stopped = true;
    window.clearTimeout(timeoutId);
  }, { once: true });
  void poll();
})();
