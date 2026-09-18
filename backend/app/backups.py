"""Encrypted PostgreSQL dumps. Restore always targets a separate, empty database."""

import os
import subprocess
import tempfile
from pathlib import Path
from datetime import timedelta
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from sqlalchemy import select, delete
from .config import settings
from .db import SessionLocal
from .models import BackupJob, Call, now
from .domain import TERMINAL


def pg_env(database=None):
    url = make_url(settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL required")
    return {
        **os.environ,
        "PGHOST": url.host or "postgres",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "caller",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": database or url.database,
        "PGCONNECT_TIMEOUT": "10",
    }


def encrypt_dump(data, key):
    return Fernet(key.encode()).encrypt(data)


def decrypt_dump(data, key):
    return Fernet(key.encode()).decrypt(data)


def backup():
    cfg = settings()
    env = pg_env()
    directory = Path(cfg.backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    filename = now().strftime("caller-%Y%m%dT%H%M%S%fZ.dump.enc")
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "dump"
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--file", str(plain)],
            env=env,
            check=True,
            capture_output=True,
            timeout=600,
        )
        subprocess.run(
            ["pg_restore", "--list", str(plain)], check=True, capture_output=True, timeout=60
        )
        encrypted = encrypt_dump(plain.read_bytes(), cfg.backup_key)
        # Authentication/decryption must round-trip before publishing the copy.
        if decrypt_dump(encrypted, cfg.backup_key) != plain.read_bytes():
            raise RuntimeError("Backup verification failed")
        part = directory / (filename + ".partial")
        part.write_bytes(encrypted)
        os.chmod(part, 0o600)
        part.replace(directory / filename)
    for old in sorted(directory.glob("caller-*.dump.enc"), reverse=True)[7:]:
        old.unlink()
    return filename


def restore_to_empty(filename, database):
    cfg = settings()
    current = make_url(cfg.database_url).database
    if (
        not database.startswith("restore_")
        or database == current
        or not all(c.isalnum() or c == "_" for c in database)
    ):
        raise ValueError("Target must be a separate database named restore_*")
    path = Path(cfg.backup_dir) / Path(filename).name
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "dump"
        plain.write_bytes(decrypt_dump(path.read_bytes(), cfg.backup_key))
        os.chmod(plain, 0o600)
        # createdb fails if the target exists; never replace existing data.
        subprocess.run(
            ["createdb", database], env=pg_env(), check=True, capture_output=True, timeout=60
        )
        subprocess.run(
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--dbname",
                database,
                str(plain),
            ],
            env=pg_env(database),
            check=True,
            capture_output=True,
            timeout=600,
        )


def tick():
    cfg = settings()
    with SessionLocal() as db:
        job = db.scalar(
            select(BackupJob)
            .where(BackupJob.status == "queued")
            .order_by(BackupJob.created_at)
            .with_for_update(skip_locked=True)
        )
        if job is None and cfg.backup_key:
            latest = db.scalar(
                select(BackupJob).where(
                    BackupJob.status == "completed",
                    BackupJob.created_at > now() - timedelta(days=1),
                )
            )
            pending = db.scalar(select(BackupJob).where(BackupJob.status == "running"))
            if not latest and not pending:
                job = BackupJob()
                db.add(job)
        if job is not None:
            job.status = "running"
            db.commit()
            try:
                job.filename = backup()
                job.status = "completed"
            except Exception as exc:
                job.status = "failed"
                job.error = type(exc).__name__  # never persist subprocess stderr with credentials
            db.commit()
        db.execute(
            delete(Call).where(
                Call.created_at < now() - timedelta(days=cfg.retention_days),
                Call.status.in_(TERMINAL),
            )
        )
        db.commit()


def main():
    import logging
    import time
    from sqlalchemy import text
    from .db import engine

    logging.basicConfig(level=logging.INFO)
    with engine.connect() as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(481727)")):
            raise RuntimeError("Maintenance worker already running")
        # A prior crash leaves a visible failed backup, not a permanently running one.
        with SessionLocal() as db:
            for job in db.scalars(select(BackupJob).where(BackupJob.status == "running")):
                job.status = "failed"
                job.error = "WorkerRestarted"
            db.commit()
        while True:
            lock.execute(text("SELECT 1"))
            try:
                tick()
            except Exception as exc:
                logging.error("maintenance_error type=%s", type(exc).__name__)
            time.sleep(60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["worker", "backup", "restore"])
    parser.add_argument("--file")
    parser.add_argument("--database")
    args = parser.parse_args()
    if args.action == "backup":
        print(backup())
    elif args.action == "restore":
        if not args.file or not args.database:
            parser.error("restore requires --file and --database")
        restore_to_empty(args.file, args.database)
        print("Restored to isolated database " + args.database)
    else:
        main()
