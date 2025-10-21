var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// src/shared/audio-processor.worklet.ts
var VoiceFormFillerAudioProcessor = class extends AudioWorkletProcessor {
  constructor() {
    super();
    __publicField(this, "smoothedRMS", 0);
    __publicField(this, "RMS_SMOOTHING_BETA", 0.6);
  }
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }
    const inputData = input[0];
    let sumSquares = 0;
    for (let i = 0; i < inputData.length; i++) {
      sumSquares += inputData[i] * inputData[i];
    }
    const instantRMS = Math.sqrt(sumSquares / inputData.length);
    const instantEnergy = instantRMS * 100;
    if (this.smoothedRMS === 0) {
      this.smoothedRMS = instantEnergy;
    } else {
      this.smoothedRMS = this.RMS_SMOOTHING_BETA * instantEnergy + (1 - this.RMS_SMOOTHING_BETA) * this.smoothedRMS;
    }
    const pcmData = new Int16Array(inputData.length);
    for (let i = 0; i < inputData.length; i++) {
      const s = Math.max(-1, Math.min(1, inputData[i]));
      pcmData[i] = s < 0 ? s * 32768 : s * 32767;
    }
    this.port.postMessage({
      type: "audio",
      pcmData: pcmData.buffer,
      energy: this.smoothedRMS
    }, [pcmData.buffer]);
    return true;
  }
};
registerProcessor("voice-form-filler-audio-processor", VoiceFormFillerAudioProcessor);
