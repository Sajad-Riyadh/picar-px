const CONFIG = {
  driveRepeatMs: 250,
  refreshIntervalMs: 2500,
  maxMessages: 18,
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

const state = {
  activeTab: "drive",
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
  recognition: null,
  transcript: "",
  driveInterval: null,
  driveCommand: null,
  activeDriveButton: null,
  activeKey: null,
  refreshPromise: null,
  refreshQueued: false,
};

const el = {
  tabButtons: [...document.querySelectorAll("[data-tab-button]")],
  tabPanels: [...document.querySelectorAll(".tab-panel")],
  sessionUpdatedLabel: document.querySelector("#session-updated-label"),
  driveStateLabel: document.querySelector("#drive-state-label"),
  cameraStateLabel: document.querySelector("#camera-state-label"),
  estopLabel: document.querySelector("#estop-label"),
  voiceModeLabel: document.querySelector("#voice-mode-label"),
  audioTargetLabel: document.querySelector("#audio-target-label"),
  hardwareLabel: document.querySelector("#hardware-label"),
  systemStatusLabel: document.querySelector("#system-status-label"),
  driveSummaryLabel: document.querySelector("#drive-summary-label"),
  lastErrorLabel: document.querySelector("#last-error-label"),
  driveSpeedSlider: document.querySelector("#drive-speed-slider"),
  driveSpeedValue: document.querySelector("#drive-speed-value"),
  stopButton: document.querySelector("#stop-btn"),
  clearEstop: document.querySelector("#clear-estop-btn"),
  refresh: document.querySelector("#refresh-btn"),
  driveButtons: [...document.querySelectorAll(".drive")],
  visionSummary: document.querySelector("#vision-summary"),
  panSlider: document.querySelector("#pan-slider"),
  tiltSlider: document.querySelector("#tilt-slider"),
  panValue: document.querySelector("#pan-value"),
  tiltValue: document.querySelector("#tilt-value"),
  centerCamera: document.querySelector("#center-camera-btn"),
  cameraCenter: document.querySelector("#camera-center-btn"),
  cameraLeft: document.querySelector("#camera-left-btn"),
  cameraRight: document.querySelector("#camera-right-btn"),
  cameraUp: document.querySelector("#camera-up-btn"),
  cameraDown: document.querySelector("#camera-down-btn"),
  cameraFollowToggle: document.querySelector("#camera-follow-toggle"),
  cameraStepBadge: document.querySelector("#camera-step-badge"),
  presetButtons: [...document.querySelectorAll(".preset-chip")],
  voiceModeSelect: document.querySelector("#voice-mode-select"),
  audioTargetSelect: document.querySelector("#audio-target-select"),
  pushToTalk: document.querySelector("#push-to-talk-btn"),
  speechStatus: document.querySelector("#speech-status"),
  messages: document.querySelector("#messages"),
  messageCountLabel: document.querySelector("#message-count-label"),
  personDetectedLabel: document.querySelector("#person-detected-label"),
  visionUpdatedLabel: document.querySelector("#vision-updated-label"),
  aiProviderLabel: document.querySelector("#ai-provider-label"),
  lastBehaviorLabel: document.querySelector("#last-behavior-label"),
  lastGreetingLabel: document.querySelector("#last-greeting-label"),
  visionForm: document.querySelector("#vision-form"),
  visionQuestion: document.querySelector("#vision-question"),
  visionAnswer: document.querySelector("#vision-answer"),
  promptChips: [...document.querySelectorAll(".prompt-chip")],
  settingsForm: document.querySelector("#settings-form"),
  greetingTextInput: document.querySelector("#greeting-text-input"),
  greetingEnabledInput: document.querySelector("#greeting-enabled-input"),
  autoTrackingInput: document.querySelector("#auto-tracking-input"),
  greetingModeSelect: document.querySelector("#greeting-mode-select"),
  startupVoiceModeSelect: document.querySelector("#startup-voice-mode-select"),
  startupAudioTargetSelect: document.querySelector("#startup-audio-target-select"),
  cameraStepInput: document.querySelector("#camera-step-input"),
  cameraStepValue: document.querySelector("#camera-step-value"),
  settingsSaveStatus: document.querySelector("#settings-save-status"),
};

function titleCase(value) {
  return String(value ?? "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function signed(value) {
  return value > 0 ? `+${value}` : `${value}`;
}

function formatTimestamp(value) {
  if (!value) {
    return "Pending";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Pending";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatDriveSummary(drive) {
  if (!drive || drive.speed === 0) {
    return "Stopped";
  }
  const direction = drive.speed > 0 ? "Forward" : "Reverse";
  if (drive.steering === 0) {
    return `${direction} ${Math.abs(drive.speed)}`;
  }
  return `${direction} ${Math.abs(drive.speed)} / steer ${signed(drive.steering)}`;
}

function formatSystemStatus(session) {
  if (!session) {
    return "Connecting";
  }
  if (session.emergency_stop) {
    return "Safety Hold";
  }
  if (session.browser_connected) {
    return "Browser Linked";
  }
  return "Standby";
}

function defaultVoiceHint(mode) {
  if (mode === "relay") {
    return "Relay mode streams your browser microphone to the selected speaker target.";
  }
  if (mode === "ai_reply") {
    return "AI Reply records one spoken turn, then speaks the Gemini-backed reply.";
  }
  return "Microphone is idle. Choose Relay or AI Reply to open the voice path.";
}

function setButtonActive(button, isActive) {
  if (!button) {
    return;
  }
  button.dataset.active = isActive ? "true" : "false";
  button.setAttribute("aria-pressed", isActive ? "true" : "false");
}

function setSpeechStatus(message, tone = "neutral") {
  el.speechStatus.textContent = message;
  el.speechStatus.dataset.tone = tone;
}

function setSettingsStatus(message, tone = "neutral") {
  el.settingsSaveStatus.textContent = message;
  el.settingsSaveStatus.dataset.tone = tone;
}

function syncRangeReadouts() {
  el.panValue.textContent = `${el.panSlider.value}deg`;
  el.tiltValue.textContent = `${el.tiltSlider.value}deg`;
  el.driveSpeedValue.textContent = `${el.driveSpeedSlider.value}%`;
  el.cameraStepValue.textContent = `${el.cameraStepInput.value}deg`;
}

function updateMessageCount() {
  const count = el.messages.childElementCount;
  el.messageCountLabel.textContent = `${count} ${count === 1 ? "entry" : "entries"}`;
}

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
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return response.json().catch(() => ({}));
}

function showTab(tabName) {
  state.activeTab = tabName;
  el.tabButtons.forEach((button) => {
    button.dataset.active = button.dataset.tabButton === tabName ? "true" : "false";
  });
  el.tabPanels.forEach((panel) => {
    panel.hidden = panel.id !== `tab-${tabName}`;
  });
}

function syncSettingsForm(settings, force = false) {
  if (state.settingsDirty && !force) {
    return;
  }
  el.greetingTextInput.value = settings.greeting_text;
  el.greetingEnabledInput.checked = settings.greeting_enabled;
  el.autoTrackingInput.checked = settings.auto_tracking_enabled;
  el.greetingModeSelect.value = settings.greeting_mode;
  el.startupVoiceModeSelect.value = settings.startup_voice_mode;
  el.startupAudioTargetSelect.value = settings.startup_audio_target;
  el.cameraStepInput.value = String(settings.camera_step_degrees);
  el.cameraFollowToggle.checked = settings.auto_tracking_enabled;
  el.cameraStepBadge.textContent = `${settings.camera_step_degrees}deg`;
  syncRangeReadouts();
}

function render(session) {
  state.session = session;
  document.body.dataset.estop = session.emergency_stop ? "active" : "clear";

  el.sessionUpdatedLabel.textContent = formatTimestamp(session.updated_at);
  el.driveStateLabel.textContent = `${signed(session.drive.speed)} spd / ${signed(session.drive.steering)} str`;
  el.cameraStateLabel.textContent = `P ${signed(session.camera.pan)}deg / T ${signed(session.camera.tilt)}deg`;
  el.estopLabel.textContent = session.emergency_stop ? "Active" : "Clear";
  el.voiceModeLabel.textContent = titleCase(session.voice_mode);
  el.audioTargetLabel.textContent = titleCase(session.audio_target);
  el.systemStatusLabel.textContent = formatSystemStatus(session);
  el.driveSummaryLabel.textContent = formatDriveSummary(session.drive);
  el.lastErrorLabel.textContent = session.last_error || "No active error.";
  el.visionSummary.textContent = session.vision.summary;
  el.visionUpdatedLabel.textContent = formatTimestamp(session.vision.analyzed_at);
  el.aiProviderLabel.textContent = titleCase(session.ai_provider);
  el.personDetectedLabel.textContent = session.person_detected ? "Yes" : "No";
  el.lastBehaviorLabel.textContent = session.last_behavior_action || "No behavior event yet";
  el.lastGreetingLabel.textContent = session.last_greeting_text || "No greeting delivered yet.";
  el.voiceModeSelect.value = session.voice_mode;
  el.audioTargetSelect.value = session.audio_target;
  el.panSlider.value = String(session.camera.pan);
  el.tiltSlider.value = String(session.camera.tilt);
  syncRangeReadouts();
  syncSettingsForm(session.settings);

  if (!state.captureActive && !state.awaitingReply) {
    setSpeechStatus(defaultVoiceHint(session.voice_mode), session.voice_mode === "mute" ? "neutral" : "cool");
  }
}

function renderHealth(health) {
  el.hardwareLabel.textContent = `${titleCase(health.hardware_backend)} / ${titleCase(health.camera_backend)}`;
}

async function refreshState() {
  if (state.refreshPromise) {
    state.refreshQueued = true;
    return state.refreshPromise;
  }
  state.refreshPromise = (async () => {
    const [session, health] = await Promise.all([api(ENDPOINTS.state), api(ENDPOINTS.health)]);
    render(session);
    renderHealth(health);
  })();

  try {
    await state.refreshPromise;
  } finally {
    state.refreshPromise = null;
    if (state.refreshQueued) {
      state.refreshQueued = false;
      queueMicrotask(() => refreshState().catch(() => null));
    }
  }
}

function base64FromArrayBuffer(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

function bytesFromBase64(encoded) {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

async function ensureAudioContext() {
  if (!state.audioContext) {
    state.audioContext = new AudioContext();
    await state.audioContext.audioWorklet.addModule("/static/pcm-worklet.js");
  }
  if (state.audioContext.state === "suspended") {
    await state.audioContext.resume();
  }
  return state.audioContext;
}

function teardownCapturePipeline() {
  if (state.sourceNode) {
    state.sourceNode.disconnect();
    state.sourceNode = null;
  }
  if (state.workletNode) {
    state.workletNode.disconnect();
    state.workletNode = null;
  }
  if (state.monitorNode) {
    state.monitorNode.disconnect();
    state.monitorNode = null;
  }
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
}

function closeVoiceSocket(reason = "Client closing") {
  if (!state.ws) {
    return;
  }
  try {
    state.ws.close(1000, reason);
  } catch (_error) {
    // Ignore close races.
  }
  state.ws = null;
  state.socketPromise = null;
}

function handleVoiceSocketMessage(payload) {
  if (payload.type === "state") {
    render(payload.state);
    return;
  }
  if (payload.type === "relay_chunk") {
    playRelayChunk(payload.audio, payload.sample_rate).catch(() => null);
    return;
  }
  if (payload.type === "assistant_audio") {
    state.awaitingReply = false;
    setSpeechStatus("Assistant audio ready for playback.", "ok");
    playAssistantAudio(payload.audio).catch(() => null);
    return;
  }
  if (payload.type === "assistant_reply") {
    state.awaitingReply = false;
    setSpeechStatus("Assistant reply received.", "ok");
    logMessage("robot", payload.text);
    return;
  }
  if (payload.type === "transcript") {
    logMessage("you", payload.text);
    return;
  }
  if (payload.type === "error") {
    state.awaitingReply = false;
    setSpeechStatus(payload.message, "danger");
  }
}

async function openVoiceSocket() {
  if (state.ws?.readyState === WebSocket.OPEN) {
    return state.ws;
  }
  if (state.socketPromise) {
    return state.socketPromise;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socketUrl = `${protocol}://${window.location.host}${ENDPOINTS.voiceSocket}`;
  state.socketPromise = new Promise((resolve, reject) => {
    const socket = new WebSocket(socketUrl);
    state.ws = socket;

    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      handleVoiceSocketMessage(payload);
    });
    socket.addEventListener("open", () => resolve(socket), { once: true });
    socket.addEventListener("error", () => reject(new Error("Unable to open the voice link.")), {
      once: true,
    });
    socket.addEventListener("close", () => {
      state.ws = null;
      state.socketPromise = null;
      state.captureActive = false;
      state.awaitingReply = false;
      setButtonActive(el.pushToTalk, false);
      setSpeechStatus("Voice link closed. Press and hold again to reconnect.", "neutral");
    });
  });

  try {
    return await state.socketPromise;
  } finally {
    state.socketPromise = null;
  }
}

async function ensureCapturePipeline() {
  await ensureAudioContext();
  if (state.mediaStream && state.workletNode) {
    return;
  }
  state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.sourceNode = state.audioContext.createMediaStreamSource(state.mediaStream);
  state.workletNode = new AudioWorkletNode(state.audioContext, "pcm-capture");
  state.monitorNode = state.audioContext.createGain();
  state.monitorNode.gain.value = 0;

  state.workletNode.port.onmessage = (event) => {
    if (!state.captureActive || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    const audio = base64FromArrayBuffer(event.data);
    state.ws.send(JSON.stringify({ type: "pcm_chunk", audio }));
  };

  state.sourceNode.connect(state.workletNode);
  state.workletNode.connect(state.monitorNode);
  state.monitorNode.connect(state.audioContext.destination);
}

function configureSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition || state.recognition) {
    return;
  }
  state.recognition = new SpeechRecognition();
  state.recognition.lang = "en-US";
  state.recognition.continuous = true;
  state.recognition.interimResults = true;
  state.recognition.onresult = (event) => {
    const chunks = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      chunks.push(event.results[index][0].transcript);
    }
    state.transcript = chunks.join(" ").trim();
  };
}

async function startTalking() {
  if (state.session?.voice_mode === "mute") {
    setSpeechStatus("Switch voice mode out of Mute before opening the microphone.", "neutral");
    return;
  }
  await openVoiceSocket();
  await ensureCapturePipeline();
  configureSpeechRecognition();

  state.transcript = "";
  state.awaitingReply = false;
  state.captureActive = true;
  setButtonActive(el.pushToTalk, true);

  if (state.session?.voice_mode === "ai_reply" && state.recognition) {
    try {
      state.recognition.start();
    } catch (_error) {
      // Recognition may already be active.
    }
  }
  setSpeechStatus("Listening for audio input...", "cool");
}

async function stopTalking() {
  if (!state.captureActive) {
    return;
  }
  state.captureActive = false;
  setButtonActive(el.pushToTalk, false);

  if (state.recognition) {
    try {
      state.recognition.stop();
    } catch (_error) {
      // Ignore stop races.
    }
  }

  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  if (state.transcript) {
    state.ws.send(JSON.stringify({ type: "transcript", text: state.transcript }));
  }
  state.awaitingReply = state.session?.voice_mode === "ai_reply";
  state.ws.send(JSON.stringify({ type: "commit" }));
  setSpeechStatus(state.awaitingReply ? "Waiting for assistant reply..." : "Finishing relay...", "warm");
}

async function playRelayChunk(audioBase64, sampleRate) {
  if (!state.session || !["browser", "both"].includes(state.session.audio_target)) {
    return;
  }
  await ensureAudioContext();
  const bytes = bytesFromBase64(audioBase64);
  const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
  const buffer = state.audioContext.createBuffer(1, pcm.length, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < pcm.length; index += 1) {
    channel[index] = pcm[index] / 32768;
  }
  const source = state.audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(state.audioContext.destination);
  const startAt = Math.max(state.audioContext.currentTime + 0.01, state.playbackCursor);
  source.start(startAt);
  state.playbackCursor = startAt + buffer.duration;
}

async function playAssistantAudio(audioBase64) {
  if (!state.session || !["browser", "both"].includes(state.session.audio_target)) {
    return;
  }
  await ensureAudioContext();
  const bytes = bytesFromBase64(audioBase64);
  const buffer = await state.audioContext.decodeAudioData(bytes.buffer.slice(0));
  const source = state.audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(state.audioContext.destination);
  source.start();
}

async function applySessionAction(path, json) {
  const session = await api(path, {
    method: "POST",
    ...(json !== undefined ? { json } : {}),
  });
  render(session);
  return session;
}

function mergedSettings(patch = {}) {
  if (!state.session) {
    throw new Error("Robot session is not ready yet.");
  }
  return {
    ...state.session.settings,
    ...patch,
  };
}

async function saveSettingsPatch(patch) {
  const session = await applySessionAction(ENDPOINTS.settings, mergedSettings(patch));
  state.settingsDirty = false;
  syncSettingsForm(session.settings, true);
  setSettingsStatus("Settings saved.", "ok");
  return session;
}

async function updateCamera(pan, tilt) {
  await applySessionAction(ENDPOINTS.camera, { pan, tilt });
}

async function moveCameraBy(deltaPan, deltaTilt) {
  if (!state.session) {
    return;
  }
  const pan = Number(state.session.camera.pan) + deltaPan;
  const tilt = Number(state.session.camera.tilt) + deltaTilt;
  el.panSlider.value = String(pan);
  el.tiltSlider.value = String(tilt);
  syncRangeReadouts();
  await updateCamera(pan, tilt);
}

function currentDriveSpeed() {
  return Number(el.driveSpeedSlider.value);
}

function buildDriveCommand(speedSign, steering, source) {
  if (speedSign === 0) {
    return { speed: 0, steering: 0, source };
  }
  return {
    speed: currentDriveSpeed() * speedSign,
    steering,
    source,
  };
}

async function sendDriveCommand(command) {
  return applySessionAction(ENDPOINTS.drive, command);
}

function clearDriveLoop() {
  window.clearInterval(state.driveInterval);
  state.driveInterval = null;
  state.driveCommand = null;
  if (state.activeDriveButton) {
    setButtonActive(state.activeDriveButton, false);
    state.activeDriveButton = null;
  }
}

async function stopDriveLoop() {
  if (!state.driveInterval && !state.driveCommand) {
    return;
  }
  clearDriveLoop();
  const session = await api(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
  if (session) {
    render(session);
  }
}

async function startDriveLoop(command, button = null) {
  if (state.session?.emergency_stop) {
    setSpeechStatus("Reset emergency stop before driving.", "danger");
    return;
  }
  if (
    state.driveCommand &&
    state.driveCommand.speed === command.speed &&
    state.driveCommand.steering === command.steering &&
    state.driveCommand.source === command.source
  ) {
    return;
  }
  clearDriveLoop();
  state.driveCommand = command;
  if (button) {
    state.activeDriveButton = button;
    setButtonActive(button, true);
  }
  try {
    await sendDriveCommand(command);
    state.driveInterval = window.setInterval(() => {
      sendDriveCommand(command).catch((error) => {
        clearDriveLoop();
        setSpeechStatus(error.message, "danger");
        api(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
      });
    }, CONFIG.driveRepeatMs);
  } catch (error) {
    clearDriveLoop();
    setSpeechStatus(error.message, "danger");
  }
}

function bindMomentaryPointerControl(node, { start, stop }) {
  let pointerId = null;

  const release = () => {
    if (pointerId === null) {
      return;
    }
    pointerId = null;
    Promise.resolve(stop()).catch((error) => setSpeechStatus(error.message, "danger"));
  };

  node.addEventListener("pointerdown", (event) => {
    if (pointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) {
      return;
    }
    pointerId = event.pointerId;
    try {
      node.setPointerCapture(event.pointerId);
    } catch (_error) {
      // Best effort.
    }
    event.preventDefault();
    Promise.resolve(start(event)).catch((error) => {
      pointerId = null;
      setSpeechStatus(error.message, "danger");
    });
  });

  node.addEventListener("pointerup", release);
  node.addEventListener("pointercancel", release);
  node.addEventListener("lostpointercapture", release);
  node.addEventListener("contextmenu", (event) => event.preventDefault());
}

function bindDriveButton(button) {
  const speedSign = Number(button.dataset.speedSign);
  const steering = Number(button.dataset.steering);
  if (speedSign === 0 && steering === 0) {
    button.addEventListener("click", () => {
      stopDriveLoop().catch(() => null);
    });
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

  window.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if (!keyMap[key] || state.activeKey === key || event.repeat) {
      return;
    }
    state.activeKey = key;
    event.preventDefault();
    startDriveLoop(keyMap[key]()).catch(() => null);
  });

  window.addEventListener("keyup", (event) => {
    if (event.key.toLowerCase() !== state.activeKey) {
      return;
    }
    state.activeKey = null;
    stopDriveLoop().catch(() => null);
  });

  window.addEventListener("blur", () => {
    state.activeKey = null;
    stopDriveLoop().catch(() => null);
    stopTalking().catch(() => null);
  });
}

async function submitVisionQuestion(question) {
  if (!question) {
    return;
  }
  el.visionAnswer.textContent = "Thinking...";
  try {
    const response = await api(ENDPOINTS.visionQuestion, {
      method: "POST",
      json: { question },
    });
    el.visionAnswer.textContent = response.answer;
  } catch (error) {
    el.visionAnswer.textContent = error.message;
  }
}

function stopDriveOnUnload() {
  const payload = new Blob(["{}"], { type: "application/json" });
  if (navigator.sendBeacon) {
    navigator.sendBeacon(ENDPOINTS.driveStop, payload);
    return;
  }
  fetch(ENDPOINTS.driveStop, {
    method: "POST",
    body: "{}",
    headers: { "Content-Type": "application/json" },
    keepalive: true,
  }).catch(() => null);
}

function registerGlobalCleanup() {
  window.addEventListener("beforeunload", () => {
    stopDriveOnUnload();
    teardownCapturePipeline();
    closeVoiceSocket("Browser unloading");
  });
}

function wireSettingsDirtyTracking() {
  [
    el.greetingTextInput,
    el.greetingEnabledInput,
    el.autoTrackingInput,
    el.greetingModeSelect,
    el.startupVoiceModeSelect,
    el.startupAudioTargetSelect,
    el.cameraStepInput,
  ].forEach((node) => {
    node.addEventListener("input", () => {
      state.settingsDirty = true;
      setSettingsStatus("Unsaved settings changes.", "warm");
      syncRangeReadouts();
    });
    node.addEventListener("change", () => {
      state.settingsDirty = true;
      setSettingsStatus("Unsaved settings changes.", "warm");
      syncRangeReadouts();
    });
  });
}

function settingsPayloadFromForm() {
  return {
    greeting_text: el.greetingTextInput.value.trim(),
    greeting_enabled: el.greetingEnabledInput.checked,
    greeting_mode: el.greetingModeSelect.value,
    auto_tracking_enabled: el.autoTrackingInput.checked,
    camera_step_degrees: Number(el.cameraStepInput.value),
    startup_voice_mode: el.startupVoiceModeSelect.value,
    startup_audio_target: el.startupAudioTargetSelect.value,
  };
}

async function init() {
  showTab("drive");
  el.tabButtons.forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tabButton));
  });

  el.driveButtons.forEach((button) => {
    setButtonActive(button, false);
    bindDriveButton(button);
  });
  setButtonActive(el.pushToTalk, false);

  bindKeyboard();
  registerGlobalCleanup();
  wireSettingsDirtyTracking();
  syncRangeReadouts();
  updateMessageCount();
  await refreshState();

  openVoiceSocket().catch((error) => {
    setSpeechStatus(error.message, "danger");
    logMessage("system", "Voice controls will reconnect automatically the next time you talk.");
  });

  el.voiceModeSelect.addEventListener("change", async () => {
    await applySessionAction(ENDPOINTS.voiceMode, { mode: el.voiceModeSelect.value });
  });

  el.audioTargetSelect.addEventListener("change", async () => {
    await applySessionAction(ENDPOINTS.audioTarget, { target: el.audioTargetSelect.value });
  });

  el.driveSpeedSlider.addEventListener("input", syncRangeReadouts);

  el.centerCamera.addEventListener("click", async () => {
    el.panSlider.value = "0";
    el.tiltSlider.value = "0";
    syncRangeReadouts();
    await updateCamera(0, 0);
  });

  el.cameraCenter.addEventListener("click", async () => {
    await updateCamera(0, 0);
  });

  el.cameraLeft.addEventListener("click", async () => {
    await moveCameraBy(-state.session.settings.camera_step_degrees, 0);
  });
  el.cameraRight.addEventListener("click", async () => {
    await moveCameraBy(state.session.settings.camera_step_degrees, 0);
  });
  el.cameraUp.addEventListener("click", async () => {
    await moveCameraBy(0, state.session.settings.camera_step_degrees);
  });
  el.cameraDown.addEventListener("click", async () => {
    await moveCameraBy(0, -state.session.settings.camera_step_degrees);
  });

  el.presetButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      await updateCamera(Number(button.dataset.pan), Number(button.dataset.tilt));
    });
  });

  el.cameraFollowToggle.addEventListener("change", async () => {
    await saveSettingsPatch({ auto_tracking_enabled: el.cameraFollowToggle.checked });
  });

  el.panSlider.addEventListener("input", syncRangeReadouts);
  el.tiltSlider.addEventListener("input", syncRangeReadouts);
  el.panSlider.addEventListener("change", () => {
    updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch((error) =>
      setSpeechStatus(error.message, "danger")
    );
  });
  el.tiltSlider.addEventListener("change", () => {
    updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch((error) =>
      setSpeechStatus(error.message, "danger")
    );
  });

  el.stopButton.addEventListener("click", async () => {
    clearDriveLoop();
    await applySessionAction(ENDPOINTS.emergencyStop);
  });

  el.clearEstop.addEventListener("click", async () => {
    await applySessionAction(ENDPOINTS.emergencyReset);
  });

  el.refresh.addEventListener("click", async () => {
    await refreshState();
    setSpeechStatus("State refreshed from the backend.", "ok");
  });

  bindMomentaryPointerControl(el.pushToTalk, {
    start: () => startTalking(),
    stop: () => stopTalking(),
  });

  el.promptChips.forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = button.dataset.prompt ?? "";
      el.visionQuestion.value = prompt;
      submitVisionQuestion(prompt).catch(() => null);
    });
  });

  el.visionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitVisionQuestion(el.visionQuestion.value.trim());
  });

  el.settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = settingsPayloadFromForm();
    if (!payload.greeting_text) {
      setSettingsStatus("Greeting text cannot be blank.", "danger");
      return;
    }
    try {
      const session = await applySessionAction(ENDPOINTS.settings, payload);
      state.settingsDirty = false;
      syncSettingsForm(session.settings, true);
      setSettingsStatus("Settings saved.", "ok");
    } catch (error) {
      setSettingsStatus(error.message, "danger");
    }
  });

  window.setInterval(() => {
    refreshState().catch(() => null);
  }, CONFIG.refreshIntervalMs);
}

init().catch((error) => {
  setSpeechStatus(error.message, "danger");
});
