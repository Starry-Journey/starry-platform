"""把 SQLite 数据迁移到 Postgres（一次性脚本）。"""

import sys

from sqlalchemy import create_engine, insert, select, text

from app import models  # noqa: F401
from app.db import Base

ORDER = [
    models.User,
    models.ApiToken,
    models.Comment,
    models.Conversation,
    models.Message,
    models.Chart,
]


def main(sqlite_path: str, pg_url: str) -> None:
    src = create_engine(f"sqlite:///{sqlite_path}", future=True)
    dst = create_engine(pg_url, future=True)
    Base.metadata.create_all(dst)

    with src.connect() as s, dst.begin() as d:
        for model in ORDER:
            rows = [dict(r) for r in s.execute(select(model)).mappings()]
            if rows:
                d.execute(insert(model), rows)
            print(f"{model.__tablename__}: {len(rows)}")

        for model in ORDER:
            table = model.__tablename__
            d.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )
            )
    print("done")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: migrate_to_postgres.py /path/api.db postgresql+psycopg2://...")
    main(sys.argv[1], sys.argv[2])
