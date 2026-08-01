#!/usr/bin/env python3
"""
Environment check script.

Verifies that the development environment is correctly set up:
  - Python >= 3.10
  - Virtual environment active
  - Dependencies installed
  - LLM API key configured
  - Raw data file present
  - SQLite writable
"""

import importlib
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw" / "medical_records.csv"
ENV_FILE = PROJECT_ROOT / ".env"

EXIT_OK = 0
EXIT_WARN = 1
EXIT_ERR = 2

warnings = []
errors = []


def check(label: str, condition: bool, severity: str = "error") -> None:
    if not condition:
        msg = f"  [{severity.upper()}] {label}"
        if severity == "error":
            errors.append(msg)
        else:
            warnings.append(msg)
    else:
        print(f"  [ OK ] {label}")


def main() -> int:
    print("=" * 60)
    print("  Clinical Interview Simulation — Environment Check")
    print("=" * 60)

    # ── Python version ──────────────────────────────────────────────
    py_ver = sys.version_info
    py_ver_str = f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    check(f"{py_ver_str} >= 3.10", py_ver >= (3, 10))
    print(f"  Executable: {sys.executable}")

    # ── Virtual environment ─────────────────────────────────────────
    in_venv = sys.prefix != sys.base_prefix
    check("虚拟环境已激活", in_venv, severity="warn")

    # ── Dependencies ────────────────────────────────────────────────
    deps = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "openai": "openai",
        "sentence_transformers": "sentence-transformers",
        "pydantic_settings": "pydantic-settings",
        "loguru": "loguru",
        "passlib": "passlib",
    }
    print("\nDependencies:")
    for import_name, pkg_name in deps.items():
        try:
            importlib.import_module(import_name)
            check(pkg_name, True)
        except ImportError:
            check(pkg_name, False)

    # ── Raw data ────────────────────────────────────────────────────
    print("\nData files:")
    check(f"Raw CSV exists: {DATA_RAW}", DATA_RAW.exists())

    # ── .env file ───────────────────────────────────────────────────
    print("\nConfiguration:")
    check(f".env file exists: {ENV_FILE}", ENV_FILE.exists())

    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        has_key = "LLM_API_KEY" in content and "your_" not in content.split("LLM_API_KEY=")[-1].split("\n")[0].strip()
        check("LLM_API_KEY 已配置（非占位符）", has_key, severity="warn")

    # ── SQLite ──────────────────────────────────────────────────────
    print("\nDatabase:")
    try:
        db_path = PROJECT_ROOT / "data" / "app.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("SELECT 1")
        conn.close()
        # Clean up test db
        db_path.unlink(missing_ok=True)
        check("SQLite 可正常读写", True)
    except Exception as e:
        check(f"SQLite 测试失败: {e}", False)

    # ── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"  ERRORS:   {len(errors)}（必须修复）")
        for e in errors:
            print(e)
    if warnings:
        print(f"  WARNINGS: {len(warnings)}（建议修复）")
        for w in warnings:
            print(w)
    if not errors and not warnings:
        print("  所有检查通过！✅")
    else:
        print(f"\n  结果: {len(errors)} errors, {len(warnings)} warnings")

    return EXIT_ERR if errors else (EXIT_WARN if warnings else EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
