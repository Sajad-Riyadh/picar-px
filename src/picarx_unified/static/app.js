/* ═══════════════════════════════════════════════════
   PiCar-X Unified Console — app.js
   Redesigned for sidebar/panel layout with open-mic,
   volume slider, autonomous controls, & HUD overlays.
   All backend endpoints preserved from original.
   ═══════════════════════════════════════════════════ */

const CONFIG = {
  driveRepeatMs: 250,
  refreshIntervalMs: 2500,
  maxMessages: 24,
};

const ENDPOINTS = {
  state: "/api/state",
  settings: "/api/settings",
  health: "/api/health",
  drive: "/api/drive",
  driveStop: "/api/drive/stop",
  camera: "/api/camera",
  voiceMode: "/api/voice/mode",
  audioTarget: "/api/audio/target",
  emergencyStop: "/api/emergency-stop",
  emergencyReset: "/api/emergency-reset",
  visionQuestion: "/api/vision/question",
  voiceSocket: "/ws/voice",
};

/* ── Global mutable state ── */
const app = {
  activePanel: "drive",
  session: null,
  settingsDirty: false,
  audioContext: null,
  playbackCursor: 0,
  ws: null,
  socketPromise: null,
  mediaStream: null,
  sourceNode: null,
  workletNode: null,
  monitorNode: null,
  captureActive: false,
  awaitingReply: false,
  openMic: false,         // open-mic mode flag
  recognition: null,
  transcript: "",
  driveInterval: null,
  driveCommand: null,
  activeDriveButton: null,
  activeKey: null,
  refreshPromise: null,
  refreshQueued: false,
  volume: 80,
};

/* ── DOM cache ── */
const el = {};

function $(selector) { return document.querySelector(selector); }
function $$(selector) { return [...document.querySelectorAll(selector)]; }

function cacheDom() {
  // Navigation
  el.navBtns        = $$(".nav-btn");
  el.panels         = $$(".ctrl-panel");

  // Status strip
  el.hwChip         = $("#hw-chip");
  el.modeChip       = $("#mode-chip");
  el.safetyChip     = $("#safety-chip");
  el.micChip        = $("#mic-chip");
  el.voiceChip      = $("#voice-chip");
  el.detectChip     = $("#detect-chip");

  // Connection
  el.connDot        = $("#conn-dot");
  el.connLabel      = $("#conn-label");

  // E-Stop
  el.estopFab       = $("#estop-fab");
  el.estopBanner    = $("#estop-banner");
  el.estopResetBtn  = $("#estop-reset-btn");

  // HUD
  el.hudDrive       = $("#hud-drive");
  el.hudCam         = $("#hud-cam");
  el.hudPerson      = $("#hud-person");
  el.hudAuto        = $("#hud-auto");
  el.visionSummary  = $("#vision-summary");

  // Drive
  el.driveBadge     = $("#drive-badge");
  el.driveSpeedSlider = $("#drive-speed-slider");
  el.driveSpeedValue = $("#drive-speed-value");
  el.stopBtn        = $("#stop-btn");
  el.lastErrorLabel = $("#last-error-label");
  el.dpadBtns       = $$(".dpad[data-speed-sign]");

  // Camera
  el.centerCameraBtn = $("#center-camera-btn");
  el.camUp          = $("#cam-up");
  el.camDown        = $("#cam-down");
  el.camLeft        = $("#cam-left");
  el.camRight       = $("#cam-right");
  el.camCenter      = $("#cam-center");
  el.panSlider      = $("#pan-slider");
  el.tiltSlider     = $("#tilt-slider");
  el.panValue       = $("#pan-value");
  el.tiltValue      = $("#tilt-value");
  el.cameraFollowToggle = $("#camera-follow-toggle");
  el.presetChips    = $$(".preset-chip");

  // Voice
  el.voiceModeSelect     = $("#voice-mode-select");
  el.audioTargetSelect   = $("#audio-target-select");
  el.micToggleBtn        = $("#mic-toggle-btn");
  el.pushToTalkBtn       = $("#push-to-talk-btn");
  el.openMicToggle       = $("#open-mic-toggle");
  el.micStateBadge       = $("#mic-state-badge");
  el.volumeSlider        = $("#volume-slider");
  el.volumeValue         = $("#volume-value");
  el.speechStatus        = $("#speech-status");
  el.messageCountLabel   = $("#message-count-label");
  el.messages            = $("#messages");

  // AI / Vision
  el.personDetectedLabel = $("#person-detected-label");
  el.aiProviderLabel     = $("#ai-provider-label");
  el.visionUpdatedLabel  = $("#vision-updated-label");
  el.lastBehaviorLabel   = $("#last-behavior-label");
  el.lastGreetingLabel   = $("#last-greeting-label");
  el.autoTrackingToggle  = $("#auto-tracking-toggle");
  el.greetingEnabledToggle = $("#greeting-enabled-toggle");
  el.greetingModeSelect  = $("#greeting-mode-select");
  el.visionForm          = $("#vision-form");
  el.visionQuestion      = $("#vision-question");
  el.visionAnswer        = $("#vision-answer");
  el.promptChips         = $$(".prompt-chip");

  // Settings
  el.settingsForm             = $("#settings-form");
  el.greetingTextInput        = $("#greeting-text-input");
  el.greetingEnabledInput     = $("#greeting-enabled-input");
  el.autoTrackingInput        = $("#auto-tracking-input");
  el.settingsGreetingMode     = $("#settings-greeting-mode");
  el.startupVoiceModeSelect   = $("#startup-voice-mode-select");
  el.startupAudioTargetSelect = $("#startup-audio-target-select");
  el.cameraStepInput          = $("#camera-step-input");
  el.cameraStepValue          = $("#camera-step-value");
  el.settingsEstopBtn         = $("#settings-estop-btn");
  el.settingsResetBtn         = $("#settings-reset-btn");
  el.settingsSaveStatus       = $("#settings-save-status");
}

/* ══════════════════════════════════════════
   UTILITIES
   ══════════════════════════════════════════ */

function titleCase(value) {
  return String(value ?? "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function signed(v) { return v > 0 ? `+${v}` : `${v}`; }

function formatTimestamp(value) {
  if (!value) return "Pending";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Pending";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", second: "2-digit" }).format(d);
}

function formatDriveSummary(drive) {
  if (!drive || drive.speed === 0) return "Stopped";
  const dir = drive.speed > 0 ? "Fwd" : "Rev";
  return drive.steering === 0
    ? `${dir} ${Math.abs(drive.speed)}`
    : `${dir} ${Math.abs(drive.speed)} / str ${signed(drive.steering)}`;
}

function defaultVoiceHint(mode) {
  if (mode === "relay") return "Relay mode streams your browser mic to the speaker target.";
  if (mode === "ai_reply") return "AI Reply records one spoken turn, then speaks the Gemini reply.";
  return "Mic idle. Choose Relay or AI Reply to open the voice path.";
}

/* ── DOM helpers ── */

function setButtonActive(button, active) {
  if (!button) return;
  button.dataset.active = active ? "true" : "false";
  button.setAttribute("aria-pressed", active ? "true" : "false");
}

function setSpeechStatus(msg, tone = "neutral") {
  if (el.speechStatus) {
    el.speechStatus.textContent = msg;
    el.speechStatus.dataset.tone = tone;
  }
}

function setSettingsStatus(msg, tone = "neutral") {
  if (el.settingsSaveStatus) {
    el.settingsSaveStatus.textContent = msg;
    el.settingsSaveStatus.dataset.tone = tone;
  }
}

function syncRangeReadouts() {
  if (el.panValue)         el.panValue.textContent = `${el.panSlider.value}°`;
  if (el.tiltValue)        el.tiltValue.textContent = `${el.tiltSlider.value}°`;
  if (el.driveSpeedValue)  el.driveSpeedValue.textContent = `${el.driveSpeedSlider.value}%`;
  if (el.cameraStepValue)  el.cameraStepValue.textContent = `${el.cameraStepInput.value}°`;
  if (el.volumeValue)      el.volumeValue.textContent = `${el.volumeSlider.value}%`;
}

function updateMessageCount() {
  const count = el.messages.childElementCount;
  el.messageCountLabel.textContent = `${count}`;
}

function updateMicBadge() {
  const badge = el.micStateBadge;
  if (!badge) return;
  if (app.captureActive) {
    badge.textContent = "Listening";
    badge.dataset.state = "listening";
  } else if (app.openMic && app.ws?.readyState === WebSocket.OPEN) {
    badge.textContent = "Ready";
    badge.dataset.state = "on";
  } else {
    badge.textContent = "Off";
    badge.dataset.state = "off";
  }
  // Status strip chip
  if (el.micChip) {
    if (app.captureActive) {
      el.micChip.textContent = "🎤 Live";
      el.micChip.dataset.tone = "active";
    } else {
      el.micChip.textContent = "🎤 Off";
      el.micChip.dataset.tone = "neutral";
    }
  }
}

/* ── Message log ── */

function logMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message message-${role}`;

  const head = document.createElement("div");
  head.className = "message-head";

  const pill = document.createElement("span");
  pill.className = "role-pill";
  pill.textContent = titleCase(role);

  const time = document.createElement("span");
  time.className = "message-time";
  time.textContent = formatTimestamp(new Date().toISOString());

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  head.append(pill, time);
  row.append(head, body);
  el.messages.prepend(row);

  while (el.messages.childElementCount > CONFIG.maxMessages) {
    el.messages.lastElementChild?.remove();
  }
  updateMessageCount();
}

/* ══════════════════════════════════════════
   API
   ══════════════════════════════════════════ */

async function api(path, options = {}) {
  const headers = {
    ...(options.json !== undefined ? { "Content-Type": "application/json" } : {}),
    ...(options.headers ?? {}),
  };
  const response = await fetch(path, {
    ...options,
    headers,
    body: options.json !== undefined ? JSON.stringify(options.json) : options.body,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return response.json().catch(() => ({}));
}

async function applySessionAction(path, json) {
  const session = await api(path, { method: "POST", ...(json !== undefined ? { json } : {}) });
  render(session);
  return session;
}

/* ══════════════════════════════════════════
   PANEL NAVIGATION
   ══════════════════════════════════════════ */

function showPanel(name) {
  app.activePanel = name;
  el.navBtns.forEach(b => {
    b.classList.toggle("active", b.dataset.panel === name);
  });
  el.panels.forEach(p => {
    p.hidden = p.id !== `panel-${name}`;
  });
}

/* ══════════════════════════════════════════
   STATE RENDER
   ══════════════════════════════════════════ */

function syncSettingsForm(settings, force = false) {
  if (app.settingsDirty && !force) return;
  el.greetingTextInput.value = settings.greeting_text;
  el.greetingEnabledInput.checked = settings.greeting_enabled;
  el.autoTrackingInput.checked = settings.auto_tracking_enabled;
  el.settingsGreetingMode.value = settings.greeting_mode;
  el.startupVoiceModeSelect.value = settings.startup_voice_mode;
  el.startupAudioTargetSelect.value = settings.startup_audio_target;
  el.cameraStepInput.value = String(settings.camera_step_degrees);
  // Sync AI panel toggles too
  el.cameraFollowToggle.checked = settings.auto_tracking_enabled;
  el.autoTrackingToggle.checked = settings.auto_tracking_enabled;
  el.greetingEnabledToggle.checked = settings.greeting_enabled;
  el.greetingModeSelect.value = settings.greeting_mode;
  syncRangeReadouts();
}

function render(session) {
  app.session = session;
  const estop = session.emergency_stop;
  document.body.dataset.estop = estop ? "active" : "clear";

  // E-Stop banner
  if (el.estopBanner) el.estopBanner.hidden = !estop;

  // Status strip chips
  if (el.safetyChip) {
    el.safetyChip.textContent = estop ? "⚠ E-STOP" : "✓ Safety OK";
    el.safetyChip.dataset.tone = estop ? "danger" : "ok";
  }
  if (el.modeChip) {
    el.modeChip.textContent = estop ? "Halted" : "Manual";
    el.modeChip.dataset.tone = estop ? "danger" : "cool";
  }
  if (el.voiceChip) {
    el.voiceChip.textContent = `🔊 ${titleCase(session.voice_mode)}`;
    el.voiceChip.dataset.tone = session.voice_mode === "mute" ? "neutral" : "cool";
  }
  if (el.detectChip) {
    el.detectChip.textContent = session.person_detected ? "👁 Person" : "👁 Idle";
    el.detectChip.dataset.tone = session.person_detected ? "active" : "neutral";
  }

  // HUD overlays
  if (el.hudDrive) el.hudDrive.textContent = `SPD ${signed(session.drive.speed)} / STR ${signed(session.drive.steering)}`;
  if (el.hudCam)   el.hudCam.textContent = `PAN ${session.camera.pan}° / TILT ${session.camera.tilt}°`;
  if (el.hudPerson) el.hudPerson.hidden = !session.person_detected;
  if (el.hudAuto)   el.hudAuto.hidden = !session.settings.auto_tracking_enabled;

  // Drive panel
  if (el.driveBadge) el.driveBadge.textContent = formatDriveSummary(session.drive);
  if (el.lastErrorLabel) el.lastErrorLabel.textContent = session.last_error || "None";

  // Vision line
  if (el.visionSummary) el.visionSummary.textContent = session.vision.summary;

  // AI / Vision stats
  if (el.personDetectedLabel) el.personDetectedLabel.textContent = session.person_detected ? "Yes" : "No";
  if (el.aiProviderLabel)     el.aiProviderLabel.textContent = titleCase(session.ai_provider);
  if (el.visionUpdatedLabel)  el.visionUpdatedLabel.textContent = formatTimestamp(session.vision.analyzed_at);
  if (el.lastBehaviorLabel)   el.lastBehaviorLabel.textContent = session.last_behavior_action || "None";
  if (el.lastGreetingLabel)   el.lastGreetingLabel.textContent = session.last_greeting_text || "No greeting yet.";

  // Selects sync
  el.voiceModeSelect.value = session.voice_mode;
  el.audioTargetSelect.value = session.audio_target;
  el.panSlider.value = String(session.camera.pan);
  el.tiltSlider.value = String(session.camera.tilt);
  syncRangeReadouts();
  syncSettingsForm(session.settings);

  if (!app.captureActive && !app.awaitingReply) {
    setSpeechStatus(defaultVoiceHint(session.voice_mode), session.voice_mode === "mute" ? "neutral" : "cool");
  }
  updateMicBadge();
}

function renderHealth(health) {
  if (el.hwChip) {
    el.hwChip.textContent = `⚙ ${titleCase(health.hardware_backend)}`;
    el.hwChip.dataset.tone = health.hardware_backend === "mock" ? "warn" : "ok";
  }
  if (el.connDot) el.connDot.dataset.ok = "true";
  if (el.connLabel) el.connLabel.textContent = "Online";
}

async function refreshState() {
  if (app.refreshPromise) {
    app.refreshQueued = true;
    return app.refreshPromise;
  }
  app.refreshPromise = (async () => {
    const [session, health] = await Promise.all([api(ENDPOINTS.state), api(ENDPOINTS.health)]);
    render(session);
    renderHealth(health);
  })();
  try {
    await app.refreshPromise;
  } finally {
    app.refreshPromise = null;
    if (app.refreshQueued) {
      app.refreshQueued = false;
      queueMicrotask(() => refreshState().catch(() => null));
    }
  }
}

/* ══════════════════════════════════════════
   AUDIO — Encoding / Playback
   ══════════════════════════════════════════ */

function base64FromArrayBuffer(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  bytes.forEach(b => { binary += String.fromCharCode(b); });
  return btoa(binary);
}

function bytesFromBase64(encoded) {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function ensureAudioContext() {
  if (!app.audioContext) {
    app.audioContext = new AudioContext();
    await app.audioContext.audioWorklet.addModule("/static/pcm-worklet.js");
  }
  if (app.audioContext.state === "suspended") await app.audioContext.resume();
  return app.audioContext;
}

function getPlaybackGain() {
  return app.volume / 100;
}

async function playRelayChunk(audioBase64, sampleRate) {
  if (!app.session || !["browser", "both"].includes(app.session.audio_target)) return;
  await ensureAudioContext();
  const bytes = bytesFromBase64(audioBase64);
  const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
  const buffer = app.audioContext.createBuffer(1, pcm.length, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
  const source = app.audioContext.createBufferSource();
  source.buffer = buffer;
  const gain = app.audioContext.createGain();
  gain.gain.value = getPlaybackGain();
  source.connect(gain).connect(app.audioContext.destination);
  const startAt = Math.max(app.audioContext.currentTime + 0.01, app.playbackCursor);
  source.start(startAt);
  app.playbackCursor = startAt + buffer.duration;
}

async function playAssistantAudio(audioBase64) {
  if (!app.session || !["browser", "both"].includes(app.session.audio_target)) return;
  await ensureAudioContext();
  const bytes = bytesFromBase64(audioBase64);
  const buffer = await app.audioContext.decodeAudioData(bytes.buffer.slice(0));
  const source = app.audioContext.createBufferSource();
  source.buffer = buffer;
  const gain = app.audioContext.createGain();
  gain.gain.value = getPlaybackGain();
  source.connect(gain).connect(app.audioContext.destination);
  source.start();
}

/* ══════════════════════════════════════════
   VOICE — WebSocket + Capture pipeline
   ══════════════════════════════════════════ */

function teardownCapturePipeline() {
  if (app.sourceNode)  { app.sourceNode.disconnect(); app.sourceNode = null; }
  if (app.workletNode) { app.workletNode.disconnect(); app.workletNode = null; }
  if (app.monitorNode) { app.monitorNode.disconnect(); app.monitorNode = null; }
  if (app.mediaStream) { app.mediaStream.getTracks().forEach(t => t.stop()); app.mediaStream = null; }
}

function closeVoiceSocket(reason = "Client closing") {
  if (!app.ws) return;
  try { app.ws.close(1000, reason); } catch (_) { /* ignore */ }
  app.ws = null;
  app.socketPromise = null;
}

function handleVoiceSocketMessage(payload) {
  if (payload.type === "state")           { render(payload.state); return; }
  if (payload.type === "relay_chunk")     { playRelayChunk(payload.audio, payload.sample_rate).catch(() => null); return; }
  if (payload.type === "assistant_audio") {
    app.awaitingReply = false;
    setSpeechStatus("Assistant audio ready.", "ok");
    playAssistantAudio(payload.audio).catch(() => null);
    return;
  }
  if (payload.type === "assistant_reply") {
    app.awaitingReply = false;
    setSpeechStatus("Assistant reply received.", "ok");
    logMessage("robot", payload.text);
    return;
  }
  if (payload.type === "transcript") { logMessage("you", payload.text); return; }
  if (payload.type === "error") {
    app.awaitingReply = false;
    setSpeechStatus(payload.message, "danger");
  }
}

async function openVoiceSocket() {
  if (app.ws?.readyState === WebSocket.OPEN) return app.ws;
  if (app.socketPromise) return app.socketPromise;

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const url = `${protocol}://${location.host}${ENDPOINTS.voiceSocket}`;
  app.socketPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(url);
    app.ws = socket;
    socket.addEventListener("message", e => {
      const payload = JSON.parse(e.data);
      handleVoiceSocketMessage(payload);
    });
    socket.addEventListener("open", () => resolve(socket), { once: true });
    socket.addEventListener("error", () => reject(new Error("Unable to open voice link.")), { once: true });
    socket.addEventListener("close", () => {
      app.ws = null;
      app.socketPromise = null;
      app.captureActive = false;
      app.awaitingReply = false;
      setButtonActive(el.pushToTalkBtn, false);
      updateMicBadge();
      setSpeechStatus("Voice link closed. Will reconnect on next use.", "neutral");
    });
  });
  try { return await app.socketPromise; }
  finally { app.socketPromise = null; }
}

async function ensureCapturePipeline() {
  await ensureAudioContext();
  if (app.mediaStream && app.workletNode) return;
  app.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  app.sourceNode = app.audioContext.createMediaStreamSource(app.mediaStream);
  app.workletNode = new AudioWorkletNode(app.audioContext, "pcm-capture");
  app.monitorNode = app.audioContext.createGain();
  app.monitorNode.gain.value = 0;

  app.workletNode.port.onmessage = (event) => {
    if (!app.captureActive || !app.ws || app.ws.readyState !== WebSocket.OPEN) return;
    const audio = base64FromArrayBuffer(event.data);
    app.ws.send(JSON.stringify({ type: "pcm_chunk", audio }));
  };

  app.sourceNode.connect(app.workletNode);
  app.workletNode.connect(app.monitorNode);
  app.monitorNode.connect(app.audioContext.destination);
}

function configureSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR || app.recognition) return;
  app.recognition = new SR();
  app.recognition.lang = "en-US";
  app.recognition.continuous = true;
  app.recognition.interimResults = true;
  app.recognition.onresult = (event) => {
    const chunks = [];
    for (let i = event.resultIndex; i < event.results.length; i++) {
      chunks.push(event.results[i][0].transcript);
    }
    app.transcript = chunks.join(" ").trim();
  };
}

async function startTalking() {
  if (app.session?.voice_mode === "mute") {
    setSpeechStatus("Switch voice mode out of Mute before opening the mic.", "neutral");
    return;
  }
  await openVoiceSocket();
  await ensureCapturePipeline();
  configureSpeechRecognition();

  app.transcript = "";
  app.awaitingReply = false;
  app.captureActive = true;
  setButtonActive(el.pushToTalkBtn, true);
  updateMicBadge();

  if (app.session?.voice_mode === "ai_reply" && app.recognition) {
    try { app.recognition.start(); } catch (_) { /* already running */ }
  }
  setSpeechStatus("Listening...", "cool");
}

async function stopTalking() {
  if (!app.captureActive) return;
  app.captureActive = false;
  setButtonActive(el.pushToTalkBtn, false);
  updateMicBadge();

  if (app.recognition) {
    try { app.recognition.stop(); } catch (_) { /* ignore */ }
  }
  if (!app.ws || app.ws.readyState !== WebSocket.OPEN) return;
  if (app.transcript) {
    app.ws.send(JSON.stringify({ type: "transcript", text: app.transcript }));
  }
  app.awaitingReply = app.session?.voice_mode === "ai_reply";
  app.ws.send(JSON.stringify({ type: "commit" }));
  setSpeechStatus(app.awaitingReply ? "Waiting for AI reply..." : "Finishing relay...", "warn");
}

/* ── Open Mic toggle ── */
async function toggleOpenMic(forceOff = false) {
  if (forceOff || app.openMic) {
    // Turn off
    app.openMic = false;
    el.openMicToggle.checked = false;
    el.micToggleBtn.textContent = "🎤 Open Mic";
    el.micToggleBtn.classList.remove("btn-danger");
    el.micToggleBtn.classList.add("btn-accent");
    await stopTalking();
  } else {
    // Turn on
    app.openMic = true;
    el.openMicToggle.checked = true;
    el.micToggleBtn.textContent = "🔴 Mic On — Tap to Stop";
    el.micToggleBtn.classList.remove("btn-accent");
    el.micToggleBtn.classList.add("btn-danger");
    await startTalking();
  }
  updateMicBadge();
}

/* ══════════════════════════════════════════
   DRIVE
   ══════════════════════════════════════════ */

function currentDriveSpeed() { return Number(el.driveSpeedSlider.value); }

function buildDriveCommand(speedSign, steering, source) {
  if (speedSign === 0) return { speed: 0, steering: 0, source };
  return { speed: currentDriveSpeed() * speedSign, steering, source };
}

async function sendDriveCommand(command) { return applySessionAction(ENDPOINTS.drive, command); }

function clearDriveLoop() {
  clearInterval(app.driveInterval);
  app.driveInterval = null;
  app.driveCommand = null;
  if (app.activeDriveButton) {
    setButtonActive(app.activeDriveButton, false);
    app.activeDriveButton = null;
  }
}

async function stopDriveLoop() {
  if (!app.driveInterval && !app.driveCommand) return;
  clearDriveLoop();
  const session = await api(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
  if (session) render(session);
}

async function startDriveLoop(command, button = null) {
  if (app.session?.emergency_stop) {
    setSpeechStatus("Reset emergency stop before driving.", "danger");
    return;
  }
  if (app.driveCommand &&
      app.driveCommand.speed === command.speed &&
      app.driveCommand.steering === command.steering &&
      app.driveCommand.source === command.source) return;
  clearDriveLoop();
  app.driveCommand = command;
  if (button) {
    app.activeDriveButton = button;
    setButtonActive(button, true);
  }
  try {
    await sendDriveCommand(command);
    app.driveInterval = setInterval(() => {
      sendDriveCommand(command).catch(err => {
        clearDriveLoop();
        setSpeechStatus(err.message, "danger");
        api(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
      });
    }, CONFIG.driveRepeatMs);
  } catch (err) {
    clearDriveLoop();
    setSpeechStatus(err.message, "danger");
  }
}

/* ══════════════════════════════════════════
   CAMERA
   ══════════════════════════════════════════ */

async function updateCamera(pan, tilt) {
  await applySessionAction(ENDPOINTS.camera, { pan, tilt });
}

async function moveCameraBy(dPan, dTilt) {
  if (!app.session) return;
  const pan = Number(app.session.camera.pan) + dPan;
  const tilt = Number(app.session.camera.tilt) + dTilt;
  el.panSlider.value = String(pan);
  el.tiltSlider.value = String(tilt);
  syncRangeReadouts();
  await updateCamera(pan, tilt);
}

/* ══════════════════════════════════════════
   VISION Q&A
   ══════════════════════════════════════════ */

async function submitVisionQuestion(question) {
  if (!question) return;
  el.visionAnswer.textContent = "Thinking...";
  try {
    const resp = await api(ENDPOINTS.visionQuestion, { method: "POST", json: { question } });
    el.visionAnswer.textContent = resp.answer;
  } catch (err) {
    el.visionAnswer.textContent = err.message;
  }
}

/* ══════════════════════════════════════════
   SETTINGS
   ══════════════════════════════════════════ */

function mergedSettings(patch = {}) {
  if (!app.session) throw new Error("Robot session not ready.");
  return { ...app.session.settings, ...patch };
}

async function saveSettingsPatch(patch) {
  const session = await applySessionAction(ENDPOINTS.settings, mergedSettings(patch));
  app.settingsDirty = false;
  syncSettingsForm(session.settings, true);
  setSettingsStatus("Settings saved.", "ok");
  return session;
}

function settingsPayloadFromForm() {
  return {
    greeting_text: el.greetingTextInput.value.trim(),
    greeting_enabled: el.greetingEnabledInput.checked,
    greeting_mode: el.settingsGreetingMode.value,
    auto_tracking_enabled: el.autoTrackingInput.checked,
    camera_step_degrees: Number(el.cameraStepInput.value),
    startup_voice_mode: el.startupVoiceModeSelect.value,
    startup_audio_target: el.startupAudioTargetSelect.value,
  };
}

/* ══════════════════════════════════════════
   INPUT HELPERS
   ══════════════════════════════════════════ */

function bindMomentaryPointerControl(node, { start, stop }) {
  let pointerId = null;
  const release = () => {
    if (pointerId === null) return;
    pointerId = null;
    Promise.resolve(stop()).catch(e => setSpeechStatus(e.message, "danger"));
  };
  node.addEventListener("pointerdown", (ev) => {
    if (pointerId !== null || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    pointerId = ev.pointerId;
    try { node.setPointerCapture(ev.pointerId); } catch (_) { /* best effort */ }
    ev.preventDefault();
    Promise.resolve(start(ev)).catch(e => { pointerId = null; setSpeechStatus(e.message, "danger"); });
  });
  node.addEventListener("pointerup", release);
  node.addEventListener("pointercancel", release);
  node.addEventListener("lostpointercapture", release);
  node.addEventListener("contextmenu", e => e.preventDefault());
}

function bindDriveButton(button) {
  const speedSign = Number(button.dataset.speedSign);
  const steering = Number(button.dataset.steering);
  if (speedSign === 0 && steering === 0) {
    button.addEventListener("click", () => stopDriveLoop().catch(() => null));
    return;
  }
  bindMomentaryPointerControl(button, {
    start: () => startDriveLoop(buildDriveCommand(speedSign, steering, "browser"), button),
    stop: () => stopDriveLoop(),
  });
}

function bindKeyboard() {
  const keyMap = {
    w: () => buildDriveCommand(1, 0, "keyboard"),
    a: () => buildDriveCommand(1, -25, "keyboard"),
    d: () => buildDriveCommand(1, 25, "keyboard"),
    s: () => buildDriveCommand(-1, 0, "keyboard"),
  };

  window.addEventListener("keydown", (ev) => {
    const key = ev.key.toLowerCase();
    if (!keyMap[key] || app.activeKey === key || ev.repeat) return;
    // Don't capture keys when typing in an input/select
    if (ev.target.tagName === "INPUT" || ev.target.tagName === "SELECT" || ev.target.tagName === "TEXTAREA") return;
    app.activeKey = key;
    ev.preventDefault();
    startDriveLoop(keyMap[key]()).catch(() => null);
  });

  window.addEventListener("keyup", (ev) => {
    if (ev.key.toLowerCase() !== app.activeKey) return;
    app.activeKey = null;
    stopDriveLoop().catch(() => null);
  });

  window.addEventListener("blur", () => {
    app.activeKey = null;
    stopDriveLoop().catch(() => null);
  });
}

/* ══════════════════════════════════════════
   CLEANUP
   ══════════════════════════════════════════ */

function stopDriveOnUnload() {
  const payload = new Blob(["{}"], { type: "application/json" });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(ENDPOINTS.driveStop, payload);
    return;
  }
  fetch(ENDPOINTS.driveStop, {
    method: "POST", body: "{}", headers: { "Content-Type": "application/json" }, keepalive: true,
  }).catch(() => null);
}

function registerGlobalCleanup() {
  window.addEventListener("beforeunload", () => {
    stopDriveOnUnload();
    teardownCapturePipeline();
    closeVoiceSocket("Browser unloading");
  });
}

/* ══════════════════════════════════════════
   SETTINGS DIRTY TRACKING
   ══════════════════════════════════════════ */

function wireSettingsDirtyTracking() {
  const inputs = [
    el.greetingTextInput, el.greetingEnabledInput, el.autoTrackingInput,
    el.settingsGreetingMode, el.startupVoiceModeSelect, el.startupAudioTargetSelect,
    el.cameraStepInput,
  ];
  inputs.forEach(node => {
    if (!node) return;
    const handler = () => {
      app.settingsDirty = true;
      setSettingsStatus("Unsaved changes.", "warn");
      syncRangeReadouts();
    };
    node.addEventListener("input", handler);
    node.addEventListener("change", handler);
  });
}

/* ══════════════════════════════════════════
   INIT
   ══════════════════════════════════════════ */

async function init() {
  cacheDom();
  showPanel("drive");
  syncRangeReadouts();
  updateMessageCount();

  // ── Navigation
  el.navBtns.forEach(btn => {
    btn.addEventListener("click", () => showPanel(btn.dataset.panel));
  });

  // ── Drive buttons
  el.dpadBtns.forEach(btn => {
    setButtonActive(btn, false);
    bindDriveButton(btn);
  });

  // ── Keyboard
  bindKeyboard();
  registerGlobalCleanup();
  wireSettingsDirtyTracking();

  // ── Initial state load
  await refreshState();

  // ── Voice WebSocket (pre-open)
  openVoiceSocket().catch(err => {
    setSpeechStatus(err.message, "danger");
    logMessage("system", "Voice link will reconnect on next use.");
  });

  // ── E-Stop FAB
  el.estopFab.addEventListener("click", async () => {
    if (app.session?.emergency_stop) {
      await applySessionAction(ENDPOINTS.emergencyReset);
    } else {
      clearDriveLoop();
      await applySessionAction(ENDPOINTS.emergencyStop);
    }
  });
  el.estopResetBtn.addEventListener("click", async () => {
    await applySessionAction(ENDPOINTS.emergencyReset);
  });

  // ── Drive stop button
  el.stopBtn.addEventListener("click", async () => {
    clearDriveLoop();
    await applySessionAction(ENDPOINTS.driveStop);
  });

  // ── Drive speed slider
  el.driveSpeedSlider.addEventListener("input", syncRangeReadouts);

  // ── Voice/Audio selects
  el.voiceModeSelect.addEventListener("change", () => {
    applySessionAction(ENDPOINTS.voiceMode, { mode: el.voiceModeSelect.value });
  });
  el.audioTargetSelect.addEventListener("change", () => {
    applySessionAction(ENDPOINTS.audioTarget, { target: el.audioTargetSelect.value });
  });

  // ── Open Mic toggle button
  el.micToggleBtn.addEventListener("click", () => toggleOpenMic());
  el.openMicToggle.addEventListener("change", () => toggleOpenMic(!el.openMicToggle.checked ? true : false));

  // ── Push-to-talk (momentary)
  bindMomentaryPointerControl(el.pushToTalkBtn, {
    start: () => startTalking(),
    stop: () => {
      // If open-mic is on, don't stop on release
      if (app.openMic) return;
      return stopTalking();
    },
  });

  // ── Volume
  el.volumeSlider.addEventListener("input", () => {
    app.volume = Number(el.volumeSlider.value);
    syncRangeReadouts();
  });

  // ── Camera D-pad
  const camStep = () => app.session?.settings?.camera_step_degrees ?? 5;
  el.camUp.addEventListener("click",     () => moveCameraBy(0, camStep()));
  el.camDown.addEventListener("click",   () => moveCameraBy(0, -camStep()));
  el.camLeft.addEventListener("click",   () => moveCameraBy(-camStep(), 0));
  el.camRight.addEventListener("click",  () => moveCameraBy(camStep(), 0));
  el.camCenter.addEventListener("click", () => {
    el.panSlider.value = "0"; el.tiltSlider.value = "0"; syncRangeReadouts();
    updateCamera(0, 0);
  });
  el.centerCameraBtn.addEventListener("click", () => {
    el.panSlider.value = "0"; el.tiltSlider.value = "0"; syncRangeReadouts();
    updateCamera(0, 0);
  });

  // ── Camera sliders
  el.panSlider.addEventListener("input", syncRangeReadouts);
  el.tiltSlider.addEventListener("input", syncRangeReadouts);
  el.panSlider.addEventListener("change", () => updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch(e => setSpeechStatus(e.message, "danger")));
  el.tiltSlider.addEventListener("change", () => updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch(e => setSpeechStatus(e.message, "danger")));

  // ── Camera presets
  el.presetChips.forEach(btn => {
    btn.addEventListener("click", () => updateCamera(Number(btn.dataset.pan), Number(btn.dataset.tilt)));
  });

  // ── Camera follow toggle
  el.cameraFollowToggle.addEventListener("change", () => {
    saveSettingsPatch({ auto_tracking_enabled: el.cameraFollowToggle.checked });
  });

  // ── AI panel autonomous toggles (instant-save)
  el.autoTrackingToggle.addEventListener("change", () => {
    saveSettingsPatch({ auto_tracking_enabled: el.autoTrackingToggle.checked });
  });
  el.greetingEnabledToggle.addEventListener("change", () => {
    saveSettingsPatch({ greeting_enabled: el.greetingEnabledToggle.checked });
  });
  el.greetingModeSelect.addEventListener("change", () => {
    saveSettingsPatch({ greeting_mode: el.greetingModeSelect.value });
  });

  // ── Vision Q&A
  el.visionForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    submitVisionQuestion(el.visionQuestion.value.trim());
  });
  el.promptChips.forEach(btn => {
    btn.addEventListener("click", () => {
      const p = btn.dataset.prompt ?? "";
      el.visionQuestion.value = p;
      submitVisionQuestion(p);
    });
  });

  // ── Settings form
  el.settingsForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const payload = settingsPayloadFromForm();
    if (!payload.greeting_text) {
      setSettingsStatus("Greeting text cannot be blank.", "danger");
      return;
    }
    try {
      const session = await applySessionAction(ENDPOINTS.settings, payload);
      app.settingsDirty = false;
      syncSettingsForm(session.settings, true);
      setSettingsStatus("Settings saved.", "ok");
    } catch (err) {
      setSettingsStatus(err.message, "danger");
    }
  });

  // ── Settings E-Stop / Reset buttons
  el.settingsEstopBtn.addEventListener("click", async () => {
    clearDriveLoop();
    await applySessionAction(ENDPOINTS.emergencyStop);
  });
  el.settingsResetBtn.addEventListener("click", async () => {
    await applySessionAction(ENDPOINTS.emergencyReset);
  });

  // ── Periodic state refresh
  setInterval(() => refreshState().catch(() => null), CONFIG.refreshIntervalMs);
}

init().catch(err => setSpeechStatus(err.message, "danger"));
