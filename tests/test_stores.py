import threading
from storage.session_store import SessionStore
from storage.cache_store import CacheStore
from domain.models import DownloadItem


def test_clear_session_then_save_does_not_break(tmp_path):
    """Regression: clear_session used DROP TABLE, so a later save_session hit
    'no such table: downloads'. It must now truncate and keep working."""
    ss = SessionStore(db_file=tmp_path / "session.db")
    item = DownloadItem(id="u1", url="u1", title="t", output_dir=tmp_path)
    ss.save_session([item])
    assert len(ss.load_session()) == 1

    ss.clear_session()
    assert ss.load_session() == []

    ss.save_session([item])                 # must not raise
    assert len(ss.load_session()) == 1


def test_cache_store_thread_safe(tmp_path):
    """Regression: concurrent set() while _save iterated raised
    'dictionary changed size during iteration'."""
    cache = CacheStore(cache_file=tmp_path / "cache.json")

    def worker(n):
        for i in range(300):
            cache.set(f"{n}-{i}", i)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert cache.get("0-0") == 0
    assert cache.get("3-299") == 299
