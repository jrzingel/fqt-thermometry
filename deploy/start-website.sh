#!/bin/bash
#

echo "Starting Thermometry website"

cd /home/fqt/thermometry
source venv/bin/activate 

cd fqt-thermometry
python -u -m waitress --listen="*:80" --call "flaskr:create_app"

