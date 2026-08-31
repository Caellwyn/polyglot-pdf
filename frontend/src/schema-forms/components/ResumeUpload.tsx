/**
 * Start over, or continue from the PDF you saved (bd polyglot-pdf-dft1).
 *
 * A client does NOT choose a form -- their link already decided that. So this
 * is not a form picker: it is one question ("start fresh, or continue what you
 * saved?") plus a drop target, shown on the form the link already opened.
 *
 * THE UPLOAD IS VERIFIED SERVER-SIDE, always. The browser may look at the file
 * first for a fast, friendly message, but a client-side check is defeated by a
 * client-side attacker -- POST /api/resume-form compares the upload against the
 * kit's own form.pdf and refuses anything that is not structurally identical.
 * This component must never treat a local read as permission to proceed.
 */
import { useCallback, useRef, useState } from 'react';

import { resumeStrings } from '../resumeStrings';

export interface ResumeResult {
  /** schema field id -> value, ready to merge into form state. */
  fieldValues: Record<string, string>;
  /** The session id carried in the file, when it had one. */
  formSessionId?: string;
  /** Link ids this form has used, oldest first (bd polyglot-pdf-1uyof). */
  linkJtis: string[];
}

export interface ResumeUploadProps {
  isOpen: boolean;
  kitId: string;
  pdfFilename: string;
  selectedLanguage?: string;
  /** Resolves the caller's bearer token; the route is auth-gated. */
  getToken?: () => Promise<string | undefined>;
  backendUrl: string;
  onResumed: (result: ResumeResult) => void;
  onStartOver: () => void;
}

type Phase = 'choosing' | 'reading' | 'error';

/**
 * Read a File's bytes.
 *
 * File.arrayBuffer() is the modern path, but it is absent in this project's
 * jsdom (verified) and in older mobile browsers -- and a client recovering
 * their work is exactly the person likely to be on an old phone. FileReader
 * is the universal fallback.
 */
function readBytes(file: File): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') {
    return file.arrayBuffer().then((b) => new Uint8Array(b));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error ?? new Error('unreadable file'));
    reader.readAsArrayBuffer(file);
  });
}

/** Base64 without blowing the stack on a multi-megabyte file. */
function toBase64(bytes: Uint8Array): string {
  let binary = '';
  const CHUNK = 0x8000;   // String.fromCharCode is variadic; a whole PDF overflows it
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

export function ResumeUpload({
  isOpen,
  kitId,
  pdfFilename,
  selectedLanguage,
  getToken,
  backendUrl,
  onResumed,
  onStartOver,
}: ResumeUploadProps) {
  const t = resumeStrings(selectedLanguage);
  const [phase, setPhase] = useState<Phase>('choosing');
  const [message, setMessage] = useState<string>('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setPhase('reading');
      setMessage('');
      try {
        const bytes = await readBytes(file);
        const token = getToken ? await getToken() : undefined;

        const response = await fetch(`${backendUrl}/api/resume-form`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            kit_id: kitId,
            pdf_filename: pdfFilename,
            pdf_base64: toBase64(bytes),
          }),
        });

        if (!response.ok) {
          // The server deliberately returns ONE message for every structural
          // failure, so do not try to be more specific than it was: guessing
          // would tell an attacker which check caught them.
          setPhase('error');
          setMessage(response.status === 413 ? t.resumeUnreadable : t.resumeMismatch);
          return;
        }

        const data = await response.json();
        onResumed({
          fieldValues: data.field_values ?? {},
          formSessionId: data.form_session_id ?? undefined,
          linkJtis: Array.isArray(data.link_jtis) ? data.link_jtis : [],
        });
      } catch {
        // A network failure or an unreadable file. Never a stack trace: the
        // client is trying to recover work, not debug us.
        setPhase('error');
        setMessage(t.resumeUnreadable);
      }
    },
    [backendUrl, getToken, kitId, onResumed, pdfFilename, t],
  );

  if (!isOpen) return null;

  return (
    <div className="resume-upload" role="dialog" aria-modal="true" aria-label={t.resumeTitle}>
      <h2>{t.resumeTitle}</h2>
      <p>{t.resumeBody}</p>

      <div
        className={`resume-dropzone${dragging ? ' is-dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
        role="button"
        tabIndex={0}
      >
        {phase === 'reading' ? '...' : t.dropHere}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFile(file);
          // Clear the input so choosing the SAME file twice fires again --
          // a client who mis-picks and re-picks the right file otherwise
          // sees nothing happen.
          e.target.value = '';
        }}
      />

      {phase === 'error' && (
        <p className="resume-error" role="alert">
          {message}
        </p>
      )}

      <button type="button" className="resume-start-over" onClick={onStartOver}>
        {t.startOverAction}
      </button>
    </div>
  );
}
