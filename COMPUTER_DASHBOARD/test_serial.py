import time
from serial_service import SerialService

print("================================")
print("   ALPINE MESH SERIAL TEST")
print("================================")

service = SerialService(
    port="COM11",
    baud_rate=115200
)

success, message = service.start()
print(message)

if success:
    print("\nWaiting for Master Node data...\n")

    try:
        start_time = time.time()

        while time.time() - start_time < 15:
            data = service.get_latest_message()

            if data:
                print("LIVE DATA RECEIVED:")
                print(data)
                print("----------------------------")

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("Test interrupted.")

    finally:
        service.stop()
        print("\nSerial connection closed.")

else:
    print("\nCould not connect.")
    print("Check that COM11 is correct and no other program is using it.")