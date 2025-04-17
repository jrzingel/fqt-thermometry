-- Old stuff
DROP TABLE IF EXISTS fridges;
DROP TABLE IF EXISTS sensors;
DROP TABLE IF EXISTS pressures;
DROP TABLE IF EXISTS temperatures;

-- If re-creating
DROP TABLE IF EXISTS sensor;
DROP TABLE IF EXISTS fridge;
DROP TABLE IF EXISTS measurement;

-- Fridge table
CREATE TABLE fridge (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Sensor table (over all fridges)
CREATE TABLE sensor (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fridge_id INTEGER NOT NULL,
    UNIQUE(name, fridge_id),
    FOREIGN KEY (fridge_id) REFERENCES fridge(id)
);

-- Measurement table
CREATE TABLE measurement (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time INTEGER NOT NULL, -- UNIX timestamp
    sensor_id INTEGER NOT NULL,
    reading REAL NOT NULL,
    FOREIGN KEY (sensor_id) REFERENCES sensor(id)
);

-- Latest readings only table
CREATE TABLE latest_reading (
    sensor_id INTEGER PRIMARY KEY,  -- max 1 row per sensor
    time INTEGER NOT NULL,
    reading REAL NOT NULL,
    FOREIGN KEY (sensor_id) REFERENCES sensor(id)
)

-- Indexes for fast reads
CREATE UNIQUE INDEX idx_measurement_sensor_time ON measurement(sensor_id, time);
CREATE INDEX idx_measurement_time ON measurement(time);