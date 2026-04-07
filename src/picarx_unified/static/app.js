const state = {
  session: null,
  audioContext: null,
  playbackCursor: 0,
  ws: null,
  mediaStream: null,
  sourceNode: null,
  workletNode: null,
  captureActive: false,
  recognition: null,
  transcript: "",
  driveInterval: null,
};

const el = {
  voiceModeLabel: document.querySelector("#voice-mode-label"),
  audioTargetLabel: document.querySelector("#audio-target-label"),
  hardwareLabel: document.querySelector("#hardware-label"),
  estopLabel: document.querySelector("#estop-label"),
  panSlider: document.querySelector("#pan-slider"),
  tiltSlider: document.querySelector("#tilt-slider"),
  visionSummary: document.querySelector("#vision-summary"),
  speechStatus: document.querySelector("#speech-status"),
  messages: document.querySelector("#messages"),
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
};

function logMessage(role, text) {
  const row = document.createElement("div");
  row.className = "message";
  row.innerHTML = `<span class="role">${role}</span><div>${text}</div>`;
  el.messages.prepend(row);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  return response.json().catch(() => ({}));
}

function render(session) {
  state.session = session;
  el.voiceModeLabel.textContent = session.voice_mode;
  el.audioTargetLabel.textContent = session.audio_target;
  el.estopLabel.textContent = session.emergency_stop ? "active" : "clear";
  el.panSlider.value = session.camera.pan;
  el.tiltSlider.value = session.camera.tilt;
  el.voiceModeSelect.value = session.voice_mode;
  el.audioTargetSelect.value = session.audio_target;
  el.visionSummary.textContent = session.vision.summary;
}

async function refreshState() {
  const [session, health] = await Promise.all([api("/api/state"), api("/api/health")]);
  render(session);
  el.hardwareLabel.textContent = `${health.hardware_backend} / ${health.camera_backend}`;
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

async function openVoiceSocket() {
  if (state.ws && state.ws.readyState <= WebSocket.OPEN) {
    return state.ws;
  }
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.ws = new WebSocket(`${protocol}://${window.location.host}/ws/voice`);
  state.ws.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === "state") {
      render(payload.state);
      return;
    }
    if (payload.type === "relay_chunk") {
      await playRelayChunk(payload.audio, payload.sample_rate);
      return;
    }
    if (payload.type === "assistant_audio") {
      await playAssistantAudio(payload.audio);
      return;
    }
    if (payload.type === "assistant_reply") {
      logMessage("robot", payload.text);
      return;
    }
    if (payload.type === "transcript") {
      logMessage("you", payload.text);
      return;
    }
    if (payload.type === "error") {
      el.speechStatus.textContent = payload.message;
    }
  });
  return new Promise((resolve) => {
    state.ws.addEventListener("open", () => resolve(state.ws), { once: true });
  });
}

async function ensureCapturePipeline() {
  await ensureAudioContext();
  if (state.mediaStream && state.workletNode) {
    return;
  }
  state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  state.sourceNode = state.audioContext.createMediaStreamSource(state.mediaStream);
  state.workletNode = new AudioWorkletNode(state.audioContext, "pcm-capture");
  state.workletNode.port.onmessage = (event) => {
    if (!state.captureActive || !state.ws || state.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    const audio = base64FromArrayBuffer(event.data);
    state.ws.send(JSON.stringify({ type: "pcm_chunk", audio }));
  };
  state.sourceNode.connect(state.workletNode);
  state.workletNode.connect(state.audioContext.destination);
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
  await openVoiceSocket();
  await ensureCapturePipeline();
  configureSpeechRecognition();
  state.transcript = "";
  state.captureActive = true;
  if (state.session?.voice_mode === "ai_reply" && state.recognition) {
    try {
      state.recognition.start();
    } catch (error) {
      // Recognition may already be active.
    }
  }
  el.speechStatus.textContent = "Listening...";
}

async function stopTalking() {
  state.captureActive = false;
  if (state.recognition) {
    try {
      state.recognition.stop();
    } catch (error) {
      // Ignore recognition stop races.
    }
  }
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  if (state.transcript) {
    state.ws.send(JSON.stringify({ type: "transcript", text: state.transcript }));
  }
  state.ws.send(JSON.stringify({ type: "commit" }));
  el.speechStatus.textContent = "Waiting for reply...";
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

function bindDriveButton(button) {
  const speed = Number(button.dataset.speed);
  const steering = Number(button.dataset.steering);
  const sendCommand = async () => {
    try {
      await api("/api/drive", {
        method: "POST",
        body: JSON.stringify({ speed, steering, source: "browser" }),
      });
    } catch (error) {
      el.speechStatus.textContent = error.message;
    }
  };
  const start = async (event) => {
    event.preventDefault();
    if (state.session?.emergency_stop) {
      el.speechStatus.textContent = "Reset emergency stop before driving.";
      return;
    }
    await sendCommand();
    state.driveInterval = window.setInterval(sendCommand, 250);
  };
  const stop = async () => {
    window.clearInterval(state.driveInterval);
    state.driveInterval = null;
    await api("/api/drive/stop", { method: "POST" }).catch(() => null);
  };
  ["mousedown", "touchstart"].forEach((eventName) => button.addEventListener(eventName, start));
  ["mouseup", "mouseleave", "touchend", "touchcancel"].forEach((eventName) =>
    button.addEventListener(eventName, stop)
  );
}

function bindKeyboard() {
  const keymap = {
    w: { speed: 35, steering: 0 },
    a: { speed: 25, steering: -25 },
    d: { speed: 25, steering: 25 },
    s: { speed: -25, steering: 0 },
  };
  let activeKey = null;
  window.addEventListener("keydown", async (event) => {
    if (activeKey || !keymap[event.key]) {
      return;
    }
    activeKey = event.key;
    const command = keymap[event.key];
    await api("/api/drive", {
      method: "POST",
      body: JSON.stringify({ ...command, source: "keyboard" }),
    }).catch(() => null);
  });
  window.addEventListener("keyup", async (event) => {
    if (event.key !== activeKey) {
      return;
    }
    activeKey = null;
    await api("/api/drive/stop", { method: "POST" }).catch(() => null);
  });
}

async function updateCamera() {
  await api("/api/camera", {
    method: "POST",
    body: JSON.stringify({
      pan: Number(el.panSlider.value),
      tilt: Number(el.tiltSlider.value),
    }),
  });
  await refreshState();
}

async function init() {
  document.querySelectorAll(".drive").forEach(bindDriveButton);
  bindKeyboard();
  await refreshState();
  await openVoiceSocket();

  el.voiceModeSelect.addEventListener("change", async () => {
    await api("/api/voice/mode", {
      method: "POST",
      body: JSON.stringify({ mode: el.voiceModeSelect.value }),
    });
    await refreshState();
  });

  el.audioTargetSelect.addEventListener("change", async () => {
    await api("/api/audio/target", {
      method: "POST",
      body: JSON.stringify({ target: el.audioTargetSelect.value }),
    });
    await refreshState();
  });

  el.centerCamera.addEventListener("click", async () => {
    el.panSlider.value = 0;
    el.tiltSlider.value = 0;
    await updateCamera();
  });

  el.panSlider.addEventListener("change", updateCamera);
  el.tiltSlider.addEventListener("change", updateCamera);

  el.stopButton.addEventListener("click", async () => {
    await api("/api/emergency-stop", { method: "POST" });
    await refreshState();
  });

  el.clearEstop.addEventListener("click", async () => {
    await api("/api/emergency-reset", { method: "POST" });
    await refreshState();
  });

  el.refresh.addEventListener("click", refreshState);

  el.pushToTalk.addEventListener("mousedown", startTalking);
  el.pushToTalk.addEventListener("mouseup", stopTalking);
  el.pushToTalk.addEventListener("mouseleave", () => {
    if (state.captureActive) {
      stopTalking();
    }
  });
  el.pushToTalk.addEventListener("touchstart", (event) => {
    event.preventDefault();
    startTalking();
  });
  el.pushToTalk.addEventListener("touchend", (event) => {
    event.preventDefault();
    stopTalking();
  });

  el.visionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = el.visionQuestion.value.trim();
    if (!question) {
      return;
    }
    el.visionAnswer.textContent = "Thinking...";
    try {
      const response = await api("/api/vision/question", {
        method: "POST",
        body: JSON.stringify({ question }),
      });
      el.visionAnswer.textContent = response.answer;
    } catch (error) {
      el.visionAnswer.textContent = error.message;
    }
  });

  window.setInterval(refreshState, 2500);
}

init().catch((error) => {
  el.speechStatus.textContent = error.message;
});
