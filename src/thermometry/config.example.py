FRIDGE_KEYS = {
    "fridge1": "e45e8a48-096e-4d5e-b987-b849cce7de2e",
    'fridge2': "e45e8a48-096e-4d5e-b987-b849cce7de2e",
    "fridge3": "e45e8a48-096e-4d5e-b987-b849cce7de2e",
}
ALERT_PATH = "src/thermometry/alarm/status.json"
ALERT_CHANGE_PATH = "src/thermometry/alarm/changes.json"
ALERT_CONFIG_YAML_PATH = "/src/thermometry/config.example.yaml"
DATABASE = {
    "dbname": "thermometry",
    "user": "user",
    "password": "password",
    "host": "localhost",
    "port": 5432,
}

WEBSITE = {
    "port": 5000,  # recommended to keep this on 5000 and use nginx to reverse proxy to port 80
    "threads": 3
}
TEAMS_WEBHOOK = "..."
SERVER_URL = "http://localhost:5000"  # from perspective of the server (used by alerts internally)

WATCHDOG_TEAMS_WEBHOOK = "..."
WATCHDOG_WEBSITE_URL = "http://thermometry.example.com"  # used by the watchdog application
EXTERNAL_WEBSITE_URL = "http://thermometry.example.com"  # used by javascript to query the api