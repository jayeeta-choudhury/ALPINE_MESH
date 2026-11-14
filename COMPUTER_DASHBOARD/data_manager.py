import json
from datetime import datetime
from collections import deque


class DataManager:
    def __init__(self):
        self.latest_data = {}
        self.message_history = deque(maxlen=100)
        self.valid_messages = 0
        self.invalid_messages = 0

    def process_message(self, raw_message):
        """Convert incoming JSON text into structured data."""

        try:
            data = json.loads(raw_message)

            if not isinstance(data, dict):
                raise ValueError("Message must be a JSON object")

            data["received_at"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            self.latest_data = data
            self.message_history.append(data.copy())
            self.valid_messages += 1

            return True, data

        except (json.JSONDecodeError, ValueError) as error:
            self.invalid_messages += 1
            return False, str(error)

    def get_latest_data(self):
        return self.latest_data

    def get_message_history(self):
        return list(self.message_history)

    def get_statistics(self):
        return {
            "valid_messages": self.valid_messages,
            "invalid_messages": self.invalid_messages,
            "stored_messages": len(self.message_history)
        }


# Test the Data Manager independently
if __name__ == "__main__":

    manager = DataManager()

    test_message = (
        '{"node_id":"MASTER_01",'
        '"role":"MASTER",'
        '"status":"ONLINE",'
        '"uptime_ms":141600,'
        '"esp_now":"NOT_CONNECTED",'
        '"lora":"STANDBY"}'
    )

    success, result = manager.process_message(test_message)

    print("================================")
    print(" ALPINE MESH DATA MANAGER TEST")
    print("================================")

    if success:
        print("\nMessage received successfully!")
        print(json.dumps(result, indent=4))
    else:
        print("\nMessage error:", result)

    print("\nStatistics:")
    print(json.dumps(manager.get_statistics(), indent=4))