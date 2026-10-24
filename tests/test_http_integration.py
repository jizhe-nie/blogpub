"""Real HTTP round trips against a local fake server (no mocks of `requests`)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from blogpub import cli

REPLY = {
    "slug": "http-test-post",
    "categories": {"en": ["Dev Notes"]},
    "tags": {"en": ["http", "test"]},
    "posts": {"en": {"title": "HTTP test", "body": "An intro paragraph that is long enough.\n\n## Section\n\nSome body text.\n\n![shot](IMG:01-shot-1.png)"}},
}
requests_seen = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        # header names are case-insensitive, and a proxy may change their case, so compare in lower case
        requests_seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.endswith("/chat/completions"):
            out = {"choices": [{"message": {"content": "```json\n" + json.dumps(REPLY) + "\n```"}}]}
        elif self.path.endswith("/v1/messages"):
            out = {"content": [{"type": "text", "text": json.dumps(REPLY)}]}
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def server(monkeypatch):
    # Never let the developer's own proxy settings influence a test that talks to 127.0.0.1.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    requests_seen.clear()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


NOTES = "Notes: I set up the blog and fixed the node_modules problem with git rm --cached.\nshot is the result."


def test_openai_compatible_endpoint_end_to_end(server, blog, png, tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-1")
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    code = cli.main(["new", str(notes), "-i", str(png), "--blog", str(blog), "--provider", "custom",
                     "--base-url", server, "--model", "any-model", "--languages", "en", "-y"])
    assert code == 0
    path, headers, body = requests_seen[0]
    assert path == "/chat/completions"
    assert headers["authorization"] == "Bearer test-key-1"
    assert body["model"] == "any-model" and body["messages"][0]["role"] == "system"
    assert "<<<NOTES" in body["messages"][1]["content"] and "01-shot-1.png" in body["messages"][1]["content"]
    draft = (blog / "source" / "_drafts" / "http-test-post.md").read_text(encoding="utf-8")
    assert "(/images/posts/http-test-post/01-shot-1.png)" in draft
    assert (blog / "source" / "images" / "posts" / "http-test-post" / "01-shot-1.png").exists()


def test_anthropic_endpoint_with_vision_sends_the_image(server, blog, png, tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-2")
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    code = cli.main(["new", str(notes), "-i", str(png), "--blog", str(blog), "--provider", "anthropic",
                     "--base-url", server, "--languages", "en", "-y"])
    assert code == 0
    path, headers, body = requests_seen[0]
    assert path == "/v1/messages" and headers["x-api-key"] == "test-key-2"
    blocks = body["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/jpeg"
    assert blocks[-1]["type"] == "text"


def test_local_endpoints_bypass_a_misconfigured_proxy(server, blog, png, tmp_path, monkeypatch):
    """A proxy variable without NO_PROXY used to send even localhost traffic through the proxy."""
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")    # nothing listens here: any use of it fails
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_API_KEY", "k")
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    assert cli.main(["new", str(notes), "-i", str(png), "--blog", str(blog), "--provider", "custom",
                     "--base-url", server, "--model", "m", "--languages", "en", "-y"]) == 0
    assert requests_seen[0][1]["authorization"] == "Bearer k"


def test_proxy_policy_by_host():
    from blogpub.providers import _proxies_for
    assert _proxies_for("http://localhost:11434/v1/chat/completions") == {"http": None, "https": None}
    assert _proxies_for("http://127.0.0.1:8000/x") == {"http": None, "https": None}
    assert _proxies_for("https://api.deepseek.com/chat/completions") is None   # follows the environment
