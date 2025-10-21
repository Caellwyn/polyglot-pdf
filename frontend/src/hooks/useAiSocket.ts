import { useRef, useState, useCallback } from 'react';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const decodeFrame = (buffer: ArrayBuffer): ArrayBuffer => {
  const view = new Uint8Array(buffer);
  const isLikelyBase64 = view.every((byte) => byte >= 32 && byte <= 126);
  if (!isLikelyBase64) {
    return buffer;
  }
  try {
    const ascii = new TextDecoder('ascii').decode(view).trim();
    const binary = atob(ascii);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      out[i] = binary.charCodeAt(i);
    }
    return out.buffer;
  } catch (err) {
    console.warn('Failed to base64 decode Gemini audio frame', err);
    return buffer;
  }
};

type FormUpdateData = { [key: string]: any };

interface AiSocketCallbacks {
  onConnect?: () => void;
  onDisconnect?: () => void;
  onFormUpdate?: (data: FormUpdateData) => void;
  onTranscript?: (data: string) => void;
  onPageChange?: (pageIndex: number) => void;
  onError?: (error: string) => void;
}

export const useAiSocket = () => {
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const playbackTimeRef = useRef<number>(0);
  const metricsRef = useRef<{ outgoingFrames: number; lastOutgoingLen: number; lastOutgoingTs: number }>({ outgoingFrames: 0, lastOutgoingLen: 0, lastOutgoingTs: 0 });

  const ensureAudioContext = () => {
    if (!audioCtxRef.current) {
      const Ctx = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext;
      audioCtxRef.current = new Ctx();
      (window as any).__aiAudioCtx = audioCtxRef.current;
    }
    return audioCtxRef.current;
  };

  const playPcm16Le = (arrayBuffer: ArrayBuffer, sampleRate = 24000) => {
    try {
      const ctx = ensureAudioContext();
      const decoded = decodeFrame(arrayBuffer);
      const frameBytes = decoded.byteLength ?? (decoded as any).size ?? 0;
      console.log('Playing AI audio frame', frameBytes, 'bytes');
      (window as any).__aiLastFrame = decoded.slice(0);
      const pcm = new Int16Array(decoded);
      const float32 = new Float32Array(pcm.length);
      for (let i = 0; i < pcm.length; i++) {
        float32[i] = pcm[i] / 32768;
      }

      const buffer = ctx.createBuffer(1, float32.length, sampleRate);
      buffer.getChannelData(0).set(float32);
      if (!(window as any).__aiFirstSamplesLogged) {
        console.log('First PCM samples', Array.from(float32.slice(0, 16)));
        (window as any).__aiFirstSamplesLogged = true;
      }

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      // Schedule playback so chunks play back-to-back without gaps or pops
      const now = ctx.currentTime + 0.01;
      const startAt = Math.max(playbackTimeRef.current, now);
      try {
        if (ctx.state === 'suspended') ctx.resume();
      } catch {}
      src.start(startAt);
      playbackTimeRef.current = startAt + buffer.duration;
      src.onended = () => {
        if (playbackTimeRef.current < ctx.currentTime) {
          playbackTimeRef.current = ctx.currentTime;
        }
      };
    } catch (e) {
      console.error('Failed to play audio from AI socket', e);
    }
  };

  const getWebSocketUrl = (sessionId: string, sendTranscript: boolean): string => {
    try {
      const url = new URL(API_URL);
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      url.pathname = `/ws/fill/${sessionId}`;
      url.searchParams.set('send_transcript', String(sendTranscript));
      return url.toString();
    } catch {
      // Fallback for environments where URL parsing might fail or API_URL is malformed
      return `ws://localhost:8000/ws/fill/${sessionId}?send_transcript=${sendTranscript}`;
    }
  };

  const connect = useCallback((sessionId: string, sendTranscript: boolean, callbacks: AiSocketCallbacks) => {
    if (socketRef.current) {
      console.warn("AI socket already connected or connecting.");
      return;
    }

    const wsUrl = getWebSocketUrl(sessionId, sendTranscript);
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      playbackTimeRef.current = audioCtxRef.current?.currentTime ?? 0;
      setIsConnected(true);
      // Expose ws state for debugging
      (window as any).__aiWsState = 'open';
      (window as any).__aiMetrics = { ...metricsRef.current, wsReadyState: ws.readyState };
      callbacks.onConnect?.();
    };

    ws.onmessage = (event) => {
      // String messages are JSON control messages; binary frames carry raw audio
      if (typeof event.data === 'string') {
        try {
          const message = JSON.parse(event.data);
          console.log('AI WebSocket message received:', message.type, message);
          switch (message.type) {
            case 'form_updated':
              callbacks.onFormUpdate?.(message.data);
              break;
            case 'transcript':
              callbacks.onTranscript?.(message.data);
              break;
            case 'page_change':
              console.log('Page change message received! page_index:', message.page_index);
              callbacks.onPageChange?.(message.page_index);
              break;
            case 'welcome':
              // Welcome message received, connection is fully established.
              break;
            default:
              console.warn('Unknown message type from AI socket:', message.type);
          }
        } catch (e) {
          console.error('Failed to parse AI socket message:', e);
          callbacks.onError?.('Received malformed message from server.');
        }
      } else {
        // Binary data path: Blob or ArrayBuffer with raw PCM16LE audio from Gemini
        const data = event.data;
        if (data instanceof ArrayBuffer) {
          playPcm16Le(data);
        } else if (data instanceof Blob) {
          // asynchronous conversion
          data.arrayBuffer().then((buf) => playPcm16Le(buf)).catch((e) => console.error(e));
        } else {
          // Fallback: try to coerce
          try {
            const maybeBuf = event.data as any;
            if (maybeBuf?.buffer instanceof ArrayBuffer) playPcm16Le(maybeBuf.buffer);
          } catch (e) {
            console.warn('Received unknown binary message from AI socket', e);
          }
        }
      }
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      socketRef.current = null;
      playbackTimeRef.current = 0;
      (window as any).__aiWsState = 'closed';
      (window as any).__aiMetrics = { ...metricsRef.current, wsReadyState: WebSocket.CLOSED };
      // Avoid firing disconnect on clean closures if not desired
      if (!event.wasClean) {
        console.log('AI WebSocket closed unexpectedly.');
      }
      callbacks.onDisconnect?.();
    };

    ws.onerror = (event) => {
      console.error('AI WebSocket error:', event);
      (window as any).__aiWsState = 'error';
      (window as any).__aiMetrics = { ...metricsRef.current, wsReadyState: socketRef.current?.readyState ?? null };
      callbacks.onError?.('WebSocket connection failed.');
      // Ensure cleanup happens on error too
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
      setIsConnected(false);
    };

  }, []);

  const disconnect = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close(1000, "User disconnected"); // Clean closure
      socketRef.current = null;
    }
    playbackTimeRef.current = 0;
    (window as any).__aiWsState = 'closed';
    (window as any).__aiMetrics = { ...metricsRef.current, wsReadyState: WebSocket.CLOSED };
  }, []);

  const sendAudio = useCallback((data: Uint8Array) => {
    try {
      const ready = socketRef.current?.readyState;
      // Update attempt timestamp even if socket isn't open
      metricsRef.current.lastOutgoingTs = Date.now();
      metricsRef.current.lastOutgoingLen = data?.byteLength ?? (data as any).length ?? 0;
      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(data);
        metricsRef.current.outgoingFrames++;
      } else {
        // Not open: record attempted send
        console.debug('sendAudio called but socket not open', ready);
      }
      (window as any).__aiMetrics = { ...metricsRef.current, wsReadyState: socketRef.current?.readyState ?? null };
      console.log('sendAudio -> len', metricsRef.current.lastOutgoingLen, 'outgoingFrames', metricsRef.current.outgoingFrames, 'wsState', socketRef.current?.readyState);
    } catch (e) {
      console.error('Error in sendAudio instrumentation', e);
    }
  }, []);

  return { isConnected, connect, disconnect, sendAudio };
};
