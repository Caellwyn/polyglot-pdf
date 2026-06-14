/**
 * Unit tests for the undo/redo schema-history hook (bd polyglot-pdf-v3y8).
 */
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSchemaHistory } from './useSchemaHistory';
import type { FormSchema } from '../types/schema';

const mk = (title: string): FormSchema => ({
  form_metadata: { title, form_number: 'T-1', version: '1' },
  fields: [],
} as unknown as FormSchema);

const A = mk('A');
const B = mk('B');
const C = mk('C');

describe('useSchemaHistory', () => {
  it('starts empty: no schema, not dirty, nothing to undo/redo', () => {
    const { result } = renderHook(() => useSchemaHistory());
    expect(result.current.schema).toBeNull();
    expect(result.current.isDirty).toBe(false);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
  });

  it('load sets a clean baseline with no history', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    expect(result.current.schema).toBe(A);
    expect(result.current.isDirty).toBe(false);
    expect(result.current.canUndo).toBe(false);
  });

  it('commit marks dirty and enables undo', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    expect(result.current.schema).toBe(B);
    expect(result.current.isDirty).toBe(true);
    expect(result.current.canUndo).toBe(true);
    expect(result.current.canRedo).toBe(false);
  });

  it('undo walks back to the prior present and re-enables redo', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.undo());
    expect(result.current.schema).toBe(A);
    expect(result.current.canRedo).toBe(true);
    // Undone back to the baseline -> no longer dirty.
    expect(result.current.isDirty).toBe(false);
  });

  it('redo re-applies an undone edit', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.undo());
    act(() => result.current.redo());
    expect(result.current.schema).toBe(B);
    expect(result.current.isDirty).toBe(true);
    expect(result.current.canRedo).toBe(false);
  });

  it('multi-step undo walks back through edits in order', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.commit(C));
    act(() => result.current.undo());
    expect(result.current.schema).toBe(B);
    act(() => result.current.undo());
    expect(result.current.schema).toBe(A);
    expect(result.current.canUndo).toBe(false);
  });

  it('a new commit after undo invalidates the redo future', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.undo());      // back to A, redo->B available
    act(() => result.current.commit(C));   // new branch -> redo future cleared
    expect(result.current.schema).toBe(C);
    expect(result.current.canRedo).toBe(false);
  });

  it('markSaved clears dirty without losing undo history', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.markSaved());
    expect(result.current.isDirty).toBe(false);
    expect(result.current.canUndo).toBe(true); // history preserved
    // Undoing away from the saved baseline makes it dirty again.
    act(() => result.current.undo());
    expect(result.current.isDirty).toBe(true);
  });

  it('load after edits clears history (a fresh form resets undo)', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.load(C));
    expect(result.current.schema).toBe(C);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);
    expect(result.current.isDirty).toBe(false);
  });

  it('clear drops everything', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.commit(B));
    act(() => result.current.clear());
    expect(result.current.schema).toBeNull();
    expect(result.current.canUndo).toBe(false);
  });

  it('undo/redo are no-ops at the ends of the stack', () => {
    const { result } = renderHook(() => useSchemaHistory());
    act(() => result.current.load(A));
    act(() => result.current.undo()); // nothing to undo
    expect(result.current.schema).toBe(A);
    act(() => result.current.redo()); // nothing to redo
    expect(result.current.schema).toBe(A);
  });
});
