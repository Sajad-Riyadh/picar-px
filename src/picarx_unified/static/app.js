const CONFIG = {
  driveRepeatMs: 200,
  refreshIntervalMs: 2500,
  visionRefreshMs: 450,
  maxMessages: 24,
  maxOverlayBoxes: 12,
  wsRenderThrottleMs: 500,
  reconnectBaseMs: 500,
  reconnectMaxMs: 10000,
  reconnectJitterMs: 250,
  videoDisplaySizeStorageKey: "PICARX_VIDEO_DISPLAY_SIZE",
  videoDisplaySizes: ["small", "medium", "large", "theater"],
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

function $(selector) {
  return document.querySelector(selector);
}

function $$(selector) {
  return [...document.querySelectorAll(selector)];
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
  if (!drive) return "Stopped";
  if (drive.speed === 0) {
    return drive.steering === 0 ? "Stopped" : `Steer ${signed(drive.steering)}`;
  }
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

function videoElementDiagnostics(videoStream, videoFrame) {
  if (!videoStream || !videoFrame) return null;
  const frameRect = videoFrame.getBoundingClientRect();
  return {
    naturalWidth: videoStream.naturalWidth || 0,
    naturalHeight: videoStream.naturalHeight || 0,
    clientWidth: Math.round(videoStream.clientWidth || 0),
    clientHeight: Math.round(videoStream.clientHeight || 0),
    frameWidth: Math.round(frameRect.width || 0),
    frameHeight: Math.round(frameRect.height || 0),
    objectFit: getComputedStyle(videoStream).objectFit,
    selectedSize: document.body.dataset.videoSize || "medium",
  };
}

class DomRegistry {
  constructor() {
    this.cache();
  }

  cache() {
    this.tabs = $$(".tab");
    this.tabPanels = $$(".tab-panels .ctrl-panel");

    this.hwChip = $("#hw-chip");
    this.modeChip = $("#mode-chip");
    this.safetyChip = $("#safety-chip");
    this.micChip = $("#mic-chip");
    this.voiceChip = $("#voice-chip");
    this.detectChip = $("#detect-chip");

    this.connDot = $("#conn-dot");
    this.connLabel = $("#conn-label");

    this.estopFab = $("#estop-fab");
    this.estopBanner = $("#estop-banner");
    this.estopResetBtn = $("#estop-reset-btn");

    this.videoFrame = $("#video-frame");
    this.videoContent = $("#video-content");
    this.videoStream = $("#video-stream");
    this.visionOverlay = $("#vision-overlay");
    this.hudDrive = $("#hud-drive");
    this.hudCam = $("#hud-cam");
    this.hudPerson = $("#hud-person");
    this.hudAuto = $("#hud-auto");
    this.visionSummary = $("#vision-summary");

    this.driveBadge = $("#drive-badge");
    this.driveSpeedSlider = $("#drive-speed-slider");
    this.driveSpeedValue = $("#drive-speed-value");
    this.stopBtn = $("#stop-btn");
    this.lastErrorLabel = $("#last-error-label");
    this.dpadBtns = $$(".dpad[data-drive-control]");

    this.centerCameraBtn = $("#center-camera-btn");
    this.camUp = $("#cam-up");
    this.camDown = $("#cam-down");
    this.camLeft = $("#cam-left");
    this.camRight = $("#cam-right");
    this.camCenter = $("#cam-center");
    this.panSlider = $("#pan-slider");
    this.tiltSlider = $("#tilt-slider");
    this.panValue = $("#pan-value");
    this.tiltValue = $("#tilt-value");
    this.cameraFollowToggle = $("#camera-follow-toggle");
    this.presetChips = $$(".preset-chip");
    this.videoSizeButtons = $$(".video-size-btn");
    this.videoSizeReset = $("#video-size-reset");
    this.videoFullscreenBtn = $("#video-fullscreen-btn");

    this.voiceModeSelect = $("#voice-mode-select");
    this.audioTargetSelect = $("#audio-target-select");
    this.micToggleBtn = $("#mic-toggle-btn");
    this.pushToTalkBtn = $("#push-to-talk-btn");
    this.openMicToggle = $("#open-mic-toggle");
    this.micStateBadge = $("#mic-state-badge");
    this.volumeSlider = $("#volume-slider");
    this.volumeValue = $("#volume-value");
    this.speechStatus = $("#speech-status");
    this.messageCountLabel = $("#message-count-label");
    this.messages = $("#messages");

    this.personDetectedLabel = $("#person-detected-label");
    this.detectedClassesLabel = $("#detected-classes-label");
    this.autonomyStateLabel = $("#autonomy-state-label");
    this.aiProviderLabel = $("#ai-provider-label");
    this.visionUpdatedLabel = $("#vision-updated-label");
    this.lastBehaviorLabel = $("#last-behavior-label");
    this.lastGreetingLabel = $("#last-greeting-label");
    this.autoTrackingToggle = $("#auto-tracking-toggle");
    this.greetingEnabledToggle = $("#greeting-enabled-toggle");
    this.greetingModeSelect = $("#greeting-mode-select");
    this.autonomousModeToggle = $("#autonomous-mode-toggle");
    this.detectionMasterToggle = $("#detection-master-toggle");
    this.faceDetectionToggle = $("#face-detection-toggle");
    this.personDetectionToggle = $("#person-detection-toggle");
    this.catDetectionToggle = $("#cat-detection-toggle");
    this.objectDetectionToggle = $("#object-detection-toggle");
    this.overlayToggle = $("#overlay-toggle");
    this.visionForm = $("#vision-form");
    this.visionQuestion = $("#vision-question");
    this.visionAnswer = $("#vision-answer");
    this.promptChips = $$(".prompt-chip");

    this.settingsForm = $("#settings-form");
    this.greetingTextInput = $("#greeting-text-input");
    this.greetingEnabledInput = $("#greeting-enabled-input");
    this.autoTrackingInput = $("#auto-tracking-input");
    this.settingsAutonomousModeInput = $("#settings-autonomous-mode-input");
    this.settingsDetectionEnabledInput = $("#settings-detection-enabled-input");
    this.settingsFaceDetectionInput = $("#settings-face-detection-input");
    this.settingsPersonDetectionInput = $("#settings-person-detection-input");
    this.settingsCatDetectionInput = $("#settings-cat-detection-input");
    this.settingsObjectDetectionInput = $("#settings-object-detection-input");
    this.settingsOverlayInput = $("#settings-overlay-input");
    this.settingsGreetingMode = $("#settings-greeting-mode");
    this.startupVoiceModeSelect = $("#startup-voice-mode-select");
    this.startupAudioTargetSelect = $("#startup-audio-target-select");
    this.cameraStepInput = $("#camera-step-input");
    this.cameraStepValue = $("#camera-step-value");
    this.cameraRedGainInput = $("#camera-red-gain-input");
    this.cameraRedGainValue = $("#camera-red-gain-value");
    this.cameraGreenGainInput = $("#camera-green-gain-input");
    this.cameraGreenGainValue = $("#camera-green-gain-value");
    this.cameraBlueGainInput = $("#camera-blue-gain-input");
    this.cameraBlueGainValue = $("#camera-blue-gain-value");
    this.autonomousSpeedInput = $("#autonomous-speed-input");
    this.autonomousSpeedValue = $("#autonomous-speed-value");
    this.autonomousTurnInput = $("#autonomous-turn-input");
    this.autonomousTurnValue = $("#autonomous-turn-value");
    this.autonomousStopDistanceInput = $("#autonomous-stop-distance-input");
    this.autonomousStopDistanceValue = $("#autonomous-stop-distance-value");
    this.settingsEstopBtn = $("#settings-estop-btn");
    this.settingsResetBtn = $("#settings-reset-btn");
    this.settingsEstopTriggerBtn = $("#settings-estop-trigger-btn");
    this.settingsEstopReleaseBtn = $("#settings-estop-release-btn");
    this.settingsEstopStatus = $("#settings-estop-status");
    this.settingsSaveStatus = $("#settings-save-status");

    this.menuBtn = $("#menu-btn");
    this.drawer = $("#drawer");
    this.drawerBackdrop = $("#drawer-backdrop");
    this.drawerClose = $("#drawer-close");
    this.drawerToggle = $("#drawer-toggle");
    this.quickMicBtn = $("#quick-mic-btn");
  }
}

class ApiClient {
  async request(path, options = {}) {
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
}

class SessionRenderer {
  constructor(state, dom, callbacks) {
    this.state = state;
    this.dom = dom;
    this.callbacks = callbacks;
  }

  syncRangeReadouts() {
    if (this.dom.panValue) this.dom.panValue.textContent = `${this.dom.panSlider.value} deg`;
    if (this.dom.tiltValue) this.dom.tiltValue.textContent = `${this.dom.tiltSlider.value} deg`;
    if (this.dom.driveSpeedValue) this.dom.driveSpeedValue.textContent = `${this.dom.driveSpeedSlider.value}%`;
    if (this.dom.cameraStepValue) this.dom.cameraStepValue.textContent = `${this.dom.cameraStepInput.value} deg`;
    if (this.dom.cameraRedGainValue) this.dom.cameraRedGainValue.textContent = `${Number(this.dom.cameraRedGainInput.value).toFixed(2)}x`;
    if (this.dom.cameraGreenGainValue) this.dom.cameraGreenGainValue.textContent = `${Number(this.dom.cameraGreenGainInput.value).toFixed(2)}x`;
    if (this.dom.cameraBlueGainValue) this.dom.cameraBlueGainValue.textContent = `${Number(this.dom.cameraBlueGainInput.value).toFixed(2)}x`;
    if (this.dom.autonomousSpeedValue) this.dom.autonomousSpeedValue.textContent = `${this.dom.autonomousSpeedInput.value}%`;
    if (this.dom.autonomousTurnValue) this.dom.autonomousTurnValue.textContent = `${this.dom.autonomousTurnInput.value} deg`;
    if (this.dom.autonomousStopDistanceValue) this.dom.autonomousStopDistanceValue.textContent = `${this.dom.autonomousStopDistanceInput.value} cm`;
    if (this.dom.volumeValue) this.dom.volumeValue.textContent = `${this.dom.volumeSlider.value}%`;
  }

  syncSettingsForm(settings, force = false) {
    if (this.state.settingsDirty && !force) return;
    this.dom.greetingTextInput.value = settings.greeting_text;
    this.dom.greetingEnabledInput.checked = settings.greeting_enabled;
    this.dom.autoTrackingInput.checked = settings.auto_tracking_enabled;
    this.dom.settingsAutonomousModeInput.checked = settings.autonomous_mode_enabled;
    this.dom.settingsDetectionEnabledInput.checked = settings.detection_enabled;
    this.dom.settingsFaceDetectionInput.checked = settings.face_detection_enabled;
    this.dom.settingsPersonDetectionInput.checked = settings.person_detection_enabled;
    this.dom.settingsCatDetectionInput.checked = settings.cat_detection_enabled;
    this.dom.settingsObjectDetectionInput.checked = settings.object_detection_enabled;
    this.dom.settingsOverlayInput.checked = settings.detection_overlay_enabled;
    this.dom.settingsGreetingMode.value = settings.greeting_mode;
    this.dom.startupVoiceModeSelect.value = settings.startup_voice_mode;
    this.dom.startupAudioTargetSelect.value = settings.startup_audio_target;
    this.dom.cameraStepInput.value = String(settings.camera_step_degrees);
    this.dom.cameraRedGainInput.value = String(settings.camera_red_gain);
    this.dom.cameraGreenGainInput.value = String(settings.camera_green_gain);
    this.dom.cameraBlueGainInput.value = String(settings.camera_blue_gain);
    this.dom.autonomousSpeedInput.value = String(settings.autonomous_drive_speed);
    this.dom.autonomousTurnInput.value = String(settings.autonomous_turn_strength);
    this.dom.autonomousStopDistanceInput.value = String(Math.round(settings.autonomous_stop_distance_cm));
    this.dom.cameraFollowToggle.checked = settings.auto_tracking_enabled;
    this.dom.autoTrackingToggle.checked = settings.auto_tracking_enabled;
    this.dom.greetingEnabledToggle.checked = settings.greeting_enabled;
    this.dom.greetingModeSelect.value = settings.greeting_mode;
    this.dom.autonomousModeToggle.checked = settings.autonomous_mode_enabled;
    this.dom.detectionMasterToggle.checked = settings.detection_enabled;
    this.dom.faceDetectionToggle.checked = settings.face_detection_enabled;
    this.dom.personDetectionToggle.checked = settings.person_detection_enabled;
    this.dom.catDetectionToggle.checked = settings.cat_detection_enabled;
    this.dom.objectDetectionToggle.checked = settings.object_detection_enabled;
    this.dom.overlayToggle.checked = settings.detection_overlay_enabled;
    this.syncRangeReadouts();
  }

  renderVisionOverlay(vision, settings = this.state.session?.settings) {
    if (!this.dom.visionOverlay) return;
    this.dom.visionOverlay.replaceChildren();
    if (!settings?.detection_enabled || !settings?.detection_overlay_enabled) return;
    if (!vision?.detections?.length || !vision.frame_width || !vision.frame_height || !this.dom.videoFrame) return;
    const rect = this.dom.videoFrame.getBoundingClientRect();
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
      this.dom.visionOverlay.append(box);
    });
  }

  renderVisionSnapshot(vision, session = this.state.session) {
    if (!vision || !session) return;
    const primary = vision.detections?.[0] ?? null;
    const detectionText = !session.settings.detection_enabled
      ? "Detect: Off"
      : vision.detections?.length ? `Detect: ${vision.detections.length}` : "Detect: Idle";

    if (this.dom.detectChip) {
      this.dom.detectChip.textContent = detectionText;
      this.dom.detectChip.dataset.tone = !session.settings.detection_enabled
        ? "warn"
        : vision.detections?.length ? "active" : "neutral";
    }
    if (this.dom.visionSummary) this.dom.visionSummary.textContent = vision.summary;
    if (this.dom.personDetectedLabel) this.dom.personDetectedLabel.textContent = session.person_detected ? "Yes" : "No";
    if (this.dom.detectedClassesLabel) this.dom.detectedClassesLabel.textContent = formatDetectedClasses(vision);
    if (this.dom.visionUpdatedLabel) this.dom.visionUpdatedLabel.textContent = formatTimestamp(vision.analyzed_at);
    if (this.dom.hudPerson) {
      this.dom.hudPerson.hidden = !primary;
      if (primary) this.dom.hudPerson.textContent = detectionName(primary);
    }
    if (this.dom.hudAuto) {
      const autoEnabled = !!session.settings.autonomous_mode_enabled;
      this.dom.hudAuto.hidden = !autoEnabled;
      if (autoEnabled) {
        this.dom.hudAuto.textContent = session.manual_override_active
          ? "Manual Override"
          : session.control_mode === "autonomous" ? "Autonomous" : "Auto Armed";
      }
    }
    if (this.dom.autonomyStateLabel) {
      this.dom.autonomyStateLabel.textContent = !session.settings.autonomous_mode_enabled
        ? "Off"
        : session.manual_override_active ? "Manual Override" : titleCase(session.control_mode || "autonomous");
    }
    this.renderVisionOverlay(vision, session.settings);
  }

  render(session) {
    this.state.session = session;
    document.body.dataset.estop = session.emergency_stop ? "active" : "clear";
    if (this.dom.estopBanner) this.dom.estopBanner.hidden = !session.emergency_stop;
    if (this.dom.safetyChip) {
      this.dom.safetyChip.textContent = session.emergency_stop ? "! E-STOP" : "Safety OK";
      this.dom.safetyChip.dataset.tone = session.emergency_stop ? "danger" : "ok";
    }
    if (this.dom.modeChip) {
      this.dom.modeChip.textContent = formatControlMode(session);
      this.dom.modeChip.dataset.tone = session.emergency_stop
        ? "danger"
        : session.control_mode === "autonomous" ? "active" : "cool";
    }
    if (this.dom.voiceChip) {
      this.dom.voiceChip.textContent = `Voice: ${titleCase(session.voice_mode)}`;
      this.dom.voiceChip.dataset.tone = session.voice_mode === "mute" ? "neutral" : "cool";
    }
    if (this.dom.hudDrive) this.dom.hudDrive.textContent = `SPD ${signed(session.drive.speed)} / STR ${signed(session.drive.steering)}`;
    if (this.dom.hudCam) this.dom.hudCam.textContent = `PAN ${session.camera.pan} deg / TILT ${session.camera.tilt} deg`;
    if (this.dom.driveBadge) this.dom.driveBadge.textContent = formatDriveSummary(session.drive);
    if (this.dom.lastErrorLabel) this.dom.lastErrorLabel.textContent = session.last_error || "None";
    if (this.dom.aiProviderLabel) this.dom.aiProviderLabel.textContent = titleCase(session.ai_provider);
    if (this.dom.lastBehaviorLabel) this.dom.lastBehaviorLabel.textContent = session.last_behavior_action || session.last_autonomy_action || "None";
    if (this.dom.lastGreetingLabel) this.dom.lastGreetingLabel.textContent = session.last_greeting_text || "No greeting yet.";
    if (this.dom.settingsEstopStatus) {
      this.dom.settingsEstopStatus.textContent = session.emergency_stop
        ? "Emergency stop is active. Motion stays blocked until you explicitly release it."
        : "Emergency stop is clear. Manual drive and autonomy are available when other safety checks pass.";
    }
    if (this.dom.settingsEstopTriggerBtn) this.dom.settingsEstopTriggerBtn.disabled = session.emergency_stop;
    if (this.dom.settingsEstopBtn) this.dom.settingsEstopBtn.disabled = session.emergency_stop;
    if (this.dom.settingsEstopReleaseBtn) this.dom.settingsEstopReleaseBtn.disabled = !session.emergency_stop;
    if (this.dom.settingsResetBtn) this.dom.settingsResetBtn.disabled = !session.emergency_stop;
    if (this.dom.estopResetBtn) this.dom.estopResetBtn.disabled = !session.emergency_stop;

    this.dom.voiceModeSelect.value = session.voice_mode;
    this.dom.audioTargetSelect.value = session.audio_target;
    this.dom.panSlider.value = String(session.camera.pan);
    this.dom.tiltSlider.value = String(session.camera.tilt);
    this.syncSettingsForm(session.settings);
    this.renderVisionSnapshot(session.vision, session);

    if (!this.state.captureActive && !this.state.awaitingReply) {
      this.callbacks.setSpeechStatus(this.callbacks.defaultVoiceHint(session.voice_mode), session.voice_mode === "mute" ? "neutral" : "cool");
    }
    this.callbacks.updateMicBadge();
  }

  renderHealth(health) {
    if (this.dom.hwChip) {
      this.dom.hwChip.textContent = `HW: ${titleCase(health.hardware_backend)}`;
      this.dom.hwChip.dataset.tone = health.hardware_backend === "mockpicarx" ? "warn" : "ok";
    }
    const videoDiagnostics = videoElementDiagnostics(this.dom.videoStream, this.dom.videoFrame);
    const videoSignature = JSON.stringify(videoDiagnostics);
    if (videoSignature !== this.state.lastVideoDiagnostics) {
      this.state.lastVideoDiagnostics = videoSignature;
      console.debug("PiCar-X video diagnostics", {
        browser: videoDiagnostics,
        camera: health.camera,
      });
    }
    if (this.dom.connDot) this.dom.connDot.dataset.ok = "true";
    if (this.dom.connLabel) this.dom.connLabel.textContent = "Online";
  }
}

class AudioController {
  constructor(state) {
    this.state = state;
    this.chunkHandler = null;
  }

  setChunkHandler(handler) {
    this.chunkHandler = handler;
  }

  async ensureAudioContext() {
    if (!this.state.audioContext) {
      this.state.audioContext = new AudioContext();
      await this.state.audioContext.audioWorklet.addModule("/static/pcm-worklet.js");
    }
    if (this.state.audioContext.state === "suspended") await this.state.audioContext.resume();
    return this.state.audioContext;
  }

  setVolume(value) {
    this.state.volume = Number(value);
  }

  getPlaybackGain() {
    return this.state.volume / 100;
  }

  base64FromArrayBuffer(buffer) {
    let text = "";
    const bytes = new Uint8Array(buffer);
    bytes.forEach(value => {
      text += String.fromCharCode(value);
    });
    return btoa(text);
  }

  bytesFromBase64(encoded) {
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  async playRelayChunk(audioBase64, sampleRate) {
    if (!this.state.session || !["browser", "both"].includes(this.state.session.audio_target)) return;
    await this.ensureAudioContext();
    const bytes = this.bytesFromBase64(audioBase64);
    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
    const buffer = this.state.audioContext.createBuffer(1, pcm.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = pcm[index] / 32768;
    }
    const source = this.state.audioContext.createBufferSource();
    const gain = this.state.audioContext.createGain();
    source.buffer = buffer;
    gain.gain.value = this.getPlaybackGain();
    source.connect(gain).connect(this.state.audioContext.destination);
    const startAt = Math.max(this.state.audioContext.currentTime + 0.01, this.state.playbackCursor);
    source.start(startAt);
    this.state.playbackCursor = startAt + buffer.duration;
  }

  async playAssistantAudio(audioBase64) {
    if (!this.state.session || !["browser", "both"].includes(this.state.session.audio_target)) return;
    await this.ensureAudioContext();
    const bytes = this.bytesFromBase64(audioBase64);
    const buffer = await this.state.audioContext.decodeAudioData(bytes.buffer.slice(0));
    const source = this.state.audioContext.createBufferSource();
    const gain = this.state.audioContext.createGain();
    source.buffer = buffer;
    gain.gain.value = this.getPlaybackGain();
    source.connect(gain).connect(this.state.audioContext.destination);
    source.start();
  }

  teardownCapturePipeline() {
    if (this.state.sourceNode) {
      this.state.sourceNode.disconnect();
      this.state.sourceNode = null;
    }
    if (this.state.workletNode) {
      this.state.workletNode.disconnect();
      this.state.workletNode = null;
    }
    if (this.state.monitorNode) {
      this.state.monitorNode.disconnect();
      this.state.monitorNode = null;
    }
    if (this.state.mediaStream) {
      this.state.mediaStream.getTracks().forEach(track => track.stop());
      this.state.mediaStream = null;
    }
  }

  async ensureCapturePipeline() {
    await this.ensureAudioContext();
    if (this.state.mediaStream && this.state.workletNode) return;
    this.state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.state.sourceNode = this.state.audioContext.createMediaStreamSource(this.state.mediaStream);
    this.state.workletNode = new AudioWorkletNode(this.state.audioContext, "pcm-capture");
    this.state.monitorNode = this.state.audioContext.createGain();
    this.state.monitorNode.gain.value = 0;
    this.state.workletNode.port.onmessage = event => {
      if (!this.state.captureActive || !this.chunkHandler) return;
      this.chunkHandler(event.data);
    };
    this.state.sourceNode.connect(this.state.workletNode);
    this.state.workletNode.connect(this.state.monitorNode);
    this.state.monitorNode.connect(this.state.audioContext.destination);
  }
}

class VoiceSocketController {
  constructor(state, renderer, audioController, callbacks) {
    this.state = state;
    this.renderer = renderer;
    this.audioController = audioController;
    this.callbacks = callbacks;
    this.socket = null;
    this.connectPromise = null;
    this.reconnectTimer = null;
    this.reconnectAttempt = 0;
    this.shouldReconnect = true;
  }

  isOpen() {
    return this.socket?.readyState === WebSocket.OPEN;
  }

  sendJson(payload) {
    if (!this.isOpen()) return false;
    this.socket.send(JSON.stringify(payload));
    return true;
  }

  disconnect(reason = "Client closing", allowReconnect = false) {
    this.shouldReconnect = allowReconnect;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    if (!this.socket) return;
    try {
      this.socket.close(1000, reason);
    } catch (_) {
      this.socket = null;
    }
  }

  handleMessage(payload) {
    if (payload.type === "state") {
      const now = performance.now();
      if (this.state.driveCommand && (now - this.state.lastWsRender) < CONFIG.wsRenderThrottleMs) return;
      this.state.lastWsRender = now;
      this.renderer.render(payload.state);
      return;
    }
    if (payload.type === "relay_chunk") {
      this.audioController.playRelayChunk(payload.audio, payload.sample_rate).catch(() => null);
      return;
    }
    if (payload.type === "assistant_audio") {
      this.state.awaitingReply = false;
      this.callbacks.setSpeechStatus("Assistant audio ready.", "ok");
      this.audioController.playAssistantAudio(payload.audio).catch(() => null);
      return;
    }
    if (payload.type === "assistant_reply") {
      this.state.awaitingReply = false;
      this.callbacks.setSpeechStatus("Assistant reply received.", "ok");
      this.callbacks.logMessage("robot", payload.text);
      return;
    }
    if (payload.type === "transcript") {
      this.callbacks.logMessage("you", payload.text);
      return;
    }
    if (payload.type === "error") {
      this.state.awaitingReply = false;
      this.callbacks.setSpeechStatus(payload.message, "danger");
      return;
    }
    if (payload.type === "status") {
      this.callbacks.setSpeechStatus(payload.message, payload.tone || "neutral");
    }
  }

  scheduleReconnect() {
    if (!this.shouldReconnect || this.reconnectTimer) return;
    const baseDelay = Math.min(
      CONFIG.reconnectBaseMs * (2 ** this.reconnectAttempt),
      CONFIG.reconnectMaxMs,
    );
    const delay = baseDelay + Math.floor(Math.random() * CONFIG.reconnectJitterMs);
    this.reconnectAttempt += 1;
    this.callbacks.setSpeechStatus(
      `Voice link lost. Reconnecting in ${(delay / 1000).toFixed(1)}s...`,
      "warn",
    );
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.open().catch(() => null);
    }, delay);
  }

  async open() {
    if (this.isOpen()) return this.socket;
    if (this.connectPromise) return this.connectPromise;
    this.shouldReconnect = true;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const url = `${protocol}://${location.host}${ENDPOINTS.voiceSocket}`;
    const recoveryAttempt = this.reconnectAttempt > 0;

    this.connectPromise = new Promise((resolve, reject) => {
      const socket = new WebSocket(url);
      this.socket = socket;
      let settled = false;

      socket.addEventListener("message", event => {
        try {
          this.handleMessage(JSON.parse(event.data));
        } catch (_) {}
      });

      socket.addEventListener("open", () => {
        settled = true;
        this.state.voiceSocketConnected = true;
        this.reconnectAttempt = 0;
        this.callbacks.updateMicBadge();
        if (recoveryAttempt) {
          this.callbacks.setSpeechStatus("Voice link restored.", "ok");
          this.callbacks.onVoiceReconnect();
        }
        resolve(socket);
      }, { once: true });

      socket.addEventListener("error", () => {
        if (!settled) {
          settled = true;
          reject(new Error("Unable to open voice link."));
        }
      }, { once: true });

      socket.addEventListener("close", () => {
        this.state.voiceSocketConnected = false;
        this.socket = null;
        this.callbacks.onVoiceClose();
        this.callbacks.updateMicBadge();
        if (this.shouldReconnect) {
          this.scheduleReconnect();
          return;
        }
        this.callbacks.setSpeechStatus("Voice link closed.", "neutral");
      });
    });

    try {
      return await this.connectPromise;
    } finally {
      this.connectPromise = null;
    }
  }
}

class DriveController {
  constructor(state, dom, apiClient, callbacks) {
    this.state = state;
    this.dom = dom;
    this.apiClient = apiClient;
    this.callbacks = callbacks;
  }

  currentDriveSpeed() {
    return Number(this.dom.driveSpeedSlider.value);
  }

  deriveDriveCommand() {
    const browserInput = this.state.browserDriveInput;
    const keyboardInput = this.state.keyboardDriveInput;
    const forward = browserInput.forward > 0 || keyboardInput.forward;
    const backward = browserInput.backward > 0 || keyboardInput.backward;
    const left = browserInput.left > 0 || keyboardInput.left;
    const right = browserInput.right > 0 || keyboardInput.right;
    const speedSign = Number(forward) - Number(backward);
    const steeringSign = Number(right) - Number(left);
    if (speedSign === 0 && steeringSign === 0) return null;
    return {
      speed: this.currentDriveSpeed() * speedSign,
      steering: steeringSign * 25,
      source: browserInput.activeCount > 0 ? "browser" : "keyboard",
    };
  }

  async sendDriveFast(command) {
    await this.apiClient.request(ENDPOINTS.driveFast ?? ENDPOINTS.drive, {
      method: "POST",
      json: command,
    });
    if (this.dom.hudDrive) this.dom.hudDrive.textContent = `SPD ${signed(command.speed)} / STR ${signed(command.steering)}`;
    if (this.dom.driveBadge) {
      this.dom.driveBadge.textContent = formatDriveSummary(command);
    }
  }

  clearDriveLoop() {
    clearTimeout(this.state.driveInterval);
    this.state.driveInterval = null;
    this.state.driveCommand = null;
    this.state.driveBusy = false;
  }

  async stopDriveLoop() {
    if (!this.state.driveInterval && !this.state.driveCommand) return;
    this.clearDriveLoop();
    const session = await this.apiClient.request(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
    if (session) this.callbacks.renderSession(session);
  }

  async startDriveLoop(command, button = null) {
    if (this.state.session?.emergency_stop) {
      this.callbacks.setSpeechStatus("Reset emergency stop before driving.", "danger");
      return;
    }
    if (
      this.state.driveCommand
      && this.state.driveCommand.speed === command.speed
      && this.state.driveCommand.steering === command.steering
      && this.state.driveCommand.source === command.source
    ) {
      return;
    }
    this.state.driveCommand = command;
    if (this.state.driveBusy || this.state.driveInterval) return;

    const tick = async () => {
      if (!this.state.driveCommand) return;
      this.state.driveBusy = true;
      try {
        await this.sendDriveFast(this.state.driveCommand);
      } catch (error) {
        this.clearDriveLoop();
        this.callbacks.setSpeechStatus(error.message, "danger");
        this.apiClient.request(ENDPOINTS.driveStop, { method: "POST" }).catch(() => null);
        return;
      }
      this.state.driveBusy = false;
      if (this.state.driveCommand) {
        this.state.driveInterval = window.setTimeout(tick, CONFIG.driveRepeatMs);
      }
    };

    tick();
  }

  async syncDriveLoop() {
    const command = this.deriveDriveCommand();
    if (!command) {
      await this.stopDriveLoop();
      return;
    }
    await this.startDriveLoop(command);
  }

  setBrowserDriveInput(control, active, button) {
    if (control === "stop") {
      if (active) {
        this.resetManualDriveInput();
      }
      return this.syncDriveLoop();
    }
    const browserInput = this.state.browserDriveInput;
    const nextValue = Math.max(0, (browserInput[control] ?? 0) + (active ? 1 : -1));
    browserInput.activeCount += active ? 1 : -1;
    browserInput.activeCount = Math.max(0, browserInput.activeCount);
    browserInput[control] = nextValue;
    this.callbacks.setButtonActive(button, active);
    return this.syncDriveLoop();
  }

  setKeyboardDriveInput(control, active) {
    this.state.keyboardDriveInput[control] = active;
    return this.syncDriveLoop();
  }

  resetManualDriveInput() {
    this.state.browserDriveInput = {
      forward: 0,
      backward: 0,
      left: 0,
      right: 0,
      activeCount: 0,
    };
    this.state.keyboardDriveInput = {
      forward: false,
      backward: false,
      left: false,
      right: false,
    };
    this.dom.dpadBtns.forEach(button => this.callbacks.setButtonActive(button, false));
  }

  bindDriveButton(button, bindMomentaryPointerControl) {
    const control = String(button.dataset.driveControl || "").trim();
    bindMomentaryPointerControl(button, {
      start: () => this.setBrowserDriveInput(control, true, button),
      stop: () => this.setBrowserDriveInput(control, false, button),
    });
  }

  bindKeyboard() {
    const keyMap = {
      w: "forward",
      a: "left",
      d: "right",
      s: "backward",
    };

    window.addEventListener("keydown", event => {
      const key = event.key.toLowerCase();
      const control = keyMap[key];
      if (!control || event.repeat || this.state.keyboardDriveInput[control]) return;
      if (["INPUT", "SELECT", "TEXTAREA"].includes(event.target.tagName)) return;
      event.preventDefault();
      this.setKeyboardDriveInput(control, true).catch(() => null);
    });

    window.addEventListener("keyup", event => {
      const control = keyMap[event.key.toLowerCase()];
      if (!control || !this.state.keyboardDriveInput[control]) return;
      this.setKeyboardDriveInput(control, false).catch(() => null);
    });

    window.addEventListener("blur", () => {
      this.resetManualDriveInput();
      this.stopDriveLoop().catch(() => null);
    });
  }

  stopDriveOnUnload() {
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
}

class SettingsController {
  constructor(state, dom, apiClient, renderer, callbacks) {
    this.state = state;
    this.dom = dom;
    this.apiClient = apiClient;
    this.renderer = renderer;
    this.callbacks = callbacks;
  }

  async saveSettingsPatch(patch) {
    const session = await this.apiClient.request(ENDPOINTS.settings, {
      method: "POST",
      json: patch,
    });
    this.state.settingsDirty = false;
    this.renderer.syncSettingsForm(session.settings, true);
    this.callbacks.setSettingsStatus("Settings saved.", "ok");
    this.renderer.render(session);
    return session;
  }

  settingsPayloadFromForm() {
    return {
      greeting_text: this.dom.greetingTextInput.value.trim(),
      greeting_enabled: this.dom.greetingEnabledInput.checked,
      greeting_mode: this.dom.settingsGreetingMode.value,
      auto_tracking_enabled: this.dom.autoTrackingInput.checked,
      detection_enabled: this.dom.settingsDetectionEnabledInput.checked,
      face_detection_enabled: this.dom.settingsFaceDetectionInput.checked,
      person_detection_enabled: this.dom.settingsPersonDetectionInput.checked,
      cat_detection_enabled: this.dom.settingsCatDetectionInput.checked,
      object_detection_enabled: this.dom.settingsObjectDetectionInput.checked,
      detection_overlay_enabled: this.dom.settingsOverlayInput.checked,
      autonomous_mode_enabled: this.dom.settingsAutonomousModeInput.checked,
      camera_step_degrees: Number(this.dom.cameraStepInput.value),
      camera_red_gain: Number(this.dom.cameraRedGainInput.value),
      camera_green_gain: Number(this.dom.cameraGreenGainInput.value),
      camera_blue_gain: Number(this.dom.cameraBlueGainInput.value),
      autonomous_drive_speed: Number(this.dom.autonomousSpeedInput.value),
      autonomous_turn_strength: Number(this.dom.autonomousTurnInput.value),
      autonomous_stop_distance_cm: Number(this.dom.autonomousStopDistanceInput.value),
      startup_voice_mode: this.dom.startupVoiceModeSelect.value,
      startup_audio_target: this.dom.startupAudioTargetSelect.value,
    };
  }

  cameraGainPatchFromForm() {
    return {
      camera_red_gain: Number(this.dom.cameraRedGainInput.value),
      camera_green_gain: Number(this.dom.cameraGreenGainInput.value),
      camera_blue_gain: Number(this.dom.cameraBlueGainInput.value),
    };
  }

  wireSettingsDirtyTracking() {
    [
      this.dom.greetingTextInput,
      this.dom.greetingEnabledInput,
      this.dom.autoTrackingInput,
      this.dom.settingsAutonomousModeInput,
      this.dom.settingsDetectionEnabledInput,
      this.dom.settingsFaceDetectionInput,
      this.dom.settingsPersonDetectionInput,
      this.dom.settingsCatDetectionInput,
      this.dom.settingsObjectDetectionInput,
      this.dom.settingsOverlayInput,
      this.dom.settingsGreetingMode,
      this.dom.startupVoiceModeSelect,
      this.dom.startupAudioTargetSelect,
      this.dom.cameraStepInput,
      this.dom.cameraRedGainInput,
      this.dom.cameraGreenGainInput,
      this.dom.cameraBlueGainInput,
      this.dom.autonomousSpeedInput,
      this.dom.autonomousTurnInput,
      this.dom.autonomousStopDistanceInput,
    ].forEach(node => {
      if (!node) return;
      const markDirty = () => {
        this.state.settingsDirty = true;
        this.callbacks.setSettingsStatus("Unsaved changes.", "warn");
        this.renderer.syncRangeReadouts();
      };
      node.addEventListener("input", markDirty);
      node.addEventListener("change", markDirty);
    });
  }

  bindInstantToggle(node, patchFactory) {
    if (!node) return;
    node.addEventListener("change", () => {
      this.saveSettingsPatch(patchFactory()).catch(error => this.callbacks.setSettingsStatus(error.message, "danger"));
    });
  }
}

class PiCarDashboard {
  constructor() {
    this.state = {
      activePanel: "camera",
      session: null,
      settingsDirty: false,
      audioContext: null,
      playbackCursor: 0,
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
      browserDriveInput: {
        forward: 0,
        backward: 0,
        left: 0,
        right: 0,
        activeCount: 0,
      },
      keyboardDriveInput: {
        forward: false,
        backward: false,
        left: false,
        right: false,
      },
      lastWsRender: 0,
      refreshPromise: null,
      refreshQueued: false,
      visionPromise: null,
      visionQueued: false,
      lastVideoDiagnostics: null,
      videoDisplaySize: "medium",
      volume: 80,
      voiceSocketConnected: false,
    };

    this.dom = new DomRegistry();
    this.apiClient = new ApiClient();
    this.audioController = new AudioController(this.state);
    this.renderer = new SessionRenderer(this.state, this.dom, {
      defaultVoiceHint: mode => this.defaultVoiceHint(mode),
      setSpeechStatus: (message, tone) => this.setSpeechStatus(message, tone),
      updateMicBadge: () => this.updateMicBadge(),
    });
    this.voiceSocket = new VoiceSocketController(
      this.state,
      this.renderer,
      this.audioController,
      {
        setSpeechStatus: (message, tone) => this.setSpeechStatus(message, tone),
        updateMicBadge: () => this.updateMicBadge(),
        logMessage: (role, text) => this.logMessage(role, text),
        onVoiceReconnect: () => this.onVoiceReconnect(),
        onVoiceClose: () => this.onVoiceClose(),
      },
    );
    this.driveController = new DriveController(
      this.state,
      this.dom,
      this.apiClient,
      {
        renderSession: session => this.renderer.render(session),
        setSpeechStatus: (message, tone) => this.setSpeechStatus(message, tone),
        setButtonActive: (button, active) => this.setButtonActive(button, active),
      },
    );
    this.settingsController = new SettingsController(
      this.state,
      this.dom,
      this.apiClient,
      this.renderer,
      {
        setSettingsStatus: (message, tone) => this.setSettingsStatus(message, tone),
      },
    );
    this.audioController.setChunkHandler(buffer => {
      if (!this.voiceSocket.isOpen()) return;
      this.voiceSocket.sendJson({
        type: "pcm_chunk",
        audio: this.audioController.base64FromArrayBuffer(buffer),
      });
    });
  }

  defaultVoiceHint(mode) {
    if (mode === "relay") return "Relay mode streams your browser mic to the speaker target.";
    if (mode === "ai_reply") return "AI Reply needs browser speech recognition or Gemini server transcription before it can answer.";
    return "Mic idle. Choose Relay or AI Reply to open the voice path.";
  }

  hasBrowserSpeechRecognition() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  hasServerTranscription() {
    return this.state.session?.ai_provider === "gemini-live";
  }

  canTranscribeAiReplyTurn() {
    return this.hasBrowserSpeechRecognition() || this.hasServerTranscription();
  }

  setButtonActive(button, active) {
    if (!button) return;
    button.dataset.active = active ? "true" : "false";
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }

  setSpeechStatus(message, tone = "neutral") {
    if (!this.dom.speechStatus) return;
    this.dom.speechStatus.textContent = message;
    this.dom.speechStatus.dataset.tone = tone;
  }

  setSettingsStatus(message, tone = "neutral") {
    if (!this.dom.settingsSaveStatus) return;
    this.dom.settingsSaveStatus.textContent = message;
    this.dom.settingsSaveStatus.dataset.tone = tone;
  }

  updateMessageCount() {
    if (this.dom.messageCountLabel) {
      this.dom.messageCountLabel.textContent = `${this.dom.messages.childElementCount}`;
    }
  }

  updateMicBadge() {
    if (!this.dom.micStateBadge) return;
    if (this.state.captureActive) {
      this.dom.micStateBadge.textContent = "Listening";
      this.dom.micStateBadge.dataset.state = "listening";
    } else if (this.state.openMic && this.state.voiceSocketConnected) {
      this.dom.micStateBadge.textContent = "Ready";
      this.dom.micStateBadge.dataset.state = "on";
    } else {
      this.dom.micStateBadge.textContent = "Off";
      this.dom.micStateBadge.dataset.state = "off";
    }
    if (this.dom.micChip) {
      this.dom.micChip.textContent = this.state.captureActive ? "Mic: Live" : "Mic: Off";
      this.dom.micChip.dataset.tone = this.state.captureActive ? "active" : "neutral";
    }
  }

  setVideoDisplaySize(size, { save = true } = {}) {
    const nextSize = CONFIG.videoDisplaySizes.includes(size) ? size : "medium";
    this.state.videoDisplaySize = nextSize;
    this.applyVideoDisplaySize({ save });
  }

  applyVideoDisplaySize({ save = true } = {}) {
    const size = CONFIG.videoDisplaySizes.includes(this.state.videoDisplaySize)
      ? this.state.videoDisplaySize
      : "medium";
    this.state.videoDisplaySize = size;
    document.body.dataset.videoSize = size;
    this.dom.videoSizeButtons.forEach(button => {
      const active = button.dataset.videoSizeOption === size;
      button.dataset.active = active ? "true" : "false";
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (save) {
      try {
        localStorage.setItem(CONFIG.videoDisplaySizeStorageKey, size);
      } catch (_) {}
    }
    queueMicrotask(() => this.renderer.renderVisionOverlay(this.state.session?.vision, this.state.session?.settings));
    const diagnostics = videoElementDiagnostics(this.dom.videoStream, this.dom.videoFrame);
    console.debug("PiCar-X video display size", diagnostics);
  }

  resetVideoDisplaySize() {
    this.setVideoDisplaySize("medium");
  }

  restoreVideoDisplaySize() {
    let storedSize = "medium";
    try {
      storedSize = localStorage.getItem(CONFIG.videoDisplaySizeStorageKey) || "medium";
    } catch (_) {}
    this.setVideoDisplaySize(storedSize, { save: false });
  }

  enterVideoFullscreen() {
    const target = this.dom.videoFrame;
    if (!target?.requestFullscreen) {
      this.setSpeechStatus("Fullscreen is not supported by this browser.", "warn");
      return;
    }
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => null);
      return;
    }
    target.requestFullscreen().catch(error => this.setSpeechStatus(error.message, "danger"));
  }

  logMessage(role, text) {
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
    this.dom.messages.prepend(row);
    while (this.dom.messages.childElementCount > CONFIG.maxMessages) {
      this.dom.messages.lastElementChild?.remove();
    }
    this.updateMessageCount();
  }

  showPanel(name) {
    this.state.activePanel = name;
    this.dom.tabs.forEach(tab => tab.classList.toggle("active", tab.dataset.panel === name));
    this.dom.tabPanels.forEach(panel => {
      panel.hidden = panel.id !== `panel-${name}`;
    });
  }

  openDrawer() {
    this.dom.drawer.classList.add("open");
    this.dom.drawerBackdrop.classList.add("open");
  }

  closeDrawer() {
    this.dom.drawer.classList.remove("open");
    this.dom.drawerBackdrop.classList.remove("open");
  }

  toggleDrawer() {
    if (this.dom.drawer.classList.contains("open")) {
      this.closeDrawer();
      return;
    }
    this.openDrawer();
  }

  onVoiceClose() {
    this.state.captureActive = false;
    this.state.awaitingReply = false;
    this.setButtonActive(this.dom.pushToTalkBtn, false);
  }

  onVoiceReconnect() {
    if (!this.state.openMic) return;
    this.state.captureActive = true;
    this.updateMicBadge();
  }

  async applySessionAction(path, json) {
    const session = await this.apiClient.request(path, {
      method: "POST",
      ...(json !== undefined ? { json } : {}),
    });
    this.renderer.render(session);
    return session;
  }

  async refreshState() {
    if (this.state.driveCommand) return;
    if (this.state.refreshPromise) {
      this.state.refreshQueued = true;
      return this.state.refreshPromise;
    }
    this.state.refreshPromise = (async () => {
      const [session, health] = await Promise.all([
        this.apiClient.request(ENDPOINTS.state),
        this.apiClient.request(ENDPOINTS.health),
      ]);
      this.renderer.render(session);
      this.renderer.renderHealth(health);
    })();
    try {
      await this.state.refreshPromise;
    } finally {
      this.state.refreshPromise = null;
      if (this.state.refreshQueued) {
        this.state.refreshQueued = false;
        queueMicrotask(() => this.refreshState().catch(() => null));
      }
    }
  }

  async refreshVision() {
    if (this.state.visionPromise) {
      this.state.visionQueued = true;
      return this.state.visionPromise;
    }
    this.state.visionPromise = (async () => {
      const vision = await this.apiClient.request(ENDPOINTS.vision);
      if (!this.state.session) return;
      this.state.session.vision = vision;
      this.state.session.person_detected = (vision.detections || []).some(detection => ["face", "person"].includes(detection.label));
      this.renderer.renderVisionSnapshot(vision, this.state.session);
    })();
    try {
      await this.state.visionPromise;
    } finally {
      this.state.visionPromise = null;
      if (this.state.visionQueued) {
        this.state.visionQueued = false;
        queueMicrotask(() => this.refreshVision().catch(() => null));
      }
    }
  }

  configureSpeechRecognition() {
    const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor || this.state.recognition) return;
    this.state.recognition = new SpeechRecognitionCtor();
    this.state.recognition.lang = "en-US";
    this.state.recognition.continuous = true;
    this.state.recognition.interimResults = true;
    this.state.recognition.onresult = event => {
      const chunks = [];
      for (let index = 0; index < event.results.length; index += 1) {
        chunks.push(event.results[index][0].transcript);
      }
      this.state.transcript = chunks.join(" ").trim();
    };
    this.state.recognition.onerror = event => {
      if (this.state.session?.voice_mode !== "ai_reply") return;
      this.setSpeechStatus(
        `Browser speech recognition failed${event?.error ? `: ${event.error}` : "."}`,
        "warn",
      );
    };
  }

  async startTalking() {
    if (this.state.session?.voice_mode === "mute") {
      this.setSpeechStatus("Switch voice mode out of Mute first.", "neutral");
      return;
    }
    if (this.state.session?.voice_mode === "ai_reply" && !this.canTranscribeAiReplyTurn()) {
      this.setSpeechStatus(
        "AI Reply needs browser speech recognition or GEMINI_API_KEY-backed server transcription.",
        "danger",
      );
      this.state.openMic = false;
      this.dom.openMicToggle.checked = false;
      this.dom.micToggleBtn.textContent = "Open Mic";
      this.dom.micToggleBtn.classList.remove("btn-danger");
      this.dom.micToggleBtn.classList.add("btn-accent");
      this.updateMicBadge();
      return;
    }
    await this.voiceSocket.open();
    await this.audioController.ensureCapturePipeline();
    this.configureSpeechRecognition();
    this.state.transcript = "";
    this.state.awaitingReply = false;
    this.state.captureActive = true;
    this.setButtonActive(this.dom.pushToTalkBtn, true);
    this.updateMicBadge();
    if (this.state.session?.voice_mode === "ai_reply" && this.state.recognition) {
      try {
        this.state.recognition.start();
      } catch (_) {}
    }
    this.setSpeechStatus("Listening...", "cool");
  }

  async stopTalking() {
    if (!this.state.captureActive) return;
    this.state.captureActive = false;
    this.setButtonActive(this.dom.pushToTalkBtn, false);
    this.updateMicBadge();
    if (this.state.recognition) {
      try {
        this.state.recognition.stop();
      } catch (_) {}
    }
    if (
      this.state.session?.voice_mode === "ai_reply"
      && !this.state.transcript
      && !this.hasServerTranscription()
    ) {
      this.setSpeechStatus(
        "No transcript path is available. Use Chrome speech recognition or configure GEMINI_API_KEY.",
        "danger",
      );
      return;
    }
    if (!this.voiceSocket.isOpen()) return;
    if (this.state.transcript) {
      this.voiceSocket.sendJson({ type: "transcript", text: this.state.transcript });
    }
    this.state.awaitingReply = this.state.session?.voice_mode === "ai_reply";
    this.voiceSocket.sendJson({ type: "commit" });
    this.setSpeechStatus(this.state.awaitingReply ? "Waiting for AI reply..." : "Finishing relay...", "warn");
  }

  async toggleOpenMic(forceOff = false) {
    if (forceOff || this.state.openMic) {
      this.state.openMic = false;
      this.dom.openMicToggle.checked = false;
      this.dom.micToggleBtn.textContent = "Open Mic";
      this.dom.micToggleBtn.classList.remove("btn-danger");
      this.dom.micToggleBtn.classList.add("btn-accent");
      await this.stopTalking();
    } else {
      this.state.openMic = true;
      this.dom.openMicToggle.checked = true;
      this.dom.micToggleBtn.textContent = "Mic On - Stop";
      this.dom.micToggleBtn.classList.remove("btn-accent");
      this.dom.micToggleBtn.classList.add("btn-danger");
      await this.startTalking();
    }
    this.updateMicBadge();
  }

  async updateCamera(pan, tilt) {
    await this.applySessionAction(ENDPOINTS.camera, { pan, tilt });
  }

  async moveCameraBy(deltaPan, deltaTilt) {
    if (!this.state.session) return;
    const pan = Number(this.state.session.camera.pan) + deltaPan;
    const tilt = Number(this.state.session.camera.tilt) + deltaTilt;
    this.dom.panSlider.value = String(pan);
    this.dom.tiltSlider.value = String(tilt);
    this.renderer.syncRangeReadouts();
    await this.updateCamera(pan, tilt);
  }

  async submitVisionQuestion(question) {
    if (!question) return;
    this.dom.visionAnswer.textContent = "Thinking...";
    try {
      const response = await this.apiClient.request(ENDPOINTS.visionQuestion, {
        method: "POST",
        json: { question },
      });
      this.dom.visionAnswer.textContent = response.answer;
    } catch (error) {
      this.dom.visionAnswer.textContent = error.message;
    }
  }

  bindMomentaryPointerControl(node, { start, stop }) {
    let pointerId = null;
    const release = () => {
      if (pointerId === null) return;
      pointerId = null;
      Promise.resolve(stop()).catch(error => this.setSpeechStatus(error.message, "danger"));
    };
    node.addEventListener("pointerdown", event => {
      if (pointerId !== null || (event.pointerType === "mouse" && event.button !== 0)) return;
      pointerId = event.pointerId;
      try {
        node.setPointerCapture(event.pointerId);
      } catch (_) {}
      event.preventDefault();
      Promise.resolve(start(event)).catch(error => {
        pointerId = null;
        this.setSpeechStatus(error.message, "danger");
      });
    });
    node.addEventListener("pointerup", release);
    node.addEventListener("pointercancel", release);
    node.addEventListener("lostpointercapture", release);
    node.addEventListener("contextmenu", event => event.preventDefault());
  }

  registerGlobalCleanup() {
    window.addEventListener("beforeunload", () => {
      this.driveController.stopDriveOnUnload();
      this.audioController.teardownCapturePipeline();
      this.voiceSocket.disconnect("Browser unloading", false);
    });
  }

  bindUi() {
    this.dom.tabs.forEach(tab => tab.addEventListener("click", () => this.showPanel(tab.dataset.panel)));
    this.dom.menuBtn.addEventListener("click", () => this.toggleDrawer());
    this.dom.drawerToggle.addEventListener("click", () => this.toggleDrawer());
    this.dom.drawerClose.addEventListener("click", () => this.closeDrawer());
    this.dom.drawerBackdrop.addEventListener("click", () => this.closeDrawer());
    window.addEventListener("keydown", event => {
      if (event.key === "Escape") this.closeDrawer();
    });
    window.addEventListener("resize", () => {
      this.renderer.renderVisionOverlay(this.state.session?.vision, this.state.session?.settings);
    });
    this.dom.videoStream.addEventListener("load", () => {
      this.renderer.renderVisionOverlay(this.state.session?.vision, this.state.session?.settings);
    });
    this.dom.videoSizeButtons.forEach(button => {
      button.addEventListener("click", () => this.setVideoDisplaySize(button.dataset.videoSizeOption));
    });
    this.dom.videoSizeReset.addEventListener("click", () => this.resetVideoDisplaySize());
    this.dom.videoFullscreenBtn.addEventListener("click", () => this.enterVideoFullscreen());
    document.addEventListener("fullscreenchange", () => {
      this.renderer.renderVisionOverlay(this.state.session?.vision, this.state.session?.settings);
    });

    this.dom.quickMicBtn.addEventListener("click", () => this.toggleOpenMic());

    this.dom.dpadBtns.forEach(button => {
      this.setButtonActive(button, false);
      this.driveController.bindDriveButton(button, (node, handlers) => this.bindMomentaryPointerControl(node, handlers));
    });
    this.driveController.bindKeyboard();
    this.registerGlobalCleanup();
    this.settingsController.wireSettingsDirtyTracking();

    this.dom.estopFab.addEventListener("click", async () => {
      if (this.state.session?.emergency_stop) {
        await this.applySessionAction(ENDPOINTS.emergencyReset);
        return;
      }
      this.driveController.resetManualDriveInput();
      this.driveController.clearDriveLoop();
      await this.applySessionAction(ENDPOINTS.emergencyStop);
    });
    this.dom.estopResetBtn.addEventListener("click", () => this.applySessionAction(ENDPOINTS.emergencyReset));

    this.dom.stopBtn.addEventListener("click", async () => {
      this.driveController.resetManualDriveInput();
      this.driveController.clearDriveLoop();
      await this.applySessionAction(ENDPOINTS.driveStop);
    });
    this.dom.driveSpeedSlider.addEventListener("input", () => this.renderer.syncRangeReadouts());
    this.dom.voiceModeSelect.addEventListener("change", () => this.applySessionAction(ENDPOINTS.voiceMode, { mode: this.dom.voiceModeSelect.value }));
    this.dom.audioTargetSelect.addEventListener("change", () => this.applySessionAction(ENDPOINTS.audioTarget, { target: this.dom.audioTargetSelect.value }));

    this.dom.micToggleBtn.addEventListener("click", () => this.toggleOpenMic());
    this.dom.openMicToggle.addEventListener("change", () => this.toggleOpenMic(!this.dom.openMicToggle.checked));
    this.bindMomentaryPointerControl(this.dom.pushToTalkBtn, {
      start: () => this.startTalking(),
      stop: () => {
        if (this.state.openMic) return;
        return this.stopTalking();
      },
    });
    this.dom.volumeSlider.addEventListener("input", () => {
      this.audioController.setVolume(this.dom.volumeSlider.value);
      this.renderer.syncRangeReadouts();
    });

    const cameraStep = () => this.state.session?.settings?.camera_step_degrees ?? 5;
    this.dom.camUp.addEventListener("click", () => this.moveCameraBy(0, cameraStep()));
    this.dom.camDown.addEventListener("click", () => this.moveCameraBy(0, -cameraStep()));
    this.dom.camLeft.addEventListener("click", () => this.moveCameraBy(-cameraStep(), 0));
    this.dom.camRight.addEventListener("click", () => this.moveCameraBy(cameraStep(), 0));
    this.dom.camCenter.addEventListener("click", () => {
      this.dom.panSlider.value = "0";
      this.dom.tiltSlider.value = "0";
      this.renderer.syncRangeReadouts();
      this.updateCamera(0, 0);
    });
    this.dom.centerCameraBtn.addEventListener("click", () => {
      this.dom.panSlider.value = "0";
      this.dom.tiltSlider.value = "0";
      this.renderer.syncRangeReadouts();
      this.updateCamera(0, 0);
    });
    this.dom.panSlider.addEventListener("input", () => this.renderer.syncRangeReadouts());
    this.dom.tiltSlider.addEventListener("input", () => this.renderer.syncRangeReadouts());
    this.dom.panSlider.addEventListener("change", () => this.updateCamera(Number(this.dom.panSlider.value), Number(this.dom.tiltSlider.value)).catch(error => this.setSpeechStatus(error.message, "danger")));
    this.dom.tiltSlider.addEventListener("change", () => this.updateCamera(Number(this.dom.panSlider.value), Number(this.dom.tiltSlider.value)).catch(error => this.setSpeechStatus(error.message, "danger")));
    this.dom.presetChips.forEach(button => button.addEventListener("click", () => this.updateCamera(Number(button.dataset.pan), Number(button.dataset.tilt))));
    this.settingsController.bindInstantToggle(this.dom.cameraFollowToggle, () => ({ auto_tracking_enabled: this.dom.cameraFollowToggle.checked }));
    [this.dom.cameraRedGainInput, this.dom.cameraGreenGainInput, this.dom.cameraBlueGainInput].forEach(node => {
      node.addEventListener("change", () => this.settingsController.saveSettingsPatch(this.settingsController.cameraGainPatchFromForm()).catch(error => this.setSettingsStatus(error.message, "danger")));
    });

    this.settingsController.bindInstantToggle(this.dom.autoTrackingToggle, () => ({ auto_tracking_enabled: this.dom.autoTrackingToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.greetingEnabledToggle, () => ({ greeting_enabled: this.dom.greetingEnabledToggle.checked }));
    this.dom.greetingModeSelect.addEventListener("change", () => this.settingsController.saveSettingsPatch({ greeting_mode: this.dom.greetingModeSelect.value }).catch(error => this.setSettingsStatus(error.message, "danger")));
    this.settingsController.bindInstantToggle(this.dom.autonomousModeToggle, () => ({ autonomous_mode_enabled: this.dom.autonomousModeToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.detectionMasterToggle, () => ({ detection_enabled: this.dom.detectionMasterToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.faceDetectionToggle, () => ({ face_detection_enabled: this.dom.faceDetectionToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.personDetectionToggle, () => ({ person_detection_enabled: this.dom.personDetectionToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.catDetectionToggle, () => ({ cat_detection_enabled: this.dom.catDetectionToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.objectDetectionToggle, () => ({ object_detection_enabled: this.dom.objectDetectionToggle.checked }));
    this.settingsController.bindInstantToggle(this.dom.overlayToggle, () => ({ detection_overlay_enabled: this.dom.overlayToggle.checked }));

    this.dom.visionForm.addEventListener("submit", event => {
      event.preventDefault();
      this.submitVisionQuestion(this.dom.visionQuestion.value.trim());
    });
    this.dom.promptChips.forEach(button => {
      button.addEventListener("click", () => {
        this.dom.visionQuestion.value = button.dataset.prompt ?? "";
        this.submitVisionQuestion(button.dataset.prompt);
      });
    });

    this.dom.settingsForm.addEventListener("submit", async event => {
      event.preventDefault();
      const payload = this.settingsController.settingsPayloadFromForm();
      if (!payload.greeting_text) {
        this.setSettingsStatus("Greeting text cannot be blank.", "danger");
        return;
      }
      try {
        const session = await this.apiClient.request(ENDPOINTS.settings, {
          method: "POST",
          json: payload,
        });
        this.state.settingsDirty = false;
        this.renderer.syncSettingsForm(session.settings, true);
        this.setSettingsStatus("Settings saved.", "ok");
        this.renderer.render(session);
      } catch (error) {
        this.setSettingsStatus(error.message, "danger");
      }
    });
    this.dom.settingsEstopBtn.addEventListener("click", async () => {
      this.driveController.resetManualDriveInput();
      this.driveController.clearDriveLoop();
      await this.applySessionAction(ENDPOINTS.emergencyStop);
    });
    this.dom.settingsResetBtn.addEventListener("click", () => this.applySessionAction(ENDPOINTS.emergencyReset));
    this.dom.settingsEstopTriggerBtn.addEventListener("click", async () => {
      this.driveController.resetManualDriveInput();
      this.driveController.clearDriveLoop();
      await this.applySessionAction(ENDPOINTS.emergencyStop);
    });
    this.dom.settingsEstopReleaseBtn.addEventListener("click", () => this.applySessionAction(ENDPOINTS.emergencyReset));
  }

  async init() {
    this.showPanel("camera");
    this.restoreVideoDisplaySize();
    this.renderer.syncRangeReadouts();
    this.updateMessageCount();
    this.bindUi();

    await Promise.all([
      this.refreshState().catch(() => null),
      this.refreshVision().catch(() => null),
    ]);
    this.voiceSocket.open().catch(error => {
      this.setSpeechStatus(error.message, "danger");
      this.logMessage("system", "Voice link will keep retrying automatically.");
    });

    window.setInterval(() => this.refreshState().catch(() => null), CONFIG.refreshIntervalMs);
    window.setInterval(() => this.refreshVision().catch(() => null), CONFIG.visionRefreshMs);
  }
}

const dashboard = new PiCarDashboard();
dashboard.init().catch(error => {
  const speechStatus = $("#speech-status");
  if (!speechStatus) return;
  speechStatus.textContent = error.message;
  speechStatus.dataset.tone = "danger";
});
