const $ = id => document.getElementById(id);
let cfg, items = [], selected = null, loading = false, saving = false, pending = null;
let cursor = 0, generation = 0, selectionGeneration = 0;
let savedSnapshot = null, recheckPending = null;
async function worker(message) {
  const reply = await chrome.runtime.sendMessage(message);
  if (!reply?.ok) throw new Error(reply?.error || "Service worker không phản hồi.");
  return reply.value;
}
$("open-guideline").onclick = async () => {
  $("open-guideline").disabled = true;
  try { await worker({type: "OPEN_GUIDELINE"}); error(""); }
  catch (err) { error(err.message); }
  finally { $("open-guideline").disabled = false; }
};
function error(message) { $("error").hidden = !message; $("error").textContent = message || ""; }
function reasonNode(reason) {
  const li = document.createElement("li");
  const parts = reason.split(/(\[[RV]\d+\])/g);
  for (const part of parts) {
    if (/^\[[RV]\d+\]$/.test(part)) { const strong = document.createElement("strong"); strong.textContent = part; li.append(strong); }
    else li.append(document.createTextNode(part));
  }
  return li;
}
function query(offset = 0) {
  const params = new URLSearchParams({limit: "50", offset: String(offset), reviewer: cfg.reviewer,
    session_id: cfg.sessionId, order: cfg.order});
  if (cfg.batch) params.set("batch", cfg.batch);
  return params;
}
function actions() {
  document.querySelectorAll("[data-verdict]").forEach(button => button.disabled = saving || !selected || !!pending || !!recheckPending);
  $("retry").hidden = !pending;
  $("retry").disabled = saving;
  $("read-saved").disabled = saving || !selected || !!pending || !!recheckPending;
  $("recheck").disabled = saving || !selected || !!pending || (!recheckPending && !savedSnapshot?.backend_ready);
  $("recheck").textContent = recheckPending ? "Thử kiểm tra lại" : "Kiểm tra lại lỗi";
}
function renderQueue() {
  $("queue").replaceChildren();
  for (const row of items) {
    const li = document.createElement("li"), button = document.createElement("button");
    button.className = `row${selected?.image_id === row.image_id ? " active" : ""}`;
    button.dataset.imageId = row.image_id;
    button.disabled = saving || !!pending || !!recheckPending;
    const title = document.createElement("span");
    const score = row.model_version?.startsWith("manual-unscored-")
      ? "Chưa chấm QC" : `${Number(row.risk_score).toFixed(1)} điểm`;
    title.className = "rank"; title.textContent = `#${row.rank} · ${score} · ${row.image_id}`;
    button.append(title);
    const reasons = document.createElement("ul");
    (row.reasons || []).slice(0, 3).forEach(reason => reasons.append(reasonNode(reason)));
    button.append(reasons); button.addEventListener("click", () => selectImage(row));
    li.append(button); $("queue").append(li);
  }
}
async function loadQueue(append = false) {
  if (loading) return;
  loading = true; const mine = ++generation;
  $("status").textContent = "Đang tải hàng đợi…"; error("");
  try {
    const result = await worker({type: "API", path: `/queue?${query(append ? cursor : 0)}`});
    if (mine !== generation) return;
    items = append ? [...items, ...result.items] : result.items;
    cursor = items.length;
    $("count").textContent = `${result.remaining}/${result.total} ảnh còn lại`;
    $("status").textContent = result.remaining ? `Model: ${result.model_version}` : "Hết ảnh trong phiên này.";
    $("warnings").textContent = (result.warnings || []).join(" · ");
    $("more").hidden = cursor >= result.remaining;
    renderQueue();
    await loadStats();
  } catch (err) { error(err.message); $("status").textContent = "Chưa tải được hàng đợi."; }
  finally { loading = false; }
}
async function loadStats() {
  const params = query(); params.delete("offset"); params.delete("limit");
  const result = await worker({type: "API", path: `/stats?${params}`});
  const rate = result.latest.error_rate === null ? "chưa có" : `${(100 * result.latest.error_rate).toFixed(1)}%`;
  $("stats").textContent = `${result.reviewed_images} ảnh · ${result.review_events} lượt · lỗi thật ${rate} · ${result.history.seconds_spent.toFixed(1)} giây`;
}
async function showDetail(detail) {
  selected = detail; $("selected").hidden = false;
  $("image-title").textContent = `#${detail.rank} · ${detail.image_id}`;
  $("reasons").replaceChildren(...detail.reasons.slice(0, 3).map(reasonNode));
  $("evidence").replaceChildren();
  for (const box of detail.evidence || []) {
    const li = document.createElement("li");
    const check = document.createElement("input"); check.type = "checkbox"; check.value = box.obj_id || "";
    check.style.width = "auto"; check.dataset.objId = "true";
    check.disabled = !box.obj_id;
    li.append(check, document.createTextNode(` #${box.obj_id || "?"}: ${box.note || box.signal || "Box nghi vấn"}`));
    $("evidence").append(li);
  }
  $("image").hidden = true; $("boxes").hidden = true; $("image-error").hidden = true;
  if (detail.image_available) {
    const data = await worker({type: "API", path: detail.image_url});
    if (selected?.image_id !== detail.image_id) return;
    const img = $("image");
    img.onload = () => {
      if (selected?.image_id !== detail.image_id) return;
      img.hidden = false;
      const canvas = $("boxes"); canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
      canvas.hidden = false;
      const ctx = canvas.getContext("2d"); ctx.strokeStyle = "#ff3b30"; ctx.fillStyle = "#ff3b30";
      ctx.lineWidth = Math.max(2, img.naturalWidth / 350); ctx.font = `${Math.max(14, img.naturalWidth / 70)}px sans-serif`;
      for (const evidence of detail.evidence || []) {
        const [x1, y1, x2, y2] = evidence.box;
        ctx.strokeRect(x1, y1, x2-x1, y2-y1); ctx.fillText(`#${evidence.obj_id || "?"}`, x1, Math.max(18, y1-4));
      }
    };
    img.onerror = () => { $("image-error").hidden = false; $("image-error").textContent = "Không đọc được nội dung ảnh."; };
    img.src = data;
  } else { $("image-error").hidden = false; $("image-error").textContent = "Ảnh chưa có trong images_dir; xem ảnh trong CVAT."; }
  actions(); renderQueue();
}
async function selectImage(row) {
  if (saving || pending || recheckPending) return;
  error(""); const mine = ++selectionGeneration;
  try {
    const clock = await worker({type: "OPEN_IMAGE", imageId: row.image_id, queueId: row.queue_id});
    if (mine !== selectionGeneration) return;
    pending = clock.pending; $("note").value = "";
    savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending;
    showSaved();
    await showDetail(clock.detail); await updateClock();
  } catch (err) { error(err.message); }
}
async function updateClock() {
  try {
    const clock = await worker({type: "CLOCK"});
    if (!clock.active) {
      pending = null; selected = null; savedSnapshot = null; recheckPending = null; $("selected").hidden = true; actions();
      return;
    }
    pending = clock.pending;
    savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending;
    $("timer").textContent = `${clock.seconds.toFixed(1)} giây · ${pending ? "chờ lưu verdict" : recheckPending ? "chờ kiểm tra lại" : clock.running ? "đang xem CVAT" : "tạm dừng (CVAT mất focus / đổi frame)"}`;
    actions();
  } catch (err) { error(err.message); }
}
function showSaved() {
  $("saved-labels").replaceChildren();
  if (!savedSnapshot) {
    $("saved-status").textContent = "Điểm hiện tại thuộc lần chấm trước. Đọc nhãn đã Save để kiểm tra lại.";
    return;
  }
  $("saved-status").textContent = `Đã đọc ${savedSnapshot.box_count} box được lưu trong CVAT. ${savedSnapshot.backend_ready ? "Có thể kiểm tra lại lỗi." : "Chưa có backend QC cho queue này; điểm chưa thay đổi."}`;
  for (const [index, box] of savedSnapshot.boxes.entries()) {
    const li = document.createElement("li");
    li.textContent = `Box ${index + 1} · ${box.category} · [${box.box.map(n => Number(n).toFixed(1)).join(", ")}]`;
    $("saved-labels").append(li);
  }
}
$("read-saved").addEventListener("click", async () => {
  saving = true; actions(); error("");
  try { savedSnapshot = await worker({type: "READ_SAVED"}); showSaved(); }
  catch (err) { error(err.message); }
  finally { saving = false; actions(); }
});
$("recheck").addEventListener("click", async () => {
  saving = true; actions(); renderQueue(); error("");
  try {
    const result = await worker({type: "RECHECK"});
    savedSnapshot = null; recheckPending = null;
    await showDetail(result.detail); showSaved(); await loadQueue();
    $("status").textContent = `Đã kiểm tra nhãn đã lưu: ${result.result.risk_before.toFixed(1)} → ${result.result.risk_after.toFixed(1)} điểm.`;
  } catch (err) { error(err.message); await updateClock(); }
  finally { saving = false; actions(); renderQueue(); }
});
async function submit(verdict) {
  if (saving || !selected || recheckPending) return;
  saving = true; actions(); renderQueue(); error("");
  try {
    const objIds = [...document.querySelectorAll("[data-obj-id]:checked")].map(el => el.value);
    await worker({type: "SAVE_VERDICT", verdict, note: $("note").value, objIds});
    pending = null; selected = null; $("selected").hidden = true;
    await loadQueue(); $("status").textContent = "Đã lưu verdict. Chọn ảnh tiếp theo.";
  } catch (err) { error(err.message); await updateClock(); }
  finally { saving = false; actions(); renderQueue(); }
}
$("refresh").addEventListener("click", () => loadQueue());
$("more").addEventListener("click", () => loadQueue(true));
$("retry").addEventListener("click", () => submit(pending?.verdict));
document.querySelectorAll("[data-verdict]").forEach(button => button.addEventListener("click", () => submit(button.dataset.verdict)));
document.addEventListener("keydown", event => {
  if (event.repeat || event.ctrlKey || event.altKey || event.metaKey || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) return;
  const verdict = {"1": "error", "2": "false_alarm", "3": "skip"}[event.key];
  if (verdict && selected && !saving && !pending) { event.preventDefault(); submit(verdict); }
});
$("settings-form").addEventListener("submit", async event => {
  event.preventDefault(); error("");
  try {
    cfg = await worker({type: "SAVE_SETTINGS", settings: {apiUrl: $("api-url").value.trim(), guidelineUrl: $("guideline-url").value.trim(), reviewer: $("reviewer").value.trim(),
      batch: $("batch").value.trim(), sessionId: $("session").value.trim(), order: $("order").value}});
    selected = null; pending = null; $("selected").hidden = true; $("settings").open = false;
    savedSnapshot = null; recheckPending = null;
    await loadQueue();
  } catch (err) { error(err.message); }
});
(async () => {
  try {
    cfg = await worker({type: "SETTINGS"});
    $("api-url").value = cfg.apiUrl; $("guideline-url").value = cfg.guidelineUrl; $("reviewer").value = cfg.reviewer;
    $("batch").value = cfg.batch; $("session").value = cfg.sessionId; $("order").value = cfg.order;
    $("settings").open = !cfg.reviewer;
    const clock = await worker({type: "CLOCK"});
    if (clock.active) {
      pending = clock.pending; savedSnapshot = clock.savedSnapshot; recheckPending = clock.recheckPending;
      await showDetail(clock.detail); showSaved();
    }
    await loadQueue(); await updateClock(); setInterval(updateClock, 1000);
  } catch (err) { error(err.message); }
})();
