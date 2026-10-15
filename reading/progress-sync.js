// 刷卡进度的上传和读取。进度存在 GitHub 私有仓库 qzkinhit/study-progress，访问令牌只保存在本机浏览器，不写进网页
(() => {
  if (window.__psync) return; window.__psync = 1;
  const REPO = 'https://api.github.com/repos/qzkinhit/study-progress', API = REPO + '/contents/progress.json';
  const K_TOKEN = 'psync-token-v1', K_LAST = 'psync-last-v1';
  const MAPS = ['hot100-status-v1', 'swipe-srs-v1', 'swipe-draft-v1', 'paper-status-v1', 'paper-srs-v1', 'paper-note-v1', 'bagu-status-v1', 'bagu-srs-v1', 'bagu-draft-v1'];
  const WHOLE = ['swipe-pos-v1', 'swipe-cfg-v1', 'paper-pos-v1', 'paper-cfg-v1', 'bagu-pos-v1', 'bagu-cfg-v1'];
  const STATUS = ['hot100-status-v1', 'paper-status-v1', 'bagu-status-v1'];
  const PAIR = { 'hot100-status-v1': 'swipe-srs-v1', 'paper-status-v1': 'paper-srs-v1', 'bagu-status-v1': 'bagu-srs-v1' };
  const IV = [0, 1, 3, 7, 15, 30];

  const rd = k => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : undefined; } catch (e) { return undefined; } };
  const wr = (k, v) => { try { if (v === undefined) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const token = () => { try { return localStorage.getItem(K_TOKEN) || ''; } catch (e) { return ''; } };
  const setToken = t => { try { if (t) localStorage.setItem(K_TOKEN, t); else localStorage.removeItem(K_TOKEN); } catch (e) {} };
  const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

  const snap = () => {
    const s = { maps: {}, whole: {} };
    MAPS.forEach(k => { const v = rd(k); if (v && typeof v === 'object') s.maps[k] = v; });
    WHOLE.forEach(k => { const v = rd(k); if (v !== undefined) s.whole[k] = v; });
    return s;
  };
  // 复习记录 {b: 间隔档位, d: 到期日}，到期日减去间隔就是复习那天
  const reviewDay = r => r && typeof r.d === 'number' ? r.d - (IV[r.b] || 0) : -Infinity;
  // 合并两份进度。两边都有的卡片，复习记录取最近复习的一边，熟练程度跟随同一边，草稿、笔记和位置取 src 一边
  function merge(src, dst) {
    const out = { maps: {}, whole: {} }, fromDst = new Set();
    const keys = [...MAPS].sort((a, b) => /srs/.test(b) - /srs/.test(a));
    for (const k of keys) {
      const a = src.maps[k] || {}, b = dst.maps[k] || {}, o = {};
      for (const id of new Set([...Object.keys(a), ...Object.keys(b)])) {
        let v;
        if (!has(a, id)) v = b[id];
        else if (!has(b, id) || eq(a[id], b[id])) v = a[id];
        else if (/srs/.test(k)) { if (reviewDay(b[id]) > reviewDay(a[id])) { v = b[id]; fromDst.add(k + '|' + id); } else v = a[id]; }
        else if (PAIR[k] && fromDst.has(PAIR[k] + '|' + id)) v = b[id];
        else v = a[id];
        o[id] = v;
      }
      if (Object.keys(o).length) out.maps[k] = o;
    }
    for (const k of WHOLE) { const v = has(src.whole, k) ? src.whole[k] : dst.whole[k]; if (v !== undefined) out.whole[k] = v; }
    return out;
  }
  const diff = (x, y) => {
    let n = 0;
    for (const k of MAPS) { const a = x.maps[k] || {}, b = y.maps[k] || {}; for (const id of new Set([...Object.keys(a), ...Object.keys(b)])) if (!eq(a[id], b[id])) n++; }
    for (const k of WHOLE) if (!eq(x.whole[k], y.whole[k])) n++;
    return n;
  };
  const cards = s => STATUS.reduce((t, k) => t + Object.keys(s.maps[k] || {}).length, 0);
  const apply = (M, L) => { MAPS.forEach(k => { if (!eq(M.maps[k], L.maps[k])) wr(k, M.maps[k]); }); WHOLE.forEach(k => { if (!eq(M.whole[k], L.whole[k])) wr(k, M.whole[k]); }); };

  const b64e = s => { const u = new TextEncoder().encode(s); let t = ''; for (let i = 0; i < u.length; i += 0x8000) t += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(t); };
  const b64d = s => new TextDecoder().decode(Uint8Array.from(atob(s.replace(/\s/g, '')), c => c.charCodeAt(0)));
  const device = () => { const u = navigator.userAgent; return /iPhone/.test(u) ? 'iPhone' : /iPad/.test(u) || (/Macintosh/.test(u) && navigator.maxTouchPoints > 1) ? 'iPad' : /Android/.test(u) ? 'Android' : /Macintosh/.test(u) ? 'Mac' : /Windows/.test(u) ? 'Windows' : '浏览器'; };
  const hdr = t => ({ Authorization: 'Bearer ' + t, Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' });
  const fail = (status, where) => {
    if (status === 401) { setToken(''); return new Error('令牌无效或已过期，请重新粘贴一个'); }
    if (status === 403) return new Error('令牌没有写入权限，把 Contents 设为 Read and write 后重新生成');
    if (status === 404) return new Error('令牌访问不到 study-progress 仓库，生成令牌时要选中这个仓库');
    return new Error(`GitHub 返回 ${status}（${where}），稍后再试`);
  };
  async function pull(t) {
    const r = await fetch(API, { headers: hdr(t), cache: 'no-store' });
    if (r.status === 404) { const rr = await fetch(REPO, { headers: hdr(t), cache: 'no-store' }); if (!rr.ok) throw fail(rr.status, '仓库'); return { sha: null, data: null }; }
    if (!r.ok) throw fail(r.status, '读取');
    const j = await r.json(); let text = j.content ? b64d(j.content) : '';
    if (!text && j.size) {
      const r2 = await fetch(API, { headers: Object.assign(hdr(t), { Accept: 'application/vnd.github.raw+json' }), cache: 'no-store' });
      if (!r2.ok) throw fail(r2.status, '读取'); text = await r2.text();
    }
    const doc = text ? JSON.parse(text) : {};
    return { sha: j.sha, data: doc.data || null, at: doc.at, device: doc.device };
  }
  async function push(t, data, sha) {
    const at = new Date().toISOString();
    const body = { message: '上传进度 ' + device() + ' ' + at.slice(0, 16), content: b64e(JSON.stringify({ v: 1, at, device: device(), data })) };
    if (sha) body.sha = sha;
    const r = await fetch(API, { method: 'PUT', headers: Object.assign(hdr(t), { 'Content-Type': 'application/json' }), body: JSON.stringify(body) });
    if (r.status === 409 || r.status === 422) return false;
    if (!r.ok) throw fail(r.status, '上传');
    return true;
  }
  const stamp = (k) => { const m = rd(K_LAST) || {}; m[k] = Date.now(); wr(K_LAST, m); };
  async function upload(t) {
    for (let i = 0; i < 3; i++) {
      const R = await pull(t), L = snap(), M = R.data ? merge(L, R.data) : L;
      if (await push(t, M, R.sha)) { stamp('up'); return `已上传，云端共有 ${cards(M)} 张卡的记录`; }
    }
    throw new Error('云端刚被别的设备更新，再点一次上传');
  }
  async function download(t) {
    const R = await pull(t);
    if (!R.data) throw new Error('云端还没有进度，先在刷过题的设备上点一次上传');
    const L = snap(), M = merge(R.data, L), n = diff(M, L);
    if (n) apply(M, L);
    stamp('down');
    const from = R.at ? `（${R.device || ''} ${fmt(Date.parse(R.at))} 上传）` : '';
    return { n, msg: n ? `已读取${from}，本机更新了 ${n} 处，页面马上刷新` : `本机已经是最新${from}` };
  }
  const fmt = ms => { if (!ms) return ''; const d = new Date(ms), p = x => String(x).padStart(2, '0'); return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };

  const css = `#psync-dlg{position:fixed;inset:0;z-index:1000;display:none;align-items:center;justify-content:center;padding:16px;background:rgba(10,14,16,.5);font:15px/1.6 system-ui,-apple-system,'PingFang SC',sans-serif}
#psync-dlg.on{display:flex}
#psync-dlg [hidden]{display:none!important}
#psync-dlg .ps-box{position:relative;width:min(420px,100%);max-height:calc(100vh - 32px);overflow:auto;box-sizing:border-box;background:#fff;color:#20332f;border-radius:18px;padding:20px 20px 16px;box-shadow:0 12px 40px rgba(0,0,0,.35)}
#psync-dlg h3{margin:0 0 4px;font-size:18px}
#psync-dlg .ps-sub,#psync-dlg .ps-hint,#psync-dlg .ps-meta{margin:0 0 10px;font-size:13px;color:#6b7a75}
#psync-dlg .ps-x{position:absolute;top:10px;right:10px;width:32px;height:32px;border:0;border-radius:50%;background:#eef2f0;color:#20332f;font-size:15px;cursor:pointer}
#psync-dlg .ps-tok{background:#f5f8f6;border-radius:12px;padding:10px 12px;margin:0 0 12px}
#psync-dlg .ps-tok p{margin:0 0 4px;font-size:14px}
#psync-dlg ol{margin:0 0 8px;padding-left:20px;font-size:13px;color:#3d4f4a}
#psync-dlg a{color:#16795f}
#psync-dlg input{display:block;width:100%;box-sizing:border-box;margin:4px 0 6px;padding:9px 12px;border:1px solid #d5ddd9;border-radius:10px;font:inherit;background:#fff;color:#20332f;outline:none}
#psync-dlg input:focus{border-color:#16795f}
#psync-dlg label{display:block;font-size:14px;font-weight:600;margin:0 0 10px}
#psync-dlg .ps-acts{display:flex;gap:10px;margin:4px 0 8px}
#psync-dlg .ps-acts button{flex:1;min-height:46px;border:0;border-radius:12px;font:600 15px/1.3 inherit;cursor:pointer;background:#e8efec;color:#20332f}
#psync-dlg .ps-acts button.ps-pri{background:#16795f;color:#fff}
#psync-dlg .ps-acts button:disabled{opacity:.55;cursor:default}
#psync-dlg .ps-msg{min-height:1.6em;margin:0 0 6px;font-size:14px}
#psync-dlg .ps-msg.ps-err{color:#b4372f}#psync-dlg .ps-msg.ps-ok{color:#16795f}
#psync-dlg .ps-more{display:flex;gap:8px;flex-wrap:wrap}
#psync-dlg .ps-more button{border:1px solid #d5ddd9;background:#fff;color:#3d4f4a;border-radius:999px;padding:4px 12px;font:13px/1.6 inherit;cursor:pointer}
.psync-chip{border:0;background:rgba(255,255,255,.2);color:#fff;border-radius:999px;padding:1px 9px;margin-right:8px;font:600 12px/1.6 inherit;cursor:pointer;vertical-align:1px}
.psync-chip:hover{background:rgba(255,255,255,.32)}`;
  const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
  const dlg = document.createElement('div'); dlg.id = 'psync-dlg'; dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true'); dlg.setAttribute('aria-labelledby', 'psync-h');
  dlg.innerHTML = `<div class="ps-box"><button class="ps-x" type="button" data-ps="close" aria-label="关闭">✕</button>
<h3 id="psync-h">☁ 进度上传和读取</h3>
<p class="ps-sub">熟练程度、复习日程、默写草稿和笔记、刷到哪一题，存到你的 GitHub 私有仓库。换一台设备点读取，就能接着刷。</p>
<div class="ps-tok"><p><b>这台设备第一次用，需要一个 GitHub 令牌</b></p>
<ol><li>打开 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener">GitHub 新建令牌页</a></li><li>Repository access 选 Only select repositories，选中 study-progress</li><li>Permissions 里把 Contents 设为 Read and write</li><li>生成后复制令牌，粘贴到下面</li></ol>
<input type="password" data-ps="token" placeholder="github_pat_ 开头的令牌" autocomplete="off" spellcheck="false">
<p class="ps-hint">令牌只保存在这台设备的浏览器里，不会写进网页。</p></div>
<div class="ps-acts"><button type="button" class="ps-pri" data-ps="up">⬆ 上传进度</button><button type="button" data-ps="down">⬇ 读取进度</button></div>
<p class="ps-msg" role="status"></p><p class="ps-meta"></p>
<div class="ps-more"><button type="button" data-ps="link">复制手机设置链接</button><button type="button" data-ps="forget">清除本机令牌</button></div></div>`;
  document.body.appendChild(dlg);
  const $ = s => dlg.querySelector(s), msg = (t, cls) => { const m = $('.ps-msg'); m.textContent = t || ''; m.className = 'ps-msg' + (cls ? ' ps-' + cls : ''); };
  const paint = () => {
    const t = token(), last = rd(K_LAST) || {};
    $('.ps-tok').hidden = !!t; $('.ps-more').hidden = !t;
    $('.ps-meta').textContent = [last.up ? '这台设备上次上传 ' + fmt(last.up) : '', last.down ? '上次读取 ' + fmt(last.down) : ''].filter(Boolean).join('，');
  };
  const open = () => { msg(''); paint(); dlg.classList.add('on'); const f = !token() ? $('[data-ps=token]') : $('[data-ps=up]'); setTimeout(() => f.focus(), 30); };
  const close = () => dlg.classList.remove('on');
  let busy = false;
  async function run(kind) {
    if (busy) return;
    const ti = $('[data-ps=token]').value.trim();
    if (!token() && !ti) { msg('先粘贴 GitHub 令牌', 'err'); $('[data-ps=token]').focus(); return; }
    if (ti) { setToken(ti); $('[data-ps=token]').value = ''; }
    busy = true; dlg.querySelectorAll('.ps-acts button').forEach(b => { b.disabled = true; }); msg(kind === 'up' ? '正在上传…' : '正在读取…');
    try {
      if (kind === 'up') msg(await upload(token()), 'ok');
      else { const r = await download(token()); msg(r.msg, 'ok'); if (r.n) setTimeout(() => location.reload(), 1200); }
    } catch (e) { msg(e.message || String(e), 'err'); }
    busy = false; dlg.querySelectorAll('.ps-acts button').forEach(b => { b.disabled = false; }); paint();
  }
  dlg.addEventListener('click', e => {
    if (e.target === dlg) return close();
    const b = e.target.closest('[data-ps]'); if (!b) return;
    const k = b.dataset.ps;
    if (k === 'close') close();
    else if (k === 'up' || k === 'down') run(k);
    else if (k === 'forget') { setToken(''); msg('已清除这台设备上的令牌'); paint(); }
    else if (k === 'link') {
      const url = location.href.replace(/[?#].*$/, '').replace(/[^/]*$/, '') + '12-cards.html#ptoken=' + encodeURIComponent(token());
      const done = () => msg('已复制。用隔空投送或备忘录发到手机上打开一次，手机就记住了令牌。链接里含令牌，只发给自己', 'ok');
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done, () => prompt('复制这个链接', url)); else prompt('复制这个链接', url);
    }
  });
  dlg.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Escape') close(); });
  dlg.addEventListener('keyup', e => e.stopPropagation());

  // 手机设置链接：地址里带 #ptoken= 时保存令牌并从地址栏去掉
  const hm = location.hash.match(/^#ptoken=([^&]+)/);
  if (hm) { setToken(decodeURIComponent(hm[1])); history.replaceState(null, '', location.pathname + location.search); setTimeout(() => { open(); msg('这台设备已记住令牌，可以上传和读取了', 'ok'); }, 300); }

  const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'psync-btn'; btn.title = '上传和读取进度'; btn.setAttribute('aria-label', '上传和读取进度');
  btn.addEventListener('click', e => { e.stopPropagation(); open(); });
  // 总览页放在右上角，刷卡页放在第二行「今日」左边，避免挤占顶栏
  const slot = document.querySelector('[data-psync]'), today = document.querySelector('#top #today');
  if (slot) { btn.textContent = '☁ 上传和读取进度'; slot.appendChild(btn); }
  else if (today) { btn.classList.add('psync-chip'); btn.textContent = '☁ 进度'; today.before(btn); }
  window.ProgressSync = { open };
})();
