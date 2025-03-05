DROP TABLE IF EXISTS fridges;
DROP TABLE IF EXISTS sensors;
DROP TABLE IF EXISTS temperatures;

CREATE TABLE fridges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE sensors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fridge TEXT NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY (fridge) REFERENCES fridges (name)
);

CREATE TABLE temperatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    fridge TEXT NOT NULL,
    sensor TEXT NOT NULL,
    temp REAL NOT NULL,
    FOREIGN KEY (fridge) REFERENCES fridges (name),
    FOREIGN KEY (sensor) REFERENCES sensors (name)

);
