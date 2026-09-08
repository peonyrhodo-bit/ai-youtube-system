import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

DATA_DIR = Path(
    os.environ.get(
        "DATA_DIR",
        str(Path(__file__).parent / "data")
    )
)

DB_PATH = DATA_DIR / "youtube.db"

BACKUP_DIR = DATA_DIR / "backups"

MAX_BACKUPS = int(
    os.environ.get(
        "MAX_BACKUPS",
        "7"
    )
)


# ============================================================
# BACKUP
# ============================================================

def create_backup():

    if not DB_PATH.exists():

        raise FileNotFoundError(
            f"База данных не найдена: {DB_PATH}"
        )

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    backup_path = (
        BACKUP_DIR
        / f"youtube_{timestamp}.db"
    )

    source = sqlite3.connect(
        DB_PATH
    )

    destination = sqlite3.connect(
        backup_path
    )

    try:

        source.backup(
            destination
        )

        destination.commit()

    finally:

        destination.close()
        source.close()

    print(
        f"BACKUP OK: {backup_path}"
    )

    cleanup_old_backups()


# ============================================================
# CLEANUP
# ============================================================

def cleanup_old_backups():

    backups = sorted(
        BACKUP_DIR.glob(
            "youtube_*.db"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    old_backups = backups[
        MAX_BACKUPS:
    ]

    for backup in old_backups:

        try:

            backup.unlink()

            print(
                f"Удалён старый backup: {backup}"
            )

        except Exception as error:

            print(
                f"Ошибка удаления {backup}: {error}"
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        create_backup()

    except Exception as error:

        print(
            f"BACKUP ERROR: {error}"
        )

        raise
