#!/usr/bin/env python3
"""Seed the database with MVP cases and a test user."""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import bcrypt

from app.database import SessionLocal, engine, Base
from app.models import User, Case


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # ── Create test users ──────────────────────────────────────────
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

    # ── Load MVP cases (ID 1-3) ─────────────────────────────────
    mvp_path = Path(__file__).resolve().parent.parent / "data" / "cases" / "mvp_cases.json"
    if not mvp_path.exists():
        print(f"Error: {mvp_path} not found")
        db.close()
        return

    with open(mvp_path, "r", encoding="utf-8") as f:
        mvp_cases = json.load(f)

    mvp_count = 0
    for c in mvp_cases:
        existing = db.query(Case).filter_by(title=c["title"]).first()
        if not existing:
            db.add(Case(
                title=c["title"],
                department=c["department"],
                difficulty=c["difficulty"],
                data=c["data"],
                status=c.get("status", "published"),
            ))
            mvp_count += 1

    db.commit()

    # ── Load enriched cases (ID 4+) ──────────────────────────────
    cases_dir = Path(__file__).resolve().parent.parent / "data" / "cases"
    # Import case_004.json through case_999.json (enriched by enrich_cases.py)
    enriched_files = sorted(
        [f for f in cases_dir.glob("case_*.json")
         if f.name != "mvp_cases.json" and f.name.startswith("case_")]
    )

    imported_count = 0
    skipped_count = 0
    for case_file in enriched_files:
        with open(case_file, "r", encoding="utf-8") as f:
            case_data = json.load(f)

        title = case_data.get("title", "")
        if not title:
            print(f"  Skipping {case_file.name}: missing title")
            skipped_count += 1
            continue

        # Status filtering: only import "published" cases
        status = case_data.get("status", "draft")
        if status != "published":
            skipped_count += 1
            continue

        existing = db.query(Case).filter_by(title=title).first()
        if existing:
            skipped_count += 1
            continue

        db.add(Case(
            title=title,
            department=case_data.get("department", "口腔科"),
            difficulty=case_data.get("difficulty", "intermediate"),
            data=case_data.get("data", {}),
            status=status,
        ))
        imported_count += 1

    db.commit()

    # ── Report ─────────────────────────────────────────────────────
    user_count = db.query(User).count()
    case_count = db.query(Case).count()
    print(f"Seeded: {user_count} users, {case_count} cases "
          f"({mvp_count} MVP + {imported_count} enriched, {skipped_count} skipped)")
    db.close()


if __name__ == "__main__":
    seed()
