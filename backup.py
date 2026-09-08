import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


# Папка, где site-insight-engine хранит данные.
# В docker-compose эта папка будет смонтирована отдельно.
DATA_DIR = Path(
    os.getenv("DATA_DIR", "./site-insight-engine/data")
).resolve()

# Куда складываем резервные копии.
BACKUP_DIR = Path(
    os.getenv("BACKUP_DIR", "./backups")
).resolve()

# Сколько последних backup храним.
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "7"))


def now_string():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


def find_databases():
    """
    Ищет SQLite-файлы в папке данных.
    """
    if not DATA_DIR.exists():
        return []

    return list(DATA_DIR.glob("*.db")) + list(DATA_DIR.glob("*.sqlite")) + list(
        DATA_DIR.glob("*.sqlite3")
    )


def backup_sqlite(source: Path, destination: Path):
    """
    Делает безопасную SQLite backup-копию через встроенный
    механизм SQLite, а не простым копированием файла.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_connection = sqlite3.connect(str(source))
    destination_connection = sqlite3.connect(str(destination))

    try:
        with destination_connection:
            source_connection.backup(destination_connection)
    finally:
        source_connection.close()
        destination_connection.close()


def backup_other_files(timestamp: str):
    """
    Сохраняет остальные файлы из DATA_DIR.
    SQLite-файлы обрабатываются отдельно.
    """
    target_dir = BACKUP_DIR / timestamp / "files"
    target_dir.mkdir(parents=True, exist_ok=True)

    database_suffixes = {".db", ".sqlite", ".sqlite3"}

    for item in DATA_DIR.iterdir():
        if item.is_dir():
            shutil.copytree(
                item,
                target_dir / item.name,
                dirs_exist_ok=True,
            )
        elif item.suffix.lower() not in database_suffixes:
            shutil.copy2(item, target_dir / item.name)


def cleanup_old_backups():
    """
    Оставляет только MAX_BACKUPS последних резервных копий.
    """
    if not BACKUP_DIR.exists():
        return

    backups = [
        item
        for item in BACKUP_DIR.iterdir()
        if item.is_dir()
    ]

    backups.sort(key=lambda item: item.name, reverse=True)

    for old_backup in backups[MAX_BACKUPS:]:
        shutil.rmtree(old_backup)


def create_backup():
    timestamp = now_string()
    backup_root = BACKUP_DIR / timestamp
    backup_root.mkdir(parents=True, exist_ok=True)

    databases = find_databases()

    if not databases:
        print(f"[BACKUP] SQLite база не найдена в: {DATA_DIR}")

    for database in databases:
        destination = backup_root / "database" / database.name
        backup_sqlite(database, destination)

        print(
            f"[BACKUP] SQLite сохранена: "
            f"{database.name}"
        )

    backup_other_files(timestamp)

    cleanup_old_backups()

    print(
        f"[BACKUP] Готово: {backup_root}"
    )

    return backup_root


if __name__ == "__main__":
    create_backup()
