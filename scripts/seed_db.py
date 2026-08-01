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

    # ── Load MVP cases ─────────────────────────────────────────────
    mvp_path = Path(__file__).resolve().parent.parent / "data" / "cases" / "mvp_cases.json"
    if not mvp_path.exists():
        print(f"Error: {mvp_path} not found")
        db.close()
        return

    with open(mvp_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for c in cases:
        existing = db.query(Case).filter_by(title=c["title"]).first()
        if not existing:
            db.add(Case(
                title=c["title"],
                department=c["department"],
                difficulty=c["difficulty"],
                data=c["data"],
                status=c.get("status", "published"),
            ))

    db.commit()

    # ── Report ─────────────────────────────────────────────────────
    user_count = db.query(User).count()
    case_count = db.query(Case).count()
    print(f"Seeded: {user_count} users, {case_count} cases")
    db.close()


if __name__ == "__main__":
    seed()
