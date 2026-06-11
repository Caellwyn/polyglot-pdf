var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

// src/shared/audio-processor.worklet.ts
var VoiceFormFillerAudioProcessor = class extends AudioWorkletProcessor {
  constructor() {
    super();
    __publicField(this, "smoothedRMS", 0);
    __publicField(this, "RMS_SMOOTHING_BETA", 0.6);
    // HALLUCINATION_REDUCTION (Oct 30, 2025): Audio preprocessing filters
    // FIX (Nov 7, 2025): Lowered threshold from -40dB to -50dB for gentler gating
    // Noise gate: -50dB threshold (gentler - preserves quiet speech)
    __publicField(this, "NOISE_GATE_THRESHOLD", 316e-5);
    // -50dB in linear scale (10^(-50/20))
    // High-pass filter: 80Hz cutoff, Q=0.7 (removes low-frequency rumble)
    // Biquad filter state variables (stores previous samples for IIR filtering)
    __publicField(this, "hpf_x1", 0);
    // input sample at n-1
    __publicField(this, "hpf_x2", 0);
    // input sample at n-2
    __publicField(this, "hpf_y1", 0);
    // output sample at n-1
    __publicField(this, "hpf_y2", 0);
    // output sample at n-2
    // High-pass filter coefficients (calculated for 80Hz @ 16kHz sample rate, Q=0.7)
    __publicField(this, "hpf_b0");
    __publicField(this, "hpf_b1");
    __publicField(this, "hpf_b2");
    __publicField(this, "hpf_a1");
    __publicField(this, "hpf_a2");
    // FIX (Nov 7, 2025): Track PTT mode to bypass noise gate when user explicitly controls audio
    __publicField(this, "pttMode", false);
    this.port.onmessage = (event) => {
      if (event.data.type === "setPTTMode") {
        this.pttMode = event.data.enabled;
        console.log("[AudioWorklet] PTT mode:", this.pttMode ? "enabled (noise gate bypassed)" : "disabled (noise gate active)");
      }
    };
    const f0 = 80;
    const Fs = 16e3;
    const Q = 0.7;
    const w0 = 2 * Math.PI * f0 / Fs;
    const cosW0 = Math.cos(w0);
    const sinW0 = Math.sin(w0);
    const alpha = sinW0 / (2 * Q);
    const b0 = (1 + cosW0) / 2;
    const b1 = -(1 + cosW0);
    const b2 = (1 + cosW0) / 2;
    const a0 = 1 + alpha;
    const a1 = -2 * cosW0;
    const a2 = 1 - alpha;
    this.hpf_b0 = b0 / a0;
    this.hpf_b1 = b1 / a0;
    this.hpf_b2 = b2 / a0;
    this.hpf_a1 = a1 / a0;
    this.hpf_a2 = a2 / a0;
  }
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (!input || !input[0]) {
      return true;
    }
    const inputData = input[0];
    const filteredData = new Float32Array(inputData.length);
    for (let i = 0; i < inputData.length; i++) {
      const x0 = inputData[i];
      const y0 = this.hpf_b0 * x0 + this.hpf_b1 * this.hpf_x1 + this.hpf_b2 * this.hpf_x2 - this.hpf_a1 * this.hpf_y1 - this.hpf_a2 * this.hpf_y2;
      this.hpf_x2 = this.hpf_x1;
      this.hpf_x1 = x0;
      this.hpf_y2 = this.hpf_y1;
      this.hpf_y1 = y0;
      filteredData[i] = y0;
    }
    if (!this.pttMode) {
      let sumSquaresFiltered = 0;
      for (let i = 0; i < filteredData.length; i++) {
        sumSquaresFiltered += filteredData[i] * filteredData[i];
      }
      const rmsFiltered = Math.sqrt(sumSquaresFiltered / filteredData.length);
      if (rmsFiltered < this.NOISE_GATE_THRESHOLD) {
        filteredData.fill(0);
      }
    }
    const processedData = filteredData;
    let sumSquares = 0;
    for (let i = 0; i < processedData.length; i++) {
      sumSquares += processedData[i] * processedData[i];
    }
    const instantRMS = Math.sqrt(sumSquares / processedData.length);
    const instantEnergy = instantRMS * 100;
    if (this.smoothedRMS === 0) {
      this.smoothedRMS = instantEnergy;
    } else {
      this.smoothedRMS = this.RMS_SMOOTHING_BETA * instantEnergy + (1 - this.RMS_SMOOTHING_BETA) * this.smoothedRMS;
    }
    const pcmData = new Int16Array(processedData.length);
    for (let i = 0; i < processedData.length; i++) {
      const s = Math.max(-1, Math.min(1, processedData[i]));
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
