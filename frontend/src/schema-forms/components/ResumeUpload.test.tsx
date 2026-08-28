// @vitest-environment jsdom
//
// The start-over / resume choice (bd polyglot-pdf-dft1).
//
// The properties worth pinning are about TRUST and about a client who is
// trying to recover their work:
//   1. the SERVER decides whether an upload is the assigned form -- a local
//      read must never stand in for that verdict
//   2. a refusal says one thing, never which check caught the file
//   3. a client can re-pick the same file after a mistake
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';

import { ResumeUpload } from './ResumeUpload';
import { RESUME_TRANSLATIONS } from '../resumeStrings';

const EN = RESUME_TRANSLATIONS.English;

function pdfFile(name = 'saved.pdf'): File {
  return new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], name, {
    type: 'application/pdf',
  });
}

function mounted(overrides: Partial<Parameters<typeof ResumeUpload>[0]> = {}) {
  const onResumed = vi.fn();
  const onStartOver = vi.fn();
  render(
    <ResumeUpload
      isOpen
      kitId="w7"
      pdfFilename="form.pdf"
      backendUrl="https://api.example"
      onResumed={onResumed}
      onStartOver={onStartOver}
      {...overrides}
    />,
  );
  return { onResumed, onStartOver };
}

function mockFetch(response: Partial<Response> & { json?: () => Promise<unknown> }) {
  const fetchMock = vi.fn(async () => response as unknown as Response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  // This project configures NO auto-cleanup, so an unmounted render stays in
  // the document and document.querySelector finds the STALE first instance.
  // Six tests here failed exactly that way before this line existed.
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('ResumeUpload', () => {
  it('sends the file to the SERVER for verification', async () => {
    // The load-bearing property: the browser does not decide. If this ever
    // resolves locally, a client-side attacker resumes anything they like.
    const fetchMock = mockFetch({
      ok: true,
      status: 200,
      json: async () => ({ field_values: { last_name: 'Okonkwo' }, link_jtis: [] }),
    });
    const { onResumed } = mounted();

    const input = document.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pdfFile()] } });

    await waitFor(() => expect(onResumed).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://api.example/api/resume-form');
    const body = JSON.parse(String(init.body));
    expect(body.kit_id).toBe('w7');
    expect(body.pdf_base64).toBeTruthy();
  });

  it('hands back the answers and the carried session id', async () => {
    mockFetch({
      ok: true,
      status: 200,
      json: async () => ({
        field_values: { last_name: 'Okonkwo' },
        form_session_id: 'fss_1_abc',
        link_jtis: ['jti-a'],
      }),
    });
    const { onResumed } = mounted();

    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement, {
      target: { files: [pdfFile()] },
    });

    await waitFor(() => expect(onResumed).toHaveBeenCalled());
    expect(onResumed).toHaveBeenCalledWith({
      fieldValues: { last_name: 'Okonkwo' },
      formSessionId: 'fss_1_abc',
      linkJtis: ['jti-a'],
    });
  });

  it('shows the mismatch message when the server refuses', async () => {
    mockFetch({ ok: false, status: 400, json: async () => ({}) });
    const { onResumed } = mounted();

    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement, {
      target: { files: [pdfFile()] },
    });

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toBe(EN.resumeMismatch);
    expect(onResumed).not.toHaveBeenCalled();
  });

  it('never resumes when the server refuses, whatever the body says', async () => {
    // A refused response that still carries field values must not be used.
    // Trusting the body over the status is how a rejected file gets in.
    mockFetch({
      ok: false,
      status: 400,
      json: async () => ({ field_values: { last_name: 'INJECTED' } }),
    });
    const { onResumed } = mounted();

    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement, {
      target: { files: [pdfFile()] },
    });

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(onResumed).not.toHaveBeenCalled();
  });

  it('shows a readable message when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network down'); }));
    mounted();

    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement, {
      target: { files: [pdfFile()] },
    });

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toBe(EN.resumeUnreadable);
  });

  it('lets a client re-pick the SAME file after a mistake', async () => {
    // Browsers do not fire change for an identical value, so the input must be
    // cleared -- otherwise a client who picks the wrong file, then the right
    // one, then the right one again sees nothing happen.
    const fetchMock = mockFetch({ ok: false, status: 400, json: async () => ({}) });
    mounted();

    const input = document.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [pdfFile('same.pdf')] } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    expect(input.value).toBe('');
    fireEvent.change(input, { target: { files: [pdfFile('same.pdf')] } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('offers START OVER as the other choice', async () => {
    const { onStartOver } = mounted();
    fireEvent.click(screen.getByText(EN.startOverAction));
    expect(onStartOver).toHaveBeenCalled();
  });

  it('renders in the client language, not English', () => {
    mounted({ selectedLanguage: 'Spanish' });
    expect(screen.getByText(RESUME_TRANSLATIONS.Spanish.resumeTitle)).toBeTruthy();
  });

  it('renders nothing when closed', () => {
    const { container } = render(
      <ResumeUpload
        isOpen={false}
        kitId="w7"
        pdfFilename="form.pdf"
        backendUrl="https://api.example"
        onResumed={vi.fn()}
        onStartOver={vi.fn()}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('attaches the bearer token, because the route is auth-gated', async () => {
    const fetchMock = mockFetch({ ok: true, status: 200, json: async () => ({ field_values: {} }) });
    mounted({ getToken: async () => 'tok-123' });

    fireEvent.change(document.querySelector('input[type=file]') as HTMLInputElement, {
      target: { files: [pdfFile()] },
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
  });
});
