import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSnapToField } from './useSnapToField';

function makeContainer(fieldIds: string[]) {
  const container = document.createElement('div');
  const spies: Record<string, ReturnType<typeof vi.fn>> = {};
  for (const id of fieldIds) {
    const el = document.createElement('div');
    el.setAttribute('data-field-id', id);
    // jsdom has no layout: give the overlay a real height and a spyable
    // scrollIntoView (jsdom does not implement it).
    el.getBoundingClientRect = () =>
      ({ top: 100, left: 0, width: 50, height: 18, right: 50, bottom: 118, x: 0, y: 100, toJSON: () => ({}) }) as DOMRect;
    spies[id] = vi.fn();
    (el as any).scrollIntoView = spies[id];
    container.appendChild(el);
  }
  return { ref: { current: container }, spies };
}

describe('useSnapToField', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('snaps to the current field on mount, including bracketed mirror ids', () => {
    const { ref, spies } = makeContainer(['p1_line3a_familyname[1]']);
    renderHook(() => useSnapToField(ref, 'p1_line3a_familyname[1]', true));
    expect(spies['p1_line3a_familyname[1]']).toHaveBeenCalledWith({
      behavior: 'auto',
      block: 'center',
      inline: 'nearest',
    });
  });

  it('snaps when the field changes', () => {
    const { ref, spies } = makeContainer(['a', 'b']);
    const { rerender } = renderHook(
      ({ id }: { id: string }) => useSnapToField(ref, id, true),
      { initialProps: { id: 'a' } }
    );
    expect(spies['a']).toHaveBeenCalledTimes(1);
    rerender({ id: 'b' });
    expect(spies['b']).toHaveBeenCalledTimes(1);
    // No re-snap to a: user wandering between advances is never fought.
    expect(spies['a']).toHaveBeenCalledTimes(1);
  });

  it('retries while the overlay is missing and gives up after the cap', () => {
    const { ref } = makeContainer([]);
    const spy = vi.spyOn(ref.current, 'querySelector');
    renderHook(() => useSnapToField(ref, 'never-rendered', true));
    vi.advanceTimersByTime(5000);
    // 1 initial attempt + at most 10 interval attempts, then the interval
    // stops -- advancing further must not query again.
    const callsAfterCap = spy.mock.calls.length;
    expect(callsAfterCap).toBeLessThanOrEqual(11);
    vi.advanceTimersByTime(5000);
    expect(spy.mock.calls.length).toBe(callsAfterCap);
  });

  it('does NOT re-snap when isSnappable identity churns without a field change', () => {
    // Production regression shape: state reloads hand the pane a fresh schema
    // object per fill, so a naively-memoized isSnappable gets a new identity
    // per fill. The hook must not re-snap on that churn (free-wander rule).
    const { ref, spies } = makeContainer(['a']);
    const { rerender } = renderHook(
      ({ fn }: { fn: (id: string) => boolean }) => useSnapToField(ref, 'a', true, fn),
      { initialProps: { fn: () => true } }
    );
    expect(spies['a']).toHaveBeenCalledTimes(1);
    rerender({ fn: () => true }); // fresh closure identity, same field
    rerender({ fn: () => true });
    expect(spies['a']).toHaveBeenCalledTimes(1);
  });

  it('short-circuits unpositioned fields without polling', () => {
    const { ref } = makeContainer([]);
    const spy = vi.spyOn(ref.current, 'querySelector');
    renderHook(() => useSnapToField(ref, 'unpositioned', true, () => false));
    vi.advanceTimersByTime(5000);
    expect(spy).not.toHaveBeenCalled();
  });

  it('cleans up the retry interval on unmount', () => {
    const { ref } = makeContainer([]);
    const spy = vi.spyOn(ref.current, 'querySelector');
    const { unmount } = renderHook(() => useSnapToField(ref, 'never-rendered', true));
    vi.advanceTimersByTime(450); // a couple of retries in flight
    const before = spy.mock.calls.length;
    unmount();
    vi.advanceTimersByTime(5000);
    expect(spy.mock.calls.length).toBe(before);
  });
});
