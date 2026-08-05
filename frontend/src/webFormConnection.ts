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
import type { FormSchema, FormField, ValidatorFinding } from "./schema-forms/types/schema";
import {
  computeNextField,
  formatNextFieldHint,
  getFieldOrder,
  isFormComplete
} from "./navigation";
import { getFieldSchema } from "./schema-forms/utils/manifestUtils";
import { shouldShowField, validateField, isFieldReadOnly } from "./schema-forms/utils/validation";
import { unwrapFieldValue, readFieldEntryWithAlias } from "./schema-forms/utils/fieldValue";
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

/**
 * Canonicalize an AI-supplied checkbox-group value to the client's one true
 * shape: string[] (bd polyglot-pdf-h76m.2).
 *
 * The backend prompt (config.py) tells Gemini "Multiple checkboxes:
 * comma-separated exact values", so the voice path delivers a checkbox-group
 * selection as ONE comma-joined STRING -- but everything downstream expects an
 * array: the interactive renderer stores string[], the conditional evaluator's
 * array branch is the reliable one, and /api/fill-pdf fills a group only from
 * a list (a raw string is rejected as checkbox_unsupported_value and the group
 * silently stays empty on the printed PDF). Splitting at the AI ingress makes
 * validation, storage, conditionals, and fill all see the same array.
 *
 * A "choice group" here is the v2 `checkbox_group` type, or (legacy shape) a
 * `type:"checkbox"` field WITH options (the renderer's own group rule --
 * CheckboxField renders options-bearing checkbox fields as a multi-select
 * storing string[]). A standalone boolean checkbox (no options) is never touched, and
 * non-string values (bool, array) pass through unchanged. Option values may
 * contain "/" but never "," (the schema contract forbids it; slugs later make
 * that structural), so comma is an unambiguous delimiter. A single no-comma
 * selection becomes a one-element array -- as a bare string it would fail PDF
 * fill exactly like the multi-select case.
 *
 * Boolean-INTENT strings ("true"/"false", the literal forms the backend tool
 * contract documents for a standalone checkbox) are excluded from the split:
 * they are not option selections, and wrapping them into a one-element array
 * would misrepresent a boolean-shaped value as a group selection (a standalone
 * checkbox that carries a single-widget options array would otherwise have its
 * "true" turned into ["true"]). They pass through untouched, matching the
 * backend filler's own boolean-string handling.
 */
export function canonicalizeAiCheckboxGroupValue(field: FormField, value: any): any {
  const isChoiceGroup =
    field.type === "checkbox_group" ||
    (field.type === "checkbox" && (field.options?.length ?? 0) > 0);
  if (!isChoiceGroup) return value;

  const raw = unwrapFieldValue(value);
  if (typeof raw !== "string") return value;
  if (/^(true|false)$/i.test(raw.trim())) return value;

  return raw
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part !== "");
}

export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "switching_section"
  | "reconnecting"
  | "idle_timeout"
  // Auto-reconnect ran out of attempts (or could not run) on an UNEXPECTED
  // drop -- a terminal, non-self-healing failure that needs an explicit user
  // action to recover. Distinct from "disconnected" (which also covers the
  // intentional/transient cases) so the UI can surface the connection-timeout
  // modal only on genuine give-up, not on every blip (bd polyglot-pdf-jf6w.3).
  | "reconnect_failed"
  | "error";

export interface ConnectionCallbacks {
  onStatusChange?: (status: ConnectionStatus) => void;
  // "Thinking" indicator (bd polyglot-pdf-wpw.5): true from the moment the user's
  // turn ends (activity_end / VAD turn-end) until the agent's first response audio
  // of that turn arrives -- the processing gap during which the app would otherwise
  // look frozen (esp. on a slow secretary lookup). Orthogonal to ConnectionStatus
  // (the connection stays "connected" throughout), so it is a SEPARATE boolean
  // signal, not a status value -- folding it into status would collide with the
  // many `status === "connected"` gates. The UI shows a calm animated indicator
  // while true. Guaranteed to clear (first-audio / turn_complete / error /
  // disconnect / section-switch / max-duration safety) so it can never stick on.
  onThinkingChange?: (thinking: boolean) => void;
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
  // The Gemini Live server sent a GoAway: it is about to terminate this
  // connection (bd polyglot-pdf-c5t). timeLeft is a duration string (may be
  // null). The handler can pre-emptively reconnect before the abrupt close; the
  // reconnect POLICY is intentionally left to the consumer (see bd follow-on).
  onGoAway?: (timeLeft: string | null) => void;
  // Gemini interrupted the current generation (user barge-in, bd
  // polyglot-pdf-s7uf). The consumer should drain any locally scheduled
  // playback (audioManager.resetPlaybackClock) so the user stops hearing the
  // dead generation's tail; the staging audioQueue here is cleared before this
  // fires (TWO queues exist -- clearing one leaves ghost audio in the other).
  onInterrupted?: () => void;
  // UI lifecycle hooks fired during the auto-switch at section completion: stop
  // mic capture just before the section switch, and signal the whole form is
  // done. Both are optional and defensively guarded at the call sites (no
  // consumer wires them today; they are the seam for an overlay that wants to
  // react to those transitions).
  onStopCapture?: () => void;
  onFormComplete?: () => void;
}

// Max-duration safety for the "thinking" indicator (bd polyglot-pdf-wpw.5): if no
// response audio arrives within this window after the user's turn ends, clear the
// indicator anyway so it can never stick on. Generous enough to cover a slow
// secretary lookup's tail (Gate 2 saw up to ~20s) plus headroom.
const THINKING_MAX_MS = 30000;

// B5 (bd polyglot-pdf-jnjj.17): the parked validator switch-gate (see
// proceedSectionSwitch). Named so the local `gate` object's type does not collapse to
// `never` after an early-return narrows the instance field to null (Codex PR #275).
interface PendingSectionSwitch {
  sectionId: string;
  resolve: () => void;
  timer: ReturnType<typeof setTimeout>;
  cancelled: boolean;
}

export class WebFormConnection {
  private ws: WebSocket | null = null;
  private state: SchemaFormState;
  private callbacks: ConnectionCallbacks;
  private status: ConnectionStatus = "disconnected";
  // "Thinking" indicator state (bd polyglot-pdf-wpw.5). `thinking` is the current
  // value (mirrored to onThinkingChange via setThinking). `thinkingTurnActive`
  // gates the first-audio CLEAR: audioChunkCount is session-cumulative (never
  // reset), so it cannot mark "first audio of THIS turn" -- instead we arm this
  // flag when the user's turn ends and clear thinking on the first audio frame
  // seen WHILE it is armed. `thinkingTimer` is the max-duration safety: thinking
  // auto-clears after THINKING_MAX_MS so a turn that never produces audio (a
  // dropped/empty reply) can't leave the indicator stuck on.
  private thinking = false;
  private thinkingTurnActive = false;
  private thinkingTimer: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private reconnectTimer: number | null = null;
  // GoAway pre-emptive-reconnect once-guard (bd polyglot-pdf-l3a.2). Set while a
  // GoAway-driven reconnect is being driven by handleGoAwayReconnect so that (a) a
  // burst of go_away messages coalesces into a SINGLE reconnect, and (b) the
  // intentional socket close we perform to reconnect is not double-handled by
  // handleClose's auto-reconnect (this flag drives the reconnect ourselves, like
  // isSectionSwitching does for a section switch). Cleared once the new socket
  // opens (handleOpen) or the reconnect attempt fails.
  private goAwayReconnectInFlight = false;
  // True while the CURRENT reconnect was triggered by a SPONTANEOUS Gemini drop
  // (gemini_session_dropped / 1011), as opposed to an ordinary WS blip that
  // attemptReconnect also drives (bd polyglot-pdf-ppfy). Both collapse to the
  // "reconnecting" status, but only a Gemini drop should surface the "having
  // trouble reaching the AI" modal -- a plain network reconnect must stay silent
  // (it is not an AI problem). Set in the gemini_session_dropped handler ONLY when
  // handleGoAwayReconnect actually STARTS a reconnect (not when it coalesces into
  // an in-flight one -- else it would leak `true` and misfire the modal on a later
  // blip; two independent fresh-eyes reviews). Cleared in setStatus only on a
  // SETTLED status (connected / reconnect_failed / error / idle_timeout /
  // disconnected) -- NOT on the intermediate "connecting" a backoff-driven reopen
  // passes through, else the modal would vanish mid-recovery -- AND explicitly in
  // handleSessionReady. Read by the overlay to gate the modal. (fresh-eyes: the bare "reconnecting"
  // status is NOT unique to the drop path.)
  private droppedReconnectInFlight = false;
  private audioQueue: ArrayBuffer[] = [];
  private audioChunkCount = 0; // Track audio chunks for logging
  private isProcessingAudio = false;
  private enableAutoReconnect = false; // Only enable after first successful connection
  private dtiModeEnabled = false; // DTI: send next field's full schema on hint response (bd polyglot-pdf-jnjj.22)
  private continuousSessionEnabled = false; // Whole form as ONE session; suppress section advance (bd polyglot-pdf-x8rt)
  private isSectionSwitching = false; // Prevent auto-reconnect during intentional section switches
  // Real re-entrancy guard for a section switch, DISTINCT from isSectionSwitching
  // (bd polyglot-pdf-aun / WS-D). isSectionSwitching is the auto-reconnect
  // suppressor and is cleared the instant the new socket opens; it does NOT
  // protect against a SECOND switch starting before the first finished, nor does
  // it survive long enough to gate the post-open handshake window. switchInFlight
  // is set for the WHOLE switch (until the new section is confirmed, errors, or
  // the watchdog fires) and released in finally, so a concurrent
  // startSection/switchToSection is rejected instead of racing two reconnects.
  private switchInFlight = false;
  // Watchdog: if a switch neither confirms (section_switched) nor errors within
  // this window, surface `error` instead of a stuck `switching_section` forever.
  private sectionSwitchWatchdog: number | null = null;
  private static readonly SECTION_SWITCH_TIMEOUT_MS = 15000;
  private connectedUrl: string = ''; // Track the URL we're connected to (for section switches/reconnects)
  private idleTimedOut: boolean = false; // Track if connection was closed due to idle timeout
  // Set to true after the first successful handleOpen so that subsequent opens
  // (auto-reconnects) include resume:true in the handshake (bd polyglot-pdf-vmxx).
  private hasConnectedOnce: boolean = false;

  // Loop-breaker for unconfirmable fields (bd polyglot-pdf-0y7). When the backend
  // asks to confirm_field a field that has no usable value, the confirm cannot make
  // progress, so computeNextField() keeps returning the SAME field and the backend
  // re-requests it forever (a tight confirm/next-field-hint loop that strands the
  // session). Two layers cap the re-prompts so the model cannot spin the session:
  //   1. PER-FIELD: count CONSECUTIVE failed confirms of the same field and, every
  //      CONFIRM_LIMIT attempts, re-prompt Gemini to collect the value -- up to a
  //      hard REPROMPT_CAP, after which we stop re-prompting for that field
  //      (fresh-eyes PR #113). The per-field counters reset when a DIFFERENT field is
  //      tried (the streak is per-field), so under cross-field alternation the
  //      per-field cap does NOT bound the total -- layer 2 does.
  //   2. SESSION-WIDE (bd polyglot-pdf-r2hy, mirroring the wpw.3 validation-reject
  //      cap): because the per-field counter resets on every field change, a model
  //      alternating confirm_field calls between DIFFERENT empty fields (A empty ->
  //      B empty -> A empty ...) would re-arm the per-field re-prompt each switch and
  //      prompt forever. So a separate counter -- NOT reset on a field change, only on
  //      (re)connect / section switch / a successful confirm -- caps the TOTAL
  //      re-prompts per session at SESSION_CAP. This is the real bound on cross-field
  //      confirm spin; the per-field cap only shapes the cadence within one field.
  // All counters reset on a successful confirm and on (re)connect / section switch
  // (resetUnconfirmableTracking).
  private lastUnconfirmableFieldId: string | null = null;
  private unconfirmableConfirmCount = 0;
  private unconfirmableRepromptCount = 0;
  private unconfirmableSessionPromptCount = 0;
  private static readonly UNCONFIRMABLE_CONFIRM_LIMIT = 2;
  private static readonly UNCONFIRMABLE_REPROMPT_CAP = 3;
  private static readonly UNCONFIRMABLE_SESSION_CAP = 6;

  // W2 (bd polyglot-pdf-kxkw): the async-validator STRIDE window builder knobs.
  // Windows are size-VALIDATOR_WINDOW_SIZE ranges over the schema field order,
  // starting every VALIDATOR_WINDOW_STRIDE fields (so window k covers indices
  // [k*stride, k*stride + size)). Overlap (stride < size) means one contradiction
  // can surface in multiple windows; the backend dedupes by field-id set (W1).
  // Defaults 20 / 10 per the sprint-12 plan; kept as constants (no runtime knob
  // needed today -- promote to config if a form ever needs different sizing).
  private static readonly VALIDATOR_WINDOW_SIZE = 20;
  private static readonly VALIDATOR_WINDOW_STRIDE = 10;

  // B4 (bd polyglot-pdf-jnjj.16): once-only guard for the proactive form_complete
  // event. Holds a serialization of the whole-form confirmed values at the last
  // form_complete emit. The guard is on the COMPLETED STATE + a dirty-since-last-
  // emit check (validation-delegation.md contract 4), NOT a fire-once latch: a
  // post-completion manual edit changes this snapshot, so the form re-validates
  // once on the complete -> edit -> complete cycle, while a static complete form
  // never re-fires. null = "no form_complete emitted yet this (re)connect"; reset
  // to null on (re)connect / section switch so a reconnect into a complete form
  // re-validates once.
  private formCompleteSnapshot: string | null = null;

  // W3 (bd polyglot-pdf-pr3i): a single drain_findings may be in flight at a time.
  // Overlapping stride windows can each surface a DIFFERENT contradiction in quick
  // succession; without this guard each validation_result would fire its own
  // drain_findings carrying the FULL queue snapshot, so the earlier finding gets
  // voiced twice (the fresh-eyes race). We drain ONE batch, wait for its
  // drain_findings_result (which consumes the delivered findings), then re-drain if
  // the queue still has anything. Reset on (re)connect so a drop mid-drain re-arms.
  private drainInFlight: boolean = false;

  // B5 (bd polyglot-pdf-jnjj.17): the validator switch-gate. When the section-
  // complete boundary fires, proceedSectionSwitch PAUSES the auto-advance and parks
  // the pending switch here until a validation_result arrives (clean -> resume) or
  // the fail-OPEN timer elapses (validation-delegation.md contract 4: never block on
  // a validator outage). `resolve` runs the parked switch exactly once; `timer`
  // backstops a validation_result that never arrives (socket drop). A CONFLICT
  // verdict cancels the switch (clears both without switching) so the user stays in
  // the section to resolve it; the switch happens on a later clean boundary.
  // `cancelled` rides the gate object (not a shared instance flag) so a conflict /
  // teardown / eviction marks THE SPECIFIC parked gate -- a stale gate evicted by a
  // newer boundary can never make the newer switch fire (each invocation reads its
  // OWN object's flag after the await).
  private pendingSectionSwitch: PendingSectionSwitch | null = null;
  // Fail-OPEN bound (contract 4): advance unchecked if no verdict in this window.
  private static readonly VALIDATOR_GATE_TIMEOUT_MS = 6000;

  // Loop-breaker for AI-applied values that FAIL client-side validation
  // (bd polyglot-pdf-wpw.3). When the model fills a field with a value that violates
  // its schema (a non-existent enum option, a malformed SSN/A-Number, a too-long
  // string), we refuse to apply it -- the client owns field state, so an invalid
  // value must never land -- and send a corrective prompt back to the model so it
  // re-asks the user in-band. Two layers cap those prompts so the model cannot spin
  // the session:
  //   1. PER-FIELD (mirrors the unconfirmable loop-breaker above): count CONSECUTIVE
  //      rejects of the SAME field; prompt on the first reject and thereafter on
  //      every count divisible by REJECT_LIMIT, up to REJECT_REPROMPT_CAP -- with
  //      LIMIT=2/CAP=3 that fires at rejects #1, #2, #4 then silence WHILE THE SAME
  //      FIELD KEEPS FAILING CONSECUTIVELY. Resets when the tracked field validates
  //      OR when a DIFFERENT field is rejected (the streak is per-field), so under
  //      cross-field alternation the per-field cap does NOT bound the total -- layer
  //      2 does. (Do not rely on the per-field cap alone; see layer 2.)
  //   2. SESSION-WIDE (Codex PR #145): because the per-field counter resets on every
  //      field change, a model bouncing invalid values BETWEEN fields (A bad -> B bad
  //      -> A bad ...) would re-arm the per-field prompt each switch and prompt
  //      forever. So a separate counter -- NOT reset on a field change -- caps the
  //      TOTAL corrective prompts per session at REJECT_SESSION_CAP. Once hit, we
  //      stop prompting regardless of field. This is the real bound on cross-field
  //      spin; the per-field cap only shapes the cadence within one field's streak.
  // Both layers reset on (re)connect and section switch (resetValidationRejectTracking),
  // and when the STUCK field (the one currently being rejected) finally validates --
  // genuine progress on the failing thing restores the budget, but an unrelated
  // success does NOT (else [bad-A, good-B] alternation would reset the cap forever;
  // fresh-eyes round 4).
  // The corrective message carries only the field's spoken name + the schema
  // constraint -- NEVER the rejected value (PII-safe, the p84m principle).
  private lastValidationRejectFieldId: string | null = null;
  private validationRejectCount = 0;
  private validationRejectRepromptCount = 0;
  private validationRejectSessionPromptCount = 0;
  private static readonly VALIDATION_REJECT_LIMIT = 2;
  private static readonly VALIDATION_REJECT_REPROMPT_CAP = 3;
  private static readonly VALIDATION_REJECT_SESSION_CAP = 6;

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
      console.log('[WebFormConnection] [reconnect] Clearing idle timeout flag for manual reconnect');
      this.idleTimedOut = false;
    }

    // Store the token-LESS base URL (bd polyglot-pdf-wq0). attemptReconnect()
    // reconnects via this.connectedUrl; storing the base (not finalUrl) means the
    // reconnect re-resolves a fresh token rather than replaying a stale one, and
    // never depends on stripToken to undo a baked-in token.
    this.connectedUrl = baseUrl;

    // Don't change status to "connecting" during section switches
    // (keeps current status visible until reconnected). Likewise keep the current
    // "connected" status during a GoAway pre-emptive reconnect (bd
    // polyglot-pdf-l3a.2) so the silent resume shows no connecting/disconnected
    // flicker to the user.
    if (!this.isSectionSwitching && !this.goAwayReconnectInFlight) {
      this.setStatus("connecting", "connect");
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
        const socket = new WebSocket(finalUrl);
        this.ws = socket;

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
          // Pass the socket that fired so handleClose can ignore a STALE close --
          // e.g. the old section socket's close arriving after startSection already
          // opened the new one (Codex PR #137).
          this.handleClose(event, socket);
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
    // Clear the drop-reconnect marker on an intentional disconnect (bd
    // polyglot-pdf-ppfy).
    this.droppedReconnectInFlight = false;

    // B5 (bd polyglot-pdf-jnjj.17): release any parked validator switch-gate on an
    // intentional disconnect. We RESOLVE the gate promise (so proceedSectionSwitch's
    // awaiter does not hang forever) but set the cancel flag so it SKIPS the switch
    // -- teardown owns the section state now, and the fail-OPEN timer must not later
    // fire a switch into a torn-down connection.
    if (this.pendingSectionSwitch) {
      clearTimeout(this.pendingSectionSwitch.timer);
      const pending = this.pendingSectionSwitch;
      this.pendingSectionSwitch = null;
      pending.cancelled = true;
      pending.resolve();
    }

    // An INTENTIONAL disconnect (UI unmount / stop-session) cancels any in-flight
    // section switch SILENTLY -- it must not be reported as a switch FAILURE
    // (Codex PR #137: otherwise handleClose's switchInFlight branch fires a false
    // onError + `error` status after normal teardown). Clear the guard + watchdog
    // first; the close that follows then takes the normal disconnected path.
    // EXCEPTION: startSection performs its own intentional disconnect mid-switch
    // (isSectionSwitching is set across that window) -- there we keep the guard so
    // the switch continues, and handleClose's isSectionSwitching early-return
    // covers the close.
    if (this.switchInFlight && !this.isSectionSwitching) {
      this.switchInFlight = false;
      this.clearSectionSwitchWatchdog();
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    // Don't change status during section switches (will be updated after reconnect)
    if (!this.isSectionSwitching) {
      this.setStatus("disconnected", "disconnect");
    }
  }

  /**
   * Send handshake to establish ephemeral session
   */
  private handleOpen(): void {
    this.reconnectAttempts = 0;
    this.reconnectDelay = 1000;
    // A GoAway pre-emptive reconnect (bd polyglot-pdf-l3a.2) is complete once the
    // new socket opens -- release the once-guard so a later GoAway can drive
    // another reconnect.
    this.goAwayReconnectInFlight = false;


    // Reset the unconfirmable-field loop-breaker on every (re)connect so a counter
    // left mid-window before a drop does not false-trip on the first confirm of the
    // new session (bd polyglot-pdf-0y7, fresh-eyes PR #113; session cap bd r2hy).
    this.resetUnconfirmableTracking();
    // Likewise reset the AI-value validation-reject loop-breaker (bd polyglot-pdf-wpw.3).
    this.resetValidationRejectTracking();
    // B4 (bd polyglot-pdf-jnjj.16): clear the form_complete dirty-snapshot on every
    // (re)connect so reconnecting into an already-complete form re-emits form_complete
    // once (the validator gets a fresh full-form pass). Without this, a reconnect
    // would inherit no snapshot anyway (fresh instance) -- but a same-instance
    // section-switch reconnect keeps the object, so resetting here is what makes the
    // post-reconnect re-validation deterministic (validation-delegation.md contract 4).
    this.formCompleteSnapshot = null;
    // W3 (bd polyglot-pdf-pr3i): a drop mid-drain never got its drain_findings_result,
    // so re-arm the guard on (re)connect -- the handleSessionReady re-drain below can
    // then re-send a surviving queue.
    this.drainInFlight = false;

    // Enable auto-reconnect after first successful connection
    this.enableAutoReconnect = true;

    // Skip automatic handshake during section switches (startSection will send it)
    if (this.isSectionSwitching) {
      return;
    }

    // Re-read the CURRENT sessionStorage state before building the handshake
    // (bd polyglot-pdf-fn1m). this.state is the constructor's init() snapshot.
    // init() already REUSES recent matching persisted state, so on a typical
    // soft page refresh this.state is usually current -- but a brand-new
    // connection is built on reload, and any save() that lands between that
    // construction and this open (or a store already ahead of the snapshot)
    // would leave this.state predating the latest currentSectionId / fieldValues.
    // The handshake would then serialize stale values and the resumed (stateless)
    // backend would rebuild context from prior-section data the client no longer
    // holds -- the "model asserts a value from a previous section" symptom.
    // reloadState() pulls the freshest sessionStorage back in so the handshake
    // reflects the client's actual current field state; it is a strict safety
    // net (never regresses, since every this.state mutator save()s synchronously
    // so the store is always >= as fresh as this.state). No-op if storage is
    // empty (keeps the snapshot). Must run BEFORE getHandshakePayload below; the
    // post-session_ready load() (handleSessionReady) fires too late for the very
    // first handshake.
    this.reloadState();

    // Send handshake with schema + current_values + fill_language.
    // Pass resume:true on reconnects so the backend skips the greeting
    // and section re-introduction (bd polyglot-pdf-vmxx).
    //
    // hasConnectedOnce covers in-memory reconnects, but it is instance-scoped
    // and a brand-new WebFormConnection built on a SOFT PAGE REFRESH (F5) has it
    // false -- so the first post-reload handshake would send resume:false and
    // the backend would re-greet a user who is mid-form. reloadState() above has
    // already pulled the freshest persisted state, so also treat an
    // already-in-progress persisted session (disclaimer accepted + at least one
    // filled field) as a resume (bd polyglot-pdf-hc4b).
    const isResume = this.hasConnectedOnce
      || SchemaFormStateManager.hasInProgressSession(this.state);
    this.hasConnectedOnce = true;
    const handshake = SchemaFormStateManager.getHandshakePayload(this.state, this.fillLanguage, isResume);
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

        case "confirm_field":
          this.handleConfirmFieldRequest(message);
          break;

        case "skip_field":
          this.handleSkipFieldRequest(message);
          break;

        case "switch_field":
          this.handleSwitchFieldRequest(message);
          break;

        case "error":
          this.handleServerError(message);
          break;

        case "turn_complete":
          // Gemini finished speaking (transcript received) - signal to activity watchdog
          if (window.vffOnTurnComplete) {
            window.vffOnTurnComplete();
          }
          // Safety clear for the thinking indicator (bd polyglot-pdf-wpw.5): the
          // agent's turn is over, so it can't still be "processing."
          this.clearThinking('turn_complete');
          break;

        case "agent_processing":
          // Backend-driven thinking-indicator signal (bd polyglot-pdf-wpw.5):
          // processing:true on a real user turn (BOTH VAD modes), false at the
          // agent's first response audio / turn end. Drive the indicator from it.
          if (message.processing === true) {
            this.startThinking();
          } else {
            this.clearThinking('agent_processing:false');
          }
          // TEST-ONLY observability (bd polyglot-pdf-fa4x): let the E2E voice
          // harness see that the native-VAD START signal fired, without a human
          // mic. Undefined in production; only the harness sets it.
          if (window.vffOnAgentProcessing) {
            window.vffOnAgentProcessing(message.processing === true);
          }
          break;

        case "gemini_session_restarted":
          // Backend confirms Gemini session has been restarted successfully
          console.log('[WebFormConnection] [OK] Gemini session restarted successfully');
          // Trigger callback to update UI (ConnectionManager will set status to 'connected')
          if (this.callbacks.onSessionRestarted) {
            this.callbacks.onSessionRestarted();
          }
          break;

        case "idle_timeout":
          // Backend is closing connection due to inactivity
          // Set flag to prevent auto-reconnect, require manual reconnect
          console.log('[WebFormConnection] [timer] Idle timeout received from backend:', message);
          this.idleTimedOut = true;
          this.setStatus("idle_timeout", "handleMessage:idle_timeout");
          // WebSocket will close shortly, handleClose() will see idleTimedOut flag
          break;

        case "go_away":
          // The Gemini Live server will terminate this connection shortly (bd
          // polyglot-pdf-c5t). Surface time_left to any consumer via onGoAway, then
          // ACT on it: unlike idle_timeout we do NOT set a no-reconnect flag,
          // because a GoAway is a server lifecycle reset (reconnect IS wanted), not
          // a user-inactivity close.
          console.log('[WebFormConnection] [wave] GoAway received from Gemini; time_left:', message.time_left);
          if (this.callbacks.onGoAway) {
            this.callbacks.onGoAway(message.time_left ?? null);
          }
          // POLICY (bd polyglot-pdf-l3a.2): act on the GoAway with a silent,
          // pre-emptive reconnect. A GoAway means the server is about to reset this
          // connection; re-establishing NOW -- through the existing reconnect path,
          // which sends resume:true (bd polyglot-pdf-vmxx) -- means the new session
          // is up around the server's own close, with no re-greeting and no jarring
          // drop. The onGoAway callback above still fires for any UI consumer, but
          // the reconnect no longer depends on one being wired.
          this.handleGoAwayReconnect();
          break;

        case "interrupted":
          // Gemini stopped the current generation because the user barged in
          // (bd polyglot-pdf-s7uf). Without this, the dead generation's
          // already-received tail keeps playing -- the reason barge-in feels
          // broken. Clear BOTH client audio holds: the staging queue here, and
          // (via onInterrupted -> audioManager.resetPlaybackClock) the
          // scheduled sources + playback clock. Deliberately NOT
          // flushAudioQueue: that sets playbackBlocked, which without a paired
          // resumePlayback kills all subsequent audio (the nm7z trap) -- and
          // the model is about to speak a NEW generation on this connection.
          console.log('[WebFormConnection] [interrupt] Gemini generation interrupted; draining stale audio');
          this.audioQueue = [];
          if (this.callbacks.onInterrupted) {
            this.callbacks.onInterrupted();
          }
          break;

        case "gemini_session_dropped":
          // The Gemini Live session died SPONTANEOUSLY behind our still-open WS
          // (e.g. a 1011 "Input data processing failed"), so the backend can no
          // longer produce responses (bd polyglot-pdf-ppfy). Without this the
          // client would sit frozen on "connected" while the user's audio is
          // silently dropped. Drive the SAME pre-emptive reconnect the GoAway path
          // uses (close + reconnect with resume:true, no re-greeting), but surface
          // a "reconnecting" status so the UI shows the transient recovery modal;
          // handleSessionReady restores "connected" on success, clearing it. The
          // goAwayReconnectInFlight guard coalesces this with any concurrent
          // GoAway reconnect so we never fire two.
          console.log('[WebFormConnection] [warn] Gemini session dropped (spontaneous); reconnecting');
          // Mark this reconnect as drop-driven so the overlay shows the "having
          // trouble reaching the AI" modal for it (and NOT for an ordinary WS blip
          // that attemptReconnect drives to the same "reconnecting" status). ONLY
          // set the marker when handleGoAwayReconnect ACTUALLY starts a fresh
          // reconnect: if it coalesces into an in-flight GoAway reconnect (or is
          // skipped), status never transitions to "reconnecting", so the marker
          // would leak `true` forever (the completing reconnect's setStatus is a
          // no-op and never clears it) -- and a later ordinary blip would then
          // wrongly show the AI modal (two independent fresh-eyes reviews). When
          // coalesced, the in-flight reconnect owns recovery; the drop rides it
          // silently, which is correct (a single seamless reconnect) (bd
          // polyglot-pdf-ppfy).
          {
            const startedReconnect = this.handleGoAwayReconnect(/* surfaceReconnectingStatus */ true);
            if (startedReconnect) {
              this.droppedReconnectInFlight = true;
            }
          }
          break;

        case "validation_result":
          // B5 (bd polyglot-pdf-jnjj.17) + W3 (bd polyglot-pdf-pr3i): the validator's
          // verdict (REPORT-ONLY since W3). A clean result ({conflicts:[]}) resumes any
          // paused section switch and enqueues nothing (no voice turn). A result with
          // surviving conflicts ENQUEUES them into validatorFindingsQueue and drains
          // immediately (drain_findings) -- the backend composes+injects the steer on
          // the drain, not here. See handleValidationResult.
          this.handleValidationResult(message);
          break;

        case "drain_findings_result":
          // W3 (bd polyglot-pdf-pr3i): the backend delivered the steer for these
          // conflicts. Mark their fields steered (max-resteer marker) + CONSUME them
          // from the queue. Un-delivered conflicts (dead session -> not here) stay
          // queued to retry on the next drain.
          this.handleDrainFindingsResult(message);
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
    const { session_id, ephemeral, jit_mode_enabled, dti_mode_enabled, native_vad, continuous_session_enabled } = message;

    // Captured at ENTRY, before any of this handler's own state writes: the
    // setSessionId/setJitMode/setContinuousSession mutators below PERSIST
    // this.state, so a later storage read would only echo the in-memory value
    // back -- the in-memory-vs-persisted divergence the opener diagnostic
    // exists to surface (the state-staleness hypothesis, bd polyglot-pdf-xp4q)
    // is only observable here.
    const storageDisclaimerAtEntry = !!SchemaFormStateManager.load()?.disclaimerAccepted;

    // Update state with session ID
    this.state = SchemaFormStateManager.setSessionId(this.state, session_id);

    // Enable JIT mode if backend supports it
    if (jit_mode_enabled !== undefined) {
      this.state = SchemaFormStateManager.setJitMode(this.state, jit_mode_enabled);
      if (jit_mode_enabled) {
        console.log('[WebFormConnection] [OK] JIT mode enabled by backend');
      }
    }

    // Continuous-session mode (bd polyglot-pdf-x8rt): when on, the client builds a
    // whole-form handshake and stops advancing sections (see proceedSectionSwitch /
    // handlePrepareSectionSwitchRequest). Store it on state so the handshake builder
    // and navigation read it. Default false when the backend omits the field.
    this.state = SchemaFormStateManager.setContinuousSession(this.state, continuous_session_enabled === true);
    this.continuousSessionEnabled = continuous_session_enabled === true;
    if (this.continuousSessionEnabled) {
      console.log('[WebFormConnection] [OK] Continuous-session mode enabled by backend');
    }

    // DTI mode (bd polyglot-pdf-jnjj.22): when on, the client supplies each next
    // field's full schema on next_field_hint_response (the backend renders it into
    // the confirm_field guidance, since the client owns the schema).
    this.dtiModeEnabled = dti_mode_enabled === true;
    if (this.dtiModeEnabled) {
      console.log('[WebFormConnection] [OK] DTI mode enabled by backend');
    }

    // Native-VAD mode (bd polyglot-pdf-333): tell the connection/audio layer
    // whether Gemini's own VAD is driving turns. Fire BEFORE onSessionReady so
    // the audio layer is configured before any connected-state effects run.
    // Default to false (manual VAD) when the backend doesn't send the field.
    if (this.callbacks.onNativeVadMode) {
      this.callbacks.onNativeVadMode(native_vad === true);
    }

    // If a reconnect-based section switch was in flight (startSection), THIS is
    // its terminal success signal -- not the moment the handshake was sent
    // (Codex/fresh-eyes PR #137). Release the guard + disarm the watchdog here so
    // a stall AFTER the handshake but BEFORE session_ready is still caught by the
    // watchdog, and a second switch can't start during the switching window.
    // Captured BEFORE the release: the field-1 opener diagnostic below needs to
    // know this session_ready terminated a section switch (the post-I-Agree
    // switchToFirstSection path is the primary such switch; bd polyglot-pdf-xp4q).
    const wasSectionSwitch = this.switchInFlight;
    if (this.switchInFlight) {
      this.completeSectionSwitch();
    }

    // A successful (re)connect reached session_ready: clear the drop-reconnect
    // marker directly here (bd polyglot-pdf-ppfy). Clearing it explicitly -- not
    // only via setStatus("connected") below -- is belt-and-suspenders: if status was
    // already "connected" (e.g. a coalesced reconnect that never transitioned),
    // setStatus no-ops and would not run its clear, so a session_ready always
    // resolves the marker regardless (two independent fresh-eyes reviews).
    this.droppedReconnectInFlight = false;

    this.setStatus("connected", "handleSessionReady");

    // Field-1 opener: on a reconnect (disclaimer already accepted) auto-send
    // the language message that triggers the initiating prompt, whose payload
    // carries the CURRENT field's guidance (bd polyglot-pdf-j748). This gate
    // used to skip SILENTLY -- and on the deployed demo it skipped in 3/3
    // observed real-auth sessions, leaving the model with no field_id to copy
    // on the first turn, so it invents one (bd polyglot-pdf-xp4q). Behavior is
    // unchanged here; the change is that a skip in the window where the opener
    // is EXPECTED now names its failing condition, in the console AND -- via
    // `client_diagnostic` -- in the backend's production logs.
    const openerDisclaimerAccepted = !!this.state.disclaimerAccepted;
    const openerHasLanguage = !!this.state.selectedLanguage;
    // Preserve the original laziness: the hint is only computed once the two
    // state gates pass, exactly as before.
    const openerNextFieldHint =
      openerDisclaimerAccepted && openerHasLanguage
        ? this.computeNextFieldHintString()
        : "";
    if (openerDisclaimerAccepted && openerHasLanguage && openerNextFieldHint) {
      this.send({
        type: 'change_spoken_language',
        spoken_language: this.state.selectedLanguage,
        next_field_hint: openerNextFieldHint
      });
      console.log('[WebFormConnection] [OK] Auto-sent language message for reconnect:', this.state.selectedLanguage);
    } else if (wasSectionSwitch || openerDisclaimerAccepted) {
      // The opener was EXPECTED here -- a section-switch handshake (the
      // post-I-Agree switchToFirstSection is the primary producer; the
      // deprecated completeSection reset path also routes through startSection)
      // or an accepted-disclaimer reconnect -- and did not fire. The very first
      // connect of a session (no switch, disclaimer not yet accepted) is the
      // one legitimate silent skip and stays quiet, so this diagnostic is
      // signal, not noise. is_form_complete disambiguates the benign
      // completed-form reconnect (nothing left to ask -> hint correctly empty)
      // from a genuinely broken opener -- the two are otherwise byte-identical
      // in the log (fresh-eyes finding, this change). Booleans only -- no
      // field data, no values (no-PII policy).
      const skipDiagnostic = {
        was_section_switch: wasSectionSwitch,
        disclaimer_accepted: openerDisclaimerAccepted,
        has_selected_language: openerHasLanguage,
        has_next_field_hint: !!openerNextFieldHint,
        is_form_complete: isFormComplete(this.state),
        // The leading live-bug hypothesis is that this.state is STALE here.
        // Reporting the persisted value ALONGSIDE the in-memory one makes
        // staleness a single-glance read: a false/true divergence names it
        // outright (Opus outer review finding, bd polyglot-pdf-xp4q). Uses the
        // handler-ENTRY capture -- this handler's own mutators persist
        // this.state before this line runs, so a fresh load() here could only
        // ever echo the in-memory value (found when the divergence test failed
        // against a same-site read).
        storage_disclaimer_accepted: storageDisclaimerAtEntry,
        // has_next_field_hint's meaning is mode-conditional: in non-continuous
        // (deprecated) mode the hint is SECTION-scoped, so "no hint" at a
        // section boundary is benign even when the form is incomplete. This
        // flag says which reading applies.
        continuous_session: !!this.continuousSessionEnabled,
      };
      console.warn('[WebFormConnection] field-1 opener SKIPPED (bd polyglot-pdf-xp4q)', skipDiagnostic);
      this.send({
        type: 'client_diagnostic',
        event: 'field1_opener_skipped',
        ...skipDiagnostic,
      });
    }

    if (this.callbacks.onSessionReady) {
      this.callbacks.onSessionReady(session_id);
    }

    // B4 (bd polyglot-pdf-jnjj.16): emit form_complete if we reconnected INTO an
    // already-complete (and dirty) form (Codex PR #271). A field edited while the
    // socket was closed (e.g. after an idle timeout) takes the early return in
    // sendManualFieldUpdate (WS not OPEN), so no form_complete fires at edit time;
    // handleOpen then clears formCompleteSnapshot to null on reconnect. Without this
    // call the guard is cleared but the emitter is never invoked, so the dirty
    // completed form would bypass the B5 validator. The socket is OPEN here
    // (session_ready arrived), so the send succeeds; refresh this.state from the
    // persisted snapshot first so a closed-socket edit saved to sessionStorage is
    // reflected. maybeEmitFormComplete is guarded -> no-op for an incomplete form.
    const persisted = SchemaFormStateManager.load();
    if (persisted) this.state = persisted;
    this.maybeEmitFormComplete();
    // W2 (bd polyglot-pdf-kxkw): stride-window validator check on the same
    // state-change seam (guarded: sends only newly-eligible, unsent windows).
    this.maybeEmitValidateWindows();
    // W3 (bd polyglot-pdf-pr3i): a validator finding queue can survive a reconnect
    // (client-owned + persisted). Re-drain it now so a contradiction found just
    // before a drop is still voiced after reconnect (guarded on an OPEN socket).
    this.drainFindings();

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
    const lockedFields: Array<{ fieldId: string; field: any; reason: string; readOnly: boolean }> = [];

    for (const [displayName, value] of Object.entries(updates)) {
      // Find field by display name
      const field = this.state.schema.fields.find(
        (f) => f.name === displayName || f.id === displayName
      );

      if (field) {
        // Check if field is locked/hidden/read-only due to dependencies.
        // A read_only field is locked too (bd polyglot-pdf-34wc): the AI must
        // not write to it, and the gate previously checked only hidden +
        // show_if visibility, so a visible read_only field slipped through to
        // the apply path instead of being reported back to the model.
        // shouldShowField ALONE (bd polyglot-pdf-ubam): it already folds in
        // `hidden` for the no-show_if case, and an extra `!field.hidden &&`
        // wrongly locked a `hidden: true` field whose show_if is SATISFIED --
        // a field that renders and is required, reported back to the model as
        // unavailable so it could never be filled by voice.
        const readOnly = isFieldReadOnly(field, this.state.fieldValues);
        const isAvailable =
          shouldShowField(field, this.state.fieldValues, this.state.schema.fields) &&
          !readOnly;

        if (!isAvailable) {
          // Field is locked - collect dependency info for error message
          const { lockedReason } = evaluateFieldAvailability(
            field,
            this.state.fieldValues,
            this.state.schema
          );

          // lockedReason is populated for show_if-gated fields (it names the
          // prerequisite); a statically-hidden field (field.hidden) has none, so
          // fall back to a short reason that does NOT restate the field name --
          // the per-field message prefix below already names it, and doubling it
          // ("Cannot update 'X': The field 'X' is not available yet") reads poorly
          // and adds no information (bd polyglot-pdf-z6xs, fresh-eyes finding 4).
          // readOnly is carried so the trailing guidance can distinguish a
          // read_only field (permanently AI-unwritable -- no prerequisite to wait
          // on) from a dependency-gated one (bd polyglot-pdf-34wc, finding 1).
          lockedFields.push({
            fieldId: field.id,
            field,
            reason: lockedReason || 'it is not available yet (a prerequisite field must be completed first).',
            readOnly
          });

          console.warn(`[WebFormConnection] [X] Field ${field.id} is locked:`, lockedReason);
          continue; // Skip applying this update
        }

        // Validate the AI-supplied value before it lands; on failure the apply is
        // skipped and a corrective PII-free prompt is routed to the model (bd
        // polyglot-pdf-wpw.3). Applied values fill as UNCONFIRMED -- they still
        // require explicit confirmation via the confirm_field tool.
        // Canonicalize the shape FIRST (comma-string -> string[] for checkbox
        // groups, bd h76m.2) so the onFieldUpdate callback carries the same
        // value the funnel validates and stores (idempotent -- the funnel
        // re-canonicalizes internally as its own guarantee).
        const canonicalValue = canonicalizeAiCheckboxGroupValue(field, value);
        if (this.applyAiValueWithValidation(field, canonicalValue, { emit: false })) {
          updatedFields.push({ fieldId: field.id, value: canonicalValue });
        }
      } else {
        // Field not found in schema - ignore
      }
    }

    // If any fields were locked, inform Gemini via completion_message (bd z6xs).
    // dependency_error has no backend handler -- it falls through to
    // unknown_control_message_type and the locked-field reason never reaches
    // the model. completion_message -> send_prompt is the proven in-band channel
    // (same path as the validation-reject loop-breaker in handleAiValueRejected).
    if (lockedFields.length > 0) {
      // PER-FIELD guidance, not a single trailing instruction (bd
      // polyglot-pdf-2ip6 + fresh-eyes): the directive depends on the lock KIND,
      // and a single batch can mix kinds. A read_only field is system-managed and
      // has NO prerequisite to wait on -- a blanket "complete the prerequisite
      // fields" suffix would send the model chasing upstream fields that don't
      // exist for it. So each field carries its own directive. The dependency-gated
      // `lf.reason` is ALREADY a complete, specific instruction ("Complete the 'X'
      // field first..."), so its directive only adds the don't-retry-now signal
      // WITHOUT restating the prerequisite (avoids the redundant / double-
      // "prerequisite" phrasing fresh-eyes flagged). The read_only directive states
      // the permanence (system-managed, never fillable).
      const errorMessages = lockedFields.map(lf => {
        const name = lf.field.spoken_name || lf.field.name;
        const directive = lf.readOnly
          ? 'It is system-managed and cannot be filled; do not attempt to fill it again.'
          : 'It was not updated; do not retry until then.';
        return `Cannot update '${name}': ${lf.reason} ${directive}`;
      });

      console.error('[WebFormConnection] Locked field(s):', errorMessages);

      this.send({
        type: 'completion_message',
        message: errorMessages.join(' '),
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

      // Validate the AI value before it lands (bd polyglot-pdf-wpw.3). Every value
      // reaching here is an AI change: either applied_fields named it (isApplied),
      // or there were no applied_fields at all (the legacy on_form_update path,
      // which sends raw tool args -- Codex PR #145) and it differs from the current
      // value. A pure unchanged echo never reaches this point (it is `continue`d by
      // the limitToApplied guard above or by shouldUpdate). So validate
      // unconditionally; a reject skips the apply and routes a corrective PII-free
      // prompt to the model. Canonicalized first (comma-string -> string[] for
      // checkbox groups, bd h76m.2) so the callback carries the stored shape.
      const canonicalValue = canonicalizeAiCheckboxGroupValue(field, value);
      if (this.applyAiValueWithValidation(field, canonicalValue, { emit: false })) {
        updatedFields.push({ fieldId: field.id, value: canonicalValue });
      }
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

        // Validate the AI value before it lands (bd polyglot-pdf-wpw.3). Re-enables
        // the client-side validateField gate that was previously disabled here.
        // Every value reaching this point is an AI change (applied_fields named it,
        // or the legacy no-applied_fields path sent it and it differs from current);
        // a pure unchanged echo was already `continue`d above. So validate
        // unconditionally; a reject skips the apply and routes a corrective PII-free
        // prompt to the model. Applied values fill as UNCONFIRMED. Canonicalized
        // first (comma-string -> string[] for checkbox groups, bd h76m.2) so the
        // callback carries the stored shape.
        const canonicalValue = canonicalizeAiCheckboxGroupValue(field, value);
        if (this.applyAiValueWithValidation(field, canonicalValue, { emit: false })) {
          updatedFields.push({ fieldId: field.id, value: canonicalValue });
        }
      }
    }

    if (updatedFields.length) {
      if (this.callbacks.onFieldUpdate) {
        this.callbacks.onFieldUpdate(updatedFields);
      }
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

    // Applicability (`shown`) rides each entry for the secretary's values tail
    // (bd polyglot-pdf-p68s / jnjj.45d): the backend cannot derive it (stateless),
    // so the client -- which owns conditional UI -- computes it via shouldShowField.
    // It is computed against the FULL fieldValues map (so a trigger field outside
    // the requested set still resolves) and passes schema.fields for checkbox-group
    // trigger disambiguation. A field absent from the schema (defensive) is treated
    // as shown=true, matching the backend renderer's shown_map default.
    const fields = this.state.schema?.fields ?? [];
    const shownFor = (fieldId: string): boolean => {
      let field = fields.find((f) => f.id === fieldId);
      // Mirror the [] bracket fallbacks used for value lookup below.
      if (!field && !fieldId.endsWith('[]')) {
        field = fields.find((f) => f.id === fieldId + '[]');
      }
      if (!field && fieldId.endsWith('[]')) {
        field = fields.find((f) => f.id === fieldId.slice(0, -2));
      }
      if (!field) return true;
      return shouldShowField(field, this.state.fieldValues, fields);
    };

    // Look up a stored value for a field id, mirroring the [] bracket fallbacks
    // used in the requested-field branch (Gemini sometimes drops/adds the []).
    const valueFor = (fieldId: string): any => {
      let fv = this.state.fieldValues[fieldId];
      if (!fv && !fieldId.endsWith('[]')) fv = this.state.fieldValues[fieldId + '[]'];
      if (!fv && fieldId.endsWith('[]')) fv = this.state.fieldValues[fieldId.slice(0, -2)];
      return fv;
    };

    if (requestedFieldIds.length === 0) {
      // No specific fields requested - return ALL fields. Iterate the SCHEMA, not
      // just state.fieldValues: the secretary's get_form_state(field_ids=[]) needs
      // every field's `shown` represented, including UNTOUCHED conditional fields.
      // If we emitted only touched fields, an untouched field hidden by show_if would
      // be omitted -> left out of the backend shown_map -> defaulted to shown=true,
      // wrongly telling the secretary a hidden empty field is applicable (Codex
      // PR #266). Untouched fields ride with value:null/confirmed:false; the one
      // value-bearing consumer (get_form_status) skips null values, so this is safe.
      const emitted = new Set<string>();
      for (const field of fields) {
        const fieldId = field.id;
        const fv = valueFor(fieldId);
        fieldValues[fieldId] = {
          value: fv ? fv.value : null,
          confirmed: fv ? fv.confirmed : false,
          shown: shownFor(fieldId),
        };
        emitted.add(fieldId);
        // Mark the resolved storage-key variant emitted too, so the sweep below
        // does not re-add the SAME value under its [] variant key.
        if (fv) {
          if (this.state.fieldValues[fieldId]) emitted.add(fieldId);
          if (!fieldId.endsWith('[]') && this.state.fieldValues[fieldId + '[]']) emitted.add(fieldId + '[]');
          if (fieldId.endsWith('[]') && this.state.fieldValues[fieldId.slice(0, -2)]) emitted.add(fieldId.slice(0, -2));
        }
      }
      // Defensive: include any stored value whose key is NOT in the schema (so a
      // stray/legacy value is never silently dropped from the all-fields response).
      for (const [fieldId, fieldValue] of Object.entries(this.state.fieldValues)) {
        if (emitted.has(fieldId)) continue;
        fieldValues[fieldId] = {
          value: fieldValue.value,
          confirmed: fieldValue.confirmed,
          shown: shownFor(fieldId),
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
            shown: shownFor(fieldId),
          };
        } else {
          // Field not yet filled
          fieldValues[fieldId] = {
            value: null,
            confirmed: false,
            shown: shownFor(fieldId),
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

    // Refresh from the persisted snapshot first -- the same staleness rule the
    // sibling next-field producers already follow (handleSwitchFieldRequest,
    // handleManualUpdateHint). This is the PRIMARY per-turn hint producer (the
    // confirm_field next-field round-trip), and `this.state` is an in-memory
    // copy, while every SchemaFormStateManager mutator builds a NEW state object
    // and save()s it -- so anything written outside this object (in the UI, or by
    // a sibling handler) is in storage but not in `this.state`. Reading the stale
    // copy makes the hint disagree with what the form actually holds
    // (bd polyglot-pdf-pjws).
    //
    // NOT about mid-session language switching: that is unsupported -- the spoken
    // language is pinned for the whole form (bd polyglot-pdf-87a9,
    // docs/standards/voice-and-vad.md). The pjws fix was originally written up
    // that way; the refresh is right regardless, because it is the general
    // read-stale-state defect, not a language one.
    const persisted = SchemaFormStateManager.load();
    if (persisted) this.state = persisted;

    // Compute the next field ONCE, and derive BOTH the hint and (for DTI) the
    // schema from it -- so the hint and the supplied schema can never refer to
    // different fields (fresh-eyes substitute review, Codex PR #229).
    const nextField = isFormComplete(this.state)
      ? null
      : computeNextField(this.state, { skipConfirmed: true });

    // Notify UI about the next field (highlight/scroll) -- same side effect
    // computeNextFieldHintString had.
    if (this.callbacks.onNextField) {
      this.callbacks.onNextField(nextField ? nextField.id : null);
    }

    const hint = nextField
      ? formatNextFieldHint(nextField, getFieldOrder(this.state, nextField.id) || undefined,
          // `this.state` was replaced from the persisted snapshot at the top of
          // this handler, so its language IS the fresh one -- no second parse.
          this.sessionLanguageFor(true))
      : null;

    // Store last field hint for recovery prompts
    if (hint) {
      sessionStorage.setItem('vff_last_field_hint', hint);
    }

    // DTI (bd polyglot-pdf-jnjj.22): the client owns the schema, so it supplies the
    // SAME field's FULL schema here -- the backend renders it into the confirm_field
    // guidance. Only when DTI is on AND there's a next field.
    let nextFieldSchema: unknown = undefined;
    if (this.dtiModeEnabled && nextField) {
      nextFieldSchema = getFieldSchema(nextField.id, this.state.schema);
    }

    // Send response back to backend
    this.send({
      type: "next_field_hint_response",
      request_id: requestId,
      hint: hint,  // Can be null if form is complete
      ...(nextFieldSchema ? { next_field_schema: nextFieldSchema } : {}),
    });
  }

  /**
   * The session's CURRENT spoken language, read through to the persisted
   * snapshot (bd polyglot-pdf-pjws).
   *
   * The language is PINNED per session (bd polyglot-pdf-87a9,
   * docs/standards/voice-and-vad.md), so this is not about switching languages.
   * It is about WHERE the pinned value lives: `acceptDisclaimer` /
   * `setSelectedLanguage` build a NEW state object and save() it, and never touch
   * this object's in-memory `this.state`. A producer formatting off `this.state`
   * before it has synced would resolve option labels against a language the
   * session no longer holds -- reading through to storage removes that class
   * entirely rather than relying on every caller having refreshed.
   *
   * Reading only the LANGUAGE through to storage (rather than reloading all of
   * `this.state`) keeps this safe for the section-switch callers, which hold a
   * freshly-mutated in-memory state that a blanket reload could revert.
   *
   * `alreadyFresh` skips the read for a caller that JUST replaced `this.state`
   * from the same snapshot. load() parses the whole persisted blob -- schema
   * included -- so on the confirm -> next-field round-trip (the primary
   * per-turn path, which refreshes at the top of the handler) the unconditional
   * read cost a second full JSON.parse for a value already in hand
   * (2nd Opus outer review, this PR). Defaults to reading through, so a caller
   * that has NOT refreshed still gets the fresh language.
   */
  private sessionLanguageFor(alreadyFresh = false): string | null | undefined {
    if (alreadyFresh) return this.state.selectedLanguage;
    return SchemaFormStateManager.load()?.selectedLanguage ?? this.state.selectedLanguage;
  }

  private get sessionLanguage(): string | null | undefined {
    return this.sessionLanguageFor();
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
    const hint = formatNextFieldHint(nextField, fieldOrder || undefined,
        this.sessionLanguage);

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
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  private handlePrepareSectionSwitchRequest(message: any): void {
    const requestId = message.request_id;
    const identifier = message.identifier;

    console.log('[WebFormConnection] handlePrepareSectionSwitchRequest START', { requestId, identifier });

    // Continuous-session mode (bd polyglot-pdf-x8rt): sections do not exist as a
    // navigation unit -- reject any AI-initiated switch. The backend drops the
    // switch_section tool in continuous mode, so this should never fire; this is the
    // client-side backstop against a stray call resetting the one session we keep.
    if (this.continuousSessionEnabled) {
      console.warn('[WebFormConnection] prepare_section_switch rejected -- continuous-session mode has no sections');
      this.send({
        type: "section_info_response",
        request_id: requestId,
        section_info: null,
        error: 'Section switching is disabled in continuous-session mode',
      });
      return;
    }

    // This is the AI-INITIATED switch path (Gemini called switch_section -> backend
    // prepare_section_switch -> here -> section_info_response -> backend restarts
    // -> section_switched). If a switch is ALREADY in flight (e.g. a manual switch
    // started first), REJECT this one: reply with a null section_info + error and
    // do NOT mutate local section state or start a second backend switch (Codex PR
    // #137 -- otherwise the reverse-order manual-then-AI overlap is not blocked).
    if (this.switchInFlight) {
      console.warn('[WebFormConnection] prepare_section_switch rejected -- a section switch is already in progress');
      this.send({
        type: "section_info_response",
        request_id: requestId,
        section_info: null,
        error: 'A section switch is already in progress',
      });
      return;
    }

    // The guard is claimed only AFTER a valid target is resolved (below), so the
    // null/error early-returns for an invalid request never leave a stuck
    // switching_section (Codex PR #137).
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

      // A valid target is resolved -- NOW claim the switch guard + arm the watchdog
      // (Codex PR #137). Doing it here (not at entry) means the null/error returns
      // above for an invalid request never leave a stuck switching_section. The
      // guard releases on section_switched (-> completeSectionSwitch) or watchdog.
      this.switchInFlight = true;
      this.setStatus('switching_section', "handlePrepareSectionSwitch");
      this.armSectionSwitchWatchdog();

      // If the client auto-advance is PARKED on the validator gate, this AI-initiated
      // switch supersedes it -- CANCEL the parked switch (bd polyglot-pdf-k726).
      // Gemini's switch_section can jump to an ARBITRARY section by order/label, so a
      // parked client N->N+1 switch and an AI switch to an unrelated section M can be
      // in flight at once; cancel is correct for BOTH targets:
      // - MATCH (same boundary): the AI switch is authoritative and advances in place.
      // - MISMATCH (different target M): the AI switch has authoritatively RELOCATED
      //   the session to M, so the parked N->N+1 boundary is now STALE -- running it
      //   later would reconnect-switch the user OUT of M (tearing down the AI's session
      //   and audio) the moment the parked gate's fail-OPEN timer fires, because that
      //   timer resolves AFTER this AI switch completes and clears switchInFlight, so
      //   proceedSectionSwitch's post-await switchInFlight re-check no longer guards it.
      //   Cancelling is the safe outcome (not a silent drop of a still-valid advance --
      //   the advance is no longer valid once the AI moved the session).
      // cancelPendingSectionSwitch resolves the gate's promise with cancelled=true, so
      // proceedSectionSwitch's await unblocks and returns at its `if (gate.cancelled)`
      // check without switching -- no reconnect, no audio teardown, no throw.
      if (this.pendingSectionSwitch) {
        const parkedTargetSectionId = this.pendingSectionSwitch.sectionId;
        console.log('[WebFormConnection] [validator] AI-initiated switch superseding a parked client switch; cancelling the parked switch.', {
          aiTargetSectionId: targetSectionId,
          parkedTargetSectionId,
          sameBoundary: parkedTargetSectionId === targetSectionId,
        });
        this.cancelPendingSectionSwitch();
      }

      // Switch to target section in local state (no disconnect!)
      console.log('[WebFormConnection] Switching to section', targetSectionId);
      const updatedState = SchemaFormStateManager.switchToSection(currentState, targetSectionId);
      this.state = updatedState;

      // Reset the unconfirmable-field loop-breaker on this backend-initiated section
      // switch too (bd polyglot-pdf-0y7) -- the other section transitions
      // (startSection/switchToSection) also clear it. This path keeps the SAME
      // WebSocket open, so handleOpen's reset does not fire. NOTE the reset sits HERE
      // (after the early-return guards, once the switch has actually been applied to
      // this.state) rather than at function entry like startSection/switchToSection:
      // a section switch that fails validation must not clear a still-valid in-progress
      // streak. Defense-in-depth: the streak is keyed on field_id and field ids are
      // globally unique per schema, so a cross-section carry-over can't currently
      // false-trip -- this just removes the reliance on the id-uniqueness invariant.
      // Also clears the session-wide re-prompt cap (bd polyglot-pdf-r2hy): a section
      // switch is genuine progress, so the model earns a fresh budget.
      this.resetUnconfirmableTracking();
      // Same reasoning for the AI-value validation-reject loop-breaker (bd
      // polyglot-pdf-wpw.3): clear it here, after the switch is applied.
      this.resetValidationRejectTracking();

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

    // The switch is confirmed: release the re-entrancy guard + disarm the
    // watchdog (bd polyglot-pdf-aun) BEFORE settling the status to connected.
    this.completeSectionSwitch();

    // Update status
    this.setStatus('connected', "handleSectionSwitched");

    // State was already updated in handlePrepareSectionSwitchRequest
    // Now trigger UI update to show the new section
    if (this.callbacks.onSectionChanged) {
      this.callbacks.onSectionChanged();
    }

    // Also save the updated state
    SchemaFormStateManager.save(this.state);
  }

  /**
   * Handle confirm_field request from backend (Gemini called confirm_field tool)
   */
  private async handleConfirmFieldRequest(message: any): Promise<void> {
    const { field_id, confirmation_method, request_id } = message;

    console.log('[WebFormConnection] Confirming field:', field_id, 'method:', confirmation_method);

    // Refresh before reading OR writing (bd polyglot-pdf-pjws). This handler
    // ends in SchemaFormStateManager.save(this.state), so running it on a stale
    // in-memory copy does not merely read the wrong values -- it PERSISTS them,
    // reverting any field written outside this object since the last sync -- a
    // value the user typed on screen, or anything a sibling handler persisted.
    // (The originally-reported symptom was selectedLanguage being written back;
    // that framing assumed mid-session language switching, which is unsupported
    // -- bd polyglot-pdf-87a9. The stale-write class is real either way, and is
    // what this refresh fixes.)
    //
    // fieldValues are MERGED with in-memory winning, NOT replaced. The rest of
    // this handler is gated on the field holding a usable VALUE, and a plain
    // overwrite could drop an entry that exists only in memory, turning a
    // legitimate confirm into a spurious 'no_value' refusal that the
    // loop-breaker escalates into a re-prompt.
    //
    // This merge is deliberately CONSERVATIVE, not correct-in-general: where the
    // two maps disagree it preserves dev's existing behavior (this handler read
    // `this.state` unconditionally before), so the pjws language fix does not
    // also change which field VALUE wins. It does NOT make the divergence safe.
    // SchemaForm.tsx's handleFieldChange is a real production writer that
    // persists through SchemaFormStateManager without touching this object, so
    // an on-screen edit can lose to a stale in-memory entry here -- pre-existing
    // on dev, out of scope for these beads, and filed as bd polyglot-pdf-uw3w
    // (with the `[]`-alias resurrection it enables as bd polyglot-pdf-3irc).
    // Fixing the write-ownership properly is that bead's job, not a side effect
    // of a language fix.
    const persistedAtEntry = SchemaFormStateManager.load();
    if (persistedAtEntry) {
      this.state = {
        ...persistedAtEntry,
        fieldValues: {
          ...persistedAtEntry.fieldValues,
          ...this.state.fieldValues,
        },
      };
    }

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
    // NOTE on empty arrays (fresh-eyes PR #145 rounds 4+5): an empty `[]` on a
    // checkbox group is deliberately NOT treated as unusable here. A blank OPTIONAL
    // group ("the user selected none") is a legitimate, confirmable end state;
    // rejecting it would STRAND the form -- computeNextField (navigation.ts) counts
    // `[]` as a value, so the field would be re-offered forever while confirm refused
    // it (a deadlock). The REQUIRED case is already handled upstream: validateField
    // treats `[]` as empty, so a required-blank fails the required check at the apply
    // gate and never lands. So hasUsableValue keeps the null/undefined/'' notion only.
    //
    // NOTE on empty strings for optional fields (bd polyglot-pdf-w3ic): the same
    // reasoning applies to text/select/etc. fields whose schema marks them NOT
    // required. An intentionally blank optional field (e.g. "I have no middle name")
    // is a legitimate, confirmable end state -- '' means the user explicitly said
    // this does not apply, and Gemini already called update_form_fields with ''.
    // Required fields can never arrive here with '' because validateField rejects ''
    // for required fields at the applyAiValueWithValidation gate, so the value
    // never lands. Therefore, treat '' as usable when the field is not required.
    const fieldSchema = this.state.schema.fields.find(f => f.id === field_id);
    const fieldIsRequired = fieldSchema?.validation?.required === true;
    const hasUsableValue =
      fieldValue !== null && fieldValue !== undefined &&
      (fieldValue !== '' || !fieldIsRequired);

    if (!hasUsableValue) {
      if (field_id === this.lastUnconfirmableFieldId) {
        this.unconfirmableConfirmCount += 1;
      } else {
        // A different field -- reset the PER-FIELD counters only. Deliberately do
        // NOT reset unconfirmableSessionPromptCount here (bd polyglot-pdf-r2hy): the
        // session-wide cap MUST survive field changes, or cross-field confirm spin
        // (A,A -> B,B -> ...) would re-arm the per-field re-prompt on every switch
        // and never engage the cap. Use resetUnconfirmableTracking() (which clears
        // the session counter too) ONLY at (re)connect / section switch / a
        // successful confirm of the stuck field -- never on a plain field change.
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
      // The SESSION cap (bd polyglot-pdf-r2hy) is NOT reset on a field change, so a
      // model alternating between different empty fields -- which resets the
      // per-field counters every switch -- is still bounded: once the total
      // re-prompts hit SESSION_CAP we stop re-prompting regardless of field.
      const sessionCapReached =
        this.unconfirmableSessionPromptCount >= WebFormConnection.UNCONFIRMABLE_SESSION_CAP;
      if (
        this.unconfirmableConfirmCount >= WebFormConnection.UNCONFIRMABLE_CONFIRM_LIMIT &&
        this.unconfirmableRepromptCount < WebFormConnection.UNCONFIRMABLE_REPROMPT_CAP &&
        !sessionCapReached
      ) {
        const field = this.state.schema.fields.find(f => f.id === field_id);
        const spokenName = field?.spoken_name || field?.name || field_id;
        this.unconfirmableConfirmCount = 0;
        this.unconfirmableRepromptCount += 1;
        this.unconfirmableSessionPromptCount += 1;
        const capped =
          this.unconfirmableRepromptCount >= WebFormConnection.UNCONFIRMABLE_REPROMPT_CAP ||
          this.unconfirmableSessionPromptCount >= WebFormConnection.UNCONFIRMABLE_SESSION_CAP;
        console.error(
          '[WebFormConnection] Breaking confirm/next-field loop for unconfirmable field:',
          field_id,
          capped ? '(final re-prompt -- giving up after this)' : ''
        );
        // Re-prompt Gemini (via send_prompt) to collect the value rather than
        // confirming an empty field. completion_message -> send_prompt carries a
        // custom instruction; the fixed-script recovery_prompt channel (bd zy3)
        // would not fit this field-specific message.
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
      // Ack the synchronous confirm round-trip (bd polyglot-pdf-wpw.2): tell the
      // backend the confirm was NOT recorded so it returns success:false to Gemini
      // in-band, instead of the old fire-and-forget that always read as success.
      // `reason` is a fixed category token, never the field value (PII-safe). This
      // is in ADDITION to the client-side re-prompt/onError loop-breaker above.
      this.sendConfirmFieldResponse(request_id, false, 'no_value');
      return;
    }

    // Field has a usable value -- record the confirmation in state.
    this.state = SchemaFormStateManager.confirmField(
      this.state,
      field_id,
      confirmation_method === 'verbal' ? 'ai_voice' : 'manual_edit'
    );
    SchemaFormStateManager.save(this.state);

    // AUTO-DETECT SECTION COMPLETION. Compute this BEFORE acking so we can tell the
    // backend whether a section boundary is imminent (bd polyglot-pdf-njvh). If this
    // was the last unconfirmed field in the section AND there is a NEXT section, the
    // FE is about to tear down the socket for switchToSection below -- so the
    // backend's post-confirm request_next_field_hint round-trip would race that
    // teardown and time out, making Gemini emit a spurious 'do NOT assume the form is
    // complete' prompt right as the section IS correctly auto-advancing. We flag
    // section_complete in the ack so the backend SKIPS that doomed hint request (the
    // new section's first-field hint arrives via the section-switch flow anyway).
    //
    // CRITICAL: gate this on a NEXT section EXISTING, not merely "current section
    // done". When the last field of the LAST section is confirmed there is no next
    // section -- the FE fires onFormComplete (no switchToSection, no socket teardown),
    // and the backend SHOULD request the hint so it gets the genuine
    // "All fields confirmed" answer. Setting section_complete there would wrongly
    // suppress that. So: section_complete == (current section done) AND (a next
    // section exists) -- exactly the switchToSection branch below.
    const nextField = computeNextField(this.state, { skipConfirmed: true });
    // Continuous-session mode (bd polyglot-pdf-x8rt): there are NO sections to
    // advance to -- computeNextField spans the whole form, so !nextField means the
    // WHOLE FORM is done, not a section boundary. Force nextSectionForAck to null so
    // sectionComplete stays false (no spurious section_complete WS message) and the
    // completion branch below takes the form-complete path (onFormComplete), not the
    // section-switch path. Without this, currentSectionId stays pinned at section 1
    // while getNextSection reports a real "section 2", misdetecting whole-form
    // completion as a section boundary (fresh-eyes gap 2).
    const nextSectionForAck = (nextField || this.continuousSessionEnabled)
      ? null
      : SchemaFormStateManager.getNextSection(this.state);
    const sectionComplete = !nextField && !!nextSectionForAck;

    // Ack the synchronous confirm round-trip (bd polyglot-pdf-wpw.2): the confirm
    // was recorded, so the backend reports success and advances. Carry
    // section_complete so the backend can skip the racing next-field-hint at a
    // boundary (bd polyglot-pdf-njvh).
    this.sendConfirmFieldResponse(request_id, true, undefined, sectionComplete);

    // B4 (bd polyglot-pdf-jnjj.16): proactively emit section_complete the moment the
    // last field of the current section is confirmed and a next section exists --
    // the boundary where the cheap-model validator should run (a SECOND-PASS net,
    // validation-delegation.md contract 4). This is a SEPARATE top-level event from
    // the section_complete SUB-FIELD on the confirm ack above (that sub-field just
    // suppresses the backend's racing next-field-hint, bd njvh); both ride the same
    // `sectionComplete` boolean by design.
    // Fire-and-forget: the validator round-trip is async and must not block the user
    // (criterion 3); B5 (jnjj.17) consumes the verdict and gates the switch.
    //
    // EXACTLY ONE event per boundary (Codex PR #271): a duplicate confirm_field for
    // the same last field, arriving while the first boundary is still resolving,
    // would otherwise re-run this block and emit a second section_complete. Two
    // states cover the whole window: `switchInFlight` (the switch is actually
    // running) and, since B5 (jnjj.17) gates the switch on the validator round-trip,
    // `pendingSectionSwitch` (the switch is PARKED waiting for the verdict -- a window
    // where switchInFlight is not yet set). Guard on both so the duplicate confirm is
    // suppressed whether the first boundary is parked at the validator or already
    // switching.
    if (sectionComplete && !this.switchInFlight && !this.pendingSectionSwitch) {
      this.send({
        type: 'section_complete',
        section_id: this.state.currentSectionId,
        fields: this.buildValidatorFields(
          SchemaFormStateManager.getCurrentSectionFields(this.state)
        ),
      });
    }

    // B4 (bd polyglot-pdf-jnjj.16): check whole-form completeness on EVERY confirm,
    // not only in the last-section/no-next-field branch below (Codex PR #271).
    // isFormComplete and computeNextField are both required-agnostic (they iterate
    // the same "every shown field confirmed" set, bd polyglot-pdf-taw3), so the two
    // agree on completion -- but the `!nextField` branch below only runs on the
    // last section. Calling maybeEmitFormComplete here covers whole-form completion
    // reached on any confirm. It is guarded (fires only when isFormComplete AND the
    // snapshot changed), so it is a no-op for an incomplete form and idempotent vs.
    // the branch below.
    this.maybeEmitFormComplete();
    // W2 (bd polyglot-pdf-kxkw): stride-window validator check on the same
    // state-change seam (guarded: sends only newly-eligible, unsent windows).
    this.maybeEmitValidateWindows();

    // Confirm took -- clear pending unconfirmable tracking. A successful confirm of
    // the stuck field is genuine progress, so it restores the session-wide re-prompt
    // budget too (bd polyglot-pdf-r2hy; mirrors the wpw.3 "stuck field validated ->
    // reset session cap" rule). We only reset on confirming the TRACKED field: an
    // unrelated success must NOT refill the budget, or [empty-A, good-B] alternation
    // would reset the cross-field cap forever (the wpw.3 fresh-eyes-round-4 lesson).
    if (field_id === this.lastUnconfirmableFieldId) {
      this.resetUnconfirmableTracking();
    }

    console.log('[WebFormConnection] [check] Section completion check:', {
      currentSectionId: this.state.currentSectionId,
      nextFieldInCurrentSection: nextField?.id || 'NONE',
      allFieldsConfirmed: !nextField
    });

    if (!nextField) {
      // All fields in current section are confirmed! Reuse the next-section lookup
      // already done above for the section_complete ack flag (bd polyglot-pdf-njvh).
      const nextSection = nextSectionForAck;

      console.log('[WebFormConnection] [check] Next section lookup:', {
        currentSectionId: this.state.currentSectionId,
        nextSectionId: nextSection?.id || 'NONE',
        nextSectionLabel: nextSection?.label || 'N/A'
      });

      if (nextSection && this.switchInFlight) {
        // A switch is already running (e.g. a DUPLICATE confirm of the same last
        // field arrived before the first auto-switch resolved). Re-attempting it
        // would throw in switchToSection (Codex PR #271); skip cleanly -- the first
        // switch is already advancing this boundary.
        console.log('[WebFormConnection] [skip] Section switch already in flight; ignoring duplicate boundary confirm.');
      } else if (nextSection) {
        console.log('[WebFormConnection] [OK] Section complete! Gating switch on the validator:', nextSection.id);

        // Trigger automatic section switch (uses backend-side reconnect).
        // B4 (bd polyglot-pdf-jnjj.16): routed through proceedSectionSwitch() -- a
        // single interceptable seam. B5 (jnjj.17) gates this call on the validator
        // round-trip (clean verdict or fail-OPEN timeout) so the verdict cannot arrive
        // after Gemini has restarted into the next section (contract 4's ordering).
        //
        // CRITICAL (Opus PR #275): the audio teardown (clear queue, stop mic capture)
        // moved INTO doSectionSwitch -- it must run ONLY when the switch actually
        // proceeds, NOT here. Stopping the mic before the gate resolved meant a
        // CONFLICT verdict (which HOLDS the section so the model can voice the steer)
        // left the user with a dead mic and no way to answer -- a deadlock. Now the
        // mic stays live while the steer plays out, and the teardown happens just
        // before the real switch.
        await this.proceedSectionSwitch(nextSection.id);
      } else {
        console.log('[WebFormConnection] [done] Form complete!');
        // B4: form_complete for this last-section completion was already emitted by
        // the unconditional maybeEmitFormComplete() above (it covers every confirm,
        // Codex PR #271). Just notify the UI here.
        if (this.callbacks.onFormComplete) {
          this.callbacks.onFormComplete();
        }
      }
    }

    // The success ack was already sent above, right after the confirm was
    // recorded (bd polyglot-pdf-wpw.2) -- the backend uses it to complete the
    // synchronous confirm_field round-trip.
  }

  /**
   * Handle skip_field request from backend (Gemini called the skip_field tool,
   * bd polyglot-pdf-7yra). The user asked to skip a REQUIRED field they cannot
   * answer right now. Unlike confirm_field there is NO usable-value gate -- the
   * whole point is to record an EMPTY field as intentionally skipped
   * (markFieldSkipped: skipped flag, empty value, satisfies the section gate,
   * prints blank on the PDF). After recording, this advances exactly like a
   * successful confirm (a skipped field satisfies the section).
   */
  private async handleSkipFieldRequest(message: any): Promise<void> {
    const { field_id, request_id } = message;

    console.log('[WebFormConnection] Skipping field:', field_id);

    // A skip is a SYNCHRONOUS round-trip: without a request_id we cannot ack, so
    // the backend future would time out and tell Gemini the skip failed. Do NOT
    // mutate state or advance in that case, or the FE would silently skip+advance
    // while the backend believes it failed (a divergence). The real backend always
    // sends request_id; this guards a malformed message (fresh-eyes review).
    if (!request_id) {
      console.warn('[WebFormConnection] skip_field with no request_id -- ignoring (cannot ack).');
      return;
    }

    // Refresh before reading OR writing -- the same rule as the confirm handler
    // (bd polyglot-pdf-pjws). This handler also ends in
    // SchemaFormStateManager.save(this.state), so on a stale in-memory copy it
    // does not merely read wrong values, it PERSISTS them: a skip landing after
    // it reverts whatever was written outside this object since the last sync.
    // A skip is as routine a per-turn tool call as a confirm; both final Opus
    // outer reviews found this sibling path independently. (Originally written
    // up as a language-clobber; mid-session language switching is unsupported --
    // bd polyglot-pdf-87a9 -- but the stale-write class is real regardless.)
    //
    // fieldValues are MERGED, not replaced, and in-memory wins. Everything below
    // is gated on a DATA-LOSS guard (markFieldSkipped BLANKS the value), and a
    // plain overwrite would drop an entry that exists only in memory, letting a
    // skip through on a field the guard would have refused (pinned by
    // webFormConnection.skipfield.test.ts, which caught exactly that).
    //
    // Same caveat as the confirm handler above: this is CONSERVATIVE, preserving
    // dev's behavior where the maps disagree, not a fix for the divergence. The
    // opposite direction has its own failure -- an on-screen edit persisted by
    // SchemaForm.tsx can lose to a stale in-memory entry, so a skip can still
    // blank a real answer. Pre-existing on dev and out of scope here; filed as
    // bd polyglot-pdf-uw3w / polyglot-pdf-3irc.
    const persistedAtEntry = SchemaFormStateManager.load();
    if (persistedAtEntry) {
      this.state = {
        ...persistedAtEntry,
        fieldValues: {
          ...persistedAtEntry.fieldValues,
          ...this.state.fieldValues,
        },
      };
    }

    const field = this.state.schema.fields.find(f => f.id === field_id);
    if (!field) {
      // Unknown field id -- cannot skip. Ack not-recorded so the backend tells
      // Gemini to re-ask rather than confabulating a skip. `reason` is a fixed
      // category token, never a field value (PII-safe).
      console.warn('[WebFormConnection] skip_field for unknown field:', field_id);
      this.sendSkipFieldResponse(request_id, false, 'unknown_field');
      return;
    }

    // DATA-LOSS GUARD (fresh-eyes review): markFieldSkipped BLANKS the value, so a
    // skip aimed at an already-FILLED field would silently destroy a real answer
    // (and mark it confirmed, so it is never re-prompted). Unlike confirm_field --
    // which only sets confirmed:true and can never blank a value -- skip is a new
    // destructive path, and the default non-DTI mode has no current-field coercion
    // to catch a wrong/misheard field_id. So refuse to skip a field that already
    // holds a usable value: ack recorded:false (reason 'already_filled') and let
    // the model clear it intentionally (update_form_fields "") or move on. `[]`
    // (an empty checkbox group) is NOT usable -> still skippable.
    // Read via the SAME `[]`-alias fallback the confirm/update/validator paths use:
    // a checkbox-group value may sit under the bracketed OR unbracketed variant
    // (Gemini drops/adds the bracket, bd polyglot-pdf-5k52). An exact-key-only read
    // would MISS an aliased filled value, the guard would pass, and markFieldSkipped
    // would shadow that real answer -- the exact data loss this guard prevents
    // (fresh-eyes review round 2).
    const existing = (
      this.state.fieldValues[field_id] ??
      this.state.fieldValues[
        field_id.endsWith('[]') ? field_id.slice(0, -2) : field_id + '[]'
      ]
    )?.value;
    const alreadyFilled =
      existing !== null && existing !== undefined && existing !== '' &&
      !(Array.isArray(existing) && existing.length === 0);
    if (alreadyFilled) {
      console.warn('[WebFormConnection] skip_field refused -- field already has a value:', field_id);
      this.sendSkipFieldResponse(request_id, false, 'already_filled');
      return;
    }

    // Record the skip in state (empty value + skipped flag, counts as confirmed
    // so it does not re-prompt). ai_voice: the skip came through the voice tool.
    this.state = SchemaFormStateManager.markFieldSkipped(this.state, field_id, 'ai_voice');
    SchemaFormStateManager.save(this.state);

    // A skipped field satisfies the section, so advance exactly like a confirm.
    // Compute the next field / section boundary BEFORE acking (mirrors the
    // confirm path's section_complete handling, bd polyglot-pdf-njvh).
    const nextField = computeNextField(this.state, { skipConfirmed: true });
    const nextSectionForAck = (nextField || this.continuousSessionEnabled)
      ? null
      : SchemaFormStateManager.getNextSection(this.state);
    const sectionComplete = !nextField && !!nextSectionForAck;

    // Ack the synchronous skip round-trip: recorded, carrying section_complete so
    // the backend can skip the racing next-field-hint at a section boundary.
    this.sendSkipFieldResponse(request_id, true, undefined, sectionComplete);

    // Emit section_complete (the cheap-model validator boundary) exactly as the
    // confirm path does -- guarded so a boundary fires once.
    if (sectionComplete && !this.switchInFlight && !this.pendingSectionSwitch) {
      this.send({
        type: 'section_complete',
        section_id: this.state.currentSectionId,
        fields: this.buildValidatorFields(
          SchemaFormStateManager.getCurrentSectionFields(this.state)
        ),
      });
    }

    // Whole-form completeness check on every skip (idempotent / guarded), same as
    // the confirm path.
    this.maybeEmitFormComplete();
    // W2 (bd polyglot-pdf-kxkw): stride-window validator check on the same
    // state-change seam (guarded: sends only newly-eligible, unsent windows).
    this.maybeEmitValidateWindows();

    // A skip of the tracked unconfirmable field is genuine progress -- restore the
    // re-prompt budget (mirrors the confirm path).
    if (field_id === this.lastUnconfirmableFieldId) {
      this.resetUnconfirmableTracking();
    }

    if (!nextField) {
      const nextSection = nextSectionForAck;
      if (nextSection && this.switchInFlight) {
        console.log('[WebFormConnection] [skip] Section switch already in flight; ignoring duplicate boundary skip.');
      } else if (nextSection) {
        await this.proceedSectionSwitch(nextSection.id);
      } else {
        if (this.callbacks.onFormComplete) {
          this.callbacks.onFormComplete();
        }
      }
    }
  }

  /**
   * Field-level navigation (bd polyglot-pdf-jnjj.36): the AI's switch_to_field
   * tool asks the client to make a SPECIFIC field current -- e.g. to correct an
   * earlier answer, or to act on an ask_secretary answer that named a field.
   * The client owns all field state, so it resolves the identifier (field_id
   * or spoken name, whole schema -- deliberately NOT the section-scoped lookup,
   * bd polyglot-pdf-lt9z), pins the field so every next-field consumer follows
   * (computeNextField pin priority), moves UI focus, and acks with the target's
   * hint + (DTI) schema so the backend can render its guidance. Synchronous
   * round-trip like skip_field: no request_id means no ack path, so bail.
   */
  private handleSwitchFieldRequest(message: any): void {
    const { field: identifier, request_id } = message;

    if (!request_id) {
      console.warn('[WebFormConnection] switch_field with no request_id -- ignoring (cannot ack).');
      return;
    }

    // Refresh from the persisted snapshot first (same staleness rule as
    // sendManualFieldUpdate, bd polyglot-pdf-ezg2).
    const persisted = SchemaFormStateManager.load();
    if (persisted) this.state = persisted;

    const fieldId = SchemaFormStateManager.resolveFieldForNavigation(this.state, identifier || '');
    if (!fieldId) {
      console.warn('[WebFormConnection] switch_field: no field matches the identifier.');
      // Carry nearest navigable candidates so the model can pick an exact name
      // and retry, instead of guessing another id (bd polyglot-pdf-3vby).
      const candidates = SchemaFormStateManager.suggestNavigationCandidates(
        this.state, identifier || ''
      );
      this.sendSwitchFieldResponse(request_id, false, { reason: 'unknown_field', candidates });
      return;
    }

    const field = this.state.schema.fields.find(f => f.id === fieldId)!;

    // A conditionally-hidden field is not askable -- navigating to it would
    // strand the conversation on a question the form does not show.
    // shouldShowField ALONE (bd polyglot-pdf-ubam): the former `field.hidden ||`
    // refused navigation to a `hidden: true` field whose show_if is SATISFIED,
    // which the form DOES show -- so the model was told 'hidden' about a
    // question sitting visible and required on screen.
    if (!shouldShowField(field, this.state.fieldValues, this.state.schema.fields)) {
      this.sendSwitchFieldResponse(request_id, false, { reason: 'hidden', field_id: fieldId });
      return;
    }

    // Section-scoped modes (non-continuous): the Gemini session only carries
    // the current section, so an out-of-section target is unreachable without
    // a section switch. Tell the backend which section holds it so the model
    // can switch_section first (sections and fields stay distinct units,
    // CLAUDE.md scar #5).
    if (!this.continuousSessionEnabled) {
      const owningSection = this.state.schema.sections?.find(s => s.fields?.includes(fieldId));
      if (owningSection && owningSection.id !== this.state.currentSectionId) {
        this.sendSwitchFieldResponse(request_id, false, {
          reason: 'other_section',
          field_id: fieldId,
          section_label: owningSection.label,
          section_order: owningSection.order,
        });
        return;
      }
    }

    // Pin the field: computeNextField now returns it first (until confirmed/
    // skipped), so the hint, the DTI drip, and any stall-recovery all point at
    // it. A pin on an already-CONFIRMED field is dormant until the model
    // updates the value (which resets confirmed) -- the correction flow.
    this.state = SchemaFormStateManager.pinField(this.state, fieldId);

    // Move UI focus immediately (the same callback the next-field flow uses).
    if (this.callbacks.onNextField) {
      this.callbacks.onNextField(fieldId);
    }

    // Ack with the TARGET's hint + (DTI) schema -- not computeNextField's pick,
    // which would skip a confirmed target the model is navigating back to
    // correct. Keep the recovery-prompt hint current, same as the other
    // next-field producers.
    const hint = formatNextFieldHint(field, getFieldOrder(this.state, fieldId) || undefined,
        // refreshed at handler entry -- no second parse.
        this.sessionLanguageFor(true));
    sessionStorage.setItem('vff_last_field_hint', hint);
    // Read via the `[]`-alias fallback (bd 5k52 class): a checkbox-group's
    // entry may sit under the bracket variant; a bare read would misreport a
    // filled/confirmed field as unanswered and degrade the correction flow to
    // a fresh fill (outer review on this bead).
    const entry = readFieldEntryWithAlias(this.state.fieldValues, fieldId);
    const currentValue = entry?.value;
    // An EMPTY checkbox-group ([]) is not a value -- treat it as unanswered so the
    // ack does not tell the model "it already holds an unconfirmed value" and ride
    // value:[] (the model would read back nothing). Mirrors the skip path's guard
    // (handleSkipFieldRequest, bd polyglot-pdf-7yra) so the two agree (bd
    // polyglot-pdf-luju nit 1).
    const hasValue =
      currentValue !== null && currentValue !== undefined && currentValue !== '' &&
      !(Array.isArray(currentValue) && currentValue.length === 0);
    this.sendSwitchFieldResponse(request_id, true, {
      field_id: fieldId,
      spoken_name: field.spoken_name || field.name,
      next_field_hint: hint,
      already_confirmed: !!entry?.confirmed,
      has_value: hasValue,
      // The current value rides the ack so the model can read it back to the
      // user (same Gemini trust boundary as ask_secretary; never logged).
      ...(hasValue ? { value: currentValue } : {}),
      ...(this.dtiModeEnabled
        ? { next_field_schema: getFieldSchema(fieldId, this.state.schema) }
        : {}),
    });
  }

  private sendSwitchFieldResponse(
    request_id: string,
    found: boolean,
    extra: Record<string, unknown> = {}
  ): void {
    this.send({
      type: 'switch_field_response',
      request_id,
      found,
      ...extra,
    });
  }

  /**
   * B4 (bd polyglot-pdf-jnjj.16): the section auto-switch seam. Extracted from the
   * confirm handler so the switch is INTERCEPTABLE without touching that handler.
   * In B4 it runs the switch immediately (behavior identical to the prior inline
   * call). B5 (jnjj.17) overrides WHEN this fires -- holding it until the validator
   * verdict returns (clean) or the fail-OPEN timeout elapses -- so the verdict
   * cannot land after Gemini has already restarted into the next section (the
   * ordering rule, validation-delegation.md contract 4). Keep all switch side
   * effects (audio teardown above) at the call site; this method owns only the
   * switch itself, so the gate B5 adds wraps one call.
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  private async proceedSectionSwitch(sectionId: string): Promise<void> {
    // Continuous-session mode (bd polyglot-pdf-x8rt): the whole form is one session,
    // so there is no section to advance to -- suppress the client auto-advance
    // entirely. computeNextField spans the whole form in this mode, so it never
    // reports "section complete, next section available" that would reach here;
    // this guard is the belt-and-suspenders backstop.
    if (this.continuousSessionEnabled) {
      console.log('[WebFormConnection] Continuous mode: suppressing section advance to', sectionId);
      return;
    }

    // B5 (bd polyglot-pdf-jnjj.17): gate the switch on the validator round-trip
    // (contract 4 ordering). Park the switch and wait for a validation_result:
    //   - clean verdict   -> resolvePendingSectionSwitch -> switch runs;
    //   - conflict verdict -> cancelPendingSectionSwitch sets the gate's cancelled flag,
    //                         resolves the gate WITHOUT switching (stay in-section so
    //                         the live model can steer; the switch happens on a later
    //                         clean boundary);
    //   - no verdict in VALIDATOR_GATE_TIMEOUT_MS -> fail-OPEN: switch runs unchecked
    //     (a validator/socket outage must never strand the user mid-form).
    // A DUPLICATE confirm of the same last field, arriving while the first boundary's
    // gate is still parked, must NOT re-park (Codex PR #275): re-parking would reset
    // the fail-OPEN timer (delaying the documented advance indefinitely under repeated
    // duplicates) and the second confirm emitted NO new validation_result to resolve
    // it. The original gate owns the boundary; this call no-ops. (The section_complete
    // emit was already suppressed for this duplicate by the pendingSectionSwitch guard
    // in the confirm handler.)
    if (this.pendingSectionSwitch) {
      console.log('[WebFormConnection] [validator] switch gate already parked for this boundary; ignoring duplicate.');
      return;
    }

    // Each invocation owns its gate object; `gate` is captured here and its
    // `cancelled` flag is read after the await, so a teardown/cancel of THIS gate
    // cannot make a later switch fire (and vice versa).
    const gate: PendingSectionSwitch = {
      sectionId,
      resolve: () => {},
      timer: undefined as unknown as ReturnType<typeof setTimeout>,
      cancelled: false,
    };
    await new Promise<void>((resolve) => {
      gate.resolve = resolve;
      gate.timer = setTimeout(() => {
        if (this.pendingSectionSwitch === gate) {
          console.warn('[WebFormConnection] [validator] gate timed out -- failing OPEN, advancing unchecked');
          this.pendingSectionSwitch = null;
          gate.resolve();
        }
      }, WebFormConnection.VALIDATOR_GATE_TIMEOUT_MS);
      this.pendingSectionSwitch = gate;
    });

    // A CONFLICT verdict (or teardown/eviction) cancelled THIS gate -> do not switch.
    if (gate.cancelled) {
      console.log('[WebFormConnection] [validator] switch deferred -- conflict/teardown held this boundary in section.');
      return;
    }
    // An AI-INITIATED switch (Gemini's switch_section -> prepare_section_switch ->
    // handlePrepareSectionSwitchRequest) may have claimed this same boundary WHILE we
    // were parked on the validator gate (bd polyglot-pdf-6job). That path keeps the
    // SAME socket open and is authoritative; running our reconnect-based switch now
    // would tear down audio/mic and then THROW in switchToSection ("a section switch
    // is already in progress"), killing the session. The switchInFlight check at the
    // confirm-handler call site (line ~1612) ran BEFORE the park, so it could not see
    // a guard claimed during the await -- re-check it here, after the await, and skip
    // cleanly. (handlePrepareSectionSwitchRequest also cancels this gate when it finds
    // one parked; this is defense-in-depth for the gate-already-resolved ordering.)
    if (this.switchInFlight) {
      console.log('[WebFormConnection] [skip] AI-initiated switch claimed this boundary while parked; skipping client auto-advance.');
      return;
    }
    // Resolved clean or failed OPEN -> run the switch.
    await this.doSectionSwitch(sectionId);
  }

  /**
   * B5 (bd polyglot-pdf-jnjj.17): the one place the parked section switch actually
   * runs (after the validator gate resolved clean or failed OPEN). Separated so the
   * gate logic in proceedSectionSwitch reads cleanly.
   */
  private async doSectionSwitch(sectionId: string): Promise<void> {
    // Audio teardown happens HERE -- only when the switch actually proceeds (clean
    // verdict or fail-OPEN), never on a conflict-hold (Opus PR #275). Stop overlapping
    // playback from the old session and stop mic capture; the new session restarts
    // capture after the reconnect.
    console.log('[WebFormConnection] [stop] Stopping audio queue + capture before section switch');
    this.audioQueue = [];
    this.isProcessingAudio = false;
    if (this.callbacks.onStopCapture) {
      this.callbacks.onStopCapture();
    }
    await this.switchToSection(sectionId, '');
  }

  /**
   * B5 (bd polyglot-pdf-jnjj.17) + W3 (bd polyglot-pdf-pr3i): handle the validator
   * verdict pushed from the backend (validation_result envelope, contract 1;
   * REPORT-ONLY since W3). Sent for EVERY validated boundary -- clean ({conflicts:
   * []}) or with conflicts:
   *   - CLEAN  -> resolve the parked section-switch gate (resume the auto-advance);
   *     enqueue nothing, drain nothing (no voice turn on an all-clear).
   *   - CONFLICT -> (a) ENQUEUE the conflicts into the persisted
   *     validatorFindingsQueue (dedup by field-id set) and, if the queue grew, DRAIN
   *     immediately (drainFindings -> drain_findings); the steer is composed+injected
   *     by the backend on the drain, NOT here, and the fields are marked steered +
   *     consumed only on the drain_findings_result (handleDrainFindingsResult) -- so
   *     an un-delivered steer keeps the finding queued to retry and a field is never
   *     marked steered for a steer the model never heard. (b) CANCEL the parked switch
   *     (stay in-section so the model can voice the correction). The switch resumes on
   *     a later clean boundary.
   * The form_complete boundary has no parked switch (last boundary); the same
   * enqueue+drain path runs, just without a switch to cancel.
   */
  private handleValidationResult(message: any): void {
    const conflicts = Array.isArray(message?.conflicts) ? message.conflicts : [];
    if (conflicts.length === 0) {
      // Clean -> resume any parked section switch. ENQUEUE nothing, DRAIN nothing:
      // no voice turn is spent on an all-clear (W3 finding-driven cadence).
      this.resolvePendingSectionSwitch();
      return;
    }

    // W3 (bd polyglot-pdf-pr3i): the result is REPORT-ONLY -- the backend did NOT
    // inject a steer. ENQUEUE the surviving conflicts (dedup by field-id set) into the
    // persisted queue, then DRAIN immediately: send drain_findings so the backend
    // composes+injects one steer for the whole queue. The fields are marked steered +
    // consumed only when the drain RESULT confirms delivery (handleDrainFindingsResult)
    // -- so an un-delivered steer keeps the finding queued to retry, and a field is
    // never marked steered for a steer the model never heard.
    const findings: ValidatorFinding[] = [];
    for (const c of conflicts) {
      const ids = c && Array.isArray(c.field_ids) ? c.field_ids.filter((i: any) => typeof i === 'string') : [];
      if (ids.length === 0) continue;
      findings.push({
        field_ids: ids,
        reason: typeof c.reason === 'string' ? c.reason : '',
        field_names: (c.field_names && typeof c.field_names === 'object') ? c.field_names : {},
      });
    }
    const before = this.state.validatorFindingsQueue.length;
    this.state = SchemaFormStateManager.enqueueValidatorFindings(this.state, findings);
    // Cancel the parked switch (if any): stay in-section to let the steer play out.
    this.cancelPendingSectionSwitch();
    // Only drain if the queue actually grew (a fully-duplicate result would otherwise
    // re-send an in-flight drain). A non-empty queue is drained right away.
    if (this.state.validatorFindingsQueue.length > before) {
      this.drainFindings();
    }
  }

  /**
   * W3 (bd polyglot-pdf-pr3i): emit `drain_findings` carrying the CURRENT queued
   * findings so the backend composes + injects one steer. Finding-driven: called
   * the moment the queue grows (handleValidationResult) and on reconnect if a queue
   * survived (handleSessionReady). Only on an OPEN socket -- otherwise the findings
   * stay queued (persisted) and a later drain retries them. The findings are NOT
   * consumed here; consumption waits for the drain RESULT (delivery confirmation).
   */
  private drainFindings(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    // One drain at a time: a second drain would re-send findings the in-flight drain
    // is already voicing (double-steer). The drain_findings_result handler re-drains
    // if the queue still has anything once the in-flight one resolves.
    if (this.drainInFlight) return;
    const queue = this.state.validatorFindingsQueue;
    if (!queue || queue.length === 0) return;
    this.drainInFlight = true;
    this.send({
      type: 'drain_findings',
      // Each finding carries field_ids + reason + field_names (the composer needs the
      // names); send the queue as-is.
      conflicts: queue.map(f => ({
        field_ids: f.field_ids,
        reason: f.reason,
        field_names: f.field_names,
      })),
    });
  }

  /**
   * W3 (bd polyglot-pdf-pr3i): the backend's drain_findings_result -- the conflicts
   * whose steer ACTUALLY DELIVERED into the live session. Mark their fields steered
   * (max-resteer marker, so the backend suppresses re-steering them) and CONSUME them
   * from the queue. Un-delivered conflicts (dead session -> absent here) stay queued
   * to retry on the next drain.
   */
  private handleDrainFindingsResult(message: any): void {
    // The in-flight drain resolved (delivered or not) -> clear the guard.
    this.drainInFlight = false;
    const delivered = Array.isArray(message?.conflicts) ? message.conflicts : [];
    if (delivered.length === 0) {
      // UNDELIVERED (dead live session). Do NOT immediately re-drain -- the WS is
      // still open, so a re-drain would spin against the dead session. The findings
      // stay queued (persisted) and retry when the session recovers: a dead live
      // session surfaces as gemini_session_dropped -> reconnect -> the
      // handleSessionReady re-drain. (drainFindings is wired to the enqueue seam +
      // reconnect + this post-consume re-drain -- NOT the confirm seam, which drives
      // maybeEmitValidateWindows, not the drain.)
      return;
    }
    const steeredIds: string[] = [];
    for (const c of delivered) {
      const ids = c && Array.isArray(c.field_ids) ? c.field_ids : [];
      for (const id of ids) if (typeof id === 'string') steeredIds.push(id);
    }
    if (steeredIds.length > 0) {
      this.state = SchemaFormStateManager.markFieldsSteered(this.state, steeredIds);
    }
    this.state = SchemaFormStateManager.consumeValidatorFindings(this.state, delivered);
    // The delivered batch was consumed. If MORE findings accumulated while this drain
    // was in flight (a distinct contradiction from a later window), drain them now --
    // this only fires for genuinely new findings, never a re-steer of a voiced one.
    if (this.state.validatorFindingsQueue.length > 0) {
      this.drainFindings();
    }
  }

  /**
   * B5: resume a parked section switch (clean verdict / fail-OPEN). Clears the timer
   * and resolves the gate promise so proceedSectionSwitch runs doSectionSwitch.
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  private resolvePendingSectionSwitch(): void {
    if (!this.pendingSectionSwitch) return;
    clearTimeout(this.pendingSectionSwitch.timer);
    const pending = this.pendingSectionSwitch;
    this.pendingSectionSwitch = null;
    pending.resolve();
  }

  /**
   * B5: cancel a parked section switch on a CONFLICT verdict. The gate promise still
   * resolves (so proceedSectionSwitch's await does not hang), but the gate's own
   * `cancelled` flag tells proceedSectionSwitch to SKIP doSectionSwitch -- the client
   * stays in the current section so the live model can voice the steer the backend
   * just injected.
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  private cancelPendingSectionSwitch(): void {
    if (!this.pendingSectionSwitch) return;
    clearTimeout(this.pendingSectionSwitch.timer);
    const pending = this.pendingSectionSwitch;
    this.pendingSectionSwitch = null;
    pending.cancelled = true;
    pending.resolve();
  }

  /**
   * B4 (bd polyglot-pdf-jnjj.16): project the client's current field state into the
   * minimal validator payload (validation-delegation.md contract 2): a list of
   * { field_id, name, value, steered }. ONLY fields with a non-empty value are
   * included (empty fields give the validator nothing to check and only cost
   * tokens). `name` is the spoken/label name so the validator can name a conflict
   * naturally. `steered` is always false in B4 -- the per-field "already steered
   * about this once" marker is owned by B5 (jnjj.17), which adds the client-side
   * store; until then every field is un-steered.
   *
   * PII note: this builds the request body sent to the SAME Gemini trust boundary
   * the live model already uses (contract 6 sign-off). It must never be LOGGED --
   * callers send it, they do not print it.
   */
  private buildValidatorFields(
    sectionFields: FormField[]
  ): Array<{ field_id: string; name: string; value: any; steered: boolean }> {
    // Mirror the [] bracket fallbacks used elsewhere for value lookup (Gemini
    // sometimes drops/adds the trailing []).
    const valueFor = (fieldId: string): any => {
      let fv = this.state.fieldValues[fieldId];
      if (!fv && !fieldId.endsWith('[]')) fv = this.state.fieldValues[fieldId + '[]'];
      if (!fv && fieldId.endsWith('[]')) fv = this.state.fieldValues[fieldId.slice(0, -2)];
      return fv;
    };
    const allFields = this.state.schema?.fields ?? [];
    const out: Array<{ field_id: string; name: string; value: any; steered: boolean }> = [];
    for (const field of sectionFields) {
      // Skip fields hidden by conditional logic (Codex PR #271). A field whose
      // show_if trigger has since flipped is no longer part of the active form, but
      // its old value can linger in sessionStorage; navigation hides it via
      // shouldShowField. Without this filter a stale hidden answer would ride into
      // the validator payload (with no `shown` flag) and the validator could flag or
      // steer the user to a field that is no longer applicable. Use the SAME
      // visibility predicate navigation uses, against the FULL value map.
      if (!shouldShowField(field, this.state.fieldValues, allFields)) continue;
      const fv = valueFor(field.id);
      const value = fv ? fv.value : undefined;
      // Skip empty/unfilled values (contract 2: non-empty only). An explicitly-blank
      // OPTIONAL checkbox group is stored as [] (the confirm handler treats that as a
      // legitimate empty answer), so an empty array is "no value" too and must NOT
      // ride to the validator -- it would hand B5 an unfilled field to check
      // (Codex PR #271 round 2). Treat [] (and an array of only blanks) as empty.
      if (value === undefined || value === null || value === '') continue;
      if (Array.isArray(value) && value.every((v) => v === undefined || v === null || v === '')) continue;
      out.push({
        field_id: field.id,
        name: field.spoken_name || field.name || field.id,
        value,
        // B5 (bd polyglot-pdf-jnjj.17): the client-owned per-field "already steered
        // once" marker. The backend reads it to suppress re-steering an
        // already-adjudicated field (max-resteer bound). B4 hardcoded false; B5 reads
        // the real marker that markFieldsSteered persisted on the last conflict.
        steered: !!(fv && fv.steered),
      });
    }
    return out;
  }

  /**
   * B4 (bd polyglot-pdf-jnjj.16): a stable serialization of the whole form's
   * confirmed values, used as the form_complete dirty-check snapshot. Sorted by
   * field id so key ordering can never spuriously change the snapshot. Confirmed
   * values only: an unconfirmed edit does not make the form complete, so it should
   * not count as a change that re-triggers the full-form pass.
   */
  private serializeFormValues(): string {
    const entries: Array<[string, any]> = [];
    for (const [fieldId, fv] of Object.entries(this.state.fieldValues)) {
      if (fv && fv.confirmed) entries.push([fieldId, fv.value]);
    }
    entries.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    return JSON.stringify(entries);
  }

  /**
   * B4 (bd polyglot-pdf-jnjj.16): emit the proactive form_complete event for the
   * full-form validator pass, IF the form is complete AND its values changed since
   * the last emit. Guard on the COMPLETED STATE + a dirty-since-last-validation
   * snapshot (validation-delegation.md contract 4), NOT a fire-once latch: that
   * closes the edit-after-complete bypass (a user changing a value after the
   * full-form pass and submitting it unchecked) while preserving the no-pester
   * property (a static complete form never re-fires). Called from BOTH the confirm
   * handler's form-complete branch and the manual-edit path, so a post-completion
   * manual edit re-validates. Fire-and-forget (criterion 3): the validator pass is
   * async and never blocks the user.
   */
  private maybeEmitFormComplete(): void {
    if (!isFormComplete(this.state)) return;
    const snapshot = this.serializeFormValues();
    if (snapshot === this.formCompleteSnapshot) return; // unchanged -> no re-pester
    this.send({
      type: 'form_complete',
      fields: this.buildValidatorFields(this.state.schema.fields),
    });
    this.formCompleteSnapshot = snapshot;
  }

  /**
   * W2 (bd polyglot-pdf-kxkw): the async-validator STRIDE window builder. Runs on
   * every confirm / manual edit (the same seams as maybeEmitFormComplete). As the
   * fill advances, it sends any overlapping windows that have become eligible and
   * were not already sent, as ONE `validate_windows` message; the backend (W1)
   * validates each window concurrently off the receive loop and reports findings
   * FINDING-DRIVEN (no page/boundary dependency -- report-cadence revision
   * 2026-07-13). Fire-and-forget: nothing here blocks the user.
   *
   * "Eligible" = EVERY field the window covers is SETTLED (confirmed / skipped /
   * not-applicable) -- see computeReadyWindows; an out-of-order fill or a trailing
   * unanswered optional field keeps its window pending, so no field is starved of
   * validation. Already-sent windows are excluded via the persisted
   * validatedWindowIndices set, so each fires exactly once across reloads.
   * Page-agnostic: keys on schema field ORDER + the settled flags, never
   * pdf_position.page, so source:"web" / pageless forms behave identically.
   */
  private maybeEmitValidateWindows(): void {
    // Only run on an OPEN socket. This method MARKS windows sent (persists their
    // indices) before send(), and send() silently no-ops on a closed socket -- so
    // running it closed would permanently retire a window that never reached the
    // wire, dropping that region's validation coverage (Opus outer-review finding).
    // Bailing when closed leaves the indices unsent, so the next open seam
    // (confirm / reconnect's handleSessionReady) re-evaluates + emits them.
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    const ready = SchemaFormStateManager.computeReadyWindows(
      this.state,
      WebFormConnection.VALIDATOR_WINDOW_SIZE,
      WebFormConnection.VALIDATOR_WINDOW_STRIDE
    );
    if (ready.length === 0) return;

    const allFields = this.state.schema?.fields ?? [];
    const windows: Array<Array<{ field_id: string; name: string; value: any; steered: boolean }>> = [];
    const sentIndices: number[] = [];
    for (const w of ready) {
      const windowFields = allFields.slice(w.start, w.end);
      const payload = this.buildValidatorFields(windowFields);
      // buildValidatorFields drops hidden/empty fields; a fully-settled window can
      // still render to ZERO validatable fields (all skipped / hidden). It carries
      // nothing to check, but is still MARKED sent (its region is done -- re-checking
      // it every confirm is waste) -- just not put on the wire.
      if (payload.length > 0) windows.push(payload);
      sentIndices.push(w.index);
    }

    // Immutable-replace the state (the codebase treats SchemaFormState as a
    // snapshot -- confirmField/markFieldSchemaLoaded etc. all spread-replace rather
    // than mutate in place). A settled window's region cannot become unsettled, so
    // once marked sent it stays sent.
    if (sentIndices.length > 0) {
      this.state = {
        ...this.state,
        validatedWindowIndices: new Set([
          ...this.state.validatedWindowIndices,
          ...sentIndices,
        ]),
      };
      SchemaFormStateManager.save(this.state);
    }
    if (windows.length > 0) {
      this.send({ type: 'validate_windows', windows });
    }
  }

  /**
   * Apply an AI-supplied value to a field only if it passes client-side
   * validation (bd polyglot-pdf-wpw.3). The client owns all field state (the
   * stateless-backend invariant), so an invalid value must never land: enum/
   * format/required violations are caught here, the apply is skipped, and a
   * corrective prompt is routed back to the model so it re-asks the user in-band.
   *
   * Returns true when the value was applied (valid), false when rejected. The
   * corrective prompt is rate-limited per field and capped in total (mirroring
   * the unconfirmable loop-breaker) so a model that keeps re-sending the same bad
   * value cannot spin the session. The prompt carries only the field's spoken
   * name + the schema constraint message -- NEVER the rejected value (PII-safe;
   * validateField's messages are built from field.name/constraints, not the
   * value).
   */
  private applyAiValueWithValidation(
    field: FormField,
    value: any,
    options: { emit: boolean }
  ): boolean {
    // Canonicalize the value SHAPE before anything sees it (bd polyglot-pdf-
    // h76m.2): the backend prompt tells Gemini to send a checkbox-group
    // selection as ONE comma-separated string of exact option values
    // (config.py "Multiple checkboxes: comma-separated exact values"), but the
    // canonical client shape for a choice-group value is string[] (what the
    // interactive renderer stores and what /api/fill-pdf fills from). Split
    // here -- the single funnel every AI call site goes through -- so
    // validation, storage, conditionals, and PDF fill all see the same array.
    value = canonicalizeAiCheckboxGroupValue(field, value);
    const validationError = validateField(field, value);

    if (validationError) {
      this.handleAiValueRejected(field, validationError);
      return false;
    }

    // Reset the reject tracking when the STUCK field finally lands a good value --
    // i.e. the field currently being rejected is the one that just succeeded. That
    // is genuine progress on the thing that was failing, so it restores the full
    // prompt budget (per-field AND session-wide).
    //
    // It must NOT reset on a success for a DIFFERENT field while a reject streak is
    // active (Codex round 2 wanted any-success-resets, but fresh-eyes round 4 showed
    // that over-corrects): a model alternating [bad-A, good-B] in every batch would
    // otherwise clear the session cap each batch and prompt for A forever -- exactly
    // the cross-field spin the session cap exists to bound. So good-B with A still
    // failing leaves A's streak + the session cap intact; the cap lifts only when A
    // itself succeeds (or on connect/section-switch). When there is NO active streak,
    // this is just a clean fill and there is nothing to reset.
    if (this.lastValidationRejectFieldId !== null &&
        field.id === this.lastValidationRejectFieldId) {
      this.resetValidationRejectTracking();
    }

    // AI fills field as UNCONFIRMED - requires explicit confirmation via confirm_field tool
    this.updateField(field.id, value as any, { confirmed: false, emit: options.emit });
    return true;
  }

  /**
   * Record an AI-value validation reject and, when the per-field window fills,
   * send ONE corrective prompt back to the model -- up to a hard cap, after which
   * we stop prompting so a value the model cannot get right does not spin the
   * session (bd polyglot-pdf-wpw.3, mirroring the 0y7 unconfirmable loop-breaker).
   * PII-safe: only the spoken name + the constraint message reach the model.
   */
  private handleAiValueRejected(field: FormField, validationError: string): void {
    if (field.id === this.lastValidationRejectFieldId) {
      this.validationRejectCount += 1;
    } else {
      this.lastValidationRejectFieldId = field.id;
      this.validationRejectCount = 1;
      this.validationRejectRepromptCount = 0;
    }

    // validationError is built from field.name + the schema constraint (never the
    // value), so it is safe to log -- but stay conservative and log only the field
    // id + the streak count, not the message, to keep the production console clean.
    console.warn(
      '[WebFormConnection] AI value rejected by client validation:',
      field.id,
      'consecutive rejects:',
      this.validationRejectCount
    );

    // Prompt on the FIRST reject (count === 1), and thereafter on every count that
    // is a multiple of REJECT_LIMIT, until the cap. With LIMIT=2 that is rejects
    // #1, #2, #4 (then the cap of 3 is hit and it goes silent): the very first
    // reject always nudges the model, and after that it is rate-limited to once
    // per LIMIT rejects. The gap between prompt #1 and prompt #2 is therefore one
    // reject (count 1 -> 2), not LIMIT -- the count===1 special case fires
    // alongside the modulo schedule, it does not shift it.
    const windowFilled =
      this.validationRejectCount === 1 ||
      this.validationRejectCount % WebFormConnection.VALIDATION_REJECT_LIMIT === 0;

    // Session-wide cap (Codex PR #145): a model alternating bad values between
    // fields resets the per-field counter on every switch, so the per-field cap
    // alone would let it prompt forever. This total-prompts cap is NOT reset on a
    // field change -- only on (re)connect / section switch -- so it stops the
    // cross-field spin.
    const sessionCapReached =
      this.validationRejectSessionPromptCount >= WebFormConnection.VALIDATION_REJECT_SESSION_CAP;

    if (
      windowFilled &&
      this.validationRejectRepromptCount < WebFormConnection.VALIDATION_REJECT_REPROMPT_CAP &&
      !sessionCapReached
    ) {
      this.validationRejectRepromptCount += 1;
      this.validationRejectSessionPromptCount += 1;
      const spokenName = field.spoken_name || field.name || field.id;
      // completion_message -> send_prompt is the proven channel that actually
      // redirects the model in-band (the unconfirmable loop-breaker uses it too);
      // dependency_error is NOT consumed by the backend. The message carries the
      // constraint phrasing but never the rejected value.
      this.send({
        type: 'completion_message',
        message:
          `The value provided for '${spokenName}' is not valid: ${validationError}. ` +
          `It was not saved. Ask the user to provide a valid value, then call ` +
          `update_form_fields again to fill it.`,
      });
      // NOTE: deliberately do NOT call this.callbacks.onError here (Codex PR #145).
      // A validation reject is a NORMAL, recoverable event -- the session is still
      // live and the model is about to re-ask via the prompt above. onError maps the
      // connection status to `error`, and the voice overlays disable push-to-talk
      // unless the status is `connected`, so firing it would STRAND the user exactly
      // when they need to speak the corrected value. The in-band completion_message
      // is the correct, non-fatal channel; the connection-error callback is reserved
      // for genuine transport/session failures.
    }
  }

  /**
   * Clear the AI-value validation-reject loop-breaker counters (bd
   * polyglot-pdf-wpw.3). Called on (re)connect, on section switch, and whenever a
   * value for the tracked field validates. Resets BOTH the per-field counters and
   * the session-wide prompt cap: a good value landing (or a fresh connection/
   * section) is genuine progress, so the model earns a fresh prompt budget -- the
   * pure cross-field spin Codex PR #145 flagged never lands a good value, so its
   * session counter still climbs to the cap and stops it.
   */
  private resetValidationRejectTracking(): void {
    this.lastValidationRejectFieldId = null;
    this.validationRejectCount = 0;
    this.validationRejectRepromptCount = 0;
    this.validationRejectSessionPromptCount = 0;
  }

  /**
   * Clear the unconfirmable-field loop-breaker counters (bd polyglot-pdf-0y7 +
   * the session-wide cap added in bd polyglot-pdf-r2hy). Called on (re)connect, on
   * section switch, and whenever the tracked field is finally confirmed. Resets
   * BOTH the per-field counters and the session-wide re-prompt cap: a fresh
   * connection / section is genuine progress, so the model earns a fresh re-prompt
   * budget -- the pure cross-field confirm spin r2hy flagged never lands a usable
   * value, so its session counter still climbs to the cap and stops it.
   */
  private resetUnconfirmableTracking(): void {
    this.lastUnconfirmableFieldId = null;
    this.unconfirmableConfirmCount = 0;
    this.unconfirmableRepromptCount = 0;
    this.unconfirmableSessionPromptCount = 0;
  }

  /**
   * Ack a synchronous confirm_field request back to the backend (bd
   * polyglot-pdf-wpw.2 / WS-E2). The backend waits on this to learn whether the
   * confirmation was actually recorded, so it can return success:false to Gemini
   * when a field has no value instead of confabulating a confirmation.
   *
   * `reason` is a fixed category token (e.g. 'no_value') when not recorded --
   * never a field value (PII-safe). A request_id is always present on a
   * synchronous confirm_field request; guard defensively in case an older backend
   * sends the legacy fire-and-forget shape (no request_id) -- then there is
   * nothing to ack.
   */
  private sendConfirmFieldResponse(
    request_id: string | undefined,
    recorded: boolean,
    reason?: string,
    sectionComplete?: boolean
  ): void {
    if (!request_id) {
      return;
    }
    this.send({
      type: 'confirm_field_response',
      request_id,
      recorded,
      ...(reason ? { reason } : {}),
      // bd polyglot-pdf-njvh: only present (true) when this confirm completed the
      // section, so the backend can skip the doomed next-field-hint round-trip that
      // would race the imminent socket teardown for switchToSection.
      ...(sectionComplete ? { section_complete: true } : {}),
    });
  }

  /**
   * Ack a skip_field request (bd polyglot-pdf-7yra), mirroring
   * sendConfirmFieldResponse: tells the backend whether the frontend recorded the
   * skip so the skip_field tool round-trip completes. `reason` is a fixed category
   * token (never a field value); section_complete rides the same njvh optimization.
   */
  private sendSkipFieldResponse(
    request_id: string | undefined,
    recorded: boolean,
    reason?: string,
    sectionComplete?: boolean
  ): void {
    if (!request_id) {
      return;
    }
    this.send({
      type: 'skip_field_response',
      request_id,
      recorded,
      ...(reason ? { reason } : {}),
      ...(sectionComplete ? { section_complete: true } : {}),
    });
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
      console.log(`[WebFormConnection] [recv] First audio chunk received from server (${arrayBuffer.byteLength} bytes)`);
    } else if (this.audioChunkCount % 100 === 0) {
      console.log(`[WebFormConnection] [recv] Audio chunk #${this.audioChunkCount}`);
    }

    // Belt-and-suspenders clear for the thinking indicator (bd polyglot-pdf-wpw.5):
    // the backend's agent_processing:false (sent at its first response audio) is the
    // primary clear, but if it is delayed/lost, response audio ARRIVING here also
    // means the agent has started replying -- so clear on any audio while thinking.
    if (this.thinkingTurnActive) {
      this.clearThinking('audio-frame');
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
    // `unknown_control` is the backend's "I don't recognize that message type"
    // ack -- by definition non-fatal (the sender's message was one-way or the
    // sender handles the missing reply). It must NEVER end the session or fail
    // a switch: during deploy skew a NEW frontend's `client_diagnostic` lands
    // on an OLD backend exactly in the post-I-Agree switch window, and before
    // this early-out that benign ack drove the UI into a dead Reconnect state
    // -- a diagnostic causing an outage in the flow it observes (Opus outer
    // review finding, bd polyglot-pdf-xp4q).
    if (message.code === 'unknown_control') {
      console.warn('[WebFormConnection] Backend does not recognize a message type we sent (deploy skew?) -- ignoring', message);
      return;
    }
    console.error('[WebFormConnection] Server error received:', {
      code: message.code,
      reason: message.reason,
      message: message.message,
      fullMessage: message
    });
    // Clear the thinking indicator on a server error (bd polyglot-pdf-wpw.5, Codex
    // PR #273): a JSON {type:"error"} arriving mid-processing does NOT necessarily
    // change status (only a section-switch error does), so the setStatus-based clear
    // would miss it and the indicator would hang until the 30s timer. Clear directly,
    // and -- for symmetry with the max-duration path -- resync the backend so a
    // non-session-ending error cannot strand _processing_active=True and dedup the
    // next turn (Opus fallback review). Fire-and-forget; safe to skip if the socket
    // is gone.
    this.clearThinking('server_error');
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.send({ type: 'clear_thinking' });
    }
    // Build error message from available fields
    const errorText = message.message || message.reason || message.code || "Server error";

    // If a section switch is in flight, this error (e.g. the backend's
    // section_switch_failed rejection of a concurrent switch, post-0c1) ends it:
    // release the guards + surface `error` so the UI doesn't hang on a stuck
    // `switching_section` (bd polyglot-pdf-aun). failSectionSwitch fires onError
    // itself, so don't double-fire below.
    if (this.switchInFlight) {
      this.failSectionSwitch(errorText);
      return;
    }

    const error = new Error(errorText);
    if (this.callbacks.onError) {
      this.callbacks.onError(error);
    }
  }

  /**
   * Handle WebSocket errors
   */
  private handleError(error: Event | Error): void {
    // Don't show error during section switches (expected during reconnect), nor
    // during a GoAway pre-emptive reconnect (bd polyglot-pdf-l3a.2): both drive
    // their own reconnect and own the terminal status. For a GoAway reconnect, the
    // connect() promise's .catch in handleGoAwayReconnect decides the outcome
    // (fall back to attemptReconnect -> "reconnecting", or "reconnect_failed" at
    // the cap); letting handleError flash "error" first would both be wrong (we do
    // recover) and strand the user on a status with no reconnect button.
    if (!this.isSectionSwitching && !this.goAwayReconnectInFlight) {
      this.setStatus("error", "handleError");
    }

    if (this.callbacks.onError && error instanceof Error) {
      this.callbacks.onError(error);
    }
  }

  /**
   * Handle WebSocket close
   */
  private handleClose(event?: CloseEvent, socket?: WebSocket): void {
    // Ignore a STALE close: the old section socket's close can arrive AFTER
    // startSection already swapped this.ws to the new socket (Codex PR #137). If
    // the firing socket is not the current one, it's the replaced socket winding
    // down -- not a real disconnect of the live connection, so do nothing (else
    // the switchInFlight branch below would falsely fail a healthy switch).
    if (socket && this.ws && socket !== this.ws) {
      console.log('[WebFormConnection] Ignoring close from a stale (replaced) socket');
      return;
    }

    // Log close details for debugging
    console.log('[WebFormConnection] [plug] WebSocket closed', {
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
      this.setStatus("disconnected", "handleClose:no-auto-reconnect");
      return;
    }

    // Don't auto-reconnect during the intentional disconnect a reconnect-based
    // switch performs itself (isSectionSwitching is set across that window and
    // cleared the moment the new socket opens). The switch logic owns the
    // lifecycle here; the watchdog backstops a switch that never completes.
    if (this.isSectionSwitching) {
      return; // Keep current status, startSection drives the reconnect
    }

    // Don't auto-reconnect for the intentional close a GoAway pre-emptive
    // reconnect performs itself (bd polyglot-pdf-l3a.2). handleGoAwayReconnect
    // set goAwayReconnectInFlight and is already driving connect(); a second
    // reconnect here would race it. Keep status "connected" (seamless) -- the
    // guard clears when the new socket opens (handleOpen) or the reconnect fails.
    if (this.goAwayReconnectInFlight) {
      return;
    }

    // A close that arrives while a switch is still IN FLIGHT but the intentional-
    // disconnect window is already over (isSectionSwitching cleared) is an
    // UNEXPECTED drop mid-switch -- surface `error` fast instead of waiting for
    // the watchdog or leaving a stuck `switching_section` (bd polyglot-pdf-aun).
    if (this.switchInFlight) {
      console.error('[WebFormConnection] Connection dropped mid-section-switch -- surfacing error');
      this.failSectionSwitch('Connection lost during section switch');
      return;
    }

    // Don't auto-reconnect if connection was closed due to idle timeout
    // User must manually click "Reconnect" button to resume
    if (this.idleTimedOut) {
      console.log('[WebFormConnection] [timer] Idle timeout - no auto-reconnect, user must manually reconnect');
      this.setStatus("idle_timeout", "handleClose:idle-timeout");
      return;
    }


    // An intentional teardown leaves status already "disconnected" -- stay put,
    // regardless of the (possibly stale, at-max) reconnect counter. Checking this
    // FIRST is what keeps a deliberate close from being misread as a terminal
    // reconnect failure (bd polyglot-pdf-jf6w.3).
    if (this.status === "disconnected") {
      this.setStatus("disconnected", "handleClose:intentional");
    } else if (this.reconnectTimer) {
      // A reconnect is ALREADY scheduled -- do not drive a second one (bd
      // polyglot-pdf-l3a.2, Opus fresh-eyes). On a failed GoAway pre-emptive
      // reconnect, the connect().catch fallback has already called
      // attemptReconnect() (scheduling reconnectTimer + counting the attempt) by
      // the time this onclose lands in a real browser; falling through here would
      // double-count the attempt and halve the retry budget. attemptReconnect's own
      // clear makes the timer safe; this guard keeps the attempt COUNT honest.
    } else if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.attemptReconnect();
    } else {
      // Auto-reconnect exhausted every attempt on an unexpected drop -- a terminal
      // failure the user must act on, so surface the distinct reconnect_failed
      // status that drives the connection-timeout modal rather than the generic
      // disconnected (bd polyglot-pdf-jf6w.3).
      this.setStatus("reconnect_failed", "handleClose:max-retries");
    }
  }

  /**
   * Attempt to reconnect with exponential backoff
   */
  private attemptReconnect(): void {
    // Idempotent scheduling (bd polyglot-pdf-l3a.2, Opus fresh-eyes): if a
    // reconnect is ALREADY scheduled, do not stack a second one. Two drivers can
    // race to here on a failed GoAway pre-emptive reconnect -- the connect().catch
    // fallback and the failed socket's onclose in handleClose fire in separate
    // browser tasks, and without this guard each would schedule its own timer
    // (leaking the first, which still fires) and double-increment reconnectAttempts,
    // halving the retry budget and opening duplicate sockets. Clearing here also
    // makes any future double-call of attemptReconnect safe, not just the GoAway
    // path.
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.reconnectAttempts++;
    this.setStatus("reconnecting", "attemptReconnect");

    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      30000 // Max 30 seconds
    );

    this.reconnectTimer = window.setTimeout(() => {
      // Null the handle as soon as the timer FIRES so `this.reconnectTimer` means
      // "a reconnect is pending" and nothing more (bd polyglot-pdf-l3a.2, Opus
      // fresh-eyes): setTimeout leaves its id in place after firing, so without
      // this a fired-but-not-yet-reconnected timer would read as "pending" and the
      // handleClose idempotence guard would wrongly skip the NEXT outage's
      // reconnect. Cleared here (not after connect) because connect() is what starts
      // the new socket; a drop of THAT socket must be free to schedule the next
      // attempt.
      this.reconnectTimer = null;
      // Use the URL we successfully connected to (not the default localhost)
      if (this.connectedUrl) {
        this.connect(this.connectedUrl);
      } else {
        console.error('[WebFormConnection] Cannot reconnect - no connectedUrl stored');
        this.setStatus("disconnected", "attemptReconnect:no-url");
      }
    }, delay);
  }

  /**
   * Pre-emptive, silent reconnect in response to a Gemini Live GoAway (bd
   * polyglot-pdf-l3a.2). The server is about to reset this connection; we get
   * ahead of the abrupt close by tearing down the current socket and immediately
   * reconnecting through the same path a normal reconnect uses -- so the new
   * session carries resume:true (bd polyglot-pdf-vmxx, no re-greeting) and the
   * user experiences a seamless continuation rather than a drop.
   *
   * We drive the reconnect ourselves (setting goAwayReconnectInFlight) so
   * handleClose does NOT also fire its auto-reconnect on the close we perform,
   * and a burst of GoAways coalesces into one reconnect. Status is left as-is
   * ("connected") -- this is not a failure the user needs to see.
   *
   * Skipped when another lifecycle path already owns the socket: an idle timeout
   * (no reconnect wanted), an in-flight section switch (it drives its own
   * reconnect), or a GoAway reconnect already in flight. Also skipped when there
   * is no open socket / no stored URL to reconnect to.
   */
  private handleGoAwayReconnect(surfaceReconnectingStatus: boolean = false): boolean {
    // Returns whether it ACTUALLY started a fresh reconnect. Callers that arm
    // drop-specific state (the spontaneous-drop marker + watchdog) must gate on
    // this: when the call coalesces into an in-flight reconnect or is skipped, no
    // reconnect starts, so setting droppedReconnectInFlight would leak `true`
    // forever (the completing reconnect never transitions status, so setStatus's
    // clear never runs) -- fresh-eyes.
    if (this.goAwayReconnectInFlight) {
      // A previous GoAway is already driving a reconnect -- coalesce.
      return false;
    }
    if (this.idleTimedOut) {
      // An idle timeout suppresses auto-reconnect on purpose; a GoAway must not
      // override the user's manual-reconnect gate.
      return false;
    }
    if (this.isSectionSwitching || this.switchInFlight) {
      // A section switch owns the socket lifecycle and drives its own reconnect;
      // do not race it with a second reconnect.
      return false;
    }
    if (!this.connectedUrl) {
      console.warn('[WebFormConnection] GoAway received but no connectedUrl to reconnect to');
      return false;
    }
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      // No live socket to pre-empt (already closing/closed) -- the normal
      // handleClose path will handle any reconnect.
      return false;
    }

    console.log('[WebFormConnection] [wave] GoAway policy: pre-emptive silent reconnect');
    this.goAwayReconnectInFlight = true;

    // Spontaneous-drop case (bd polyglot-pdf-ppfy): unlike a GoAway (a clean
    // server-lifecycle reset the user should not see), a 1011 drop is a real
    // interruption -- surface "reconnecting" so the UI can show the transient
    // "having issues connecting" modal. handleSessionReady restores "connected"
    // on a successful reopen, which clears the modal; a failed reconnect falls
    // through to attemptReconnect / reconnect_failed below.
    if (surfaceReconnectingStatus) {
      this.setStatus("reconnecting", "handleSessionDroppedReconnect");
    }

    // Close the current socket WITHOUT the disconnect() side effects (which would
    // set status "disconnected" and, more importantly, is meant for intentional
    // teardown). handleClose sees goAwayReconnectInFlight and stands down so we
    // are the sole reconnect driver. Keep status "connected" for seamlessness.
    const closing = this.ws;
    this.ws = null;
    try {
      closing.close();
    } catch (error) {
      console.warn('[WebFormConnection] Error closing socket for GoAway reconnect', error);
    }

    // Reconnect immediately through the standard path: connect() re-resolves a
    // fresh token and handleOpen() sends resume:true (hasConnectedOnce is already
    // true after the first connect). A successful open clears the guard in
    // handleOpen.
    //
    // On FAILURE (token error / network blip / the new socket timing out), clear
    // the guard and fall back to the normal auto-reconnect exponential-backoff
    // loop (fresh-eyes PR-review gap): if we merely cleared the guard, the user
    // would be stranded -- the connect() timeout path never touches status (stale
    // "connected" over a dead socket) and its onerror path lands on "error", which
    // has no reconnect button and no retry. attemptReconnect() restores the exact
    // recovery the pre-bead baseline had (an unhandled GoAway close fell through to
    // it via handleClose), so a failed pre-emptive reconnect degrades to a normal
    // reconnecting state instead of a dead end. Skip the fallback if the user has
    // since idle-timed-out or a section switch took over (those own the lifecycle),
    // or if the reconnect-attempt cap is already exhausted (let it terminate as
    // reconnect_failed rather than spin).
    this.connect(this.connectedUrl).catch((error) => {
      console.error('[WebFormConnection] GoAway pre-emptive reconnect failed', error);
      this.goAwayReconnectInFlight = false;
      if (this.idleTimedOut || this.isSectionSwitching || this.switchInFlight) {
        return;
      }
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.attemptReconnect();
      } else {
        this.setStatus("reconnect_failed", "handleGoAwayReconnect:max-retries");
      }
    });
    // A fresh reconnect was started (socket closed + connect() driving).
    return true;
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
        console.error('[WebFormConnection] [warn] SUSPICIOUS: Sending message without type!', {
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

    // Refresh this.state from the persisted snapshot BEFORE computing the next
    // field (bd polyglot-pdf-ezg2). The manual-edit path (connection.ts
    // onManualEdit) applies the edit to a separate state object and SAVES it to
    // sessionStorage, but does NOT mutate this.state -- so a stale this.state
    // would compute the just-edited (auto-confirmed) field as still "next" and
    // point Gemini back at it. load() is the same source-of-truth sessionStorage
    // read this class uses elsewhere; the edit handler just wrote the
    // authoritative post-edit state there. (The refresh is ALSO required by the
    // maybeEmitFormComplete dirty-check below -- fresh-eyes finding, jnjj.16.)
    const persisted = SchemaFormStateManager.load();
    if (persisted) this.state = persisted;

    // Compute the next field ONCE and derive BOTH the hint and (for DTI) the
    // schema from it, so they can never refer to different fields -- same rule
    // as handleGetNextFieldHintRequest (Codex PR #229).
    const nextField = isFormComplete(this.state)
      ? null
      : computeNextField(this.state, { skipConfirmed: true });
    if (this.callbacks.onNextField) {
      this.callbacks.onNextField(nextField ? nextField.id : null);
    }
    const nextFieldHint = nextField
      ? formatNextFieldHint(nextField, getFieldOrder(this.state, nextField.id) || undefined,
          // refreshed at handler entry -- no second parse.
          this.sessionLanguageFor(true))
      : null;

    // Keep the recovery-prompt hint current (same side effect as
    // handleGetNextFieldHintRequest): a stall-recovery prompt after a manual
    // edit must name the POST-edit next field, not the pre-edit one.
    if (nextFieldHint) {
      sessionStorage.setItem('vff_last_field_hint', nextFieldHint);
    }

    // DTI (bd polyglot-pdf-ezg2): a manual edit never triggers the confirm_field
    // next-field round-trip that normally carries the next field's schema, so
    // supply it here -- the backend re-establishes the current-field coercion
    // pointer + validation entry from it (form_filling_service.
    // send_manual_field_update -> merge_field_schema).
    let nextFieldSchema: unknown = undefined;
    if (this.dtiModeEnabled && nextField) {
      nextFieldSchema = getFieldSchema(nextField.id, this.state.schema);
    }

    this.send({
      type: 'manual_field_update',
      field_id: fieldId,
      field_name: fieldName,
      value: value,
      next_field_hint: nextFieldHint,  // Include next field guidance
      ...(nextFieldSchema ? { next_field_schema: nextFieldSchema } : {}),
    });

    // B4 (bd polyglot-pdf-jnjj.16): a manual edit can land on an ALREADY-complete
    // form (the UI allows editing a completed form). The confirm handler does not
    // run for a manual edit, so without this the edited value would bypass the
    // full-form validator pass and be submittable unchecked. maybeEmitFormComplete
    // is guarded (only re-emits when the form is complete AND a value changed), so
    // a manual edit that does not complete the form is a no-op here. this.state
    // was refreshed from the persisted snapshot above.
    this.maybeEmitFormComplete();
    // W2 (bd polyglot-pdf-kxkw): stride-window validator check on the same
    // state-change seam (guarded: sends only newly-eligible, unsent windows).
    this.maybeEmitValidateWindows();
  }


  /**
   * Send activity_start signal to Gemini (user started speaking).
   * Signals the beginning of user speech before sending audio chunks.
   */
  sendActivityStart(): void {
    console.log(`[WebFormConnection] [send] sendActivityStart() called - WebSocket state: ${this.ws ? this.ws.readyState : 'null'} (OPEN=${WebSocket.OPEN})`)

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error(`[WebFormConnection] [X] Cannot send activity_start - WebSocket not open (state: ${this.ws ? this.ws.readyState : 'null'})`)
      return;
    }

    console.log('[WebFormConnection] [send] Sending activity_start message to backend')
    // The user is starting a NEW turn (incl. a barge-in over a still-"thinking"
    // window): the prior turn's thinking indicator is now obsolete -- clear it so a
    // barge-in can never leave it stuck (bd polyglot-pdf-wpw.5, fresh-eyes). The new
    // turn re-arms thinking via the backend agent_processing signal on its own end.
    this.clearThinking('activity_start');
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
    console.log(`[WebFormConnection] [send] sendActivityEnd() called - WebSocket state: ${this.ws ? this.ws.readyState : 'null'} (OPEN=${WebSocket.OPEN})`)

    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.error(`[WebFormConnection] [X] Cannot send activity_end - WebSocket not open (state: ${this.ws ? this.ws.readyState : 'null'})`)
      return;
    }

    // CRITICAL: Wait for all buffered audio to be sent before signaling activity_end
    // This ensures Gemini receives all audio chunks before we close the turn
    const bufferedBefore = this.ws.bufferedAmount;
    if (bufferedBefore > 0) {
      console.log(`[WebFormConnection] [wait] Waiting for ${bufferedBefore} bytes of audio to drain before activity_end`)
      await this.waitForBufferDrain(2000); // Wait up to 2 seconds for audio to send
    }

    console.log('[WebFormConnection] [send] Sending activity_end message to backend')
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

    console.log('[WebFormConnection] [door] Ending Gemini session (keeping WebSocket alive)');
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
   * Set connection status and notify.
   * Every transition is logged at console.info level with old->new and a
   * short caller-supplied reason tag so status stranding is visible in devtools.
   */
  private setStatus(status: ConnectionStatus, reason = ''): void {
    if (this.status === status) return;

    console.info(
      '[WebFormConnection] status ' + this.status + '->' + status +
      (reason ? ' (' + reason + ')' : '')
    );

    this.status = status;

    // Clear the drop-driven-reconnect marker only on a SETTLED status (bd
    // polyglot-pdf-ppfy): "connected" = recovered, and reconnect_failed / error /
    // idle_timeout / disconnected = gave up. NOT on the intermediate "connecting"
    // that a live drop reconnect passes through -- a drop reconnect whose first
    // socket fails falls into attemptReconnect's backoff, whose connect() sets
    // "connecting"; clearing there would drop the marker mid-recovery and the
    // "having trouble reaching the AI" modal would vanish into a bare "connecting"
    // screen for the rest of the episode (fresh-eyes). The modal only draws on
    // status==='reconnecting', so keeping the marker across "connecting" is safe --
    // it just lets the modal reappear if a later leg returns to "reconnecting".
    // handleSessionReady also clears it explicitly on success.
    if (
      status === "connected" ||
      status === "reconnect_failed" ||
      status === "error" ||
      status === "idle_timeout" ||
      status === "disconnected"
    ) {
      this.droppedReconnectInFlight = false;
    }

    // Safety clear for the thinking indicator (bd polyglot-pdf-wpw.5): any move OFF
    // "connected" (disconnect, error, reconnecting, section switch, idle_timeout,
    // reconnect_failed) means there is no live turn in flight, so the indicator must
    // not persist across it. Clearing here covers every terminal/transitional path
    // in one place. (A fresh "connected" does not set thinking; only agent_processing
    // does.)
    if (status !== "connected") {
      this.clearThinking('status:' + status);
    }

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
   * Whether the CURRENT "reconnecting" is driven by a spontaneous Gemini drop
   * (gemini_session_dropped / 1011), as opposed to an ordinary WS blip that
   * attemptReconnect also drives to the same status (bd polyglot-pdf-ppfy). The
   * overlay gates the "having trouble reaching the AI" modal on this so a plain
   * network reconnect stays silent. Only meaningful while status is "reconnecting".
   */
  isDroppedReconnect(): boolean {
    return this.droppedReconnectInFlight;
  }

  /** Whether the "thinking" indicator is currently active (bd polyglot-pdf-wpw.5). */
  getThinking(): boolean {
    return this.thinking;
  }

  /**
   * Set the "thinking" flag and notify (bd polyglot-pdf-wpw.5). Mirrors setStatus:
   * dedups same-value calls and fires onThinkingChange. The boolean is the single
   * source of truth the UI subscribes to.
   */
  private setThinking(thinking: boolean): void {
    if (this.thinking === thinking) return;
    this.thinking = thinking;
    if (this.callbacks.onThinkingChange) {
      this.callbacks.onThinkingChange(thinking);
    }
  }

  /**
   * Begin the "thinking" window: the user's turn just ended and we are waiting on
   * the agent's reply (bd polyglot-pdf-wpw.5). Arms thinkingTurnActive so the next
   * audio frame clears it, and starts the max-duration safety timer so a reply that
   * never produces audio cannot strand the indicator on.
   */
  private startThinking(): void {
    this.thinkingTurnActive = true;
    this.setThinking(true);
    if (this.thinkingTimer !== null) {
      clearTimeout(this.thinkingTimer);
    }
    this.thinkingTimer = setTimeout(() => {
      this.thinkingTimer = null;
      // Safety net: the reply never arrived (dropped/empty turn). Clear so the
      // indicator can never stick on -- a stuck "thinking" is worse than none.
      this.clearThinking('max-duration');
      // Also reset the BACKEND processing state (bd polyglot-pdf-wpw.5, Codex
      // PR #273): a frontend-only clear leaves backend _processing_active stuck
      // True, which would dedup the NEXT turn's processing:true. Fire-and-forget;
      // safe to skip if the socket is gone (the next connect resets state anyway).
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.send({ type: 'clear_thinking' });
      }
    }, THINKING_MAX_MS) as unknown as number;
  }

  /**
   * End the "thinking" window (bd polyglot-pdf-wpw.5). Called on the FIRST response
   * audio of the turn and on every safety boundary (turn_complete / error /
   * disconnect / section-switch / idle_timeout) so the indicator never sticks on.
   * Idempotent: harmless when not thinking.
   */
  private clearThinking(_reason = ''): void {
    this.thinkingTurnActive = false;
    if (this.thinkingTimer !== null) {
      clearTimeout(this.thinkingTimer);
      this.thinkingTimer = null;
    }
    this.setThinking(false);
  }

  /**
   * Returns true when the underlying WebSocket is in the OPEN state.
   * Used by the mic audio-send gate in connection.ts: during a same-socket
   * section switch (switching_section) the socket stays open, so audio can
   * still be forwarded to the backend -- which drops it server-side via
   * drop_audio=True (manual path: websocket_routes.py manual_section_switch).
   */
  isSocketOpen(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  // --- Section-switch durability (bd polyglot-pdf-aun / WS-D) ----------------

  /** Arm the watchdog so a switch that never confirms/errors can't leave the UI
   *  stuck on `switching_section`. */
  private armSectionSwitchWatchdog(): void {
    this.clearSectionSwitchWatchdog();
    this.sectionSwitchWatchdog = window.setTimeout(() => {
      this.sectionSwitchWatchdog = null;
      // Only fire if a switch is genuinely still in flight (a late
      // section_switched would have disarmed us).
      if (this.switchInFlight) {
        console.error('[WebFormConnection] Section switch timed out -- surfacing error');
        // Observability (bd polyglot-pdf-xp4q): a switch that never reaches
        // session_ready produces ZERO opener diagnostics -- which would read as
        // "opener worked" in the logs. Name this outcome too, so an absent
        // field1_opener_skipped line plus THIS line means "failed before the
        // gate", not "no bug". Fire-and-forget: if the socket is dead the send
        // silently goes nowhere, and the server-side handshake-without-
        // session_ready is itself the readable evidence in that case.
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          // Every field is COMPUTED, none hardcoded: a hardcoded
          // is_form_complete=false would assert the opposite of the truth when
          // a switch times out on a completed form -- inverting the very signal
          // that flag exists to carry (Opus outer review finding, round 2).
          // has_next_field_hint uses the side-effect-free computeNextField
          // directly, NOT computeNextFieldHintString -- the latter fires the
          // onNextField UI callback, which a timeout path must not do.
          const wdFormComplete = isFormComplete(this.state);
          this.send({
            type: 'client_diagnostic',
            event: 'section_switch_watchdog_timeout',
            was_section_switch: true,
            disclaimer_accepted: !!this.state.disclaimerAccepted,
            has_selected_language: !!this.state.selectedLanguage,
            has_next_field_hint:
              !wdFormComplete && !!computeNextField(this.state, { skipConfirmed: true }),
            is_form_complete: wdFormComplete,
            storage_disclaimer_accepted: !!SchemaFormStateManager.load()?.disclaimerAccepted,
            continuous_session: !!this.continuousSessionEnabled,
          });
        }
        this.failSectionSwitch('Section switch timed out');
      }
    }, WebFormConnection.SECTION_SWITCH_TIMEOUT_MS);
  }

  private clearSectionSwitchWatchdog(): void {
    if (this.sectionSwitchWatchdog !== null) {
      clearTimeout(this.sectionSwitchWatchdog);
      this.sectionSwitchWatchdog = null;
    }
  }

  /** A switch finished SUCCESSFULLY (section_switched arrived): release the
   *  guards so the next switch can proceed and the status can settle. */
  private completeSectionSwitch(): void {
    this.switchInFlight = false;
    this.isSectionSwitching = false;
    this.clearSectionSwitchWatchdog();
  }

  /** A switch FAILED (reconnect close, server error, or watchdog). Release the
   *  guards and surface `error` instead of a stuck `switching_section` (bd aun).
   *  The caller's onError is invoked so the UI can prompt a manual reconnect. */
  private failSectionSwitch(reason: string): void {
    this.switchInFlight = false;
    this.isSectionSwitching = false;
    this.clearSectionSwitchWatchdog();
    this.setStatus('error', "failSectionSwitch:" + reason);
    if (this.callbacks.onError) {
      this.callbacks.onError(new Error(reason));
    }
  }

  /**
   * Get current state
   */
  getState(): SchemaFormState {
    return this.state;
  }

  /**
   * Reload this connection's in-memory state from sessionStorage.
   *
   * `this.state` is a copy seeded at construction (init()); this pulls the latest
   * persisted `schema_form_state` back into it. No-op if storage is empty (keeps
   * the current copy). Two production callers:
   *
   * 1. `handleOpen` (bd polyglot-pdf-fn1m): on every (re)connect, before building
   *    the handshake, so a soft page refresh -- which builds a BRAND-NEW connection
   *    whose init() snapshot can predate the latest save -- serializes the client's
   *    actual current section + field values, not a stale snapshot. This is the
   *    primary real-world purpose; do NOT treat this method as test-only.
   * 2. TEST-SUPPORT (bd polyglot-pdf-o1c): the E2E voice harness clears a field's
   *    state between same-page reruns via SchemaFormStateManager (save + dispatch),
   *    which refreshes SchemaForm's React state but NOT this connection's copy;
   *    calling this after such a clear pulls the updated state back in.
   */
  reloadState(): void {
    const loaded = SchemaFormStateManager.load();
    if (loaded) {
      this.state = loaded;
    }
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
    // the breaker a cycle early on a same field_id. Also resets the session-wide
    // re-prompt cap (bd polyglot-pdf-r2hy).
    this.resetUnconfirmableTracking();
    // Same for the AI-value validation-reject loop-breaker (bd polyglot-pdf-wpw.3):
    // a reject streak must not carry across a section transition.
    this.resetValidationRejectTracking();

    // Re-entrancy guard (bd polyglot-pdf-aun): reject a second switch while one is
    // already in flight, so two reconnects can't race. Distinct from
    // isSectionSwitching, which is cleared the moment the new socket opens.
    if (this.switchInFlight) {
      // THROW so the caller knows the switch was rejected and can roll back its
      // optimistic UI update (Codex PR #137), rather than a silent resolve.
      console.warn('[WebFormConnection] startSection rejected -- a section switch is already in progress');
      throw new Error('A section switch is already in progress');
    }
    this.switchInFlight = true;
    try {
      // Set switching status + arm the watchdog so a hung switch surfaces error.
      this.isSectionSwitching = true;
      this.setStatus("switching_section", "startSection");
      this.armSectionSwitchWatchdog();

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
      // Reset the auto-reconnect suppressor now the new socket is open. The
      // switch is not fully "complete" until the handshake is sent below; the
      // watchdog stays armed until then.
      this.isSectionSwitching = false;

      // Continuous-session mode (bd polyglot-pdf-x8rt): startSection is the REAL
      // session-start path (switchToFirstSection calls it right after the user
      // accepts the disclaimer), NOT just the auto-reconnect path (handleOpen).
      // The raw single-section handshake below would chop the form back into
      // sections -- defeating continuous mode on the session that actually fills
      // the form. So in continuous mode, send the SAME whole-form handshake
      // handleOpen builds (getHandshakePayload -> getJITHandshakePayload ->
      // buildContinuousManifest): one synthetic section, every field,
      // total_sections=1. currentState was already switched into this.state above.
      if (this.continuousSessionEnabled) {
        this.send(
          SchemaFormStateManager.getHandshakePayload(this.state, this.fillLanguage, this.hasConnectedOnce)
        );
        this.hasConnectedOnce = true;
      } else {
        // DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
        // continuous-DTI is the live flow. Kept as a fallback, not deleted.
        // Do not extend.
        // Compute initial field hint (first unfilled field in this section)
        const initialFieldHint = this.computeNextFieldHintString();

        // Send handshake with section metadata and initial field hint
        this.send({
          type: "handshake",
          schema: sectionSchema,
          // FULL form schema for the secretary catalog (bd polyglot-pdf-p68s /
          // jnjj.45d). Re-sent on the section-switch handshake so the backend's
          // in-session cache survives the reconnect (stateless invariant); schema
          // only, no PII. It is the whole form, unchanged across sections.
          full_schema: currentState.schema,
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
      }

      // Do NOT release the guard here: the switch is terminally DONE only when the
      // backend replies `session_ready` (-> handleSessionReady -> completeSectionSwitch),
      // so a stall after this handshake send is still caught by the watchdog
      // (Codex/fresh-eyes PR #137). isSectionSwitching was already cleared above so
      // the new socket's auto-reconnect works; switchInFlight stays set until ready.

    } catch (error) {
      // A failed reconnect/handshake must surface `error` (bd polyglot-pdf-aun),
      // not leave the UI stuck on `switching_section`. failSectionSwitch clears
      // the guards, disarms the watchdog, sets `error`, and fires onError.
      this.failSectionSwitch(
        error instanceof Error ? error.message : 'Section switch failed');
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
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  async switchToSection(sectionId: string, wsUrl: string): Promise<void> {
    // bd polyglot-pdf-0y7: clear the confirm-loop failure streak on a section
    // switch so a stale count can't carry into the new section (e.g. a same
    // field_id in the next section would otherwise trip the breaker one cycle
    // early). The in-session auto-switch keeps the SAME WebSocket open (no
    // reconnect, so handleOpen's reset does not fire). Also resets the session-wide
    // re-prompt cap (bd polyglot-pdf-r2hy).
    this.resetUnconfirmableTracking();
    // Same for the AI-value validation-reject loop-breaker (bd polyglot-pdf-wpw.3):
    // a reject streak must not carry across a section switch (this same-socket path
    // does not hit handleOpen's reset).
    this.resetValidationRejectTracking();

    // Re-entrancy guard (bd polyglot-pdf-aun): a manual switch arriving while an
    // AI-initiated switch is mid-flight (or vice versa) must not start a second
    // overlapping switch. The backend (post-0c1) also rejects the second switch
    // with success:false; this guard stops the FE from even sending it.
    if (this.switchInFlight) {
      // THROW (not a silent resolve) so the caller can roll back: the UI pre-updates
      // currentSectionId/sessionStorage before awaiting this, so a silent ignore
      // would leave the UI on the wrong section while the first switch is still
      // running (Codex PR #137).
      console.warn('[WebFormConnection] switchToSection rejected -- a section switch is already in progress');
      throw new Error('A section switch is already in progress');
    }
    // Claim the guard SYNCHRONOUSLY, before ANY await -- otherwise two concurrent
    // callers (an AI prepare_section_switch and a user nav click in the same tick)
    // both pass the check above and race past the await below (fresh-eyes PR #137).
    // Set the status + arm the watchdog here too so the whole switch window is
    // covered. This path keeps the SAME socket open and waits for the backend's
    // `section_switched` (-> handleSectionSwitched -> completeSectionSwitch) or an
    // `error` (-> handleServerError -> failSectionSwitch); the watchdog backstops a
    // switch that never replies.
    this.switchInFlight = true;
    this.setStatus('switching_section', "switchToSection");
    this.armSectionSwitchWatchdog();

    let currentState: ReturnType<typeof SchemaFormStateManager.load>;
    let targetSection: { id: string; order: number; label: string } | undefined;
    try {
      currentState = SchemaFormStateManager.load();
      if (!currentState || !currentState.schema.sections) {
        throw new Error('Sections not initialized');
      }

      // Find section by ID
      targetSection = currentState.schema.sections.find(s => s.id === sectionId) as any;
      if (!targetSection) {
        throw new Error(`Section not found: ${sectionId}`);
      }

      // Validate range
      if (targetSection.order < 1 || targetSection.order > currentState.schema.sections.length) {
        throw new Error(`Invalid section number: ${targetSection.order} (must be 1-${currentState.schema.sections.length})`);
      }
    } catch (err) {
      // A validation failure must release the guard we just claimed (else the next
      // switch is wrongly rejected) and surface error, not stay switching_section.
      this.failSectionSwitch(err instanceof Error ? err.message : 'Section switch failed');
      throw err;
    }

    // Wait for WebSocket send buffer to drain before sending control message
    // This prevents the control message from being queued behind audio frames
    console.log('[WebFormConnection] Waiting for buffer to drain before section switch');
    await this.waitForBufferDrain(1000);

    // Wrap the post-validation state-update + send in a catch so an unexpected
    // throw (e.g. corrupted sessionStorage in extractSectionFields) releases the
    // guard immediately rather than leaving it stuck until the watchdog fires.
    try {
      // Switch to target section in local state
      const updatedState = SchemaFormStateManager.switchToSection(currentState, sectionId);
      this.state = updatedState;

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
    } catch (err) {
      this.failSectionSwitch(err instanceof Error ? err.message : 'Section switch failed');
      throw err;
    }
  }

  /**
   * Complete current section and move to next
   *
   * @param wsUrl - Backend WebSocket URL (REQUIRED - no default to prevent localhost fallback in production)
   *
   * DEPRECATED (bd polyglot-pdf-55jg): section-reset production path;
   * continuous-DTI is the live flow. Kept as a fallback, not deleted.
   * Do not extend.
   */
  async completeSection(wsUrl: string): Promise<void> {
    // Continuous-session mode (bd polyglot-pdf-x8rt): no sections to complete or
    // advance -- this would call startSection on a real next-section id, restarting
    // the session we keep open. Defense-in-depth: completeSection has no UI caller
    // today, but guarding it keeps every section-mutation entry point consistent so
    // a future caller can't bypass the continuous-mode contract.
    if (this.continuousSessionEnabled) return;
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
      this.setStatus('connected', "completeSection:last-section"); // Stay connected but don't start new section
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
