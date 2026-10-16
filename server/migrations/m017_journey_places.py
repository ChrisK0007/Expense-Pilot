def upgrade(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS journey_places (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        id TEXT NOT NULL, version INTEGER NOT NULL, mutation_id TEXT NOT NULL,
        deleted INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, address TEXT NOT NULL,
        latitude REAL NOT NULL, longitude REAL NOT NULL,
        PRIMARY KEY (user_id, id))''')
    connection.execute('''CREATE TABLE IF NOT EXISTS journey_place_mutations (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        mutation_id TEXT NOT NULL, fingerprint TEXT NOT NULL, response TEXT NOT NULL,
        PRIMARY KEY (user_id, mutation_id))''')
