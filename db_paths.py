from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "databases"


def get_db_path(db_name: str) -> str:
    DB_DIR.mkdir(exist_ok=True)

    old_locations = [
        BASE_DIR / db_name,
        BASE_DIR / "BASES DE DATOS" / db_name,
    ]
    new_path = DB_DIR / db_name

    if not new_path.exists():
        for old_path in old_locations:
            if old_path.exists():
                old_path.replace(new_path)
                break

    return str(new_path)
