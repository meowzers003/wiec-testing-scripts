# WIEC QC 

run program below and follow user input prompts 

`python3 wiec_qc.py `


# DUNE-HV-Crate-Testing
Automated production testing for DUNE HV Crate

Navigate to the simulation directory and use

`./setup.sh`

Which should set up the virtual environment and the require Python packages. Then edit the `config.json` file for your preferences.

Run like:

`python3 dune_hv_crate_test.py config.json`

The script will ask you to name the test once it starts. Alternatively you can just put the name in the command, like:

`python3 dune_hv_crate_test.py config.json name_of_test`


### CAEN HV Wrapper library version
At least in some versions of Ubuntu, using the latest available version of libcaenhvwrapper, 6.6, causes an error when it tries to open libcrypto.so.1.1, so the version in config.json is set be default to `libcaenhvwrapper.so.6.3`. Both versions are included in the repository. If you experience a communication issue, try setting `caenR8033DM_driver` to `libcaenhvwrapper.so.6.6`. Some suggestions for solving the libcrypto.so.1.1 issue are [here](https://stackoverflow.com/a/72507864).
