#!/usr/bin/env python3
"""
Data cleaning pipeline for medical_records.csv.

Input:  data/raw/medical_records.csv (2,124 raw dental outpatient records)
Output: data/cases/case_XXX.json    (standardized structured cases)
        data/processed/cleaning_report.json (statistics)

Processing steps:
  1. Read CSV
  2. Group by patient (Filename) — merge multi-row visits
  3. Privacy cleaning — age bucketing, remove identifiers
  4. Completeness filtering — keep only records with core fields
  5. Standardize to JSON schema per architecture doc §3.3
  6. Generate cleaning report
"""

import csv
import json
import os
import re
from collections import defaultdict
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "medical_records.csv"
CASES_DIR = PROJECT_ROOT / "data" / "cases"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_PATH = PROCESSED_DIR / "cleaning_report.json"

CASES_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ─── Age bucketing ────────────────────────────────────────────────────
def bucket_age(age_str: str) -> str:
    """Convert numeric age to bucketed range for privacy."""
    if not age_str or not age_str.strip():
        return "未知"
    try:
        age = int(float(age_str))
    except ValueError:
        return "未知"
    if age <= 12:
        return "0–12"
    elif age <= 20:
        return "13–20"
    elif age <= 40:
        return "21–40"
    elif age <= 60:
        return "41–60"
    else:
        return "60+"


# ─── Field mapping ────────────────────────────────────────────────────
def extract_tier1(row: dict) -> dict:
    """Chief complaint — Tier 1 info (disclosed on first contact)."""
    return {
        "gender": "男" if row.get("Sex", "").strip().lower() == "male" else "女",
        "age_range": bucket_age(row.get("Age", "")),
        "chief_complaint": (row.get("Main appeal") or row.get("Subsequent") or "").strip(),
    }


def extract_tier2(row: dict) -> dict:
    """Present illness + Past history — Tier 2 (disclosed on inquiry)."""
    return {
        "present_illness": (row.get("Present medical history") or "").strip(),
        "past_history": (row.get("Past medical history") or "").strip(),
    }


def extract_tier3(row: dict) -> dict:
    """Oral examination — Tier 3 (disclosed on explicit exam inquiry)."""
    return {
        "oral_examination": (row.get("Oral Check") or "").strip(),
    }


def extract_tier4(row: dict) -> dict:
    """Diagnosis + Treatment plan — Tier 4 (permanently hidden)."""
    return {
        "diagnosis": (row.get("Diagnosis") or "").strip(),
        "treatment_plan": (row.get("Treatment plan") or "").strip(),
    }


# ─── Main pipeline ────────────────────────────────────────────────────
def main() -> None:
    print(f"Reading: {RAW_CSV}")

    # 1. Read CSV (tab-delimited, BOM-stripped)
    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        # Detect tab vs comma delimiter from header line
        first_line = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        print(f"  Detected delimiter: {'TAB' if delimiter == chr(9) else 'COMMA'}")
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)

    total_raw = len(rows)
    print(f"  Raw records: {total_raw}")

    # 2. Group by patient (Filename)
    patient_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        fid = row.get("Filename", "").strip()
        patient_groups[fid].append(row)

    print(f"  Unique patients: {len(patient_groups)}")

    # 3. Merge visits — take first-visit row as primary, merge treatment notes
    merged_cases: list[dict] = []
    stats = {
        "raw_records": total_raw,
        "unique_patients": len(patient_groups),
        "missing_values": defaultdict(int),
        "field_presence": defaultdict(lambda: {"present": 0, "missing": 0}),
    }

    # Field list for completeness check
    core_fields = [
        "Main appeal", "Present medical history", "Past medical history",
        "Oral Check", "Diagnosis", "Treatment plan",
    ]

    for fid, visits in patient_groups.items():
        # First row with a main appeal is the "index visit"
        primary = next((v for v in visits if v.get("Main appeal", "").strip()), visits[0])

        # Track field presence
        for field in core_fields:
            val = (primary.get(field) or "").strip()
            if val:
                stats["field_presence"][field]["present"] += 1
            else:
                stats["field_presence"][field]["missing"] += 1

        # Completeness filter: need at least Diagnosis + Oral Check
        diag = (primary.get("Diagnosis") or "").strip()
        oral = (primary.get("Oral Check") or "").strip()
        if not diag or not oral:
            stats["missing_values"]["filtered_incomplete"] += 1
            continue

        # Build standardized case
        case = {
            "basic_info": extract_tier1(primary),
            "chief_complaint": extract_tier1(primary),
            "present_illness": extract_tier2(primary),
            "past_history": extract_tier2(primary),
            "oral_examination": extract_tier3(primary),
            "auxiliary_examination": {"xray": "", "cbct": ""},
            "diagnosis": {"primary": diag, "secondary": [], "icd_code": ""},
            "treatment_plan": {
                "emergency": "",
                "definitive": (primary.get("Treatment plan") or "").strip(),
                "restoration": "",
                "notes": (primary.get("Doctor advices") or "").strip(),
            },
            "source_handle": (primary.get("Handle") or "").strip(),
            "visit_type": "首诊" if primary.get("Main appeal", "").strip() else "复诊",
        }
        merged_cases.append(case)

    stats["after_filter"] = len(merged_cases)
    stats["filtered_out"] = stats["unique_patients"] - len(merged_cases)
    filter_rate = stats["filtered_out"] / stats["unique_patients"] * 100 if stats["unique_patients"] else 0
    stats["filter_rate_pct"] = round(filter_rate, 1)

    # 4. Write case JSON files
    for i, case in enumerate(merged_cases, start=1):
        case_path = CASES_DIR / f"case_{i:03d}.json"
        with open(case_path, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)

    print(f"  Written {len(merged_cases)} cases to {CASES_DIR}/")

    # 5. Write cleaning report
    # Convert defaultdict to plain dict for JSON serialization
    report = {
        **stats,
        "field_presence": dict(stats["field_presence"]),
        "missing_values": dict(stats["missing_values"]),
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Report written to {REPORT_PATH}")
    print(f"\nSummary:")
    print(f"  Raw records:       {total_raw}")
    print(f"  Unique patients:   {report['unique_patients']}")
    print(f"  After filtering:   {report['after_filter']}")
    print(f"  Filtered out:      {report['filtered_out']} ({report['filter_rate_pct']}%)")
    print(f"\nField presence (in qualifying cases):")
    for field, counts in stats["field_presence"].items():
        pct = counts["present"] / report["unique_patients"] * 100 if report["unique_patients"] else 0
        print(f"  {field:30s}: {counts['present']:4d} present ({pct:.1f}%), {counts['missing']:4d} missing")


if __name__ == "__main__":
    main()
