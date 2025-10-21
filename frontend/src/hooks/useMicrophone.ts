import { useRef, useState } from 'react';

// Helper to convert float audio data to 16-bit PCM
const floatTo16BitPCM = (input: Float32Array): Uint8Array => {
  const out = new Uint8Array(input.length * 2);
  let offset = 0;
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    const val = s < 0 ? s * 0x8000 : s * 0x7fff;
    const v = val | 0;
    out[offset++] = v & 0xff;
    out[offset++] = (v >> 8) & 0xff;
  }
  return out;
};

// Simple linear interpolation for resampling
const resampleLinear = (input: Float32Array, srcRate: number, targetRate: number): Float32Array => {
  if (srcRate === targetRate) return input;
  const ratio = targetRate / srcRate;
  const newLen = Math.floor(input.length * ratio);
  const out = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const srcPos = i / ratio;
    const i0 = Math.floor(srcPos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = srcPos - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
};

type AudioNodes = {
  ctx: AudioContext;
  src: MediaStreamAudioSourceNode;
  proc: ScriptProcessorNode;
  stream: MediaStream;
};

export const useMicrophone = () => {
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const audioNodesRef = useRef<AudioNodes | null>(null);
  const micMetricsRef = useRef<{ framesProduced: number; lastFrameLen: number; lastFrameTs: number }>({ framesProduced: 0, lastFrameLen: 0, lastFrameTs: 0 });

  const start = async (onAudioData: (data: Uint8Array) => void) => {
    if (isListening) return;
    setError(null);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 }, video: false });
      
      let ctx: AudioContext;
      try {
        ctx = new AudioContext({ sampleRate: 16000 });
      } catch {
        // Fallback to system default sample rate, we will resample anyway
        ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      }

      const src = ctx.createMediaStreamSource(stream);
      // Buffer size of 4096 is a common choice
      const proc = ctx.createScriptProcessor(4096, 1, 1);
      const targetRate = 16000;
      // Send audio in 20ms chunks, as recommended for streaming speech recognition.
      // 16000 samples/sec * 0.020 sec = 320 samples per chunk.
      const frameSamples = 320; 

      let buffer: number[] = [];

      proc.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        const resampled = resampleLinear(input, ctx.sampleRate, targetRate);
        
        // Add new resampled data to our buffer
        for (let i = 0; i < resampled.length; i++) buffer.push(resampled[i]);

        // While we have enough data for a full frame, process and send it
        while (buffer.length >= frameSamples) {
          const slice = buffer.splice(0, frameSamples);
          const pcm = floatTo16BitPCM(Float32Array.from(slice));
          
          // Note: We DO send silent chunks - Gemini's VAD needs silence to detect end-of-turn
          
          // Update mic metrics and expose for debugging
          try {
            micMetricsRef.current.framesProduced += 1;
            micMetricsRef.current.lastFrameLen = pcm.byteLength;
            micMetricsRef.current.lastFrameTs = Date.now();
            (window as any).__micMetrics = { ...micMetricsRef.current };
            console.log('mic frame produced', micMetricsRef.current.framesProduced, 'len', micMetricsRef.current.lastFrameLen);
          } catch (e) {
            // ignore instrumentation errors
          }
          onAudioData(pcm);
        }
      };

      src.connect(proc);
      proc.connect(ctx.destination);
  audioNodesRef.current = { ctx, src, proc, stream };
  // Initialize exposed metrics object
  try { (window as any).__micMetrics = { ...micMetricsRef.current }; } catch (e) {}
  setIsListening(true);
    } catch (err: any) {
      setError(err?.message ?? String(err));
      setIsListening(false);
    }
  };

  const stop = () => {
    if (!isListening) return;
    
    const nodes = audioNodesRef.current;
    if (nodes) {
      // Disconnect and stop everything gracefully
      try { nodes.proc?.disconnect(); } catch {}
      try { nodes.src?.disconnect(); } catch {}
      try { nodes.stream?.getTracks().forEach(track => track.stop()); } catch {}
      // Close the context last
      try { nodes.ctx?.close(); } catch {}
    }
    
    audioNodesRef.current = null;
    setIsListening(false);
    try { (window as any).__micMetrics = { ...micMetricsRef.current }; } catch (e) {}
  };

  return { isListening, error, start, stop };
};
