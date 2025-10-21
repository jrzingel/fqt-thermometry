# FQT Thermometry

**View here http://status.fqt.unsw.edu.au**
(Must be on the UNSW VPN)

## Run

0) Dependencies are managed using `uv`. Install from https://docs.astral.sh/uv/.
1) First copy `config.example.py` to `config.py` and add the desired values.
2) Make sure that a PostgreSQL database has been created with TimescaleDB extension. See below for additional commands of how to do this.
3) Build the listener application and deploy it on the BlueFors fridge computer. See instructions below.
3) Run the website and alerts.


To run the website: `uv run website` or the alert system `uv run alerts` or to run both simultaneously `uv run all`.

To build the listener application:`uv run build-listener`

To build the watchdog application: `uv run build-watchdog`

### Other database commands
First install the TimescaleDB extension to the PostgreSQL database. This just is optimised for time series data and makes retriving data faster. Instructions to install this are found https://docs.tigerdata.com/self-hosted/latest/install/

To adjust the database by adding sensors and fridges use the following click commands.
All must be run with the format `uv run -- flask --app thermometry.flask <COMMAND>` where `<COMMAND>` can be any of the following.
Make sure to initialise the database before continuing.

- `init-db` create the default database from `schema.sql`
- `create-default-fridges` adds the fridges and sensors used by FQT. See `thermometry.flaskr.db.create_default_fridges` for a guide of how to add custom fridges using a python function. Alternatively run the following commands:
- `add-fridge <name>` adds a named fridge and returns the fridge ID
- `add-sensor <name> <fridge ID> <latest>` adds a named sensor to a given fridge. `latest` is a boolean flag of `0` or `1` if only the latest result should be recorded or if historic values should be kept. 
- `create-dummy-data` is an internal method used for testing the database with some fake data

Finally, everything is just postgresql.... you can simply edit the database if that is easier. I recommend pgAdmin for a graphical interface.

### Building the listener application
To build and deploy 




### Basic Schematic
A basic schematic of how the system works with multiple fridges is shown below. Note that the internal alert system is not shown.

![Schematic of the networking layout of the system](thermometry_layout.jpg)