from marceddy.dedup import SeenStore


def test_seen_store_roundtrip(cfg):
    s = SeenStore.load(cfg)
    assert not s.contains("fixture-abc")
    s.add("fixture-abc")
    s.add("fixture-def")
    s.save()

    s2 = SeenStore.load(cfg)
    assert s2.contains("fixture-abc")
    assert s2.contains("fixture-def")
    assert not s2.contains("fixture-zzz")
