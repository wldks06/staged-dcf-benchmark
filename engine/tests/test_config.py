"""config.py: .env loading, secret lookup and redaction.

The repo .env is never read here: REPO_ROOT points at a temp directory and the
cached "already loaded" flag is reset for every test.
"""

from __future__ import annotations

import os

import pytest

from dcfbench import config

SECRET_NAMES = [name for name in config.SECRETS if name != "SEC_USER_AGENT"]


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A clean slate: no secrets set, nothing cached, a temp repo root.

    load_env writes to os.environ directly, so monkeypatch alone would not undo it.
    The whole mapping is restored afterwards.
    """
    saved = dict(os.environ)
    for name in config.SECRETS:
        os.environ.pop(name, None)
    monkeypatch.setattr(config, "_loaded", False)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


def write_env(directory, text):
    path = directory / ".env"
    path.write_text(text, encoding="utf-8")
    return path


# --- load_env ----------------------------------------------------------------


def test_load_env_reads_key_value_lines(env):
    config.load_env(write_env(env, "DCFT_A=alpha\nDCFT_B = spaced out \nDCFT_C=a=b=c\n"))
    assert os.environ["DCFT_A"] == "alpha"
    assert os.environ["DCFT_B"] == "spaced out"
    # Only the first equals sign separates the name from the value.
    assert os.environ["DCFT_C"] == "a=b=c"


def test_load_env_strips_surrounding_quotes(env):
    config.load_env(write_env(env, 'DCFT_A="Jane Doe jane@example.com"\nDCFT_B=\'single\'\n'))
    assert os.environ["DCFT_A"] == "Jane Doe jane@example.com"
    assert os.environ["DCFT_B"] == "single"


def test_load_env_skips_comments_blanks_and_lines_without_equals(env):
    text = "# DCFT_A=commented\n\n   \n   # DCFT_B=indented comment\nnot a setting\nDCFT_C=kept\n"
    config.load_env(write_env(env, text))
    assert "DCFT_A" not in os.environ
    assert "DCFT_B" not in os.environ
    assert os.environ["DCFT_C"] == "kept"
    assert not any("not a setting" in name for name in os.environ)


def test_real_environment_wins_over_the_file(env):
    os.environ["DCFT_A"] = "from-shell"
    config.load_env(write_env(env, "DCFT_A=from-file\nDCFT_B=from-file\n"))
    assert os.environ["DCFT_A"] == "from-shell"
    assert os.environ["DCFT_B"] == "from-file"


def test_empty_values_are_ignored(env):
    config.load_env(write_env(env, 'DCFT_A=\nDCFT_B=""\nDCFT_C=   \nDCFT_D=\'\'\n'))
    for name in ("DCFT_A", "DCFT_B", "DCFT_C", "DCFT_D"):
        assert name not in os.environ


def test_load_env_without_a_path_reads_the_repo_env_only_once(env):
    write_env(env, "DCFT_A=first\n")
    config.load_env()
    assert os.environ["DCFT_A"] == "first"
    # The second call is a no-op: the variable removed here does not come back.
    del os.environ["DCFT_A"]
    config.load_env()
    assert "DCFT_A" not in os.environ


def test_load_env_with_an_explicit_path_reads_even_after_the_first_load(env):
    config.load_env()
    config.load_env(write_env(env, "DCFT_A=explicit\n"))
    assert os.environ["DCFT_A"] == "explicit"


def test_load_env_tolerates_a_missing_file(env):
    config.load_env(env / "absent.env")
    config.load_env()


# --- secret ------------------------------------------------------------------


def test_secret_returns_the_value_without_surrounding_whitespace(env):
    os.environ["FRED_API_KEY"] = "  abc123  "
    assert config.secret("FRED_API_KEY") == "abc123"


def test_secret_reads_the_env_file_on_first_use(env):
    write_env(env, "FRED_API_KEY=from-dotenv\n")
    assert config.secret("FRED_API_KEY") == "from-dotenv"


def test_secret_required_raises_with_a_helpful_message(env):
    with pytest.raises(RuntimeError) as caught:
        config.secret("FRED_API_KEY")
    message = str(caught.value)
    assert "FRED_API_KEY" in message
    assert str(env / ".env") in message
    assert ".env.example" in message


def test_secret_optional_returns_none_when_unset(env):
    assert config.secret("FRED_API_KEY", required=False) is None


def test_secret_treats_a_blank_value_as_unset(env):
    os.environ["FRED_API_KEY"] = "   "
    assert config.secret("FRED_API_KEY", required=False) is None
    with pytest.raises(RuntimeError):
        config.secret("FRED_API_KEY")


# --- redact ------------------------------------------------------------------


@pytest.mark.parametrize("param", ["api_key", "crtfc_key", "token", "API_KEY", "Token"])
def test_redact_removes_key_values_from_a_query_string(env, param):
    url = f"https://api.example.test/obs?series_id=DGS10&{param}=SECRET123&file_type=json"
    assert config.redact(url) == (
        f"https://api.example.test/obs?series_id=DGS10&{param}=REDACTED&file_type=json")


def test_redact_removes_several_keys_in_one_url(env):
    out = config.redact("https://x.test/a?api_key=SECRET123&crtfc_key=SECRET456&token=SECRET789")
    assert out == "https://x.test/a?api_key=REDACTED&crtfc_key=REDACTED&token=REDACTED"


def test_redact_stops_at_the_end_of_the_url_inside_a_message(env):
    message = "GET https://x.test/a?api_key=SECRET123 failed: HTTP 400"
    assert config.redact(message) == "GET https://x.test/a?api_key=REDACTED failed: HTTP 400"


@pytest.mark.parametrize("name", SECRET_NAMES)
def test_redact_removes_any_secret_value_present_in_the_environment(env, name):
    os.environ[name] = "s3cr3t-value-42"
    # A key in the URL path is invisible to the query-string pattern.
    out = config.redact("https://x.test/api/Search/s3cr3t-value-42/json and s3cr3t-value-42")
    assert out == "https://x.test/api/Search/REDACTED/json and REDACTED"


def test_redact_leaves_sec_user_agent_alone(env):
    os.environ["SEC_USER_AGENT"] = "Jane Doe jane@example.com"
    text = "User-Agent: Jane Doe jane@example.com"
    assert config.redact(text) == text


def test_redact_ignores_secret_values_too_short_to_be_keys(env):
    # Replacing a three-letter value would blank out ordinary words.
    os.environ["FRED_API_KEY"] = "abc"
    assert config.redact("abcdef and abc") == "abcdef and abc"


def test_redact_leaves_ordinary_text_alone(env):
    text = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
    assert config.redact(text) == text
