/* ═══════════════════════════════════════════════════
   JARVIS v3.0 — Voice-First Voice Module
   Voice is ALWAYS ACTIVE (no toggle/mode needed)
   PASSIVE: wake word detection, low CPU
   ACTIVE:  continuous conversation until dismissal
   ═══════════════════════════════════════════════════ */

const Voice = (() => {
  let recognition = null;
  let isActive = false;
  let isInitialized = false;
  let audioContext = null;
  let analyser = null;
  let mediaStream = null;

  let idleTimer = null;
  let IDLE_TIMEOUT = 30000;

  let onResultCallback = null;
  let onErrorCallback = null;

  const DISMISSAL_PHRASES = [
    'bye', 'goodbye', 'thank you', 'thanks', 'sleep',
    'stop listening', 'go to sleep', 'exit'
  ];

  function isDismissal(text) {
    const lower = text.toLowerCase().trim();
    return DISMISSAL_PHRASES.some(p => lower.includes(p));
  }

  function resetIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      if (isActive) {
        isActive = false;
        updateHUD();
      }
    }, IDLE_TIMEOUT);
  }

  function updateHUD() {
    const statusEl = document.getElementById('voice-status');
    const indicator = document.getElementById('voice-indicator');
    const textEl = document.getElementById('voice-status-text');
    const hudCanvas = document.getElementById('hud-canvas');
    const dockIndicator = document.getElementById('dock-voice-indicator');

    if (statusEl) {
      statusEl.classList.toggle('active', isActive);
      statusEl.classList.toggle('passive', !isActive);
    }

    if (textEl) {
      textEl.textContent = isActive ? 'Listening...' : 'Listening for "I am back"...';
    }

    if (indicator) {
      indicator.style.background = isActive ? 'var(--pri)' : 'var(--text-dim)';
    }

    if (dockIndicator) {
      dockIndicator.style.background = isActive
        ? 'linear-gradient(135deg, rgba(110,243,255,0.3), rgba(61,216,247,0.15))'
        : 'linear-gradient(135deg, rgba(110,243,255,0.1), rgba(61,216,247,0.05))';
      dockIndicator.style.borderColor = isActive ? 'var(--pri)' : 'var(--text-dim)';
    }

    if (hudCanvas && typeof HUD !== 'undefined') {
      HUD.setVoiceState(isActive ? 'active' : 'passive');
    }
  }

  function onResult(e) {
    const raw = e.results[0][0].transcript;
    const confidence = e.results[0][0].confidence;

    resetIdleTimer();

    if (isActive && isDismissal(raw)) {
      isActive = false;
      updateHUD();
      if (onResultCallback) onResultCallback('DISMISSAL', raw);
      return;
    }

    if (!isActive && (raw.toLowerCase().includes('hey jarvis') || raw.toLowerCase().includes('i am back') || raw.toLowerCase().includes('im back') || raw.toLowerCase().includes('jarvis') || raw.toLowerCase().includes('ok jarvis'))) {
      isActive = true;
      updateHUD();
      if (onResultCallback) onResultCallback('WAKE', raw);
      resetIdleTimer();
      return;
    }

    if (isActive) {
      if (onResultCallback) onResultCallback('COMMAND', raw);
      resetIdleTimer();
    }
  }

  function onEnd() {
    if (isActive) {
      try { recognition && recognition.start(); } catch (_) {}
    }
  }

  function onError(e) {
    if (onErrorCallback) onErrorCallback(e.error || e.message);
  }

  function init() {
    if (isInitialized) return;
    isInitialized = true;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      console.warn('SpeechRecognition API not available');
      return;
    }

    recognition = new SR();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';
  }

  function start() {
    if (!recognition) return;
    try {
      recognition.onresult = onResult;
      recognition.onerror = onError;
      recognition.onend = onEnd;
      recognition.start();
      updateHUD();
    } catch (e) {
      console.error('Voice start error:', e);
    }
  }

  function stop() {
    if (!recognition) return;
    try { recognition.stop(); } catch (_) {}
    if (idleTimer) clearTimeout(idleTimer);
  }

  function setMode(mode) {
    if (mode === 'active') {
      isActive = true;
    } else if (mode === 'passive') {
      isActive = false;
    }
    updateHUD();
  }

  function onResult(cb) { onResultCallback = cb; }
  function onError(cb) { onErrorCallback = cb; }

  function isVoiceActive() { return isActive; }

  async function initAudioVisualization() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStream = stream;
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
    } catch (e) {
      console.warn('Audio visualization unavailable:', e);
    }
  }

  function getAudioLevel() {
    if (!analyser) return 0;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    return Math.min(1, (sum / data.length) / 128);
  }

  return {
    init, start, stop, setMode,
    onResult, onError, isVoiceActive,
    initAudioVisualization, getAudioLevel,
    isActive: () => isActive
  };
})();