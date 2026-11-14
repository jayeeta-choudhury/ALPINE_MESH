import csv
import io
import serial
import threading
import json
import time
import sqlite3
import uuid

from collections import deque


class SerialService:

    def __init__(
        self,
        port="COM11",
        baud_rate=115200,
        history_limit=500,
        database_path="alpine_mesh_telemetry.db"
    ):
        self.port = port
        self.baud_rate = baud_rate
        self.database_path = database_path

        self.connection = None
        self.reader_thread = None

        self.running = False
        self.connected = False

        self.history = deque(maxlen=history_limit)

        self.valid_messages = 0
        self.invalid_messages = 0
        self.storage_errors = 0

        self.last_error = None

        self.lock = threading.Lock()
        self.write_lock = threading.Lock()

        self.pending_acks = {}
        self.pending_lock = threading.Lock()

        self._initialize_database()

    # -------------------------------------------------
    # DATABASE INITIALIZATION
    # -------------------------------------------------

    def _initialize_database(self):

        try:
            with sqlite3.connect(self.database_path) as database:

                database.execute("""
                    CREATE TABLE IF NOT EXISTS telemetry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        received_timestamp REAL NOT NULL,
                        received_at TEXT NOT NULL,
                        node_id TEXT,
                        payload_json TEXT NOT NULL
                    )
                """)

                database.execute("""
                    CREATE TABLE IF NOT EXISTS alert_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT UNIQUE NOT NULL,
                        event_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        created_timestamp REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        acknowledgement TEXT,
                        response_message TEXT
                    )
                """)

                database.commit()

        except sqlite3.Error as error:

            self.last_error = str(error)
            self.storage_errors += 1

    # -------------------------------------------------
    # SAVE MESSAGE
    # -------------------------------------------------

    def _save_message(self, data):

        try:
            payload = json.dumps(data)

            with sqlite3.connect(self.database_path) as database:

                database.execute("""
                    INSERT INTO telemetry (
                        received_timestamp,
                        received_at,
                        node_id,
                        payload_json
                    )
                    VALUES (?, ?, ?, ?)
                """, (
                    data["received_timestamp"],
                    data["received_at"],
                    data.get("node_id", "UNKNOWN"),
                    payload
                ))

                database.commit()

            return True

        except (sqlite3.Error, TypeError, ValueError) as error:

            with self.lock:
                self.storage_errors += 1
                self.last_error = f"Database save failed: {error}"

            return False

    # -------------------------------------------------
    # ALERT DATABASE OPERATIONS
    # -------------------------------------------------

    def _record_alert(
        self,
        event_id,
        event_type,
        severity,
        status,
        acknowledgement=None,
        response_message=None
    ):

        try:
            now = time.time()
            created_at = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(now)
            )

            with sqlite3.connect(self.database_path) as database:

                database.execute("""
                    INSERT INTO alert_events (
                        event_id,
                        event_type,
                        severity,
                        created_timestamp,
                        created_at,
                        status,
                        acknowledgement,
                        response_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                        status = excluded.status,
                        acknowledgement = excluded.acknowledgement,
                        response_message = excluded.response_message
                """, (
                    event_id,
                    event_type,
                    severity,
                    now,
                    created_at,
                    status,
                    acknowledgement,
                    response_message
                ))

                database.commit()

            return True

        except sqlite3.Error as error:

            with self.lock:
                self.storage_errors += 1
                self.last_error = f"Alert database error: {error}"

            return False

    def _update_alert_status(
        self,
        event_id,
        status,
        acknowledgement=None,
        response_message=None
    ):

        try:
            with sqlite3.connect(self.database_path) as database:

                database.execute("""
                    UPDATE alert_events
                    SET status = ?,
                        acknowledgement = ?,
                        response_message = ?
                    WHERE event_id = ?
                """, (
                    status,
                    acknowledgement,
                    response_message,
                    event_id
                ))

                database.commit()

            return True

        except sqlite3.Error as error:

            with self.lock:
                self.storage_errors += 1
                self.last_error = f"Alert update error: {error}"

            return False

    def get_alert_history(self, limit=100):

        try:
            with sqlite3.connect(self.database_path) as database:

                database.row_factory = sqlite3.Row

                rows = database.execute("""
                    SELECT *
                    FROM alert_events
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            return [dict(row) for row in rows]

        except sqlite3.Error as error:

            with self.lock:
                self.last_error = str(error)

            return []

    # -------------------------------------------------
    # START SERIAL CONNECTION
    # -------------------------------------------------

    def start(self):

        if self.connected and self.running:
            return True, "Already connected"

        try:

            connection = serial.Serial(port=None)

            connection.port = self.port
            connection.baudrate = self.baud_rate
            connection.timeout = 0.2
            connection.write_timeout = 2

            connection.dtr = False
            connection.rts = False

            connection.open()

            self.connection = connection

            time.sleep(2)

            self.connection.reset_input_buffer()

            self.running = True
            self.connected = True
            self.last_error = None

            self.reader_thread = threading.Thread(
                target=self._read_loop,
                daemon=True
            )

            self.reader_thread.start()

            return True, "Connected to Master Node"

        except (serial.SerialException, OSError) as error:

            self.last_error = str(error)
            self.connected = False
            self.running = False

            return False, self.last_error

    # -------------------------------------------------
    # SERIAL READING LOOP
    # -------------------------------------------------

    def _read_loop(self):

        while self.running:

            try:

                if not self.connection or not self.connection.is_open:
                    break

                line = self.connection.readline().decode(
                    "utf-8",
                    errors="replace"
                ).strip()

                if not line:
                    continue

                data = json.loads(line)

                if not isinstance(data, dict):
                    raise ValueError("JSON message must be an object")

                data["received_at"] = time.strftime("%H:%M:%S")
                data["received_timestamp"] = time.time()

                with self.lock:
                    self.valid_messages += 1
                    self.history.append(data)

                self._save_message(data)

                if data.get("event") == "ALERT_ACK":

                    event_id = data.get("event_id")

                    with self.pending_lock:

                        pending = self.pending_acks.get(event_id)

                        if pending:
                            pending["response"] = data
                            pending["event"].set()

            except json.JSONDecodeError:

                with self.lock:
                    self.invalid_messages += 1

            except (serial.SerialException, OSError) as error:

                with self.lock:
                    self.last_error = str(error)
                    self.connected = False

                self.running = False

            except Exception as error:

                with self.lock:
                    self.invalid_messages += 1
                    self.last_error = str(error)

        with self.lock:
            self.connected = False

    # -------------------------------------------------
    # SEND ALERT TO MASTER NODE
    # -------------------------------------------------

    def send_alert(
        self,
        event_type,
        severity="CRITICAL",
        timeout=10
    ):

        event_type = str(event_type).upper().strip()
        severity = str(severity).upper().strip()

        allowed_events = ["LANDSLIDE", "ACCIDENT"]
        allowed_severities = ["CRITICAL", "HIGH", "MEDIUM"]

        if event_type not in allowed_events:
            return False, "Invalid alert type", None

        if severity not in allowed_severities:
            return False, "Invalid severity", None

        if not self.connected or not self.running:
            return False, "Master Node is disconnected", None

        event_id = "ALP-" + uuid.uuid4().hex[:8].upper()

        command = (
            f"ALERT|{event_type}|{severity}|{event_id}\n"
        )

        acknowledgement = threading.Event()

        # Register the acknowledgement before transmission.
        with self.pending_lock:
            self.pending_acks[event_id] = {
                "event": acknowledgement,
                "response": None
            }

        # Save the event before attempting transmission.
        saved = self._record_alert(
            event_id=event_id,
            event_type=event_type,
            severity=severity,
            status="PENDING",
            response_message="Waiting for Master acknowledgement"
        )

        if not saved:

            with self.pending_lock:
                self.pending_acks.pop(event_id, None)

            return (
                False,
                "Alert could not be recorded in the database",
                event_id
            )

        try:

            with self.write_lock:

                if not self.connection or not self.connection.is_open:
                    raise serial.SerialException(
                        "Serial connection is not open"
                    )

                self.connection.write(command.encode("utf-8"))
                self.connection.flush()

            received = acknowledgement.wait(timeout)

            with self.pending_lock:
                pending = self.pending_acks.pop(event_id, None)

            if not received or not pending:

                message = "No acknowledgement received from Master"

                self._update_alert_status(
                    event_id,
                    status="FAILED",
                    response_message=message
                )

                return False, message, event_id

            response = pending["response"]

            if response and response.get("status") == "RECEIVED":

                message = "Master acknowledged alert"

                self._update_alert_status(
                    event_id,
                    status="ACKNOWLEDGED",
                    acknowledgement=response.get("status"),
                    response_message=message
                )

                return True, message, event_id

            message = "Master returned an unexpected response"

            self._update_alert_status(
                event_id,
                status="FAILED",
                acknowledgement=(
                    response.get("status") if response else None
                ),
                response_message=message
            )

            return False, message, event_id

        except (serial.SerialException, OSError) as error:

            with self.pending_lock:
                self.pending_acks.pop(event_id, None)

            with self.lock:
                self.last_error = str(error)

            self._update_alert_status(
                event_id,
                status="FAILED",
                response_message=str(error)
            )

            return False, str(error), event_id

    # -------------------------------------------------
    # SAVE EXTERNAL / SIMULATED NODE MESSAGE
    # -------------------------------------------------

    def save_external_message(self, data):

        if not isinstance(data, dict):
            return False

        if not data.get("node_id"):
            return False

        try:

            message = dict(data)

            message["received_at"] = time.strftime("%H:%M:%S")
            message["received_timestamp"] = time.time()

            saved = self._save_message(message)

            if not saved:
                return False

            with self.lock:
                self.valid_messages += 1
                self.history.append(message)

            return True

        except Exception as error:

            with self.lock:
                self.last_error = str(error)

            return False

    # -------------------------------------------------
    # GET LATEST MESSAGE
    # -------------------------------------------------

    def get_latest_message(self):

        with self.lock:

            if not self.history:
                return None

            return dict(self.history[-1])

    # -------------------------------------------------
    # GET IN-MEMORY HISTORY
    # -------------------------------------------------

    def get_message_history(self, limit=None):

        with self.lock:
            messages = list(self.history)

        if limit is not None:
            messages = messages[-limit:] if limit > 0 else []

        return [dict(message) for message in messages]

    # -------------------------------------------------
    # GET DATABASE HISTORY
    # -------------------------------------------------

    def get_persisted_messages(self, limit=100):

        try:

            with sqlite3.connect(self.database_path) as database:

                database.row_factory = sqlite3.Row

                rows = database.execute("""
                    SELECT *
                    FROM telemetry
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,)).fetchall()

            messages = []

            for row in rows:

                message = json.loads(row["payload_json"])
                message["database_id"] = row["id"]

                messages.append(message)

            return messages

        except (sqlite3.Error, json.JSONDecodeError) as error:

            with self.lock:
                self.last_error = str(error)

            return []

    # -------------------------------------------------
    # GET LATEST MESSAGE FROM EACH NODE
    # -------------------------------------------------

    def get_latest_node_messages(self):

        try:

            with sqlite3.connect(self.database_path) as database:

                database.row_factory = sqlite3.Row

                rows = database.execute("""
                    SELECT t.*
                    FROM telemetry AS t
                    INNER JOIN (
                        SELECT node_id, MAX(id) AS latest_id
                        FROM telemetry
                        GROUP BY node_id
                    ) AS latest
                    ON t.id = latest.latest_id
                    ORDER BY t.id DESC
                """).fetchall()

            nodes = []

            for row in rows:

                message = json.loads(row["payload_json"])

                message["database_id"] = row["id"]
                message["node_id"] = row["node_id"]
                message["received_at"] = row["received_at"]

                nodes.append(message)

            return nodes

        except (sqlite3.Error, json.JSONDecodeError) as error:

            with self.lock:
                self.last_error = str(error)

            return []

    # -------------------------------------------------
    # EXPORT TELEMETRY TO CSV
    # -------------------------------------------------

    def export_telemetry_csv(self):

        try:

            with sqlite3.connect(self.database_path) as database:

                rows = database.execute("""
                    SELECT id, received_at, node_id, payload_json
                    FROM telemetry
                    ORDER BY id ASC
                """).fetchall()

            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow([
                "Record ID",
                "Received At",
                "Node ID",
                "Role",
                "Status",
                "Uptime (ms)",
                "ESP-NOW",
                "LoRa"
            ])

            for row in rows:

                record_id, received_at, node_id, payload_json = row
                message = json.loads(payload_json)

                writer.writerow([
                    record_id,
                    received_at,
                    node_id,
                    message.get("role", ""),
                    message.get("status", ""),
                    message.get("uptime_ms", ""),
                    message.get("esp_now", ""),
                    message.get("lora", "")
                ])

            return output.getvalue()

        except (sqlite3.Error, json.JSONDecodeError) as error:

            with self.lock:
                self.last_error = str(error)

            return None

    # -------------------------------------------------
    # GET STATISTICS
    # -------------------------------------------------

    def get_statistics(self):

        with self.lock:

            return {
                "valid_messages": self.valid_messages,
                "invalid_messages": self.invalid_messages,
                "storage_errors": self.storage_errors,
                "connected": self.connected,
                "port": self.port,
                "last_error": self.last_error,
                "history_size": len(self.history),
                "database_path": self.database_path
            }

    # -------------------------------------------------
    # STOP SERIAL CONNECTION
    # -------------------------------------------------

    def stop(self):

        self.running = False

        with self.lock:
            self.connected = False

        if self.connection and self.connection.is_open:
            self.connection.close()

        if (
            self.reader_thread
            and self.reader_thread.is_alive()
            and threading.current_thread() != self.reader_thread
        ):
            self.reader_thread.join(timeout=1)