import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "./backups"))


def utc_now():
    return datetime.now(timezone.utc)


def create_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = utc_now().strftime("%Y%m%d_%H%M%S")
    target = BACKUP_DIR / timestamp
    target.mkdir(parents=True, exist_ok=True)

    if DATA_DIR.exists():
        shutil.copytree(
            DATA_DIR,
            target / "data",
            dirs_exist_ok=True,
        )

    return {
        "status": "ok",
        "created_at": utc_now().isoformat(),
        "path": str(target),
    }


if __name__ == "__main__":
    print(create_backup())
