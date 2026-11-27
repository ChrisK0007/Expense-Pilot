"""Preserve old numbers without claiming they were confirmed dashboard readings."""


def upgrade(connection):
    if 'odometer_source' in {row[1] for row in connection.execute('PRAGMA table_info(vehicle_fuel)')}:
        return
    connection.execute('ALTER TABLE vehicle_fuel RENAME TO vehicle_fuel_previous')
    connection.execute('''CREATE TABLE vehicle_fuel(
        expense_id INTEGER PRIMARY KEY REFERENCES expenses(id) ON DELETE CASCADE,
        volume_ml INTEGER NOT NULL CHECK(volume_ml BETWEEN 1 AND 1000000),
        odometer_m INTEGER CHECK(odometer_m BETWEEN 0 AND 10000000000),
        full_tank INTEGER NOT NULL CHECK(full_tank IN (0,1)),
        odometer_source TEXT NOT NULL DEFAULT 'unknown' CHECK(odometer_source IN ('unknown','estimated','dashboard'))
    )''')
    connection.execute("INSERT INTO vehicle_fuel SELECT expense_id,volume_ml,odometer_m,full_tank,'unknown' FROM vehicle_fuel_previous")
    connection.execute('DROP TABLE vehicle_fuel_previous')
