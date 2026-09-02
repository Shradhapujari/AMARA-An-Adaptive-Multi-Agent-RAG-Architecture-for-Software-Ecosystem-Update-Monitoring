"""
The store is shared between Streamlit's per-rerun threads, so it must survive
concurrent use of one connection.

`sqlite3.connect(..., check_same_thread=False)` only silences sqlite's thread
check. It does not serialise anything. Streamlit runs every script execution on
its own thread and `st.cache_resource` hands each session the *same* Store, so
two overlapping reruns share one connection: interleaved `with self.conn:`
blocks raise "cannot start a transaction within a transaction", and interleaved
cursor use raises "Recursive use of cursors not allowed". Either escapes before
the page draws, which is a blank app rather than a visible error.

These tests hammer one Store from several threads. They fail without the
RLock -- `_synchronized` is the thing under test, not decoration.
"""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store import Store, open_store  # noqa: E402

THREADS = 8
PER_THREAD = 25


def _rows(tag, n):
    return [{"title": f"{tag} release {i}", "product": "linux",
             "version": f"7.1.{i}", "date": "20260719",
             "url": f"https://example.invalid/{tag}/{i}", "notes": "n"}
            for i in range(n)]


def _run_concurrently(fn, threads=THREADS):
    errors = []

    def worker(idx):
        try:
            fn(idx)
        except Exception as exc:            # noqa: BLE001 - the point of the test
            errors.append(exc)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return errors


@pytest.fixture
def store(tmp_path):
    s = open_store(str(tmp_path / "s.db"))
    yield s
    s.close()


def test_concurrent_writes_do_not_raise(store):
    errors = _run_concurrently(
        lambda i: store.record_documents("release", _rows(f"t{i}", PER_THREAD)))
    assert not errors, f"concurrent writes raised: {errors[:3]}"


def test_concurrent_reads_and_writes_do_not_raise(store):
    store.record_documents("release", _rows("seed", 10))

    def mixed(i):
        for _ in range(PER_THREAD):
            if i % 2:
                store.record_documents("release", _rows(f"w{i}", 3))
            else:
                store.search("linux", pool="release", limit=5)

    assert not _run_concurrently(mixed)


def test_every_concurrent_write_is_persisted(store):
    # Serialising must not silently drop work.
    _run_concurrently(
        lambda i: store.record_documents("release", _rows(f"keep{i}", PER_THREAD)))
    rows = store.conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
    assert rows["n"] == THREADS * PER_THREAD


def test_nested_call_does_not_deadlock(store):
    # record_run calls record_documents; a non-reentrant lock would hang here.
    # A deadlock shows up as a timeout, so the join is bounded.
    done = threading.Event()

    def go():
        store.record_run({"original_query": "q", "releases": _rows("r", 2),
                          "community": [], "cve": []}, answer="a")
        done.set()

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout=10)
    assert done.is_set(), "record_run deadlocked on the store lock"


def test_lock_is_reentrant():
    assert isinstance(Store(None, False)._lock, type(threading.RLock()))
