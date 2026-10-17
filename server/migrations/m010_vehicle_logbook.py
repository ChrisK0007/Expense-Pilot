"""Actual odometer readings and timestamped, deduplicated native journeys."""
from migrations import execute_script


def upgrade(connection):
    for name, definition in [('started_at', 'REAL'), ('ended_at', 'REAL'), ('client_ref', 'TEXT')]:
        if name not in {r[1] for r in connection.execute('PRAGMA table_info(vehicle_journeys)')}:
            connection.execute(f'ALTER TABLE vehicle_journeys ADD COLUMN {name} {definition}')
    execute_script(connection, """
        CREATE UNIQUE INDEX IF NOT EXISTS vehicle_journey_client_ref ON vehicle_journeys(client_ref) WHERE client_ref IS NOT NULL;
        CREATE TABLE IF NOT EXISTS vehicle_odometer(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
            recorded_at REAL NOT NULL,
            reading_m INTEGER NOT NULL CHECK(reading_m>=0),
            notes TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            UNIQUE(vehicle_id,recorded_at)
        );
    """)
