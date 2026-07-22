#!/bin/bash
echo "DUNE HV Crate testing --> Setting up virtual Python environment"
python3 -m venv ./venv
echo "DUNE HV Crate testing --> Python venv setup"
source venv/bin/activate
echo "DUNE HV Crate testing --> Inside Python venv"
pip install -r requirements.txt
echo "DUNE HV Crate testing --> Python packages installed"
