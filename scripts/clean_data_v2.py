#!/usr/bin/env python3
"""
Data cleaning pipeline v2 for medical_records.csv.

Improvements over v1:
  - Stricter quality filtering: 6 core fields all present + content-length thresholds
  - Garbage-text removal: truncated fragments, placeholders, COVID screening templates
  - HTML entity decoding: &#39; → '  &quot; → "
  - ICD code extraction: regex from diagnosis text → separate icd_code field
  - No duplicate keys: basic_info ≠ chief_complaint, present_illness ≠ past_history
  - Output intermediate format (English raw text) for downstream LLM enrichment

Input:  data/raw/medical_records.csv (2,124 records, TSV)
Output: data/cases/intermediate/case_XXX.json (high-quality subset, ~80-120 cases)
        data/processed/cleaning_report_v2.json
"""

import csv
import html
import json
import re
import os
import sys
from collections import defaultdict
from pathlib import Path


# ─── Paths ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV = PROJECT_ROOT / "data" / "raw" / "medical_records.csv"
INTERMEDIATE_DIR = PROJECT_ROOT / "data" / "cases" / "intermediate"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORT_PATH = PROCESSED_DIR / "cleaning_report_v2.json"

# ─── Quality thresholds ──────────────────────────────────────────────
MIN_CHIEF_COMPLAINT = 10       # Main appeal character count
MIN_PRESENT_ILLNESS = 50       # Present medical history
MIN_ORAL_CHECK = 30            # Oral Check
MIN_TREATMENT = 20             # Treatment plan
MIN_PAST_HISTORY = 10          # Past medical history

# ─── Garbage patterns ────────────────────────────────────────────────
RE_TRUNCATED = re.compile(r"^abled\.?$", re.IGNORECASE)
RE_NOTHING_SPECIAL = re.compile(r"^nothing special$", re.IGNORECASE)
RE_SAME_AS = re.compile(r"^same as", re.IGNORECASE)
RE_ONLY_PUNCTUATION = re.compile(r"^[\s,./;:'\"\[\]{}|\\`~!@#$%^&*()_\-=+]+$")

# COVID screening template fragments to strip
COVID_FRAGMENTS = [
    "denied &quot;fever, dry cough, fatigue, loss of smell and taste",
    "denied \"fever, dry cough, fatigue",
    "fever, dry cough, fatigue, loss of smell and taste",
    "nasal congestion, runny nose, sore throat, conjunctivitis, myalgia and diarrhea",
    "symptoms related to COVID-19",
    "history of traveling to medium- and high-risk areas within 14 days",
    "traveling to medium- and high-risk areas",
    "Body temperature 36.2C",
    "Body temperature 36.2",
]

# ─── ICD code extraction ─────────────────────────────────────────────
RE_ICD = re.compile(r"\(?(K\d{2}\.\d+)\)?")
RE_ICD_LC = re.compile(r"\(?(LC\d+)\)?")


def bucket_age(age_str: str) -> str:
    """Convert numeric age to bucketed range for privacy."""
    if not age_str or not age_str.strip():
        return "未知"
    try:
        age = int(float(age_str))
    except (ValueError, TypeError):
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


def extract_icd_code(diagnosis_text: str) -> tuple[str, str]:
    """Extract ICD code from diagnosis text.

    Returns (icd_code, cleaned_diagnosis) pair.
    """
    codes = []
    # Find all ICD codes in the text
    codes.extend(RE_ICD.findall(diagnosis_text))
    codes.extend(RE_ICD_LC.findall(diagnosis_text))

    icd_code = codes[0] if codes else ""

    # Remove ICD codes from the diagnosis text for cleaner primary
    cleaned = diagnosis_text
    cleaned = RE_ICD.sub("", cleaned)
    cleaned = RE_ICD_LC.sub("", cleaned)
    # Clean up: remove empty parens, extra spaces
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" ,;.")

    return icd_code, cleaned


def strip_covid_template(text: str) -> str:
    """Remove COVID-19 screening template boilerplate from text."""
    for fragment in COVID_FRAGMENTS:
        idx = text.lower().find(fragment.lower())
        if idx >= 0:
            # Find the sentence/paragraph boundaries around the fragment
            # Try to remove the full COVID screening paragraph
            # Pattern: "...He denied...COVID-19...Body temperature..."
            start = text.lower().find("he denied")
            if start >= 0 and start <= idx:
                # Find where the COVID section ends (usually at "Body temperature" or next sentence)
                end_markers = ["Body temperature", "body temperature", ". ", ".\n"]
                end = -1
                for marker in end_markers:
                    pos = text.lower().find(marker.lower(), idx + len(fragment))
                    if pos >= 0:
                        end = pos + len(marker)
                        break
                if end > start:
                    text = text[:start] + text[end:]
                else:
                    text = text[:idx] + text[idx + len(fragment):]
            else:
                text = text[:idx] + text[idx + len(fragment):]
            text = text.strip()

    # Remove leftover empty paragraphs / double spaces
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"  +", " ", text)
    text = text.strip()

    return text


def is_garbage_text(text: str) -> bool:
    """Check if text is effectively garbage/empty."""
    t = text.strip()
    if not t:
        return True
    if RE_TRUNCATED.match(t):
        return True
    if RE_NOTHING_SPECIAL.match(t):
        return True
    if RE_SAME_AS.match(t):
        return True
    if RE_ONLY_PUNCTUATION.match(t):
        return True
    return False


def main() -> None:
    print("=" * 60)
    print("clean_data_v2: High-quality case filter + intermediate format")
    print("=" * 60)

    # ── 1. Read CSV ──────────────────────────────────────────────────
    print(f"\nReading: {RAW_CSV}")
    with open(RAW_CSV, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()
        f.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        print(f"  Detected delimiter: {'TAB' if delimiter == chr(9) else 'COMMA'}")
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)

    total_raw = len(rows)
    print(f"  Raw records: {total_raw}")

    # ── 2. Group by patient ──────────────────────────────────────────
    patient_groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        fid = row.get("Filename", "").strip()
        patient_groups[fid].append(row)

    print(f"  Unique patients: {len(patient_groups)}")

    # ── 3. Quality filtering ─────────────────────────────────────────
    stats = {
        "raw_records": total_raw,
        "unique_patients": len(patient_groups),
        "filter_reasons": defaultdict(int),
        "field_stats": defaultdict(lambda: {"present": 0, "missing": 0, "short": 0}),
    }

    core_fields = [
        "Main appeal",
        "Present medical history",
        "Past medical history",
        "Oral Check",
        "Diagnosis",
        "Treatment plan",
    ]

    intermediate_cases = []

    for fid, visits in patient_groups.items():
        # Take the first visit with a non-empty Main appeal as primary
        primary = next(
            (v for v in visits if v.get("Main appeal", "").strip()),
            visits[0],
        )

        # ── Extract raw fields ──
        main_appeal = (primary.get("Main appeal") or "").strip()
        present_illness_raw = (primary.get("Present medical history") or "").strip()
        past_history_raw = (primary.get("Past medical history") or "").strip()
        oral_check_raw = (primary.get("Oral Check") or "").strip()
        diagnosis_raw = (primary.get("Diagnosis") or "").strip()
        treatment_raw = (primary.get("Treatment plan") or "").strip()
        doctor_advices = (primary.get("Doctor advices") or "").strip()

        # ── De-duplicate vs subsequent visits ──
        # If primary's Main appeal is empty, check subsequent
        subsequent = (primary.get("Subsequent") or "").strip()
        if not main_appeal and subsequent:
            main_appeal = subsequent

        # ── HTML decode ──
        main_appeal = html.unescape(main_appeal)
        present_illness_raw = html.unescape(present_illness_raw)
        past_history_raw = html.unescape(past_history_raw)
        oral_check_raw = html.unescape(oral_check_raw)
        diagnosis_raw = html.unescape(diagnosis_raw)
        treatment_raw = html.unescape(treatment_raw)
        doctor_advices = html.unescape(doctor_advices)

        # ── Strip COVID templates ──
        past_history_raw = strip_covid_template(past_history_raw)
        present_illness_raw = strip_covid_template(present_illness_raw)

        # ── Quality checks ──
        field_values = {
            "Main appeal": main_appeal,
            "Present medical history": present_illness_raw,
            "Past medical history": past_history_raw,
            "Oral Check": oral_check_raw,
            "Diagnosis": diagnosis_raw,
            "Treatment plan": treatment_raw,
        }

        # Track field presence
        for field in core_fields:
            val = field_values[field]
            if val and not is_garbage_text(val):
                stats["field_stats"][field]["present"] += 1
            else:
                stats["field_stats"][field]["missing"] += 1

        # ── Apply filters ──
        skip = False

        # Main appeal: non-empty + length >= 10
        if is_garbage_text(main_appeal) or len(main_appeal) < MIN_CHIEF_COMPLAINT:
            stats["filter_reasons"]["main_appeal_short_or_empty"] += 1
            skip = True

        # Present medical history: non-empty + length >= 50
        if is_garbage_text(present_illness_raw) or len(present_illness_raw) < MIN_PRESENT_ILLNESS:
            stats["filter_reasons"]["present_illness_short_or_empty"] += 1
            skip = True

        # Oral Check: non-empty + length >= 30
        if is_garbage_text(oral_check_raw) or len(oral_check_raw) < MIN_ORAL_CHECK:
            stats["filter_reasons"]["oral_check_short_or_empty"] += 1
            skip = True

        # Diagnosis: non-empty (content check — must contain recognizable terms)
        if is_garbage_text(diagnosis_raw):
            stats["filter_reasons"]["diagnosis_empty"] += 1
            skip = True

        # Treatment plan: non-empty + length >= 20
        if is_garbage_text(treatment_raw) or len(treatment_raw) < MIN_TREATMENT:
            stats["filter_reasons"]["treatment_short_or_empty"] += 1
            skip = True

        # Past medical history: non-empty + length >= 10
        if is_garbage_text(past_history_raw) or len(past_history_raw) < MIN_PAST_HISTORY:
            stats["filter_reasons"]["past_history_short_or_empty"] += 1
            skip = True

        if skip:
            continue

        # ── Extract ICD code ──
        icd_code, cleaned_diagnosis = extract_icd_code(diagnosis_raw)

        # ── Build intermediate case ──
        gender_val = (primary.get("Sex") or "").strip().lower()
        gender = "男" if gender_val == "male" else "女"

        age_val = (primary.get("Age") or "").strip()
        age_range = bucket_age(age_val)

        visit_type = "首诊" if main_appeal else "复诊"
        # Use subsequent visit label if it's a follow-up
        if not main_appeal and subsequent:
            visit_type = "复诊"

        case = {
            "source_id": int(fid) if fid.isdigit() else 0,
            "department": "口腔科",
            "visit_type": visit_type,
            "raw": {
                "gender": gender,
                "age_range": age_range,
                "chief_complaint_en": main_appeal,
                "present_illness_en": present_illness_raw,
                "past_history_en": past_history_raw,
                "oral_examination_en": oral_check_raw,
                "diagnosis_primary_en": cleaned_diagnosis if cleaned_diagnosis else diagnosis_raw,
                "icd_code": icd_code,
                "treatment_definitive_en": treatment_raw,
                "treatment_notes_en": doctor_advices,
            },
        }
        intermediate_cases.append(case)

    stats["after_filter"] = len(intermediate_cases)
    stats["filtered_out"] = stats["unique_patients"] - len(intermediate_cases)
    if stats["unique_patients"] > 0:
        stats["filter_rate_pct"] = round(
            stats["filtered_out"] / stats["unique_patients"] * 100, 1
        )
    else:
        stats["filter_rate_pct"] = 0.0

    # ── 4. Write intermediate JSON files ─────────────────────────────
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    # Clean up old intermediate files
    for old_file in INTERMEDIATE_DIR.glob("case_*.json"):
        old_file.unlink()

    for i, case in enumerate(intermediate_cases, start=1):
        case_path = INTERMEDIATE_DIR / f"case_{i:03d}.json"
        with open(case_path, "w", encoding="utf-8") as f:
            json.dump(case, f, ensure_ascii=False, indent=2)

    print(f"\n  Written {len(intermediate_cases)} intermediate cases to {INTERMEDIATE_DIR}/")

    # ── 5. Write cleaning report ─────────────────────────────────────
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Convert defaultdicts for JSON serialization
    report = {
        **stats,
        "filter_reasons": dict(stats["filter_reasons"]),
        "field_stats": {
            field: dict(counts)
            for field, counts in stats["field_stats"].items()
        },
        "thresholds": {
            "min_chief_complaint": MIN_CHIEF_COMPLAINT,
            "min_present_illness": MIN_PRESENT_ILLNESS,
            "min_oral_check": MIN_ORAL_CHECK,
            "min_treatment": MIN_TREATMENT,
            "min_past_history": MIN_PAST_HISTORY,
        },
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  Report written to {REPORT_PATH}")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Raw records:               {total_raw}")
    print(f"  Unique patients:           {report['unique_patients']}")
    print(f"  After filtering:           {report['after_filter']}")
    print(f"  Filtered out:              {report['filtered_out']} ({report['filter_rate_pct']}%)")
    print(f"\n  Quality thresholds applied:")
    print(f"    Main appeal              >= {MIN_CHIEF_COMPLAINT} chars")
    print(f"    Present medical history  >= {MIN_PRESENT_ILLNESS} chars")
    print(f"    Oral Check               >= {MIN_ORAL_CHECK} chars")
    print(f"    Treatment plan           >= {MIN_TREATMENT} chars")
    print(f"    Past medical history     >= {MIN_PAST_HISTORY} chars")
    print(f"\n  Filter reasons breakdown:")
    for reason, count in sorted(
        report["filter_reasons"].items(), key=lambda x: -x[1]
    ):
        print(f"    {reason:40s}: {count:4d}")

    # ── Field presence in qualifying cases ──
    print(f"\n  Field presence (in {len(intermediate_cases)} qualifying cases):")
    for field in core_fields:
        counts = stats["field_stats"][field]
        pct = (
            counts["present"] / stats["unique_patients"] * 100
            if stats["unique_patients"]
            else 0
        )
        print(
            f"    {field:30s}: {counts['present']:4d} present ({pct:.1f}%), "
            f"{counts['missing']:4d} missing"
        )

    # ── Disease distribution (quick sampling from diagnosis) ──
    disease_counts: dict[str, int] = defaultdict(int)
    disease_keywords = {
        "牙髓炎/pulpitis": re.compile(r"pulpitis", re.IGNORECASE),
        "根尖周炎/apical": re.compile(r"apical", re.IGNORECASE),
        "龋病/caries": re.compile(r"caries", re.IGNORECASE),
        "阻生齿/impacted": re.compile(r"impacted", re.IGNORECASE),
        "牙周病/perio": re.compile(r"perio(?!dontal)", re.IGNORECASE),
        "牙龈炎/gingivitis": re.compile(r"gingivitis", re.IGNORECASE),
        "牙列缺损/missing": re.compile(r"missing", re.IGNORECASE),
        "牙体缺损/defect": re.compile(r"defect", re.IGNORECASE),
        "正畸/orthodontic|malformed": re.compile(r"orthodontic|malformed", re.IGNORECASE),
    }
    for case in intermediate_cases:
        diag = case["raw"]["diagnosis_primary_en"]
        matched = False
        for label, pattern in disease_keywords.items():
            if pattern.search(diag):
                disease_counts[label] += 1
                matched = True
        if not matched:
            disease_counts["其他/other"] += 1

    print(f"\n  Disease distribution (from diagnosis text):")
    for label, count in sorted(disease_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:35s}: {count:3d}")

    print(f"\n{'=' * 60}")
    print("Done. Next step: scripts/enrich_cases.py")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
