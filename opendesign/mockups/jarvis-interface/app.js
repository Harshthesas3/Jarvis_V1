/* ═══════════════════════════════════════════════════
   JARVIS v3.0 — Voice-First Arc Reactor HUD Core
   Canvas renderer, particles, widgets, API polling
   Voice is DEFAULT — no Voice Mode toggle needed
   ═══════════════════════════════════════════════════ */

const API = (window.location.protocol.startsWith('http') && window.location.port === '8000') ? '' : 'http://127.0.0.1:8000';
const state = { status: 'online', history: [], metrics: {} };

// ─────────────────────────────────────────────
// Arc Reactor HUD Canvas
// ─────────────────────────────────────────────
const HUD = (() => {
  const canvas = document.getElementById('hud-canvas');
  const ctx = canvas.getContext('2d');
  let W, H, cx, cy, frame = 0;
  const dpr = window.devicePixelRatio || 1;

  const RINGS = {
    outer:    { r: 0, stroke: 6,  segments: 96,  color: '#77F0FF', opacity: 0.95, speed: 0.08, dir: 1 },
    tick:     { r: 0, stroke: 2,  ticks: 120,    tickLen: 12, color: '#82F5FF', speed: 1.2 },
    glow:     { r: 0, stroke: 16, color: '#5FEFFF', blur: 16, speed: 1.5 },
    inner:    { r: 0, stroke: 4,  color: '#B8FFFF', speed: 0.3, dir: -1 },
  };

  const particles = [];
  const PARTICLE_COUNT = 48;
  let voiceLevel = 0;
  let voiceState = 'idle';

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    W = rect.width; H = rect.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = W / 2; cy = H / 2;
    const base = Math.min(W, H) * 0.38;
    RINGS.outer.r = base * 1.0;
    RINGS.tick.r  = base * 0.89;
    RINGS.glow.r  = base * 0.75;
    RINGS.inner.r = base * 0.65;
  }

  function initParticles() {
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        angle: Math.random() * Math.PI * 2,
        dist: Math.random() * RINGS.outer.r * 1.1 + RINGS.glow.r * 0.5,
        speed: (Math.random() - 0.5) * 0.003,
        size: Math.random() * 1.5 + 0.3,
        alpha: Math.random() * 0.5 + 0.1,
      });
    }
  }

  function drawSegmentedRing(r, stroke, segments, color, opacity, angle) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    const segLen = (Math.PI * 2) / segments;
    const gap = segLen * 0.3;
    ctx.strokeStyle = color;
    ctx.lineWidth = stroke;
    ctx.globalAlpha = opacity;
    for (let i = 0; i < segments; i++) {
      const a = i * segLen;
      ctx.beginPath();
      ctx.arc(0, 0, r, a + gap / 2, a + segLen - gap / 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawTickRing(r, ticks, tickLen, color, pulseVal) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    for (let i = 0; i < ticks; i++) {
      const a = (i / ticks) * Math.PI * 2;
      const len = tickLen * (0.6 + pulseVal * 0.4);
      ctx.globalAlpha = 0.3 + pulseVal * 0.4;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
      ctx.lineTo(Math.cos(a) * (r + len), Math.sin(a) * (r + len));
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawGlowRing(r, stroke, color, blur, breathe) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.globalAlpha = 0.5 + breathe * 0.3;
    ctx.shadowColor = color;
    ctx.shadowBlur = blur;
    ctx.strokeStyle = color;
    ctx.lineWidth = stroke;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.restore();
  }

  function drawInnerRing(r, stroke, color, angle) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.strokeStyle = color;
    ctx.lineWidth = stroke;
    ctx.globalAlpha = 0.5;
    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.lineWidth = 0.8;
    ctx.globalAlpha = 0.25;
    for (let i = 0; i < 60; i++) {
      const a = (i / 60) * Math.PI * 2;
      const len = i % 5 === 0 ? 6 : 3;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * (r - 2), Math.sin(a) * (r - 2));
      ctx.lineTo(Math.cos(a) * (r - 2 - len), Math.sin(a) * (r - 2 - len));
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawOrangeArc() {
    const start = (150 * Math.PI) / 180;
    const end = (225 * Math.PI) / 180;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = '#F7B733';
    ctx.lineWidth = 5;
    ctx.globalAlpha = 0.85;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(0, 0, RINGS.glow.r + 10, start, end);
    ctx.stroke();
    ctx.restore();
  }

  function drawYellowIndicators() {
    const angles = [258, 266, 274, 282, 290];
    ctx.save();
    ctx.translate(cx, cy);
    ctx.fillStyle = '#FFC247';
    for (const deg of angles) {
      const a = (deg * Math.PI) / 180;
      const x = Math.cos(a) * (RINGS.outer.r - 14);
      const y = Math.sin(a) * (RINGS.outer.r - 14);
      ctx.globalAlpha = 0.7;
      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawMicroTicks() {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = 'rgba(110,243,255,0.12)';
    ctx.lineWidth = 0.5;
    const r = (RINGS.tick.r + RINGS.glow.r) / 2;
    for (let i = 0; i < 200; i++) {
      const a = (i / 200) * Math.PI * 2;
      const len = i % 10 === 0 ? 5 : 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * (r - len), Math.sin(a) * (r - len));
      ctx.lineTo(Math.cos(a) * (r + len), Math.sin(a) * (r + len));
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawCore() {
    const coreR = RINGS.inner.r * 0.55;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.beginPath();
    ctx.arc(0, 0, coreR, 0, Math.PI * 2);
    ctx.fillStyle = '#071116';
    ctx.fill();
    ctx.strokeStyle = '#6EF3FF';
    ctx.lineWidth = 3;
    ctx.globalAlpha = 0.9;
    ctx.stroke();
    ctx.restore();

    const coreGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 0.8);
    coreGlow.addColorStop(0, `rgba(110,243,255,${0.08 + voiceLevel * 0.15})`);
    coreGlow.addColorStop(1, 'transparent');
    ctx.globalAlpha = 1;
    ctx.fillStyle = coreGlow;
    ctx.fillRect(cx - coreR, cy - coreR, coreR * 2, coreR * 2);

    ctx.save();
    ctx.globalAlpha = 0.9 + Math.sin(frame * 0.03) * 0.1;
    ctx.fillStyle = '#FFFFFF';
    ctx.font = `700 ${Math.max(14, coreR * 0.32)}px Orbitron, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = '#6EF3FF';
    ctx.shadowBlur = 12;
    ctx.fillText('J.A.R.V.I.S.', cx, cy);
    ctx.shadowBlur = 0;
    ctx.restore();
  }

  function drawParticles() {
    for (const p of particles) {
      p.angle += p.speed;
      const x = cx + Math.cos(p.angle) * p.dist;
      const y = cy + Math.sin(p.angle) * p.dist;
      ctx.globalAlpha = p.alpha * (0.5 + voiceLevel * 0.5);
      ctx.fillStyle = '#6EF3FF';
      ctx.fillRect(x, y, p.size, p.size);
    }
  }

  function drawBackground() {
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, RINGS.outer.r * 1.4);
    grad.addColorStop(0, 'rgba(110,243,255,0.04)');
    grad.addColorStop(0.4, 'rgba(110,243,255,0.015)');
    grad.addColorStop(1, 'transparent');
    ctx.globalAlpha = 1;
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
  }

  function drawModules() {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.strokeStyle = 'rgba(110,243,255,0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(-20, -RINGS.outer.r - 16); ctx.lineTo(20, -RINGS.outer.r - 16); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-12, -RINGS.outer.r - 22); ctx.lineTo(12, -RINGS.outer.r - 22); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-20, RINGS.outer.r + 16); ctx.lineTo(20, RINGS.outer.r + 16); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-RINGS.outer.r - 16, -12); ctx.lineTo(-RINGS.outer.r - 16, 12); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(RINGS.outer.r + 16, -12); ctx.lineTo(RINGS.outer.r + 16, 12); ctx.stroke();
    ctx.restore();
  }

  function render() {
    frame++;
    ctx.clearRect(0, 0, W, H);

    drawBackground();
    drawParticles();

    const t = frame * 0.01;

    drawSegmentedRing(RINGS.outer.r, RINGS.outer.stroke, RINGS.outer.segments, RINGS.outer.color, RINGS.outer.opacity, t * RINGS.outer.speed * RINGS.outer.dir);

    const tickPulse = 0.5 + Math.sin(t * 1.2) * 0.5;
    drawTickRing(RINGS.tick.r, RINGS.tick.ticks, RINGS.tick.tickLen, RINGS.tick.color, tickPulse);

    drawMicroTicks();

    const breathe = Math.sin(t * 1.5 * 0.3);
    drawGlowRing(RINGS.glow.r, RINGS.glow.stroke, RINGS.glow.color, RINGS.glow.blur, breathe);

    drawOrangeArc();
    drawYellowIndicators();
    drawInnerRing(RINGS.inner.r, RINGS.inner.stroke, RINGS.inner.color, t * RINGS.inner.speed * RINGS.inner.dir);
    drawModules();
    drawCore();

    requestAnimationFrame(render);
  }

  function setVoiceLevel(v) { voiceLevel = Math.min(1, Math.max(0, v)); }
  function setVoiceState(s) { voiceState = s; }

  return { resize, initParticles, render, setVoiceLevel, setVoiceState };
})();

// ─────────────────────────────────────────────
// API communication — returns result for voice
// ─────────────────────────────────────────────
async function sendMessage(text) {
  if (!text || !text.trim()) return '';
  addLog('user', text);
  showCmdLog('user', text);

  const bar = document.getElementById('hud-command-bar');
  if (bar) bar.classList.remove('active');

  showCmdLog('jarvis', 'Processing...');

  try {
    const r = await fetch(`${API}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.trim() })
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const result = d.result || d.output || 'Done.';
    addLog('jarvis', result, d.plan);
    showCmdLog('jarvis', result);
    return result;
  } catch (e) {
    const msg = `Error: ${e.message}`;
    addLog('jarvis', msg);
    showCmdLog('jarvis', msg);
    return msg;
  }
}

function addLog(role, text, plan) {
  state.history.push({ role, text, ts: new Date().toISOString() });
}

function showCmdLog(role, text) {
  const log = document.getElementById('cmd-log');
  if (!log) return;
  const entry = document.createElement('div');
  entry.className = `cmd-log-entry ${role}`;
  entry.textContent = (role === 'user' ? '> ' : '▸ ') + text;
  log.prepend(entry);
  if (log.children.length > 6) log.lastChild.remove();
  setTimeout(() => { if (entry.parentElement) entry.remove(); }, 8000);
}

// ─────────────────────────────────────────────
// Widget updates
// ─────────────────────────────────────────────
function $(id) { return document.getElementById(id); }

function updateClock() {
  const now = new Date();
  const ts = now.toLocaleTimeString('en-US', { hour12: false });
  const el = $('tb-clock');
  if (el) el.textContent = ts;
}

let _metricsAvailable = false;

async function updateTopBar() {
  try {
    const r = await fetch(`${API}/api/metrics`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const m = await r.json();
    if (m.error) throw new Error(m.error);
    state.metrics = m;
    _metricsAvailable = true;
    _renderMetrics(m);
  } catch (_) {
    // API unreachable — nothing to update; simulateStats handles fallback
  }
}

function _renderMetrics(m) {
  const sets = {
    'tb-cpu':    (m.cpu ?? '—') + (m.cpu != null ? '%' : ''),
    'tb-ram':    (m.ram ?? '—') + (m.ram != null ? '%' : ''),
    'tb-bat':    m.battery_pct != null ? Math.round(m.battery_pct) + '%' : '—',
    'tb-dsk':    (m.disk_pct ?? '—') + (m.disk_pct != null ? '%' : ''),
    'tb-netup':  m.net_up != null ? m.net_up + ' MB' : '—',
    'tb-netdn':  m.net_down != null ? m.net_down + ' MB' : '—',
    'power-val': m.battery_pct != null ? Math.round(m.battery_pct) + '%' : '—',
    'power-status': m.battery_charging != null ? (m.battery_charging ? 'Charging' : 'Discharging') : '—',
    'storage-used':  m.disk_used != null ? m.disk_used + ' GB' : '—',
    'storage-total': m.disk_total != null ? m.disk_total + ' GB' : '—',
    'storage-bar':   m.disk_pct != null ? m.disk_pct + '%' : '—',
  };
  for (const [id, val] of Object.entries(sets)) {
    const el = $(id);
    if (el) el.textContent = val;
  }
}

let fakeCPU = 13, fakeRAM = 62, fakeBat = 87;
function simulateStats() {
  // Only run simulated stats when the real API is not available.
  if (_metricsAvailable) return;

  fakeCPU = Math.max(2, Math.min(95, fakeCPU + (Math.random() - 0.5) * 4));
  fakeRAM = Math.max(30, Math.min(90, fakeRAM + (Math.random() - 0.5) * 1));
  fakeBat = Math.max(0, Math.min(100, fakeBat - 0.01));

  const sets = {
    'tb-cpu': Math.round(fakeCPU) + '%',
    'tb-ram': Math.round(fakeRAM) + '%',
    'tb-vol': '80%',
    'tb-bat': Math.round(fakeBat) + '%',
    'tb-dsk': '45%',
    'tb-netup': '1.2 MB/s',
    'tb-netdn': '4.8 MB/s',
    'tb-app': '—',
    'tb-media': '—',
    'dev-app': '—',
    'dev-vol': '80%',
    'dev-brightness': '70%',
    'dev-muted': 'No',
    'net-lan': 'Connected',
    'net-wan': '142ms',
    'power-val': Math.round(fakeBat) + '%',
    'power-status': 'Charging',
    'power-time': '3h 24m',
    'wifi-ssid': 'HomeNetwork',
    'wifi-signal': 'Excellent',
    'wifi-ip': '192.168.1.42',
    'wifi-bar': '99%',
    'wifi-label': '99%',
    'storage-used': '218 GB',
    'storage-total': '500 GB',
    'storage-bar': '45%',
    'disk-read': '120 MB/s',
    'disk-write': '85 MB/s',
    'gpu-name': 'NVIDIA RTX 4070',
    'gpu-load': Math.round(20 + Math.random() * 30) + '%',
    'gpu-vram': '8.2 / 12 GB',
    'gpu-tem': '67°C',
    'music-device': 'Spotify',
    'mc-shuffle': 'Off',
    'mc-repeat': 'Off',
  };

  for (const [id, val] of Object.entries(sets)) {
    const el = $(id);
    if (el) el.textContent = val;
  }
}

// ─────────────────────────────────────────────
// Dock — event delegation (fast, no lag)
// ─────────────────────────────────────────────
function initDock() {
  const dock = document.querySelector('.dock');
  if (!dock) return;
  let lastClick = 0;
  dock.addEventListener('click', e => {
    const item = e.target.closest('.dock-item');
    if (!item) return;
    const now = Date.now();
    if (now - lastClick < 300) return;
    lastClick = now;

    const action = item.dataset.action;
    if (action === 'voice') return;  // Voice is always on, no button needed
    if (action === 'settings') {
      const bar = $('hud-command-bar');
      bar.classList.toggle('active');
      $('hud-input').focus();
      return;
    }
    const map = {
      explorer: 'open file explorer',
      chrome: 'open chrome',
      steam: 'open steam',
      terminal: 'open terminal',
      music: 'play music',
      desktop: 'show desktop',
    };
    sendMessage(map[action] || `open ${action}`);
  });
}

function musicCmd(op, val) {
  sendMessage(`music ${op}${val ? ' ' + val : ''}`);
}

// ─────────────────────────────────────────────
// Command input
// ─────────────────────────────────────────────
function initInput() {
  const input = $('hud-input');
  if (!input) return;
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input.value);
      input.value = '';
    }
    if (e.key === 'Escape') {
      $('hud-command-bar').classList.remove('active');
    }
  });
}

// ─────────────────────────────────────────────
// Media Session API integration for music widget
// ─────────────────────────────────────────────
function initMediaSession() {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: 'No Track',
    artist: 'JARVIS Music',
    album: 'System',
  });
  navigator.mediaSession.setActionHandler('play', () => musicCmd('play'));
  navigator.mediaSession.setActionHandler('pause', () => musicCmd('pause'));
  navigator.mediaSession.setActionHandler('previoustrack', () => musicCmd('previous'));
  navigator.mediaSession.setActionHandler('nexttrack', () => musicCmd('next'));
  navigator.mediaSession.setActionHandler('stop', () => musicCmd('pause'));
}

function updateMusicUI(song, artist, album, playing) {
  const track = $('music-track');
  const artistEl = $('music-artist');
  const albumEl = $('music-album');
  if (track) track.textContent = song || 'No Track';
  if (artistEl) artistEl.textContent = artist || '';
  if (albumEl) albumEl.textContent = album || '';
}

let _musicPollInterval = null;
function startMusicPolling() {
  if (_musicPollInterval) return;
  _musicPollInterval = setInterval(async () => {
    try {
      const r = await fetch(`${API}/api/media/status`);
      if (!r.ok) return;
      const d = await r.json();
      if (d.playing !== undefined) {
        updateMusicUI(d.track, d.artist, d.album, d.playing);
        if ('mediaSession' in navigator) {
          navigator.mediaSession.metadata = new MediaMetadata({
            title: d.track || 'No Track',
            artist: d.artist || 'JARVIS Music',
            album: d.album || 'System',
          });
          navigator.mediaSession.playbackState = d.playing ? 'playing' : 'paused';
        }
      }
    } catch (_) {}
  }, 5000);
}

// ─────────────────────────────────────────────
// SpeechRecognition - Voice-First always-on
// ─────────────────────────────────────────────
let recognition = null;
let isListening = false;
let lastResult = '';

function initSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    console.warn('SpeechRecognition API not available in this browser');
    return;
  }

  recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    const result = event.results[event.results.length - 1];
    const transcript = result[0].transcript;
    const isFinal = result.isFinal;

    if (isFinal && transcript.trim()) {
      lastResult = transcript.trim();
      processVoiceInput(transcript.trim());
    }
  };

  recognition.onerror = (event) => {
    if (event.error === 'no-speech') return;
    if (event.error === 'not-allowed') {
      console.error('Microphone permission denied');
      updateVoiceStatus();
    }
    if (event.error === 'network') {
      console.warn('Speech recognition network error, retrying...');
      setTimeout(startListening, 2000);
    }
  };

  recognition.onend = () => {
    if (isListening) {
      try { recognition.start(); } catch (_) {}
    }
  };
}

async function startListening() {
  if (!recognition) {
    initSpeechRecognition();
    if (!recognition) return;
  }
  try {
    recognition.start();
    isListening = true;
    updateVoiceStatus();
    const hudCanvas = document.getElementById('hud-canvas');
    if (hudCanvas && typeof HUD !== 'undefined') {
      HUD.setVoiceState('active');
    }
    const dockIndicator = document.getElementById('dock-voice-indicator');
    if (dockIndicator) {
      dockIndicator.style.background = 'linear-gradient(135deg, rgba(110,243,255,0.3), rgba(61,216,247,0.15))';
      dockIndicator.style.borderColor = 'var(--pri)';
    }
  } catch (e) {
    console.error('Failed to start speech recognition:', e);
    setTimeout(startListening, 3000);
  }
}

function stopListening() {
  isListening = false;
  if (recognition) {
    try { recognition.stop(); } catch (_) {}
  }
  updateVoiceStatus();
  const dockIndicator = document.getElementById('dock-voice-indicator');
  if (dockIndicator) {
    dockIndicator.style.background = 'linear-gradient(135deg, rgba(110,243,255,0.1), rgba(61,216,247,0.05))';
    dockIndicator.style.borderColor = 'var(--text-dim)';
  }
}

async function processVoiceInput(text) {
  if (!text || !text.trim()) return;

  addLog('user', text);
  showCmdLog('user', text);

  const bar = document.getElementById('hud-command-bar');
  if (bar) bar.classList.remove('active');

  showCmdLog('jarvis', 'Processing...');

  try {
    const r = await fetch(`${API}/api/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.trim() })
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    const result = d.result || d.output || 'Done.';
    addLog('jarvis', result, d.plan);
    showCmdLog('jarvis', result);
  } catch (e) {
    const msg = `Error: ${e.message}`;
    addLog('jarvis', msg);
    showCmdLog('jarvis', msg);
  }
}
async function updateVoiceStatus() {
  const statusEl = $('voice-status');
  const indicator = $('voice-indicator');
  const textEl = $('voice-status-text');
  const dockIndicator = $('dock-voice-indicator');

  try {
    const r = await fetch(`${API}/api/voice/state`);
    if (!r.ok) throw new Error('voice state unavailable');
    const d = await r.json();
    const isActive = d.active;
    if (statusEl) { statusEl.classList.toggle('active', isActive); statusEl.classList.toggle('passive', !isActive); }
    if (textEl) textEl.textContent = isActive ? 'Listening...' : 'Listening for "Hey Jarvis"...';
    if (indicator) indicator.style.background = isActive ? 'var(--pri)' : 'var(--text-dim)';
    if (dockIndicator) {
      dockIndicator.style.background = isActive
        ? 'linear-gradient(135deg, rgba(110,243,255,0.3), rgba(61,216,247,0.15))'
        : 'linear-gradient(135deg, rgba(110,243,255,0.1), rgba(61,216,247,0.05))';
      dockIndicator.style.borderColor = isActive ? 'var(--pri)' : 'var(--text-dim)';
    }
  } catch (_) {
    if (statusEl) { statusEl.classList.remove('active'); statusEl.classList.add('passive'); }
    if (textEl) textEl.textContent = 'Listening for "I am back"...';
    if (indicator) indicator.style.background = 'var(--text-dim)';
  }
}

// ─────────────────────────────────────────────
// Boot - Voice-First: start listening immediately
// ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  HUD.resize();
  HUD.initParticles();
  HUD.render();
  initDock();
  initInput();
  initMediaSession();
  startMusicPolling();
  initSpeechRecognition();
  startListening();
  simulateStats();
  setInterval(updateClock, 1000);
  setInterval(simulateStats, 2000);
  setInterval(updateTopBar, 5000);
  setInterval(updateVoiceStatus, 5000);
  updateClock();

  window.addEventListener('resize', () => HUD.resize());
});

// Expose for voice-mode.js compatibility
window.showCmdLog = showCmdLog;
window.HUD = HUD;