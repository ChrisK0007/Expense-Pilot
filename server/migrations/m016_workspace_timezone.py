def upgrade(connection):
    # Existing trips were recorded against Brisbane. Preserve that calendar
    # context when the workspace changes timezone or an offline draft is retried.
    connection.execute("ALTER TABLE vehicle_journeys ADD COLUMN date_timezone TEXT NOT NULL DEFAULT 'Australia/Brisbane'")
