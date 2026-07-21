const SYMBOLS = ["AAPL", "GOOG", "MSFT", "TSLA", "AMZN"];
const MAX_RECONNECT_DELAY_MS = 15000;

const state = {
  subscribed: new Set(SYMBOLS),
  ticks: {},
  candles: {},
  alerts: [],
};

let socket = null;
let reconnectDelay = 1000;

function setStatus(text, cls) {
  const el = document.getElementById("connection-status");
  el.textContent = text;
  el.className = `status ${cls}`;
}

function connectWebSocket() {
  const symbolsParam = Array.from(state.subscribed).join(",");
  const url = `${WS_URL}?symbols=${encodeURIComponent(symbolsParam)}`;
  socket = new WebSocket(url);

  socket.addEventListener("open", () => {
    setStatus("connected", "status-connected");
    reconnectDelay = 1000;
  });

  socket.addEventListener("message", (event) => {
    handleMessage(JSON.parse(event.data));
  });

  socket.addEventListener("close", () => {
    setStatus("disconnected — reconnecting…", "status-disconnected");
    setTimeout(connectWebSocket, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
  });

  socket.addEventListener("error", () => {
    socket.close();
  });
}

function sendWsMessage(payload) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload));
  }
}

function handleMessage(message) {
  if (message.topic === "ticks") {
    handleTick(message);
  } else if (message.topic === "candles") {
    handleCandle(message);
  } else if (message.topic === "alerts") {
    handleAlertEvent(message);
  } else if (message.type === "subscriptions") {
    syncCheckboxesWithServer(message.symbols);
  }
}

function handleTick(tick) {
  state.ticks[tick.symbol] = tick;
  renderTickerRow(tick.symbol);
}

function handleCandle(candle) {
  state.candles[candle.symbol] = candle;
  renderCandleRow(candle.symbol);
}

function handleAlertEvent(message) {
  if (message.event === "triggered") {
    showNotification(
      `Alert #${message.alert_id}: ${message.symbol} crossed ${message.direction} ` +
        `${message.threshold} (now $${message.price.toFixed(2)})`
    );
    refreshAlerts();
  }
}

function showNotification(text) {
  const container = document.getElementById("notifications");
  const el = document.createElement("div");
  el.className = "notification";
  el.textContent = text;
  container.prepend(el);
  setTimeout(() => el.remove(), 10000);
}

// --- Subscription checkboxes -------------------------------------------

function renderSymbolCheckboxes() {
  const container = document.getElementById("symbol-checkboxes");
  container.innerHTML = "";
  for (const symbol of SYMBOLS) {
    const label = document.createElement("label");
    label.className = "symbol-checkbox";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.subscribed.has(symbol);
    checkbox.dataset.symbol = symbol;
    checkbox.addEventListener("change", onSubscriptionToggle);

    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(" " + symbol));
    container.appendChild(label);
  }
}

function onSubscriptionToggle(event) {
  const symbol = event.target.dataset.symbol;
  if (event.target.checked) {
    state.subscribed.add(symbol);
    sendWsMessage({ action: "subscribe", symbols: [symbol] });
  } else {
    state.subscribed.delete(symbol);
    sendWsMessage({ action: "unsubscribe", symbols: [symbol] });
  }
}

function syncCheckboxesWithServer(symbols) {
  state.subscribed = new Set(symbols);
  document.querySelectorAll("#symbol-checkboxes input[type=checkbox]").forEach((checkbox) => {
    checkbox.checked = state.subscribed.has(checkbox.dataset.symbol);
  });
}

// --- Ticker table ---------------------------------------------------------

function renderTickerTable() {
  const tbody = document.getElementById("ticker-body");
  tbody.innerHTML = "";
  for (const symbol of SYMBOLS) {
    const row = document.createElement("tr");
    row.id = `ticker-row-${symbol}`;
    row.innerHTML = `
      <td>${symbol}</td>
      <td class="price">–</td>
      <td class="percent-change">–</td>
      <td class="moving-average">–</td>
      <td class="updated">–</td>
    `;
    tbody.appendChild(row);
  }
}

function renderTickerRow(symbol) {
  const tick = state.ticks[symbol];
  const row = document.getElementById(`ticker-row-${symbol}`);
  if (!tick || !row) return;

  row.querySelector(".price").textContent = tick.price.toFixed(2);

  const pct = tick.percent_change;
  const pctCell = row.querySelector(".percent-change");
  pctCell.textContent = pct === null || pct === undefined ? "–" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
  pctCell.className = "percent-change" + (pct > 0 ? " up" : pct < 0 ? " down" : "");

  row.querySelector(".moving-average").textContent = tick.moving_average.toFixed(2);
  row.querySelector(".updated").textContent = new Date(tick.occurred_at).toLocaleTimeString();
}

// --- Candles table ----------------------------------------------------------

function renderCandlesTable() {
  const tbody = document.getElementById("candles-body");
  tbody.innerHTML = "";
  for (const symbol of SYMBOLS) {
    const row = document.createElement("tr");
    row.id = `candle-row-${symbol}`;
    row.innerHTML = `
      <td>${symbol}</td>
      <td class="open">–</td>
      <td class="high">–</td>
      <td class="low">–</td>
      <td class="close">–</td>
      <td class="window">–</td>
    `;
    tbody.appendChild(row);
  }
}

function renderCandleRow(symbol) {
  const candle = state.candles[symbol];
  const row = document.getElementById(`candle-row-${symbol}`);
  if (!candle || !row) return;

  row.querySelector(".open").textContent = candle.open.toFixed(2);
  row.querySelector(".high").textContent = candle.high.toFixed(2);
  row.querySelector(".low").textContent = candle.low.toFixed(2);
  row.querySelector(".close").textContent = candle.close.toFixed(2);

  const start = new Date(candle.window_start).toLocaleTimeString();
  const end = new Date(candle.window_end).toLocaleTimeString();
  row.querySelector(".window").textContent = `${start}–${end}`;
}

// --- Alerts panel -----------------------------------------------------------

function populateAlertSymbolOptions() {
  const select = document.getElementById("alert-symbol");
  select.innerHTML = "";
  for (const symbol of SYMBOLS) {
    const option = document.createElement("option");
    option.value = symbol;
    option.textContent = symbol;
    select.appendChild(option);
  }
}

async function refreshAlerts() {
  const response = await fetch(`${API_BASE_URL}/alerts`);
  state.alerts = await response.json();
  renderAlerts();
}

function renderAlerts() {
  const tbody = document.getElementById("alerts-body");
  tbody.innerHTML = "";

  for (const alert of state.alerts) {
    const row = document.createElement("tr");
    row.className = `alert-row state-${alert.current_state}`;
    const triggeredAt = alert.triggered_at ? new Date(alert.triggered_at).toLocaleTimeString() : "–";

    row.innerHTML = `
      <td>${alert.id}</td>
      <td>${alert.symbol}</td>
      <td>${alert.direction}</td>
      <td>${alert.threshold}</td>
      <td>${alert.current_state}</td>
      <td>${triggeredAt}</td>
    `;

    const actionsCell = document.createElement("td");
    if (alert.current_state === "triggered") {
      const ackButton = document.createElement("button");
      ackButton.textContent = "Ack";
      ackButton.addEventListener("click", () => ackAlert(alert.id));
      actionsCell.appendChild(ackButton);
    }
    if (alert.current_state === "armed" || alert.current_state === "triggered") {
      const cancelButton = document.createElement("button");
      cancelButton.textContent = "Cancel";
      cancelButton.addEventListener("click", () => cancelAlert(alert.id));
      actionsCell.appendChild(cancelButton);
    }
    row.appendChild(actionsCell);

    tbody.appendChild(row);
  }
}

async function ackAlert(id) {
  await fetch(`${API_BASE_URL}/alerts/${id}/ack`, { method: "POST" });
  await refreshAlerts();
}

async function cancelAlert(id) {
  await fetch(`${API_BASE_URL}/alerts/${id}/cancel`, { method: "POST" });
  await refreshAlerts();
}

async function onAlertFormSubmit(event) {
  event.preventDefault();

  const symbol = document.getElementById("alert-symbol").value;
  const direction = document.getElementById("alert-direction").value;
  const threshold = parseFloat(document.getElementById("alert-threshold").value);
  const expiresAtLocal = document.getElementById("alert-expires-at").value;
  const ackWindowSeconds = parseInt(document.getElementById("alert-ack-window").value, 10);

  const response = await fetch(`${API_BASE_URL}/alerts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      symbol,
      direction,
      threshold,
      expires_at: new Date(expiresAtLocal).toISOString(),
      ack_window_seconds: ackWindowSeconds,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    showNotification(`Failed to create alert: ${error.detail || response.statusText}`);
    return;
  }

  event.target.reset();
  document.getElementById("alert-ack-window").value = "300";
  await refreshAlerts();
}

// --- Init ---------------------------------------------------------------

function init() {
  renderSymbolCheckboxes();
  renderTickerTable();
  renderCandlesTable();
  populateAlertSymbolOptions();
  document.getElementById("alert-form").addEventListener("submit", onAlertFormSubmit);
  refreshAlerts();
  connectWebSocket();
}

document.addEventListener("DOMContentLoaded", init);
