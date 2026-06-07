/**
 * WebFormConnection - WebSocket connection manager
 *
 * Handles WebSocket lifecycle with auto-reconnect and state preservation.
 * Works with SchemaFormStateManager for stateless architecture.
 */

import {
  SchemaFormStateManager,
  type SchemaFormState
} from "./schema-forms/state/schemaFormState";
import type { FormSchema } from "./schema-forms/types/schema";
import {
  computeNextField,
  formatNextFieldHint,
  getFieldOrder,
  isFormComplete
} from "./navigation";
import { shouldShowField } from "./schema-forms/utils/validation";
import { evaluateFieldAvailability } from "./schema-forms/utils/conditionalFieldCheck";
import { FIELD_HIGHLIGHT_DURATION_MS } from "./schema-forms/utils/fieldHighlight";

/**
 * Remove a `token=...` query parameter from a ws URL, wherever it sits, without
 * leaving a dangling or doubled separator (bd polyglot-pdf-wq0). Handles token
 * alone (`?token=x`), first (`?token=x&a=b`), middle (`?a=b&token=x&c=d`), and
 * last (`?a=b&token=x`); returns the URL unchanged when there is no token.
 */
export function stripToken(url: string): string {
  const qIndex = url.indexOf("?");
  if (qIndex === -1) return url;

  const base = url.slice(0, qIndex);
  const params = url
    .slice(qIndex + 1)
    .split("&")
    .filter((p) => p.length > 0 && !p.startsWith("token="));

  return params.length > 0 ? `${base}?${params.join("&")}` : base;
}

export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "switching_section"
  | "reconnecting"
  | "idle_timeout"
  | "error";

export interface ConnectionCallbacks {
  onStatusChange?: (status: ConnectionStatus) => void;
  onSessionReady?: (sessionId: string) => void;
  onSessionRestarted?: () => void;
  onSectionChanged?: () => void;
  onFieldUpdate?: (updates: { fieldId: string; value: any }[]) => void;
  onError?: (error: Error) => void;
  onAudioData?: (arrayBuffer: ArrayBuffer) => void;
  onNextField?: (fieldId: string | null) => void;
  // Native-VAD mode toggle from the backend session_ready handshake (bd
  // polyglot-pdf-333). When enabled, the connection layer must stop sending
  // manual activity signals and stream continuous audio.
  onNativeVadMode?: (enabled: boolean) => void;
}

export class WebFormConnection {
  private ws: WebSocket | null = null;
  private state: SchemaFormState;
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
  private idleTimedOut: boolean = false; // Track if connection was closed due to idle timeout

  // Loop-breaker for unconfirmable fields (bd polyglot-pdf-0y7). When the backend
  // asks to confirm_field a field that has no usable value, the confirm cannot make
  // progress, so computeNextField() keeps returning the SAME field and the backend
  // re-requests it forever (a tight confirm/next-field-hint loop that strands the
  // session). We count consecutive failed confirms of the same field and, every
  // CONFIRM_LIMIT attempts, re-prompt Gemini to collect the value -- up to a hard
  // REPROMPT_CAP, after which we stop entirely so a genuinely unfillable field does
  // not spin forever even at the reduced re-prompt rate (fresh-eyes PR #113). All
  // three counters reset on a successful confirm and on (re)connect.
  private lastUnconfirmableFieldId: string | null = null;
  private unconfirmableConfirmCount = 0;
  private unconfirmableRepromptCount = 0;
  private static readonly UNCONFIRMABLE_CONFIRM_LIMIT = 2;
  private static readonly UNCONFIRMABLE_REPROMPT_CAP = 3;

  // Auth token plumbing (bd polyglot-pdf-wq0). The backend /ws/fill gate rejects
  // tokenless connections with HTTP 403. Reconnect paths (startSection,
  // attemptReconnect) previously called connect() without a token, so every
  // reconnect -- notably the post-disclaimer first-section switch -- got 403.
  // We hold a getToken callback and fetch a FRESH token before every (re)connect,
  // which also covers ~1h Firebase ID token expiry on long sessions. lastToken is
  // a fallback so a one-off token-fetch failure does not regress a working path.
  private getToken?: () => Promise<string | undefined>;
  private lastToken?: string;

  // Fill language for form fields
  private fillLanguage: string = "English";

  constructor(schema: FormSchema, callbacks: ConnectionCallbacks = {}, fillLanguage: string = "English") {
    this.state = SchemaFormStateManager.init(schema);
    this.callbacks = callbacks;
    this.fillLanguage = fillLanguage;
  }

  /**
   * Connect to WebSocket endpoint and send full form schema
   */
  async connect(wsUrl: string = "ws://localhost:8000/ws/fill", timeoutMs: number = 10000, token?: string): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return;
    }

    // Resolve the auth token for THIS connect (bd polyglot-pdf-wq0). Priority:
    // explicit token arg (back-compat) > fresh token from getToken callback >
    // last-known token (fallback if a one-off fetch fails). Fetching fresh on
    // every (re)connect is what fixes the tokenless reconnect 403 and covers
    // Firebase ID token expiry.
    let resolvedToken = token;
    if (!resolvedToken && this.getToken) {
      try {
        resolvedToken = await this.getToken();
      } catch (error) {
        console.warn('[WebFormConnection] getToken failed, falling back to last-known token', error);
      }
    }
    if (!resolvedToken) {
      resolvedToken = this.lastToken;
    }
    if (resolvedToken) {
      this.lastToken = resolvedToken;
    }

    // Strip any token already baked into the URL (e.g. a stale token from a
    // previously-stored connectedUrl) before appending the freshly-resolved one,
    // so we never send two token params or a stale one. stripToken handles the
    // token appearing first, middle, last, or alone without leaving a dangling
    // or doubled separator (it does NOT rely on the strip being unreachable).
    const baseUrl = stripToken(wsUrl);

    // Append the resolved token to the URL
    let finalUrl = baseUrl;
    if (resolvedToken) {
      const separator = baseUrl.includes('?') ? '&' : '?';
      finalUrl = `${baseUrl}${separator}token=${resolvedToken}`;
    }

    // Clear idle timeout flag on reconnect (user manually clicked reconnect)
    if (this.idleTimedOut) {
      console.log('[WebFormConnection] 🔄 Clearing idle timeout flag for manual reconnect');
      this.idleTimedOut = false;
    }

    // Store the token-LESS base URL (bd polyglot-pdf-wq0). attemptReconnect()
    // reconnects via this.connectedUrl; storing the base (not finalUrl) means the
    // reconnect re-resolves a fresh token rather than replaying a stale one, and
    // never depends on stripToken to undo a baked-in token.
    this.connectedUrl = baseUrl;

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
        this.ws = new WebSocket(finalUrl);

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

        this.ws.onclose = (event) => {
          clearTimeout(timeout);
          this.handleClose(event);
        };
      } catch (error) {
        clearTimeout(timeout);
        this.handleError(error as Error);
        reject(error);
      }
    });
  }

  /**
   * Register a callback that returns a fresh auth token (bd polyglot-pdf-wq0).
   * connect() invokes this before every (re)connect so reconnects and long
   * sessions always carry a valid, non-expired Firebase ID token.
   */
  setGetToken(getToken: () => Promise<string | undefined>): void {
    this.getToken = getToken;
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

    // Reset the unconfirmable-field loop-breaker on every (re)connect so a counter
    // left mid-window before a drop does not false-trip on the first confirm of the
    // new session (bd polyglot-pdf-0y7, fresh-eyes PR #113).
    this.lastUnconfirmableFieldId = null;
    this.unconfirmableConfirmCount = 0;
    this.unconfirmableRepromptCount = 0;

    // Enable auto-reconnect after first successful connection
    this.enableAutoReconnect = true;

    // Skip automatic handshake during section switches (startSection will send it)
    if (this.isSectionSwitching) {
      return;
    }

    // Send handshake with schema + current_values + fill_language
    const handshake = SchemaFormStateManager.getHandshakePayload(this.state, this.fillLanguage);
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

        case "get_field_value":
          this.handleGetFieldValueRequest(message);
          break;

        case "complete_section":
          // DEPRECATED: Section completion now auto-detected after field confirmation
          // Gemini no longer calls complete_section tool - frontend detects when
          // all fields are confirmed and auto-switches to next section
          console.warn('[WebFormConnection] Received deprecated complete_section message');
          break;

        case "confirm_field":
          this.handleConfirmFieldRequest(message);
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

        case "idle_timeout":
          // Backend is closing connection due to inactivity
          // Set flag to prevent auto-reconnect, require manual reconnect
          console.log('[WebFormConnection] ⏱️ Idle timeout received from backend:', message);
          this.idleTimedOut = true;
          this.setStatus("idle_timeout");
          // WebSocket will close shortly, handleClose() will see idleTimedOut flag
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
    const { session_id, ephemeral, jit_mode_enabled, native_vad } = message;

    // Update state with session ID
    this.state = SchemaFormStateManager.setSessionId(this.state, session_id);

    // Enable JIT mode if backend supports it
    if (jit_mode_enabled !== undefined) {
      this.state = SchemaFormStateManager.setJitMode(this.state, jit_mode_enabled);
      if (jit_mode_enabled) {
        console.log('[WebFormConnection] ✅ JIT mode enabled by backend');
      }
    }

    // Native-VAD mode (bd polyglot-pdf-333): tell the connection/audio layer
    // whether Gemini's own VAD is driving turns. Fire BEFORE onSessionReady so
    // the audio layer is configured before any connected-state effects run.
    // Default to false (manual VAD) when the backend doesn't send the field.
    if (this.callbacks.onNativeVadMode) {
      this.callbacks.onNativeVadMode(native_vad === true);
    }

    this.setStatus("connected");

    // Check if this is a reconnect (disclaimer already accepted)
    if (this.state.disclaimerAccepted && this.state.selectedLanguage) {
      // Auto-send language message to trigger initiating prompt (skip disclaimer)
      const nextFieldHint = this.computeNextFieldHintString();
      if (nextFieldHint) {
        this.send({
          type: 'change_spoken_language',
          spoken_language: this.state.selectedLanguage,
          next_field_hint: nextFieldHint
        });
        console.log('[WebFormConnection] ✅ Auto-sent language message for reconnect:', this.state.selectedLanguage);
      }
    }

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
    const lockedFields: Array<{ fieldId: string; field: any; reason: string }> = [];

    for (const [displayName, value] of Object.entries(updates)) {
      // Find field by display name
      const field = this.state.schema.fields.find(
        (f) => f.name === displayName || f.id === displayName
      );

      if (field) {
        // Check if field is locked/hidden due to dependencies (Nov 22, 2025)
        const isAvailable = !field.hidden && shouldShowField(field, this.state.fieldValues);

        if (!isAvailable) {
          // Field is locked - collect dependency info for error message
          const { availability, lockedReason } = evaluateFieldAvailability(
            field,
            this.state.fieldValues,
            this.state.schema
          );

          lockedFields.push({
            fieldId: field.id,
            field,
            reason: lockedReason || `The field '${field.spoken_name || field.name}' is not available yet.`
          });

          console.warn(`[WebFormConnection] ❌ Field ${field.id} is locked:`, lockedReason);
          continue; // Skip applying this update
        }

        // AI fills field as UNCONFIRMED - requires explicit confirmation via confirm_field tool
        this.updateField(field.id, value as any, { confirmed: false, emit: false });
        updatedFields.push({ fieldId: field.id, value });
      } else {
        // Field not found in schema - ignore
      }
    }

    // If any fields were locked, send error message back to backend/Gemini
    if (lockedFields.length > 0) {
      const errorMessages = lockedFields.map(lf =>
        `Cannot update '${lf.field.spoken_name || lf.field.name}': ${lf.reason}`
      );

      console.error('[WebFormConnection] Dependency errors:', errorMessages);

      // Send dependency error back to backend so it can inform Gemini
      this.send({
        type: 'dependency_error',
        locked_fields: lockedFields.map(lf => ({
          field_id: lf.fieldId,
          spoken_name: lf.field.spoken_name || lf.field.name,
          reason: lf.reason
        })),
        message: errorMessages.join('; ')
      });
    }

    // Notify callback
    if (this.callbacks.onFieldUpdate && updatedFields.length > 0) {
      this.callbacks.onFieldUpdate(updatedFields);
    }
  }

  private handleFormUpdated(message: any): void {
    const data = (message && message.data) || {};
    const formState = data.form_state || {};
    const applied = data.applied_fields || {};
    const requestNextFieldHint = data.request_next_field_hint || false;
    const requestId = data.request_id;
    const nextFieldSchema = data.next_field_schema; // JIT mode: backend sends next field schema

    if (!formState || typeof formState !== "object") {
      return;
    }

    // Handle JIT mode: mark next field as loaded if schema provided
    if (nextFieldSchema && nextFieldSchema.id) {
      this.state = SchemaFormStateManager.markFieldSchemaLoaded(this.state, nextFieldSchema.id);
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

      const currentValue = this.state.fieldValues[field.id]?.value;
      const shouldUpdate = isApplied || !Object.is(currentValue, value);
      if (!shouldUpdate) {
        continue;
      }

      // AI fills field as UNCONFIRMED - requires explicit confirmation via confirm_field tool
      this.updateField(field.id, value as any, { confirmed: false, emit: false });
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

        const currentValue = this.state.fieldValues[field.id]?.value;
        const shouldUpdate = isApplied || !Object.is(currentValue, value);
        if (!shouldUpdate) {
          continue;
        }

        // Validate field before updating (only for AI-applied updates)
        // Note: Frontend validation temporarily disabled - backend handles validation
        // if (isApplied) {
        //   const validationError = validateField(field, value);
        //   if (validationError) {
        //     console.warn(`[WebFormConnection] Validation failed for ${field.id}:`, validationError);
        //     continue; // Skip this field update
        //   }
        // }

        // AI fills field as UNCONFIRMED - requires explicit confirmation via confirm_field tool
        this.updateField(field.id, value as any, { confirmed: false, emit: false });
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
      for (const [fieldId, fieldValue] of Object.entries(this.state.fieldValues)) {
        fieldValues[fieldId] = {
          value: fieldValue.value,
          confirmed: fieldValue.confirmed,
        };
      }
    } else {
      // Return only requested fields
      for (const fieldId of requestedFieldIds) {
        let fieldValue = this.state.fieldValues[fieldId];

        // Fallback: Try with [] appended if not found (Gemini sometimes drops the [])
        if (!fieldValue && !fieldId.endsWith('[]')) {
          fieldValue = this.state.fieldValues[fieldId + '[]'];
        }

        // Fallback: Try without [] if not found (in case query has [] but state doesn't)
        if (!fieldValue && fieldId.endsWith('[]')) {
          fieldValue = this.state.fieldValues[fieldId.slice(0, -2)];
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
      if (this.callbacks.onNextField) {
        this.callbacks.onNextField(null);
      }
      return null;
    }

    // Compute next field to fill
    const nextField = computeNextField(this.state, { skipConfirmed: true });

    if (!nextField) {
      if (this.callbacks.onNextField) {
        this.callbacks.onNextField(null);
      }
      return null;
    }

    // Notify UI about the next field (for highlighting/scrolling)
    if (this.callbacks.onNextField) {
      this.callbacks.onNextField(nextField.id);
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
  /**
   * Handle prepare_section_switch request from backend (new backend-side reconnect pattern)
   */
  private handlePrepareSectionSwitchRequest(message: any): void {
    const requestId = message.request_id;
    const identifier = message.identifier;

    console.log('[WebFormConnection] handlePrepareSectionSwitchRequest START', { requestId, identifier });

    try {
      const currentState = SchemaFormStateManager.load();
      console.log('[WebFormConnection] Loaded state', { hasState: !!currentState, hasParts: !!currentState?.schema.parts });

      if (!currentState || !currentState.schema.parts) {
        // Send error response
        console.log('[WebFormConnection] No state/parts, sending null response');
        this.send({
          type: "section_info_response",
          request_id: requestId,
          section_info: null,
        });
        return;
      }

      // Parse identifier - try multiple strategies
      // CRITICAL: identifier is a SECTION order (1-16 for I-90), not a PART order (1-8)
      let targetSectionId: string | null | undefined;

      if (typeof identifier === 'number') {
        // Find section by order number
        const section = currentState.schema.sections.find(s => s.order === identifier);
        targetSectionId = section?.id;
      } else if (typeof identifier === 'string') {
        const parsed = parseInt(identifier, 10);
        if (!isNaN(parsed)) {
          // Numeric string - find section by order
          const section = currentState.schema.sections.find(s => s.order === parsed);
          targetSectionId = section?.id;
        } else {
          // Try exact label match first
          targetSectionId = SchemaFormStateManager.findSectionByLabel(currentState, identifier);

          // If not found, try fuzzy matching (e.g., "Section 2" -> section with order 2)
          if (!targetSectionId) {
            const sectionMatch = identifier.match(/section\s+(\d+)/i);
            if (sectionMatch) {
              const sectionNum = parseInt(sectionMatch[1], 10);
              const section = currentState.schema.sections.find(s => s.order === sectionNum);
              targetSectionId = section?.id;
              console.log('[WebFormConnection] Fuzzy matched "' + identifier + '" to section order', sectionNum);
            }
          }
        }
      }

      console.log('[WebFormConnection] Parsed target section ID:', targetSectionId);

      if (!targetSectionId) {
        console.log('[WebFormConnection] Invalid target identifier, sending error with available sections');

        // Build list of available sections for error message
        const availableSections = currentState.schema.sections?.map(s =>
          `${s.order}: ${s.label}`
        ).join(', ') || 'none';

        this.send({
          type: "section_info_response",
          request_id: requestId,
          section_info: null,
          error: `Section '${identifier}' not found. Available sections: ${availableSections}`
        });
        return;
      }

      // Switch to target section in local state (no disconnect!)
      console.log('[WebFormConnection] Switching to section', targetSectionId);
      const updatedState = SchemaFormStateManager.switchToSection(currentState, targetSectionId);
      this.state = updatedState;

      // Get section schema and values
      console.log('[WebFormConnection] Building section schema and values');
      const sectionSchema = SchemaFormStateManager.extractSectionFields(updatedState.schema, targetSectionId);
      const sectionFieldIds = new Set(sectionSchema.fields.map((f: any) => f.id));
      const sectionValues: Record<string, any> = {};

      for (const [fieldId, fieldValue] of Object.entries(updatedState.fieldValues)) {
        if (sectionFieldIds.has(fieldId)) {
          sectionValues[fieldId] = fieldValue;
        }
      }

      // Build previous spoken names from completed sections
      console.log('[WebFormConnection] Building previous spoken names');
      const previousSpokenNames = SchemaFormStateManager.getPreviousSpokenNames(updatedState);

      // Compute initial field hint
      console.log('[WebFormConnection] Computing initial field hint');
      const initialFieldHint = this.computeNextFieldHintString();

      // Store last field hint for recovery prompts
      if (initialFieldHint) {
        sessionStorage.setItem('vff_last_field_hint', initialFieldHint);
      }

      // Get section metadata
      const currentSection = updatedState.schema.sections.find(s => s.id === targetSectionId);

      console.log('[WebFormConnection] Sending section_info_response', {
        requestId,
        sectionNumber: currentSection?.order,
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
            section_id: currentSection?.id,
            section_number: currentSection?.order ?? 1,
            total_sections: updatedState.schema.sections.length,
            section_label: currentSection?.label || '',
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
    // Now trigger UI update to show the new section
    if (this.callbacks.onSectionChanged) {
      this.callbacks.onSectionChanged();
    }

    // Also save the updated state
    SchemaFormStateManager.save(this.state);
  }

  /**
   * Phase 3: Handle get_field_value request from backend (AI tool call)
   */
  private handleGetFieldValueRequest(message: any): void {
    const requestId = message.request_id;
    const spokenName = message.spoken_name;

    try {
      const currentState = SchemaFormStateManager.load();
      if (!currentState) {
        this.sendFieldValueResponse(requestId, null, false);
        return;
      }

      // Lookup field ID by spoken name (searches current + completed parts)
      const fieldId = SchemaFormStateManager.getFieldBySpokenName(currentState, spokenName);

      if (!fieldId) {
        // Field doesn't exist in schema
        this.sendFieldValueResponse(requestId, null, false);
        return;
      }

      // Field exists - get value from fieldValues
      const fieldValue = currentState.fieldValues[fieldId];

      if (fieldValue && fieldValue.value !== undefined && fieldValue.value !== null && String(fieldValue.value).trim() !== '') {
        // Field has a value
        this.sendFieldValueResponse(requestId, fieldValue.value, true);
      } else {
        // Field exists but is empty/unfilled - send found=true with null value
        // This lets backend distinguish "field exists but empty" from "field doesn't exist"
        this.sendFieldValueResponse(requestId, null, true);
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
   * DEPRECATED: Phase 3 complete_section handling (no longer used)
   *
   * Section completion is now auto-detected in handleConfirmFieldRequest()
   * when computeNextField() returns null (all fields confirmed).
   *
   * Kept for reference but no longer called.
   */
  // private async handleCompleteSectionRequest(message: any): Promise<void> { ... }

  /**
   * Handle confirm_field request from backend (Gemini called confirm_field tool)
   */
  private async handleConfirmFieldRequest(message: any): Promise<void> {
    const { field_id, confirmation_method } = message;

    console.log('[WebFormConnection] Confirming field:', field_id, 'method:', confirmation_method);

    // Loop-breaker (bd polyglot-pdf-0y7): a field is only meaningfully confirmable
    // when it has a usable value. confirmField() no-ops when there is no fieldValues
    // entry at all, but it would ALSO "succeed" (set confirmed:true) on an entry that
    // exists with an empty/null value -- which both lets an empty field count as done
    // AND hides the very loop we are guarding against. So we gate on the VALUE, not on
    // confirmField()'s confirmed flag: if the field has no usable value, the confirm
    // cannot make progress, computeNextField() keeps returning the SAME field, and the
    // backend re-requests it forever (a tight confirm/next-field-hint spin that strands
    // the session and silences Gemini). Detect that, do not record a bogus confirmation,
    // and re-prompt Gemini to collect the value.
    const fieldValue = this.state.fieldValues[field_id]?.value;
    const hasUsableValue =
      fieldValue !== null && fieldValue !== undefined && fieldValue !== '';

    if (!hasUsableValue) {
      if (field_id === this.lastUnconfirmableFieldId) {
        this.unconfirmableConfirmCount += 1;
      } else {
        this.lastUnconfirmableFieldId = field_id;
        this.unconfirmableConfirmCount = 1;
        this.unconfirmableRepromptCount = 0;
      }

      console.warn(
        '[WebFormConnection] confirm_field cannot take (no usable value):',
        field_id,
        'consecutive attempts:',
        this.unconfirmableConfirmCount
      );

      // Re-prompt Gemini each time the per-reprompt window fills, but only up to a
      // hard cap. Resetting the per-window counter (not the field id) means the
      // re-prompt is rate-limited rather than fired on every request; capping the
      // total re-prompts means a field Gemini simply cannot fill stops spinning
      // entirely instead of re-prompting forever at half speed (fresh-eyes PR #113).
      if (
        this.unconfirmableConfirmCount >= WebFormConnection.UNCONFIRMABLE_CONFIRM_LIMIT &&
        this.unconfirmableRepromptCount < WebFormConnection.UNCONFIRMABLE_REPROMPT_CAP
      ) {
        const field = this.state.schema.fields.find(f => f.id === field_id);
        const spokenName = field?.spoken_name || field?.name || field_id;
        this.unconfirmableConfirmCount = 0;
        this.unconfirmableRepromptCount += 1;
        const capped =
          this.unconfirmableRepromptCount >= WebFormConnection.UNCONFIRMABLE_REPROMPT_CAP;
        console.error(
          '[WebFormConnection] Breaking confirm/next-field loop for unconfirmable field:',
          field_id,
          capped ? '(final re-prompt -- giving up after this)' : ''
        );
        // Re-prompt Gemini (via send_prompt) to collect the value rather than
        // confirming an empty field. completion_message -> send_prompt is wired and
        // works today (unlike recovery_prompt, which is broken backend-side until
        // bd polyglot-pdf-zy3 lands), so this is the channel that actually redirects
        // Gemini.
        this.send({
          type: 'completion_message',
          message:
            `The field '${spokenName}' has no value yet, so it cannot be confirmed. ` +
            `Do not call confirm_field for it again. Ask the user for the value, ` +
            `then call update_form_fields to fill it before confirming.`,
        });
        // Also surface the stall to the UI directly -- a belt-and-suspenders signal
        // that does not depend on Gemini acting on the prompt.
        this.callbacks.onError?.(new Error(
          `Could not confirm '${spokenName}' -- no value was entered. ` +
          `Please provide the value before confirming.`
        ));
      }
      return;
    }

    // Field has a usable value -- record the confirmation in state.
    this.state = SchemaFormStateManager.confirmField(
      this.state,
      field_id,
      confirmation_method === 'verbal' ? 'ai_voice' : 'manual_edit'
    );
    SchemaFormStateManager.save(this.state);

    // Confirm took -- clear any pending unconfirmable tracking for this field.
    if (field_id === this.lastUnconfirmableFieldId) {
      this.lastUnconfirmableFieldId = null;
      this.unconfirmableConfirmCount = 0;
      this.unconfirmableRepromptCount = 0;
    }

    // 🆕 AUTO-DETECT SECTION COMPLETION
    // Check if all fields in current section are now confirmed
    const nextField = computeNextField(this.state, { skipConfirmed: true });

    console.log('[WebFormConnection] 🔍 Section completion check:', {
      currentSectionId: this.state.currentSectionId,
      nextFieldInCurrentSection: nextField?.id || 'NONE',
      allFieldsConfirmed: nextField === null
    });

    if (!nextField) {
      // All fields in current section are confirmed!
      const nextSection = SchemaFormStateManager.getNextSection(this.state);

      console.log('[WebFormConnection] 🔍 Next section lookup:', {
        currentSectionId: this.state.currentSectionId,
        nextSectionId: nextSection?.id || 'NONE',
        nextSectionLabel: nextSection?.label || 'N/A'
      });

      if (nextSection) {
        console.log('[WebFormConnection] ✅ Section complete! Auto-switching to:', nextSection.id);

        // CRITICAL: Stop all audio processing immediately to prevent overlap with new session
        console.log('[WebFormConnection] 🛑 Stopping audio queue before section switch');
        this.audioQueue = []; // Clear any queued audio from old session
        this.isProcessingAudio = false; // Stop processing loop

        // Stop capturing user audio (will restart after section switch)
        if (this.callbacks.onStopCapture) {
          this.callbacks.onStopCapture();
        }

        // Trigger automatic section switch (uses backend-side reconnect)
        // Note: wsUrl parameter not used (kept for API compatibility)
        await this.switchToSection(nextSection.id, '');
      } else {
        console.log('[WebFormConnection] 🎉 Form complete!');
        // Notify UI that entire form is complete
        if (this.callbacks.onFormComplete) {
          this.callbacks.onFormComplete();
        }
      }
    }

    // Note: No acknowledgment needed - backend handles confirmation logging internally
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

    // Log first chunk and then every 100th chunk to reduce log spam
    if (this.audioChunkCount === 1) {
      console.log(`[WebFormConnection] 📥 First audio chunk received from server (${arrayBuffer.byteLength} bytes)`);
    } else if (this.audioChunkCount % 100 === 0) {
      console.log(`[WebFormConnection] 📥 Audio chunk #${this.audioChunkCount}`);
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
  private handleClose(event?: CloseEvent): void {
    // Log close details for debugging
    console.log('[WebFormConnection] 🔌 WebSocket closed', {
      code: event?.code,
      reason: event?.reason,
      wasClean: event?.wasClean,
      status: this.status,
      reconnectAttempts: this.reconnectAttempts,
      enableAutoReconnect: this.enableAutoReconnect,
      isSectionSwitching: this.isSectionSwitching,
      idleTimedOut: this.idleTimedOut
    });

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

    // Don't auto-reconnect if connection was closed due to idle timeout
    // User must manually click "Reconnect" button to resume
    if (this.idleTimedOut) {
      console.log('[WebFormConnection] ⏱️ Idle timeout - no auto-reconnect, user must manually reconnect');
      this.setStatus("idle_timeout");
      return;
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
      // Use the URL we successfully connected to (not the default localhost)
      if (this.connectedUrl) {
        this.connect(this.connectedUrl);
      } else {
        console.error('[WebFormConnection] Cannot reconnect - no connectedUrl stored');
        this.setStatus("disconnected");
      }
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

      // DEBUG: Log full details if type is undefined (suspicious message)
      if (message.type === undefined) {
        console.error('[WebFormConnection] ⚠️ SUSPICIOUS: Sending message without type!', {
          size: jsonStr.length,
          keys: Object.keys(message),
          preview: jsonStr.substring(0, 200),
          stack: new Error().stack
        });
      } else {
        console.log('[WebFormConnection] Sending JSON message', {
          type: message.type,
          size: jsonStr.length,
          readyState: this.ws.readyState,
          bufferedAmount: this.ws.bufferedAmount
        });
      }
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

    // Compute next field hint after this manual update
    const nextFieldHint = this.computeNextFieldHintString();

    this.send({
      type: 'manual_field_update',
      field_id: fieldId,
      field_name: fieldName,
      value: value,
      next_field_hint: nextFieldHint,  // Include next field guidance
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
  async sendActivityEnd(): Promise<void> {
    console.log(`[WebFormConnection] 📤 sendActivityEnd() called - WebSocket state: ${this.ws ? this.ws.readyState : 'null'} (OPEN=${WebSocket.OPEN})`)

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error(`[WebFormConnection] ❌ Cannot send activity_end - WebSocket not open (state: ${this.ws ? this.ws.readyState : 'null'})`)
      return;
    }

    // CRITICAL: Wait for all buffered audio to be sent before signaling activity_end
    // This ensures Gemini receives all audio chunks before we close the turn
    const bufferedBefore = this.ws.bufferedAmount;
    if (bufferedBefore > 0) {
      console.log(`[WebFormConnection] ⏳ Waiting for ${bufferedBefore} bytes of audio to drain before activity_end`)
      await this.waitForBufferDrain(2000); // Wait up to 2 seconds for audio to send
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
   * Update field value (user edit or AI fill)
   */
  updateField(
    fieldId: string,
    value: string | boolean | null,
    options?: { confirmed?: boolean; emit?: boolean }
  ): void {
    const confirmed = options?.confirmed;
    const emit = options?.emit ?? false;

    // Determine confirmation status and method
    // If confirmed is explicitly set (from AI), use 'ai_voice'
    // If not confirmed but emit is true (manual edit), auto-confirm with 'manual_edit'
    const isManualEdit = !confirmed && emit;
    const finalConfirmed = confirmed || isManualEdit;
    const confirmationMethod = confirmed ? 'ai_voice' : (isManualEdit ? 'manual_edit' : undefined);

    this.state = SchemaFormStateManager.updateField(this.state, fieldId, value, {
      confirmed: finalConfirmed,
      confirmationMethod: confirmationMethod
    });

    // Auto-scroll to field when Gemini fills it (confirmed = true means AI filled)
    if (confirmed && typeof document !== 'undefined') {
      // Use setTimeout to allow React to update DOM first
      setTimeout(() => {
        const element = document.getElementById(fieldId);
        if (element) {
          element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
            inline: 'nearest'
          });

          // Optional: Add a brief highlight effect to draw attention
          element.classList.add('field-highlight');
          setTimeout(() => {
            element.classList.remove('field-highlight');
          }, FIELD_HIGHLIGHT_DURATION_MS);
        }
      }, 50);
    }

    if (emit) {
      this.flushField(fieldId);
    }
  }

  flushField(fieldId: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return;
    }

    const fieldState = this.state.fieldValues[fieldId];
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
  getState(): SchemaFormState {
    return this.state;
  }

  /**
   * Get completion percentage
   */
  getCompletionPercentage(): number {
    return SchemaFormStateManager.getProgress(this.state);
  }

  /**
   * Clear state and disconnect
   */
  reset(): void {
    this.disconnect();
    SchemaFormStateManager.clear();
  }

  /**
   * Start a specific section (closes current session, starts new one)
   * @param sectionId - Section ID (e.g., "part_1_2_addresses")
   */
  async startSection(sectionId: string, wsUrl: string = "ws://localhost:8000/ws/fill"): Promise<void> {
    // bd polyglot-pdf-0y7: clear the confirm-loop failure streak on this section
    // transition too (the other path besides switchToSection -- called by
    // completeSection), so a stale count can't carry into the new section and trip
    // the breaker a cycle early on a same field_id.
    this.lastUnconfirmableFieldId = null;
    this.unconfirmableConfirmCount = 0;
    this.unconfirmableRepromptCount = 0;
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
      let currentState = SchemaFormStateManager.load();
      if (!currentState || !currentState.schema.sections) {
        throw new Error('Sections not initialized in schema');
      }

      // Find section by ID
      const targetSection = currentState.schema.sections.find(s => s.id === sectionId);
      if (!targetSection) {
        throw new Error(`Section with ID ${sectionId} not found`);
      }

      // Switch to target section
      currentState = SchemaFormStateManager.switchToSection(currentState, targetSection.id);
      this.state = currentState;

      // Get section schema and current values for this section
      const sectionSchema = SchemaFormStateManager.extractSectionFields(currentState.schema, targetSection.id);
      const sectionValues: Record<string, any> = {};

      // Filter fieldValues to only include fields in this section
      const sectionFieldIds = new Set(sectionSchema.fields.map((f: any) => f.id));
      for (const [fieldId, fieldValue] of Object.entries(currentState.fieldValues)) {
        if (sectionFieldIds.has(fieldId)) {
          sectionValues[fieldId] = fieldValue;
        }
      }

      // Build previous_spoken_names from completed sections
      const previousSpokenNames = SchemaFormStateManager.getPreviousSpokenNames(currentState);

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
        // Section metadata
        section_id: targetSection.id,
        section_number: targetSection.order,
        total_sections: currentState.schema.sections.length,
        section_label: targetSection.label,
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
   * Switch to a different section (backend-side reconnect pattern)
   *
   * Uses the backend-side Gemini reconnect pattern. The backend closes/recreates
   * the Gemini session with fresh context for the new section.
   *
   * @param sectionId - Section ID (e.g., "part_1_2_addresses")
   * @param wsUrl - Backend WebSocket URL (kept for API compatibility but not used)
   */
  async switchToSection(sectionId: string, wsUrl: string): Promise<void> {
    // bd polyglot-pdf-0y7: clear the confirm-loop failure streak on a section
    // switch so a stale count can't carry into the new section (e.g. a same
    // field_id in the next section would otherwise trip the breaker one cycle
    // early). The in-session auto-switch keeps the SAME WebSocket open (no
    // reconnect, so handleOpen's reset does not fire).
    this.lastUnconfirmableFieldId = null;
    this.unconfirmableConfirmCount = 0;
    this.unconfirmableRepromptCount = 0;

    const currentState = SchemaFormStateManager.load();
    if (!currentState || !currentState.schema.sections) {
      throw new Error('Sections not initialized');
    }

    // Find section by ID
    const targetSection = currentState.schema.sections.find(s => s.id === sectionId);
    if (!targetSection) {
      throw new Error(`Section not found: ${sectionId}`);
    }

    // Validate range
    if (targetSection.order < 1 || targetSection.order > currentState.schema.sections.length) {
      throw new Error(`Invalid section number: ${targetSection.order} (must be 1-${currentState.schema.sections.length})`);
    }

    // Wait for WebSocket send buffer to drain before sending control message
    // This prevents the control message from being queued behind audio frames
    console.log('[WebFormConnection] Waiting for buffer to drain before section switch');
    await this.waitForBufferDrain(1000);

    // Update status
    this.setStatus('switching_section');

    // Switch to target section in local state
    const updatedState = SchemaFormStateManager.switchToSection(currentState, sectionId);
    this.state = updatedState;

    // Reset the unconfirmable-field loop-breaker on a section switch (bd
    // polyglot-pdf-0y7). The in-session auto-switch keeps the SAME WebSocket open
    // (no reconnect, so handleOpen's reset does not fire), and a same-id field in
    // the next section must not inherit a stale failure streak.
    this.lastUnconfirmableFieldId = null;
    this.unconfirmableConfirmCount = 0;
    this.unconfirmableRepromptCount = 0;

    // Build section info to send to backend (avoid round-trip delay)
    const sectionSchema = SchemaFormStateManager.extractSectionFields(updatedState.schema, sectionId);
    const sectionFieldIds = new Set(sectionSchema.fields.map((f: any) => f.id));
    const sectionValues: Record<string, any> = {};

    for (const [fieldId, fieldValue] of Object.entries(updatedState.fieldValues)) {
      if (sectionFieldIds.has(fieldId)) {
        sectionValues[fieldId] = fieldValue;
      }
    }

    // Build previous spoken names from completed sections
    const previousSpokenNames = SchemaFormStateManager.getPreviousSpokenNames(updatedState);

    // Compute initial field hint
    const initialFieldHint = this.computeNextFieldHintString();

    console.log('[WebFormConnection] Sending section switch with embedded info', {
      sectionId: targetSection.id,
      sectionNumber: targetSection.order,
      fieldCount: sectionSchema.fields.length,
      valueCount: Object.keys(sectionValues).length
    });

    // Send section switch with all info embedded (no round-trip needed)
    this.send({
      type: "manual_section_switch",
      identifier: targetSection.id,
      section_info: {
        schema: sectionSchema,
        current_values: sectionValues,
        metadata: {
          section_id: targetSection.id,
          section_number: targetSection.order,
          total_sections: updatedState.schema.sections.length,
          section_label: targetSection.label,
          previous_spoken_names: previousSpokenNames,
        },
        initial_field_hint: initialFieldHint,
      },
    });
  }

  /**
   * Complete current section and move to next
   *
   * @param wsUrl - Backend WebSocket URL (REQUIRED - no default to prevent localhost fallback in production)
   */
  async completeSection(wsUrl: string): Promise<void> {
    if (!wsUrl) {
      throw new Error('wsUrl is required for completeSection - must pass the connected backend URL');
    }
    const currentState = SchemaFormStateManager.load();
    if (!currentState || !currentState.currentSectionId || !currentState.schema.sections) {
      throw new Error('Section state not initialized');
    }

    const currentSection = SchemaFormStateManager.getCurrentSection(currentState);
    if (!currentSection) {
      throw new Error('Current section not found');
    }

    // Mark section as complete
    const updatedState = SchemaFormStateManager.markSectionComplete(currentState, currentState.currentSectionId);
    this.state = updatedState;

    // Check if this was the last section
    if (currentSection.order >= currentState.schema.sections.length) {
      this.setStatus('connected'); // Stay connected but don't start new section
      return;
    }

    // Move to next section
    const nextSection = SchemaFormStateManager.getNextSection(updatedState);
    if (nextSection) {
      await this.startSection(nextSection.id, wsUrl);
    }
  }

  /**
   * Get current section ID
   */
  getCurrentSectionId(): string | undefined {
    const currentSection = SchemaFormStateManager.getCurrentSection(this.state);
    return currentSection?.id;
  }

  /**
   * Get completed section IDs
   */
  getCompletedSections(): Set<string> {
    return this.state.completedSections || new Set();
  }
}
