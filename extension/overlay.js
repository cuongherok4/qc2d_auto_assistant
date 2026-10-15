/* Tô màu box evidence ngay trên canvas CVAT: đỏ = chắc chắn lỗi, vàng = cần review.
   Chỉ vẽ lớp SVG không bắt chuột; không sửa nhãn hay object của CVAT. */
(() => {
  if (globalThis.m13Overlay) return;
  const NS = 'http://www.w3.org/2000/svg';
  const COLORS = {error: '#ff1f1f', review: '#ffd000'};
  const PENDING = 'm13-qc-focus';
  let detail = null, focused = null;

  const set = (node, attrs) => { for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v)); return node; };
  function frameNow() {
    const value = Number(document.querySelector('.cvat-player-frame-selector input')?.value);
    if (Number.isInteger(value)) return value;
    const raw = new URLSearchParams(location.search).get('frame');
    return raw === null ? 0 : Number(raw);
  }
  const onTarget = () => Boolean(detail?.cvat) &&
    location.pathname.replace(/\/$/, '') === `/tasks/${detail.cvat.task_id}/jobs/${detail.cvat.job_id}` &&
    frameNow() === detail.cvat.frame;
  // Shapes của CVAT dùng toạ độ ảnh cộng một offset; góc trên-trái ảnh nền cho đúng offset đó.
  function geometry(svg) {
    const bg = document.getElementById('cvat_canvas_background'), ctm = svg.getScreenCTM();
    if (!bg || !ctm) return null;
    const rect = bg.getBoundingClientRect(), point = svg.createSVGPoint();
    point.x = rect.left; point.y = rect.top;
    const origin = point.matrixTransform(ctm.inverse());
    const scale = Math.hypot(ctm.a, ctm.b);
    return Number.isFinite(origin.x) && scale > 0 ? {x: origin.x, y: origin.y, scale} : null;
  }

  function render() {
    const svg = document.getElementById('cvat_canvas_content');
    let layer = document.getElementById('m13-qc-layer');
    if (!svg || !onTarget()) { layer?.remove(); return; }
    const g = geometry(svg);
    if (!g) return;
    const key = [detail.queue_id, detail.image_id, g.x.toFixed(1), g.y.toFixed(1), g.scale.toFixed(4), focused].join('|');
    if (layer && layer.dataset.key === key && svg.lastElementChild === layer) return;
    if (!layer) layer = set(document.createElementNS(NS, 'g'), {id: 'm13-qc-layer', 'pointer-events': 'none'});
    layer.dataset.key = key;
    layer.replaceChildren();
    const px = n => n / g.scale;
    (detail.evidence || []).forEach((ev, i) => {
      const [x1, y1, x2, y2] = ev.box, color = COLORS[ev.severity] || COLORS.review, hi = i === focused;
      const x = x1 + g.x, y = y1 + g.y;
      layer.append(set(document.createElementNS(NS, 'rect'), {
        x, y, width: x2 - x1, height: y2 - y1, fill: color, 'fill-opacity': hi ? 0.22 : 0,
        stroke: color, 'stroke-width': px(hi ? 6 : 3),
        // Box nét đứt: dự đoán của model, không có object tương ứng trong CVAT.
        'stroke-dasharray': ev.obj_id == null ? `${px(9)} ${px(5)}` : 'none',
      }));
      const tag = set(document.createElementNS(NS, 'text'), {
        x: x + px(2), y: y - px(4), fill: color, 'font-size': px(hi ? 18 : 14), 'font-weight': 700,
        'font-family': 'system-ui, sans-serif', stroke: '#000', 'stroke-width': px(3), 'paint-order': 'stroke',
      });
      tag.textContent = String(i + 1);
      layer.append(tag);
    });
    svg.append(layer);
  }

  // Chọn sẵn object CVAT trùng box nhãn: CVAT kích hoạt object khi rê chuột vào dòng sidebar.
  function activate(ev) {
    const svg = document.getElementById('cvat_canvas_content'), g = svg && geometry(svg);
    if (!g || ev.obj_id == null) return;
    const [x1, y1, x2, y2] = ev.box, near = (a, b) => Math.abs(a - b) < 2;
    for (const shape of svg.querySelectorAll('rect.cvat_canvas_shape')) {
      const sx = Number(shape.getAttribute('x')) - g.x, sy = Number(shape.getAttribute('y')) - g.y;
      if (near(sx, x1) && near(sy, y1) && near(sx + Number(shape.getAttribute('width')), x2) &&
          near(sy + Number(shape.getAttribute('height')), y2)) {
        const item = document.getElementById(`cvat-objects-sidebar-state-item-${shape.getAttribute('clientID')}`);
        item?.scrollIntoView({block: 'center'});
        item?.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        return;
      }
    }
  }

  function focus(index) {
    if (!detail?.evidence?.[index]) return;
    focused = index;
    if (!onTarget()) {
      // Đang ở frame khác: mở lại đúng frame, chọn box sau khi CVAT tải xong.
      try { sessionStorage.setItem(PENDING, JSON.stringify({image: detail.image_id, index})); } catch { /* chỉ mất bước tự chọn */ }
      if (detail.cvat_url) location.href = detail.cvat_url;
      return;
    }
    render();
    activate(detail.evidence[index]);
  }

  function load(value) {
    const next = value?.detail || null;
    if (next?.image_id !== detail?.image_id) focused = null;
    detail = next;
    render();
  }
  chrome.storage.local.get('review').then(v => {
    load(v.review);
    let pending = null;
    try { pending = JSON.parse(sessionStorage.getItem(PENDING) || 'null'); sessionStorage.removeItem(PENDING); } catch { /* bỏ qua */ }
    if (pending && pending.image === detail?.image_id) {
      // CVAT cần thời gian dựng canvas sau khi tải trang.
      const started = Date.now();
      const wait = setInterval(() => {
        if (onTarget() && document.querySelector('#cvat_canvas_content rect.cvat_canvas_shape')) {
          clearInterval(wait); focus(pending.index);
        } else if (Date.now() - started > 15000) clearInterval(wait);
      }, 300);
    }
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.review) load(changes.review.newValue);
  });
  // CVAT dựng lại canvas khi đổi frame/zoom; vẽ lại khi khoá (frame, zoom, box chọn) đổi.
  setInterval(render, 400);
  globalThis.m13Overlay = {focus};
})();
