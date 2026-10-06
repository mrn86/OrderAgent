"""Create order_agent database if missing."""

from sqlalchemy import create_engine, text

URL = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"


def main() -> None:
    engine = create_engine(URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'order_agent'")
        ).scalar()
        if exists:
            print("order_agent already exists")
            return
        conn.execute(text("CREATE DATABASE order_agent"))
        print("created database order_agent")


if __name__ == "__main__":
    main()
