// @vitest-environment jsdom
//
// WHEN the save prompt appears (bd polyglot-pdf-dft1).
//
// The timing rules carry the judgment, so they are tested apart from the
// component. Two failure modes matter and they pull opposite ways:
//   - never nudging: the client loses everything and never knew saving existed
//   - nudging repeatedly: they learn to dismiss by reflex, which is the same
//     outcome with extra steps
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import { useSaveNudge } from './useSaveNudge';

function fakeStorage(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v;
    },
    _data: data,
  };
}

const BASE = {
  formSessionId: 'fss_1_abc',
  completedSectionCount: 0,
  voiceEnding: false,
  enabled: true,
};

describe('useSaveNudge', () => {
  it('says nothing before a section is finished', () => {
    const { result } = renderHook(() =>
      useSaveNudge({ ...BASE, storage: fakeStorage() }),
    );
    expect(result.current.variant).toBeNull();
  });

  it('shows the EARLY nudge once the first section is done', () => {
    const { result } = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage: fakeStorage() }),
    );
    expect(result.current.variant).toBe('early');
  });

  it('STAYS dismissed -- nagging trains a client to ignore it', () => {
    const storage = fakeStorage();
    const { result, rerender } = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage }),
    );
    expect(result.current.variant).toBe('early');

    act(() => result.current.dismiss());
    rerender();
    expect(result.current.variant).toBeNull();
  });

  it('stays dismissed across a RELOAD, not just a re-render', () => {
    // A client who reloads has not un-learned the nudge. Re-showing it every
    // refresh is how reflex-dismissal is taught.
    const storage = fakeStorage();
    const first = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage }),
    );
    act(() => first.result.current.dismiss());

    const second = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage }),
    );
    expect(second.result.current.variant).toBeNull();
  });

  it('shows the ENDING nudge when voice is stopping', () => {
    const { result } = renderHook(() =>
      useSaveNudge({ ...BASE, voiceEnding: true, storage: fakeStorage() }),
    );
    expect(result.current.variant).toBe('ending');
  });

  it('ENDING outranks EARLY when both would fire', () => {
    // The client is about to lose voice; that is the more urgent message.
    const { result } = renderHook(() =>
      useSaveNudge({
        ...BASE,
        completedSectionCount: 3,
        voiceEnding: true,
        storage: fakeStorage(),
      }),
    );
    expect(result.current.variant).toBe('ending');
  });

  it('shows the ENDING nudge even after the EARLY one was dismissed', () => {
    // Dismissing "not now" early must not silence the urgent one later.
    const storage = fakeStorage();
    const { result, rerender } = renderHook(
      (props: { voiceEnding: boolean }) =>
        useSaveNudge({
          ...BASE,
          completedSectionCount: 1,
          voiceEnding: props.voiceEnding,
          storage,
        }),
      { initialProps: { voiceEnding: false } },
    );
    act(() => result.current.dismiss());
    expect(result.current.variant).toBeNull();

    rerender({ voiceEnding: true });
    expect(result.current.variant).toBe('ending');
  });

  it('stops asking once the client has actually SAVED', () => {
    const storage = fakeStorage();
    const { result, rerender } = renderHook(
      (props: { voiceEnding: boolean }) =>
        useSaveNudge({
          ...BASE,
          completedSectionCount: 2,
          voiceEnding: props.voiceEnding,
          storage,
        }),
      { initialProps: { voiceEnding: false } },
    );

    act(() => result.current.markSaved());
    expect(result.current.variant).toBeNull();

    // ...and not even when voice ends: they have the habit.
    rerender({ voiceEnding: true });
    expect(result.current.variant).toBeNull();
  });

  it('says nothing for a STAFF session', () => {
    const { result } = renderHook(() =>
      useSaveNudge({
        ...BASE,
        enabled: false,
        completedSectionCount: 3,
        voiceEnding: true,
        storage: fakeStorage(),
      }),
    );
    expect(result.current.variant).toBeNull();
  });

  it('says nothing before the form session exists', () => {
    const { result } = renderHook(() =>
      useSaveNudge({
        ...BASE,
        formSessionId: null,
        completedSectionCount: 3,
        storage: fakeStorage(),
      }),
    );
    expect(result.current.variant).toBeNull();
  });

  it('treats a RESUMED session as its own', () => {
    // A resumed form carries a different session id; its flags are separate,
    // so a client who resumes still learns to save the new file.
    const storage = fakeStorage({ 'polyglot.saveNudge.early.fss_OLD': '1' });
    const { result } = renderHook(() =>
      useSaveNudge({
        ...BASE,
        formSessionId: 'fss_NEW',
        completedSectionCount: 1,
        storage,
      }),
    );
    expect(result.current.variant).toBe('early');
  });

  it('survives storage that THROWS', () => {
    // Private browsing and some embedded webviews throw on access. The cost
    // must be an extra nudge, never a broken page.
    const hostile = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    };
    const { result } = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage: hostile }),
    );
    expect(result.current.variant).toBe('early');
    expect(() => act(() => result.current.dismiss())).not.toThrow();
  });

  it('persists under a key scoped to the form session', () => {
    const storage = fakeStorage();
    const { result } = renderHook(() =>
      useSaveNudge({ ...BASE, completedSectionCount: 1, storage }),
    );
    act(() => result.current.dismiss());
    expect(Object.keys(storage._data)).toEqual(['polyglot.saveNudge.early.fss_1_abc']);
  });
});
