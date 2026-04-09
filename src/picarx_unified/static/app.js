const CONFIG = {
  driveRepeatMs: 250,
  refreshIntervalMs: 2500,
  maxMessages: 18,
};

const ENDPOINTS = {
  state: "/api/state",
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

const DRIVE_KEYMAP = {
  w: { speed: 35, steering: 0 },
  a: { speed: 25, steering: -25 },
  d: { speed: 25, steering: 25 },
  s: { speed: -25, steering: 0 },
};

const state = {
  session: null,
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
  activeDriveButton: null,
  driveCommand: null,
  activeKey: null,
  refreshPromise: null,
  refreshQueued: false,
};

const el = {
  voiceModeLabel: document.querySelector("#voice-mode-label"),
  audioTargetLabel: document.querySelector("#audio-target-label"),
  hardwareLabel: document.querySelector("#hardware-label"),
  estopLabel: document.querySelector("#estop-label"),
  sessionUpdatedLabel: document.querySelector("#session-updated-label"),
  driveStateLabel: document.querySelector("#drive-state-label"),
  cameraStateLabel: document.querySelector("#camera-state-label"),
  driveSummaryLabel: document.querySelector("#drive-summary-label"),
  cameraSummaryLabel: document.querySelector("#camera-summary-label"),
  visionUpdatedLabel: document.querySelector("#vision-updated-label"),
  systemStatusLabel: document.querySelector("#system-status-label"),
  panSlider: document.querySelector("#pan-slider"),
  tiltSlider: document.querySelector("#tilt-slider"),
  panValue: document.querySelector("#pan-value"),
  tiltValue: document.querySelector("#tilt-value"),
  visionSummary: document.querySelector("#vision-summary"),
  speechStatus: document.querySelector("#speech-status"),
  messages: document.querySelector("#messages"),
  messageCountLabel: document.querySelector("#message-count-label"),
  visionAnswer: document.querySelector("#vision-answer"),
  voiceModeSelect: document.querySelector("#voice-mode-select"),
  audioTargetSelect: document.querySelector("#audio-target-select"),
  pushToTalk: document.querySelector("#push-to-talk-btn"),
  centerCamera: document.querySelector("#center-camera-btn"),
  stopButton: document.querySelector("#stop-btn"),
  clearEstop: document.querySelector("#clear-estop-btn"),
  refresh: document.querySelector("#refresh-btn"),
  visionForm: document.querySelector("#vision-form"),
  visionQuestion: document.querySelector("#vision-question"),
  driveButtons: [...document.querySelectorAll(".drive")],
  promptChips: [...document.querySelectorAll(".prompt-chip")],
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

function formatCameraSummary(camera) {
  if (!camera || (camera.pan === 0 && camera.tilt === 0)) {
    return "Centered";
  }
  return `Pan ${signed(camera.pan)} / Tilt ${signed(camera.tilt)}`;
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
    return "Relay mode streams your mic to the selected audio target.";
  }
  if (mode === "ai_reply") {
    return "AI Reply mode records your speech, commits the turn, and returns spoken output.";
  }
  return "Microphone is idle. Choose Relay or AI Reply to open the voice path.";
}

function toneForVoiceMode(mode) {
  if (mode === "relay") {
    return "cool";
  }
  if (mode === "ai_reply") {
    return "warm";
  }
  return "neutral";
}

function setButtonActive(button, isActive) {
  if (!button) {
    return;
  }
  button.dataset.active = isActive ? "true" : "false";
  button.setAttribute("aria-pressed", isActive ? "true" : "false");
}

function setCardTone(node, tone) {
  const card = node.closest(".status-card, .telemetry-card");
  if (card) {
    card.dataset.tone = tone;
  }
}

function updateMessageCount() {
  const count = el.messages.childElementCount;
  el.messageCountLabel.textContent = `${count} ${count === 1 ? "entry" : "entries"}`;
}

function setSpeechStatus(message, tone = "neutral") {
  el.speechStatus.textContent = message;
  el.speechStatus.dataset.tone = tone;
}

function syncRangeReadouts() {
  el.panValue.textContent = `${el.panSlider.value}deg`;
  el.tiltValue.textContent = `${el.tiltSlider.value}deg`;
}

function logMessage(role, text) {
  const row = document.createElement("div");
  row.className = `message message-${role}`;

  const head = document.createElement("div");
  head.className = "message-head";

  const rolePill = document.createElement("span");
  rolePill.className = "role-pill";
  rolePill.textContent = titleCase(role);

  const stamp = document.createElement("span");
  stamp.className = "message-time";
  stamp.textContent = formatTimestamp(new Date().toISOString());

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;

  head.append(rolePill, stamp);
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

function render(session) {
  state.session = session;
  document.body.dataset.estop = session.emergency_stop ? "active" : "clear";

  el.voiceModeLabel.textContent = titleCase(session.voice_mode);
  el.audioTargetLabel.textContent = titleCase(session.audio_target);
  el.estopLabel.textContent = session.emergency_stop ? "Active" : "Clear";
  el.sessionUpdatedLabel.textContent = formatTimestamp(session.updated_at);
  el.driveStateLabel.textContent = `${signed(session.drive.speed)} spd / ${signed(session.drive.steering)} str`;
  el.cameraStateLabel.textContent = `P ${signed(session.camera.pan)}deg / T ${signed(session.camera.tilt)}deg`;
  el.driveSummaryLabel.textContent = formatDriveSummary(session.drive);
  el.cameraSummaryLabel.textContent = formatCameraSummary(session.camera);
  el.visionUpdatedLabel.textContent = formatTimestamp(session.vision.analyzed_at);
  el.systemStatusLabel.textContent = formatSystemStatus(session);
  el.panSlider.value = String(session.camera.pan);
  el.tiltSlider.value = String(session.camera.tilt);
  el.voiceModeSelect.value = session.voice_mode;
  el.audioTargetSelect.value = session.audio_target;
  el.visionSummary.textContent = session.vision.summary;

  syncRangeReadouts();

  setCardTone(el.voiceModeLabel, toneForVoiceMode(session.voice_mode));
  setCardTone(el.audioTargetLabel, session.audio_target === "both" ? "warm" : "cool");
  setCardTone(el.estopLabel, session.emergency_stop ? "danger" : "ok");
  setCardTone(el.driveSummaryLabel, session.drive.speed === 0 ? "neutral" : "warm");
  setCardTone(
    el.cameraSummaryLabel,
    session.camera.pan === 0 && session.camera.tilt === 0 ? "neutral" : "cool"
  );
  setCardTone(
    el.systemStatusLabel,
    session.emergency_stop ? "danger" : session.browser_connected ? "ok" : "neutral"
  );

  if (!state.captureActive && !state.awaitingReply) {
    setSpeechStatus(defaultVoiceHint(session.voice_mode), toneForVoiceMode(session.voice_mode));
  }
}

function renderHealth(health) {
  const hardwareText = `${titleCase(health.hardware_backend)} / ${titleCase(health.camera_backend)}`;
  el.hardwareLabel.textContent = hardwareText;
  const looksMock =
    hardwareText.toLowerCase().includes("mock") || health.camera_backend.toLowerCase() === "none";
  setCardTone(el.hardwareLabel, looksMock ? "neutral" : "ok");
}

async function refreshState() {
  if (state.refreshPromise) {
    state.refreshQueued = true;
    return state.refreshPromise;
  }

  state.refreshPromise = (async () => {
    const [session, health] = await Promise.all([
      api(ENDPOINTS.state),
      api(ENDPOINTS.health),
    ]);
    render(session);
    renderHealth(health);
  })();

  try {
    await state.refreshPromise;
  } finally {
    state.refreshPromise = null;
    if (state.refreshQueued) {
      state.refreshQueued = false;
      queueMicrotask(() => {
        refreshState().catch(() => null);
      });
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
    // Ignore socket close races during shutdown.
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
    setSpeechStatus("Assistant response ready for playback.", "ok");
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

    socket.addEventListener(
      "open",
      () => {
        resolve(socket);
      },
      { once: true }
    );

    socket.addEventListener(
      "error",
      () => {
        reject(new Error("Unable to open the voice link."));
      },
      { once: true }
    );

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

  // Keep the worklet connected without playing mic monitoring through the speakers.
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
      // Ignore recognition stop races.
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
  setSpeechStatus(
    state.awaitingReply ? "Waiting for assistant reply..." : "Finishing relay...",
    "warm"
  );
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
    Promise.resolve(stop()).catch((error) => {
      setSpeechStatus(error.message, "danger");
    });
  };

  node.addEventListener("pointerdown", (event) => {
    if (pointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) {
      return;
    }
    pointerId = event.pointerId;
    try {
      node.setPointerCapture(event.pointerId);
    } catch (_error) {
      // Pointer capture is best-effort across browsers.
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
  const command = {
    speed: Number(button.dataset.speed),
    steering: Number(button.dataset.steering),
    source: "browser",
  };

  bindMomentaryPointerControl(button, {
    start: () => startDriveLoop(command, button),
    stop: () => stopDriveLoop(),
  });
}

function bindKeyboard() {
  window.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if (!DRIVE_KEYMAP[key] || state.activeKey === key || event.repeat) {
      return;
    }
    state.activeKey = key;
    event.preventDefault();
    startDriveLoop({ ...DRIVE_KEYMAP[key], source: "keyboard" }).catch(() => null);
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

async function updateCamera() {
  await applySessionAction(ENDPOINTS.camera, {
    pan: Number(el.panSlider.value),
    tilt: Number(el.tiltSlider.value),
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

async function init() {
  el.driveButtons.forEach((button) => {
    setButtonActive(button, false);
    bindDriveButton(button);
  });
  setButtonActive(el.pushToTalk, false);

  bindKeyboard();
  registerGlobalCleanup();
  syncRangeReadouts();
  updateMessageCount();
  await refreshState();

  openVoiceSocket().catch((error) => {
    setSpeechStatus(error.message, "danger");
    logMessage("system", "Voice controls will reconnect automatically the next time you talk.");
  });

  el.voiceModeSelect.addEventListener("change", async () => {
    await applySessionAction(ENDPOINTS.voiceMode, {
      mode: el.voiceModeSelect.value,
    });
  });

  el.audioTargetSelect.addEventListener("change", async () => {
    await applySessionAction(ENDPOINTS.audioTarget, {
      target: el.audioTargetSelect.value,
    });
  });

  el.centerCamera.addEventListener("click", async () => {
    el.panSlider.value = "0";
    el.tiltSlider.value = "0";
    syncRangeReadouts();
    await updateCamera();
  });

  el.panSlider.addEventListener("input", syncRangeReadouts);
  el.tiltSlider.addEventListener("input", syncRangeReadouts);
  el.panSlider.addEventListener("change", () => {
    updateCamera().catch((error) => setSpeechStatus(error.message, "danger"));
  });
  el.tiltSlider.addEventListener("change", () => {
    updateCamera().catch((error) => setSpeechStatus(error.message, "danger"));
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
    const question = el.visionQuestion.value.trim();
    await submitVisionQuestion(question);
  });

  window.setInterval(() => {
    refreshState().catch(() => null);
  }, CONFIG.refreshIntervalMs);
}

init().catch((error) => {
  setSpeechStatus(error.message, "danger");
});
