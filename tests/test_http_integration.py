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
        requests_seen.append((self.path, dict(self.headers), body))
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
def server():
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
