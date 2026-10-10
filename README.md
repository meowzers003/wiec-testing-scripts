# DUNE WIEC Testing Scripts

Automated hardware characterization, quality control (QC), and instrument-control utilities for the **DUNE Warm Interface Electronics Crate (WIEC)**, including high-voltage (HV) crate testing and Warm Interface Board / Front-End Motherboard (WIB/FEMB) checkout.

> **Laboratory-use software.** This repository interfaces with energized electronics and high-voltage supplies. Only trained personnel should operate it, using the approved wiring, interlocks, operating limits, and local QC procedure. Do not treat example configuration values as authorization to energize hardware.

## Contents

- [Overview](#overview)
- [Implemented functionality](#implemented-functionality)
- [Repository guide](#repository-guide)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Operating the integrated QC sequence](#operating-the-integrated-qc-sequence)
- [Standalone HV crate testing](#standalone-hv-crate-testing)
- [Configuration](#configuration)
- [Test outputs and pass/fail tracking](#test-outputs-and-passfail-tracking)
- [Troubleshooting](#troubleshooting)
- [Safety and shutdown](#safety-and-shutdown)

## Overview

The scripts provide a Python-based framework for repeatable laboratory testing of the DUNE electronics infrastructure. The framework couples programmable supplies and measurement instruments with device-specific control, scripted electrical tests, configuration-driven thresholds, and retained QC records.

The **integrated entry point** is `wiec_qc.py`, which coordinates the selected stages and tracks whether each required stage completed successfully. The existing HV-crate characterization application, `dune_hv_crate_test.py`, can also be run independently.

### High-level sequence

```text
Operator inputs / config.json
            |
            v
       wiec_qc.py
            |
     Select test mode
       /     |     \
      C      W      B
      |      |      |
 HV crate  WIB/FEMB Both
      |      |      |
      |      +---- PTC initialization / power
      |      +---- WIB configuration / power
      |      +---- FEMB checkout
      |             |
      +------ HV crate QC / characterization
                    |
         Store stage pass/fail results
                    |
         Shutdown / close output log
```

The `B` mode runs the HV-crate stage **before** the WIB/FEMB stages. A failed required stage stops subsequent testing.

## Implemented functionality

| Area | Implemented capabilities | Main modules |
|---|---|---|
| Integrated workflow | Operator metadata entry, mode selection (`C`, `W`, `B`), ordered execution, pass/fail persistence, exception handling and final shutdown | `wiec_qc.py`, `wiec_crate_gui.py`, `wiec_output_log.py` |
| HV crate QC | Automated electrical characterization with configurable test limits, supply sequencing and measured data collection | `dune_hv_crate_test.py`, `hv_crate_characterization.py`, `hv_testing.py` |
| HV channel / filter checks | Configurable channel selection, voltage/current measurements, open/terminated RC-filter testing, time-constant and resistance parameters | `config.json`, `qc_utils.py`, HV test modules |
| ISEG / MPOD controls | HV supply/module control and dedicated electrical QC routines, including module-specific wrappers and validation scripts | `iseg_control.py`, `iseg_HV_electrical_test.py`, `iseg_pmod_qc.py`, `iseg_pmod_wrapper_QC.py`, `HVmodule/` |
| Low-voltage and PTC power | Controlled PL506 power-supply initialization, bounded voltage/current settings and readback, coordinated WIEC initialization and shutdown | `pl506.py`, `wiec_ptc_power.py`, `pl506_write_off.py` |
| WIB / FEMB checkout | WIB selection and power-state input, board setup, serial/network communications and subsequent FEMB checkout | `wiec_wib_setup.py`, `wiec_femb_checkout.py`, `wiec_serial.py`, `cts_ssh_FEMB.py` |
| Fans and thermal hardware | Fan supply/readback and dedicated fan-test routines; heater and temperature measurement interfaces | `new_fans_test.py`, `rigol_dp832a.py`, `keysight_daq970a.py` |
| Continuity / auxiliary debug | Standalone continuity and PetaLinux debugging tools, serial routines, plotting and device read/write checks | `wiec_continuity.py`, `wiec_petalinux_debug.py`, `just_plot.py`, `test_pl506_read.py`, `test_pl506_write.py` |
| Results and reporting | Central test-status JSON, test-specific output logs and QC result utilities | `results.json`, `wiec_output_log.py`, `qc_results.py`, `qc_utils.py` |

**Notes on scope:** Some modules are standalone diagnostics rather than stages automatically called by `wiec_qc.py`. A filename's presence does not mean that module runs in every QC mode. Refer to `steps_for_mode()` in `wiec_qc.py` for the authoritative integrated sequence.

## Repository guide

```text
wiec-testing-scripts/
├── wiec_qc.py                  # Integrated QC controller (recommended entry point)
├── wiec_crate_gui.py           # Interactive HV-crate wrapper and test naming
├── dune_hv_crate_test.py       # Standalone HV-crate characterization entry point
├── hv_crate_characterization.py
├── hv_testing.py
├── wiec_ptc_power.py           # PTC/WIEC power initialization + shutdown
├── wiec_wib_setup.py          # WIB configuration / power control
├── wiec_femb_checkout.py      # FEMB checkout
├── wiec_serial.py              # Serial communication helpers
├── wiec_output_log.py         # Test console logging
├── qc_results.py              # QC result management
├── qc_utils.py                # Shared QC utilities
├── iseg_control.py             # ISEG high-voltage control
├── iseg_pmod_qc.py             # ISEG/MPOD QC
├── iseg_pmod_wrapper_QC.py
├── iseg_HV_electrical_test.py
├── caen_r8033dm.py            # CAEN HV device interface
├── caen_r8033dm_wrapper.py
├── keysight_daq970a.py        # Keysight measurement instrument interface
├── rigol_dp832a.py            # Rigol power supply interface
├── pl506.py                   # PL506 power supply interface
├── new_fans_test.py           # Dedicated fan tests
├── wiec_continuity.py         # Continuity diagnostics
├── wiec_petalinux_debug.py    # Embedded system debug tools
├── cts_ssh_FEMB.py            # FEMB/SSH-related utility
├── config.json                # Equipment addresses + test parameters/limits
├── ip_addresses.json          # Network/device address settings
├── init_setup.csv             # Initial setup data
├── femb_info.csv              # FEMB metadata
├── femb_info_implement.csv    # FEMB metadata / implementation reference
├── results.json               # Persisted stage pass/fail status
├── requirements.txt           # Python dependencies
├── setup.sh                   # Virtual environment setup
├── GUI/                       # GUI-related files
├── HVmodule/                  # HV module support files
└── components/                # Supporting hardware/software components
```

This tree describes the major files, not every repository file.

## Requirements

### Host computer

- Linux-based laboratory machine with `python3`, `pip`, `venv`, and `git`.
- Working Ethernet/serial connections to the instruments and embedded targets that the selected mode requires.
- Permission to access the associated device nodes/network interfaces.
- Vendor libraries required by the selected CAEN/ISEG equipment.

The included `requirements.txt` specifies packages such as `PyVISA`, `PyVISA-py`, `openpyxl`, `psutil`, `pydantic`, and `tabulate`. Other imports and vendor-specific drivers may require additional installation on the laboratory host.

### Laboratory hardware (as applicable)

- DUNE WIEC crate, WIB and FEMB hardware under test.
- CAEN HV crate/supply interface and/or ISEG HV modules.
- PL506 supply, Rigol DP832A supplies, and Keysight DAQ970A data acquisition hardware.
- Relevant power, grounding, termination, Ethernet, serial, and measurement connections.
- Approved interlocks and independent emergency disconnects.

Not all instruments are used for every operating mode. Follow the approved bench wiring document for the actual configuration.

## Quick start

### 1. Obtain the code

```bash
git clone https://github.com/meowzers003/wiec-testing-scripts.git
cd wiec-testing-scripts
```

### 2. Set up Python

```bash
bash setup.sh
source venv/bin/activate
```

`setup.sh` creates `./venv`, activates it for the setup process, and installs `requirements.txt`. **Activation does not persist in your invoking terminal after running `bash setup.sh`**, so activate it explicitly afterward.

Alternatively:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

### 3. Check bench readiness and configuration

Before running a powered test:

1. Follow the lab's power-off wiring and continuity inspection procedure.
2. Confirm proper grounding, channel identification, connectors, loads, terminations, and any HV safety interlocks.
3. Check host network reachability and serial device availability **without enabling HV**.
4. Review `config.json` and `ip_addresses.json`. Verify that the instrument addresses match the actual bench equipment.
5. Confirm supply ranges, compliance/current limits, ramp values, channel lists, QC thresholds, and test duration against the approved procedure.
6. Verify that the designated test-output directory is writable and previous results have been archived if necessary.

**Never use the checked-in IP addresses or voltage thresholds without verifying them for the current test bench.**

### 4. Launch the integrated controller

```bash
python3 wiec_qc.py
```

At the prompts, provide:

- Version / run identifier.
- Tester name.
- Extra comments (required by the current prompt implementation).
- Configuration path (press Enter for the default `config.json`).
- Test mode: `C` = HV crate only; `W` = WIB/FEMB only; `B` = both.
- For `W`/`B`: the WIB number(s) and their requested `on` or `off` states.

Example interaction (illustrative, not test data):

```text
Enter version number: v3
Enter name of tester: operator
Enter extra comments from test user: bench_validation
Enter config file path [default: config.json]:
Are you testing HV crate only [C], WIB-FEMB only [W], or Both [B]: C
```

The program composes a run name from the version, tester name and comments, then executes the relevant stages.

### 5. Monitor results and verify shutdown

Observe terminal messages and instrument behavior throughout the run. Afterward:

- Check `results.json` for recorded stage states.
- Locate and archive the generated test log and any reports produced by the selected test modules.
- Review measured values, not just the high-level PASS/FAIL marker.
- Verify that all supplies are actually in their prescribed safe post-test state **at the hardware**.

**Do not assume that an exception-handling shutdown routine substitutes for electrical verification.**

## Operating the integrated QC sequence

The current `wiec_qc.py` implementation uses the following order:

| Mode | Sequence |
|---|---|
| `C` — crate only | `wiec_crate_gui.main()` (invokes HV-crate testing) |
| `W` — WIB/FEMB only | `wiec_ptc_power.initialize_wiec()` → `wiec_wib_setup.wib_power()` → `wiec_femb_checkout.main()` |
| `B` — both | HV crate test → PTC initialization → WIB setup/power → FEMB checkout |

Each required stage is dynamically imported and called. Its returned value is converted to `bool` and saved in `results.json` under the appropriate stage key. On a false result or an exception, the remaining stages are skipped and `full_wiec_test_sequence` is marked false. On full success the sequence is marked true.

The controller runs shutdown logic in a `finally` block, attempting `wiec_ptc_power.shutdown_wiec()` and `wiec_crate_gui.shutdown_dune_hv_crate_test()`, then stopping the output log. Errors in individual shutdown operations are printed; the operator must still verify the final electrical state.

> `results.json` contains persistent string values (`"True"` / `"False"`) rather than a complete database of measurement data. It can contain results from earlier runs for stages that are not exercised in the current mode; inspect the active run's log and stage selection before interpreting it.

## Standalone HV crate testing

For an HV crate test without the integrated controller:

```bash
python3 dune_hv_crate_test.py config.json
```

To supply an explicit test name:

```bash
python3 dune_hv_crate_test.py config.json example_hv_run
```

If the name is not supplied, the script requests one interactively. This is the existing repository's documented standalone invocation.

Use this route when validating only the HV crate or debugging the HV characterization pipeline. Separate support utilities should only be executed after checking their `__main__` entry points and hardware effects; do not assume every module is a safe independent command.

## Configuration

The repository's `config.json` centralizes instrument addressing, test selection and acceptance parameters, including examples of:

| Configuration field | Purpose |
|---|---|
| `channels_to_test` | HV channels to include in a test |
| `simultaneous_test` | Parallel/simultaneous test selection (represented as a string in the checked-in JSON) |
| `hv_minutes_duration_short`, `hv_seconds_interval` | Selected test timing parameters |
| `fan_wait`, `fan_voltage_min/max`, `fan_current_min/max` | Fan timing and acceptance bands |
| `heating_element_min/max`, `temp_increase_min/max` | Heater/temperature criteria |
| `hv_resistance_open_min/max`, `hv_resistance_term_min/max` | Electrical resistance acceptance bands |
| `hv_tau_min/max` | RC time-constant criteria |
| `rc_filter_ch0_3_*`, `rc_filter_ch4_7_*` | RC component models and tolerances by channel group |
| `rc_filter_termination_ohm` | Nominal termination value |
| `caenR8033DM`, `caenR8033DM_driver` | CAEN device address and wrapper-library choice |
| `keysight970a`, `keysight970a_*` | DAQ resource and measurement settings |
| `PL506_*` | Low-voltage supply settings, limits and readback parameters |

The checked-in configuration also contains explicit per-channel positive/negative mappings. Changes to wiring, channel positions or test thresholds must be reflected in the configuration and verified before operation.

### CAEN shared-library compatibility

The original repository README notes that `libcaenhvwrapper.so.6.6` may fail on certain Ubuntu installations due to `libcrypto.so.1.1`; versions **6.3** and **6.6** are included. Check the actual `caenR8033DM_driver` value in your local `config.json` and select a compatible, approved library. Do not install obsolete system crypto libraries indiscriminately.

## Test outputs and pass/fail tracking

- **Integrated stage status:** `results.json` is loaded and rewritten as required stages complete.
- **Console output capture:** `wiec_output_log.py` starts and stops logging around the integrated sequence.
- **Instrument measurements / QC data:** individual HV, fan, and other test modules manage their measurement records and report generation; their output format and location depend on the invoked routine and run name.
- **QC utilities:** `qc_results.py` and `qc_utils.py` support result handling and associated analysis.

For a reproducible QC record, retain the run identifier, tester, hardware serial numbers, date/time, configuration snapshot, raw measurements, result logs, and any observed failure or deviation. Store these according to the experiment's approved data retention protocol.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `ModuleNotFoundError` | Activate `venv`; verify `pip install -r requirements.txt`; check additional vendor-dependent imports. |
| VISA instrument not found | Confirm device power, connectivity, IP/subnet, configured resource name, and available VISA backend. |
| CAEN wrapper cannot load | Verify `.so` version, architecture, library dependencies, and `caenR8033DM_driver`. |
| Power supply fails initialization | Confirm bench wiring and interlocks; inspect PL506/Rigol settings and hardware state. Do not bypass limits. |
| WIB/FEMB communication fails | Check WIB number/state input, `ip_addresses.json`, serial ports, SSH access, boot state and PetaLinux/network connections. |
| QC stage fails without running later stages | This is expected fail-stop behavior in `wiec_qc.py`; consult the specific stage's trace/log before retrying. |
| Confusing historical PASS/FAIL entries | `results.json` persists between runs; correlate with the current run's log and the chosen operating mode. |
| Unexpected fan or RC result | Check relevant thresholds, physical loads/terminations, instrument connections, and stabilization/delay settings. |

## Safety and shutdown

HV testing can involve hazardous electrical energy. Use this code only with a bench that has been commissioned and approved for the test. The software's nominal setpoints, ramp rates and numerical acceptance bands do not replace hardware current limiting, physical interlocks or emergency power removal.

For a normal completed or interrupted run:

1. Observe the program's shutdown messages.
2. Confirm HV and auxiliary supplies are off or in the approved safe state using their physical indicators/readbacks.
3. Follow the lab's discharge, lockout and verification procedure before touching connections.
4. Preserve logs and record any discrepancy between software-reported and physically observed state.

## Maintenance notes

- **Use `wiec_qc.py` for full orchestrated testing** and `dune_hv_crate_test.py` for standalone HV-crate tests.
- Review stage boundaries before changing the execution order; WIB/FEMB steps depend on prior setup.
- Treat `config.json` as an experimental configuration requiring version control and review.
- Ensure new QC modules return a meaningful success/failure value if called through `run_required_step()`.
- Do not store live credentials or private network secrets in a public repository.
- The integrated controller currently stores boolean stage status; users needing immutable per-run manifests should extend the results structure rather than relying exclusively on `results.json`.

## Project context

Developed for testing and validation of electronics associated with the **Deep Underground Neutrino Experiment (DUNE)**. This repository is a laboratory QC and hardware-control codebase, not a general-purpose simulator or an independently certified hardware safety system.
