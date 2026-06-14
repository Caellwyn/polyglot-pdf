/**
 * Undo/redo history for the edited schema (bd polyglot-pdf-v3y8).
 *
 * The editor previously had NO undo: one wrong edit forced a full Reset (losing
 * all progress) or hand-editing JSON. This hook owns the schema as a past /
 * present / future stack so every edit is reversible (Cmd+Z) and re-appliable
 * (Cmd+Shift+Z).
 *
 * Usage in App: replace `useState<FormSchema|null>` + the manual
 * `hasUnsavedChanges` flag with this hook.
 *   - `commit(next)`  -- a user EDIT: push present onto the past, set next,
 *                        clear the redo future, mark dirty.
 *   - `load(schema)`  -- a fresh load (form select / reload-from-file): set as
 *                        the new baseline, CLEAR history, mark clean.
 *   - `markSaved()`   -- a save succeeded: keep history, mark clean.
 *   - `clear()`       -- no schema (initial / form-switch teardown).
 *   - `undo()` / `redo()` with `canUndo` / `canRedo`.
 *
 * `isDirty` is derived: true whenever the present differs from the last
 * saved/loaded baseline (so undoing back to the baseline correctly clears the
 * dirty flag, and redoing past it re-sets it).
 */
import { useCallback, useState } from 'react';
import type { FormSchema } from '../types/schema';

interface HistoryState {
  past: FormSchema[];
  present: FormSchema | null;
  future: FormSchema[];
  // The schema as last loaded or saved -- the clean baseline isDirty compares to.
  baseline: FormSchema | null;
}

const EMPTY: HistoryState = { past: [], present: null, future: [], baseline: null };

export interface SchemaHistory {
  schema: FormSchema | null;
  isDirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
  /** A user edit: pushes the prior present to the undo stack. */
  commit: (next: FormSchema) => void;
  /** A fresh load: new baseline, history cleared, clean. */
  load: (schema: FormSchema) => void;
  /** Mark the current present as saved (clean) without touching history. */
  markSaved: () => void;
  /** Drop the schema entirely (initial state / form-switch teardown). */
  clear: () => void;
  undo: () => void;
  redo: () => void;
}

export function useSchemaHistory(): SchemaHistory {
  const [state, setState] = useState<HistoryState>(EMPTY);

  const commit = useCallback((next: FormSchema) => {
    setState((s) => ({
      past: s.present ? [...s.past, s.present] : s.past,
      present: next,
      future: [], // a new edit invalidates the redo stack
      baseline: s.baseline,
    }));
  }, []);

  const load = useCallback((schema: FormSchema) => {
    setState({ past: [], present: schema, future: [], baseline: schema });
  }, []);

  const markSaved = useCallback(() => {
    setState((s) => ({ ...s, baseline: s.present }));
  }, []);

  const clear = useCallback(() => setState(EMPTY), []);

  const undo = useCallback(() => {
    setState((s) => {
      if (s.past.length === 0) return s;
      const previous = s.past[s.past.length - 1];
      return {
        past: s.past.slice(0, -1),
        present: previous,
        future: s.present ? [s.present, ...s.future] : s.future,
        baseline: s.baseline,
      };
    });
  }, []);

  const redo = useCallback(() => {
    setState((s) => {
      if (s.future.length === 0) return s;
      const next = s.future[0];
      return {
        past: s.present ? [...s.past, s.present] : s.past,
        present: next,
        future: s.future.slice(1),
        baseline: s.baseline,
      };
    });
  }, []);

  return {
    schema: state.present,
    isDirty: state.present !== state.baseline,
    canUndo: state.past.length > 0,
    canRedo: state.future.length > 0,
    commit,
    load,
    markSaved,
    clear,
    undo,
    redo,
  };
}
