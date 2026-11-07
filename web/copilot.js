/* 画布副驾驶：右侧对话面板 → 剧本 → 镜头图 + 视频节点 → 自动出图出片 */
(() => {
  const api = window.STUDIO;
  if (!api) return;
  const { S, newNode, render, getLLM } = api;

  const PANEL = `
    <div class="cp-head">
      <span class="cp-title">AI 创作伙伴</span>
      <button class="cp-close" title="收起">×</button>
    </div>
    <div class="cp-chat" id="cpChat"></div>
    <div class="cp-opts">
      <label>镜头 <input id="cpShots" type="number" min="1" max="12" value="4"></label>
      <label>时长 <input id="cpSecs" type="number" min="2" max="10" value="5"></label>
      <label><input id="cpAuto" type="checkbox" checked> 自动出图</label>
    </div>
    <div class="cp-input">
      <textarea id="cpText" rows="3" placeholder="写一句话，或粘贴一段剧本。回车发送，Shift+回车换行"></textarea>
      <div class="cp-actions">
        <button class="btn" id="cpStop" style="display:none">停止</button>
        <button class="btn primary" id="cpSend">拆分成画布</button>
      </div>
    </div>`;

  let panel, chat, plan = null, nodes = { images: [], videos: [] }, running = false, stopFlag = false;

  function addMsg(text, cls) {
    const d = document.createElement('div');
    d.className = 'cp-msg ' + (cls || '');
    d.textContent = text;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
    return d;
  }

  async function job(jobId) {
    for (let i = 0; i < 900; i++) {
      const j = await (await fetch('/api/job/' + jobId)).json();
      if (j.status === 'done') return j;
      if (j.status === 'error') throw new Error((j.error || '生成失败').slice(0, 200));
      await new Promise((r) => setTimeout(r, 3000));
      if (stopFlag) throw new Error('已停止');
    }
    throw new Error('超时');
  }

  function layout(baseX, baseY) {
    const gapX = 420, gapY = 40;
    return { baseX, baseY, gapX, gapY };
  }

  function build(pl) {
    plan = pl;
    // 清掉上一轮生成的节点
    const old = new Set([...nodes.images, ...nodes.videos].map((n) => n.id));
    if (nodes.script) old.add(nodes.script.id);
    S.nodes = S.nodes.filter((n) => !old.has(n.id));
    S.edges = S.edges.filter((e) => !old.has(e.from) && !old.has(e.to));
    nodes = { images: [], videos: [] };

    const box = document.getElementById('nodes');
    const cx = box ? box.parentElement.scrollLeft / 1 - 0 : 0;
    const baseX = 120 + (S.nodes.length % 4) * 40;
    const baseY = 120;

    const script = newNode('script', baseX, baseY);
    script.w = 340;
    script.data.text = `《${pl.title || '未命名'}》\n${pl.logline || ''}\n\n` +
      pl.shots.map((s, i) => `${i + 1}. [${s.shot_size}] ${s.action}${s.dialogue ? ' 对白：' + s.dialogue : ''}`).join('\n');
    nodes.script = script;

    const L = layout(baseX + 400, baseY);
    pl.shots.forEach((s, i) => {
      const img = newNode('image', L.baseX, L.baseY + i * 360);
      img.data.prompt = s.image_prompt;
      img.data.mode = 'single';
      img.data.aspect = '16:9';
      img.data.status = '待出图';
      nodes.images.push(img);

      const vid = newNode('video', L.baseX + 420, L.baseY + i * 360);
      vid.data.prompt = s.video_prompt;
      vid.data.seconds = s.seconds;
      vid.data.preset = 'draft';
      vid.data.aspect = '16:9';
      vid.data.status = '待出视频';
      nodes.videos.push(vid);

      S.edges.push({ from: script.id, to: img.id });
      S.edges.push({ from: img.id, to: vid.id });
    });
    render();
    const key = document.getElementById('btnFit');
    if (key) key.click();
  }

  async function runImages() {
    for (let i = 0; i < nodes.images.length; i++) {
      if (stopFlag) return;
      const img = nodes.images[i];
      img.data.status = '出图中…';
      render();
      const r = await fetch('/api/image/render', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: img.data.prompt, engine: 'sdxl', aspect: img.data.aspect,
          seed: Math.floor(Math.random() * 1e6), llm: getLLM(),
        }),
      });
      const j0 = await r.json();
      if (!r.ok) throw new Error(j0.error || '出图失败');
      const done = await job(j0.id);
      img.data.file = (done.files && done.files[0]) || null;
      img.data.status = '完成';
      img.data.statusClass = 'ok';
      render();
      addMsg(`镜头 ${i + 1} 出图完成`, 'ok');
    }
  }

  async function runVideos() {
    for (let i = 0; i < nodes.videos.length; i++) {
      if (stopFlag) return;
      const vid = nodes.videos[i];
      const img = nodes.images[i];
      vid.data.status = '生成中…';
      render();
      const r = await fetch('/api/render', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: vid.data.prompt, seconds: vid.data.seconds, preset: 'draft',
          aspect: vid.data.aspect, seed: Math.floor(Math.random() * 1e6),
          image: img && img.data.file ? img.data.file.filename : undefined,
          llm: getLLM(),
        }),
      });
      const j0 = await r.json();
      if (!r.ok) throw new Error(j0.error || '出视频失败');
      const done = await job(j0.id);
      vid.data.file = (done.files && done.files[0]) || null;
      vid.data.status = '完成 · ' + Math.round(done.elapsed) + 's';
      vid.data.statusClass = 'ok';
      render();
      addMsg(`镜头 ${i + 1} 视频完成`, 'ok');
    }
  }

  async function go() {
    const textEl = document.getElementById('cpText');
    const text = textEl.value.trim();
    if (!text || running) return;
    textEl.value = '';
    addMsg(text, 'me');
    running = true; stopFlag = false;
    document.getElementById('cpSend').disabled = true;
    document.getElementById('cpStop').style.display = '';

    try {
      const isRefine = !!plan;
      addMsg('正在拆解剧本…（最多等 90 秒，超时会退回模板分镜）');
      const ctl = new AbortController();
      const to = setTimeout(() => ctl.abort(), 90000);
      let j;
      try {
        const r = await fetch(isRefine ? '/api/copilot/refine' : '/api/copilot/plan', {
          signal: ctl.signal,
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(isRefine
            ? { plan, instruction: text, llm: getLLM() }
            : {
              text,
              shots: Number(document.getElementById('cpShots').value) || 4,
              seconds: Number(document.getElementById('cpSecs').value) || 5,
              llm: getLLM(),
            }),
        });
        j = await r.json();
        if (!r.ok) throw new Error(j.error || '拆分失败');
      } catch (e) {
        if (e && e.name === 'AbortError') throw new Error('等待超时（90 秒），请检查 API Key 或换个模型再试');
        throw e;
      } finally {
        clearTimeout(to);
      }
      j.style = '';
      build(j);
      addMsg(`已拆成 ${j.shots.length} 个镜头，画布上铺好了图节点和视频节点` +
        (j.note ? `（${j.note}）` : ''), 'ok');

      if (document.getElementById('cpAuto').checked) {
        await runImages();
        addMsg('出图完成，开始逐镜出视频…', 'ok');
        await runVideos();
        addMsg('全部完成，可以在画布上拼接或下载。', 'ok');
      }
    } catch (e) {
      addMsg('出错：' + (e.message || e), 'err');
    } finally {
      running = false;
      document.getElementById('cpSend').disabled = false;
      document.getElementById('cpStop').style.display = 'none';
    }
  }

  function mount() {
    panel = document.createElement('aside');
    panel.id = 'copilot';
    panel.innerHTML = PANEL;
    document.body.appendChild(panel);
    chat = document.getElementById('cpChat');

    panel.querySelector('.cp-close').onclick = () => {
      panel.classList.add('hidden');
      document.body.classList.remove('cp-open');
    };
    document.getElementById('cpSend').onclick = go;
    document.getElementById('cpStop').onclick = () => { stopFlag = true; addMsg('正在停止…'); };
    document.getElementById('cpText').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(); }
    });
    addMsg('你好，我是你的 AI 创作伙伴。\n写一句话，我把它拆成镜头、铺到画布上，再逐镜出图、出视频。', 'hello');
  }

  function toggle() {
    if (!panel) { mount(); document.body.classList.add('cp-open'); return; }
    const nowHidden = panel.classList.toggle('hidden');
    document.body.classList.toggle('cp-open', !nowHidden);
  }

  window.COPILOT = { toggle };
  if (location.hash === '#copilot') { toggle(); }
  const btn = document.getElementById('btnCopilot');
  if (btn) btn.onclick = toggle;
})();
