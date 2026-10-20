import importlib

import pytest


@pytest.mark.parametrize("package", ["api", "core", "tools", "ingestion"])
def test_top_level_packages_import(package: str) -> None:
    assert importlib.import_module(package) is not None
