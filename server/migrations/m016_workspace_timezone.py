def upgrade(connection):
    # Existing trips were recorded against Brisbane. Preserve that calendar
    # context when the workspace changes timezone or an offline draft is retried.
    columns = {row[1] for row in connection.execute('PRAGMA table_info(vehicle_journeys)')}
    if 'date_timezone' not in columns:
        connection.execute("ALTER TABLE vehicle_journeys ADD COLUMN date_timezone TEXT NOT NULL DEFAULT 'Australia/Brisbane'")
