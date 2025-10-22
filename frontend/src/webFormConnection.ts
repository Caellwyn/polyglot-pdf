/**
 * WebFormConnection - WebSocket connection manage  async connect(wsUrl: string = "ws://localhost:8000/ws/fill"): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }
    
    this.setStatus("connecting");
    
    try:
      this.ws = new WebSocket(wsUrl); * 
 * Handles WebSocket lifecycle with auto-reconnect and state preservation.
 * Works with WebFormStateManager for stateless architecture.
 */

import { WebFormStateManager, WebFormState, FormSchema } from "./webFormState";
import { 
  computeNextField, 
  formatNextFieldHint, 
  getFieldOrder,
  isFormComplete 
} from "./navigation";

export type ConnectionStatus = 
  | "disconnected"
  | "connecting"
  | "connected"
  | "switching_section"
  | "reconnecting"
  | "error";

export interface ConnectionCallbacks {
  onStatusChange?: (status: ConnectionStatus) => void;
  onSessionReady?: (sessionId: string) => void;
  onSessionRestarted?: () => void;
  onFieldUpdate?: (updates: { fieldId: string; value: any }[]) => void;
  onError?: (error: Error) => void;
  onAudioData?: (arrayBuffer: ArrayBuffer) => void;
}

export class WebFormConnection {
  private ws: WebSocket | null = null;
  private state: WebFormState;
  private callbacks: ConnectionCallbacks;
  private status: ConnectionStatus = "disconnected";
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private reconnectTimer: number | null = null;
  private audioQueue: ArrayBuffer[] = [];
  private audioChunkCount = 0; // Track audio chunks for logging
  private isProcessingAudio = false;
  private enableAutoReconnect = false; // Only enable after first successful connection
  private isSectionSwitching = false; // Prevent auto-reconnect during intentional section switches
  private connectedUrl: string = ''; // Track the URL we're connected to (for section switches/reconnects)
  
  // Fill language for form fields
  private fillLanguage: string = "English";
  
  constructor(schema: FormSchema, callbacks: ConnectionCallbacks = {}, fillLanguage: string = "English") {
    this.state = WebFormStateManager.init(schema);
    this.callbacks = callbacks;
    this.fillLanguage = fillLanguage;
  }
  
  /**
   * Connect to WebSocket endpoint and send full form schema
   */
  async connect(wsUrl: string = "ws://localhost:8000/ws/fill", timeoutMs: number = 10000): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }
    
    // Store the URL we're connecting to
    this.connectedUrl = wsUrl;
    
    // Don't change status to "connecting" during section switches
    // (keeps current status visible until reconnected)
    if (!this.isSectionSwitching) {
      this.setStatus("connecting");
    }
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        if (this.ws) {
          this.ws.close();
          this.ws = null;
        }
        reject(new Error(`Connection timeout after ${timeoutMs}ms`));
      }, timeoutMs);
      
      try {
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
          clearTimeout(timeout);
          this.handleOpen();
          resolve();
        };
        
        this.ws.onmessage = (event) => this.handleMessage(event);
        
        this.ws.onerror = (error) => {
          clearTimeout(timeout);
          this.handleError(error);
          reject(error);
        };
        
        this.ws.onclose = () => {
          clearTimeout(timeout);
          this.handleClose();
        };
      } catch (error) {
        clearTimeout(timeout);
        this.handleError(error as Error);
        reject(error);
      }
    });
  }
  
  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    
    // Don't change status during section switches (will be updated after reconnect)
    if (!this.isSectionSwitching) {
      this.setStatus("disconnected");
    }
  }
  
  /**
   * Send handshake to establish ephemeral session
   */
  private handleOpen(): void {
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    
    // Enable auto-reconnect after first successful connection
    this.enableAutoReconnect = true;
    
    // Skip automatic handshake during section switches (startSection will send it)
    if (this.isSectionSwitching) {
      return;
    }
    
    // Send handshake with schema + current_values + fill_language
    const handshake = WebFormStateManager.getHandshakePayload(this.state, this.fillLanguage);
    this.send(handshake);
  }
  
  /**
   * Handle incoming messages
   */
  private async handleMessage(event: MessageEvent): Promise<void> {
    // Handle binary audio frames (silent - no logging)
    if (event.data instanceof ArrayBuffer || event.data instanceof Blob) {
      await this.handleAudioFrame(event.data);
      return;
    }
    
    // Handle JSON control messages
    try {
      const message = JSON.parse(event.data);
      
      switch (message.type) {
        case "session_ready":
          this.handleSessionReady(message);
          break;
          
        case "field_update":
          this.handleFieldUpdate(message);
          break;
          
        case "form_updated":
          this.handleFormUpdated(message);
          break;
          
        case "form_state_ack":
          break;
          
        case "hint_ack":
          // Backend acknowledges next field hint - silent
          break;
          
        case "get_form_state":
          this.handleGetFormStateRequest(message);
          break;
          
        case "get_next_field_hint":
          this.handleGetNextFieldHintRequest(message);
          break;
          
        case "prepare_section_switch":
          this.handlePrepareSectionSwitchRequest(message);
          break;
          
        case "section_switched":
          this.handleSectionSwitched(message);
          break;
          
        case "switch_section":
          this.handleSwitchSectionRequest(message);
          break;
          
        case "get_field_value":
          this.handleGetFieldValueRequest(message);
          break;
          
        case "complete_section":
          this.handleCompleteSectionRequest(message);
          break;
          
        case "error":
          this.handleServerError(message);
          break;
          
        case "ai_response":
          // AI is speaking - no action needed
          break;
          
        case "turn_complete":
          // Gemini finished speaking (transcript received) - signal to activity watchdog
          if (window.vffOnTurnComplete) {
            window.vffOnTurnComplete();
          }
          break;
        
        case "gemini_session_restarted":
          // Backend confirms Gemini session has been restarted successfully
          console.log('[WebFormConnection] ✅ Gemini session restarted successfully');
          // Trigger callback to update UI (ConnectionManager will set status to 'connected')
          if (this.callbacks.onSessionRestarted) {
            this.callbacks.onSessionRestarted();
          }
          break;
          
        default:
          // Unknown message type - ignore
          break;
      }
    } catch (error) {
      // Failed to parse message - ignore
    }
  }
  
  /**
   * Handle session_ready message from backend
   */
  private handleSessionReady(message: any): void {
    const { session_id, ephemeral } = message;
    
    // Update state with session ID
    this.state = WebFormStateManager.setSessionId(this.state, session_id);
    this.setStatus("connected");
    
    if (this.callbacks.onSessionReady) {
      this.callbacks.onSessionReady(session_id);
    }
    
    // No need to send initial hint - backend will request it as part of initial message
  }
  
  /**
   * Handle field_update from AI
   */
  private handleFieldUpdate(message: any): void {
    const { updates } = message;
    
    if (!updates || typeof updates !== "object") {
      return;
    }
    
    // Apply updates to state
    const updatedFields: Array<{ fieldId: string; value: any }> = [];
    
    for (const [displayName, value] of Object.entries(updates)) {
      // Find field by display name
      const field = this.state.schema.fields.find(
        (f) => f.name === displayName || f.id === displayName
      );
      
      if (field) {
        this.updateField(field.id, value as any, { confirmed: true, emit: false });
        updatedFields.push({ fieldId: field.id, value });
      } else {
        // Field not found in schema - ignore
      }
    }
    
    // Notify callback
    if (this.callbacks.onFieldUpdate && updatedFields.length > 0) {
      this.callbacks.onFieldUpdate(updatedFields);
    }
  }

  private handleFormUpdated(message: any): void {
    const data = (message && message.data) || {};
    const formState = data.form_state || {};
    const applied = data.applied_fields || [];
    const requestNextFieldHint = data.request_next_field_hint || false;
    const requestId = data.request_id;

    if (!formState || typeof formState !== "object") {
      return;
    }

    const appliedSet = new Set(applied.map((entry: any) => String(entry)));
    const limitToApplied = appliedSet.size > 0;

    const updatedFields: Array<{ fieldId: string; value: any }> = [];

    for (const field of this.state.schema.fields) {
      const value =
        (formState as Record<string, unknown>)[field.id] ??
        (formState as Record<string, unknown>)[field.name ?? ""];
      if (value === undefined) {
        continue;
      }

      const isApplied = appliedSet.has(field.id) || (field.name ? appliedSet.has(field.name) : false);
      if (limitToApplied && !isApplied) {
        continue;
      }

      const currentValue = this.state.current_values[field.id]?.value;
      const shouldUpdate = isApplied || !Object.is(currentValue, value);
      if (!shouldUpdate) {
        continue;
      }

      this.updateField(field.id, value as any, { confirmed: isApplied, emit: false });
      updatedFields.push({ fieldId: field.id, value });
    }
    
    // Also check for fields where Gemini dropped the [] suffix (e.g., "functioningConcerns" instead of "functioningConcerns[]")
    for (const [key, value] of Object.entries(formState)) {
      // Skip if we already processed this field
      if (this.state.schema.fields.some(f => f.id === key || f.name === key)) {
        continue;
      }
      
      // Try appending [] to see if that matches a field
      const keyWithBrackets = key + '[]';
      const field = this.state.schema.fields.find(f => f.id === keyWithBrackets || f.name === keyWithBrackets);
      
      if (field) {
        const isApplied = appliedSet.has(key) || appliedSet.has(keyWithBrackets);
        if (limitToApplied && !isApplied) {
          continue;
        }
        
        const currentValue = this.state.current_values[field.id]?.value;
        const shouldUpdate = isApplied || !Object.is(currentValue, value);
        if (!shouldUpdate) {
          continue;
        }
        
        this.updateField(field.id, value as any, { confirmed: isApplied, emit: false });
        updatedFields.push({ fieldId: field.id, value });
      }
    }

    if (updatedFields.length) {
      if (this.callbacks.onFieldUpdate) {
        this.callbacks.onFieldUpdate(updatedFields);
      }
    }

    // If backend requested next field hint, send it now
    if (requestNextFieldHint && requestId) {
      const hint = this.computeNextFieldHintString();
      
      // Store last field hint for recovery prompts
      if (hint) {
        sessionStorage.setItem('vff_last_field_hint', hint);
      }
      
      this.send({
        type: "next_field_hint_response",
        request_id: requestId,
        hint: hint
      });
    }
  }

  /**
   * Handle get_form_state request from backend
   * Part of async request/response pattern for stateless backend
   */
  private handleGetFormStateRequest(message: any): void {
    const requestId = message.request_id;
    const requestedFieldIds: string[] = message.field_ids || [];
    
    // Build field values response
    const fieldValues: Record<string, any> = {};
    
    if (requestedFieldIds.length === 0) {
      // No specific fields requested - return all
      for (const [fieldId, fieldValue] of Object.entries(this.state.current_values)) {
        fieldValues[fieldId] = {
          value: fieldValue.value,
          confirmed: fieldValue.confirmed,
        };
      }
    } else {
      // Return only requested fields
      for (const fieldId of requestedFieldIds) {
        let fieldValue = this.state.current_values[fieldId];
        
        // Fallback: Try with [] appended if not found (Gemini sometimes drops the [])
        if (!fieldValue && !fieldId.endsWith('[]')) {
          fieldValue = this.state.current_values[fieldId + '[]'];
        }
        
        // Fallback: Try without [] if not found (in case query has [] but state doesn't)
        if (!fieldValue && fieldId.endsWith('[]')) {
          fieldValue = this.state.current_values[fieldId.slice(0, -2)];
        }
        
        if (fieldValue) {
          fieldValues[fieldId] = {
            value: fieldValue.value,
            confirmed: fieldValue.confirmed,
          };
        } else {
          // Field not yet filled
          fieldValues[fieldId] = {
            value: null,
            confirmed: false,
          };
        }
      }
    }
    
    // Send response back to backend
    this.send({
      type: "form_state_response",
      request_id: requestId,
      field_values: fieldValues,
    });
  }

  /**
   * Handle get_next_field_hint request from backend
   * Part of async request/response pattern for navigation hints
   */
  private handleGetNextFieldHintRequest(message: any): void {
    const requestId = message.request_id;
    
    // Compute next field hint
    const hint = this.computeNextFieldHintString();
    
    // Store last field hint for recovery prompts
    if (hint) {
      sessionStorage.setItem('vff_last_field_hint', hint);
    }
    
    // Send response back to backend
    this.send({
      type: "next_field_hint_response",
      request_id: requestId,
      hint: hint,  // Can be null if form is complete
    });
  }

  /**
   * Compute next field hint string (helper for hint requests)
   * Returns null if form is complete
   */
  private computeNextFieldHintString(): string | null {
    // Check if form is complete
    if (isFormComplete(this.state)) {
      return null;
    }
    
    // Compute next field to fill
    const nextField = computeNextField(this.state, { skipConfirmed: true });
    
    if (!nextField) {
      return null;
    }
    
    // Get field order for hint
    const fieldOrder = getFieldOrder(this.state, nextField.id);
    
    // Format hint for Gemini
    const hint = formatNextFieldHint(nextField, fieldOrder || undefined);
    
    return hint;
  }

  /**
   * Public method to get next field hint for session restart
   * Used by connection manager when restarting Gemini session
   */
  public getNextFieldHint(): string | null {
    return this.computeNextFieldHintString();
  }

  /**
   * Phase 3: Handle switch_section request from backend (AI tool call)
   */
  private async handleSwitchSectionRequest(message: any): Promise<void> {
    const identifier = message.identifier;
    
    try {
      // Parse identifier - try as number first
      let targetNumber: number | undefined;
      
      if (typeof identifier === 'number') {
        targetNumber = identifier;
      } else if (typeof identifier === 'string') {
        // Try to parse as number
        const parsed = parseInt(identifier, 10);
        if (!isNaN(parsed)) {
          targetNumber = parsed;
        } else {
          // Look up by label (case-insensitive)
          const currentState = WebFormStateManager.load();
          if (currentState?.section_index) {
            const identifierLower = identifier.toLowerCase();
            const section = currentState.section_index.sections.find(
              s => s.section_label.toLowerCase() === identifierLower ||
                   s.section_id.toLowerCase() === identifierLower
            );
            
            if (section) {
              targetNumber = section.section_number;
            }
          }
        }
      }
      
      if (!targetNumber) {
        return;
      }
      
      // Call existing switchSection method using the stored connected URL
      await this.switchSection(targetNumber, this.connectedUrl);
      
    } catch (error) {
      // Error switching section - ignore
    }
  }

  /**
   * Handle prepare_section_switch request from backend (new backend-side reconnect pattern)
   */
  private handlePrepareSectionSwitchRequest(message: any): void {
    const requestId = message.request_id;
    const identifier = message.identifier;
    
    console.log('[WebFormConnection] handlePrepareSectionSwitchRequest START', { requestId, identifier });
    
    try {
      const currentState = WebFormStateManager.load();
      console.log('[WebFormConnection] Loaded state', { hasState: !!currentState, hasSectionIndex: !!currentState?.section_index });
      
      if (!currentState || !currentState.section_index) {
        // Send error response
        console.log('[WebFormConnection] No state/section_index, sending null response');
        this.send({
          type: "section_info_response",
          request_id: requestId,
          section_info: null,
        });
        return;
      }
      
      // Parse identifier - try as number first
      let targetNumber: number | undefined;
      
      if (typeof identifier === 'number') {
        targetNumber = identifier;
      } else if (typeof identifier === 'string') {
        const parsed = parseInt(identifier, 10);
        if (!isNaN(parsed)) {
          targetNumber = parsed;
        } else {
          // Look up by label
          const identifierLower = identifier.toLowerCase();
          const section = currentState.section_index.sections.find(
            s => s.section_label.toLowerCase() === identifierLower ||
                 s.section_id.toLowerCase() === identifierLower
          );
          if (section) {
            targetNumber = section.section_number;
          }
        }
      }
      
      console.log('[WebFormConnection] Parsed target number:', targetNumber);
      
      if (!targetNumber) {
        console.log('[WebFormConnection] Invalid target number, sending null response');
        this.send({
          type: "section_info_response",
          request_id: requestId,
          section_info: null,
        });
        return;
      }
      
      // Switch to target section in local state (no disconnect!)
      console.log('[WebFormConnection] Switching to section', targetNumber);
      const updatedState = WebFormStateManager.switchSection(currentState, targetNumber);
      this.state = updatedState;
      
      // Get section schema and values
      console.log('[WebFormConnection] Building section schema and values');
      const sectionSchema = updatedState.schema;
      const sectionFieldIds = new Set(sectionSchema.fields.map(f => f.id));
      const sectionValues: Record<string, any> = {};
      
      for (const [fieldId, fieldValue] of Object.entries(updatedState.current_values)) {
        if (sectionFieldIds.has(fieldId)) {
          sectionValues[fieldId] = fieldValue;
        }
      }
      
      // Build previous spoken names from completed sections
      console.log('[WebFormConnection] Building previous spoken names');
      const spokenNameMap = WebFormStateManager.getSpokenNameMap(updatedState);
      const previousSpokenNames = Array.from(spokenNameMap.keys());
      
      // Compute initial field hint
      console.log('[WebFormConnection] Computing initial field hint');
      const initialFieldHint = this.computeNextFieldHintString();
      
      // Store last field hint for recovery prompts
      if (initialFieldHint) {
        sessionStorage.setItem('vff_last_field_hint', initialFieldHint);
      }
      
      console.log('[WebFormConnection] Sending section_info_response', { 
        requestId, 
        sectionNumber: targetNumber,
        fieldCount: sectionSchema.fields.length,
        valueCount: Object.keys(sectionValues).length
      });
      
      // Send section info back to backend
      this.send({
        type: "section_info_response",
        request_id: requestId,
        section_info: {
          schema: sectionSchema,
          current_values: sectionValues,
          metadata: {
            section_number: targetNumber,
            total_sections: updatedState.section_index!.total_sections,
            section_label: WebFormStateManager.getSectionLabel(updatedState, targetNumber) || '',
            previous_spoken_names: previousSpokenNames,
          },
          initial_field_hint: initialFieldHint,
        },
      });
      
      console.log('[WebFormConnection] handlePrepareSectionSwitchRequest COMPLETE');
      
    } catch (error) {
      console.error('[WebFormConnection] Error preparing section switch:', error);
      this.send({
        type: "section_info_response",
        request_id: requestId,
        section_info: null,
      });
    }
  }

  /**
   * Handle section_switched confirmation from backend
   */
  private handleSectionSwitched(message: any): void {
    const sectionNumber = message.section_number;
    console.log(`[WebFormConnection] Section switched confirmed: ${sectionNumber}`);
    
    // Update status
    this.setStatus('connected');
    
    // State was already updated in handlePrepareSectionSwitchRequest
    // Just confirm the switch is complete
  }

  /**
   * Phase 3: Handle get_field_value request from backend (AI tool call)
   */
  private handleGetFieldValueRequest(message: any): void {
    const requestId = message.request_id;
    const spokenName = message.spoken_name;
    
    try {
      const currentState = WebFormStateManager.load();
      if (!currentState) {
        this.sendFieldValueResponse(requestId, null, false);
        return;
      }
      
      // Get spoken name map (includes current + completed sections)
      const spokenNameMap = WebFormStateManager.getSpokenNameMap(currentState);
      
      // Lookup field ID by spoken name (case-insensitive)
      const fieldId = spokenNameMap.get(spokenName.toLowerCase());
      
      if (!fieldId) {
        this.sendFieldValueResponse(requestId, null, false);
        return;
      }
      
      // Get value from current_values
      const value = currentState.current_values[fieldId];
      
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        this.sendFieldValueResponse(requestId, value, true);
      } else {
        this.sendFieldValueResponse(requestId, null, false);
      }
      
    } catch (error) {
      this.sendFieldValueResponse(requestId, null, false);
    }
  }

  /**
   * Phase 3: Send field_value_response back to backend
   */
  private sendFieldValueResponse(requestId: string, value: any, found: boolean): void {
    this.send({
      type: "field_value_response",
      request_id: requestId,
      value: value,
      found: found,
    });
  }

  /**
   * Phase 3: Handle complete_section request from backend (AI tool call)
   */
  private async handleCompleteSectionRequest(message: any): Promise<void> {
    try {
      // Mark current section as complete in state
      const currentState = WebFormStateManager.load();
      if (!currentState || !currentState.current_section) {
        throw new Error('Section state not initialized');
      }
      
      const currentSection = currentState.current_section;
      const updatedState = WebFormStateManager.completeSection(currentState, currentSection);
      this.state = updatedState;
      
      // Check if this was the last section
      if (currentSection >= updatedState.section_index!.total_sections) {
        // Form is complete - stay connected but don't start new section
        this.send({
          type: "section_completed",
          next_section: currentSection, // Same section (we're done)
          form_complete: true,
        });
        return;
      }
      
      // Move to next section using backend-side reconnect (switchSection pattern)
      const nextSection = currentSection + 1;
      
      // Use the switchSection method which uses manual_section_switch message
      // This keeps WebSocket alive and lets backend restart Gemini session
      await this.switchSection(nextSection, this.connectedUrl);
      
      // Send response to backend confirming section completed
      this.send({
        type: "section_completed",
        next_section: nextSection,
        form_complete: false,
      });
      
    } catch (error) {
      console.error('[WebFormConnection] Error completing section:', error);
      // Send error response to backend
      this.send({
        type: "section_completed",
        success: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  /**
   * Send completion message to AI when form is complete
   * Part of Phase 1: Graceful completion handling
   */
  private sendCompletionMessage(): void {
    const completionMessage = "Say the following: 'The form is complete. if all fields are correct, please press submit.'";
    
    this.send({
      type: "completion_message",
      message: completionMessage,
    });
  }

  /**
   * Handle audio frames from AI
   */
  private async handleAudioFrame(data: ArrayBuffer | Blob): Promise<void> {
    const arrayBuffer = data instanceof Blob ? await data.arrayBuffer() : data;
    
    // Track audio chunks received
    if (!this.audioChunkCount) {
      this.audioChunkCount = 0;
    }
    this.audioChunkCount++;
    
    if (this.audioChunkCount === 1) {
      console.log(`[WebFormConnection] 📥 First audio chunk received from server (${arrayBuffer.byteLength} bytes)`);
    } else if (this.audioChunkCount % 10 === 0) {
      console.log(`[WebFormConnection] 📥 Audio chunk #${this.audioChunkCount} (${arrayBuffer.byteLength} bytes)`);
    }
    
    // Queue audio for processing
    this.audioQueue.push(arrayBuffer);
    
    if (!this.isProcessingAudio) {
      this.processAudioQueue();
    }
  }
  
  /**
   * Process queued audio frames
   */
  private async processAudioQueue(): Promise<void> {
    this.isProcessingAudio = true;
    
    while (this.audioQueue.length > 0) {
      const audioData = this.audioQueue.shift()!;
      
      // Silent audio processing - no logging
      
      if (this.callbacks.onAudioData) {
        this.callbacks.onAudioData(audioData);
      }
    }
    
    this.isProcessingAudio = false;
  }
  
  /**
   * Handle server error messages
   */
  private handleServerError(message: any): void {
    console.error('[WebFormConnection] Server error received:', {
      code: message.code,
      reason: message.reason,
      message: message.message,
      fullMessage: message
    });
    // Build error message from available fields
    const errorText = message.message || message.reason || message.code || "Server error";
    const error = new Error(errorText);
    
    if (this.callbacks.onError) {
      this.callbacks.onError(error);
    }
  }
  
  /**
   * Handle WebSocket errors
   */
  private handleError(error: Event | Error): void {
    // Don't show error during section switches (expected during reconnect)
    if (!this.isSectionSwitching) {
      this.setStatus("error");
    }
    
    if (this.callbacks.onError && error instanceof Error) {
      this.callbacks.onError(error);
    }
  }
  
  /**
   * Handle WebSocket close
   */
  private handleClose(): void {
    // Don't auto-reconnect if this is the initial connection attempt
    // (allows fallback logic in connection.ts to try cloud URL)
    if (!this.enableAutoReconnect) {
      this.setStatus("disconnected");
      return;
    }
    
    // Don't auto-reconnect during intentional section switches
    if (this.isSectionSwitching) {
      return; // Keep current status, will be updated after reconnect
    }
    
    // Attempt reconnect if not intentionally disconnected
    if (this.status !== "disconnected" && this.reconnectAttempts < this.maxReconnectAttempts) {
      this.attemptReconnect();
    } else {
      this.setStatus("disconnected");
    }
  }
  
  /**
   * Attempt to reconnect with exponential backoff
   */
  private attemptReconnect(): void {
    this.reconnectAttempts++;
    this.setStatus("reconnecting");
    
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      30000 // Max 30 seconds
    );
    
    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, delay);
  }
  
  /**
   * Wait for WebSocket send buffer to drain
   */
  private async waitForBufferDrain(maxWaitMs: number = 1000): Promise<void> {
    if (!this.ws) return;
    
    const startTime = Date.now();
    while (this.ws.bufferedAmount > 0) {
      if (Date.now() - startTime > maxWaitMs) {
        console.warn('[WebFormConnection] Buffer drain timeout', {
          bufferedAmount: this.ws.bufferedAmount,
          waitedMs: Date.now() - startTime
        });
        break;
      }
      // Wait 10ms before checking again
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    if (this.ws.bufferedAmount === 0) {
      console.log('[WebFormConnection] Buffer drained successfully', {
        waitedMs: Date.now() - startTime
      });
    }
  }

  /**
   * Send message to server
   */
  send(message: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error('[WebFormConnection] send() called but WebSocket not open!', {
        hasWs: !!this.ws,
        readyState: this.ws?.readyState,
        message: message
      });
      return;
    }
    
    if (message instanceof ArrayBuffer) {
      this.ws.send(message);
    } else {
      const jsonStr = JSON.stringify(message);
      console.log('[WebFormConnection] Sending JSON message', {
        type: message.type,
        size: jsonStr.length,
        readyState: this.ws.readyState,
        bufferedAmount: this.ws.bufferedAmount
      });
      this.ws.send(jsonStr);
    }
  }
  
  /**
   * Send audio data to AI
   */
  sendAudio(audioData: ArrayBuffer): void {
    this.send(audioData);
  }
  
  /**
   * Send manual field update notification to Gemini
   * Notifies AI when user manually edits a field
   */
  sendManualFieldUpdate(fieldId: string, fieldName: string, value: any): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    
    this.send({
      type: 'manual_field_update',
      field_id: fieldId,
      field_name: fieldName,
      value: value,
    });
  }
  
  
  /**
   * Send activity_start signal to Gemini (user started speaking).
   * Signals the beginning of user speech before sending audio chunks.
   */
  sendActivityStart(): void {
    console.log(`[WebFormConnection] 📤 sendActivityStart() called - WebSocket state: ${this.ws ? this.ws.readyState : 'null'} (OPEN=${WebSocket.OPEN})`)
    
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error(`[WebFormConnection] ❌ Cannot send activity_start - WebSocket not open (state: ${this.ws ? this.ws.readyState : 'null'})`)
      return;
    }

    console.log('[WebFormConnection] 📤 Sending activity_start message to backend')
    this.send({
      type: 'vad_activity_start',
      timestamp: Date.now(),
    });
  }

  /**
   * Send activity_end signal to Gemini (user stopped speaking).
   * Signals the end of user speech and flushes Gemini's cached audio buffer.
   */
  sendActivityEnd(): void {
    console.log(`[WebFormConnection] 📤 sendActivityEnd() called - WebSocket state: ${this.ws ? this.ws.readyState : 'null'} (OPEN=${WebSocket.OPEN})`)
    
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error(`[WebFormConnection] ❌ Cannot send activity_end - WebSocket not open (state: ${this.ws ? this.ws.readyState : 'null'})`)
      return;
    }

    console.log('[WebFormConnection] 📤 Sending activity_end message to backend')
    this.send({
      type: 'vad_activity_end',
      timestamp: Date.now(),
    });
  }
  
  /**
   * Send text prompt to Gemini (for recovery, nudges, inactivity handling)
   * Uses completion_message type to send direct text instructions
   */
  sendPrompt(prompt: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebFormConnection] Cannot send prompt - not connected');
      return;
    }
    
    console.log('[WebFormConnection] Sending prompt to Gemini:', prompt);
    this.send({
      type: 'completion_message',
      message: prompt,
    });
  }
  
  /**
   * Send recovery prompt to Gemini (activity watchdog escalation)
   * Backend translates level into configured prompt from config.py
   * 
   * @param level - Escalation level (1=next field, 2=presence check, 3=goodbye)
   * @param nextFieldHint - Optional hint for level 1 (e.g., "firstName (First Name)")
   */
  sendRecoveryPrompt(level: number, nextFieldHint?: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebFormConnection] Cannot send recovery prompt - not connected');
      return;
    }
    
    console.log(`[WebFormConnection] Sending recovery prompt level ${level}`, nextFieldHint ? `with hint: ${nextFieldHint}` : '');
    this.send({
      type: 'recovery_prompt',
      level: level,
      next_field_hint: nextFieldHint,
    });
  }
  
  /**
   * End Gemini session only (keep WebSocket alive)
   * Called after Level 3 farewell completes
   */
  endGeminiSession(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WebFormConnection] Cannot end Gemini session - not connected');
      return;
    }
    
    console.log('[WebFormConnection] 🚪 Ending Gemini session (keeping WebSocket alive)');
    this.send({
      type: 'end_gemini_session',
    });
  }
  
  /**
   * Change the language used for filling form field values
   * Sends a message to backend which forwards it to Gemini
   */
  async changeFillLanguage(language: string): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }
    
    // Update internal state
    this.fillLanguage = language;
    
    this.send({
      type: 'change_fill_language',
      language: language,
    });
    
    // Wait for acknowledgment (optional - fire and forget is also fine)
    // The backend will send back a language_changed message
  }
  
  /**
   * Update field value (user edit)
   */
  updateField(
    fieldId: string,
    value: string | boolean | null,
    options?: { confirmed?: boolean; emit?: boolean }
  ): void {
    const confirmed = options?.confirmed;
    const emit = options?.emit ?? false;

    this.state = WebFormStateManager.updateFieldValue(this.state, fieldId, value, { confirmed });

    if (emit) {
      this.flushField(fieldId);
    }
  }

  flushField(fieldId: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const fieldState = this.state.current_values[fieldId];
    if (!fieldState) {
      return;
    }

    this.send({
      type: "form_state",
      fields: [
        {
          field_id: fieldId,
          value: fieldState.value,
          confirmed: !!fieldState.confirmed,
        },
      ],
    });

    // No need to send hint for manual edits - user is in control
    // Next hint will be requested when AI next calls update_form_fields
  }
  
  /**
   * Set connection status and notify
   */
  private setStatus(status: ConnectionStatus): void {
    if (this.status === status) return;
    
    this.status = status;
    
    if (this.callbacks.onStatusChange) {
      this.callbacks.onStatusChange(status);
    }
  }
  
  /**
   * Get current status
   */
  getStatus(): ConnectionStatus {
    return this.status;
  }
  
  /**
   * Get current state
   */
  getState(): WebFormState {
    return this.state;
  }
  
  /**
   * Get completion percentage
   */
  getCompletionPercentage(): number {
    return WebFormStateManager.getCompletionPercentage(this.state);
  }
  
  /**
   * Clear state and disconnect
   */
  reset(): void {
    this.disconnect();
    WebFormStateManager.clear();
  }
  
  /**
   * Phase 3: Start a specific section (closes current session, starts new one)
   */
  async startSection(sectionNumber: number, wsUrl: string = "ws://localhost:8000/ws/fill"): Promise<void> {
    try {
      // Set switching status
      this.isSectionSwitching = true;
      this.setStatus("switching_section");
      
      // Disconnect current session if connected
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.disconnect();
        // Wait a moment for cleanup
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      // Load current state
      let currentState = WebFormStateManager.load();
      if (!currentState || !currentState.section_index || !currentState.full_schema) {
        throw new Error('Section index or full schema not initialized');
      }
      
      // Switch to target section
      currentState = WebFormStateManager.switchSection(currentState, sectionNumber);
      this.state = currentState;
      
      // Get section schema and current values for this section
      const sectionSchema = currentState.schema;
      const sectionValues: Record<string, any> = {};
      
      // Filter current_values to only include fields in this section
      const sectionFieldIds = new Set(sectionSchema.fields.map(f => f.id));
      for (const [fieldId, fieldValue] of Object.entries(currentState.current_values)) {
        if (sectionFieldIds.has(fieldId)) {
          sectionValues[fieldId] = fieldValue;
        }
      }
      
      // Build previous_spoken_names from completed sections
      const spokenNameMap = WebFormStateManager.getSpokenNameMap(currentState);
      const previousSpokenNames = Array.from(spokenNameMap.keys());
      
      // Connect to backend with section-specific handshake
      await this.connect(wsUrl);
      this.isSectionSwitching = false; // Reset flag after successful reconnect
      
      // Compute initial field hint (first unfilled field in this section)
      const initialFieldHint = this.computeNextFieldHintString();
      
      // Send handshake with section metadata and initial field hint
      this.send({
        type: "handshake",
        schema: sectionSchema,
        current_values: sectionValues,
        fill_language: this.fillLanguage,
        // Phase 3: Section metadata
        section_number: sectionNumber,
        total_sections: currentState.section_index!.total_sections,
        section_label: WebFormStateManager.getSectionLabel(currentState, sectionNumber) || '',
        previous_spoken_names: previousSpokenNames,
        // Include initial field hint so backend can use it immediately
        initial_field_hint: initialFieldHint,
      });
      
    } catch (error) {
      // Reset flag on error
      this.isSectionSwitching = false;
      throw error;
    }
  }
  
  /**
   * Phase 3: Switch to a different section (NEW: backend-side reconnect pattern)
   * 
   * This now uses the backend-side Gemini reconnect pattern instead of disconnecting
   * the WebSocket. The backend closes/recreates the Gemini session with fresh context.
   * 
   * @param target - Section number (1-indexed) or section label
   * @param wsUrl - Backend WebSocket URL (kept for API compatibility but not used)
   */
  async switchSection(target: number | string, wsUrl: string): Promise<void> {
    const currentState = WebFormStateManager.load();
    if (!currentState || !currentState.section_index) {
      throw new Error('Section index not initialized');
    }
    
    let targetNumber: number;
    
    // Parse target: number or label
    if (typeof target === 'number') {
      targetNumber = target;
    } else {
      // Try to find by label
      const found = WebFormStateManager.findSectionByLabel(currentState, target);
      if (!found) {
        throw new Error(`Section not found: ${target}`);
      }
      targetNumber = found;
    }
    
    // Validate range
    if (targetNumber < 1 || targetNumber > currentState.section_index.total_sections) {
      throw new Error(`Invalid section number: ${targetNumber} (must be 1-${currentState.section_index.total_sections})`);
    }
    
    // Wait for WebSocket send buffer to drain before sending control message
    // This prevents the control message from being queued behind audio frames
    console.log('[WebFormConnection] Waiting for buffer to drain before section switch');
    await this.waitForBufferDrain(1000);
    
    // Update status
    this.setStatus('switching_section');
    
    // Switch to target section in local state
    const updatedState = WebFormStateManager.switchSection(currentState, targetNumber);
    this.state = updatedState;
    
    // Build section info to send to backend (avoid round-trip delay)
    const sectionSchema = updatedState.schema;
    const sectionFieldIds = new Set(sectionSchema.fields.map(f => f.id));
    const sectionValues: Record<string, any> = {};
    
    for (const [fieldId, fieldValue] of Object.entries(updatedState.current_values)) {
      if (sectionFieldIds.has(fieldId)) {
        sectionValues[fieldId] = fieldValue;
      }
    }
    
    // Build previous spoken names from completed sections
    const spokenNameMap = WebFormStateManager.getSpokenNameMap(updatedState);
    const previousSpokenNames = Array.from(spokenNameMap.keys());
    
    // Compute initial field hint
    const initialFieldHint = this.computeNextFieldHintString();
    
    console.log('[WebFormConnection] Sending section switch with embedded info', {
      sectionNumber: targetNumber,
      fieldCount: sectionSchema.fields.length,
      valueCount: Object.keys(sectionValues).length
    });
    
    // Send section switch with all info embedded (no round-trip needed)
    this.send({
      type: "manual_section_switch",
      identifier: targetNumber.toString(),
      section_info: {
        schema: sectionSchema,
        current_values: sectionValues,
        metadata: {
          section_number: targetNumber,
          total_sections: updatedState.section_index!.total_sections,
          section_label: WebFormStateManager.getSectionLabel(updatedState, targetNumber) || '',
          previous_spoken_names: previousSpokenNames,
        },
        initial_field_hint: initialFieldHint,
      },
    });
  }
  
  /**
   * Phase 3: Complete current section and move to next
   * 
   * @param wsUrl - Backend WebSocket URL (REQUIRED - no default to prevent localhost fallback in production)
   */
  async completeSection(wsUrl: string): Promise<void> {
    if (!wsUrl) {
      throw new Error('wsUrl is required for completeSection - must pass the connected backend URL');
    }
    const currentState = WebFormStateManager.load();
    if (!currentState || !currentState.current_section || !currentState.section_index) {
      throw new Error('Section state not initialized');
    }
    
    const currentSection = currentState.current_section;
    
    // Mark section as complete
    const updatedState = WebFormStateManager.completeSection(currentState, currentSection);
    this.state = updatedState;
    
    // Check if this was the last section
    if (currentSection >= updatedState.section_index!.total_sections) {
      this.setStatus('connected'); // Stay connected but don't start new section
      return;
    }
    
    // Move to next section
    const nextSection = currentSection + 1;
    await this.startSection(nextSection, wsUrl);
  }
  
  /**
   * Phase 3: Get current section number
   */
  getCurrentSection(): number | undefined {
    return this.state.current_section;
  }
  
  /**
   * Phase 3: Get completed sections
   */
  getCompletedSections(): Set<number> {
    return this.state.completed_sections || new Set();
  }
}
