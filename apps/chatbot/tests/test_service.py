import importlib.util
from pathlib import Path

SERVICE = Path(__file__).resolve().parents[1] / "service.py"
spec = importlib.util.spec_from_file_location("chatbot_service", SERVICE)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def test_clean_messages_filters_and_ends_with_user():
    raw = [
        {"role": "system", "content": "ignored"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "  hello  "},
        {"role": "assistant", "content": "trailing"},
    ]
    out = service.clean_messages(raw)
    assert out == [
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "hello"},
    ]


def test_clean_messages_truncates_long_content():
    out = service.clean_messages([{"role": "user", "content": "x" * 5000}])
    assert len(out[0]["content"]) == service.MAX_CHARS


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(service, "RATE_LIMIT", 2)
    monkeypatch.setattr(service, "_buckets", {})
    assert service.rate_ok("1.2.3.4") is True
    assert service.rate_ok("1.2.3.4") is True
    assert service.rate_ok("1.2.3.4") is False
    assert service.rate_ok("5.6.7.8") is True


def test_daily_limit(monkeypatch, tmp_path):
    usage = tmp_path / "usage.json"
    monkeypatch.setattr(service, "USAGE_FILE", str(usage))
    monkeypatch.setattr(service, "DAILY_LIMIT", 2)
    assert service.daily_ok() is True
    assert service.daily_ok() is True
    assert service.daily_ok() is False
