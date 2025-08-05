-- If re-creating
CREATE EXTENSION IF NOT EXISTS timescaledb;

DROP TABLE IF EXISTS measurement;
DROP TABLE IF EXISTS latest_reading;
DROP TABLE IF EXISTS sensor;
DROP TABLE IF EXISTS fridge;

-- Fridge table
CREATE TABLE fridge (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Sensor table (over all fridges)
CREATE TABLE sensor (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    fridge_id INTEGER NOT NULL,
    latest BOOLEAN NOT NULL DEFAULT FALSE,  -- Store in FALSE=measurement, TRUE=latest_reading
    UNIQUE(name, fridge_id),
    FOREIGN KEY (fridge_id) REFERENCES fridge(id)
);

-- Latest readings only table
CREATE TABLE latest_reading (
    sensor_id INTEGER PRIMARY KEY,  -- max 1 row per sensor
    time TIMESTAMPTZ NOT NULL,  -- use timestamp with timezone
    reading DOUBLE PRECISION NOT NULL,
    FOREIGN KEY (sensor_id) REFERENCES sensor(id)
);

-- Measurement table (use TimescaleDB for optimisation)
CREATE TABLE measurement (
    id BIGSERIAL NOT NULL,
    time TIMESTAMPTZ NOT NULL, -- use timestamp with timezone
    sensor_id INTEGER NOT NULL,
    reading DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (sensor_id, time),
    FOREIGN KEY (sensor_id) REFERENCES sensor(id)
);

-- Create Timescale hypertable
SELECT create_hypertable('measurement', 'time', chunk_time_interval => INTERVAL '1 week', if_not_exists => TRUE);

ALTER TABLE measurement SET (
    timescaledb.compress = true,
    timescaledb.compress_segmentby = 'sensor_id'
);
SELECT add_compression_policy('measurement', INTERVAL '2 months');

-- Indexes for fast reads
CREATE INDEX idx_measurement_time ON measurement (time DESC);
CREATE INDEX idx_measurement_sensor_time ON measurement(sensor_id, time);

