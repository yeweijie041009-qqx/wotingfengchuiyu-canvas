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
      <label title="整片总时长，会从你写的话里自动识别">总时长
        <input id="cpTotal" type="number" min="2" max="180" value="10"> 秒
      </label>
      <span id="cpSplit" class="cp-split">≈ 2 镜 × 5 秒</span>
      <label><input id="cpAuto" type="checkbox" checked> 自动出图</label>
      <label title="默认关：先出图让你确认人物一致性，满意了再出视频"><input id="cpAutoVid" type="checkbox"> 出完图直接出视频</label>
    </div>
    <div class="cp-input">
      <textarea id="cpText" rows="3" placeholder="写一句话，或粘贴一段剧本。回车发送，Shift+回车换行"></textarea>
      <div class="cp-actions">
        <button class="btn" id="cpStop" style="display:none">停止</button>
        <button class="btn primary" id="cpSend">拆分成画布</button>
      </div>
    </div>`;

  let panel, chat, plan = null, nodes = { images: [], videos: [] }, running = false, stopFlag = false;

  /* ---------- 时长 / 镜头数：从文字里自动推断 ---------- */
  const CN = { 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };

  function parseTotal(text) {
    let m = text.match(/(\d+(?:\.\d+)?)\s*(分钟|分|min|秒钟|秒|s)(?![a-z])/i);
    if (m) {
      const v = parseFloat(m[1]);
      return /分|min/i.test(m[2]) ? Math.round(v * 60) : Math.round(v);
    }
    m = text.match(/([一二两三四五六七八九十]+)\s*(分钟|秒)/);
    if (m) {
      const v = CN[m[1]] || 10;
      return m[2] === '分钟' ? v * 60 : v;
    }
    return null;
  }

  function parseShots(text) {
    let m = text.match(/(\d+)\s*(个)?\s*(镜头|分镜|镜)/);
    if (m) return Math.max(1, Math.min(24, parseInt(m[1], 10)));
    m = text.match(/([一二两三四五六七八九十]+)\s*(个)?\s*(镜头|分镜|镜)/);
    if (m) return Math.max(1, Math.min(24, CN[m[1]] || 1));
    return null;
  }

  function splitPlan() {
    const totalEl = document.getElementById('cpTotal');
    const total = Math.max(2, Math.min(180, Number(totalEl && totalEl.value) || 10));
    const text = (document.getElementById('cpText') || {}).value || '';
    const wantShots = parseShots(text);
    // 单镜不超过 10 秒；有明确镜数就按镜数均分
    // 单镜按 5 秒切（H3 出片质量与显存更稳），有明确镜数就听用户的
    const shots = wantShots || Math.max(1, Math.min(12, Math.round(total / 5)));
    const seconds = Math.max(2, Math.min(10, Math.round((total / shots) * 10) / 10));
    return { shots, seconds, total };
  }

  function refreshSplit() {
    const { shots, seconds, total } = splitPlan();
    const el = document.getElementById('cpSplit');
    if (el) {
      const real = Math.round(shots * seconds * 10) / 10;
      el.textContent = `≈ ${shots} 镜 × ${seconds} 秒` +
        (Math.abs(real - total) > 0.6 ? `（接近 ${total} 秒）` : '');
    }
  }

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
      const tickMsg = addMsg('正在拆解剧本…0s（最多等 150 秒）');
      let elapsed = 0;
      const tickTimer = setInterval(() => {
        elapsed += 3;
        tickMsg.textContent = '正在拆解剧本…' + elapsed + 's（最多等 150 秒）';
      }, 3000);
      const ctl = new AbortController();
      const to = setTimeout(() => ctl.abort(), 150000);
      let j;
      try {
        const r = await fetch(isRefine ? '/api/copilot/refine' : '/api/copilot/plan', {
          signal: ctl.signal,
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(isRefine
            ? { plan, instruction: text, llm: getLLM() }
            : {
              text,
              ...splitPlan(),
              llm: getLLM(),
            }),
        });
        j = await r.json();
        if (!r.ok) throw new Error(j.error || '拆分失败');
      } catch (e) {
        if (e && e.name === 'AbortError') throw new Error('等待超时（150 秒）。Kimi k3 系列比较慢，可换 kimi-k2.5 / kimi-latest，或稍后再试');
        throw e;
      } finally {
        clearTimeout(to);
        clearInterval(tickTimer);
      }
      j.style = '';
      build(j);
      addMsg(`已用【${j.skill || '模板'}】拆成 ${j.shots.length} 个镜头，画布上铺好了图节点和视频节点` +
        (j.note ? `（${j.note}）` : ''), 'ok');

      if (document.getElementById('cpAuto').checked) {
        await runImages();
        if (document.getElementById('cpAutoVid').checked) {
          addMsg('出图完成，按设置直接出视频…', 'ok');
          await runVideos();
          addMsg('全部完成，可以在画布上拼接或下载。', 'ok');
        } else {
          addMsg('图片出完了 —— 先检查人物是否一致。\n' +
            '满意就点「继续出视频」；不满意可以改某个图片节点的提示词后点「重出图」，' +
            '或用第一张图做角色参考再出。', 'ok');
          addActions();
        }
      }
    } catch (e) {
      addMsg('出错：' + (e.message || e), 'err');
    } finally {
      running = false;
      document.getElementById('cpSend').disabled = false;
      document.getElementById('cpStop').style.display = 'none';
      refreshActions();
    }
  }

  /* ---------- 出图之后的「确认 / 继续」按钮 ---------- */
  function addActions() {
    const box = document.createElement('div');
    box.className = 'cp-msg cp-actions-box';
    box.innerHTML = `
      <button class="btn primary" data-a="go">继续出视频</button>
      <button class="btn" data-a="redo">重出图</button>
      <button class="btn" data-a="lock">用第 1 镜当角色参考</button>`;
    box.querySelector('[data-a="go"]').onclick = async (e) => {
      e.target.disabled = true;
      try {
        addMsg('开始逐镜出视频…');
        await runVideos();
        addMsg('视频全部完成。', 'ok');
      } catch (err) {
        addMsg('出视频出错：' + (err.message || err), 'err');
      } finally {
        box.remove();
      }
    };
    box.querySelector('[data-a="redo"]').onclick = async (e) => {
      e.target.disabled = true;
      try {
        await runImages();
        addMsg('重出图完成。', 'ok');
      } catch (err) {
        addMsg('重出图失败：' + (err.message || err), 'err');
      } finally {
        e.target.disabled = false;
      }
    };
    box.querySelector('[data-a="lock"]').onclick = () => {
      const first = nodes.images[0];
      if (!first || !first.data.file) { addMsg('还没有图可以当参考', 'err'); return; }
      api.setSubject && api.setSubject(first.data.file.filename);
      addMsg(`已把「${first.data.file.filename}」设为角色参考图；` +
        '之后重新出图会锁住这个人物。', 'ok');
    };
    chat.appendChild(box);
    chat.scrollTop = chat.scrollHeight;
  }

  function refreshActions() { /* 预留：手动按钮的状态同步 */ }

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
    const ta = document.getElementById('cpText');
    ta.addEventListener('input', () => {
      const t = parseTotal(ta.value);
      if (t) document.getElementById('cpTotal').value = t;
      refreshSplit();
    });
    document.getElementById('cpTotal').addEventListener('input', refreshSplit);
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(); }
    });
    refreshSplit();
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
