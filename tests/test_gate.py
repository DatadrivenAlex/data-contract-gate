import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pydantic import ValidationError

from contractgate.api import app
from contractgate.engine import validate_csv
from contractgate.models import Contract


def contract(rule=None, **kwargs):
    return Contract(name="test", columns={"x": rule or {}}, **kwargs)


def codes(text, spec=None, **kwargs):
    return [e["code"] for e in validate_csv(text, spec or contract(), **kwargs)["errors"]]


@pytest.mark.parametrize(
    "kind,value",
    [
        ("integer", "10"),
        ("integer", "-1"),
        ("decimal", "10.25"),
        ("date", "2024-02-29"),
        ("string", "hello"),
    ],
)
def test_valid_types(kind, value):
    assert validate_csv(f"x\n{value}\n", contract({"type": kind}))["passed"]


@pytest.mark.parametrize(
    "kind,value",
    [
        ("integer", "1.1"),
        ("integer", "true"),
        ("decimal", "NaN"),
        ("decimal", "Infinity"),
        ("decimal", "bad"),
        ("date", "2026-02-30"),
        ("date", "20260101"),
    ],
)
def test_invalid_types(kind, value):
    assert codes(f"x\n{value}\n", contract({"type": kind})) == ["invalid_type"]


def test_unique_uses_typed_values():
    assert codes("x\n01\n1\n", contract({"type": "integer", "unique": True})) == ["duplicate_value"]


def test_decimal_bounds():
    spec = contract({"type": "decimal", "min": "0.10", "max": "0.30"})
    assert validate_csv("x\n0.10\n0.30\n", spec)["passed"]
    assert codes("x\n0.09\n0.31\n", spec) == ["below_min", "above_max"]


def test_required_nullable_empty_fields():
    assert codes("x,y\n,ok\n", contract(allow_extra_columns=True)) == ["null_not_allowed"]
    assert validate_csv('x\n""\n', contract({"nullable": True}))["passed"]


def test_missing_and_extra_columns():
    assert codes("y\nhello\n") == ["missing_column", "unexpected_column"]
    assert validate_csv("x,y\nok,extra\n", contract(allow_extra_columns=True))["passed"]


def test_duplicate_headers_fail_without_reading_data():
    assert codes("x,x\none,two\n") == ["duplicate_header", "too_few_rows"]


def test_field_counts():
    assert codes("x\none,two\n") == ["field_count"]
    assert codes("x,y\none\n", contract(allow_extra_columns=True)) == ["field_count"]


def test_bom_and_quoted_newlines():
    assert validate_csv('\ufeffx\n"hello\nworld"\n', contract())["passed"]


def test_malformed_csv():
    assert "malformed_csv" in codes('x\n"unclosed')


def test_allowed_and_pattern():
    assert codes("x\nGBP\n", contract({"allowed": ["EUR", "USD"]})) == ["not_allowed"]
    assert codes("x\nC-12\n", contract({"pattern": r"C-[0-9]{3}"})) == ["pattern_mismatch"]


def test_row_bounds():
    assert codes("x\n", contract(min_rows=1)) == ["too_few_rows"]
    assert codes("x\na\nb\n", contract(max_rows=1)) == ["too_many_rows"]
    assert validate_csv("x\n", contract(min_rows=0, max_rows=0))["passed"]


def test_missing_header():
    assert codes("") == ["missing_header", "too_few_rows"]


def test_bounded_details_but_total_count():
    report = validate_csv("x\nno\nno\nno\n", contract({"type": "integer"}), detail_limit=2)
    assert report["error_count"] == 3
    assert len(report["errors"]) == 2
    assert report["details_truncated"] is True
    assert report["errors"][0]["record"] == 2
    assert "no" not in json.dumps(report)


@pytest.mark.parametrize(
    "rule",
    [
        {"type": "other"},
        {"pattern": "["},
        {"min": 0},
        {"type": "integer", "min": 2, "max": 1},
        {"type": "decimal", "max": "NaN"},
        {"typo": True},
    ],
)
def test_invalid_contract_rule(rule):
    with pytest.raises(ValidationError):
        contract(rule)


def test_contract_bounds_and_names():
    with pytest.raises(ValidationError):
        contract(min_rows=10, max_rows=1)
    with pytest.raises(ValidationError):
        Contract(name="bad", columns={" ": {}})


def test_resource_limits():
    with pytest.raises(ValueError):
        validate_csv("x" * 1000001, contract())
    with pytest.raises(ValueError):
        validate_csv("x\na\n", contract(), detail_limit=0)


def test_examples():
    spec = Contract.model_validate(yaml.safe_load(Path("examples/orders.yml").read_text()))
    assert validate_csv(Path("examples/valid.csv").read_text(), spec)["passed"]
    assert validate_csv(Path("examples/invalid.csv").read_text(), spec)["error_count"] == 5


def test_api():
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    payload = {"contract": {"name": "x", "columns": {"x": {"type": "integer"}}}, "csv": "x\nno\n"}
    result = client.post("/validate", json=payload)
    assert result.status_code == 200 and result.json()["passed"] is False
    payload["contract"]["columns"]["x"]["type"] = "unsupported"
    assert client.post("/validate", json=payload).status_code == 422


def test_cli(tmp_path):
    cmd = [
        sys.executable,
        "-c",
        "from contractgate.cli import main; raise SystemExit(main())",
        "examples/orders.yml",
    ]
    result = subprocess.run(cmd + ["examples/valid.csv"], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["passed"]
    assert subprocess.run(cmd + ["examples/invalid.csv"], capture_output=True).returncode == 1
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"\xff")
    assert subprocess.run(cmd + [str(bad)], capture_output=True).returncode == 2


def test_duplicate_yaml_keys_and_unsafe_tags():
    from contractgate.loader import load_contract

    with pytest.raises(ValueError, match="duplicate YAML key"):
        load_contract("name: one\nname: two\ncolumns: {x: {}}")
    with pytest.raises(yaml.YAMLError):
        load_contract("!!python/object/apply:os.system [echo forbidden]")
    assert load_contract("name: ok\ncolumns: {x: {}}").name == "ok"


def test_nullable_unique_skips_nulls():
    assert validate_csv('x\n""\n""\n', contract({"nullable": True, "unique": True}))["passed"]


def test_string_uniqueness_is_case_sensitive():
    assert validate_csv("x\nA\na\n", contract({"unique": True}))["passed"]
