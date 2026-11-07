/* AI 短剧画布 · 前端（零依赖） */
(() => {
  const S = { k: 1, x: 80, y: 60, nodes: [], edges: [], sel: null, seq: 0,
              conn: null, drag: null, pan: null };
  let DIRTY = false, LAST_SAVE = 0;
  const $ = (s) => document.querySelector(s);
  const canvasEl = $('#canvas'), nodesEl = $('#nodes'), edgesEl = $('#edges'),
        viewport = $('#viewport'), insp = $('#inspector'), inspBody = $('#inspBody'),
        inspTitle = $('#inspTitle'), menu = $('#menu');

  const RES = ['360P', '416P', '480P', '540P', '720P'];
  const ASPECT = ['9:16', '16:9', '1:1', '3:4', '4:3'];
  const PRESET_NAME = { draft: '草稿 360P/4步', standard: '标准 480P/8步', fine: '精细 720P/8步' };
  let PROFILES = [];

  const uid = () => 'n' + (++S.seq);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  /* ---------------- model ---------------- */
  function newNode(type, x, y) {
    const n = { id: uid(), type, x, y, w: type === 'script' ? 300 : 300, data: {} };
    if (type === 'video') {
      n.data = { prompt: '', seconds: 5, preset: 'standard', resolution: '480P',
                 aspect: '9:16', width: 720, height: 1280, steps: 8,
                 seed: Math.floor(Math.random() * 1e6),
                 turbo: true, jobId: null, file: null, status: '' };
    } else if (type === 'script') {
      n.data = { text: '', shots: 4 };
    } else if (type === 'director') {
      n.data = { idea: '', format: 'ultrashort', shots: 6, seconds: 5, units: 4, minutes: 3,
                 style: '电影感写实风格', provider: '', storyboard: null,
                 outline: null, expanded: null, status: '' };
      n.w = 460;
    } else if (type === 'image') {
      n.data = { prompt: '', mode: 'single', aspect: '9:16', engine: 'sdxl',
                 seed: Math.floor(Math.random() * 1e6), jobId: null, file: null, status: '' };
    } else {
      n.data = { text: '' };
    }
    S.nodes.push(n);
    return n;
  }

  function nodeById(id) { return S.nodes.find((n) => n.id === id); }

  /** 删除一个节点及其连线 */
  function removeNode(id) {
    if (!id) return;
    S.nodes = S.nodes.filter((x) => x.id !== id);
    S.edges = S.edges.filter((e) => e.from !== id && e.to !== id);
    if (S.sel === id) S.sel = null;
    render();
    if (!S.sel) $('#inspector').classList.add('hidden');
  }

  /** 复制一个节点（含参数） */
  function duplicateNode(id) {
    const src = nodeById(id);
    if (!src) return;
    const copy = newNode(src.type, src.x + 50, src.y + 50);
    copy.data = JSON.parse(JSON.stringify(src.data));
    copy.data.jobId = null;
    copy.data.status = '已复制';
    render();
    focusNode(copy);
    openInspector(copy);
  }

  /* ---------------- view ---------------- */
  function applyView() {
    canvasEl.style.transform = `translate(${S.x}px, ${S.y}px) scale(${S.k})`;
    $('#zoomLabel').textContent = Math.round(S.k * 100) + '%';
  }
  function screenToWorld(cx, cy) {
    const r = viewport.getBoundingClientRect();
    return { x: (cx - r.left - S.x) / S.k, y: (cy - r.top - S.y) / S.k };
  }
  function fit() {
    if (!S.nodes.length) { S.k = 1; S.x = 80; S.y = 60; applyView(); return; }
    const xs = S.nodes.map((n) => n.x), ys = S.nodes.map((n) => n.y);
    const x0 = Math.min(...xs) - 60, y0 = Math.min(...ys) - 60;
    const x1 = Math.max(...S.nodes.map((n) => n.x + n.w)) + 60;
    const y1 = Math.max(...S.nodes.map((n) => n.y + 380)) + 60;
    const r = viewport.getBoundingClientRect();
    S.k = clamp(Math.min(r.width / (x1 - x0), r.height / (y1 - y0)), 0.2, 1.2);
    S.x = (r.width - (x1 - x0) * S.k) / 2 - x0 * S.k;
    S.y = (r.height - (y1 - y0) * S.k) / 2 - y0 * S.k;
    applyView();
  }

  /* ---------------- render ---------------- */
  const TYPE_NAME = { director: '导演 · 剧本', script: '脚本', video: '视频 · H3', text: '文本', image: '图片', audio: '音频' };
  const IMG_MODES = { single: '单图', turnaround: '角色三视图', grid4: '四宫格', grid9: '九宫格' };

  function nodeHTML(n) {
    let body = '';
    if (n.type === 'director') {
      const sb = n.data.storyboard;
      const ol = n.data.outline;
      const ex = n.data.expanded || null;
      const fmts = [['ultrashort', '超短片'], ['short', '短片'], ['feature', '长片'], ['series', '剧集']];
      const fmt = n.data.format || 'ultrashort';
      const long = fmt === 'feature' || fmt === 'series';
      const fmtRow = long
        ? `<span class="lbl">${fmt === 'series' ? '集数' : '序列数'}</span>
           <input data-f="units" type="number" min="1" max="12" value="${n.data.units || 4}" style="width:92px">
           <span class="lbl">每${fmt === 'series' ? '集' : '段'}分钟</span>
           <input data-f="minutes" type="number" min="1" max="45" value="${n.data.minutes || 3}" style="width:92px">`
        : `<span class="lbl">镜头</span>
           <input data-f="shots" type="number" min="1" max="12" value="${n.data.shots}" style="width:92px">
           <span class="lbl">时长</span>
           <input data-f="seconds" type="number" min="2" max="10" value="${n.data.seconds}" style="width:92px">`;
      // 长片/剧集：每个单元内还要控制「镜数」和「单镜秒数」
      const unitRow = long
        ? `<div class="row">
             <span class="lbl">每${fmt === 'series' ? '集' : '段'}镜头</span>
             <input data-f="shots" type="number" min="1" max="24" value="${n.data.shots}" style="width:92px">
             <span class="lbl">单镜秒数</span>
             <input data-f="seconds" type="number" min="2" max="10" value="${n.data.seconds}" style="width:92px">
           </div>`
        : '';

      const outlineHTML = ol ? `
        <div class="sd-head"><b>${esc(ol.title || '')}</b>
          <div class="sd-log">${esc(ol.logline || '')}</div></div>
        ${(ol.units || []).map((u, ui) => `
          <div class="sd-shot">
            <div class="sd-meta">${fmt === 'series' ? '第 ' + u.index + ' 集' : '序列 ' + u.index} · ${esc(u.title || '')}</div>
            <div class="sd-log">${esc(u.logline || '')}</div>
            <div class="row" style="margin-top:6px">
              <button class="btn" data-act="expand" data-unit="${ui}">
                ${ex && ex.index === ui ? '重新展开' : '展开本' + (fmt === 'series' ? '集' : '段')}</button>
            </div>
            ${ex && ex.index === ui ? (ex.shots || []).map((s, i) => `
              <div class="sd-shot" style="margin-top:6px">
                <div class="sd-meta">#${s.index} ${esc(s.beat || '')} · ${esc(s.shot_size || '')} · ${esc(s.camera || '')} · ${s.duration_sec || ''}s</div>
                <textarea data-f="unitShot" data-idx="${i}" rows="2">${esc(s.action || '')}</textarea>
              </div>`).join('') : ''}
          </div>`).join('')}` : '';

      body = `
        <textarea data-f="idea" rows="3" placeholder="一句话创意：雨夜，外卖员敲开一扇门，开门的是十年后的自己">${esc(n.data.idea)}</textarea>
        <div class="row">
          <select data-f="format">${fmts.map(([k, v]) =>
            `<option value="${k}" ${k === fmt ? 'selected' : ''}>${v}</option>`).join('')}</select>
          ${fmtRow}
        </div>
        ${unitRow}
        <div class="row">
          <button class="btn primary" data-act="${long ? 'outline' : 'script'}">
            ${long ? (ol ? '重新生成大纲' : '生成大纲') : (sb ? '重新生成' : '生成剧本')}</button>
          ${long
            ? `<button class="btn" data-act="splitunit" ${ex ? '' : 'disabled'}>本${fmt === 'series' ? '集' : '段'}拆成视频</button>`
            : `<button class="btn" data-act="tosplit" ${sb ? '' : 'disabled'}>拆成视频节点</button>`}
        </div>
        <div class="status ${n.data.statusClass || ''}">${esc(n.data.status || '')}</div>
        ${long ? outlineHTML : (sb ? `<div class="sd-head"><b>${esc(sb.title || '')}</b>
                 <div class="sd-log">${esc(sb.logline || '')}</div></div>
               ${(sb.shots || []).map((s, i) => `
                 <div class="sd-shot">
                   <div class="sd-meta">#${s.index} ${esc(s.beat || '')} · ${esc(s.shot_size || '')} · ${esc(s.camera || '')} · ${s.duration_sec || ''}s</div>
                   <textarea data-f="shotAction" data-idx="${i}" rows="2">${esc(s.action || '')}</textarea>
                   ${s.dialogue ? `<div class="sd-line">「${esc(s.dialogue)}」</div>` : ''}
                 </div>`).join('')}` : '')}`;
    } else if (n.type === 'script') {
      body = `
        <textarea data-f="text" rows="5" placeholder="写一句创意，或粘贴剧本。例如：雨夜，外卖员敲开一扇门，发现开门的是十年后的自己。">${esc(n.data.text)}</textarea>
        <div class="row">
          <span class="lbl">镜头数</span>
          <input data-f="shots" type="number" min="1" max="24" value="${n.data.shots}" style="width:92px">
          <button class="btn primary" data-act="split">拆成分镜</button>
        </div>`;
    } else if (n.type === 'video') {
      const imgs = S.nodes.filter((x) => x.type === 'image' && x.data.file)
        .map((x) => x.data.file.filename);
      const cur = n.data.image || '';
      body = `
        <textarea data-f="prompt" rows="5" placeholder="镜头描述：机位 / 景别 / 人物 / 动作 / 光线 / 声音">${esc(n.data.prompt)}</textarea>
        <div class="row">
          <span class="lbl">首帧</span>
          <select data-f="image">
            <option value="">无（纯文生视频）</option>
            ${imgs.map((f) => `<option value="${esc(f)}" ${f === cur ? 'selected' : ''}>${esc(f)}</option>`).join('')}
          </select>
          <select data-f="refMode" title="有图时怎么用这张图">
            <option value="i2va" ${(n.data.refMode || 'i2va') === 'i2va' ? 'selected' : ''}>当首帧</option>
            <option value="ref2va" ${n.data.refMode === 'ref2va' ? 'selected' : ''}>参考图锁角色</option>
          </select>
        </div>
        <div class="row">
          <span class="lbl">模型</span>
          <select data-f="profile">
            <option value="">默认（H3）</option>
            ${PROFILES.filter((p) => p.kind !== 'image').map((p) =>
              `<option value="${p.id}" ${p.id === n.data.profile ? 'selected' : ''}>${esc(p.name)}${p.ready ? '' : '（缺模型）'}</option>`).join('')}
          </select>
        </div>
        <div class="row">
          <span class="lbl">时长</span>
          <input data-f="seconds" type="number" min="2" max="15" step="1" value="${n.data.seconds}" style="width:92px">
          <select data-f="preset">${Object.keys(PRESET_NAME).map((k) =>
            `<option value="${k}" ${k === (n.data.preset || 'standard') ? 'selected' : ''}>${PRESET_NAME[k]}</option>`).join('')}</select>
        </div>
        <div class="row">
          <span class="lbl">比例</span>
          <select data-f="aspect">${ASPECT.map((r) => `<option ${r === n.data.aspect ? 'selected' : ''}>${r}</option>`).join('')}</select>
          <span class="lbl">种子</span>
          <input data-f="seed" type="number" value="${n.data.seed}" style="width:120px">
          <button class="btn primary" data-act="gen">生成</button>
        </div>
        <div class="status ${n.data.statusClass || ''}">${esc(n.data.status || '')}</div>
        ${n.data.file ? `<video class="preview" controls src="/api/media?filename=${encodeURIComponent(n.data.file.filename)}&subfolder=${encodeURIComponent(n.data.file.subfolder || '')}"></video>` : ''}`;
    } else if (n.type === 'image') {
      const grid = n.data.mode === 'grid9' ? 9 : n.data.mode === 'grid4' ? 4 : 0;
      body = `
        <textarea data-f="prompt" rows="4" placeholder="描述主体与风格（英文效果最好）：young woman, red coat, rainy neon street, cinematic">${esc(n.data.prompt)}</textarea>
        <div class="row">
          <select data-f="mode">${Object.entries(IMG_MODES).map(([k, v]) =>
            `<option value="${k}" ${k === (n.data.mode || 'single') ? 'selected' : ''}>${v}</option>`).join('')}</select>
          <select data-f="profile">
            <option value="">默认（SDXL）</option>
            ${PROFILES.filter((p) => p.kind === 'image').map((p) => `<option value="${p.id}" ${p.id === n.data.profile ? 'selected' : ''}>${esc(p.name)}${p.ready ? '' : '（缺模型）'}</option>`).join('')}
          </select>
          <select data-f="engine">
            <option value="sdxl" ${(n.data.engine || 'sdxl') === 'sdxl' ? 'selected' : ''}>SDXL</option>
            <option value="i2i" ${n.data.engine === 'i2i' ? 'selected' : ''}>图生图</option>
          </select>
          <select data-f="aspect">${ASPECT.map((r) => `<option ${r === n.data.aspect ? 'selected' : ''}>${r}</option>`).join('')}</select>
          <button class="btn primary" data-act="gen">生成</button>
        </div>
        <div class="status ${n.data.statusClass || ''}">${esc(n.data.status || '')}</div>
        ${n.data.file ? `<img class="preview" src="/api/media?filename=${encodeURIComponent(n.data.file.filename)}&subfolder=${encodeURIComponent(n.data.file.subfolder || '')}">` : ''}
        ${n.data.file ? `<button class="btn" data-act="subject">存为主体（锁脸）</button>` : ''}
        ${n.data.file && grid ? `<button class="btn" data-act="slice">切分成 ${grid} 张分镜</button>` : ''}
        ${n.data.file ? `<div class="row">
            <span class="lbl">切成</span>
            <input data-f="sliceRows" type="number" min="1" max="9" value="${n.data.sliceRows || 1}" style="width:92px">
            <span class="lbl">行</span>
            <input data-f="sliceCols" type="number" min="1" max="9" value="${n.data.sliceCols || 5}" style="width:92px">
            <span class="lbl">列</span>
            <button class="btn" data-act="slicecustom">切分</button>
          </div>` : ''}
        ${n.data.board ? `<button class="btn primary" data-act="tovideo">全部分镜转视频</button>` : ''}`;
    } else {
      body = `<textarea data-f="text" rows="4" placeholder="素材文本">${esc(n.data.text)}</textarea>`;
    }
    return `
      <div class="node-head">
        <span>${TYPE_NAME[n.type] || n.type}</span>
        <span class="tag">#${n.id}</span>
      </div>
      <div class="node-body">${body}</div>
      ${n.type !== 'text' ? '<div class="port in" data-port="in"></div>' : ''}
      <div class="port out" data-port="out"></div>`;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function render() {
    nodesEl.innerHTML = '';
    for (const n of S.nodes) {
      const el = document.createElement('div');
      el.className = 'node' + ((S.sel === n.id || (S.multi && S.multi.has(n.id))) ? ' sel' : '');
      el.dataset.id = n.id;
      el.style.left = n.x + 'px';
      el.style.top = n.y + 'px';
      el.style.width = n.w + 'px';
      el.innerHTML = nodeHTML(n);
      nodesEl.appendChild(el);
    }
    drawEdges();
    markDirty();
  }

  function portPos(nodeEl, which) {
    const p = nodeEl.querySelector(`.port.${which}`);
    const n = nodeById(nodeEl.dataset.id);
    if (!p || !n) return null;
    return { x: n.x + (which === 'out' ? n.w : 0), y: n.y + nodeEl.offsetHeight / 2 };
  }

  function drawEdges(temp) {
    let w = 1, h = 1;
    for (const n of S.nodes) { w = Math.max(w, n.x + n.w + 400); h = Math.max(h, n.y + 800); }
    edgesEl.setAttribute('width', w);
    edgesEl.setAttribute('height', h);
    let html = '';
    for (const e of S.edges) {
      const a = nodeEl(e.from), b = nodeEl(e.to);
      if (!a || !b) continue;
      const p1 = portPos(a, 'out'), p2 = portPos(b, 'in');
      if (!p1 || !p2) continue;
      html += `<path d="${bezier(p1, p2)}"/>`;
    }
    if (temp) html += `<path class="hot" d="${bezier(temp.a, temp.b)}"/>`;
    edgesEl.innerHTML = html;
  }
  function nodeEl(id) { return nodesEl.querySelector(`.node[data-id="${id}"]`); }

  /** 把某个节点摆到视口中央（新增节点时用，避免建到看不见的地方） */
  function focusNode(n) {
    const r = viewport.getBoundingClientRect();
    const el = nodeEl(n.id);
    const h = (el && el.offsetHeight) || 360;
    S.x = r.width / 2 - (n.x + n.w / 2) * S.k;
    S.y = r.height / 2 - (n.y + h / 2) * S.k;
    applyView();
    drawEdges();
  }
  function bezier(a, b) {
    const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
    return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
  }

  /* ---------------- inspector ---------------- */
  function openInspector(n) {
    S.sel = n.id;
    insp.classList.remove('hidden');
    inspTitle.textContent = TYPE_NAME[n.type] + ' #' + n.id;
    inspBody.innerHTML = `
      <div class="lbl">坐标</div>
      <div class="row"><input value="${Math.round(n.x)}" disabled><input value="${Math.round(n.y)}" disabled></div>
      <div class="lbl">内容</div>
      <textarea rows="10" disabled>${esc(n.data.prompt || n.data.text || '')}</textarea>
      <div class="lbl">提示</div>
      <div class="muted" style="font-size:12px;color:#8b93a3">
        视频节点走本地 MiniMax-H3：一次只跑一个任务，排队执行。
        360P 是最快的草稿档，满意后再用更高分辨率重跑。
      </div>
      <button class="btn" id="inspDel">删除节点</button>`;
    $('#inspDel').onclick = () => { removeNode(n.id); closeInspector(); };
    render();
  }
  function closeInspector() { insp.classList.add('hidden'); S.sel = null; render(); }
  $('#inspClose').onclick = closeInspector;

  /* ---------------- interaction ---------------- */
  const mqEl = document.createElement('div');
  mqEl.id = 'marquee';
  mqEl.style.display = 'none';
  document.body.appendChild(mqEl);

  function mqPaint() {
    const a = S.mq;
    const x = Math.min(a.x0, a.x1), y = Math.min(a.y0, a.y1);
    const w = Math.abs(a.x1 - a.x0), h = Math.abs(a.y1 - a.y0);
    mqEl.style.display = 'block';
    mqEl.style.left = x + 'px';
    mqEl.style.top = y + 'px';
    mqEl.style.width = w + 'px';
    mqEl.style.height = h + 'px';
  }

  function toast(text) {
    let t = document.getElementById('toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'toast';
      document.body.appendChild(t);
    }
    t.textContent = text;
    t.classList.add('show');
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('show'), 2400);
  }

  function mqFinish() {
    mqEl.style.display = 'none';
    if (!S.mq) return;
    const a = screenToWorld(Math.min(S.mq.x0, S.mq.x1), Math.min(S.mq.y0, S.mq.y1));
    const b = screenToWorld(Math.max(S.mq.x0, S.mq.x1), Math.max(S.mq.y0, S.mq.y1));
    S.multi = S.multi || new Set();
    if (!S.additive) S.multi.clear();
    for (const n of S.nodes) {
      const hit = !(n.x > b.x || n.x + n.w < a.x || n.y > b.y || n.y + n.h < a.y);
      if (hit) S.multi.add(n.id);
    }
    S.mq = null;
    S.sel = null;
    render();
    if (S.multi.size) toast(`已选中 ${S.multi.size} 个节点 · 按 Delete 删除`);
  }

  viewport.addEventListener('mousedown', (e) => {
    if (e.target.closest('.node') || e.target.closest('#inspector')) return;
    if (e.button !== 0 && e.button !== 1) return;
    S.additive = e.shiftKey || e.ctrlKey;
    S.pan = { sx: e.clientX, sy: e.clientY, ox: S.x, oy: S.y };
    viewport.classList.add('panning');
    menu.classList.add('hidden');
    // 长按空白（260ms 内基本不动）→ 进入框选
    clearTimeout(S.mqTimer);
    if (e.button === 0) {
      S.mqTimer = setTimeout(() => {
        if (!S.pan) return;
        S.pan = null;
        viewport.classList.remove('panning');
        S.mq = { x0: e.clientX, y0: e.clientY, x1: e.clientX, y1: e.clientY };
        mqPaint();
      }, 260);
    }
  });

  window.addEventListener('mousemove', (e) => {
    if (S.mq) {
      S.mq.x1 = e.clientX;
      S.mq.y1 = e.clientY;
      mqPaint();
      return;
    }
    if (S.pan) {
      if (Math.abs(e.clientX - S.pan.sx) + Math.abs(e.clientY - S.pan.sy) > 8) clearTimeout(S.mqTimer);
      S.x = S.pan.ox + (e.clientX - S.pan.sx);
      S.y = S.pan.oy + (e.clientY - S.pan.sy);
      applyView();
      return;
    }
    if (S.drag) {
      const n = nodeById(S.drag.id);
      if (!n) return;
      const p = screenToWorld(e.clientX, e.clientY);
      n.x = p.x - S.drag.dx;
      n.y = p.y - S.drag.dy;
      nodeEl(n.id).style.left = n.x + 'px';
      nodeEl(n.id).style.top = n.y + 'px';
      drawEdges();
      return;
    }
    if (S.conn) {
      const p = screenToWorld(e.clientX, e.clientY);
      drawEdges({ a: S.conn.start, b: p });
    }
  });

  window.addEventListener('mouseup', (e) => {
    clearTimeout(S.mqTimer);
    if (S.mq) { mqFinish(); return; }
    if (S.pan) { S.pan = null; viewport.classList.remove('panning'); }
    S.drag = null;
    if (S.conn) {
      const t = e.target.closest('.port.in');
      if (t) {
        const to = t.closest('.node').dataset.id;
        if (to !== S.conn.from && !S.edges.some((x) => x.from === S.conn.from && x.to === to)) {
          S.edges.push({ from: S.conn.from, to });
        }
      }
      S.conn = null;
      render();
    }
  });

  nodesEl.addEventListener('mousedown', (e) => {
    const nodeElm = e.target.closest('.node');
    if (!nodeElm) return;
    const n = nodeById(nodeElm.dataset.id);
    if (!n) return;

    if (e.target.classList.contains('port')) {
      if (e.target.dataset.port === 'out') {
        const p = screenToWorld(e.clientX, e.clientY);
        S.conn = { from: n.id, start: portPos(nodeElm, 'out') || p };
        e.preventDefault();
      }
      return;
    }
    if (e.target.closest('.node-head')) {
      const p = screenToWorld(e.clientX, e.clientY);
      S.drag = { id: n.id, dx: p.x - n.x, dy: p.y - n.y };
      S.sel = n.id;
      openInspector(n);
    }
  });

  nodesEl.addEventListener('input', (e) => {
    const nodeElm = e.target.closest('.node');
    if (!nodeElm) return;
    const n = nodeById(nodeElm.dataset.id);
    const f = e.target.dataset.f;
    if (!n || !f) return;
    if (f === 'shotAction') {
      const i = Number(e.target.dataset.idx);
      const shot = n.data.storyboard && n.data.storyboard.shots[i];
      if (shot) {
        shot.action = e.target.value;
        delete shot.h3_prompt;   // 改过就重新生成提示词
      }
      return;
    }
    if (f === 'unitShot') {
      const i = Number(e.target.dataset.idx);
      const shot = n.data.expanded && n.data.expanded.shots[i];
      if (shot) {
        shot.action = e.target.value;
        delete shot.h3_prompt;
      }
      return;
    }
    n.data[f] = e.target.type === 'number' ? Number(e.target.value) : e.target.value;
    // 切换格式/模式要重绘，参数区才会跟着变
    if (f === 'format' || f === 'mode' || f === 'engine') repaint(n);
  });

  nodesEl.addEventListener('click', (e) => {
    const act = e.target.dataset.act;
    if (!act) return;
    const n = nodeById(e.target.closest('.node').dataset.id);
    if (!n) return;
    if (act === 'gen') generate(n);
    if (act === 'split') splitScript(n);
    if (act === 'slice') sliceGrid(n);
    if (act === 'slicecustom') sliceCustom(n);
    if (act === 'subject') setSubject(n);
    if (act === 'tovideo') panelsToVideo(n);
    if (act === 'script') generateScript(n);
    if (act === 'tosplit') splitDirector(n);
    if (act === 'outline') generateOutline(n);
    if (act === 'expand') expandUnit(n, Number(e.target.dataset.unit));
    if (act === 'splitunit') splitUnit(n);
  });

  /* 导演节点：生成剧本 / 逐镜改写 / 拆成视频节点 */
  async function generateScript(n) {
    n.data.status = '生成中…';
    n.data.statusClass = '';
    repaint(n);
    try {
      const r = await fetch('/api/director/script', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: n.data.idea, format: n.data.format || 'ultrashort',
          shots: Number(n.data.shots) || 6, seconds: Number(n.data.seconds) || 5,
          style: n.data.style || '电影感写实风格', llm: getLLM(),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '生成失败');
      n.data.storyboard = j.storyboard;
      n.data.provider = j.provider;
      n.data.status = j.provider === 'prompt-only'
        ? '模板分镜（未填 key，点 🔑 可用真编剧）'
        : '已由 ' + j.provider + ' 生成';
      n.data.statusClass = 'ok';
    } catch (e) {
      n.data.status = String(e.message || e);
      n.data.statusClass = 'err';
    }
    repaint(n);
  }

  function splitDirector(n) {
    const sb = n.data.storyboard;
    if (!sb || !sb.shots || !sb.shots.length) return;
    sb.shots.forEach((s, i) => {
      const v = newNode('video', n.x + n.w + 110, n.y + i * 360);
      v.data.seconds = Math.round(s.duration_sec || 5);
      v.data.preset = 'draft';
      v.data.prompt = s.h3_prompt || s.action || '';
      S.edges.push({ from: n.id, to: v.id });
    });
    render();
    fit();
  }

  /* ---- 长片 / 剧集：先大纲，后按单元展开 ---- */
  async function generateOutline(n) {
    n.data.status = '生成大纲…';
    n.data.statusClass = '';
    repaint(n);
    try {
      const r = await fetch('/api/director/outline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: n.data.idea, format: n.data.format || 'series',
          units: Number(n.data.units) || 4, minutes: Number(n.data.minutes) || 3,
          llm: getLLM(),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '生成失败');
      n.data.outline = j.outline;
      n.data.expanded = null;
      n.data.status = j.provider === 'prompt-only'
        ? '占位大纲（未填 key，点 🔑 可用真编剧）' : '大纲已由 ' + j.provider + ' 生成';
      n.data.statusClass = 'ok';
    } catch (e) {
      n.data.status = String(e.message || e);
      n.data.statusClass = 'err';
    }
    repaint(n);
  }

  async function expandUnit(n, ui) {
    const u = (n.data.outline && n.data.outline.units || [])[ui];
    if (!u) return;
    n.data.status = '展开本单元…';
    n.data.statusClass = '';
    repaint(n);
    try {
      const r = await fetch('/api/director/expand', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: n.data.idea, unit: u, format: n.data.format || 'series',
          shots: Number(n.data.shots) || 6, seconds: Number(n.data.seconds) || 5,
          llm: getLLM(),
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '展开失败');
      n.data.expanded = { index: ui, shots: j.storyboard.shots };
      n.data.status = '已展开：' + (u.title || '') + ' · ' + j.provider;
      n.data.statusClass = 'ok';
    } catch (e) {
      n.data.status = String(e.message || e);
      n.data.statusClass = 'err';
    }
    repaint(n);
  }

  function splitUnit(n) {
    const ex = n.data.expanded;
    if (!ex || !ex.shots) return;
    ex.shots.forEach((s, i) => {
      const v = newNode('video', n.x + n.w + 110, n.y + i * 360);
      v.data.seconds = Math.round(s.duration_sec || 5);
      v.data.preset = 'draft';
      v.data.prompt = s.h3_prompt || s.action || '';
      S.edges.push({ from: n.id, to: v.id });
    });
    render();
    fit();
  }

  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    const before = screenToWorld(e.clientX, e.clientY);
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    S.k = clamp(S.k * factor, 0.15, 2.5);
    const after = screenToWorld(e.clientX, e.clientY);
    S.x += (after.x - before.x) * S.k;
    S.y += (after.y - before.y) * S.k;
    applyView();
    drawEdges();
  }, { passive: false });

  function openMenuAt(clientX, clientY) {
    const w = 260, h = 260;
    const x = Math.min(clientX, window.innerWidth - w - 12);
    const y = Math.min(clientY, window.innerHeight - h - 12);
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.classList.remove('hidden');
    const p = screenToWorld(clientX, clientY);
    menu.dataset.wx = p.x;
    menu.dataset.wy = p.y;
  }

  viewport.addEventListener('dblclick', (e) => {
    if (e.target.closest('.node')) return;
    openMenuAt(e.clientX, e.clientY);
  });

  // 右键：空白处=新建节点；节点上=删除/复制
  viewport.addEventListener('contextmenu', (e) => {
    const el = e.target.closest('.node');
    if (!el) {
      e.preventDefault();
      openMenuAt(e.clientX, e.clientY);
      return;
    }
    e.preventDefault();
    const id = el.dataset.id;
    S.sel = id;
    render();
    const nm = $('#nodeMenu');
    nm.dataset.id = id;
    nm.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    nm.style.top = Math.min(e.clientY, window.innerHeight - 140) + 'px';
    nm.classList.remove('hidden');
  });

  $('#nodeMenu').addEventListener('click', (e) => {
    const it = e.target.closest('.menu-item');
    if (!it) return;
    const id = $('#nodeMenu').dataset.id;
    $('#nodeMenu').classList.add('hidden');
    if (it.dataset.nodeAct === 'delete') removeNode(id);
    if (it.dataset.nodeAct === 'duplicate') duplicateNode(id);
  });

  menu.addEventListener('click', (e) => {
    const it = e.target.closest('.menu-item');
    if (!it || it.hasAttribute('disabled')) return;
    const n = newNode(it.dataset.type, Number(menu.dataset.wx), Number(menu.dataset.wy));
    menu.classList.add('hidden');
    render();
    focusNode(n);
    openInspector(n);
  });

  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('#menu') && !e.target.closest('#viewport')) menu.classList.add('hidden');
    if (!e.target.closest('#nodeMenu')) $('#nodeMenu').classList.add('hidden');
  });

  /* 键盘：Delete / Backspace 删除（支持多选）；Ctrl+A 全选；Esc 取消选择 */
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
    const del = e.key === 'Delete' || e.key === 'Backspace';
    if (e.key === 'Escape') {
      S.multi = new Set();
      S.sel = null;
      render();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault();
      S.multi = new Set(S.nodes.map((n) => n.id));
      S.sel = null;
      render();
      toast(`已全选 ${S.multi.size} 个节点 · 按 Delete 删除`);
      return;
    }
    if (del && S.multi && S.multi.size) {
      e.preventDefault();
      const ids = [...S.multi];
      ids.forEach((id) => removeNode(id));
      S.multi.clear();
      S.sel = null;
      $('#inspector').classList.add('hidden');
      render();
      toast(`已删除 ${ids.length} 个节点`);
      return;
    }
    if (!S.sel) return;
    if (del || e.key === 'Enter') {
      e.preventDefault();
      const id = S.sel;
      removeNode(id);
      $('#inspector').classList.add('hidden');
    }
  });

  // 点节点正文也能选中（原来只有拖标题栏才算选中）
  nodesEl.addEventListener('mousedown', (e) => {
    const el = e.target.closest('.node');
    if (!el) return;
    if (e.target.closest('input, textarea, select, button')) return;
    S.sel = el.dataset.id;
    render();
  });

  /* ---------------- actions ---------------- */
  function splitScript(n) {
    const raw = (n.data.text || '').trim();
    if (!raw) { alert('先写点东西'); return; }
    let parts = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    if (parts.length < 2) {
      parts = raw.split(/(?<=[。！？!?])/).map((s) => s.trim()).filter(Boolean);
    }
    const want = clamp(Number(n.data.shots) || 4, 1, 24);
    if (parts.length > want) {
      const per = Math.ceil(parts.length / want);
      const merged = [];
      for (let i = 0; i < parts.length; i += per) merged.push(parts.slice(i, i + per).join(' '));
      parts = merged;
    }
    while (parts.length < want) parts.push(parts[parts.length - 1] || '');
    parts.slice(0, want).forEach((p, i) => {
      const v = newNode('video', n.x + n.w + 80, n.y + i * 300);
      v.data.prompt = p;
      v.data.seconds = 5;
      S.edges.push({ from: n.id, to: v.id });
    });
    render();
    fit();
  }

  async function generate(n) {
    const btns = nodesEl.querySelectorAll('.node[data-id="' + n.id + '"] [data-act="gen"]');
    btns.forEach((b) => (b.disabled = true));
    n.data.status = '排队中…';
    n.data.statusClass = '';
    repaint(n);
    try {
      const isImage = n.type === 'image';
      const grid = n.data.mode === 'grid4' ? 4 : n.data.mode === 'grid9' ? 9 : 0;
      const url = grid ? '/api/image/storyboard' : (isImage ? '/api/image/render' : '/api/render');
      const r = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(grid ? {
          prompt: n.data.prompt, panels: grid, aspect: n.data.aspect, seed: n.data.seed,
        } : isImage ? {
          prompt: n.data.prompt, mode: n.data.mode || 'single',
          aspect: n.data.aspect, seed: n.data.seed,
          engine: n.data.engine || 'sdxl',
          profile: n.data.profile || undefined,
          ref: (S.subject && S.subject.filename) || undefined,
          llm: getLLM(),
        } : {
          prompt: n.data.prompt, seconds: n.data.seconds,
          preset: n.data.preset || 'standard',
          aspect: n.data.aspect, width: n.data.width, height: n.data.height,
          seed: n.data.seed, turbo: n.data.turbo,
          profile: n.data.profile || undefined,
          image: n.data.image || undefined,
          ref_mode: n.data.refMode === 'ref2va',
          subject: S.subjectDesc || undefined,
        }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '提交失败');
      n.data.jobId = j.id;
      poll(n);
    } catch (err) {
      n.data.status = String(err.message || err);
      n.data.statusClass = 'err';
      btns.forEach((b) => (b.disabled = false));
      repaint(n);
    }
  }

  async function poll(n) {
    const el = () => nodesEl.querySelector('.node[data-id="' + n.id + '"] .status');
    const tick = async () => {
      try {
        const r = await fetch('/api/job/' + n.data.jobId);
        const j = await r.json();
        if (j.status === 'queued') n.data.status = '排队中…';
        else if (j.status === 'running') {
          const s = Math.round((Date.now() / 1000) - (j.started || Date.now() / 1000));
          n.data.status = '生成中… ' + (s > 0 ? s + 's' : '');
        } else if (j.status === 'done') {
          n.data.file = (j.files && j.files[0]) || null;
          n.data.status = '完成 · ' + Math.round(j.elapsed) + 's';
          n.data.statusClass = 'ok';
          if (j.kind === 'storyboard' && j.files && j.files.length > 1) {
            j.files.slice(1).forEach((f, i) => {
              const img = newNode('image', n.x + n.w + 100, n.y + i * 320);
              img.data.file = f;
              img.data.mode = 'single';
              img.data.status = '分镜 ' + (i + 1);
              img.data.statusClass = 'ok';
              S.edges.push({ from: n.id, to: img.id });
            });
            n.data.status = '分镜 ' + (j.files.length - 1) + ' 张 · ' + Math.round(j.elapsed) + 's';
            n.data.board = true;
          }
          repaint(n);
          return;
        } else if (j.status === 'error') {
          n.data.status = '失败：' + (j.error || '').slice(0, 300);
          n.data.statusClass = 'err';
          repaint(n);
          return;
        }
        const s = el();
        if (s) { s.textContent = n.data.status; s.className = 'status'; }
        setTimeout(tick, 2000);
      } catch (err) {
        n.data.status = '轮询失败：' + err.message;
        repaint(n);
      }
    };
    tick();
  }

  function setSubject(n) {
    if (!n.data.file) return;
    S.subject = { filename: n.data.file.filename, subfolder: n.data.file.subfolder || '' };
    localStorage.setItem('studio.subject', JSON.stringify(S.subject));
    renderSubjectChip();
    n.data.status = '已设为主体参考';
    n.data.statusClass = 'ok';
    repaint(n);
  }

  function renderSubjectChip() {
    let chip = $('#subjectChip');
    if (!S.subject) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement('div');
      chip.id = 'subjectChip';
      chip.style.cssText = 'display:flex;align-items:center;gap:6px;margin-left:12px;font-size:11px;color:#8b93a3';
      $('.tools').prepend(chip);
    }
    chip.innerHTML = `<img src="/api/media?filename=${encodeURIComponent(S.subject.filename)}&subfolder=${encodeURIComponent(S.subject.subfolder)}"
      style="width:26px;height:26px;object-fit:cover;border-radius:6px;border:1px solid #3d4657">
      <span>主体锁定中</span><button class="btn ghost" style="padding:2px 6px" id="subjectClear">✕</button>`;
    $('#subjectClear').onclick = () => {
      S.subject = null;
      localStorage.removeItem('studio.subject');
      renderSubjectChip();
    };
  }

  function panelsToVideo(n) {
    const kids = S.edges.filter((e) => e.from === n.id)
      .map((e) => nodeById(e.to))
      .filter((k) => k && k.type === 'image' && k.data.file);
    if (!kids.length) { alert('这张联络表下面还没有分镜节点'); return; }
    const made = [];
    kids.forEach((k) => {
      const v = newNode('video', k.x + k.w + 100, k.y);
      v.data.prompt = (k.data.prompt || n.data.prompt || '') + ', cinematic camera, subtle motion';
      v.data.image = k.data.file.filename;
      v.data.seconds = 5;
      v.data.preset = 'draft';
      S.edges.push({ from: k.id, to: v.id });
      made.push(v);
    });
    render();
    fit();
    made.forEach((v) => generate(v));
  }

  async function sliceCustom(n) {
    if (!n.data.file) return;
    const rows = clamp(Number(n.data.sliceRows) || 1, 1, 9);
    const cols = clamp(Number(n.data.sliceCols) || 5, 1, 9);
    n.data.status = `切分 ${rows}×${cols}…`;
    n.data.statusClass = '';
    repaint(n);
    try {
      const r = await fetch('/api/image/slice', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: n.data.file.filename, rows, cols }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '切分失败');
      j.files.forEach((f, i) => {
        const img = newNode('image', n.x + n.w + 100, n.y + i * 340);
        img.data.file = f;
        img.data.mode = 'single';
        img.data.status = `第 ${f.row} 行 第 ${f.col} 列`;
        img.data.statusClass = 'ok';
        S.edges.push({ from: n.id, to: img.id });
      });
      n.data.status = `已切分 ${j.count} 张`;
      n.data.statusClass = 'ok';
      render();
      fit();
    } catch (e) {
      n.data.status = String(e.message || e);
      n.data.statusClass = 'err';
      repaint(n);
    }
  }

  async function sliceGrid(n) {
    if (!n.data.file) return;
    n.data.status = '切分中…';
    n.data.statusClass = '';
    repaint(n);
    try {
      const rows = n.data.mode === 'grid9' ? 3 : 2;
      const r = await fetch('/api/image/slice', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: n.data.file.filename, rows, cols: rows }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '切分失败');
      j.files.forEach((f, i) => {
        const img = newNode('image', n.x + n.w + 90, n.y + i * 320);
        img.data.file = f;
        img.data.mode = 'single';
        img.data.status = `第 ${f.row} 行 第 ${f.col} 列`;
        img.data.statusClass = 'ok';
        S.edges.push({ from: n.id, to: img.id });
      });
      n.data.status = `已切分 ${j.count} 张`;
      n.data.statusClass = 'ok';
      render();
      fit();
    } catch (e) {
      n.data.status = String(e.message || e);
      n.data.statusClass = 'err';
      repaint(n);
    }
  }

  function repaint(n) {
    const old = nodeEl(n.id);
    if (!old) return;
    const el = document.createElement('div');
    el.className = 'node' + ((S.sel === n.id || (S.multi && S.multi.has(n.id))) ? ' sel' : '');
    el.dataset.id = n.id;
    el.style.cssText = old.style.cssText;
    el.innerHTML = nodeHTML(n);
    old.replaceWith(el);
    drawEdges();
  }

  /* ---------------- agent：一句话成片 ---------------- */
  let AG = null;
  const STAGE = { queued: '排队中', story: '写剧本', render: '逐镜渲染',
                  concat: '拼接成片', done: '完成', error: '出错' };

  function agItemHTML(it) {
    const st = it.status === 'done' ? '✓ ' + Math.round(it.elapsed || 0) + 's'
      : it.status === 'running' ? '渲染中…'
      : it.status === 'error' ? '失败' : '等待';
    return `<div class="ag-item ${it.status}">
      <span class="idx">${it.index}</span>
      <span class="beat">${esc(it.beat || '')}</span>
      <span class="st">${st}</span>
    </div>`;
  }

  async function startAgent() {
    const idea = $('#agIdea').value.trim();
    if (!idea) { $('#agIdea').focus(); return; }
    const shots = Number($('#agShots').value);
    const btn = $('#agGo');
    btn.disabled = true; btn.textContent = '导演中…';
    $('#agPanel').classList.remove('hidden');
    $('#agFinal').classList.add('hidden');
    $('#agList').innerHTML = '';
    $('#agTitle').textContent = '剧本创作中…';
    $('#agStage').textContent = '';
    try {
      const r = await fetch('/api/agent/start', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, shots, preset: $('#agPreset').value,
                               use_skill: $('#agSkill').checked,
                               format: $('#agFormat').value,
                               llm: getLLM() }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || '启动失败');
      AG = { id: j.id, scriptId: null, nodes: {} };
      const c = screenToWorld(window.innerWidth / 2, 220);
      const s = newNode('script', c.x - 150, c.y);
      s.data.text = idea;
      s.data.shots = shots;
      AG.scriptId = s.id;
      render();
      fit();
      pollAgent();
    } catch (e) {
      $('#agTitle').textContent = '启动失败';
      $('#agStage').textContent = String(e.message || e);
      btn.disabled = false; btn.textContent = '一句话成片';
    }
  }

  async function pollAgent() {
    if (!AG) return;
    let j;
    try {
      j = await (await fetch('/api/agent/job/' + AG.id)).json();
    } catch { setTimeout(pollAgent, 3000); return; }

    if (j.plan) {
      $('#agTitle').textContent = j.plan.title || '成片中';
      const sNode = nodeById(AG.scriptId);
      if (sNode) { sNode.data.text = j.plan.logline || sNode.data.text; }
    }
    $('#agStage').textContent = STAGE[j.stage] || j.stage || '';
    $('#agList').innerHTML = (j.items || []).map(agItemHTML).join('');

    const script = nodeById(AG.scriptId);
    (j.items || []).forEach((it) => {
      let id = AG.nodes[it.index];
      if (!id) {
        const v = newNode('video', (script ? script.x + script.w + 90 : it.index * 340),
                          (script ? script.y : 120) + (it.index - 1) * 350);
        v.data.prompt = it.prompt;
        v.data.seconds = Math.round(it.seconds || 5);
        v.data.preset = $('#agPreset').value || 'standard';
        id = v.id;
        AG.nodes[it.index] = id;
        if (script) S.edges.push({ from: script.id, to: v.id });
        render();
      }
      const n = nodeById(id);
      if (!n) return;
      const changed = n.data.status !== it.status;
      n.data.status = it.status === 'done' ? '完成 · ' + Math.round(it.elapsed || 0) + 's'
        : it.status === 'error' ? '失败：' + (it.error || '').slice(0, 160)
        : it.status === 'running' ? '渲染中…' : '排队中…';
      n.data.statusClass = it.status === 'done' ? 'ok' : it.status === 'error' ? 'err' : '';
      if (it.file && (!n.data.file || n.data.file.filename !== it.file.filename)) {
        n.data.file = it.file;
        repaint(n);
      } else if (changed) {
        repaint(n);
      }
    });

    if (j.final) {
      const v = $('#agFinal');
      v.classList.remove('hidden');
      v.src = '/api/media?filename=' + encodeURIComponent(j.final.filename);
    }
    if (j.stage === 'done' || j.stage === 'error') {
      const btn = $('#agGo');
      btn.disabled = false; btn.textContent = '一句话成片';
      if (j.stage === 'error') $('#agStage').textContent = '出错：' + (j.error || '').slice(0, 120);
      fit();
      return;
    }
    setTimeout(pollAgent, 2500);
  }

  $('#agGo').onclick = startAgent;
  $('#agIdea').addEventListener('keydown', (e) => { if (e.key === 'Enter') startAgent(); });
  $('#agClose').onclick = () => { $('#agPanel').classList.add('hidden'); };

  /* ---------------- status / save ---------------- */
  async function loadProfiles() {
    try {
      const j = await (await fetch('/api/profiles')).json();
      PROFILES = j.profiles || [];
      render();
    } catch (e) { /* 忽略：没有档案就用默认 */ }
  }
  async function health() {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 6000);
    try {
      const r = await fetch('/api/health', { signal: ctl.signal, cache: 'no-store' });
      const j = await r.json();
      $('#comfyDot').className = 'dot ' + (j.comfy ? 'ok' : 'err');
      $('#comfyState').textContent = j.comfy ? 'ComfyUI 在线' : 'ComfyUI 启动中…';
    } catch (e) {
      $('#comfyDot').className = 'dot err';
      $('#comfyState').textContent = (e && e.name === 'AbortError')
        ? '检测超时，点刷新'
        : '后端未连接';
    } finally {
      clearTimeout(timer);
    }
  }

  async function save(silent) {
    await fetch('/api/project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'current', nodes: S.nodes, edges: S.edges,
                             ui: localStorage.getItem('studio.ui') || undefined,
                             view: { k: S.k, x: S.x, y: S.y } }),
    });
    DIRTY = false;
    LAST_SAVE = Date.now();
    if (!silent) {
      $('#btnSave').textContent = '已保存';
      setTimeout(() => ($('#btnSave').textContent = '保存'), 1200);
    }
  }

  // ---------- 自动保存 ----------
  function markDirty() { DIRTY = true; }
  setInterval(() => {
    if (DIRTY && Date.now() - LAST_SAVE > 2000) save(true).catch(() => {});
  }, 3000);
  window.addEventListener('beforeunload', () => {
    if (!DIRTY) return;
    try {
      const blob = new Blob([JSON.stringify({
        name: 'current', nodes: S.nodes, edges: S.edges,
        ui: localStorage.getItem('studio.ui') || undefined,
        view: { k: S.k, x: S.x, y: S.y },
      })], { type: 'application/json' });
      navigator.sendBeacon('/api/project', blob);
    } catch { /* 忽略 */ }
  });

  async function load() {
    try {
      const j = await (await fetch('/api/project?name=current')).json();
      S.nodes = j.nodes || [];
      S.edges = j.edges || [];
      S.seq = S.nodes.reduce((m, n) => Math.max(m, Number(String(n.id).slice(1)) || 0), 0);
      if (j.view) { S.k = j.view.k; S.x = j.view.x; S.y = j.view.y; }
      if (j.ui) { localStorage.setItem('studio.ui', j.ui); applyUi(j.ui); }
      applyView();
      render();
      DIRTY = false;
    } catch { /* 首次运行没有存档 */ }
  }

  /* ---------------- boot ---------------- */
  document.querySelectorAll('[data-add]').forEach((b) => {
    b.onclick = () => {
      const n = newNode(b.dataset.add, 0, 0);
      render();
      focusNode(n);
      openInspector(n);
    };
  });
  $('#btnFit').onclick = fit;
  $('#btnSave').onclick = save;

  /* 顶栏「＋ 节点」：不依赖双击，直接弹出节点菜单 */
  $('#btnAddMenu').onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const p = screenToWorld(window.innerWidth / 2, r.bottom + 120);
    menu.dataset.wx = p.x;
    menu.dataset.wy = p.y;
    menu.style.left = Math.max(12, r.left) + 'px';
    menu.style.top = (r.bottom + 8) + 'px';
    menu.classList.remove('hidden');
  };

  /* 图生视频：新建视频节点，自动挂上最近一张图作首帧 */
  $('#btnI2V').onclick = () => {
    const v = newNode('video', 0, 0);
    const imgs = S.nodes.filter((x) => x.type === 'image' && x.data.file);
    if (imgs.length) {
      v.data.image = imgs[imgs.length - 1].data.file.filename;
      v.data.status = '已挂首帧：' + v.data.image;
    } else {
      v.data.status = '还没有图片，先点「+ 图片」生成一张';
    }
    render();
    focusNode(v);
    openInspector(v);
  };

  /* 界面字号：标准 → 大 → 特大 循环 */
  const UI_MODES = ['normal', 'large', 'xlarge'];
  const UI_LABEL = { normal: 'Aa', large: 'Aa+', xlarge: 'Aa++' };
  function applyUi(mode) {
    document.documentElement.dataset.ui = mode === 'normal' ? '' : mode;
    const b = $('#btnUi');
    if (b) b.textContent = UI_LABEL[mode] || 'Aa';
    localStorage.setItem('studio.ui', mode);
    applyView();
  }
  $('#btnUi').onclick = () => {
    const cur = localStorage.getItem('studio.ui') || 'normal';
    const next = UI_MODES[(UI_MODES.indexOf(cur) + 1) % UI_MODES.length];
    applyUi(next);
  };
  applyUi(localStorage.getItem('studio.ui') || 'large');
  $('#btnIn').onclick = () => { S.k = clamp(S.k * 1.15, 0.15, 2.5); applyView(); drawEdges(); };
  $('#btnOut').onclick = () => { S.k = clamp(S.k / 1.15, 0.15, 2.5); applyView(); drawEdges(); };

  /* ---------------- LLM key（可选，不填也能用） ---------------- */
  window.getLLM = getLLM;
  function getLLM() {
    try {
      const v = JSON.parse(localStorage.getItem('studio.llm') || 'null');
      return v && v.api_key ? v : null;
    } catch { return null; }
  }
  function refreshKeyBtn() {
    const b = $('#btnKey');
    if (b) b.style.color = getLLM() ? '#5b8cff' : '';
  }
  $('#btnKey').onclick = () => {
    const p = $('#keyPanel');
    const cur = getLLM() || {};
    $('#keyInput').value = cur.api_key || '';
    $('#keyBase').value = cur.base_url || 'https://api.deepseek.com';
    $('#keyModel').value = cur.model || 'deepseek-chat';
    p.classList.toggle('hidden');
  };
  $('#keyClose').onclick = () => $('#keyPanel').classList.add('hidden');
  $('#keySave').onclick = () => {
    const v = {
      api_key: $('#keyInput').value.trim(),
      base_url: $('#keyBase').value.trim() || 'https://api.deepseek.com',
      model: $('#keyModel').value.trim() || 'deepseek-chat',
    };
    if (!v.api_key) { $('#keyInput').value = ''; localStorage.removeItem('studio.llm'); $('#keyPanel').classList.add('hidden'); refreshKeyBtn(); return; }
    localStorage.setItem('studio.llm', JSON.stringify(v));
    $('#keyPanel').classList.add('hidden');
    refreshKeyBtn();
  };
  $('#keyClear').onclick = () => {
    localStorage.removeItem('studio.llm');
    $('#keyInput').value = '';
    $('#keyPanel').classList.add('hidden');
    refreshKeyBtn();
  };
  $('#keyPreset').onchange = (e) => {
    const v = e.target.value;
    if (!v) return;
    const [base, model] = v.split('|');
    $('#keyBase').value = base;
    $('#keyModel').value = model;
  };
  $('#keyTest').onclick = async () => {
    const st = $('#keyStatus');
    if (!document.getElementById('keyModel').value.trim()) {
      st.className = 'status err';
      st.textContent = '模型还没填：先点「拉取模型」选一个，或手填（Kimi 现在可用 kimi-k3.1-pro / kimi-latest）。';
      return;
    }
    st.textContent = '测试中…';
    st.className = 'status';
    try {
      const r = await fetch('/api/llm/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: {
          api_key: $('#keyInput').value.trim(),
          base_url: $('#keyBase').value.trim(),
          model: $('#keyModel').value.trim(),
        } }),
      });
      const j = await r.json();
      st.textContent = j.ok ? `✓ ${j.model} 可用：${j.reply}` : '✗ ' + (j.error || '失败');
      st.className = 'status ' + (j.ok ? 'ok' : 'err');
    } catch (e) {
      st.textContent = '✗ ' + e.message;
      st.className = 'status err';
    }
  };
  refreshKeyBtn();

  applyView();
  render();
  load();
  health();
  loadProfiles();
  S.subject = JSON.parse(localStorage.getItem('studio.subject') || 'null');
  renderSubjectChip();
  window.STUDIO = { S, newNode, render, getLLM, aspect: () => '16:9' };
  window.__BOOTED = true;
  setInterval(health, 5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) health(); });
})();
