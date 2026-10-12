#!/usr/bin/env python3
"""Seed the database with patient-simulation cases and test users.

Two case sources:

  1. data/cases/*.patient.json  — the v2.1 patient-simulation schema (H/P + opening).
     This is the current source of truth; loaded by default.
  2. data/cases/mvp_cases.json  — the legacy nested schema (basic_info/present_illness/…).
     Superseded; loaded only with --with-legacy.

exam.json is deliberately NOT loaded: the exam module is deferred to the frontend
(images / prompt cards), so nothing on the patient side needs it yet.
"""

import argparse
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import bcrypt

from app.database import SessionLocal, engine, Base
from app.models import User, Case

CASES_DIR = Path(__file__).resolve().parent.parent / "data" / "cases"

# 医院数据用中文难度（基础/中等/…），DB 与前端沿用英文枚举（见 frontend/src/components/ui/DifficultyBadge.tsx）。
# 不做映射的话，前端只会退回灰色原文标签，与其它病例的配色不一致。
DIFFICULTY_MAP = {
    "基础": "beginner",
    "初级": "beginner",
    "中等": "intermediate",
    "进阶": "intermediate",
    "高级": "advanced",
}
DEFAULT_DIFFICULTY = "intermediate"


def _seed_users(db) -> None:
    test_users = [
        {"username": "test001", "password": "123456", "role": "student"},
        {"username": "teacher001", "password": "123456", "role": "teacher"},
    ]
    for u in test_users:
        existing = db.query(User).filter_by(username=u["username"]).first()
        if not existing:
            db.add(User(
                username=u["username"],
                password=bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode(),
                role=u["role"],
            ))
    db.commit()


def _load_sidecar(case_id: str, kind: str) -> dict | None:
    """Load data/cases/<case>.<kind>.json (answer / rubric). Missing file is not fatal —
    the case still loads, just without scoring data. Loudly noted, never silently blanked."""
    path = CASES_DIR / f"{case_id.lower()}.{kind}.json"
    if not path.exists():
        print(f"  Note: {path.name} not found — {case_id} loaded without {kind} data")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_patient_cases(db) -> tuple[int, int]:
    """Load data/cases/*.patient.json (patient-simulation schema). Returns (added, skipped)."""
    files = sorted(CASES_DIR.glob("*.patient.json"))

    added_count = 0
    skipped_count = 0
    for case_file in files:
        with open(case_file, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        # 标题用中性编号（EN01…）。医院原始标题里含诊断，绝不能进学生端。
        title = case_data.get("case_id", "")
        if not title:
            print(f"  Skipping {case_file.name}: missing case_id")
            skipped_count += 1
            continue

        existing = db.query(Case).filter_by(title=title).first()
        if existing:
            skipped_count += 1
            continue

        # 同一 case_id 的 exam.json（检查侧数据），存到独立列，不进 data
        exam_path = CASES_DIR / f"{title.lower()}.exam.json"
        exam_data = None
        if exam_path.exists():
            with open(exam_path, "r", encoding="utf-8") as f:
                exam_data = json.load(f)
        else:
            print(f"  Note: {exam_path.name} not found — {title} loaded without exam data")

        # 评分侧数据：参考答案（A2 隐藏块）与 R 锚点（A3 页）。独立列，只有评分链路读得到。
        answer_key = _load_sidecar(title, "answer")
        scoring_rubric = _load_sidecar(title, "rubric")

        raw_difficulty = case_data.get("difficulty", "")
        db.add(Case(
            title=title,
            department=case_data.get("group", "口腔科"),
            difficulty=DIFFICULTY_MAP.get(raw_difficulty, DEFAULT_DIFFICULTY),
            data=case_data,          # 整份 patient.json：identity + opening + facts + psychology
            exam_data=exam_data,     # 整份 exam.json：E 项的 label/level/aliases/result/boundary
            answer_key=answer_key,   # 整份 answer.json：D/DD/T/G（评分链路专用）
            scoring_rubric=scoring_rubric,  # 整份 rubric.json：R01–R14 锚点（评分链路专用）
            status="published",
        ))
        added_count += 1

    db.commit()
    return added_count, skipped_count


def _load_legacy_mvp_cases(db) -> tuple[int, int]:
    """Load data/cases/mvp_cases.json (legacy nested schema). Returns (added, skipped)."""
    mvp_path = CASES_DIR / "mvp_cases.json"
    if not mvp_path.exists():
        print(f"  --with-legacy given but {mvp_path} not found")
        return 0, 0

    with open(mvp_path, "r", encoding="utf-8") as f:
        mvp_cases = json.load(f)

    added_count = 0
    skipped_count = 0
    for c in mvp_cases:
        existing = db.query(Case).filter_by(title=c["title"]).first()
        if existing:
            skipped_count += 1
            continue
        db.add(Case(
            title=c["title"],
            department=c["department"],
            difficulty=c["difficulty"],
            data=c["data"],
            status=c.get("status", "published"),
        ))
        added_count += 1

    db.commit()
    return added_count, skipped_count


def seed(with_legacy: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    _seed_users(db)

    patient_added, patient_skipped = _load_patient_cases(db)

    legacy_added, legacy_skipped = (0, 0)
    if with_legacy:
        legacy_added, legacy_skipped = _load_legacy_mvp_cases(db)

    user_count = db.query(User).count()
    case_count = db.query(Case).count()
    print(f"Seeded: {user_count} users, {case_count} cases "
          f"({patient_added} patient + {legacy_added} legacy, "
          f"{patient_skipped + legacy_skipped} skipped)")
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-legacy",
        action="store_true",
        help="also load mvp_cases.json (legacy schema; off by default)",
    )
    seed(with_legacy=parser.parse_args().with_legacy)
