from migrations import execute_script


def upgrade(connection):
    if 'route_json' not in {r[1] for r in connection.execute('PRAGMA table_info(vehicle_journeys)')}:
        connection.execute('ALTER TABLE vehicle_journeys ADD COLUMN route_json TEXT')
    execute_script(connection, '''
        CREATE TABLE IF NOT EXISTS journey_upload_receipts(
            client_ref TEXT PRIMARY KEY, journey_id INTEGER NOT NULL,
            fingerprint TEXT NOT NULL);
    ''')
