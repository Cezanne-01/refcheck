from refcheck.fetch.cache import DiskCache


def test_set_and_get(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("key1", {"a": 1})
    assert cache.get("key1") == {"a": 1}


def test_missing_returns_none(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.get("missing") is None


def test_keys_are_hashed_path_safe(tmp_path):
    cache = DiskCache(tmp_path)
    weird_key = "10.1016/some/slash?and&stuff"
    cache.set(weird_key, {"ok": True})
    assert cache.get(weird_key) == {"ok": True}


def test_survives_across_instances(tmp_path):
    c1 = DiskCache(tmp_path)
    c1.set("persist", {"v": 42})
    c2 = DiskCache(tmp_path)
    assert c2.get("persist") == {"v": 42}
