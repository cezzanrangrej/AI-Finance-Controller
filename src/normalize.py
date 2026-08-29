#!/usr/bin/env python3
"""
CLI entrypoint for AI Finance Controller Financial-Data Normalizer.

Transforms third-party/heterogeneous CSV files into canonical 4-source reconciliation datasets.

Usage Examples:
    # 1. Normalize an IBM AML synthetic public dataset
    python src/normalize.py --source ibm_aml --input data/raw_ibm_transactions.csv --output data/normalized/ibm_aml_run1

    # 2. Normalize an arbitrary CSV using explicit column mappings in a JSON file
    python src/normalize.py --source generic_csv --input data/custom_feed.csv --mapping mapping.json --output data/normalized/custom_run1

    # 3. View list of available normalizers and detailed help
    python src/normalize.py --help
"""

import argparse
import json
import os
import sys

# Ensure project root is on sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.abspath(os.path.join(_current_dir, ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.normalizer import get_normalizer, list_normalizers


def main():
    parser = argparse.ArgumentParser(
        description="AI Finance Controller - Financial Data Normalizer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Normalize IBM AML CSV:
    python src/normalize.py --source ibm_aml --input data/ibm_sample.csv --output data/normalized/ibm_aml_01

  Normalize Generic CSV with explicit JSON mapping:
    python src/normalize.py --source generic_csv --input data/raw.csv --mapping mapping.json --output data/normalized/custom_01

Available Normalizers:
  - ibm_aml: IBM AML / AMLSim public synthetic transaction dataset
  - generic_csv: Generic CSV with explicit user-provided column mapping
        """,
    )

    parser.add_argument(
        "--source",
        "-s",
        type=str,
        required=True,
        help="Normalizer source type (e.g. 'ibm_aml', 'generic_csv')",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to input raw CSV file",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        required=True,
        help="Directory to save normalized CSVs and manifest.json",
    )
    parser.add_argument(
        "--mapping",
        "-m",
        type=str,
        default=None,
        help="Path to JSON file with column mappings (required for generic_csv)",
    )
    parser.add_argument(
        "--no-derive",
        action="store_true",
        help="Do not derive ledger/bank/adjustment test data for 4-source reconciliation",
    )

    args = parser.parse_args()

    # Verify input exists
    if not os.path.exists(args.input):
        print(f"Error: Input file '{args.input}' not found.", file=sys.stderr)
        sys.exit(1)

    mapping_dict = None
    if args.mapping:
        if not os.path.exists(args.mapping):
            print(f"Error: Mapping file '{args.mapping}' not found.", file=sys.stderr)
            sys.exit(1)
        try:
            with open(args.mapping, "r", encoding="utf-8") as f:
                mapping_dict = json.load(f)
        except Exception as e:
            print(f"Error reading mapping JSON: {str(e)}", file=sys.stderr)
            sys.exit(1)

    try:
        normalizer = get_normalizer(args.source)
    except ValueError as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

    print(f"Normalizing '{args.input}' using '{args.source}' normalizer...")
    try:
        normalized_dataset = normalizer.normalize(
            source_input=args.input,
            filename=os.path.basename(args.input),
            derive_reconciliation_sources=not args.no_derive,
            mapping=mapping_dict,
        )
    except Exception as e:
        print(f"Normalization failed: {str(e)}", file=sys.stderr)
        sys.exit(1)

    if normalized_dataset.errors:
        print(f"\nNormalization completed with {len(normalized_dataset.errors)} error(s):", file=sys.stderr)
        for err in normalized_dataset.errors[:10]:
            print(f"  - {err}", file=sys.stderr)
        if len(normalized_dataset.errors) > 10:
            print(f"  ... and {len(normalized_dataset.errors) - 10} more errors.", file=sys.stderr)
        if len(normalized_dataset.payments) == 0:
            print("No valid records were normalized.", file=sys.stderr)
            sys.exit(1)

    # Export
    exported = normalizer.export_to_directory(normalized_dataset, args.output)
    print(f"\nSuccessfully normalized {len(normalized_dataset.payments)} records.")
    print(f"Exported files to '{args.output}':")
    for key, path in exported.items():
        print(f"  - {key}: {path}")


if __name__ == "__main__":
    main()
