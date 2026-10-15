/* All HTTP calls and the focus-aware review clock live in the MV3 worker. */
const DEFAULTS = {apiUrl: "http://127.0.0.1:8000", guidelineUrl: "http://127.0.0.1:8010", reviewer: "", batch: "", sessionId: "default", order: "priority"};
let operations = Promise.resolve();
let uiOperations = Promise.resolve();
const panelFocus = new Map();
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
async function openGuideline() {
  const cfg = await settings();
  const url = localUrl(cfg.guidelineUrl);
  const tabs = await chrome.tabs.query({url: `${url.origin}/*`});
  const existing = tabs.find(tab => tab.url === url.href);
  if (existing) {
    await chrome.windows.update(existing.windowId, {focused: true});
    await chrome.tabs.update(existing.id, {active: true});
  } else await chrome.tabs.create({url: url.href});
  return {opened: true};
}
async function api(path, method = "GET", body) {
  if (!/^\/(health|queue|stats|model|image\/[^/?]+(?:\/(file|saved|recheck))?|rechecks\/[A-Za-z0-9-]+|verdict)(?:\?|$)/.test(path) || path.includes("..")) {
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
function frameNumber(url) {
  const raw = url.searchParams.get("frame");
  // CVAT's default frame is zero; the UI removes ?frame=0 after navigation.
  if (raw === null) return 0;
  if (!/^\d+$/.test(raw)) return null;
  const frame = Number(raw);
  return Number.isSafeInteger(frame) ? frame : null;
}
async function refreshClock() {
  const value = await state();
  if (!value) return null;
  accrue(value);
  if (!value.pending && !value.recheckPending) {
    try {
      const [tab, win] = await Promise.all([chrome.tabs.get(value.tabId), chrome.windows.get(value.windowId)]);
      // Frame changes and another focused tab pause the clock even in the same CVAT job.
      const actual = new URL(tab.url), expected = new URL(value.cvatUrl);
      const actualFrame = frameNumber(actual);
      const sameFrame = actual.origin === expected.origin && actual.pathname === expected.pathname &&
        actualFrame !== null && actualFrame === frameNumber(expected);
      if (tab.active && win.focused && tab.status === "complete" && sameFrame && !panelFocus.get(tab.id)) {
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
    seconds: value.elapsedMs / 1000, pending: value.pending, detail: value.detail,
    savedSnapshot: value.savedSnapshot || value.lastSavedSnapshot || null, recheckPending: value.recheckPending || null,
    lastRecheck: value.lastRecheck || null};
}
async function openImage(message, sender) {
  const old = await refreshClock();
  if (old?.pending) throw new Error("Còn verdict chưa xác nhận. Thử gửi lại trước khi đổi ảnh.");
  if (old?.recheckPending) throw new Error("Còn yêu cầu kiểm tra lại chưa xác nhận. Thử lại trước khi đổi ảnh.");
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
  const tabs = await chrome.tabs.query({});
  const compatible = tab => {
    try { return new URL(tab.url).origin === target.origin && tab.url.includes("/tasks/"); }
    catch { return false; }
  };
  const matchingJob = tab => compatible(tab) && new URL(tab.url).pathname === target.pathname;
  const existing = tabs.find(tab => tab.id === sender.tab?.id && compatible(tab)) ||
    tabs.find(tab => tab.active && matchingJob(tab)) || tabs.find(matchingJob) || tabs.find(compatible);
  const same = existing && new URL(existing.url).pathname === target.pathname && frameNumber(new URL(existing.url)) === frameNumber(target);
  const tab = existing ? await chrome.tabs.update(existing.id, {...(same ? {} : {url: target.href}), active: true}) :
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
  if (value.recheckPending) throw new Error("Xác nhận kết quả kiểm tra lại trước khi gửi verdict.");
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
async function readSaved() {
  const value = await refreshClock();
  if (!value || value.pending || value.recheckPending) throw new Error("Chọn ảnh, xử lý yêu cầu đang chờ trước khi đọc nhãn.");
  const cfg = await settings();
  const query = new URLSearchParams({queue_id: value.detail.queue_id});
  if (cfg.batch) query.set("batch", cfg.batch);
  const saved = await api(`/image/${encodeURIComponent(value.detail.image_id)}/saved?${query}`);
  value.savedSnapshot = saved;
  await persist(value);
  return saved;
}
async function recheckImage() {
  const value = await refreshClock();
  if (!value || value.pending) throw new Error("Chọn ảnh và xử lý verdict đang chờ trước khi kiểm tra lại.");
  if (!value.recheckPending) {
    if (!value.savedSnapshot?.backend_ready) throw new Error("Đọc nhãn đã Save trước; backend QC cần sẵn sàng.");
    accrue(value);
    value.recheckPending = {request_id: crypto.randomUUID(), queue_id: value.detail.queue_id,
      snapshot_id: value.savedSnapshot.snapshot_id};
    await persist(value);
  }
  let result;
  try { result = await api(`/image/${encodeURIComponent(value.detail.image_id)}/recheck`, "POST", value.recheckPending); }
  catch (failure) {
    let status;
    try { status = await api(`/rechecks/${value.recheckPending.request_id}`); }
    catch (checkFailure) {
      if (checkFailure.status === 404) { value.recheckPending = null; await persist(value); }
      throw failure;
    }
    if (status.status === "completed") result = status.result;
    else if (status.status === "failed") { value.recheckPending = null; await persist(value); throw failure; }
    else throw failure; // Running/unknown: retain the durable request ID.
  }
  const cfg = await settings();
  const query = new URLSearchParams();
  if (cfg.batch) query.set("batch", cfg.batch);
  value.detail = await api(`/image/${encodeURIComponent(value.detail.image_id)}?${query}`);
  value.lastRecheck = result;
  value.lastSavedSnapshot = {...value.savedSnapshot, backend_ready:false,
    backend_message:"Snapshot này đã được kiểm tra. Bấm nút QC để đọc nhãn mới nếu bạn sửa tiếp."};
  value.recheckPending = null; value.savedSnapshot = null;
  await persist(value);
  return {result, detail: value.detail, savedSnapshot:value.lastSavedSnapshot};
}
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return false;
  const extensionPage = sender.url?.startsWith(chrome.runtime.getURL(''));
  if (!extensionPage && !["UI_GET", "UI_SET", "PANEL_FOCUS"].includes(message.type)) return false;
  if (["UI_GET", "UI_SET"].includes(message.type)) {
    const task=uiOperations.then(async()=>{
      if(!sender.tab)throw new Error("Thiếu tab CVAT");
      const key=`qc-ui:${sender.tab.id}`;
      if(message.type==='UI_GET')return (await chrome.storage.local.get(key))[key]||{open:false,width:390};
      const value={open:message.value?.open===true,width:Math.max(300,Math.min(650,Number(message.value?.width)||390))};
      await chrome.storage.local.set({[key]:value});return value;
    });
    uiOperations=task.catch(()=>{});
    task.then(value=>sendResponse({ok:true,value}),error=>sendResponse({ok:false,error:error.message}));
    return true;
  }
  serial(async () => {
    switch (message.type) {
      case "PANEL_FOCUS": {
        if (!sender.tab) throw new Error("Thiếu tab CVAT");
        const value=await state();
        if(value?.tabId===sender.tab.id) {accrue(value);await persist(value);}
        panelFocus.set(sender.tab.id,message.focused===true);
        return publicClock(await refreshClock());
      }
      case "SETTINGS": return settings();
      case "SAVE_SETTINGS": {
        localUrl(message.settings.apiUrl);
        localUrl(message.settings.guidelineUrl ?? DEFAULTS.guidelineUrl);
        const current = await state();
        if (current?.pending || current?.recheckPending) throw new Error("Xử lý yêu cầu đang chờ trước khi đổi cài đặt.");
        if (!["priority", "file"].includes(message.settings.order)) throw new Error("Thứ tự không hợp lệ.");
        await persist(null);
        await chrome.storage.local.set({settings: {...DEFAULTS, ...message.settings}});
        return settings();
      }
      case "API": return api(message.path, "GET");
      case "OPEN_GUIDELINE": return openGuideline();
      case "OPEN_IMAGE": return openImage(message, sender);
      case "CLOCK": return publicClock(await refreshClock());
      case "SAVE_VERDICT": return saveVerdict(message);
      case "READ_SAVED": return readSaved();
      case "RECHECK": return recheckImage();
      case "RUN_QC": {
        const current=await state();
        if (!current?.recheckPending) {
          const saved=await readSaved();
          if(!saved.backend_ready) throw new Error(saved.backend_message || "Chưa có backend QC; điểm cũ được giữ.");
        }
        return recheckImage();
      }
      default: throw new Error("Thao tác không hỗ trợ.");
    }
  }).then(value => sendResponse({ok: true, value}), error => sendResponse({ok: false, error: error.message}));
  return true;
});
const refresh = () => serial(refreshClock).catch(() => {});
chrome.tabs.onActivated.addListener(refresh);
chrome.tabs.onUpdated.addListener(refresh);
chrome.tabs.onRemoved.addListener(id => {panelFocus.delete(id);chrome.storage.local.remove(`qc-ui:${id}`);refresh();});
chrome.windows.onFocusChanged.addListener(refresh);
chrome.runtime.onStartup.addListener(() => serial(async () => {
  const value = await state();
  if (value) { value.runningSince = null; await persist(value); }
}));
chrome.action.onClicked.addListener(tab => {
  if (!tab.id) return;
  chrome.tabs.sendMessage(tab.id,{type:'QC_TOGGLE'}).then(reply=>{
    if(!reply?.ok)throw new Error('Không phải job CVAT');
    chrome.action.setBadgeText({tabId:tab.id,text:''});
    chrome.action.setTitle({tabId:tab.id,title:'Mở/đóng QC'});
  }).catch(() => {
    chrome.action.setBadgeText({tabId:tab.id,text:'!'});
    chrome.action.setTitle({tabId:tab.id,title:'Mở một job CVAT rồi bấm QC; reload trang sau khi reload extension.'});
  });
});
