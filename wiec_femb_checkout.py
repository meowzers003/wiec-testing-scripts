"""
CTS Checkout Script
Performs quick checkout test for FEMB boards in 4 slots.
Scans QR codes, runs checkout, provides result summary, and sends email notification.
"""

import os
import sys
import time
import csv
from datetime import datetime
from colorama import init, Fore, Style
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QC_PACKAGE_DIR = BASE_DIR

from qc_utils import QC_Process
from qc_results import analyze_test_results, display_qc_results



# Image paths for instruction popups
IMG_DIR = os.path.join(QC_PACKAGE_DIR, 'GUI', 'output_pngs')

init()

# Email configuration
SENDER_EMAIL = "bnlr216@gmail.com"
SENDER_PASSWORD = "vvef tosp minf wwhf"

CSV_FILE = os.path.join(QC_PACKAGE_DIR, 'femb_info.csv')
INIT_SETUP_CSV = os.path.join(QC_PACKAGE_DIR, 'init_setup.csv')
RESULTS_FILE = os.path.join(BASE_DIR, 'results.json')



def read_init_setup():
    """Read configuration from init_setup.csv"""
    config = {}
    with open(INIT_SETUP_CSV, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) == 2:
                key, value = row
                config[key.strip()] = value.strip()
    return config


def print_header(title):
    """Print a formatted header"""
    print("\n" + Fore.CYAN + "=" * 70)
    print(f"  {title.upper()}")
    print("=" * 70 + Style.RESET_ALL + "\n")


def print_step(step_num, total, description):
    """Print a formatted step"""
    print(Fore.CYAN + f"[{step_num}/{total}] {description}" + Style.RESET_ALL)


def print_status(status_type, message):
    """Print status message with icon"""
    icons = {
        'success': ('✓', Fore.GREEN),
        'error': ('✗', Fore.RED),
        'warning': ('⚠', Fore.YELLOW),
        'info': ('ℹ', Fore.CYAN)
    }
    icon, color = icons.get(status_type, ('•', Fore.WHITE))
    print(color + f"{icon} {message}" + Style.RESET_ALL)


def save_config(tester_name, tester_email, femb_ids, init_config):
    """Save configuration to CSV file with all fields matching femb_info_implement.csv"""
    if isinstance(femb_ids, list):
        femb_ids = {f"SLOT{idx}": femb_id for idx, femb_id in enumerate(femb_ids[:4])}
    elif not isinstance(femb_ids, dict):
        femb_ids = {}

    csv_data = {
        # User input
        'tester': tester_name,
        'SLOT0': femb_ids.get('SLOT0', ''),
        'SLOT1': femb_ids.get('SLOT1', ''),
        'SLOT2': femb_ids.get('SLOT2', ''),
        'SLOT3': femb_ids.get('SLOT3', ''),
        'comment': 'Checkout test',
        # From init_setup.csv with defaults
        'test_site': init_config.get('Test_Site', 'BNL'),
        'toy_TPC': init_config.get('toy_TPC', 'y'),
        'top_path': init_config.get('QC_data_root_folder', '/home/dune/Documents/data'),
        'Tech_site_email': tester_email or init_config.get('Tech_site_email', ''),
        'Tech_receiver': init_config.get('Tech_receiver', 'lke@bnl.gov'),
        'Test_Site': init_config.get('Test_Site', 'BNL'),
        'Tech_Coordinator': init_config.get('Tech_Coordinator', ''),
        'QC_data_root_folder': init_config.get('QC_data_root_folder', '/home/dune/Documents/data'),
        'Rigol_PS_for_WIB': init_config.get('Rigol_PS_for_WIB', 'True'),
        'Rigol_PS_ID': init_config.get('Rigol_PS_ID', ''),
        'CTS_LN2_AM': init_config.get('CTS_LN2_AM', '1800'),
        'CTS_LN2_PM': init_config.get('CTS_LN2_PM', '1200'),
        'PS_Control_Mode': init_config.get('PS_Control_Mode', 'USB'),
        'CTS_LN2_Fill_Wait': init_config.get('CTS_LN2_Fill_Wait', '1800'),
        'CTS_Warmup_Wait': init_config.get('CTS_Warmup_Wait', '3600'),
        'Network_Upload_Path': init_config.get('Network_Upload_Path', '/data/femb/FEMB_CHK'),
    }

    # Ensure directory exists
    os.makedirs(os.path.dirname(CSV_FILE), exist_ok=True)

    with open(CSV_FILE, mode="w", newline="", encoding='utf-8-sig') as file:
        writer = csv.writer(file)
        for key, value in csv_data.items():
            writer.writerow([key, value])
        print(csv_data)

    return csv_data


def run_checkout_test(inform):
    """
    Run the checkout test for all installed FEMBs.
    Returns paths to data and report directories.
    """
    print_header("Running Checkout Test")

    # Step 2: Wait for fiber converter
    print_step(2, 4, "Waiting for Fiber Converter")
    print(Fore.YELLOW + "Waiting 30 seconds for fiber converter..." + Style.RESET_ALL)
    for i in range(30, 0, -1):
        print(f"\r  Countdown: {Fore.GREEN}{i:2d}s{Style.RESET_ALL}", end="", flush=True)
        time.sleep(1)
    print(f"\r  {Fore.GREEN}✓ Fiber converter ready!{' '*20}{Style.RESET_ALL}")

    # Step 3: Initialize WIB
    print_step(3, 4, "Initializing WIB")
    qc_path = inform['QC_data_root_folder']
    QC_Process(path=qc_path, QC_TST_EN=77, input_info=inform)  # Ping WIB
    QC_Process(path=qc_path, QC_TST_EN=0, input_info=inform)   # Init WIB
    QC_Process(path=qc_path, QC_TST_EN=1, input_info=inform)   # Init FEMB I2C

    # Step 4: Run checkout test
    print_step(4, 4, "Running Assembly Checkout Test")
    data_path, report_path = QC_Process(path=qc_path, QC_TST_EN=2, input_info=inform)  # Checkout

    return data_path, report_path


def generate_result_summary(inform, data_path, report_path):
    """
    Generate test result summary for all slots.
    Returns (all_passed, summary_text, slot_results)
    """
    print_header("Test Results Summary")

    paths = []
    if data_path:
        paths.append(data_path)
    if report_path:
        paths.append(report_path)

    # Analyze results
    result = analyze_test_results(paths, inform)
    all_passed, failed_slots = display_qc_results(result, "Checkout Test", verbose=True)

    # Build summary text for email
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary_lines = [
        "=" * 60,
        "CTS FEMB CHECKOUT TEST RESULTS",
        "=" * 60,
        f"Date/Time: {timestamp}",
        f"Tester: {inform.get('tester', 'Unknown')}",
        f"Test Site: {inform.get('test_site', 'BNL')}",
        "",
        "-" * 60,
        "SLOT RESULTS:",
        "-" * 60,
    ]

    slot_results = {}
    for slot_num in ['0', '1', '2', '3']:
        slot_key = f'SLOT{slot_num}'
        display_slot = int(slot_num) + 1
        femb_id = inform.get(slot_key, '')

        if not femb_id or femb_id in ['', ' ', 'N/A', 'EMPTY', 'NONE']:
            summary_lines.append(f"  Slot {display_slot}: Empty (skipped)")
            slot_results[slot_num] = ('empty', '')
            continue

        if slot_num in result.slot_status:
            passed, _ = result.slot_status[slot_num]
            status = "PASS" if passed else "FAIL"
            summary_lines.append(f"  Slot {display_slot} ({femb_id}): {status}")
            slot_results[slot_num] = ('pass' if passed else 'fail', femb_id)
        else:
            summary_lines.append(f"  Slot {display_slot} ({femb_id}): No test data")
            slot_results[slot_num] = ('no_data', femb_id)

    summary_lines.extend([
        "",
        "-" * 60,
        f"OVERALL RESULT: {'PASS' if all_passed else 'FAIL'}",
        "-" * 60,
    ])

    if not all_passed:
        summary_lines.append("\nFailed FEMBs requiring attention:")
        for slot_num, femb_id in failed_slots:
            display_slot = int(slot_num) + 1
            summary_lines.append(f"  - Slot {display_slot}: {femb_id}")

    summary_text = "\n".join(summary_lines)
    return all_passed, summary_text, slot_results


# def send_result_email(tester_email, all_passed, summary_text, inform):
#     """Send email notification with test results to tester and tech receiver"""
#     print_header("Sending Email Notification")
#     # Build recipient list
#     recipients = []
#     if tester_email and '@' in tester_email:
#         recipients.append(tester_email)
#     tech_receiver = inform.get('Tech_receiver', 'lke@bnl.gov')
#     if tech_receiver and '@' in tech_receiver and tech_receiver not in recipients:
#         recipients.append(tech_receiver)
#     if not recipients:
#         print_status('warning', "No valid email recipients. Skipping email notification.")
#         return False
#     status_str = "PASS" if all_passed else "FAIL"
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
#     test_site = inform.get('test_site', 'BNL')
#     subject = f"[CTS Checkout {status_str}] {test_site} - {timestamp}"
#     body = f"""CTS FEMB Checkout Test Completed
# {summary_text}

# ---
# This is an automated message from the FEMB Post-Assembly Checkout System.
# """

#     try:
#         send_email.send_email(
#             SENDER_EMAIL,
#             SENDER_PASSWORD,
#             recipients,
#             subject,
#             body
#         )
#         print_status('success', f"Email sent to: {', '.join(recipients)}")
#         return True
#     except Exception as email_err:
#         print_status('error', f"Failed to send email: {email_err}")
#         return False

# Function 01 CSV Read
def read_csv_to_dict(filename, env, p=False):
    data = {}
    with open(filename, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        # headers = next(reader)
        for row in reader:
            if len(row) >= 2:
                key = row[0]
                if row[1] == '':
                    row[1] = ' '
                value = row[1]
                data[key] = value
            if p:
                print("\033[96m" + key + "\t\t:\t\t" + data[key] + "\033[0m")
    if env == 'LN':
        data['env'] = 'y'
        if p:
            print("\033[96m" + 'environment' + "\t:\t\t" + data['env'] + '(Cold)' + "\033[0m")
    else:
        data['env'] = 'n'
        if p:
            print("\033[96m" + 'environment' + "\t:\t\t" + data['env'] + '(Warm)' + "\033[0m")
    return data


def main():
    """Main checkout workflow"""
    print_header("CTS FEMB Checkout Test")
    print(Fore.GREEN + "This script performs a quick checkout test for FEMB boards." + Style.RESET_ALL)
    print(Fore.GREEN + "Supports 4 slots. Empty slots will be skipped.\n" + Style.RESET_ALL)

    # # Step 1: Get tester information
    # # Show Page 2: Tester information instruction
    # print_step(1, 5, "Tester Information")
    # tester_name = input(Fore.CYAN + "  Enter your name: " + Style.RESET_ALL).strip()
    # if not tester_name:
    #     tester_name = "Unknown"

    # tester_email = SENDER_EMAIL

    # # Show Page 1: Test site setup instruction
    # pop.show_image_popup(
    #     title="Page 1: Check the Test Site",
    #     image_path=os.path.join(IMG_DIR, "1.png")
    # )
    # pop.show_image_popup(
    #     title="Page 2: ESD Preparation",
    #     image_path=os.path.join(IMG_DIR, "2.png")
    # )
    # # Step 2: Scan FEMB QR codes
    # # Show Page 3: Open shielding box cover
    # pop.show_image_popup(
    #     title="Page 3: Open the Cover of the Shielding Box",
    #     image_path=os.path.join(IMG_DIR, "3.png")
    # )
    # print_step(2, 5, "Scanning FEMB QR Codes")
    # femb_ids = scan_femb_qr_codes()
    # 
    # # Check if any FEMB installed
    # installed_fembs = [k for k, v in femb_ids.items() if v]
    # if not installed_fembs:
    #     print_status('error', "No FEMBs installed. Exiting.")
    #     sys.exit(1)

    # # Step 3: Review and confirm
    # print_step(3, 5, "Configuration Review")
    # print(Fore.GREEN + "\nPlease review the configuration:" + Style.RESET_ALL)
    # print(f"  Tester: {tester_name}")
    # for slot_key in ['SLOT0', 'SLOT1', 'SLOT2', 'SLOT3']:
    #     femb_id = femb_ids.get(slot_key, '')
    #     status = femb_id if femb_id else "Empty"
    #     print(f"  {slot_key}: {status}")

    confirm = input(Fore.YELLOW + "\nProceed with checkout test? (y/n): " + Style.RESET_ALL).lower()
    if confirm != 'y':
        print_status('info', "Test cancelled by user.")
        sys.exit(0)

    # # Show Page 8: Close cover and start test
    # pop.show_image_popup(
    #     title="Page 8: Review Information and Close Cover",
    #     image_path=os.path.join(IMG_DIR, "8.png")
    # )
    while True:
        print(Fore.YELLOW + "\n⚠️  SAFETY CHECK:" + Style.RESET_ALL)
        print("Please confirm the CTS chamber is empty.")
        print("Type " + Fore.GREEN + "'I confirm the cover is closed'" + Style.RESET_ALL + " to proceed")
        com = input(Fore.YELLOW + '>> ' + Style.RESET_ALL)
        if com.lower() == 'i confirm the cover is closed':
            print(
                Fore.GREEN + '✓ Ready for Test.' + Style.RESET_ALL)
            break
    # Read init_setup.csv for configuration
    init_config = read_init_setup()

    # Save configuration with all fields matching femb_info_implement.csv
    info = None
    with open(RESULTS_FILE, "r") as jsonfile:
        info = json.load(jsonfile)  

    tester_name = info.get("tester_name", "Unknown")
    tester_email = info.get("tester_email", "Unknown")
    femb_ids = info.get("femb_ids", {})
    save_config(tester_name, tester_email, femb_ids, init_config)
    inform = read_csv_to_dict(CSV_FILE, 'RT')

    
    # Step 4: Run checkout test
    print_step(4, 5, "Running Checkout Test")
    data_path, report_path = run_checkout_test(inform)

        # Step 5: Generate results 
    print_step(5, 6, "Generating Results ")
    all_passed, summary_text, slot_results = generate_result_summary(inform, data_path, report_path)    
    print("---------------------------------------------------------")
    print("Summary Test")
    print("-------------")
    print(summary_text)
    print("---------------------------------------------------------")
    print("---------------------------------------------------------")
    print_header("Checkout Test Complete")
    if all_passed:
        print(Fore.GREEN + "  ✓✓✓ ALL TESTS PASSED ✓✓✓" + Style.RESET_ALL)
    else:
        print(Fore.RED + "  ✗✗✗ SOME TESTS FAILED ✗✗✗" + Style.RESET_ALL)
        print(Fore.YELLOW + "\n  Please check the failed FEMBs and take appropriate action." + Style.RESET_ALL)
        print_status('success', "Power supply turned OFF and connection closed.")
    
    return True if all_passed else False
    

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\nTest interrupted by user." + Style.RESET_ALL)
        sys.exit(1)
    except Exception as e:
        print(Fore.RED + f"\nError: {e}" + Style.RESET_ALL)
        sys.exit(1)
