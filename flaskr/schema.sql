DROP TABLE IF EXISTS fridges;
DROP TABLE IF EXISTS sensors;
DROP TABLE IF EXISTS pressures;
DROP TABLE IF EXISTS temperatures;

CREATE TABLE pressures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    fridge TEXT NOT NULL,
    sensor TEXT NOT NULL,
    pressure REAL NOT NULL
);
CREATE UNIQUE INDEX no_duplicate_pressures ON pressures (timestamp, fridge, sensor, pressure);

CREATE TABLE temperatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    fridge TEXT NOT NULL,
    sensor TEXT NOT NULL,
    temp REAL NOT NULL
);
CREATE UNIQUE INDEX no_duplicate_temperatures ON temperatures (timestamp, fridge, sensor, temp);
