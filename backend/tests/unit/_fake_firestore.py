"""A FAKE FIRESTORE with real transaction semantics, shared by every test
that drives backend/services/credit_ledger.py's transactional helper.

Extracted from test_credit_ledger.py (Epic 2 bead A2) when the mint route
(bead A3, backend/routes/link_routes.py:_reserve_mint) became a second
caller of the same transaction: two copies of a fake whose whole job is to
model buffer-and-retry semantics would drift, and a drifted copy would let
one caller's tests pass against semantics the other caller does not have.
ONE fake, both callers.

It models the two properties the real Firestore transaction has that a plain
dict does not: writes are BUFFERED until commit (so an aborted body leaves
nothing behind, which is what makes "nothing was committed" a real assertion
rather than a tautology), and a body can be RE-RUN on contention (so a test
can interleave two transactions and prove the loser re-reads). Deliberately a
fake and not a mock: a MagicMock would assert that calls happened rather than
that the money is right.

ASCII only.
"""




class _Snap:
    """A POINT-IN-TIME copy, like a real Firestore snapshot.

    The copy is load-bearing, not tidiness: holding a reference to the live
    store dict would let a snapshot taken BEFORE a competing commit silently
    observe that commit's values, and every "the stale read is the bug" test
    below would pass against a helper that reads outside its transaction.
    """

    def __init__(self, data):
        self._data = dict(data) if data is not None else None

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, path):
        self._store = store
        self._path = path
        self.id = path[-1]

    def collection(self, name):
        return _Collection(self._store, self._path + (name,))

    def get(self, transaction=None):
        if transaction is not None:
            # Record which docs a transaction read, and WHEN, so a test can
            # assert reads-before-writes and drive a contention retry.
            transaction.reads.append(self._path)
        return _Snap(self._store.docs.get(self._path))

    def set(self, data, merge=False):
        self._store.apply_set(self._path, data, merge)

    def update(self, data):
        # Firestore's update() REQUIRES the doc to exist and merges into it
        # -- modelled, not aliased to set(merge=True), because the mint
        # record's `opened` mirror (links_store.mark_opened) relies on
        # update's refusal to conjure a document that was never minted.
        if self._path not in self._store.docs:
            raise KeyError("no such document: {}".format(self._path))
        self._store.docs[self._path].update(dict(data))


class _Query:
    """Ordering, filtering and limiting are ONE query in Firestore, applied
    in that fixed order regardless of the builder call sequence -- so the
    fake models the RESULT (filter, sort, then slice), and a test pins
    which entries come back rather than which builder method was called
    first.

    `direction` is honoured (not just accepted) so a mutation that flips the
    sort is a red test rather than a TypeError that reddens everything.

    `where()` clauses (credit_ledger.py's query_period_entries -- the
    monthly top-up's idempotency query, bd polyglot-pdf-0euzk) are AND-ed
    equality filters only: every clause this fake's one caller builds is
    `field == value`, so that is the only operator modelled. A caller
    passing anything else gets NotImplementedError rather than a silent
    wrong answer.
    """

    def __init__(self, store, path, order_field=None, limit=None,
                 descending=False, clauses=()):
        self._store = store
        self._path = path
        self._order = order_field
        self._limit = limit
        self._descending = descending
        self._clauses = tuple(clauses)

    def where(self, *args, **kwargs):
        if "filter" in kwargs:
            ff = kwargs["filter"]
            field, op, value = ff.field_path, ff.op_string, ff.value
        else:
            field, op, value = args
        if op != "==":
            raise NotImplementedError(
                "fake _Query only models == filters, got {!r}".format(op))
        return _Query(self._store, self._path, self._order, self._limit,
                      self._descending, self._clauses + ((field, value),))

    def order_by(self, field, direction="ASCENDING"):
        return _Query(self._store, self._path, field, self._limit,
                      str(direction).upper().startswith("DESC"),
                      self._clauses)

    def limit(self, n):
        return _Query(self._store, self._path, self._order, n,
                      self._descending, self._clauses)

    def _matches(self, data):
        return all(data.get(field) == value for field, value in self._clauses)

    def _rows(self):
        rows = [
            (path, data) for path, data in self._store.docs.items()
            if path[:-1] == self._path and self._matches(data)
        ]
        if self._order:
            rows.sort(key=lambda kv: kv[1].get(self._order),
                      reverse=self._descending)
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def stream(self):
        return iter([_Snap(data) for _, data in self._rows()])

    def get(self, transaction=None):
        """The transactional read form (credit_ledger.py's
        query_period_entries passes `transaction=tx`, matching the real
        Admin SDK's Query.get(transaction=...) -- .stream() does NOT accept
        one). Records each matched doc's path on the transaction's `reads`
        list, exactly like _DocRef.get(transaction=tx) does, so a query
        read participates in the same reads-before-writes / retry-on-
        contention model a single-doc read already gets."""
        rows = self._rows()
        if transaction is not None:
            for path, _ in rows:
                transaction.reads.append(path)
        return [_Snap(data) for _, data in rows]


class _Collection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id=None):
        if doc_id is None:
            self._store.auto_id_counter += 1
            doc_id = "auto{}".format(self._store.auto_id_counter)
        return _DocRef(self._store, self._path + (doc_id,))

    def where(self, *args, **kwargs):
        return _Query(self._store, self._path).where(*args, **kwargs)

    def order_by(self, field):
        return _Query(self._store, self._path).order_by(field)

    def limit(self, n):
        return _Query(self._store, self._path).limit(n)

    def stream(self):
        return _Query(self._store, self._path).stream()


class _Transaction:
    """Buffers writes; the buffer is applied only on a clean commit.

    This is what makes "nothing was committed" a real assertion rather than
    a tautology: a body that raises leaves the buffer unapplied.
    """

    def __init__(self, store):
        self._store = store
        self._buffer = []
        self.reads = []
        self.writes = []

    def set(self, ref, data, merge=False):
        self.writes.append(ref._path)
        self._buffer.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._buffer:
            self._store.apply_set(path, data, merge)
        self._buffer = []

    def reset(self):
        """What the real client does before RE-RUNNING a contended body."""
        self._buffer = []
        self.reads = []
        self.writes = []


class _WriteBatch:
    """firestore.Client.batch() -- buffers set() calls, applies them all on
    commit() (bd polyglot-pdf-he3lt: backend/services/usage_rollups.py's
    record_link_minted uses a batch, not a transaction, for its
    reservation-independent rollup write).

    Deliberately NOT the same object as _Transaction: a batch has no
    reads-before-writes rule and no contention retry -- it is just
    "apply these set() calls together, or none of them" -- so this is a
    smaller sibling rather than an alias, mirroring the real Admin SDK's own
    separate WriteBatch/Transaction types.

    NOTE: like _Transaction, apply_set()'s Increment resolution is FLAT
    (top-level int fields only) -- it does not recursively merge a nested
    dict the way test_usage_rollups.py's own purpose-built fake does. That
    is fine for the flat counters this fake's callers assert on; a test
    needing the nested by_employee/by_kit/by_language shape belongs in
    test_usage_rollups.py's own fake, which models that precisely.
    """

    def __init__(self, store):
        self._store = store
        self._pending = []

    def set(self, ref, data, merge=False):
        self._pending.append((ref._path, dict(data), merge))

    def commit(self):
        for path, data, merge in self._pending:
            self._store.apply_set(path, data, merge)
        self._pending = []


class _FakeDb:
    def __init__(self, docs=None):
        # {(collection, doc_id, [subcollection, doc_id, ...]): {...}}
        self.docs = dict(docs or {})
        self.auto_id_counter = 0
        # Set by a test to run a callback between the transaction body's
        # reads and its commit -- the contention window.
        self.on_before_commit = None
        self.transactions = []

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        tx = _Transaction(self)
        self.transactions.append(tx)
        return tx

    def batch(self):
        return _WriteBatch(self)

    def apply_set(self, path, data, merge):
        resolved = {}
        existing = self.docs.get(path, {})
        for key, value in data.items():
            if isinstance(value, _Increment):
                base = existing.get(key)
                base = base if isinstance(base, int) and not isinstance(
                    base, bool) else 0
                resolved[key] = base + value.delta
            else:
                resolved[key] = value
        if merge and path in self.docs:
            self.docs[path].update(resolved)
        else:
            self.docs[path] = dict(resolved)

    # test helpers -------------------------------------------------------
    def firm(self, firm_id):
        return self.docs.get(("firms", firm_id))

    def ledger_rows(self, firm_id):
        rows = [
            data for path, data in self.docs.items()
            if path[:3] == ("firms", firm_id, "ledger")
        ]
        return sorted(rows, key=lambda r: (r["ts"], r["balance_after"]))

    def link_rows(self, collection="links"):
        """Every mint record in one links[_<channel>] collection.

        Keyed by collection NAME rather than hard-coding "links", so a test
        can assert that a staging-channel mint wrote links_staging and not
        the demo collection -- the channel-isolation half of bead A3.
        """
        return {
            path[1]: data for path, data in self.docs.items()
            if len(path) == 2 and path[0] == collection
        }


class _FakeTransactionalDecorator:
    """Stands in for firebase_admin.firestore.transactional.

    Runs the body, then commits. Models CONTENTION when the db carries an
    on_before_commit hook: the hook runs after the body's reads, and if it
    reports that the underlying doc moved, the body is reset and RE-RUN
    exactly as the real client re-runs a contended transaction. Without the
    re-run the race test would be pinning the fake, not the helper.
    """

    def __init__(self, max_attempts=5):
        self._max_attempts = max_attempts

    def __call__(self, fn):
        def wrapper(transaction):
            store = transaction._store
            for _ in range(self._max_attempts):
                fn(transaction)
                hook = store.on_before_commit
                if hook is not None:
                    store.on_before_commit = None
                    if hook(transaction) == "retry":
                        transaction.reset()
                        continue
                transaction.commit()
                return
            raise RuntimeError("transaction exceeded its retry budget")
        return wrapper


class _Increment:
    """firestore.Increment(n) -- a SENTINEL the real client resolves
    server-side, modelled here so a caller that uses it (the per-firm mint
    counter, backend/services/link_metering.py) actually increments instead
    of silently landing in its own fail-soft except branch. A test that let
    that happen would be asserting against a code path production never
    takes.
    """

    def __init__(self, delta):
        self.delta = delta


class _FakeFirestoreModule:
    transactional = _FakeTransactionalDecorator()
    Increment = _Increment
