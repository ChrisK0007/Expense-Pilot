"""Store a fuel fill-up against the original expense."""


def upgrade(connection):
    connection.execute("""
        CREATE TABLE IF NOT EXISTS vehicle_fuel (
            expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE CASCADE,
            volume_ml INTEGER NOT NULL CHECK(volume_ml BETWEEN 1 AND 1000000),
            odometer_m INTEGER NOT NULL CHECK(odometer_m BETWEEN 0 AND 10000000000),
            full_tank INTEGER NOT NULL CHECK(full_tank IN (0, 1))
        )
    """)
