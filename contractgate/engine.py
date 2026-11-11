"""CSV validation: record numbers (header=1), typed constraints and bounded details."""

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from contractgate.models import Contract

MAX_TEXT = 1_000_000


def convert(value: str, kind: str):
    if kind == "string":
        return value
    if kind == "integer":
        if not re.fullmatch(r"[+-]?[0-9]+", value):
            raise ValueError("expected integer")
        return int(value)
    if kind == "decimal":
        try:
            parsed = Decimal(value)
        except InvalidOperation as error:
            raise ValueError("expected decimal") from error
        if not parsed.is_finite():
            raise ValueError("expected finite decimal")
        return parsed
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("expected YYYY-MM-DD date")
    return date.fromisoformat(value)


def validate_csv(text: str, contract: Contract, detail_limit: int = 100) -> dict:
    if len(text) > MAX_TEXT:
        raise ValueError("CSV exceeds 1,000,000 characters")
    if not 1 <= detail_limit <= 1000:
        raise ValueError("detail_limit must be 1..1000")
    errors = []
    error_count = 0
    rows_checked = 0

    def fail(code, row=None, column=None):
        nonlocal error_count
        error_count += 1
        if len(errors) < detail_limit:
            errors.append({"code": code, "record": row, "column": column})

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    seen = {name: set() for name, rule in contract.columns.items() if rule.unique}
    try:
        headers = next(reader, None)
        if not headers:
            fail("missing_header", 1)
        else:
            if headers[0].startswith("\ufeff"):
                headers[0] = headers[0].removeprefix("\ufeff")
            if len(headers) != len(set(headers)):
                fail("duplicate_header", 1)
            else:
                for name in contract.columns:
                    if name not in headers:
                        fail("missing_column", 1, name)
                if not contract.allow_extra_columns:
                    for name in headers:
                        if name not in contract.columns:
                            fail("unexpected_column", 1, name)
                positions = {
                    name: headers.index(name) for name in contract.columns if name in headers
                }
                for number, values in enumerate(reader, start=2):
                    rows_checked += 1
                    if rows_checked > 100000:
                        fail("hard_row_limit", number)
                        break
                    if len(values) != len(headers):
                        fail("field_count", number)
                        continue
                    for name, index in positions.items():
                        rule = contract.columns[name]
                        raw = values[index]
                        if raw == "":
                            if not rule.nullable:
                                fail("null_not_allowed", number, name)
                            continue
                        try:
                            parsed = convert(raw, rule.type)
                        except (ValueError, OverflowError):
                            fail("invalid_type", number, name)
                            continue
                        if rule.unique:
                            if parsed in seen[name]:
                                fail("duplicate_value", number, name)
                            seen[name].add(parsed)
                        if rule.min is not None and parsed < rule.min:
                            fail("below_min", number, name)
                        if rule.max is not None and parsed > rule.max:
                            fail("above_max", number, name)
                        if rule.allowed is not None and raw not in rule.allowed:
                            fail("not_allowed", number, name)
                        if rule.pattern is not None and re.fullmatch(rule.pattern, raw) is None:
                            fail("pattern_mismatch", number, name)
    except csv.Error:
        fail("malformed_csv", rows_checked + 2)
    if rows_checked < contract.min_rows:
        fail("too_few_rows")
    if rows_checked > contract.max_rows:
        fail("too_many_rows")
    return {
        "contract": contract.name,
        "passed": error_count == 0,
        "rows_checked": rows_checked,
        "error_count": error_count,
        "errors": errors,
        "details_truncated": error_count > len(errors),
    }
