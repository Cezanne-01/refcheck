import pytest
from streamlit.testing.v1 import AppTest


def test_app_loads_without_error():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert not at.exception


def test_app_shows_title():
    at = AppTest.from_file("src/refcheck/ui/app.py", default_timeout=10)
    at.run()
    assert any("refcheck" in str(t.value) for t in at.title)
