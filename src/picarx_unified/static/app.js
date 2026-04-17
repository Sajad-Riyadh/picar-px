const CONFIG = {
  driveRepeatMs: 200,
  refreshIntervalMs: 2500,
  visionRefreshMs: 450,
  maxMessages: 24,
  maxOverlayBoxes: 12,
  wsRenderThrottleMs: 500,
};

const ENDPOINTS = {
  state: "/api/state",
  vision: "/api/vision",
  settings: "/api/settings",
  health: "/api/health",
  drive: "/api/drive",
  driveFast: "/api/drive/fast",
  driveStop: "/api/drive/stop",
  camera: "/api/camera",
  voiceMode: "/api/voice/mode",
  audioTarget: "/api/audio/target",
  emergencyStop: "/api/emergency-stop",
  emergencyReset: "/api/emergency-reset",
  visionQuestion: "/api/vision/question",
  voiceSocket: "/ws/voice",
};

const app = {
  activePanel: "camera",
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
  openMic: false,
  recognition: null,
  transcript: "",
  driveInterval: null,
  driveCommand: null,
  driveBusy: false,
  activeDriveButton: null,
  activeKey: null,
  lastWsRender: 0,
  refreshPromise: null,
  refreshQueued: false,
  visionPromise: null,
  visionQueued: false,
  volume: 80,
};

const el = {};

function $(sel) {
  return document.querySelector(sel);
}

function $$(sel) {
  return [...document.querySelectorAll(sel)];
}

function cacheDom() {
  el.tabs = $$(".tab");
  el.tabPanels = $$(".tab-panels .ctrl-panel");

  el.hwChip = $("#hw-chip");
  el.modeChip = $("#mode-chip");
  el.safetyChip = $("#safety-chip");
  el.micChip = $("#mic-chip");
  el.voiceChip = $("#voice-chip");
  el.detectChip = $("#detect-chip");

  el.connDot = $("#conn-dot");
  el.connLabel = $("#conn-label");

  el.estopFab = $("#estop-fab");
  el.estopBanner = $("#estop-banner");
  el.estopResetBtn = $("#estop-reset-btn");

  el.videoFrame = $("#video-frame");
  el.videoStream = $("#video-stream");
  el.visionOverlay = $("#vision-overlay");
  el.hudDrive = $("#hud-drive");
  el.hudCam = $("#hud-cam");
  el.hudPerson = $("#hud-person");
  el.hudAuto = $("#hud-auto");
  el.visionSummary = $("#vision-summary");

  el.driveBadge = $("#drive-badge");
  el.driveSpeedSlider = $("#drive-speed-slider");
  el.driveSpeedValue = $("#drive-speed-value");
  el.stopBtn = $("#stop-btn");
  el.lastErrorLabel = $("#last-error-label");
  el.dpadBtns = $$(".dpad[data-speed-sign]");

  el.centerCameraBtn = $("#center-camera-btn");
  el.camUp = $("#cam-up");
  el.camDown = $("#cam-down");
  el.camLeft = $("#cam-left");
  el.camRight = $("#cam-right");
  el.camCenter = $("#cam-center");
  el.panSlider = $("#pan-slider");
  el.tiltSlider = $("#tilt-slider");
  el.panValue = $("#pan-value");
  el.tiltValue = $("#tilt-value");
  el.cameraFollowToggle = $("#camera-follow-toggle");
  el.presetChips = $$(".preset-chip");

  el.voiceModeSelect = $("#voice-mode-select");
  el.audioTargetSelect = $("#audio-target-select");
  el.micToggleBtn = $("#mic-toggle-btn");
  el.pushToTalkBtn = $("#push-to-talk-btn");
  el.openMicToggle = $("#open-mic-toggle");
  el.micStateBadge = $("#mic-state-badge");
  el.volumeSlider = $("#volume-slider");
  el.volumeValue = $("#volume-value");
  el.speechStatus = $("#speech-status");
  el.messageCountLabel = $("#message-count-label");
  el.messages = $("#messages");

  el.personDetectedLabel = $("#person-detected-label");
  el.detectedClassesLabel = $("#detected-classes-label");
  el.autonomyStateLabel = $("#autonomy-state-label");
  el.aiProviderLabel = $("#ai-provider-label");
  el.visionUpdatedLabel = $("#vision-updated-label");
  el.lastBehaviorLabel = $("#last-behavior-label");
  el.lastGreetingLabel = $("#last-greeting-label");
  el.autoTrackingToggle = $("#auto-tracking-toggle");
  el.greetingEnabledToggle = $("#greeting-enabled-toggle");
  el.greetingModeSelect = $("#greeting-mode-select");
  el.autonomousModeToggle = $("#autonomous-mode-toggle");
  el.detectionMasterToggle = $("#detection-master-toggle");
  el.faceDetectionToggle = $("#face-detection-toggle");
  el.personDetectionToggle = $("#person-detection-toggle");
  el.catDetectionToggle = $("#cat-detection-toggle");
  el.objectDetectionToggle = $("#object-detection-toggle");
  el.overlayToggle = $("#overlay-toggle");
  el.visionForm = $("#vision-form");
  el.visionQuestion = $("#vision-question");
  el.visionAnswer = $("#vision-answer");
  el.promptChips = $$(".prompt-chip");

  el.settingsForm = $("#settings-form");
  el.greetingTextInput = $("#greeting-text-input");
  el.greetingEnabledInput = $("#greeting-enabled-input");
  el.autoTrackingInput = $("#auto-tracking-input");
  el.settingsAutonomousModeInput = $("#settings-autonomous-mode-input");
  el.settingsDetectionEnabledInput = $("#settings-detection-enabled-input");
  el.settingsFaceDetectionInput = $("#settings-face-detection-input");
  el.settingsPersonDetectionInput = $("#settings-person-detection-input");
  el.settingsCatDetectionInput = $("#settings-cat-detection-input");
  el.settingsObjectDetectionInput = $("#settings-object-detection-input");
  el.settingsOverlayInput = $("#settings-overlay-input");
  el.settingsGreetingMode = $("#settings-greeting-mode");
  el.startupVoiceModeSelect = $("#startup-voice-mode-select");
  el.startupAudioTargetSelect = $("#startup-audio-target-select");
  el.cameraStepInput = $("#camera-step-input");
  el.cameraStepValue = $("#camera-step-value");
  el.cameraRedGainInput = $("#camera-red-gain-input");
  el.cameraRedGainValue = $("#camera-red-gain-value");
  el.cameraGreenGainInput = $("#camera-green-gain-input");
  el.cameraGreenGainValue = $("#camera-green-gain-value");
  el.cameraBlueGainInput = $("#camera-blue-gain-input");
  el.cameraBlueGainValue = $("#camera-blue-gain-value");
  el.autonomousSpeedInput = $("#autonomous-speed-input");
  el.autonomousSpeedValue = $("#autonomous-speed-value");
  el.autonomousTurnInput = $("#autonomous-turn-input");
  el.autonomousTurnValue = $("#autonomous-turn-value");
  el.autonomousStopDistanceInput = $("#autonomous-stop-distance-input");
  el.autonomousStopDistanceValue = $("#autonomous-stop-distance-value");
  el.settingsEstopBtn = $("#settings-estop-btn");
  el.settingsResetBtn = $("#settings-reset-btn");
  el.settingsSaveStatus = $("#settings-save-status");

  el.menuBtn = $("#menu-btn");
  el.drawer = $("#drawer");
  el.drawerBackdrop = $("#drawer-backdrop");
  el.drawerClose = $("#drawer-close");
  el.drawerToggle = $("#drawer-toggle");
  el.quickMicBtn = $("#quick-mic-btn");
}

function titleCase(value) {
  return String(value ?? "").replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
}

function signed(value) {
  return value > 0 ? `+${value}` : `${value}`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function detectionName(detection) {
  if (!detection) return "Target";
  return detection.display_label || titleCase(detection.label);
}

function formatTimestamp(value) {
  if (!value) return "Pending";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Pending";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(parsed);
}

function formatDriveSummary(drive) {
  if (!drive || drive.speed === 0) return "Stopped";
  const direction = drive.speed > 0 ? "Fwd" : "Rev";
  return drive.steering === 0
    ? `${direction} ${Math.abs(drive.speed)}`
    : `${direction} ${Math.abs(drive.speed)} / str ${signed(drive.steering)}`;
}

function formatControlMode(session) {
  if (!session) return "Manual";
  if (session.emergency_stop) return "Halted";
  return titleCase(session.control_mode || "manual");
}

function formatDetectedClasses(vision) {
  if (!vision?.counts || !Object.keys(vision.counts).length) return "None";
  return Object.entries(vision.counts)
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([label, count]) => `${titleCase(label)}${count > 1 ? ` x${count}` : ""}`)
    .join(", ");
}

function defaultVoiceHint(mode) {
  if (mode === "relay") return "Relay mode streams your browser mic to the speaker target.";
  if (mode === "ai_reply") return "AI Reply records one spoken turn, then speaks the Gemini reply.";
  return "Mic idle. Choose Relay or AI Reply to open the voice path.";
}

function setButtonActive(btn, active) {
  if (!btn) return;
  btn.dataset.active = active ? "true" : "false";
  btn.setAttribute("aria-pressed", active ? "true" : "false");
}

function setSpeechStatus(message, tone = "neutral") {
  if (!el.speechStatus) return;
  el.speechStatus.textContent = message;
  el.speechStatus.dataset.tone = tone;
}

function setSettingsStatus(message, tone = "neutral") {
  if (!el.settingsSaveStatus) return;
  el.settingsSaveStatus.textContent = message;
  el.settingsSaveStatus.dataset.tone = tone;
}

function syncRangeReadouts() {
  if (el.panValue) el.panValue.textContent = `${el.panSlider.value} deg`;
  if (el.tiltValue) el.tiltValue.textContent = `${el.tiltSlider.value} deg`;
  if (el.driveSpeedValue) el.driveSpeedValue.textContent = `${el.driveSpeedSlider.value}%`;
  if (el.cameraStepValue) el.cameraStepValue.textContent = `${el.cameraStepInput.value} deg`;
  if (el.cameraRedGainValue) el.cameraRedGainValue.textContent = `${Number(el.cameraRedGainInput.value).toFixed(2)}x`;
  if (el.cameraGreenGainValue) el.cameraGreenGainValue.textContent = `${Number(el.cameraGreenGainInput.value).toFixed(2)}x`;
  if (el.cameraBlueGainValue) el.cameraBlueGainValue.textContent = `${Number(el.cameraBlueGainInput.value).toFixed(2)}x`;
  if (el.autonomousSpeedValue) el.autonomousSpeedValue.textContent = `${el.autonomousSpeedInput.value}%`;
  if (el.autonomousTurnValue) el.autonomousTurnValue.textContent = `${el.autonomousTurnInput.value} deg`;
  if (el.autonomousStopDistanceValue) el.autonomousStopDistanceValue.textContent = `${el.autonomousStopDistanceInput.value} cm`;
  if (el.volumeValue) el.volumeValue.textContent = `${el.volumeSlider.value}%`;
}

function updateMessageCount() {
  if (el.messageCountLabel) el.messageCountLabel.textContent = `${el.messages.childElementCount}`;
}

function updateMicBadge() {
  if (!el.micStateBadge) return;
  if (app.captureActive) {
    el.micStateBadge.textContent = "Listening";
    el.micStateBadge.dataset.state = "listening";
  } else if (app.openMic && app.ws?.readyState === WebSocket.OPEN) {
    el.micStateBadge.textContent = "Ready";
    el.micStateBadge.dataset.state = "on";
  } else {
    el.micStateBadge.textContent = "Off";
    el.micStateBadge.dataset.state = "off";
  }
  if (el.micChip) {
    el.micChip.textContent = app.captureActive ? "Mic: Live" : "Mic: Off";
    el.micChip.dataset.tone = app.captureActive ? "active" : "neutral";
  }
}

function logMessage(role, text) {
  const row = document.createElement("div");
  const head = document.createElement("div");
  const pill = document.createElement("span");
  const time = document.createElement("span");
  const body = document.createElement("div");

  row.className = `message message-${role}`;
  head.className = "message-head";
  pill.className = "role-pill";
  time.className = "message-time";
  body.className = "message-body";

  pill.textContent = titleCase(role);
  time.textContent = formatTimestamp(new Date().toISOString());
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

function showPanel(name) {
  app.activePanel = name;
  el.tabs.forEach(tab => tab.classList.toggle("active", tab.dataset.panel === name));
  el.tabPanels.forEach(panel => { panel.hidden = panel.id !== `panel-${name}`; });
}

function openDrawer() {
  el.drawer.classList.add("open");
  el.drawerBackdrop.classList.add("open");
}

function closeDrawer() {
  el.drawer.classList.remove("open");
  el.drawerBackdrop.classList.remove("open");
}

function toggleDrawer() {
  el.drawer.classList.contains("open") ? closeDrawer() : openDrawer();
}

function syncSettingsForm(settings, force = false) {
  if (app.settingsDirty && !force) return;
  el.greetingTextInput.value = settings.greeting_text;
  el.greetingEnabledInput.checked = settings.greeting_enabled;
  el.autoTrackingInput.checked = settings.auto_tracking_enabled;
  el.settingsAutonomousModeInput.checked = settings.autonomous_mode_enabled;
  el.settingsDetectionEnabledInput.checked = settings.detection_enabled;
  el.settingsFaceDetectionInput.checked = settings.face_detection_enabled;
  el.settingsPersonDetectionInput.checked = settings.person_detection_enabled;
  el.settingsCatDetectionInput.checked = settings.cat_detection_enabled;
  el.settingsObjectDetectionInput.checked = settings.object_detection_enabled;
  el.settingsOverlayInput.checked = settings.detection_overlay_enabled;
  el.settingsGreetingMode.value = settings.greeting_mode;
  el.startupVoiceModeSelect.value = settings.startup_voice_mode;
  el.startupAudioTargetSelect.value = settings.startup_audio_target;
  el.cameraStepInput.value = String(settings.camera_step_degrees);
  el.cameraRedGainInput.value = String(settings.camera_red_gain);
  el.cameraGreenGainInput.value = String(settings.camera_green_gain);
  el.cameraBlueGainInput.value = String(settings.camera_blue_gain);
  el.autonomousSpeedInput.value = String(settings.autonomous_drive_speed);
  el.autonomousTurnInput.value = String(settings.autonomous_turn_strength);
  el.autonomousStopDistanceInput.value = String(Math.round(settings.autonomous_stop_distance_cm));
  el.cameraFollowToggle.checked = settings.auto_tracking_enabled;
  el.autoTrackingToggle.checked = settings.auto_tracking_enabled;
  el.greetingEnabledToggle.checked = settings.greeting_enabled;
  el.greetingModeSelect.value = settings.greeting_mode;
  el.autonomousModeToggle.checked = settings.autonomous_mode_enabled;
  el.detectionMasterToggle.checked = settings.detection_enabled;
  el.faceDetectionToggle.checked = settings.face_detection_enabled;
  el.personDetectionToggle.checked = settings.person_detection_enabled;
  el.catDetectionToggle.checked = settings.cat_detection_enabled;
  el.objectDetectionToggle.checked = settings.object_detection_enabled;
  el.overlayToggle.checked = settings.detection_overlay_enabled;
  syncRangeReadouts();
}

function renderVisionOverlay(vision, settings = app.session?.settings) {
  if (!el.visionOverlay) return;
  el.visionOverlay.replaceChildren();
  if (!settings?.detection_enabled || !settings?.detection_overlay_enabled) return;
  if (!vision?.detections?.length || !vision.frame_width || !vision.frame_height || !el.videoFrame) return;
  const rect = el.videoFrame.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const scale = Math.min(rect.width / vision.frame_width, rect.height / vision.frame_height);
  const renderWidth = vision.frame_width * scale;
  const renderHeight = vision.frame_height * scale;
  const offsetX = (rect.width - renderWidth) / 2;
  const offsetY = (rect.height - renderHeight) / 2;

  vision.detections.slice(0, CONFIG.maxOverlayBoxes).forEach(detection => {
    const box = document.createElement("div");
    const label = document.createElement("div");
    box.className = "vision-box";
    label.className = "vision-label";
    box.dataset.label = detection.label || "object";
    box.style.left = `${offsetX + detection.x * scale}px`;
    box.style.top = `${offsetY + detection.y * scale}px`;
    box.style.width = `${clamp(detection.width * scale, 24, renderWidth)}px`;
    box.style.height = `${clamp(detection.height * scale, 24, renderHeight)}px`;
    label.textContent = `${detectionName(detection)} ${Math.round((detection.confidence || 0) * 100)}%`;
    box.append(label);
    el.visionOverlay.append(box);
  });
}

function renderVisionSnapshot(vision, session = app.session) {
  if (!vision || !session) return;
  const primary = vision.detections?.[0] ?? null;
  const detectionText = !session.settings.detection_enabled
    ? "Detect: Off"
    : vision.detections?.length ? `Detect: ${vision.detections.length}` : "Detect: Idle";

  if (el.detectChip) {
    el.detectChip.textContent = detectionText;
    el.detectChip.dataset.tone = !session.settings.detection_enabled
      ? "warn"
      : vision.detections?.length ? "active" : "neutral";
  }
  if (el.visionSummary) el.visionSummary.textContent = vision.summary;
  if (el.personDetectedLabel) el.personDetectedLabel.textContent = session.person_detected ? "Yes" : "No";
  if (el.detectedClassesLabel) el.detectedClassesLabel.textContent = formatDetectedClasses(vision);
  if (el.visionUpdatedLabel) el.visionUpdatedLabel.textContent = formatTimestamp(vision.analyzed_at);
  if (el.hudPerson) {
    el.hudPerson.hidden = !primary;
    if (primary) el.hudPerson.textContent = detectionName(primary);
  }
  if (el.hudAuto) {
    const autoEnabled = !!session.settings.autonomous_mode_enabled;
    el.hudAuto.hidden = !autoEnabled;
    if (autoEnabled) {
      el.hudAuto.textContent = session.manual_override_active
        ? "Manual Override"
        : session.control_mode === "autonomous" ? "Autonomous" : "Auto Armed";
    }
  }
  if (el.autonomyStateLabel) {
    el.autonomyStateLabel.textContent = !session.settings.autonomous_mode_enabled
      ? "Off"
      : session.manual_override_active ? "Manual Override" : titleCase(session.control_mode || "autonomous");
  }
  renderVisionOverlay(vision, session.settings);
}

function render(session) {
  app.session = session;
  document.body.dataset.estop = session.emergency_stop ? "active" : "clear";
  if (el.estopBanner) el.estopBanner.hidden = !session.emergency_stop;
  if (el.safetyChip) {
    el.safetyChip.textContent = session.emergency_stop ? "! E-STOP" : "Safety OK";
    el.safetyChip.dataset.tone = session.emergency_stop ? "danger" : "ok";
  }
  if (el.modeChip) {
    el.modeChip.textContent = formatControlMode(session);
    el.modeChip.dataset.tone = session.emergency_stop
      ? "danger"
      : session.control_mode === "autonomous" ? "active" : "cool";
  }
  if (el.voiceChip) {
    el.voiceChip.textContent = `Voice: ${titleCase(session.voice_mode)}`;
    el.voiceChip.dataset.tone = session.voice_mode === "mute" ? "neutral" : "cool";
  }
  if (el.hudDrive) el.hudDrive.textContent = `SPD ${signed(session.drive.speed)} / STR ${signed(session.drive.steering)}`;
  if (el.hudCam) el.hudCam.textContent = `PAN ${session.camera.pan} deg / TILT ${session.camera.tilt} deg`;
  if (el.driveBadge) el.driveBadge.textContent = formatDriveSummary(session.drive);
  if (el.lastErrorLabel) el.lastErrorLabel.textContent = session.last_error || "None";
  if (el.aiProviderLabel) el.aiProviderLabel.textContent = titleCase(session.ai_provider);
  if (el.lastBehaviorLabel) el.lastBehaviorLabel.textContent = session.last_behavior_action || session.last_autonomy_action || "None";
  if (el.lastGreetingLabel) el.lastGreetingLabel.textContent = session.last_greeting_text || "No greeting yet.";

  el.voiceModeSelect.value = session.voice_mode;
  el.audioTargetSelect.value = session.audio_target;
  el.panSlider.value = String(session.camera.pan);
  el.tiltSlider.value = String(session.camera.tilt);
  syncSettingsForm(session.settings);
  renderVisionSnapshot(session.vision, session);

  if (!app.captureActive && !app.awaitingReply) {
    setSpeechStatus(defaultVoiceHint(session.voice_mode), session.voice_mode === "mute" ? "neutral" : "cool");
  }
  updateMicBadge();
}

function renderHealth(health) {
  if (el.hwChip) {
    el.hwChip.textContent = `HW: ${titleCase(health.hardware_backend)}`;
    el.hwChip.dataset.tone = health.hardware_backend === "mock" ? "warn" : "ok";
  }
  if (el.connDot) el.connDot.dataset.ok = "true";
  if (el.connLabel) el.connLabel.textContent = "Online";
}

async function refreshState() {
  if (app.driveCommand) return;
  if (app.refreshPromise) { app.refreshQueued = true; return app.refreshPromise; }
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

async function refreshVision() {
  if (app.visionPromise) { app.visionQueued = true; return app.visionPromise; }
  app.visionPromise = (async () => {
    const vision = await api(ENDPOINTS.vision);
    if (!app.session) return;
    app.session.vision = vision;
    app.session.person_detected = (vision.detections || []).some(detection => ["face", "person"].includes(detection.label));
    renderVisionSnapshot(vision, app.session);
  })();
  try {
    await app.visionPromise;
  } finally {
    app.visionPromise = null;
    if (app.visionQueued) {
      app.visionQueued = false;
      queueMicrotask(() => refreshVision().catch(() => null));
    }
  }
}

function base64FromArrayBuffer(buf) {
  let text = "";
  const bytes = new Uint8Array(buf);
  bytes.forEach(value => { text += String.fromCharCode(value); });
  return btoa(text);
}

function bytesFromBase64(encoded) {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
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
  for (let index = 0; index < pcm.length; index += 1) channel[index] = pcm[index] / 32768;
  const source = app.audioContext.createBufferSource();
  const gain = app.audioContext.createGain();
  source.buffer = buffer;
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
  const gain = app.audioContext.createGain();
  source.buffer = buffer;
  gain.gain.value = getPlaybackGain();
  source.connect(gain).connect(app.audioContext.destination);
  source.start();
}

function teardownCapturePipeline() {
  if (app.sourceNode) { app.sourceNode.disconnect(); app.sourceNode = null; }
  if (app.workletNode) { app.workletNode.disconnect(); app.workletNode = null; }
  if (app.monitorNode) { app.monitorNode.disconnect(); app.monitorNode = null; }
  if (app.mediaStream) {
    app.mediaStream.getTracks().forEach(track => track.stop());
    app.mediaStream = null;
  }
}

function closeVoiceSocket(reason = "Client closing") {
  if (!app.ws) return;
  try { app.ws.close(1000, reason); } catch (_) {}
  app.ws = null;
  app.socketPromise = null;
}

function handleVoiceSocketMessage(payload) {
  if (payload.type === "state") {
    const now = performance.now();
    if (app.driveCommand && (now - app.lastWsRender) < CONFIG.wsRenderThrottleMs) return;
    app.lastWsRender = now;
    render(payload.state);
    return;
  }
  if (payload.type === "relay_chunk") { playRelayChunk(payload.audio, payload.sample_rate).catch(() => null); return; }
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
    socket.addEventListener("message", event => handleVoiceSocketMessage(JSON.parse(event.data)));
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
  try {
    return await app.socketPromise;
  } finally {
    app.socketPromise = null;
  }
}

async function ensureCapturePipeline() {
  await ensureAudioContext();
  if (app.mediaStream && app.workletNode) return;
  app.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  app.sourceNode = app.audioContext.createMediaStreamSource(app.mediaStream);
  app.workletNode = new AudioWorkletNode(app.audioContext, "pcm-capture");
  app.monitorNode = app.audioContext.createGain();
  app.monitorNode.gain.value = 0;
  app.workletNode.port.onmessage = event => {
    if (!app.captureActive || !app.ws || app.ws.readyState !== WebSocket.OPEN) return;
    app.ws.send(JSON.stringify({ type: "pcm_chunk", audio: base64FromArrayBuffer(event.data) }));
  };
  app.sourceNode.connect(app.workletNode);
  app.workletNode.connect(app.monitorNode);
  app.monitorNode.connect(app.audioContext.destination);
}

function configureSpeechRecognition() {
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognitionCtor || app.recognition) return;
  app.recognition = new SpeechRecognitionCtor();
  app.recognition.lang = "en-US";
  app.recognition.continuous = true;
  app.recognition.interimResults = true;
  app.recognition.onresult = event => {
    const chunks = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) chunks.push(event.results[index][0].transcript);
    app.transcript = chunks.join(" ").trim();
  };
}

async function startTalking() {
  if (app.session?.voice_mode === "mute") { setSpeechStatus("Switch voice mode out of Mute first.", "neutral"); return; }
  await openVoiceSocket();
  await ensureCapturePipeline();
  configureSpeechRecognition();
  app.transcript = "";
  app.awaitingReply = false;
  app.captureActive = true;
  setButtonActive(el.pushToTalkBtn, true);
  updateMicBadge();
  if (app.session?.voice_mode === "ai_reply" && app.recognition) {
    try { app.recognition.start(); } catch (_) {}
  }
  setSpeechStatus("Listening...", "cool");
}

async function stopTalking() {
  if (!app.captureActive) return;
  app.captureActive = false;
  setButtonActive(el.pushToTalkBtn, false);
  updateMicBadge();
  if (app.recognition) {
    try { app.recognition.stop(); } catch (_) {}
  }
  if (!app.ws || app.ws.readyState !== WebSocket.OPEN) return;
  if (app.transcript) app.ws.send(JSON.stringify({ type: "transcript", text: app.transcript }));
  app.awaitingReply = app.session?.voice_mode === "ai_reply";
  app.ws.send(JSON.stringify({ type: "commit" }));
  setSpeechStatus(app.awaitingReply ? "Waiting for AI reply..." : "Finishing relay...", "warn");
}

async function toggleOpenMic(forceOff = false) {
  if (forceOff || app.openMic) {
    app.openMic = false;
    el.openMicToggle.checked = false;
    el.micToggleBtn.textContent = "Open Mic";
    el.micToggleBtn.classList.remove("btn-danger");
    el.micToggleBtn.classList.add("btn-accent");
    await stopTalking();
  } else {
    app.openMic = true;
    el.openMicToggle.checked = true;
    el.micToggleBtn.textContent = "Mic On - Stop";
    el.micToggleBtn.classList.remove("btn-accent");
    el.micToggleBtn.classList.add("btn-danger");
    await startTalking();
  }
  updateMicBadge();
}

function currentDriveSpeed() { return Number(el.driveSpeedSlider.value); }

function buildDriveCommand(speedSign, steering, source) {
  if (speedSign === 0) return { speed: 0, steering: 0, source };
  return { speed: currentDriveSpeed() * speedSign, steering, source };
}

async function sendDriveFast(command) {
  api(ENDPOINTS.driveFast ?? ENDPOINTS.drive, { method: "POST", json: command }).catch(error => {
    if (el.lastErrorLabel) el.lastErrorLabel.textContent = error.message;
  });
  if (el.hudDrive) el.hudDrive.textContent = `SPD ${signed(command.speed)} / STR ${signed(command.steering)}`;
  if (el.driveBadge) {
    el.driveBadge.textContent = command.speed === 0
      ? "Stopped"
      : `${command.speed > 0 ? "Fwd" : "Rev"} ${Math.abs(command.speed)}${command.steering ? ` / str ${signed(command.steering)}` : ""}`;
  }
}

function clearDriveLoop() {
  clearTimeout(app.driveInterval);
  app.driveInterval = null;
  app.driveCommand = null;
  app.driveBusy = false;
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
  if (app.session?.emergency_stop) { setSpeechStatus("Reset emergency stop before driving.", "danger"); return; }
  if (app.driveCommand && app.driveCommand.speed === command.speed && app.driveCommand.steering === command.steering && app.driveCommand.source === command.source) return;
  clearDriveLoop();
  app.driveCommand = command;
  if (button) {
    app.activeDriveButton = button;
    setButtonActive(button, true);
  }
  const tick = async () => {
    if (!app.driveCommand) return;
    app.driveBusy = true;
    try {
      await sendDriveFast(command);
    } catch (error) {
      clearDriveLoop();
      setSpeechStatus(error.message, "danger");
      api(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
      return;
    }
    app.driveBusy = false;
    if (app.driveCommand) app.driveInterval = setTimeout(tick, CONFIG.driveRepeatMs);
  };
  tick();
}

async function updateCamera(pan, tilt) {
  await applySessionAction(ENDPOINTS.camera, { pan, tilt });
}

async function moveCameraBy(deltaPan, deltaTilt) {
  if (!app.session) return;
  const pan = Number(app.session.camera.pan) + deltaPan;
  const tilt = Number(app.session.camera.tilt) + deltaTilt;
  el.panSlider.value = String(pan);
  el.tiltSlider.value = String(tilt);
  syncRangeReadouts();
  await updateCamera(pan, tilt);
}

async function submitVisionQuestion(question) {
  if (!question) return;
  el.visionAnswer.textContent = "Thinking...";
  try {
    const response = await api(ENDPOINTS.visionQuestion, { method: "POST", json: { question } });
    el.visionAnswer.textContent = response.answer;
  } catch (error) {
    el.visionAnswer.textContent = error.message;
  }
}

function mergedSettings(patch = {}) {
  if (!app.session) throw new Error("Robot session not ready.");
  return { ...app.session.settings, ...patch };
}

async function saveSettingsPatch(patch) {
  const session = await applySessionAction(ENDPOINTS.settings, mergedSettings(patch));
  app.settingsDirty = false;
  syncSettingsForm(session.settings, true);
  setSettingsStatus("Settings saved.", "ok");
  renderVisionOverlay(session.vision, session.settings);
  return session;
}

function settingsPayloadFromForm() {
  return {
    greeting_text: el.greetingTextInput.value.trim(),
    greeting_enabled: el.greetingEnabledInput.checked,
    greeting_mode: el.settingsGreetingMode.value,
    auto_tracking_enabled: el.autoTrackingInput.checked,
    detection_enabled: el.settingsDetectionEnabledInput.checked,
    face_detection_enabled: el.settingsFaceDetectionInput.checked,
    person_detection_enabled: el.settingsPersonDetectionInput.checked,
    cat_detection_enabled: el.settingsCatDetectionInput.checked,
    object_detection_enabled: el.settingsObjectDetectionInput.checked,
    detection_overlay_enabled: el.settingsOverlayInput.checked,
    autonomous_mode_enabled: el.settingsAutonomousModeInput.checked,
    camera_step_degrees: Number(el.cameraStepInput.value),
    camera_red_gain: Number(el.cameraRedGainInput.value),
    camera_green_gain: Number(el.cameraGreenGainInput.value),
    camera_blue_gain: Number(el.cameraBlueGainInput.value),
    autonomous_drive_speed: Number(el.autonomousSpeedInput.value),
    autonomous_turn_strength: Number(el.autonomousTurnInput.value),
    autonomous_stop_distance_cm: Number(el.autonomousStopDistanceInput.value),
    startup_voice_mode: el.startupVoiceModeSelect.value,
    startup_audio_target: el.startupAudioTargetSelect.value,
  };
}

function cameraGainPatchFromForm() {
  return {
    camera_red_gain: Number(el.cameraRedGainInput.value),
    camera_green_gain: Number(el.cameraGreenGainInput.value),
    camera_blue_gain: Number(el.cameraBlueGainInput.value),
  };
}

function bindMomentaryPointerControl(node, { start, stop }) {
  let pointerId = null;
  const release = () => {
    if (pointerId === null) return;
    pointerId = null;
    Promise.resolve(stop()).catch(error => setSpeechStatus(error.message, "danger"));
  };
  node.addEventListener("pointerdown", event => {
    if (pointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) return;
    pointerId = event.pointerId;
    try { node.setPointerCapture(event.pointerId); } catch (_) {}
    event.preventDefault();
    Promise.resolve(start(event)).catch(error => {
      pointerId = null;
      setSpeechStatus(error.message, "danger");
    });
  });
  node.addEventListener("pointerup", release);
  node.addEventListener("pointercancel", release);
  node.addEventListener("lostpointercapture", release);
  node.addEventListener("contextmenu", event => event.preventDefault());
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
  window.addEventListener("keydown", event => {
    const key = event.key.toLowerCase();
    if (!keyMap[key] || app.activeKey === key || event.repeat) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
    app.activeKey = key;
    event.preventDefault();
    startDriveLoop(keyMap[key]()).catch(() => null);
  });
  window.addEventListener("keyup", event => {
    if (event.key.toLowerCase() !== app.activeKey) return;
    app.activeKey = null;
    stopDriveLoop().catch(() => null);
  });
  window.addEventListener("blur", () => {
    app.activeKey = null;
    stopDriveLoop().catch(() => null);
  });
}

function stopDriveOnUnload() {
  const payload = new Blob(["{}"], { type: "application/json" });
  if (navigator.sendBeacon) { navigator.sendBeacon(ENDPOINTS.driveStop, payload); return; }
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
    el.settingsAutonomousModeInput,
    el.settingsDetectionEnabledInput,
    el.settingsFaceDetectionInput,
    el.settingsPersonDetectionInput,
    el.settingsCatDetectionInput,
    el.settingsObjectDetectionInput,
    el.settingsOverlayInput,
    el.settingsGreetingMode,
    el.startupVoiceModeSelect,
    el.startupAudioTargetSelect,
    el.cameraStepInput,
    el.cameraRedGainInput,
    el.cameraGreenGainInput,
    el.cameraBlueGainInput,
    el.autonomousSpeedInput,
    el.autonomousTurnInput,
    el.autonomousStopDistanceInput,
  ].forEach(node => {
    if (!node) return;
    const markDirty = () => {
      app.settingsDirty = true;
      setSettingsStatus("Unsaved changes.", "warn");
      syncRangeReadouts();
    };
    node.addEventListener("input", markDirty);
    node.addEventListener("change", markDirty);
  });
}

function bindInstantToggle(node, patchFactory) {
  if (!node) return;
  node.addEventListener("change", () => {
    saveSettingsPatch(patchFactory()).catch(error => setSettingsStatus(error.message, "danger"));
  });
}

async function init() {
  cacheDom();
  showPanel("camera");
  syncRangeReadouts();
  updateMessageCount();

  el.tabs.forEach(tab => tab.addEventListener("click", () => showPanel(tab.dataset.panel)));
  el.menuBtn.addEventListener("click", toggleDrawer);
  el.drawerToggle.addEventListener("click", toggleDrawer);
  el.drawerClose.addEventListener("click", closeDrawer);
  el.drawerBackdrop.addEventListener("click", closeDrawer);
  window.addEventListener("keydown", event => { if (event.key === "Escape") closeDrawer(); });
  window.addEventListener("resize", () => renderVisionOverlay(app.session?.vision, app.session?.settings));

  el.quickMicBtn.addEventListener("click", () => toggleOpenMic());

  el.dpadBtns.forEach(button => {
    setButtonActive(button, false);
    bindDriveButton(button);
  });
  bindKeyboard();
  registerGlobalCleanup();
  wireSettingsDirtyTracking();

  refreshState().catch(() => null);
  refreshVision().catch(() => null);
  openVoiceSocket().catch(error => {
    setSpeechStatus(error.message, "danger");
    logMessage("system", "Voice link will reconnect on next use.");
  });

  el.estopFab.addEventListener("click", async () => {
    if (app.session?.emergency_stop) await applySessionAction(ENDPOINTS.emergencyReset);
    else {
      clearDriveLoop();
      await applySessionAction(ENDPOINTS.emergencyStop);
    }
  });
  el.estopResetBtn.addEventListener("click", () => applySessionAction(ENDPOINTS.emergencyReset));

  el.stopBtn.addEventListener("click", async () => {
    clearDriveLoop();
    await applySessionAction(ENDPOINTS.driveStop);
  });
  el.driveSpeedSlider.addEventListener("input", syncRangeReadouts);
  el.voiceModeSelect.addEventListener("change", () => applySessionAction(ENDPOINTS.voiceMode, { mode: el.voiceModeSelect.value }));
  el.audioTargetSelect.addEventListener("change", () => applySessionAction(ENDPOINTS.audioTarget, { target: el.audioTargetSelect.value }));

  el.micToggleBtn.addEventListener("click", () => toggleOpenMic());
  el.openMicToggle.addEventListener("change", () => toggleOpenMic(!el.openMicToggle.checked));
  bindMomentaryPointerControl(el.pushToTalkBtn, {
    start: () => startTalking(),
    stop: () => { if (app.openMic) return; return stopTalking(); },
  });
  el.volumeSlider.addEventListener("input", () => {
    app.volume = Number(el.volumeSlider.value);
    syncRangeReadouts();
  });

  const step = () => app.session?.settings?.camera_step_degrees ?? 5;
  el.camUp.addEventListener("click", () => moveCameraBy(0, step()));
  el.camDown.addEventListener("click", () => moveCameraBy(0, -step()));
  el.camLeft.addEventListener("click", () => moveCameraBy(-step(), 0));
  el.camRight.addEventListener("click", () => moveCameraBy(step(), 0));
  el.camCenter.addEventListener("click", () => {
    el.panSlider.value = "0";
    el.tiltSlider.value = "0";
    syncRangeReadouts();
    updateCamera(0, 0);
  });
  el.centerCameraBtn.addEventListener("click", () => {
    el.panSlider.value = "0";
    el.tiltSlider.value = "0";
    syncRangeReadouts();
    updateCamera(0, 0);
  });
  el.panSlider.addEventListener("input", syncRangeReadouts);
  el.tiltSlider.addEventListener("input", syncRangeReadouts);
  el.panSlider.addEventListener("change", () => updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch(error => setSpeechStatus(error.message, "danger")));
  el.tiltSlider.addEventListener("change", () => updateCamera(Number(el.panSlider.value), Number(el.tiltSlider.value)).catch(error => setSpeechStatus(error.message, "danger")));
  el.presetChips.forEach(button => button.addEventListener("click", () => updateCamera(Number(button.dataset.pan), Number(button.dataset.tilt))));
  bindInstantToggle(el.cameraFollowToggle, () => ({ auto_tracking_enabled: el.cameraFollowToggle.checked }));
  [el.cameraRedGainInput, el.cameraGreenGainInput, el.cameraBlueGainInput].forEach(node => {
    node.addEventListener("change", () => saveSettingsPatch(cameraGainPatchFromForm()).catch(error => setSettingsStatus(error.message, "danger")));
  });

  bindInstantToggle(el.autoTrackingToggle, () => ({ auto_tracking_enabled: el.autoTrackingToggle.checked }));
  bindInstantToggle(el.greetingEnabledToggle, () => ({ greeting_enabled: el.greetingEnabledToggle.checked }));
  el.greetingModeSelect.addEventListener("change", () => saveSettingsPatch({ greeting_mode: el.greetingModeSelect.value }).catch(error => setSettingsStatus(error.message, "danger")));
  bindInstantToggle(el.autonomousModeToggle, () => ({ autonomous_mode_enabled: el.autonomousModeToggle.checked }));
  bindInstantToggle(el.detectionMasterToggle, () => ({ detection_enabled: el.detectionMasterToggle.checked }));
  bindInstantToggle(el.faceDetectionToggle, () => ({ face_detection_enabled: el.faceDetectionToggle.checked }));
  bindInstantToggle(el.personDetectionToggle, () => ({ person_detection_enabled: el.personDetectionToggle.checked }));
  bindInstantToggle(el.catDetectionToggle, () => ({ cat_detection_enabled: el.catDetectionToggle.checked }));
  bindInstantToggle(el.objectDetectionToggle, () => ({ object_detection_enabled: el.objectDetectionToggle.checked }));
  bindInstantToggle(el.overlayToggle, () => ({ detection_overlay_enabled: el.overlayToggle.checked }));

  el.visionForm.addEventListener("submit", event => {
    event.preventDefault();
    submitVisionQuestion(el.visionQuestion.value.trim());
  });
  el.promptChips.forEach(button => {
    button.addEventListener("click", () => {
      el.visionQuestion.value = button.dataset.prompt ?? "";
      submitVisionQuestion(button.dataset.prompt);
    });
  });

  el.settingsForm.addEventListener("submit", async event => {
    event.preventDefault();
    const payload = settingsPayloadFromForm();
    if (!payload.greeting_text) { setSettingsStatus("Greeting text cannot be blank.", "danger"); return; }
    try {
      const session = await applySessionAction(ENDPOINTS.settings, payload);
      app.settingsDirty = false;
      syncSettingsForm(session.settings, true);
      setSettingsStatus("Settings saved.", "ok");
    } catch (error) {
      setSettingsStatus(error.message, "danger");
    }
  });
  el.settingsEstopBtn.addEventListener("click", async () => {
    clearDriveLoop();
    await applySessionAction(ENDPOINTS.emergencyStop);
  });
  el.settingsResetBtn.addEventListener("click", () => applySessionAction(ENDPOINTS.emergencyReset));

  setInterval(() => refreshState().catch(() => null), CONFIG.refreshIntervalMs);
  setInterval(() => refreshVision().catch(() => null), CONFIG.visionRefreshMs);
}

init().catch(error => setSpeechStatus(error.message, "danger"));
