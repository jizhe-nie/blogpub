import pytest

from blogpub import safety
from blogpub.config import ConfigError, load_config


def test_defaults_and_relative_blog_dir(tmp_path):
    (tmp_path / "blogpub.yml").write_text("blog_dir: ../site\nlanguages: [en]\n", encoding="utf-8")
    cfg = load_config(cwd=tmp_path)
    assert cfg["languages"] == ["en"]
    assert cfg["blog_dir"] == str((tmp_path / ".." / "site").resolve())
    assert cfg["provider"] == "openai"


def test_config_rejects_api_keys(tmp_path):
    (tmp_path / "blogpub.yml").write_text("provider: openai\napi_key: sk-abc\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="environment variable"):
        load_config(cwd=tmp_path)


def test_config_rejects_bad_languages(tmp_path):
    (tmp_path / "blogpub.yml").write_text("languages: [zh, zh]\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(cwd=tmp_path)


def test_scan_finds_secrets_and_masks_them():
    key = "sk-proj-" + "a1B2c3D4" * 4
    text = f"export OPENAI_API_KEY={key}\nssh root@10.1.2.3\nmail me: me@gmail.com\nphone 13812345678"
    found = safety.scan(text)
    kinds = {f.kind for f in found}
    assert {"API key (sk-...)", "IPv4 address", "email address", "mainland China mobile number", "ssh target (user@host)"} <= kinds
    assert safety.worst(found) == safety.BLOCK
    assert all(key not in str(f) for f in found)  # never echo the full secret


def test_scan_ignores_documentation_values():
    text = "see 127.0.0.1, 203.0.113.7 and someone@example.com; use <your-api-key>"
    assert safety.scan(text) == []


def test_scan_private_key_and_home_path():
    header = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"  # built at runtime so this file holds no key-like literal
    found = safety.scan(header + "\ncd /Users/alice/project")
    assert {f.kind for f in found} == {"private key", "home directory path"}


def test_example_config_file_matches_the_one_blogpub_init_writes():
    from pathlib import Path
    from blogpub.cli import EXAMPLE_CONFIG
    assert (Path(__file__).parent.parent / "blogpub.example.yml").read_text(encoding="utf-8") == EXAMPLE_CONFIG
    import yaml
    from blogpub.config import DEFAULTS
    assert set(yaml.safe_load(EXAMPLE_CONFIG)) <= set(DEFAULTS)  # every documented key really exists


def test_config_is_found_from_a_subfolder(tmp_path):
    (tmp_path / "blogpub.yml").write_text("languages: [en]\n", encoding="utf-8")
    sub = tmp_path / "source" / "_posts"
    sub.mkdir(parents=True)
    cfg = load_config(cwd=sub)
    assert cfg["languages"] == ["en"]
    assert cfg["blog_dir"] == str(tmp_path.resolve())   # blog_dir '.' means the folder holding the config
