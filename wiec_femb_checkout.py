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

from BNL_CE_WIB_SW_QC import cts_ssh_FEMB as cts

from BNL_CE_WIB_SW_QC.GUI import send_email
from BNL_CE_WIB_SW_QC.GUI import Rigol_DP800 as rigol
from BNL_CE_WIB_SW_QC.GUI import pop_window as pop

from BNL_CE_WIB_SW_QC.qc_utils import QC_Process
from BNL_CE_WIB_SW_QC.qc_results import analyze_test_results, display_qc_results



# Image paths for instruction popups
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'GUI', 'output_pngs')

init()

# Email configuration
SENDER_EMAIL = "bnlr216@gmail.com"
SENDER_PASSWORD = "vvef tosp minf wwhf"

CSV_FILE = './femb_info.csv'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INIT_SETUP_CSV = os.path.join(BASE_DIR, 'init_setup.csv')



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


def scan_femb_qr_codes():
    """
    Scan QR codes for all 4 FEMB slots.
    Returns a dictionary with slot assignments.
    """
    print_header("FEMB QR Code Scanning")
    print(Fore.YELLOW + "Scan the QR code for each FEMB board in the popup window." + Style.RESET_ALL)
    print(Fore.YELLOW + "Click 'Skip' or press Enter with empty field to skip empty slots.\n" + Style.RESET_ALL)

    femb_ids = {}
    # slot_key, display_name, image_file
    slot_names = [
        ("SLOT0", "Slot #1", "4.png"),
        ("SLOT1", "Slot #2", "5.png"),
        ("SLOT2", "Slot #3", "6.png"),
        ("SLOT3", "Slot #4", "7.png")
    ]

    for slot_key, slot_desc, img_file in slot_names:
        # Show installation instruction popup with QR input field
        slot_num = int(slot_key[-1]) + 1
        femb_id = pop.show_input_popup(
            title=f"Page {slot_num + 3}: Install FEMB into {slot_desc}",
            image_path=os.path.join(IMG_DIR, img_file),
            prompt=f"Scan FEMB QR Code for {slot_desc}:",
            require_confirmation=True
        )

        femb_ids[slot_key] = femb_id
        if femb_id:
            print_status('success', f"{slot_desc}: {femb_id}")
        else:
            print_status('info', f"{slot_desc}: Empty (skipped)")

    # Summary
    print("\n" + Fore.CYAN + "-" * 50 + Style.RESET_ALL)
    print(Fore.GREEN + "FEMB Assignment Summary:" + Style.RESET_ALL)
    installed_count = 0
    for slot_key, slot_desc, _ in slot_names:
        femb_id = femb_ids.get(slot_key, "")
        if femb_id:
            print(f"  {slot_desc}: {Fore.GREEN}{femb_id}{Style.RESET_ALL}")
            installed_count += 1
        else:
            print(f"  {slot_desc}: {Fore.YELLOW}Empty{Style.RESET_ALL}")

    print(f"\nTotal FEMBs installed: {Fore.GREEN}{installed_count}{Style.RESET_ALL}")

    return femb_ids


def save_config(tester_name, tester_email, femb_ids, init_config):
    """Save configuration to CSV file with all fields matching femb_info_implement.csv"""
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


def run_checkout_test(inform, psu):
    """
    Run the checkout test for all installed FEMBs.
    Returns paths to data and report directories.
    """
    print_header("Running Checkout Test")

    # Step 1: Power ON WIB via USB-controlled power supply
    print_step(1, 4, "Power On Warm Interface Board")
    print_status('info', "Powering ON WIB via USB power supply...")
    psu.set_channel(1, 12.0, 3.0, on=True)
    psu.set_channel(2, 12.0, 3.0, on=True)
    print_status('success', "WIB power ON (CH1: 12V/3A, CH2: 12V/3A)")

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


def process_board_removal(inform, slot_results):
    """
    Guide tester through removing each board slot by slot.
    Requires QR scan confirmation before removal.
    Uses popup window with image, result display, and QR scan field.
    """
    print_header("Board Removal Process")
    print(Fore.YELLOW + "Remove boards one by one. Scan QR code to confirm each board." + Style.RESET_ALL)
    print(Fore.YELLOW + "PASS -> GOOD tray | FAIL -> BAD tray\n" + Style.RESET_ALL)

    # slot_num, display_name, image_file
    slot_names = [
        ("0", "Slot #1", "10.png"),
        ("1", "Slot #2", "11.png"),
        ("2", "Slot #3", "12.png"),
        ("3", "Slot #4", "13.png")
    ]

    for slot_num, slot_desc, img_file in slot_names:
        slot_key = f'SLOT{slot_num}'
        expected_id = inform.get(slot_key, '')

        # Skip empty slots
        if not expected_id or expected_id in ['', ' ', 'N/A', 'EMPTY', 'NONE']:
            print(Fore.CYAN + f"\n[{slot_desc}] " + Fore.YELLOW + "Empty - Skip" + Style.RESET_ALL)
            continue

        # Get test result for this slot
        status, _ = slot_results.get(slot_num, ('no_data', ''))

        # Determine tray info for logging
        if status == 'pass':
            tray_name = "GOOD"
            tray_style = Fore.GREEN
        elif status == 'fail':
            tray_name = "BAD"
            tray_style = Fore.RED
        else:
            tray_name = "REVIEW"
            tray_style = Fore.YELLOW

        # Show combined removal popup with image, result, and QR scan
        display_slot = int(slot_num) + 1
        confirmed = pop.show_removal_popup(
            title=f"Page {display_slot + 9}: Remove Board from {slot_desc}",
            image_path=os.path.join(IMG_DIR, img_file),
            expected_id=expected_id,
            test_status=status
        )

        # Log result to terminal
        print("\n" + Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(Fore.CYAN + f"  {slot_desc}" + Style.RESET_ALL)
        print(Fore.CYAN + "=" * 60 + Style.RESET_ALL)
        print(f"  FEMB ID: {Fore.WHITE}{expected_id}{Style.RESET_ALL}")
        print(f"  Test Result: {tray_style}{status.upper()}{Style.RESET_ALL}")

        if confirmed:
            print_status('success', f"ID confirmed. FEMB removed and placed in {tray_name} tray.")
        else:
            print_status('warning', f"Removal cancelled for {slot_desc}.")

    print("\n" + Fore.GREEN + "=" * 60)
    print("  All boards processed!")
    print("=" * 60 + Style.RESET_ALL)


def send_result_email(tester_email, all_passed, summary_text, inform):
    """Send email notification with test results to tester and tech receiver"""
    print_header("Sending Email Notification")
    # Build recipient list
    recipients = []
    if tester_email and '@' in tester_email:
        recipients.append(tester_email)
    tech_receiver = inform.get('Tech_receiver', 'lke@bnl.gov')
    if tech_receiver and '@' in tech_receiver and tech_receiver not in recipients:
        recipients.append(tech_receiver)
    if not recipients:
        print_status('warning', "No valid email recipients. Skipping email notification.")
        return False
    status_str = "PASS" if all_passed else "FAIL"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    test_site = inform.get('test_site', 'BNL')
    subject = f"[CTS Checkout {status_str}] {test_site} - {timestamp}"
    body = f"""CTS FEMB Checkout Test Completed
{summary_text}

---
This is an automated message from the FEMB Post-Assembly Checkout System.
"""

    try:
        send_email.send_email(
            SENDER_EMAIL,
            SENDER_PASSWORD,
            recipients,
            subject,
            body
        )
        print_status('success', f"Email sent to: {', '.join(recipients)}")
        return True
    except Exception as email_err:
        print_status('error', f"Failed to send email: {email_err}")
        return False


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
    with open('results.json', "r") as jsonfile:
        info = json.load(jsonfile)  

    tester_name = info.get("tester_name", "Unknown")
    tester_email = info.get("tester_email", "Unknown")
    femb_ids = info.get("femb_ids", ["0", "1", "2", "3"])
    save_config(tester_name, tester_email, femb_ids, init_config)
    inform = cts.read_csv_to_dict(CSV_FILE, 'RT')

    # Initialize power supply controller
    print_status('info', "Initializing power supply controller...")
    psu = rigol.PowerSupplyController()

    try:
        # Step 4: Run checkout test
        print_step(4, 5, "Running Checkout Test")
        data_path, report_path = run_checkout_test(inform, psu)

        # Step 5: Generate results 
        print_step(5, 6, "Generating Results ")
        all_passed, summary_text, slot_results = generate_result_summary(inform, data_path, report_path)
        # send_result_email(tester_email, all_passed, summary_text, inform)
        print_status('info', "Turning OFF power supply...")
        psu.close()
        # # Show Page 9: Open cover for board removal
        # pop.show_image_popup(
        #     title="Page 9: Review Result and Open Cover",
        #     image_path=os.path.join(IMG_DIR, "9.png")
        # )

        # # Step 6: Board removal with QR confirmation
        # print_step(6, 6, "Board Removal")
        # process_board_removal(inform, slot_results)

        # # Show Page 14: Clean the test site
        # pop.show_image_popup(
        #     title="Page 14: Clean the Test Site",
        #     image_path=os.path.join(IMG_DIR, "14.png")
        # )

        # Final summary display

        print_header("Checkout Test Complete")
        if all_passed:
            print(Fore.GREEN + "  ✓✓✓ ALL TESTS PASSED ✓✓✓" + Style.RESET_ALL)
        else:
            print(Fore.RED + "  ✗✗✗ SOME TESTS FAILED ✗✗✗" + Style.RESET_ALL)
            print(Fore.YELLOW + "\n  Please check the failed FEMBs and take appropriate action." + Style.RESET_ALL)
        print_status('success', "Power supply turned OFF and connection closed.")
        return True if all_passed else False

    finally:
        # Always turn off power supply, even on exceptions
        input(Fore.CYAN + "  Press Enter to next" + Style.RESET_ALL)
        print(Fore.CYAN + "  Press Enter 'exit' in terminal line to quit..." + Style.RESET_ALL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n\nTest interrupted by user." + Style.RESET_ALL)
        sys.exit(1)
    except Exception as e:
        print(Fore.RED + f"\nError: {e}" + Style.RESET_ALL)
        sys.exit(1)
