/**
 * ONE definition of which kits the catalogue shows (bd polyglot-pdf-n5fwd,
 * polyglot-pdf-tx8gi).
 *
 * WHY SHARED. Each catalogue renders its kits TWICE -- as a card grid and as a
 * compact `<select>` strip -- and there are two catalogues (hosted and local
 * folder), so this list is rendered four times. Filtering at each render site
 * is four chances to disagree about what exists, and a strip that offers a kit
 * the cards deny is worse than no filter at all. So the decision lives here and
 * every surface asks the same function.
 *
 * Deliberately pure and dependency-free: it takes the fields both entry types
 * already share, so hosted `RemoteKitEntry` and local `CatalogueEntry` both
 * satisfy it without either importing the other.
 */

/** The fields a catalogue entry must expose to be filtered. Both entry types
 *  satisfy this structurally. */
export interface FilterableKit {
  id: string;
  label?: string | null;
  status: string;
  hidden?: boolean;
}

export interface CatalogueFilter {
  /** Free text. Empty/whitespace matches everything. */
  query: string;
  /** Lifecycle statuses to show. Empty set means "no status filter". */
  statuses: ReadonlySet<string>;
  /** Show kits an author has hidden. Off by default -- that is the point. */
  includeHidden: boolean;
}

export const EMPTY_FILTER: CatalogueFilter = {
  query: '',
  statuses: new Set<string>(),
  includeHidden: false,
};

/** True when the filter would change nothing -- used to decide whether to show
 *  a "showing N of M" line, so an untouched catalogue stays quiet. */
export function isFilterActive(f: CatalogueFilter): boolean {
  return f.query.trim() !== '' || f.statuses.size > 0 || f.includeHidden;
}

/**
 * Does one kit survive the filter?
 *
 * Text matches against the LABEL and the ID, both case-insensitively. The id
 * matters because every server refusal names a kit by id (bd kztlr), so an
 * operator reading an error can paste that id straight in -- searching only the
 * label would fail exactly the person who most needs to find the kit.
 */
export function kitMatches(kit: FilterableKit, f: CatalogueFilter): boolean {
  if (kit.hidden === true && !f.includeHidden) return false;
  if (f.statuses.size > 0 && !f.statuses.has(kit.status)) return false;
  const q = f.query.trim().toLowerCase();
  if (!q) return true;
  const label = (kit.label ?? '').toLowerCase();
  return label.includes(q) || kit.id.toLowerCase().includes(q);
}

/** The kits a catalogue surface should render. */
export function filterKits<T extends FilterableKit>(
  kits: readonly T[], f: CatalogueFilter,
): T[] {
  return kits.filter((k) => kitMatches(k, f));
}

/**
 * How many kits the filter is holding back, for the "showing N of M" line.
 *
 * Counted rather than inferred from lengths at the call site: a surface that
 * forgets to subtract renders a confident wrong number, and this is the one
 * thing telling an operator their list is incomplete.
 */
export function hiddenByFilterCount(
  kits: readonly FilterableKit[], f: CatalogueFilter,
): number {
  return kits.length - kits.filter((k) => kitMatches(k, f)).length;
}
