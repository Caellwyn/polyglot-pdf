/**
 * ConfigEditorPage (bd polyglot-pdf-b6943): the round-trip test the exit
 * criteria name -- "the config editor round trip against a mocked API".
 *
 * Pins: load renders the channel's current values; Save PUTs exactly ONE key
 * (config_routes.py's ConfigPutRequest contract -- a whole-doc PUT would let
 * a stale value in the form clobber a key someone else just set); after a
 * successful save the page RE-READS the channel (GET) so the screen reflects
 * what the server actually stored, not merely the form's draft; unknown_keys
 * render read-only, never as an editable row a save could target; a
 * mid-session AuthError/ForbiddenError routes to onAuthExpired instead of
 * this page's own generic error banner (fresh-eyes finding: the gate's
 * refused-screen machinery existed but nothing ever called it).
 *
 * SCHEMA-DRIVEN CONTROLS (bd polyglot-pdf-wxcj0): a `bool` key renders a
 * <select> whose change sends a real boolean (not the string "true"); an
 * `int`/`float` key renders a number input and sends a JS number; a key
 * absent from `schema` (or of an unrecognized type) falls back to the
 * original text input, unchanged from before this bead.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { ConfigEditorPage } from './ConfigEditorPage';
import { AuthError, ForbiddenError, getChannelConfig, setChannelConfigKey } from '../utils/adminApi';

vi.mock('../utils/adminApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../utils/adminApi')>();
  // Keep the REAL error classes -- onAuthExpired branches on instanceof.
  return { ...actual, getChannelConfig: vi.fn(), setChannelConfigKey: vi.fn() };
});

const STAGING_SCHEMA = {
  LINK_MINTING_ENABLED: { type: 'bool', default: false },
};

const STAGING_CONFIG = {
  channel: 'staging',
  values: { LINK_MINTING_ENABLED: false, STALE_KEY: 'orphan' },
  known_keys: ['LINK_MINTING_ENABLED'],
  unknown_keys: ['STALE_KEY'],
  schema: STAGING_SCHEMA,
};

// One key of each type the console knows how to render, plus one of an
// unrecognized type -- feeds every branch of controlKind() in one fixture.
const TYPED_CONFIG = {
  channel: 'staging',
  values: {
    LINK_MINTING_ENABLED: true,
    LINK_FIRM_CAP: 30,
    LINK_COST_CEILING_USD: 4.5,
    SOME_STRING_KEY: 'hello',
  },
  known_keys: [
    'LINK_MINTING_ENABLED', 'LINK_FIRM_CAP', 'LINK_COST_CEILING_USD', 'SOME_STRING_KEY',
  ],
  unknown_keys: [],
  schema: {
    LINK_MINTING_ENABLED: { type: 'bool', default: false },
    LINK_FIRM_CAP: { type: 'int', default: 30 },
    LINK_COST_CEILING_USD: { type: 'float', default: 10.0 },
    SOME_STRING_KEY: { type: 'mystery', default: null },
  },
};

const noAuthExpired = () => false;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getChannelConfig).mockResolvedValue(STAGING_CONFIG);
});

describe('ConfigEditorPage', () => {
  it('loads the default channel and renders its known + unknown keys', async () => {
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledWith('staging'));
    expect(await screen.findByLabelText('LINK_MINTING_ENABLED')).toHaveValue('false');
    expect(screen.getByText('STALE_KEY')).toBeInTheDocument();
    expect(screen.getByText('orphan')).toBeInTheDocument();
    // Unknown keys are read-only: no input rendered for them.
    expect(screen.queryByLabelText('STALE_KEY')).not.toBeInTheDocument();
  });

  // Fresh-eyes round-2 gap on bd polyglot-pdf-dp1zq: this page renders a
  // PageIntro (same commit as WhoAmIPage's), but nothing pinned it here --
  // the same gap shape round 1 fixed for WhoAmIPage.tsx, unfixed on this
  // sibling. A mutation deleting the <PageIntro> block previously passed
  // the full suite; this assertion is what makes that mutation fail.
  it('renders exactly one purpose header describing what the page is for', async () => {
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);
    const intros = await screen.findAllByTestId('page-intro');
    expect(intros).toHaveLength(1);
    expect(intros[0]).toHaveTextContent(
      'View and edit the per-channel policy flags (like minting on/off and spend ceilings) that take effect without a redeploy.',
    );
  });

  it('switching channel re-fetches that channel\'s config', async () => {
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);
    await screen.findByLabelText('LINK_MINTING_ENABLED');

    vi.mocked(getChannelConfig).mockResolvedValue({
      channel: 'demo',
      values: { LINK_MINTING_ENABLED: true },
      known_keys: ['LINK_MINTING_ENABLED'],
      unknown_keys: [],
      schema: STAGING_SCHEMA,
    });
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'demo' } });

    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledWith('demo'));
    await waitFor(() =>
      expect(screen.getByLabelText('LINK_MINTING_ENABLED')).toHaveValue('true'));
  });

  it('Save PUTs exactly the one edited key, then re-reads the channel', async () => {
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging',
      key: 'LINK_MINTING_ENABLED',
      before: false,
      after: true,
      request_id: 'req-1',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'true' } });

    // The re-read after save should reflect the NEW server-stored value.
    vi.mocked(getChannelConfig).mockResolvedValue({
      channel: 'staging',
      values: { LINK_MINTING_ENABLED: true, STALE_KEY: 'orphan' },
      known_keys: ['LINK_MINTING_ENABLED'],
      unknown_keys: ['STALE_KEY'],
      schema: STAGING_SCHEMA,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    // LINK_MINTING_ENABLED is a bool key -- the select's "true" option sends
    // the real boolean `true`, never the string "true".
    await waitFor(() =>
      expect(setChannelConfigKey).toHaveBeenCalledWith('staging', 'LINK_MINTING_ENABLED', true));
    // Exactly one PUT -- never a whole-doc write.
    expect(setChannelConfigKey).toHaveBeenCalledTimes(1);

    // getChannelConfig called again (initial load + post-save re-read).
    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Saved LINK_MINTING_ENABLED.')).toBeInTheDocument();
  });

  it('shows the server error and does not re-read on a failed save', async () => {
    vi.mocked(setChannelConfigKey).mockRejectedValue(
      new Error("'nope' is not a valid value for LINK_MINTING_ENABLED"));
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'false' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/not a valid value/)).toBeInTheDocument();
    // Only the initial load read the channel -- a failed write must not
    // trigger the success re-read.
    expect(getChannelConfig).toHaveBeenCalledTimes(1);
  });

  // Fresh-eyes finding on bd polyglot-pdf-b6943: SignInGate's refusedReason
  // prop and its dedicated test existed, but nothing in the app ever
  // constructed it -- a mid-session 401/403 surfaced as this page's generic
  // red error string with no path back to sign-in. Pin the fix: this page
  // routes an AuthError/ForbiddenError to onAuthExpired FIRST, and shows no
  // generic banner of its own when onAuthExpired reports it handled the
  // failure.
  it('routes a 403 on load to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(getChannelConfig).mockRejectedValueOnce(new ForbiddenError('Access was revoked'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<ConfigEditorPage onAuthExpired={onAuthExpired} />);

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(ForbiddenError);
    expect(screen.queryByText('Access was revoked')).not.toBeInTheDocument();
  });

  it('routes a 401 on save to onAuthExpired instead of the generic error banner', async () => {
    vi.mocked(setChannelConfigKey).mockRejectedValueOnce(new AuthError('Sign-in required'));
    const onAuthExpired = vi.fn((_err: unknown) => true);
    render(<ConfigEditorPage onAuthExpired={onAuthExpired} />);

    const input = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(input, { target: { value: 'false' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onAuthExpired).toHaveBeenCalledTimes(1));
    const [[passedErr]] = onAuthExpired.mock.calls;
    expect(passedErr).toBeInstanceOf(AuthError);
    expect(screen.queryByText(/Could not save/)).not.toBeInTheDocument();
  });

  // --------------------------------------------------------------------
  // Schema-driven controls (bd polyglot-pdf-wxcj0).
  // --------------------------------------------------------------------

  it('renders a bool key as a select, an int/float key as a number input, and an unknown type as text', async () => {
    vi.mocked(getChannelConfig).mockResolvedValue(TYPED_CONFIG);
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const boolControl = await screen.findByLabelText('LINK_MINTING_ENABLED');
    expect(boolControl.tagName).toBe('SELECT');
    expect(boolControl).toHaveValue('true');

    const intControl = screen.getByLabelText('LINK_FIRM_CAP');
    expect(intControl.tagName).toBe('INPUT');
    expect(intControl).toHaveAttribute('type', 'number');
    expect(intControl).toHaveAttribute('step', '1');
    expect(intControl).toHaveValue(30);

    const floatControl = screen.getByLabelText('LINK_COST_CEILING_USD');
    expect(floatControl.tagName).toBe('INPUT');
    expect(floatControl).toHaveAttribute('type', 'number');
    expect(floatControl).toHaveAttribute('step', 'any');
    expect(floatControl).toHaveValue(4.5);

    // A type this console doesn't recognize falls back to plain text --
    // never a crash, never a number input coercing a non-numeric value.
    const textControl = screen.getByLabelText('SOME_STRING_KEY');
    expect(textControl.tagName).toBe('INPUT');
    expect(textControl).not.toHaveAttribute('type', 'number');
    expect(textControl).toHaveValue('hello');
  });

  it('a bool select change sends a real boolean, not the string "true"/"false"', async () => {
    vi.mocked(getChannelConfig).mockResolvedValue(TYPED_CONFIG);
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging', key: 'LINK_MINTING_ENABLED', before: true, after: false, request_id: 'r1',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const boolControl = await screen.findByLabelText('LINK_MINTING_ENABLED');
    fireEvent.change(boolControl, { target: { value: 'false' } });

    const row = boolControl.closest('div')!.parentElement!;
    fireEvent.click(within(row).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setChannelConfigKey).toHaveBeenCalledWith(
      'staging', 'LINK_MINTING_ENABLED', false));
    const [, , sentValue] = vi.mocked(setChannelConfigKey).mock.calls[0];
    expect(typeof sentValue).toBe('boolean');
  });

  it('an int number-input change sends a JS number, not a string', async () => {
    vi.mocked(getChannelConfig).mockResolvedValue(TYPED_CONFIG);
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging', key: 'LINK_FIRM_CAP', before: 30, after: 45, request_id: 'r2',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const intControl = await screen.findByLabelText('LINK_FIRM_CAP');
    fireEvent.change(intControl, { target: { value: '45' } });

    const row = intControl.closest('div')!.parentElement!;
    fireEvent.click(within(row).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setChannelConfigKey).toHaveBeenCalledWith(
      'staging', 'LINK_FIRM_CAP', 45));
    const [, , sentValue] = vi.mocked(setChannelConfigKey).mock.calls[0];
    expect(typeof sentValue).toBe('number');
  });

  it('a float number-input change sends a JS number', async () => {
    vi.mocked(getChannelConfig).mockResolvedValue(TYPED_CONFIG);
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging', key: 'LINK_COST_CEILING_USD', before: 4.5, after: 7.25, request_id: 'r3',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const floatControl = await screen.findByLabelText('LINK_COST_CEILING_USD');
    fireEvent.change(floatControl, { target: { value: '7.25' } });

    const row = floatControl.closest('div')!.parentElement!;
    fireEvent.click(within(row).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(setChannelConfigKey).toHaveBeenCalledWith(
      'staging', 'LINK_COST_CEILING_USD', 7.25));
    const [, , sentValue] = vi.mocked(setChannelConfigKey).mock.calls[0];
    expect(typeof sentValue).toBe('number');
  });

  // Fresh-eyes finding on bd polyglot-pdf-wxcj0: an admin backend older than
  // this console (deploy-admin.sh not yet redeployed, while deploy-admin-
  // console.sh already shipped this page) returns GET /admin/config with NO
  // `schema` key at all. The page must degrade every row to a plain text
  // input, matching controlKind()'s own documented fallback -- not throw
  // reading `undefined[key]` and white-screen the tab.
  it('degrades to text inputs when the admin backend response has no schema field at all (deploy skew)', async () => {
    const noSchemaConfig = {
      channel: 'staging',
      values: { LINK_MINTING_ENABLED: false, LINK_FIRM_CAP: 30 },
      known_keys: ['LINK_MINTING_ENABLED', 'LINK_FIRM_CAP'],
      unknown_keys: [],
      // No `schema` key -- the shape GET /admin/config/{channel} had before
      // this bead.
    };
    vi.mocked(getChannelConfig).mockResolvedValue(noSchemaConfig as unknown as Awaited<ReturnType<typeof getChannelConfig>>);
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const boolControl = await screen.findByLabelText('LINK_MINTING_ENABLED');
    expect(boolControl.tagName).toBe('INPUT');
    expect(boolControl).not.toHaveAttribute('type', 'number');
    expect(boolControl).toHaveValue('false');

    const intControl = screen.getByLabelText('LINK_FIRM_CAP');
    expect(intControl.tagName).toBe('INPUT');
    expect(intControl).not.toHaveAttribute('type', 'number');
    expect(intControl).toHaveValue('30');
  });

  // Fresh-eyes finding on bd polyglot-pdf-wxcj0: `step="1"` on an int-typed
  // number input is a validation HINT only -- jsdom (and a real browser
  // outside a <form>'s submit event) never blocks entry of a decimal, and
  // Save is a plain button, not a submit. Without a client-side integer
  // check, `2.5` reaches setChannelConfigKey as a JS number and the server's
  // coerce_value (`int(2.5)`) truncates it to `2` SILENTLY -- turning what
  // was a loud 400 refusal on origin/dev into a silent mis-write.
  it('typing a decimal into an int key is refused client-side, not silently truncated', async () => {
    vi.mocked(getChannelConfig).mockResolvedValue(TYPED_CONFIG);
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const intControl = await screen.findByLabelText('LINK_FIRM_CAP');
    fireEvent.change(intControl, { target: { value: '2.5' } });

    const row = intControl.closest('div')!.parentElement!;
    fireEvent.click(within(row).getByRole('button', { name: 'Save' }));

    expect(await screen.findByText(/'2.5' is not a valid value for LINK_FIRM_CAP/)).toBeInTheDocument();
    expect(setChannelConfigKey).not.toHaveBeenCalled();
  });

  it('a bool select left on "unset -- use the fallback" does not PUT on Save, and tells the operator why', async () => {
    const unsetConfig = {
      channel: 'staging',
      values: {},
      known_keys: ['LINK_MINTING_ENABLED'],
      unknown_keys: [],
      schema: STAGING_SCHEMA,
    };
    vi.mocked(getChannelConfig).mockResolvedValue(unsetConfig);
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const boolControl = await screen.findByLabelText('LINK_MINTING_ENABLED');
    expect(boolControl).toHaveValue('__unset__');

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    // No PUT happens: there is nothing to save while the draft is unset.
    await waitFor(() => expect(getChannelConfig).toHaveBeenCalledTimes(1));
    expect(setChannelConfigKey).not.toHaveBeenCalled();
    // The click is not silent: the operator is told there was nothing to save.
    expect(await screen.findByText(/Nothing to save for LINK_MINTING_ENABLED/)).toBeInTheDocument();
  });

  it('Save on an unset row clears a stale "Saved ..." banner from a previous row', async () => {
    const config = {
      channel: 'staging',
      values: { LINK_FIRM_CAP: 5 },
      known_keys: ['LINK_FIRM_CAP', 'LINK_MINTING_ENABLED'],
      unknown_keys: [],
      schema: STAGING_SCHEMA,
    };
    vi.mocked(getChannelConfig).mockResolvedValue(config);
    vi.mocked(setChannelConfigKey).mockResolvedValue({
      channel: 'staging',
      key: 'LINK_FIRM_CAP',
      before: 5,
      after: 9,
      request_id: 'req-2',
    });
    render(<ConfigEditorPage onAuthExpired={noAuthExpired} />);

    const intControl = await screen.findByLabelText('LINK_FIRM_CAP');
    fireEvent.change(intControl, { target: { value: '9' } });
    const capRow = intControl.closest('div')!.parentElement!;
    fireEvent.click(within(capRow).getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('Saved LINK_FIRM_CAP.')).toBeInTheDocument();

    const boolControl = screen.getByLabelText('LINK_MINTING_ENABLED');
    expect(boolControl).toHaveValue('__unset__');
    const boolRow = boolControl.closest('div')!.parentElement!;
    fireEvent.click(within(boolRow).getByRole('button', { name: 'Save' }));

    // The stale success banner from the PREVIOUS row's save must not survive
    // a click that does nothing -- it would otherwise read as confirmation
    // of a save that never happened.
    expect(screen.queryByText('Saved LINK_FIRM_CAP.')).not.toBeInTheDocument();
    expect(await screen.findByText(/Nothing to save for LINK_MINTING_ENABLED/)).toBeInTheDocument();
  });
});
