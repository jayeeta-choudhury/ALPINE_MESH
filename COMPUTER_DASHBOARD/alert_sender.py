import serial
import json
import time
import uuid

from streamlit import connection

SERIAL_PORT = "COM11"
BAUD_RATE = 115200
ACK_TIMEOUT = 10


def send_alert():
    print("\n===== ALPINE MESH ALERT SENDER =====")

    print("1. LANDSLIDE")
    print("2. ACCIDENT")

    choice = input("\nSelect alert type: ").strip()

    if choice == "1":
        event_type = "LANDSLIDE"
    elif choice == "2":
        event_type = "ACCIDENT"
    else:
        print("Invalid selection.")
        return

    print("\nSelect severity:")
    print("1. CRITICAL")
    print("2. HIGH")
    print("3. MEDIUM")

    severity_choice = input("Enter choice: ").strip()

    severity_map = {
        "1": "CRITICAL",
        "2": "HIGH",
        "3": "MEDIUM"
    }

    if severity_choice not in severity_map:
        print("Invalid severity.")
        return

    severity = severity_map[severity_choice]
    event_id = "ALP-" + uuid.uuid4().hex[:8].upper()

    command = f"ALERT|{event_type}|{severity}|{event_id}\n"

    print("\nPreparing alert...")
    print("Event:", event_type)
    print("Severity:", severity)
    print("Event ID:", event_id)

    try:
        connection = serial.Serial(port=None)
        connection.port = SERIAL_PORT
        connection.baudrate = BAUD_RATE
        connection.timeout = 0.5
        connection.write_timeout = 2
        connection.dtr = False
        connection.rts = False

        connection.open()

        try:

            time.sleep(2)
            connection.reset_input_buffer()

            print("\nSending alert to Master Node...")
            connection.write(command.encode("utf-8"))
            connection.flush()

            print("Waiting for Master acknowledgement...")

            start_time = time.time()

            while time.time() - start_time < ACK_TIMEOUT:
                line = connection.readline().decode(
                    "utf-8", errors="replace"
                ).strip()

                if not line:
                    continue

                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if (
                    message.get("event") == "ALERT_ACK"
                    and message.get("event_id") == event_id
                ):
                    print("\nMASTER ACKNOWLEDGEMENT RECEIVED")
                    print("Status:", message.get("status"))
                    print("Event ID:", event_id)
                    return

                if message.get("event") == "COMMAND_ERROR":
                    print("Master reported a command error:", message)
                    return

            print("\nNo acknowledgement received.")
            print("Check the Master firmware and USB connection.")
        finally:
            if connection.is_open:
                 connection.close()
    except serial.SerialException as error:
        print("\nSerial connection error:", error)
        print("Make sure the dashboard and Serial Monitor are closed.")


if __name__ == "__main__":
    send_alert()