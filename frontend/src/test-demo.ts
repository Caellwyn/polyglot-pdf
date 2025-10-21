/**
 * Test Demo Application
 * 
 * Testing ground for WebFormConnection and frontend logic before
 * deploying as a bookmarklet. This file uses all our production
 * frontend code (WebFormConnection, navigation, state management).
 */

// @ts-nocheck - TODO: Remove or update this file - references old warmup API
import { WebFormConnection, ConnectionStatus, ConnectionCallbacks } from './webFormConnection';
import { WebFormStateManager, FormSchema, FieldValue } from './webFormState';
import type { ConnectionCallbacks } from './webFormConnection';

// Constants
const WS_URL = 'wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill';  // Production Cloud Run backend
const GEMINI_PCM_SAMPLE_RATE = 24000;

// Form Schema for testing
const FORM_SCHEMA: FormSchema = {
  source: 'web',
  form_metadata: {
    title: 'Contact Form - Manual Test',
    url: window.location.href,
  },
  fields: [
    { id: 'name', name: 'Full Name', type: 'text', required: true },
    { id: 'email', name: 'Email Address', type: 'text', required: true },
    { id: 'phone', name: 'Phone Number', type: 'text', required: true },
    { id: 'address', name: 'Address', type: 'text', required: false },
    { id: 'comments', name: 'Comments', type: 'text', required: false },
  ],
};

// UI Elements
interface UIElements {
  statusBar: HTMLElement;
  statusText: HTMLElement;
  sessionId: HTMLElement;
  completion: HTMLElement;
  recordingStatus: HTMLElement;
  progressFill: HTMLElement;
  connectBtn: HTMLButtonElement;
  disconnectBtn: HTMLButtonElement;
  recordBtn: HTMLButtonElement;
  resetBtn: HTMLButtonElement;
  submitBtn: HTMLButtonElement;
  logs: HTMLElement;
  debugState: HTMLElement;
}

// Application State
class TestDemoApp {
  private connection: WebFormConnection;
  private els!: UIElements;
  private audioContext: AudioContext | null = null;
  private playbackContext: AudioContext | null = null;
  private playbackTime = 0;
  private audioStream: MediaStream | null = null;
  private audioProcessor: ScriptProcessorNode | null = null;
  private isRecording = false;
  private sessionId: string | null = null;
  private audioChunkCount = 0;

  constructor() {
    // Initialize WebFormConnection with callbacks
    const callbacks: ConnectionCallbacks = {
      onStatusChange: (status) => this.handleStatusChange(status),
      onSessionReady: (sessionId) => this.handleSessionReady(sessionId),
      onFieldUpdate: (updates) => this.handleFieldUpdates(updates),
      onError: (error) => this.handleError(error),
      onAudioData: (audioData) => this.playAudio(audioData),
      onWarmupReady: () => this.handleWarmupReady(),
    };

    this.connection = new WebFormConnection(FORM_SCHEMA, callbacks);
  }

  /**
   * Initialize the application
   */
  init(): void {
    this.initUIElements();
    this.initEventListeners();
    this.restoreFormFields();
    this.updateCompletion();
    this.updateDebugState();
    
    // Start warming up connection immediately
    this.startWarmup();
    
    this.log('Ready to test!', 'success');
    this.log('Click "Connect" to start', 'info');
  }
  
  /**
   * Start warming up Gemini connection in background
   */
  private async startWarmup(): Promise<void> {
    this.log('🔥 Pre-warming Gemini connection...', 'info');
    
    try {
      await this.connection.warmup(WS_URL);
    } catch (error) {
      this.log(`Warmup failed: ${error} (will connect normally)`, 'warning');
    }
  }
  
  /**
   * Handle warmup ready event
   */
  private handleWarmupReady(): void {
    this.log('✅ Gemini connection ready! Click "Connect" for instant start.', 'success');
    
    // Optional: Enable connect button with visual indicator
    if (this.els?.connectBtn) {
      this.els.connectBtn.classList.add('warmup-ready');
      this.els.connectBtn.title = 'Connection pre-warmed and ready!';
    }
  }

  /**
   * Initialize UI element references
   */
  private initUIElements(): void {
    this.els = {
      statusBar: this.getElement('statusBar'),
      statusText: this.getElement('statusText'),
      sessionId: this.getElement('sessionId'),
      completion: this.getElement('completion'),
      recordingStatus: this.getElement('recordingStatus'),
      progressFill: this.getElement('progressFill'),
      connectBtn: this.getElement('connectBtn') as HTMLButtonElement,
      disconnectBtn: this.getElement('disconnectBtn') as HTMLButtonElement,
      recordBtn: this.getElement('recordBtn') as HTMLButtonElement,
      resetBtn: this.getElement('resetBtn') as HTMLButtonElement,
      submitBtn: this.getElement('submitBtn') as HTMLButtonElement,
      logs: this.getElement('logs'),
      debugState: this.getElement('debugState'),
    };
  }

  /**
   * Helper to get element with error checking
   */
  private getElement(id: string): HTMLElement {
    const el = document.getElementById(id);
    if (!el) throw new Error(`Element #${id} not found`);
    return el;
  }

  /**
   * Initialize event listeners
   */
  private initEventListeners(): void {
    this.els.connectBtn.addEventListener('click', () => this.connect());
    this.els.disconnectBtn.addEventListener('click', () => this.disconnect());
    this.els.recordBtn.addEventListener('click', () => this.toggleRecording());
    this.els.resetBtn.addEventListener('click', () => this.resetState());
    this.els.submitBtn.addEventListener('click', () => this.submitForm());

    // Form field listeners
    FORM_SCHEMA.fields.forEach(field => {
      const inputEl = document.getElementById(field.id) as HTMLInputElement;
      if (!inputEl) return;

      // Update state on input
      inputEl.addEventListener('input', (e) => {
        const value = (e.target as HTMLInputElement).value;
        this.connection.updateField(field.id, value, { confirmed: false, emit: false });
        this.updateCompletion();
        this.updateDebugState();
      });

      // Send manual update notification on blur/change
      const handleManualUpdate = (e: Event) => {
        const value = (e.target as HTMLInputElement).value;
        this.connection.sendManualFieldUpdate(field.id, field.name, value);
        this.log(`Sent manual update notification: ${field.name} = ${value}`, 'info');
      };

      inputEl.addEventListener('blur', handleManualUpdate);
      inputEl.addEventListener('change', handleManualUpdate);
    });
  }

  /**
   * Connect to WebSocket
   */
  private async connect(): Promise<void> {
    try {
      this.log('Connecting to WebSocket...', 'info');
      await this.connection.connect(WS_URL);
    } catch (error) {
      this.log(`Connection failed: ${error}`, 'error');
    }
  }

  /**
   * Disconnect from WebSocket
   */
  private disconnect(): void {
    this.connection.disconnect();
    if (this.isRecording) {
      this.stopRecording();
    }
    this.playbackTime = 0;
    this.sessionId = null;
    this.els.sessionId.textContent = '';
    this.log('Disconnected', 'info');
  }

  /**
   * Handle status changes from WebFormConnection
   */
  private handleStatusChange(status: ConnectionStatus): void {
    this.log(`Status changed: ${status}`, 'info');
    
    // Update UI status indicator
    this.els.statusBar.className = `status-bar status-${status}`;
    this.els.statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    
    const isConnected = status === 'connected';
    this.els.connectBtn.disabled = isConnected;
    this.els.disconnectBtn.disabled = !isConnected;
    this.els.recordBtn.disabled = !isConnected;
    
    // Enable/disable form fields
    FORM_SCHEMA.fields.forEach(field => {
      const inputEl = document.getElementById(field.id) as HTMLInputElement;
      if (inputEl) {
        inputEl.disabled = !isConnected;
      }
    });
  }

  /**
   * Handle session ready event
   */
  private handleSessionReady(sessionId: string): void {
    this.sessionId = sessionId;
    this.els.sessionId.textContent = sessionId;
    this.log(`Session ready: ${sessionId}`, 'success');
    this.restoreFormFields();
  }

  /**
   * Handle field updates from AI
   */
  private handleFieldUpdates(updates: { fieldId: string; value: any }[]): void {
    updates.forEach(update => {
      const inputEl = document.getElementById(update.fieldId) as HTMLInputElement;
      if (inputEl) {
        inputEl.value = String(update.value);
        inputEl.classList.add('field-confirmed');
        
        const badge = document.getElementById(`${update.fieldId}Badge`);
        if (badge) {
          badge.style.display = 'inline-block';
        }
      }
      
      this.log(`Field updated by AI: ${update.fieldId} = ${update.value}`, 'info');
    });
    
    this.updateCompletion();
    this.updateDebugState();
  }

  /**
   * Handle errors
   */
  private handleError(error: Error): void {
    this.log(`Error: ${error.message}`, 'error');
  }

  /**
   * Play audio from Gemini
   */
  private async playAudio(audioData: ArrayBuffer): Promise<void> {
    try {
      this.log(`🔊 Received audio: ${audioData.byteLength} bytes`, 'info');
      
      // Decode Gemini frame (may be base64-encoded)
      const decoded = this.decodeGeminiFrame(audioData);
      
      if (!this.playbackContext) {
        this.playbackContext = new AudioContext({ sampleRate: GEMINI_PCM_SAMPLE_RATE });
        this.playbackTime = 0;
        this.log(`🔊 Created AudioContext, state: ${this.playbackContext.state}`, 'info');
      }

      const ctx = this.playbackContext;
      const int16Array = new Int16Array(decoded);
      
      if (int16Array.length === 0) {
        this.log('🔊 No PCM samples to play (empty buffer)', 'warning');
        return;
      }
      
      const float32 = new Float32Array(int16Array.length);
      
      for (let i = 0; i < int16Array.length; i++) {
        float32[i] = int16Array[i] / 32768.0;
      }

      const audioBuffer = ctx.createBuffer(1, float32.length, GEMINI_PCM_SAMPLE_RATE);
      audioBuffer.getChannelData(0).set(float32);

      const now = ctx.currentTime + 0.01;
      const startAt = Math.max(this.playbackTime, now);
      
      if (ctx.state === 'suspended') {
        this.log('🔊 AudioContext suspended, resuming...', 'info');
        await ctx.resume();
        this.log(`🔊 AudioContext resumed, state: ${ctx.state}`, 'info');
      }
      
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.start(startAt);
      this.playbackTime = startAt + audioBuffer.duration;
      
      this.log(`🔊 Playing ${audioBuffer.duration.toFixed(2)}s at ${startAt.toFixed(2)}s`, 'success');
      
      source.onended = () => {
        if (this.playbackTime < ctx.currentTime) {
          this.playbackTime = ctx.currentTime;
        }
      };
    } catch (error) {
      this.log(`Audio playback failed: ${error}`, 'error');
      console.error('Audio playback error', error);
    }
  }

  /**
   * Decode Gemini audio frame (may be base64-encoded)
   */
  private decodeGeminiFrame(buffer: ArrayBuffer): ArrayBuffer {
    const view = new Uint8Array(buffer);
    
    // Check if this looks like base64 (all ASCII-printable bytes)
    const isLikelyBase64 = view.every(byte => byte >= 32 && byte <= 126);
    
    if (!isLikelyBase64) {
      return buffer;
    }
    
    try {
      // Decode as ASCII text
      const ascii = new TextDecoder('ascii').decode(view).trim();
      
      // Decode base64 to binary
      const binary = atob(ascii);
      const out = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        out[i] = binary.charCodeAt(i);
      }
      
      return out.buffer;
    } catch (err) {
      console.warn('Failed to base64 decode audio frame, using raw data', err);
      return buffer;
    }
  }

  /**
   * Toggle recording
   */
  private toggleRecording(): void {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.startRecording();
    }
  }

  /**
   * Start recording audio
   */
  private async startRecording(): Promise<void> {
    try {
      this.log('Requesting microphone access...', 'info');
      
      this.audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: GEMINI_PCM_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      // Create AudioContext (browser will resample to 24kHz)
      this.audioContext = new AudioContext({ sampleRate: GEMINI_PCM_SAMPLE_RATE });
      const source = this.audioContext.createMediaStreamSource(this.audioStream);

      // Use ScriptProcessorNode for PCM extraction (deprecated but works reliably)
      const bufferSize = 4096;
      this.audioProcessor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

      this.audioProcessor.onaudioprocess = (event: AudioProcessingEvent) => {
        if (this.connection && this.connection.getStatus() === 'connected') {
          const inputData = event.inputBuffer.getChannelData(0);

          // Convert Float32Array to Int16Array (PCM 16-bit)
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }

          // Send raw PCM16 chunk
          this.connection.sendAudio(pcmData.buffer);
          
          // Log periodically (every 100 chunks ~= every 10 seconds at 4096 buffer)
          if (!this.audioChunkCount) this.audioChunkCount = 0;
          this.audioChunkCount++;
          if (this.audioChunkCount % 100 === 1) {
            console.log(`🎤 Sent ${this.audioChunkCount} audio chunks (${pcmData.buffer.byteLength} bytes each)`);
          }
        }
      };

      source.connect(this.audioProcessor);
      this.audioProcessor.connect(this.audioContext.destination);

      this.isRecording = true;
      this.els.recordBtn.textContent = '⏹ Stop';
      this.els.recordBtn.classList.add('btn-danger');
      this.els.recordingStatus.textContent = 'Recording';
      this.log('Recording started', 'success');
    } catch (error) {
      this.log(`Microphone access failed: ${error}`, 'error');
    }
  }

  /**
   * Stop recording audio
   */
  private stopRecording(): void {
    if (this.audioProcessor) {
      this.audioProcessor.disconnect();
      this.audioProcessor = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
      this.audioStream = null;
    }

    this.isRecording = false;
    this.els.recordBtn.textContent = '🎤 Record';
    this.els.recordBtn.classList.remove('btn-danger');
    this.els.recordingStatus.textContent = 'Not recording';
    this.log('Recording stopped', 'warning');
  }

  /**
   * Restore form fields from state
   */
  private restoreFormFields(): void {
    const state = this.connection.getState();
    
    FORM_SCHEMA.fields.forEach(field => {
      const fieldValue = state.current_values[field.id];
      if (fieldValue && fieldValue.value) {
        const inputEl = document.getElementById(field.id) as HTMLInputElement;
        if (inputEl) {
          inputEl.value = String(fieldValue.value);
          
          if (fieldValue.confirmed) {
            inputEl.classList.add('field-confirmed');
            const badge = document.getElementById(`${field.id}Badge`);
            if (badge) {
              badge.style.display = 'inline-block';
            }
          }
        }
      }
    });
  }

  /**
   * Update completion percentage
   */
  private updateCompletion(): void {
    const state = this.connection.getState();
    const requiredFields = FORM_SCHEMA.fields.filter(f => f.required);
    const filledRequired = requiredFields.filter(f => 
      state.current_values[f.id]?.value
    ).length;
    
    const percentage = Math.round((filledRequired / requiredFields.length) * 100);
    this.els.completion.textContent = `${percentage}%`;
    this.els.progressFill.style.width = `${percentage}%`;
    this.els.progressFill.textContent = `${percentage}%`;
    
    if (percentage === 100) {
      this.els.submitBtn.disabled = false;
      this.els.submitBtn.classList.add('submit-ready');
    } else {
      this.els.submitBtn.disabled = true;
      this.els.submitBtn.classList.remove('submit-ready');
    }
  }

  /**
   * Update debug state display
   */
  private updateDebugState(): void {
    const state = this.connection.getState();
    this.els.debugState.textContent = JSON.stringify(state, null, 2);
  }

  /**
   * Reset state
   */
  private resetState(): void {
    if (!confirm('Clear all form data and reset state?')) {
      return;
    }

    // Clear sessionStorage
    sessionStorage.removeItem('webFormState');
    
    // Reset connection with fresh state
    const callbacks: ConnectionCallbacks = {
      onStatusChange: (status) => this.handleStatusChange(status),
      onSessionReady: (sessionId) => this.handleSessionReady(sessionId),
      onFieldUpdate: (updates) => this.handleFieldUpdates(updates),
      onError: (error) => this.handleError(error),
      onAudioData: (audioData) => this.playAudio(audioData),
    };
    this.connection = new WebFormConnection(FORM_SCHEMA, callbacks);
    
    // Clear form fields
    FORM_SCHEMA.fields.forEach(field => {
      const inputEl = document.getElementById(field.id) as HTMLInputElement;
      if (inputEl) {
        inputEl.value = '';
        inputEl.classList.remove('field-confirmed');
      }
      
      const badge = document.getElementById(`${field.id}Badge`);
      if (badge) {
        badge.style.display = 'none';
      }
    });
    
    this.updateCompletion();
    this.updateDebugState();
    this.log('State reset', 'warning');
  }

  /**
   * Submit form
   */
  private submitForm(): void {
    const state = this.connection.getState();
    this.log('Form submitted!', 'success');
    alert('Form submitted!\n\nData:\n' + JSON.stringify(state.current_values, null, 2));
  }

  /**
   * Log message to UI and console
   */
  private log(message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info'): void {
    const entry = document.createElement('div');
    entry.className = `log-entry log-${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    this.els.logs.appendChild(entry);
    this.els.logs.scrollTop = this.els.logs.scrollHeight;
    console.log(`[${type.toUpperCase()}]`, message);
  }
}

// Initialize app when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    const app = new TestDemoApp();
    app.init();
  });
} else {
  const app = new TestDemoApp();
  app.init();
}
