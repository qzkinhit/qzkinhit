/* 人声和伴奏始终使用独立媒体元素；所有播放入口共用同一组暂停和恢复操作。 */
window.createStudyAudioPlayer = function (options) {
  'use strict';
  const { element: panel, trigger, storage, toast } = options;
  const $ = selector => panel.querySelector(selector);
  const voice = new Audio(), music = new Audio();
  for (const [name, audio] of [['voice', voice], ['music', music]]) {
    audio.preload = 'none';
    audio.setAttribute('playsinline', '');
    audio.setAttribute('webkit-playsinline', '');
    audio.dataset.audioTrack = name;
    audio.hidden = true;
    panel.appendChild(audio);
  }
  const DEFAULT_MUSIC = 'audio/music/quiet-study.m4a';
  const RATES = [0.8, 1, 1.2, 1.5, 1.8, 2];
  const storedRate = Number(storage.get('swipe-rate-v2', 1.2));
  let rate = RATES.includes(storedRate) ? storedRate : 1.2;
  const savedMix = storage.get('swipe-mix-v1', {}) || {};
  const volume = (value, fallback) => typeof value === 'number' && isFinite(value) ? Math.max(0, Math.min(1, value)) : fallback;
  let voiceVolume = volume(savedMix.voice, 1), musicVolume = volume(savedMix.music, 0.22);
  let musicEnabled = savedMix.enabled !== false;
  let active = false, wanted = false, index = -1, entry = null, expectedVoiceSrc = '';
  let voiceAttempt = 0, musicAttempt = 0, musicBroken = false;
  let sleepTimer = null, sleepEnd = 0, sleepMinutes = 0;
  let audioContext = null, voiceGain = null, musicGain = null;
  let customMusicURL = null, musicRevision = 0;
  let databasePromise = null, saveQueue = Promise.resolve();
  const fmt = seconds => isFinite(seconds) && seconds >= 0 ? `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}` : '0:00';
  const setStatus = message => { $('.pstatus').textContent = message || ''; $('.pstatus').hidden = !message; };
  const setMusicStatus = message => { $('.pmusic-status').textContent = message || ''; $('.pmusic-status').hidden = !message; };
  const canPlayMusic = () => active && wanted && musicEnabled && !musicBroken;
  const saveMix = () => storage.set('swipe-mix-v1', { voice: voiceVolume, music: musicVolume, enabled: musicEnabled });

  function syncHeight() {
    if (active) document.body.style.setProperty('--player-height', Math.ceil(panel.getBoundingClientRect().height) + 'px');
  }
  if ('ResizeObserver' in window) new ResizeObserver(syncHeight).observe(panel);
  window.addEventListener('resize', syncHeight);

  function applyVolumes() {
    // iOS 不支持可靠地设置媒体元素音量，使用各自的 GainNode 调整两轨。
    if (voiceGain && musicGain) {
      voice.volume = music.volume = 1;
      voiceGain.gain.setTargetAtTime(voiceVolume, audioContext.currentTime, 0.025);
      musicGain.gain.setTargetAtTime(musicVolume, audioContext.currentTime, 0.025);
    } else {
      voice.volume = voiceVolume;
      music.volume = musicVolume;
    }
    $('[data-volume=voice]').value = Math.round(voiceVolume * 100);
    $('[data-volume=music]').value = Math.round(musicVolume * 100);
    $('[data-level=voice]').textContent = Math.round(voiceVolume * 100) + '%';
    $('[data-level=music]').textContent = Math.round(musicVolume * 100) + '%';
  }

  function prepareAudio(attempt) {
    try {
      if (!audioContext) {
        const Context = window.AudioContext || window.webkitAudioContext;
        if (Context) {
          audioContext = new Context();
          voiceGain = audioContext.createGain();
          musicGain = audioContext.createGain();
          voiceGain.gain.value = voiceVolume;
          musicGain.gain.value = musicVolume;
          audioContext.createMediaElementSource(voice).connect(voiceGain);
          audioContext.createMediaElementSource(music).connect(musicGain);
          voiceGain.connect(audioContext.destination);
          musicGain.connect(audioContext.destination);
          applyVolumes();
          audioContext.addEventListener('statechange', () => {
            if (audioContext.state === 'interrupted' && active && wanted) pauseBoth('播放被系统暂停，点播放可继续。');
          });
        }
      }
      // 支持 Audio Session API 的 Safari 可在锁屏时保持播放用途。
      try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (error) {}
      if (audioContext && audioContext.state !== 'running') {
        Promise.resolve(audioContext.resume()).catch(() => {
          if (active && wanted && attempt === voiceAttempt) pauseBoth('音频未能启动，请再点一次播放。');
        });
      }
    } catch (error) {
      if (audioContext) {
        pauseBoth('音频未能启动，请刷新页面后重试。');
        return false;
      }
    }
    return true;
  }

  function paintPlayback() {
    const button = $('[data-p=toggle]');
    button.textContent = wanted ? '⏸' : '▶';
    button.title = wanted ? '暂停' : '播放';
    button.setAttribute('aria-label', wanted ? '暂停人声与背景音乐' : '播放人声与背景音乐');
    if ('mediaSession' in navigator) {
      try { navigator.mediaSession.playbackState = active ? (wanted ? 'playing' : 'paused') : 'none'; } catch (error) {}
    }
  }

  function paintRate() {
    const button = $('[data-p=rate]');
    button.textContent = rate + '×';
    button.setAttribute('aria-label', `人声倍速 ${rate} 倍，点击切换`);
    voice.defaultPlaybackRate = voice.playbackRate = rate;
    if ('preservesPitch' in voice) voice.preservesPitch = true;
    music.defaultPlaybackRate = music.playbackRate = 1;
  }

  function paintMusic() {
    const button = $('[data-p=music]');
    button.textContent = musicEnabled ? '已开启' : '已关闭';
    button.setAttribute('aria-pressed', String(musicEnabled));
    button.setAttribute('aria-label', musicEnabled ? '关闭背景音乐' : '开启背景音乐');
  }

  function paintMetadata() {
    if (!entry) return;
    $('.ptitle').textContent = entry.title;
    const download = $('[data-download=voice]');
    download.href = 'audio/hot100-natural/' + encodeURIComponent(entry.id) + '.mp3';
    download.download = entry.id + '-纯人声.mp3';
    download.setAttribute('aria-label', `下载 ${entry.title} 的纯人声`);
    options.markActive(active ? index : -1);
    if ('mediaSession' in navigator && 'MediaMetadata' in window) {
      try { navigator.mediaSession.metadata = new MediaMetadata({ title: entry.title, artist: '自然合成女声 · Hot 100 听题', album: entry.album }); } catch (error) {}
    }
  }

  function paintProgress() {
    const duration = Number.isFinite(voice.duration) ? voice.duration : 0;
    const position = Math.max(0, Math.min(voice.currentTime || 0, duration));
    const seek = $('.pseek');
    seek.disabled = !duration;
    seek.value = duration ? Math.round(position / duration * 1000) : 0;
    seek.style.setProperty('--progress', (duration ? position / duration * 100 : 0) + '%');
    seek.setAttribute('aria-valuetext', `${fmt(position)}，共 ${fmt(duration)}`);
    $('.ptime').textContent = `${fmt(position)} / ${fmt(duration)}`;
    if (active && duration && navigator.mediaSession && navigator.mediaSession.setPositionState) {
      try { navigator.mediaSession.setPositionState({ duration, playbackRate: rate, position }); } catch (error) {}
    }
    if (sleepEnd) { if (!checkSleep()) paintSleep(); }
  }

  function startMusic() {
    if (!canPlayMusic() || !music.paused) return;
    const attempt = ++musicAttempt;
    try {
      Promise.resolve(music.play()).then(() => {
        if (attempt === musicAttempt && canPlayMusic()) setMusicStatus('');
      }).catch(error => {
        if (attempt !== musicAttempt || !canPlayMusic()) return;
        music.pause();
        setMusicStatus(error.name === 'NotAllowedError' ? '背景音乐未能启动，可关闭后重新开启。人声会继续。' : '这首音乐无法播放，可更换音乐或恢复默认。人声会继续。');
      });
    } catch (error) {
      setMusicStatus('这首音乐无法播放，可更换音乐或恢复默认。人声会继续。');
    }
  }

  function pauseBoth(message) {
    wanted = false;
    ++voiceAttempt;
    ++musicAttempt;
    voice.pause();
    music.pause();
    paintPlayback();
    if (message !== undefined) setStatus(message);
  }

  function resumeBoth() {
    if (!active || !entry || checkSleep()) return;
    if (voice.error) { playAt(index, false, true); return; }
    const attempt = ++voiceAttempt;
    wanted = true;
    if (!prepareAudio(attempt)) return;
    setStatus(voice.readyState < 3 ? '正在准备人声…' : '');
    paintPlayback();
    // 同一用户手势内调用两次 play，避免移动端因异步等待丢失播放权限。
    startMusic();
    try {
      Promise.resolve(voice.play()).then(() => {
        if (attempt !== voiceAttempt || !active || !wanted) return;
        if (!voice.paused) setStatus('');
      }).catch(error => {
        // 切题和暂停会使旧的 play Promise 失败，它不能影响当前题目。
        if (attempt !== voiceAttempt || !active || !wanted) return;
        pauseBoth(error.name === 'NotAllowedError' ? '请点播放继续听题。' : '这题人声暂时无法播放，点播放重试或手动切换下一题。');
      });
    } catch (error) {
      if (attempt === voiceAttempt) pauseBoth('这题人声暂时无法播放，点播放重试或手动切换下一题。');
    }
  }

  function playAt(k, scroll, resume) {
    const nextEntry = options.getQuestion(k);
    if (!nextEntry) {
      stop();
      toast(options.getCount() ? '本轮都听完了' : '当前没有可播放的题目');
      return;
    }
    ++voiceAttempt;
    index = k;
    entry = nextEntry;
    wanted = !!resume;
    expectedVoiceSrc = new URL('audio/hot100-natural/' + encodeURIComponent(entry.id) + '.mp3', document.baseURI).href;
    voice.src = expectedVoiceSrc;
    voice.preload = 'metadata';
    voice.load();
    paintRate();
    paintMetadata();
    paintProgress();
    setStatus('');
    if (scroll) options.showQuestion(k);
    if (wanted) resumeBoth();
    else { music.pause(); ++musicAttempt; paintPlayback(); }
  }

  function start(k) {
    if (!options.getCount()) { toast('当前没有可播放的题目'); return; }
    active = true;
    document.body.classList.add('listening');
    document.body.classList.toggle('listening-settings-open', !$('#listening-settings').hidden);
    panel.classList.add('on');
    trigger.classList.add('on');
    trigger.setAttribute('aria-pressed', 'true');
    playAt(k === undefined ? Math.min(options.getCurrentIndex(), options.getCount() - 1) : k, false, true);
    syncHeight();
  }

  function stop() {
    active = false;
    pauseBoth('');
    clearTimeout(sleepTimer);
    sleepTimer = null; sleepEnd = 0; sleepMinutes = 0;
    paintSleep();
    document.body.classList.remove('listening');
    document.body.classList.remove('listening-settings-open');
    panel.classList.remove('on');
    trigger.classList.remove('on');
    trigger.setAttribute('aria-pressed', 'false');
    options.markActive(-1);
  }

  function paintSleep() {
    const button = $('[data-p=sleep]');
    const remaining = sleepEnd ? Math.max(1, Math.ceil((sleepEnd - Date.now()) / 60000)) : 0;
    button.textContent = remaining ? `${remaining} 分钟` : '定时';
    button.classList.toggle('sleep-on', !!remaining);
    button.setAttribute('aria-label', remaining ? `睡眠定时，约 ${remaining} 分钟后暂停，点击切换` : '睡眠定时，当前关闭，点击设置');
  }

  function checkSleep() {
    if (!sleepEnd || Date.now() < sleepEnd) return false;
    clearTimeout(sleepTimer);
    sleepTimer = null; sleepEnd = 0; sleepMinutes = 0;
    pauseBoth('睡眠定时已结束，点播放可继续。');
    paintSleep();
    return true;
  }

  function seekTo(seconds) {
    if (!Number.isFinite(voice.duration) || !voice.duration) return;
    voice.currentTime = Math.max(0, Math.min(voice.duration, seconds));
    paintProgress();
  }

  voice.addEventListener('play', () => { if (!active || !wanted) voice.pause(); else paintPlayback(); });
  voice.addEventListener('playing', () => { if (active && wanted) { setStatus(''); startMusic(); } });
  voice.addEventListener('pause', () => {
    // 系统或耳机暂停主音轨时，伴奏也必须停止。自然结束由 ended 负责连播。
    if (active && wanted && voice.paused && !voice.ended) pauseBoth('');
  });
  voice.addEventListener('ended', () => {
    if (active && wanted && voice.ended && voice.src === expectedVoiceSrc && !checkSleep()) playAt(index + 1, true, true);
  });
  voice.addEventListener('error', () => {
    if (active && voice.error && voice.src === expectedVoiceSrc) pauseBoth('这题人声暂时无法加载，点播放重试或手动切换下一题。');
  });
  for (const event of ['timeupdate', 'durationchange', 'loadedmetadata']) voice.addEventListener(event, paintProgress);
  music.addEventListener('play', () => { if (!canPlayMusic()) music.pause(); });
  music.addEventListener('error', () => {
    if (!music.error) return;
    musicBroken = true;
    music.pause();
    setMusicStatus('这首音乐无法加载，可更换音乐或恢复默认。');
  });

  function openDatabase() {
    if (databasePromise) return databasePromise;
    databasePromise = new Promise((resolve, reject) => {
      if (!window.indexedDB) { reject(new Error('storage unavailable')); return; }
      const request = indexedDB.open('hot100-listening-v1', 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('music')) request.result.createObjectStore('music'); };
      request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error('storage blocked'));
    });
    return databasePromise;
  }

  function musicTransaction(db, mode, operation) {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction('music', mode);
      const request = operation(transaction.objectStore('music'));
      transaction.oncomplete = () => resolve(request.result);
      const failure = () => reject((request.readyState === 'done' && request.error) || transaction.error || new Error('storage aborted'));
      transaction.onerror = failure;
      transaction.onabort = failure;
    });
  }

  function rememberMusic(record, revision) {
    saveQueue = saveQueue.catch(() => {}).then(async () => {
      if (revision !== musicRevision) return;
      const db = await openDatabase();
      if (revision !== musicRevision) return;
      try {
        await musicTransaction(db, 'readwrite', store => record ? store.put(record, 'selected') : store.delete('selected'));
      } catch (error) {
        // 部分 WebKit 会拒绝直接保存 File。小文件改存原始字节，避免放弃本地记忆。
        if (!record || !['UnknownError', 'DataCloneError'].includes(error?.name) || record.file.size > 64 * 1024 * 1024) throw error;
        const bytes = await record.file.arrayBuffer();
        if (revision !== musicRevision) return;
        await musicTransaction(db, 'readwrite', store => store.put({ bytes, type: record.file.type, name: record.name }, 'selected'));
      }
      if (revision === musicRevision) $('.pstorage').textContent = record ? '已保存在这个浏览器，下次自动恢复。清除网站数据后需重新选择。' : '已恢复默认伴奏。自选音乐只保存在这个浏览器，不会上传。';
    }).catch(() => {
      if (revision === musicRevision) $('.pstorage').textContent = record ? '当前音乐仅本次打开有效，浏览器未能保存文件。音乐不会上传。' : '当前已恢复默认，浏览器未能保存此设置。';
    });
  }

  function useMusic(file, name) {
    ++musicAttempt;
    music.pause();
    const previousURL = customMusicURL;
    customMusicURL = file ? URL.createObjectURL(file) : null;
    music.src = customMusicURL || DEFAULT_MUSIC;
    music.loop = true;
    music.playbackRate = music.defaultPlaybackRate = 1;
    musicBroken = false;
    music.load();
    if (previousURL) URL.revokeObjectURL(previousURL);
    $('.pmusic-name').textContent = file ? `当前音乐 · ${name}` : '轻柔学习伴奏';
    const download = $('[data-download=music]');
    download.href = music.src;
    download.download = file ? name : 'quiet-study.m4a';
    download.setAttribute('aria-label', file ? `下载纯背景音乐 ${name}` : '下载默认纯背景音乐');
    setMusicStatus('');
    if (canPlayMusic()) startMusic();
  }

  $('#listening-music-file').addEventListener('change', event => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    if (!file.type.startsWith('audio/') && !/\.(mp3|m4a|aac|wav|ogg|oga|flac|webm|aif|aiff|opus)$/i.test(file.name)) { toast('请选择一个音频文件'); return; }
    const revision = ++musicRevision;
    useMusic(file, file.name);
    $('.pstorage').textContent = '音乐已替换，正在保存到这个浏览器。文件不会上传。';
    rememberMusic({ file, name: file.name }, revision);
  });

  panel.addEventListener('input', event => {
    if (event.target.matches('[data-volume]')) {
      const value = Number(event.target.value) / 100;
      if (event.target.dataset.volume === 'voice') voiceVolume = volume(value, 1);
      else musicVolume = volume(value, 0.22);
      applyVolumes(); saveMix();
    } else if (event.target.matches('.pseek')) seekTo(Number(event.target.value) / 1000 * voice.duration);
  });

  function setSettings(open) {
    $('#listening-settings').hidden = !open;
    document.body.classList.toggle('listening-settings-open', active && open);
    $('[data-p=settings]').setAttribute('aria-expanded', String(open));
    $('[data-p=settings]').textContent = open ? '收起设置 ▴' : '声音与下载 ▾';
    syncHeight();
  }

  panel.addEventListener('click', event => {
    const button = event.target.closest('[data-p]');
    if (!button) return;
    switch (button.dataset.p) {
      case 'toggle': wanted ? pauseBoth('') : resumeBoth(); break;
      case 'next': playAt(index + 1, true, true); break;
      case 'prev': if (voice.currentTime > 5) seekTo(0); else playAt(Math.max(0, index - 1), true, true); break;
      case 'back': seekTo(voice.currentTime - 10); break;
      case 'rate': rate = RATES[(RATES.indexOf(rate) + 1) % RATES.length]; storage.set('swipe-rate-v2', rate); paintRate(); paintProgress(); break;
      case 'sleep': {
        const values = [0, 15, 30, 60];
        sleepMinutes = values[(values.indexOf(sleepMinutes) + 1) % values.length];
        clearTimeout(sleepTimer);
        sleepEnd = sleepMinutes ? Date.now() + sleepMinutes * 60000 : 0;
        sleepTimer = sleepMinutes ? setTimeout(checkSleep, sleepMinutes * 60000) : null;
        paintSleep();
        toast(sleepMinutes ? `${sleepMinutes} 分钟后暂停人声和音乐` : '已关闭睡眠定时');
        break;
      }
      case 'settings': setSettings($('#listening-settings').hidden); break;
      case 'music':
        musicEnabled = !musicEnabled; paintMusic(); saveMix();
        if (musicEnabled) { if (musicBroken) { musicBroken = false; music.load(); } if (wanted) { prepareAudio(voiceAttempt); startMusic(); } }
        else { ++musicAttempt; music.pause(); setMusicStatus(''); }
        break;
      case 'restore-music': {
        const revision = ++musicRevision;
        useMusic(null, '');
        $('.pstorage').textContent = '已恢复默认伴奏，正在保存设置。';
        rememberMusic(null, revision);
        break;
      }
      case 'close': stop(); trigger.focus({ preventScroll: true }); break;
    }
  });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('#listening-settings').hidden) { setSettings(false); $('[data-p=settings]').focus(); }
  });

  if ('mediaSession' in navigator) {
    const set = (action, handler) => { try { navigator.mediaSession.setActionHandler(action, handler); } catch (error) {} };
    set('play', () => active ? resumeBoth() : start());
    set('pause', () => pauseBoth(''));
    set('stop', stop);
    set('nexttrack', () => { if (active) playAt(index + 1, true, true); });
    set('previoustrack', () => { if (active) playAt(Math.max(0, index - 1), true, true); });
    set('seekbackward', event => seekTo(voice.currentTime - (event.seekOffset || 10)));
    set('seekforward', event => seekTo(voice.currentTime + (event.seekOffset || 10)));
    set('seekto', event => { if (Number.isFinite(event.seekTime)) seekTo(event.seekTime); });
  }
  trigger.setAttribute('aria-label', '开始或关闭连播听题');
  trigger.setAttribute('aria-pressed', 'false');
  trigger.addEventListener('click', () => { if (active) stop(); else { start(); if (active) toast('连播已开始，播完自动下一题'); } });
  window.addEventListener('pagehide', () => pauseBoth(''));
  document.addEventListener('visibilitychange', () => {
    checkSleep();
    if (document.visibilityState === 'visible' && active && wanted && audioContext && audioContext.state !== 'running') pauseBoth('播放被系统暂停，点播放可继续。');
  });

  useMusic(null, '');
  applyVolumes(); paintRate(); paintMusic(); paintPlayback();
  openDatabase().then(db => musicTransaction(db, 'readonly', store => store.get('selected'))).then(record => {
    if (musicRevision || !record) return;
    const file = record.file instanceof Blob ? record.file : record.bytes instanceof ArrayBuffer ? new Blob([record.bytes], { type: record.type || 'audio/mpeg' }) : null;
    if (!file) return;
    useMusic(file, record.name || '本地背景音乐');
    $('.pstorage').textContent = '已从这个浏览器恢复音乐。清除网站数据后需重新选择。';
  }).catch(() => {});

  return {
    toggleFor(k) { if (active && index === k && entry && options.getQuestion(k)?.id === entry.id) wanted ? pauseBoth('') : resumeBoth(); else start(k); },
    follow(k) {
      if (!active) return;
      const question = options.getQuestion(k);
      if (!question) { stop(); return; }
      if (k !== index || !entry || question.id !== entry.id) playAt(k, false, wanted);
      else { entry = question; paintMetadata(); }
    },
    stop
  };
};
