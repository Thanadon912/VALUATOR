from pathlib import Path

from app.core.runtime_paths import BACKEND_ROOT, runtime_cache_path


def test_runtime_cache_path_uses_project_cache_locally(monkeypatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    assert runtime_cache_path("quotes", "cache.json") == (
        BACKEND_ROOT / ".cache" / "quotes" / "cache.json"
    )


def test_runtime_cache_path_uses_tmp_on_vercel(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    assert runtime_cache_path("quotes", "cache.json") == Path(
        "/tmp/valuator/quotes/cache.json"
    )
