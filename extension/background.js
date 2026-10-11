/* All HTTP calls and the focus-aware review clock live in the MV3 worker. */
const DEFAULTS = {apiUrl: "http://127.0.0.1:8000", reviewer: "", batch: "", sessionId: "default", order: "priority"};
let operations = Promise.resolve();
const serial = (fn) => {
  const next = operations.then(fn, fn);
  operations = next.catch(() => {});
  return next;
};

function localUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["localhost", "127.0.0.1"].includes(url.hostname) || url.username || url.password) {
    throw new Error("Chỉ dùng địa chỉ HTTP localhost hoặc 127.0.0.1 cho API/CVAT local.");
  }
  return url;
}
async function settings() {
  return {...DEFAULTS, ...(await chrome.storage.local.get("settings")).settings};
}
async function api(path, method = "GET", body) {
  if (!/^\/(health|queue|stats|model|image\/[^/?]+(?:\/file)?|verdict)(?:\?|$)/.test(path) || path.includes("..")) {
    throw new Error("API path không được phép.");
  }
  const cfg = await settings();
  const base = localUrl(cfg.apiUrl);
  const target = new URL(path, base.origin);
  if (target.origin !== base.origin) throw new Error("API origin không hợp lệ.");
  let response;
  try {
    response = await fetch(target.href, {method, headers: {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(30000)});
  } catch {
    throw new Error("Không kết nối được API. Kiểm tra API đang chạy và địa chỉ trong Cài đặt.");
  }
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { detail = "Không đọc được phản hồi"; }
    const failure = new Error(`HTTP ${response.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
    failure.status = response.status;
    throw failure;
  }
  if (path.split("?")[0].endsWith("/file")) {
    const data = new Uint8Array(await response.arrayBuffer());
    if (data.length > 20 * 1024 * 1024) throw new Error("Ảnh lớn hơn 20 MB.");
    let text = "";
    for (let i = 0; i < data.length; i += 8192) text += String.fromCharCode(...data.subarray(i, i + 8192));
    return `data:${response.headers.get("content-type") || "image/jpeg"};base64,${btoa(text)}`;
  }
  return response.json();
}
async function state() { return (await chrome.storage.local.get("review")).review || null; }
async function persist(value) { await chrome.storage.local.set({review: value}); }
function accrue(value) {
  if (value.runningSince !== null) {
    value.elapsedMs = Math.min(86400000, value.elapsedMs + Math.max(0, Date.now() - value.runningSince));
    value.runningSince = null;
  }
}
async function refreshClock() {
  const value = await state();
  if (!value) return null;
  accrue(value);
  if (!value.pending) {
    try {
      const [tab, win] = await Promise.all([chrome.tabs.get(value.tabId), chrome.windows.get(value.windowId)]);
      // Frame changes and another focused tab pause the clock even in the same CVAT job.
      const actual = new URL(tab.url), expected = new URL(value.cvatUrl);
      const sameFrame = actual.origin === expected.origin && actual.pathname === expected.pathname &&
        actual.searchParams.get("frame") === expected.searchParams.get("frame");
      if (tab.active && win.focused && tab.status === "complete" && sameFrame) {
        value.runningSince = Date.now();
      }
    } catch { /* Closed CVAT tab: clock remains paused. */ }
  }
  await persist(value);
  return value;
}
function publicClock(value) {
  if (!value) return {active: false};
  return {active: true, imageId: value.detail.image_id, running: value.runningSince !== null,
    seconds: value.elapsedMs / 1000, pending: value.pending, detail: value.detail};
}
async function openImage(message) {
  const old = await refreshClock();
  if (old?.pending) throw new Error("Còn verdict chưa xác nhận. Thử gửi lại trước khi đổi ảnh.");
  const cfg = await settings();
  if (!cfg.reviewer.trim()) throw new Error("Điền tên reviewer trong Cài đặt trước khi review.");
  const query = new URLSearchParams({queue_id: message.queueId});
  if (cfg.batch) query.set("batch", cfg.batch);
  const detail = await api(`/image/${encodeURIComponent(message.imageId)}?${query}`);
  if (!detail.cvat_url) throw new Error("Ảnh chưa có CVAT mapping. Chạy cvat-sync cho batch demo.");
  const target = localUrl(detail.cvat_url);
  if (!/^\/tasks\/\d+\/jobs\/\d+$/.test(target.pathname) || !/^\d+$/.test(target.searchParams.get("frame"))) {
    throw new Error("CVAT URL thiếu task/job/frame hợp lệ.");
  }
  const existing = (await chrome.tabs.query({})).find(tab => {
    try { return new URL(tab.url).origin === target.origin && tab.url.includes("/tasks/"); }
    catch { return false; }
  });
  const tab = existing ? await chrome.tabs.update(existing.id, {url: target.href, active: true}) :
    await chrome.tabs.create({url: target.href, active: true});
  await chrome.windows.update(tab.windowId, {focused: true});
  await persist({tabId: tab.id, windowId: tab.windowId, cvatUrl: target.href, detail,
    reviewer: cfg.reviewer.trim(), sessionId: cfg.sessionId, order: cfg.order,
    elapsedMs: 0, runningSince: null, pending: null});
  return publicClock(await refreshClock());
}
async function saveVerdict(message) {
  const value = await refreshClock();
  if (!value) throw new Error("Chọn ảnh và mở CVAT trước khi ghi verdict.");
  if (!value.pending) {
    if (!["error", "false_alarm", "skip"].includes(message.verdict)) throw new Error("Verdict không hợp lệ.");
    accrue(value);
    const d = value.detail;
    value.pending = {request_id: crypto.randomUUID(), image_id: d.image_id, verdict: message.verdict,
      reviewer: value.reviewer, seconds_spent: value.elapsedMs / 1000, note: message.note || null,
      obj_ids: message.objIds || [], batch_id: d.batch_id, queue_id: d.queue_id,
      model_version: d.model_version, rank: d.rank, session_id: value.sessionId, review_order: value.order};
    await persist(value); // Durable retry key BEFORE network: worker suspension cannot duplicate a vote.
  }
  let result;
  try { result = await api("/verdict", "POST", value.pending); }
  catch (failure) {
    // These responses explicitly reject this immutable submission. A network/5xx
    // failure is uncertain and MUST keep the retry key.
    if ([400, 404, 409, 422].includes(failure.status)) await persist(null);
    throw failure;
  }
  if (result.status !== "saved") throw new Error("API chưa xác nhận đã lưu verdict.");
  await persist(null);
  return result;
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  serial(async () => {
    switch (message.type) {
      case "SETTINGS": return settings();
      case "SAVE_SETTINGS": {
        localUrl(message.settings.apiUrl);
        const current = await state();
        if (current?.pending) throw new Error("Gửi lại verdict đang chờ trước khi đổi cài đặt.");
        if (!["priority", "file"].includes(message.settings.order)) throw new Error("Thứ tự không hợp lệ.");
        await persist(null);
        await chrome.storage.local.set({settings: {...DEFAULTS, ...message.settings}});
        return settings();
      }
      case "API": return api(message.path, "GET");
      case "OPEN_IMAGE": return openImage(message);
      case "CLOCK": return publicClock(await refreshClock());
      case "SAVE_VERDICT": return saveVerdict(message);
      default: throw new Error("Thao tác không hỗ trợ.");
    }
  }).then(value => sendResponse({ok: true, value}), error => sendResponse({ok: false, error: error.message}));
  return true;
});
const refresh = () => serial(refreshClock).catch(() => {});
chrome.tabs.onActivated.addListener(refresh);
chrome.tabs.onUpdated.addListener(refresh);
chrome.tabs.onRemoved.addListener(refresh);
chrome.windows.onFocusChanged.addListener(refresh);
chrome.runtime.onStartup.addListener(() => serial(async () => {
  const value = await state();
  if (value) { value.runningSince = null; await persist(value); }
}));
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {});
