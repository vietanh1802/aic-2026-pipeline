from app.db.connection import get_conn
from app.db.migrate import migrate
from app.evaluation.seed import import_seed


def main() -> None :
    conn = get_conn()
    try :
        migrate(conn)
        result = import_seed(conn)
    finally :
        conn.close()

    print(
        f"Seeded {result['dataset_version']} / {result['reference_set_version']} "
        f"with {result['query_count']} queries"
    )


if (__name__ == "__main__") :
    main()
