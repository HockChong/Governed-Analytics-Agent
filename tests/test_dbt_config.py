import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt"
ENV_VAR_CALL = re.compile(r"env_var\(\s*['\"]([A-Z0-9_]+)['\"]")
KEY_FILE_FIELDS = {"keyfile", "keyfile_json", "private_key", "private_key_id"}


# Any: yaml.safe_load returns untyped nested data; the tests only index known keys.
def _dev_output() -> dict[str, Any]:
    profiles = yaml.safe_load((DBT_DIR / "profiles.yml").read_text(encoding="utf-8"))
    output: dict[str, Any] = profiles["governed_analytics"]["outputs"]["dev"]
    return output


def _documented_env_vars() -> set[str]:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    return {line.split("=", 1)[0] for line in lines if "=" in line and not line.startswith("#")}


def test_profile_uses_impersonation_not_key_files() -> None:
    output = _dev_output()
    assert output["method"] == "oauth"
    assert "DBT_IMPERSONATE_SA" in output["impersonate_service_account"]
    assert not KEY_FILE_FIELDS & output.keys()


def test_profile_caps_bytes_billed() -> None:
    assert 0 < _dev_output()["maximum_bytes_billed"] <= 2_000_000_000


def test_every_dbt_env_var_is_documented() -> None:
    used = {
        name
        for path in DBT_DIR.rglob("*.yml")
        if "target" not in path.parts
        for name in ENV_VAR_CALL.findall(path.read_text(encoding="utf-8"))
    }
    assert used, "expected dbt config to read env vars"
    assert used <= _documented_env_vars()
