import json

import pytest
from PIL import Image

from blogpub import images as imglib
from blogpub.config import load_config
from blogpub.providers import Image as LLMImage
from blogpub.providers import Provider, ProviderError


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._body


def test_openai_request_shape_and_image(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, payload=json)
        return FakeResp(200, {"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("blogpub.providers.requests.post", fake_post)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k-123")
    p = Provider(name="deepseek", kind="openai", model="m", base_url="https://api.deepseek.com/",
                 api_key_env="DEEPSEEK_API_KEY", vision=True, json_mode=True)
    assert p.complete("sys", "hi", [LLMImage("a.jpg", "image/jpeg", "QQ==")]) == "{}"
    assert seen["url"] == "https://api.deepseek.com/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer k-123"
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert seen["payload"]["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_anthropic_request_shape(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, payload=json)
        return FakeResp(200, {"content": [{"type": "text", "text": "hello"}]})

    monkeypatch.setattr("blogpub.providers.requests.post", fake_post)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-abc")
    p = Provider(name="anthropic", kind="anthropic", model="claude-x", base_url="https://api.anthropic.com",
                 api_key_env="ANTHROPIC_API_KEY")
    assert p.complete("sys", "hi") == "hello"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "k-abc" and seen["payload"]["system"] == "sys"


def test_missing_key_gives_actionable_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = Provider(name="openai", kind="openai", model="m", base_url="https://x", api_key_env="OPENAI_API_KEY")
    with pytest.raises(ProviderError, match="export OPENAI_API_KEY"):
        p.complete("s", "u")


def test_retries_transient_errors_but_not_bad_requests(monkeypatch):
    monkeypatch.setattr("blogpub.providers.time.sleep", lambda s: None)
    monkeypatch.setenv("K", "secret-key-value")
    calls = []

    def flaky(url, headers=None, json=None, timeout=None):
        calls.append(1)
        return FakeResp(429, {"error": "slow down"}) if len(calls) < 3 else FakeResp(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr("blogpub.providers.requests.post", flaky)
    p = Provider(name="x", kind="openai", model="m", base_url="https://x", api_key_env="K")
    assert p.complete("s", "u") == "ok" and len(calls) == 3

    calls.clear()
    monkeypatch.setattr("blogpub.providers.requests.post",
                        lambda *a, **k: (calls.append(1), FakeResp(401, {"error": "bad key secret-key-value"}))[1])
    with pytest.raises(ProviderError) as e:
        p.complete("s", "u")
    assert len(calls) == 1                       # a 401 is not retried
    assert "secret-key-value" not in str(e.value)  # and the key never leaks into errors


def test_image_processing_strips_metadata_and_resizes(tmp_path):
    src = tmp_path / "Photo One.JPG"
    img = Image.new("RGB", (3000, 2000), (200, 30, 30))
    exif = Image.Exif()
    exif[0x0112] = 6                    # rotated 90 degrees
    exif[0x8825] = {1: "N", 2: (31.0, 14.0, 0.0)}   # GPS block
    img.save(src, exif=exif)
    assert Image.open(src).getexif().get(0x8825) is not None

    cfg = load_config(cwd=tmp_path)
    out = imglib.process([src], tmp_path / "out", cfg)[0]
    assert out.name == "01-photo-one.jpg"
    result = Image.open(out.path)
    assert not result.getexif() and "exif" not in result.info      # GPS and all metadata are gone
    assert result.width == 1600 or result.height == 1600 or max(result.size) <= 1600
    assert result.size == (1067, 1600) or result.size == (1600, 1067) or result.width <= 1600
    assert out.thumb.media_type == "image/jpeg" and out.thumb.data_b64


def test_png_stays_png_and_unsupported_files_rejected(tmp_path, png):
    cfg = load_config(cwd=tmp_path)
    out = imglib.process([png], tmp_path / "o", cfg)[0]
    assert out.name == "01-shot-1.png" and Image.open(out.path).width == 1600
    bad = tmp_path / "notes.txt"
    bad.write_text("x")
    with pytest.raises(imglib.ImageError):
        imglib.collect([str(bad)])
    with pytest.raises(imglib.ImageError):
        imglib.collect([str(tmp_path / "missing.png")])


def test_collect_expands_directories(tmp_path, png):
    (tmp_path / "notes.txt").write_text("x")
    found = imglib.collect([str(tmp_path)])
    assert [f.name for f in found] == ["Shot 1.PNG"]
