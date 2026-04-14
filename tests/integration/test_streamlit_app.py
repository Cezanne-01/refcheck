import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")
    monkeypatch.setenv("UNPAYWALL_EMAIL", "test@example.com")


def test_app_loads_without_error():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert not at.exception


def test_app_shows_title():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert any("refcheck" in str(t.value) for t in at.title)


def test_app_shows_upload_widget():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # file_uploader가 한 개 이상 있어야 함
    uploaders = getattr(at, "file_uploader", None) or []
    assert len(uploaders) >= 1


def test_app_shows_verification_level_selector():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    # selectbox가 최소 1개 있어야 함 (verification level)
    assert len(at.selectbox) >= 1
