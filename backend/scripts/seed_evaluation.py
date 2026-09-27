# -*- coding: utf-8 -*-
"""Register every benchmark seed file into the local database.

Idempotent: a dataset that is already seeded is left alone. Run after the
schema is in place.

    cd backend && python -m scripts.seed_evaluation
"""
from __future__ import annotations

from app.db.connection import get_conn
from app.db.migrate import migrate
from app.evaluation.seed import import_all_seeds


def main() -> None :
    conn = get_conn()
    try :
        migrate(conn)
        results = import_all_seeds(conn)
    finally :
        conn.close()

    for result in results :
        print(
            f"Seeded {result['dataset_version']} / {result['reference_set_version']} "
            f"with {result['query_count']} queries"
        )


if (__name__ == "__main__") :
    main()
