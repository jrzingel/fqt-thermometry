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


-- ---------------------------------------------------------------------------
-- Alert subsystem state.
--
-- Alert state used to live in the alarm process's memory, mirrored to disk as
-- status.json and commanded through changes.json. That lost every alarm and
-- every manual override on restart, raced against the web server, and took up
-- to a minute to propagate. It lives here now so both processes share one
-- authoritative copy.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS alert_event;
DROP TABLE IF EXISTS alert_state;
DROP TABLE IF EXISTS evaluator_heartbeat;

-- Current state of every configured (alert type, fridge) pair
CREATE TABLE alert_state (
    alert_type TEXT NOT NULL,
    fridge TEXT NOT NULL,
    state TEXT NOT NULL,                  -- DISABLED / ENABLED / ALARM / MANUALLY_DISABLED / UNKNOWN
    since TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_triggered TIMESTAMPTZ,
    updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Requested state change from the website, applied by the alarm process on its next tick.
    -- Replaces changes.json.
    pending_action TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,   -- display fields, latch reasons, evidence
    PRIMARY KEY (alert_type, fridge)
);

-- Audit trail of every state transition. The alarm system has never had one.
CREATE TABLE alert_event (
    id BIGSERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_type TEXT NOT NULL,
    fridge TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_alert_event_time ON alert_event (time DESC);
CREATE INDEX idx_alert_event_lookup ON alert_event (alert_type, fridge, time DESC);

-- Liveness of the alarm evaluator. The web server reads this to decide whether
-- the alert states it is serving can be trusted; a stale heartbeat makes the
-- critical interlock fail safe instead of freezing on its last known value.
CREATE TABLE evaluator_heartbeat (
    name TEXT PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT now()
);
