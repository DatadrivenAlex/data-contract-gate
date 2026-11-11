import argparse
import json
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from contractgate.engine import validate_csv
from contractgate.loader import load_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CSV against a local YAML contract")
    parser.add_argument("contract", type=Path)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    try:
        if args.contract.stat().st_size > 64000 or args.csv.stat().st_size > 4000000:
            raise ValueError("input file exceeds size limit")
        contract = load_contract(args.contract.read_text(encoding="utf-8"))
        report = validate_csv(args.csv.read_text(encoding="utf-8-sig"), contract)
    except (OSError, UnicodeError, ValueError, ValidationError, yaml.YAMLError) as error:
        print(f"Invalid input: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1
