import serial
import json
import time

from data_manager import DataManager


# SERIAL CONFIGURATION
SERIAL_PORT = "COM11"  # Change if your board uses another port
BAUD_RATE = 115200


# INITIALIZE DATA MANAGER
manager = DataManager()


print("================================")
print("     ALPINE MESH DASHBOARD")
print("================================")

print("Connecting to Master Node...")

esp32 = None

try:
    # Connect to ESP32
    esp32 = serial.Serial(
        port=SERIAL_PORT,
        baudrate=BAUD_RATE,
        timeout=2
    )

    time.sleep(2)

    print("Master Node connected!")
    print("Listening for incoming data...")
    print("--------------------------------")

    while True:

        line = esp32.readline().decode(
            "utf-8",
            errors="replace"
        ).strip()

        if not line:
            continue

        # Process incoming JSON
        success, result = manager.process_message(line)

        if success:

            print("\nMASTER NODE DATA:")
            print(json.dumps(result, indent=4))

            print("\nDATA STATISTICS:")
            print(json.dumps(
                manager.get_statistics(),
                indent=4
            ))

            print("--------------------------------")

        else:
            print("Invalid message:", result)


except serial.SerialException as error:
    print("Serial connection error:", error)

except KeyboardInterrupt:
    print("\nALPINE MESH reader stopped.")

finally:
    if esp32 is not None and esp32.is_open:
        esp32.close()
        print("Serial connection closed.")