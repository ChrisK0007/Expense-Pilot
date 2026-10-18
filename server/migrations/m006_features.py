def upgrade(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS feature_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,data TEXT NOT NULL)')
