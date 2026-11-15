"""Store quote-link digests and acceptance details."""


def upgrade(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS billing_quote_acceptance (
            document_id INTEGER PRIMARY KEY REFERENCES billing_documents(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE,
            recipient TEXT NOT NULL,
            accepted_name TEXT,
            accepted_at TEXT,
            CHECK ((accepted_name IS NULL) = (accepted_at IS NULL))
        )
    """)
