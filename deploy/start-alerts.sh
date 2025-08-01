#!/bin/bash
#

echo "Starting thermometry alerts"

cd /home/fqt/thermometry
source venv/bin/activate 

cd fqt-thermometry/alarm
python -u Watchtower.py

