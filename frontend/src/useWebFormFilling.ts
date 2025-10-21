/**
 * useWebFormFilling - React hook for web form voice filling
 * 
 * Provides easy integration with WebFormConnection and state management.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { WebFormConnection, ConnectionStatus } from "./webFormConnection";
import { FormSchema, WebFormState } from "./webFormState";

const GEMINI_PCM_SAMPLE_RATE = 24000;

const decodeGeminiFrame = (buffer: ArrayBuffer): ArrayBuffer => {
  const view = new Uint8Array(buffer);
  const isLikelyBase64 = view.every((byte) => byte >= 32 && byte <= 126);
  if (!isLikelyBase64) {
    return buffer;
  }
  try {
    const ascii = new TextDecoder("ascii").decode(view).trim();
    const binary = atob(ascii);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      out[i] = binary.charCodeAt(i);
    }
    return out.buffer;
  } catch (err) {
    return buffer;
  }
};

const decodePCM16ToAudioBuffer = (audioCtx: AudioContext, arrayBuffer: ArrayBuffer, sampleRate = GEMINI_PCM_SAMPLE_RATE) => {
  if (!(arrayBuffer instanceof ArrayBuffer) || arrayBuffer.byteLength === 0) {
    throw new Error("Empty audio buffer");
  }
  const view = new DataView(arrayBuffer);
  const sampleCount = Math.floor(arrayBuffer.byteLength / 2);
  if (sampleCount === 0) {
    throw new Error("No PCM samples to decode");
  }
  const audioBuffer = audioCtx.createBuffer(1, sampleCount, sampleRate);
  const channelData = audioBuffer.getChannelData(0);
  for (let i = 0; i < sampleCount; i++) {
    const sample = view.getInt16(i * 2, true);
    channelData[i] = sample / 0x8000;
  }
  return audioBuffer;
};

const ensureAudioContext = (existing: AudioContext | null): AudioContext => {
  if (existing) {
    return existing;
  }
  const ContextCtor = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext;
  return new ContextCtor({ sampleRate: GEMINI_PCM_SAMPLE_RATE });
};

export interface UseWebFormFillingOptions {
  schema: FormSchema;
  wsUrl?: string;
  autoConnect?: boolean;
  onFieldUpdate?: (fieldId: string, value: any) => void;
  onError?: (error: Error) => void;
}

export interface UseWebFormFillingReturn {
  // Connection state
  status: ConnectionStatus;
  sessionId: string | null;
  isConnected: boolean;
  
  // Form state
  formState: WebFormState | null;
  completionPercentage: number;
  
  // Actions
  connect: () => Promise<void>;
  disconnect: () => void;
  updateField: (
    fieldId: string,
    value: string | boolean | null,
    options?: { confirmed?: boolean }
  ) => void;
  flushField: (fieldId: string) => void;
  sendAudio: (audioData: ArrayBuffer) => void;
  reset: () => void;
  
  // Audio handling
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  isRecording: boolean;
}

export function useWebFormFilling(
  options: UseWebFormFillingOptions
): UseWebFormFillingReturn {
  const { schema, wsUrl = "ws://localhost:8000/ws/fill", autoConnect = false } = options;
  
  // State
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [formState, setFormState] = useState<WebFormState | null>(null);
  const [completionPercentage, setCompletionPercentage] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  
  // Refs
  const connectionRef = useRef<WebFormConnection | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const playbackTimeRef = useRef<number>(0);
  
  // Initialize connection
  useEffect(() => {
    const connection = new WebFormConnection(schema, {
      onStatusChange: (newStatus) => {
        setStatus(newStatus);
        if (newStatus === "connected") {
          playbackTimeRef.current = audioContextRef.current?.currentTime ?? 0;
        } else if (newStatus === "disconnected") {
          playbackTimeRef.current = 0;
        }
      },
      onSessionReady: (id) => {
        setSessionId(id);
        setFormState(connection.getState());
        setCompletionPercentage(connection.getCompletionPercentage());
      },
      onFieldUpdate: (updates) => {
        // Update form state
        setFormState(connection.getState());
        setCompletionPercentage(connection.getCompletionPercentage());
        
        // Notify individual field updates
        if (options.onFieldUpdate) {
          updates.forEach((update) => {
            options.onFieldUpdate!(update.fieldId, update.value);
          });
        }
      },
      onError: (error) => {
        if (options.onError) {
          options.onError(error);
        }
      },
      onAudioData: (audioData) => {
        // Play audio from AI
        playAudio(audioData);
      },
    });
    
    connectionRef.current = connection;
    setFormState(connection.getState());
    setCompletionPercentage(connection.getCompletionPercentage());
    
    // Auto-connect if requested
    if (autoConnect) {
      connection.connect(wsUrl);
    }
    
    // Cleanup on unmount
    return () => {
      connection.disconnect();
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
      playbackTimeRef.current = 0;
    };
  }, [schema, wsUrl, autoConnect]);
  
  // Connect action
  const connect = useCallback(async () => {
    if (connectionRef.current) {
      await connectionRef.current.connect(wsUrl);
    }
  }, [wsUrl]);
  
  // Disconnect action
  const disconnect = useCallback(() => {
    if (connectionRef.current) {
      connectionRef.current.disconnect();
    }
  }, []);
  
  // Update field action
  const updateField = useCallback((
    fieldId: string,
    value: string | boolean | null,
    options?: { confirmed?: boolean }
  ) => {
    if (connectionRef.current) {
      connectionRef.current.updateField(fieldId, value, options);
      setFormState(connectionRef.current.getState());
      setCompletionPercentage(connectionRef.current.getCompletionPercentage());
    }
  }, []);

  const flushField = useCallback((fieldId: string) => {
    connectionRef.current?.flushField(fieldId);
  }, []);
  
  // Send audio action
  const sendAudio = useCallback((audioData: ArrayBuffer) => {
    if (connectionRef.current) {
      connectionRef.current.sendAudio(audioData);
    }
  }, []);
  
  // Reset action
  const reset = useCallback(() => {
    if (connectionRef.current) {
      connectionRef.current.reset();
      setSessionId(null);
      setFormState(null);
      setCompletionPercentage(0);
    }
  }, []);
  
  // Start recording audio
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: "audio/webm;codecs=opus",
      });
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          event.data.arrayBuffer().then((buffer) => {
            sendAudio(buffer);
          });
        }
      };
      
      mediaRecorder.start(100); // Send audio chunks every 100ms
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
      
    } catch (error) {
      if (options.onError) {
        options.onError(error as Error);
      }
    }
  }, [sendAudio, options]);
  
  // Stop recording audio
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop());
      mediaRecorderRef.current = null;
      setIsRecording(false);
    }
  }, []);
  
  // Play audio from AI
  const playAudio = useCallback(async (audioData: ArrayBuffer) => {
    try {
      audioContextRef.current = ensureAudioContext(audioContextRef.current);
      const audioContext = audioContextRef.current;
      if (!audioContext) {
        throw new Error('AudioContext unavailable');
      }

      if (audioContext.state === 'suspended') {
        try {
          await audioContext.resume();
        } catch (resumeError) {
          // Silently handle AudioContext resume failure
        }
      }

      let audioBuffer: AudioBuffer | null = null;
      let decodeError: unknown = null;

      try {
        const bufferCopy = audioData.slice(0);
        audioBuffer = await audioContext.decodeAudioData(bufferCopy);
      } catch (err) {
        decodeError = err;
      }

      if (!audioBuffer) {
        try {
          const decoded = decodeGeminiFrame(audioData);
          audioBuffer = decodePCM16ToAudioBuffer(audioContext, decoded);
        } catch (pcmError) {
          const decodeMsg = decodeError && (decodeError as Error).message ? (decodeError as Error).message : String(decodeError || '');
          const pcmMsg = pcmError && (pcmError as Error).message ? (pcmError as Error).message : String(pcmError || '');
          throw new Error('decodeAudioData=' + decodeMsg + '; pcmDecode=' + pcmMsg);
        }
      }

      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);

      const now = audioContext.currentTime + 0.01;
      const startAt = Math.max(playbackTimeRef.current, now);
      source.start(startAt);
      playbackTimeRef.current = startAt + audioBuffer.duration;
      source.onended = () => {
        if (playbackTimeRef.current < audioContext.currentTime) {
          playbackTimeRef.current = audioContext.currentTime;
        }
        try {
          source.disconnect();
        } catch (_) {
          // noop
        }
      };
    } catch (error) {
      // Silently handle audio playback errors
    }
  }, []);
  
  return {
    // Connection state
    status,
    sessionId,
    isConnected: status === "connected",
    
    // Form state
    formState,
    completionPercentage,
    
    // Actions
    connect,
    disconnect,
    updateField,
    flushField,
    sendAudio,
    reset,
    
    // Audio handling
    startRecording,
    stopRecording,
    isRecording,
  };
}
