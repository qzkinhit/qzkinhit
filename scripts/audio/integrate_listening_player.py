"""Idempotently attach the shared player to the papers/bagu generated HTML.

Builders and the CLI write pages through write_integrated_page, which holds
the same per-page flock through read, integration and atomic replacement.
integrate_player transforms strings without writing files or rebuilding data.
Unknown or partially changed page structures raise IntegrationError.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROFILES = {
    'papers': ('10-papers.html', 'paper-rate-v2', '论文面试卡', '  // 听卡：连播、自动下滑、锁屏控制、倍速、睡眠定时'),
    'bagu': ('11-bagu.html', 'bagu-rate-v2', '八股速记', '  // ---------- 听题 ----------'),
}
DATA = re.compile(r'<script\b(?=[^>]*\bid=["\']data["\'])[^>]*>(.*?)</script>', re.S)
OLD_CLICK = "if (e.target.closest('[data-listen]')) { const k = +sl.dataset.k; if (listening && playIdx === k) { audio.paused ? audio.play() : audio.pause(); } else startListen(k); return; }"
NEW_CLICK = "if (e.target.closest('[data-listen]')) { listener.toggleFor(+sl.dataset.k); return; }"
OLD_FOLLOW = "  setCur = function (k, force) { _setCur(k, force); if (listening && k !== playIdx && k < order.length) playAt(k, false); };"
PANEL_BEGIN = '<!-- study-player:panel:begin -->'
PANEL_END = '<!-- study-player:panel:end -->'
ADAPTER_BEGIN = '  // study-player:adapter:begin '
ADAPTER_END = '  // study-player:adapter:end'


class IntegrationError(ValueError):
    pass


def data_payload(html):
    matches = list(DATA.finditer(html))
    if len(matches) != 1:
        raise IntegrationError('Expected exactly one script with id=data')
    return matches[0].group(1)


def replace_once(text, old, new, name):
    if text.count(old) != 1:
        raise IntegrationError(f'{name}: expected one known anchor, found {text.count(old)}')
    return text.replace(old, new, 1)


def replace_marked(text, begin, end, replacement, name):
    if text.count(begin) != 1 or text.count(end) != 1:
        raise IntegrationError(f'{name}: incomplete or duplicate integration markers')
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    return text[:start] + replacement + text[finish:]


def audio_version(collection):
    manifest = ROOT / 'reading' / 'audio' / (collection + '-natural') / 'manifest.json'
    try:
        return hashlib.sha256(manifest.read_bytes()).hexdigest()[:12]
    except FileNotFoundError:
        return 'pending'


def adapter(collection):
    _, rate_key, artist, _ = PROFILES[collection]
    version = audio_version(collection)
    availability_declaration = ''
    availability_loader = ''
    availability_option = ''
    if collection == 'papers':
        question = """      return c ? {
        id: c.id, title: `${c.name} · ${c.q}`,
        album: `论文面试卡 · 第 ${k + 1} / ${order.length} 张`, artist: c.name,
        audioSrc: 'audio/papers-natural/' + encodeURIComponent(c.id) + '.mp3?v=__AUDIO_VERSION__',
        fallbackAudioSrc: 'audio/papers/' + encodeURIComponent(c.id) + '.m4a',
        fallbackVoiceLabel: '原版合成音频'
      } : null;"""
    else:
        availability_declaration = '  let availableAudio = null, availableAudioVersions = new Map();\n'
        availability_option = '    refreshAvailability: refreshAudioAvailability,\n'
        question = """      return c ? {
        id: c.id, title: c.q,
        album: `${deckOf(cfg.deck).name} · 第 ${k + 1} / ${order.length} 题`,
        audioAvailable: availableAudio === null ? undefined : availableAudio.has(c.id),
        audioSrc: 'audio/bagu-natural/' + encodeURIComponent(c.id) + '.mp3?v=' + (availableAudioVersions.get(c.id) || '__AUDIO_VERSION__')
      } : null;"""
        availability_loader = """
  let audioManifestRequest = null, lastAudioManifestAttempt = -Infinity;
  function refreshAudioAvailability({ explicit = false } = {}) {
    if (audioManifestRequest) return audioManifestRequest;
    const now = Date.now(), cooldown = explicit ? 3000 : 15000;
    if (now - lastAudioManifestAttempt < cooldown) return Promise.resolve(false);
    lastAudioManifestAttempt = now;
    $('#player').dataset.audioManifest = 'loading';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const manifestURL = 'audio/bagu-natural/manifest.json?t=' + now;
    audioManifestRequest = fetch(manifestURL, { cache: 'no-store', signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('Audio manifest unavailable'); return response.json(); })
      .then(manifest => {
        if (!manifest.tracks || typeof manifest.tracks !== 'object' || Array.isArray(manifest.tracks)) throw new Error('Invalid audio manifest');
        availableAudio = new Set(Object.keys(manifest.tracks));
        availableAudioVersions = new Map();
        for (const [id, track] of Object.entries(manifest.tracks)) {
          if (typeof track?.audioSha256 === 'string' && /^[0-9a-f]{64}$/i.test(track.audioSha256)) availableAudioVersions.set(id, track.audioSha256.slice(0, 12));
        }
        $('#player').dataset.audioManifest = 'ready';
        listener.availabilityUpdated();
        return true;
      })
      .catch(() => {
        // 请求失败时清单状态为未知，允许用户按原有单卡方式重试。
        availableAudio = null;
        $('#player').dataset.audioManifest = 'unavailable';
        listener.availabilityUpdated();
        return false;
      })
      .finally(() => { clearTimeout(timeout); audioManifestRequest = null; });
    return audioManifestRequest;
  }
  window.addEventListener('pageshow', event => { if (event.persisted) refreshAudioAvailability({ explicit: true }); });
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshAudioAvailability(); });
  refreshAudioAvailability();
"""
    question = question.replace('__AUDIO_VERSION__', version)
    return f"""{ADAPTER_BEGIN}{collection}
{availability_declaration}  const listener = window.createStudyAudioPlayer({{
    element: $('#player'), trigger: $('#listen'), storage: LS, toast,
    rateStorageKey: '{rate_key}', artist: '{artist}',
{availability_option.rstrip()}
    getCount: () => order.length,
    getCurrentIndex: () => cur,
    getQuestion: k => {{
      const c = BY[order[k]];
{question}
    }},
    showQuestion: k => jump(k),
    markActive: k => document.querySelectorAll('.rb.lis').forEach(b => b.classList.toggle('on', +b.closest('.slide').dataset.k === k))
  }});
  const _setCur = setCur;
  setCur = function (k, force) {{ _setCur(k, force); listener.follow(k); }};
{availability_loader.rstrip()}
{ADAPTER_END}"""


def integrate_player(html, collection):
    if collection not in PROFILES:
        raise IntegrationError(f'Unsupported collection: {collection}')
    before_data = data_payload(html)
    # Inspect the existing schema without serializing it back into the page.
    try:
        data = json.loads(before_data)
    except json.JSONDecodeError as error:
        raise IntegrationError('id=data does not contain valid JSON') from error
    if collection == 'papers':
        valid = isinstance(data, list) and all(isinstance(p, dict) and isinstance(p.get('cards'), list) for p in data)
    else:
        valid = isinstance(data, dict) and isinstance(data.get('cards'), list) and isinstance(data.get('decks'), list)
    if not valid:
        raise IntegrationError(f'{collection}: card schema does not match the page adapter')

    panel = (ROOT / 'reading/listening-player.html').read_text().strip().replace('{{collection}}', collection)
    panel = PANEL_BEGIN + '\n' + panel + '\n' + PANEL_END
    marked = PANEL_BEGIN in html or PANEL_END in html
    if marked:
        if f'data-study-player="{collection}"' not in html:
            raise IntegrationError('Player panel belongs to a different collection')
        html = replace_marked(html, PANEL_BEGIN, PANEL_END, panel, 'player panel')
    else:
        matches = list(re.finditer(r'<div id="player">[^\n]*</div>(?=\n<div id="toast")', html))
        if len(matches) != 1 or 'class="pbar"' not in matches[0].group():
            raise IntegrationError('Legacy player markup changed; refusing to replace an unknown section')
        m = matches[0]
        html = html[:m.start()] + panel + html[m.end():]

    new_adapter = adapter(collection)
    if ADAPTER_BEGIN in html or ADAPTER_END in html:
        if html.count(ADAPTER_BEGIN) != 1 or ADAPTER_BEGIN + collection not in html:
            raise IntegrationError('Player adapter belongs to a different collection or is duplicated')
        html = replace_marked(html, ADAPTER_BEGIN + collection, ADAPTER_END, new_adapter, 'player adapter')
        if html.count(NEW_CLICK) != 1 or OLD_CLICK in html:
            raise IntegrationError('Integrated card listening handler changed')
    else:
        start_anchor = PROFILES[collection][3] + '\n  const audio = new Audio();'
        if html.count(start_anchor) != 1 or html.count(OLD_FOLLOW) != 1:
            raise IntegrationError('Legacy player JavaScript boundaries changed')
        start = html.index(start_anchor)
        finish = html.index(OLD_FOLLOW, start) + len(OLD_FOLLOW)
        block = html[start:finish]
        if "const _setCur = setCur;" not in block or "$('#listen').addEventListener('click'" not in block:
            raise IntegrationError('Legacy playback block is incomplete')
        html = html[:start] + new_adapter + html[finish:]
        html = replace_once(html, OLD_CLICK, NEW_CLICK, 'card listening handler')

    digest = hashlib.sha256()
    for name in ('listening-player.js', 'listening-player.css'):
        digest.update((ROOT / 'reading' / name).read_bytes())
    version = digest.hexdigest()[:12]
    css = f'<link data-study-audio-asset="css" rel="stylesheet" href="listening-player.css?v={version}">'
    js = f'<script data-study-audio-asset="js" src="listening-player.js?v={version}"></script>'
    for name, tag, pattern in (
        ('css', css, r'<link\b[^>]*data-study-audio-asset="css"[^>]*>'),
        ('js', js, r'<script\b[^>]*data-study-audio-asset="js"[^>]*></script>'),
    ):
        matches = list(re.finditer(pattern, html))
        if len(matches) > 1:
            raise IntegrationError(f'Duplicate shared player {name} assets')
        if matches:
            m = matches[0]
            html = html[:m.start()] + tag + html[m.end():]
        else:
            # A bare/unknown import might otherwise silently load an old module.
            if f'listening-player.{name}' in html:
                raise IntegrationError(f'Unrecognized shared player {name} import')
            if name == 'css':
                html = replace_once(html, '</head>', tag + '</head>', 'document head')
            else:
                data_end = list(DATA.finditer(html))[0].end()
                html = html[:data_end] + '\n' + tag + html[data_end:]

    if data_payload(html).encode('utf-8') != before_data.encode('utf-8'):
        raise IntegrationError('Refusing output because the id=data bytes changed')
    if html.count('id="player"') != 1 or html.count('window.createStudyAudioPlayer(') != 1:
        raise IntegrationError('Expected exactly one player and one adapter')
    return html


def write_integrated_page(path, html=None, *, collection, check=False):
    """Serialize all cooperating writers, preserving the incoming JSON bytes.

    html=None reads the current page only after acquiring the lock. Builders
    pass their newly constructed HTML instead; no card-source imports occur.
    The persistent lock is separate from the atomically replaced page inode.
    """
    if collection not in PROFILES:
        raise IntegrationError(f'Unsupported collection: {collection}')
    path = Path(path).resolve()
    lock_path = path.with_name('.' + path.name + '.audio.lock')
    with lock_path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            before = path.read_bytes() if path.exists() else None
            if html is None:
                if before is None:
                    raise FileNotFoundError(path)
                source = before.decode('utf-8')
            elif isinstance(html, str):
                source = html
            else:
                raise TypeError('html must be a string or None')
            source_data = data_payload(source).encode('utf-8')
            after = integrate_player(source, collection).encode('utf-8')
            output_data = data_payload(after.decode('utf-8')).encode('utf-8')
            if source_data != output_data:
                raise IntegrationError('Refusing a write because id=data bytes changed')
            changed = before != after
            if check and changed:
                raise IntegrationError(f'{path.name}: shared player needs integration')
            if changed:
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.audio-', suffix='.tmp', delete=False) as output:
                        temporary = output.name
                        output.write(after)
                        output.flush()
                        os.fsync(output.fileno())
                    os.chmod(temporary, path.stat().st_mode if before is not None else 0o644)
                    os.replace(temporary, path)
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
            previous_hash = None
            if before is not None:
                try:
                    previous_hash = hashlib.sha256(data_payload(before.decode('utf-8')).encode('utf-8')).hexdigest()
                except (IntegrationError, UnicodeDecodeError):
                    pass
            return {
                'page': path.name, 'changed': changed, 'lockFile': str(lock_path),
                'beforeDataSha256': previous_hash,
                'inputDataSha256': hashlib.sha256(source_data).hexdigest(),
                'dataSha256': hashlib.sha256(output_data).hexdigest(),
            }
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection', choices=PROFILES)
    parser.add_argument('--check', action='store_true', help='Check that the current page is already integrated')
    args = parser.parse_args()
    path = ROOT / 'reading' / PROFILES[args.collection][0]
    try:
        result = write_integrated_page(path, collection=args.collection, check=args.check)
    except IntegrationError as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
