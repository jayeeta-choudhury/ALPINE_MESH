import time
import random

from serial_service import SerialService


# ==============================================
# ALPINE MESH - MULTI TREKKER SIMULATOR
# ==============================================

NODE_IDS = [
    "TREKKER_01",
    "TREKKER_02",
    "TREKKER_03"
]

REPORT_INTERVAL = 5

service = SerialService()


def generate_telemetry(node_id):

    telemetry = {
        "node_id": node_id,
        "role": "TREKKER",
        "status": "ONLINE",

        "battery": random.randint(65, 100),

        "location_zone": random.choice([
            "ZONE_01",
            "ZONE_02",
            "ZONE_03"
        ]),

        "temperature": round(
            random.uniform(18.0, 30.0), 1
        ),

        "heart_rate": random.randint(65, 100),

        "spo2": random.randint(95, 99),

        "fall_detected": False,

        "uptime_ms": int(time.monotonic() * 1000),

        "data_mode": "SIMULATED"
    }

    return telemetry


def main():

    print("=" * 55)
    print("       ALPINE MESH MULTI-TREKKER SIMULATOR")
    print("=" * 55)

    print("Registered test nodes:")

    for node_id in NODE_IDS:
        print(f" - {node_id}")

    print("\nReporting interval:", REPORT_INTERVAL, "seconds")
    print("Database: alpine_mesh_telemetry.db")
    print("Data mode: SIMULATED")

    print("=" * 55)

    packet_number = 0

    try:

        while True:

            for node_id in NODE_IDS:

                packet_number += 1

                telemetry = generate_telemetry(node_id)

                success = service.save_external_message(
                    telemetry
                )

                if success:

                    print(
                        f"\nPACKET #{packet_number} SAVED"
                    )

                    print(
                        f"Node: {node_id}"
                    )

                    print(
                        f"Battery: {telemetry['battery']}%"
                    )

                    print(
                        f"Zone: {telemetry['location_zone']}"
                    )

                    print(
                        f"Temperature: "
                        f"{telemetry['temperature']} C"
                    )

                    print(
                        f"Heart Rate: "
                        f"{telemetry['heart_rate']} bpm"
                    )

                    print(
                        f"SpO2: {telemetry['spo2']}%"
                    )

                else:

                    print(
                        f"ERROR: Could not save {node_id}"
                    )

            print("\nAll Trekker Nodes reported.")

            time.sleep(REPORT_INTERVAL)

    except KeyboardInterrupt:

        print("\nMulti-Trekker simulator stopped.")

    finally:

        service.stop()


if __name__ == "__main__":
    main()