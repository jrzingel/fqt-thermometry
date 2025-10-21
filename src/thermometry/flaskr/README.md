
Get all readings in a time range
```sql
SELECT m.time, m.reading
FROM measurement m
JOIN sensor s ON m.sensor_id = s.id
JOIN fridge f ON s.fridge_id = f.id
WHERE f.name = 'fridge' AND s.name = 'sensor'
  AND m.time BETWEEN ? AND ?
ORDER BY m.time;
```

Or for more readings
```sql
SELECT f.name AS fridge, s.name AS sensor, m.time, m.reading
FROM measurement m
JOIN sensor s ON m.sensor_id = s.id
JOIN fridge f ON s.fridge_id = f.id
WHERE (
    (f.name = 'A' AND s.name = 'S1') OR
    (f.name = 'C' AND s.name IN ('S2', 'S3'))
)
AND m.time BETWEEN ? AND ?
ORDER BY m.time;
```

To add a reading run the following
```sql
INSERT INTO measurement (sensor_id, time, reading)
VALUES (
    (
        SELECT s.id FROM sensor s
        JOIN fridge f ON s.fridge_id = f.id
        WHERE f.name = 'A' AND s.name = 'S1'
    ),
    strftime('%s', '2025-04-16T12:00:00'),  -- convert ISO to UNIX timestamp
    3.1415
);
```

To add a reading to the latest table:
```sql
INSERT INTO latest_reading (sensor_id, time, reading)
VALUES (
    (SELECT s.id FROM sensor s
     JOIN fridge f ON s.fridge_id = f.id
     WHERE f.name = 'B' AND s.name = 'S2'),
    strftime('%s', '2025-04-16T12:34:00'),
    42.0
)
ON CONFLICT(sensor_id) DO UPDATE SET
    time = excluded.time,
    reading = excluded.reading;
```

And to fetch these latest readings
```sql
SELECT lr.time, lr.reading
FROM latest_reading lr
JOIN sensor s ON lr.sensor_id = s.id
JOIN fridge f ON s.fridge_id = f.id
WHERE f.name = 'B' AND s.name = 'S2';
```

## Adding new fridges / sensors

New fridge (assume unique name)
```sql
INSERT INTO fridge (name) VALUES ('E');
```

New sensor for a fridge
```sql
INSERT INTO sensor (fridge_id, name)
VALUES (
    (SELECT id FROM fridge WHERE name = 'E'),
    'S1'
);
```