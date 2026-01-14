#!/usr/bin/env python3
"""Initialize SQLite database for hello_database.

This script is intentionally idempotent:
- It always targets a stable DB file path: ./myapp.db (relative to this container directory)
- It uses CREATE TABLE IF NOT EXISTS so it can be run repeatedly
- It writes connection helper files used by other tooling in this repo (db_connection.txt and db_visualizer/sqlite.env)

It also creates the request logging table required by the app:
  request_logs(
    id INTEGER PRIMARY KEY,
    route TEXT,
    timestamp INTEGER,
    ip TEXT,
    user_agent TEXT,
    location TEXT,
    temperature REAL,
    units TEXT
  )
"""

import os
import sqlite3
from pathlib import Path

DB_NAME = "myapp.db"


def _container_db_path() -> Path:
    """Return the stable DB path within this container directory."""
    # Ensure stability regardless of working directory: always place DB next to this script.
    return Path(__file__).resolve().parent / DB_NAME


def _connect(db_path: Path) -> sqlite3.Connection:
    """Create a SQLite connection with sensible defaults."""
    conn = sqlite3.connect(str(db_path))
    # Improve concurrency a bit; safe for a simple app.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create/upgrade schema in an idempotent way."""
    cursor = conn.cursor()

    # Existing sample tables (kept for backwards compatibility with existing tooling)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # New: Request log table for the Hello + Location + Temperature app
    #
    # Notes:
    # - We store timestamp as INTEGER epoch milliseconds for easy ordering/queries.
    # - location is stored as TEXT so the backend can store either a human-readable string
    #   or JSON (stringified) without schema churn.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY,
            route TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            ip TEXT,
            user_agent TEXT,
            location TEXT,
            temperature REAL,
            units TEXT
        )
        """
    )

    # Helpful indexes for common analytics queries
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_logs_timestamp ON request_logs(timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_request_logs_route ON request_logs(route)"
    )

    # Seed info (idempotent)
    cursor.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("project_name", "hello_database"),
    )
    cursor.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("version", "0.1.0"),
    )
    cursor.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("author", "John Doe"),
    )
    cursor.execute(
        "INSERT OR REPLACE INTO app_info (key, value) VALUES (?, ?)",
        ("description", "SQLite DB backing the Hello+Location+Temperature app with request logging."),
    )

    conn.commit()


def _write_helper_files(db_path: Path) -> None:
    """Write db_connection.txt and db_visualizer/sqlite.env used by local tooling."""
    container_dir = Path(__file__).resolve().parent
    connection_string = f"sqlite:///{db_path}"

    # Save connection information to a file (stable absolute path is helpful)
    try:
        with open(container_dir / "db_connection.txt", "w", encoding="utf-8") as f:
            f.write("# SQLite connection methods:\n")
            f.write(f"# Python: sqlite3.connect('{db_path}')\n")
            f.write(f"# Connection string: {connection_string}\n")
            f.write(f"# File path: {db_path}\n")
    except Exception as e:
        print(f"Warning: Could not save connection info: {e}")

    # Create environment variables file for Node.js viewer
    visualizer_dir = container_dir / "db_visualizer"
    visualizer_dir.mkdir(parents=True, exist_ok=True)
    try:
        with open(visualizer_dir / "sqlite.env", "w", encoding="utf-8") as f:
            f.write(f'export SQLITE_DB="{db_path}"\n')
    except Exception as e:
        print(f"Warning: Could not save environment variables: {e}")


def main() -> None:
    """Entrypoint for initializing the SQLite DB schema and helper files."""
    db_path = _container_db_path()

    print("Starting SQLite setup...")
    if db_path.exists():
        print(f"SQLite database already exists at {db_path}")
        # Verify it's accessible
        try:
            conn = _connect(db_path)
            conn.execute("SELECT 1")
            conn.close()
            print("Database is accessible and working.")
        except Exception as e:
            print(f"Warning: Database exists but may be corrupted: {e}")
    else:
        print(f"Creating new SQLite database at {db_path}...")

    conn = _connect(db_path)
    try:
        _create_schema(conn)
    finally:
        conn.close()

    # Basic statistics
    conn = _connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM request_logs")
        logs_count = cursor.fetchone()[0]
    finally:
        conn.close()

    _write_helper_files(db_path)

    print("\nSQLite setup complete!")
    print(f"Database: {DB_NAME}")
    print(f"Location: {db_path}")
    print("")
    print("To use with Node.js viewer, run: source db_visualizer/sqlite.env")
    print("\nTo connect to the database, use one of the following methods:")
    print(f"1. Python: sqlite3.connect('{db_path}')")
    print(f"2. Connection string: sqlite:///{db_path}")
    print(f"3. Direct file access: {db_path}")
    print("")
    print("Database statistics:")
    print(f"  Tables: {table_count}")
    print(f"  Request logs records: {logs_count}")

    # If sqlite3 CLI is available, show how to use it
    try:
        import subprocess

        result = subprocess.run(["which", "sqlite3"], capture_output=True, text=True)
        if result.returncode == 0:
            print("")
            print("SQLite CLI is available. You can also use:")
            print(f"  sqlite3 {db_path}")
    except Exception:
        pass

    print("\nScript completed successfully.")


if __name__ == "__main__":
    main()
