class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }
    const channelData = input[0];
    const downsampled = this.downsample(channelData, sampleRate, this.targetSampleRate);
    if (downsampled.length === 0) {
      return true;
    }
    const pcm = new Int16Array(downsampled.length);
    for (let index = 0; index < downsampled.length; index += 1) {
      const sample = Math.max(-1, Math.min(1, downsampled[index]));
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    return true;
  }

  downsample(buffer, inputRate, outputRate) {
    if (outputRate >= inputRate) {
      return buffer;
    }
    const ratio = inputRate / outputRate;
    const resultLength = Math.round(buffer.length / ratio);
    const result = new Float32Array(resultLength);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < result.length) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accumulator = 0;
      let count = 0;
      for (let index = offsetBuffer; index < nextOffsetBuffer && index < buffer.length; index += 1) {
        accumulator += buffer[index];
        count += 1;
      }
      result[offsetResult] = count ? accumulator / count : 0;
      offsetResult += 1;
      offsetBuffer = nextOffsetBuffer;
    }
    return result;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
