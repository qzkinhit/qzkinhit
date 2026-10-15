// 论文阅读笔记和论文面试卡的密码锁。页面内容用 AES-GCM 加密后放在外壳页里，密钥由密码经 PBKDF2 推导，解锁后密钥保存在本机浏览器
(() => {
  const SALT = 'KehAOZAwriNDc6LRbUljgg==', ITER = 300000, K = 'paper-key-v1';
  const b64d = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const b64e = u8 => { let t = ''; for (let i = 0; i < u8.length; i += 0x8000) t += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(t); };
  const getRaw = () => { try { return localStorage.getItem(K) || ''; } catch (e) { return ''; } };
  const setRaw = v => { try { if (v) localStorage.setItem(K, v); else localStorage.removeItem(K); } catch (e) {} };
  const text = u8 => new TextDecoder().decode(u8);
  async function deriveRaw(pw) {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveBits']);
    const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: b64d(SALT), iterations: ITER, hash: 'SHA-256' }, base, 256);
    return b64e(new Uint8Array(bits));
  }
  async function decrypt(iv, ct, raw) {
    const key = await crypto.subtle.importKey('raw', b64d(raw), 'AES-GCM', false, ['decrypt']);
    return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct));
  }
  // sealed 为 {iv, ct} 两段 base64；密钥不对时返回 null
  async function openSealed(sealed, raw) { try { return await decrypt(b64d(sealed.iv), b64d(sealed.ct), raw || getRaw()); } catch (e) { return null; } }
  // 加密文件：前 12 字节是 IV，后面是密文
  async function openFile(url) {
    const r = await fetch(url); if (!r.ok) throw new Error('文件读取失败 ' + r.status);
    const buf = new Uint8Array(await r.arrayBuffer());
    return decrypt(buf.subarray(0, 12), buf.subarray(12), getRaw());
  }

  const PL = window.PaperLock || {};
  Object.assign(PL, {
    unlocked: () => !!getRaw(),
    lock: () => setRaw(''),
    async json(sealed) { const u = await openSealed(sealed); return u ? JSON.parse(text(u)) : null; },
    // 解锁后的页面调用：音频清单走本地内存，证据链接和证据请求改为读取加密文件后在本地解开
    after(opts) {
      const map = opts.map || {}, manifest = opts.manifest || null;
      const find = u => { const p = String(u).replace(/^.*?\/reading\//, '').replace(/^\.\//, ''); const k = p.split(/[?#]/)[0]; return map[k] ? { k, hash: (p.match(/#.*$/) || [''])[0] } : null; };
      if (!PL._fetch) PL._fetch = window.fetch.bind(window);
      window.fetch = (u, o) => {
        const s = String(u && u.url || u);
        if (manifest && s.includes('audio/papers-natural/manifest.json')) return Promise.resolve(new Response(JSON.stringify(manifest), { status: 200, headers: { 'Content-Type': 'application/json' } }));
        const hit = find(s);
        if (hit) return openFile(map[hit.k].f).then(u8 => new Response(u8, { status: 200, headers: { 'Content-Type': map[hit.k].t } }));
        return PL._fetch(u, o);
      };
      document.addEventListener('click', e => {
        const a = e.target.closest && e.target.closest('a[href]'); if (!a) return;
        const hit = find(a.getAttribute('href')); if (!hit) return;
        e.preventDefault();
        const w = window.open('', '_blank');
        openFile(map[hit.k].f).then(u8 => { const url = URL.createObjectURL(new Blob([u8], { type: map[hit.k].t })) + hit.hash; if (w) w.location.href = url; else location.href = url; })
          .catch(err => { if (w) w.close(); alert(err.message); });
      }, true);
    },
    scrollHash() { if (!location.hash) return; const go = () => { const el = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (el) el.scrollIntoView(); }; go(); setTimeout(go, 400); }
  });
  window.PaperLock = PL;

  // 外壳页：先用本机记住的密钥解锁，没有或不对就显示密码框
  // 解开后的页面里也会再加载本脚本，那时没有 sealed-doc，或者已经写过一次，都直接返回
  const el = document.getElementById('sealed-doc'); if (!el || window.__plShown) return;
  const sealed = JSON.parse(el.textContent);
  // 页面还在解析时调用 document.open 不会替换文档，所以等外壳页加载完再写入
  const loaded = () => document.readyState === 'loading' ? new Promise(r => document.addEventListener('DOMContentLoaded', r, { once: true })) : Promise.resolve();
  const show = async u8 => { const html = text(u8); await loaded(); await new Promise(r => setTimeout(r, 0)); if (window.__plShown) return; window.__plShown = 1; document.open(); document.write(html); document.close(); };
  const form = document.getElementById('lockform'), msg = document.getElementById('lockmsg'), box = document.getElementById('lock');
  (async () => {
    const u = getRaw() ? await openSealed(sealed) : null;
    if (u) return show(u);
    box.classList.add('ready'); setTimeout(() => form.pw.focus(), 50);
  })();
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const pw = form.pw.value; if (!pw) return;
    msg.textContent = '正在解锁…'; form.btn.disabled = true;
    const raw = await deriveRaw(pw), u = await openSealed(sealed, raw);
    if (!u) { msg.textContent = '密码不对'; form.btn.disabled = false; form.pw.select(); return; }
    setRaw(raw); show(u);
  });
})();
