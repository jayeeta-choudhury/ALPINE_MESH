import csv
import io
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from datetime import datetime
from serial_service import SerialService
from streamlit_autorefresh import st_autorefresh

# =====================================================
# ALPINE MESH | TACTICAL EXPEDITION COMMAND CENTRE
# =====================================================

st.set_page_config(
    page_title="ALPINE MESH | Command Centre",
    page_icon="🏔️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------
# LIVE HARDWARE CONNECTION
# -----------------------------------------------------

SERIAL_PORT = "COM11"
BAUD_RATE = 115200

# Initial communication-health thresholds.
# Adjust these after the real Trekker Node reporting
# interval has been finalized.
RECENT_THRESHOLD = 30
DELAYED_THRESHOLD = 60


@st.cache_resource
def get_serial_service():
    service = SerialService(
        port=SERIAL_PORT,
        baud_rate=BAUD_RATE
    )
    service.start()
    return service


serial_service = get_serial_service()

# Refresh dashboard every 2 seconds
st_autorefresh(
    interval=2000,
    key="alpine_mesh_refresh"
)

latest_data = serial_service.get_latest_message()
serial_stats = serial_service.get_statistics()

MASTER_ID = "MASTER_01"

if latest_data:
    MASTER_STATUS = latest_data.get("status", "UNKNOWN")
    MASTER_UPTIME = latest_data.get("uptime_ms", 0)
    ESP_STATUS = latest_data.get("esp_now", "UNKNOWN")
    LORA_STATUS = latest_data.get("lora", "UNKNOWN")
else:
    MASTER_STATUS = "WAITING"
    MASTER_UPTIME = 0
    ESP_STATUS = "UNKNOWN"
    LORA_STATUS = "UNKNOWN"

USB_STATUS = (
    "CONNECTED" if serial_stats.get("connected", False)
    else "DISCONNECTED"
)


# -----------------------------------------------------
# GENERAL HELPER FUNCTIONS
# -----------------------------------------------------

def format_uptime(milliseconds):
    try:
        seconds = int(milliseconds / 1000)
    except (ValueError, TypeError):
        seconds = 0

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"

    return f"{hours:02}h {minutes:02}m {remaining_seconds:02}s"


def get_node_health(last_seen_seconds):
    """
    Determines communication freshness.

    This does NOT determine the physical safety
    or actual condition of the trekker.
    """

    if last_seen_seconds is None or last_seen_seconds < 0:
        return {
            "status": "UNKNOWN",
            "color": "orange"
        }

    if last_seen_seconds <= RECENT_THRESHOLD:
        return {
            "status": "RECENTLY HEARD",
            "color": "green"
        }

    elif last_seen_seconds <= DELAYED_THRESHOLD:
        return {
            "status": "DELAYED",
            "color": "orange"
        }

    else:
        return {
            "status": "NO RECENT TELEMETRY",
            "color": "red"
        }


def get_node_age(node, current_time):
    """Returns seconds since the last packet was received."""

    received_timestamp = node.get("received_timestamp", 0)

    try:
        age = current_time - float(received_timestamp)

        if age < 0:
            return None

        return age

    except (ValueError, TypeError):
        return None




    

def get_trekker_nodes():
    """Read each node's newest persisted packet; never fabricate sensor data."""
    try:
        records = serial_service.get_latest_node_messages() or []
        nodes_by_id = {}
        for node in records:
            node_id = str(node.get("node_id", "")).strip()
            if node_id.upper().startswith("TREKKER") and node_id:
                nodes_by_id[node_id] = node
        return sorted(nodes_by_id.values(), key=lambda item: str(item.get("node_id", "")))
    except Exception as exc:
        st.error(f"Unable to retrieve Trekker Node data from the database: {exc}")
        return []
# Retrieve Trekker Nodes once per dashboard refresh.
trekker_nodes = get_trekker_nodes()

TREKKER_COUNT = len(trekker_nodes)


current_time = datetime.now().timestamp()

recent_nodes = []
delayed_nodes = []
stale_nodes = []
unknown_nodes = []

for node in trekker_nodes:

    age = get_node_age(node, current_time)
    health = get_node_health(age)

    if health["status"] == "RECENTLY HEARD":
        recent_nodes.append(node)

    elif health["status"] == "DELAYED":
        delayed_nodes.append(node)

    elif health["status"] == "NO RECENT TELEMETRY":
        stale_nodes.append(node)

    else:
        unknown_nodes.append(node)
def generate_emergency_pdf(events):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(
        Paragraph(
            "ALPINE MESH",
            styles["Title"]
        )
    )

    story.append(
        Paragraph(
            "TACTICAL EXPEDITION COMMAND CENTRE",
            styles["Heading2"]
        )
    )

    story.append(Spacer(1, 8 * mm))

    story.append(
        Paragraph(
            "EMERGENCY INCIDENT REPORT",
            styles["Heading1"]
        )
    )

    story.append(
        Paragraph(
            f"Report generated: {datetime.now().strftime('%d %B %Y, %H:%M:%S')}",
            styles["Normal"]
        )
    )

    story.append(Spacer(1, 8 * mm))

    if not events:
        story.append(
            Paragraph(
                "No emergency incidents have been recorded.",
                styles["Normal"]
            )
        )

    for index, event in enumerate(events, start=1):

        story.append(
            Paragraph(
                f"INCIDENT {index}",
                styles["Heading2"]
            )
        )

        incident_data = [
            ["FIELD", "RECORDED VALUE"],
            ["Event ID", str(event.get("event_id", "UNKNOWN"))],
            ["Event Type", str(event.get("event_type", "UNKNOWN"))],
            ["Severity", str(event.get("severity", "UNKNOWN"))],
            ["Created At", str(event.get("created_at", "UNKNOWN"))],
            ["Status", str(event.get("status", "UNKNOWN"))],
            [
                "Acknowledgement",
                str(event.get("acknowledgement") or "NOT AVAILABLE")
            ],
            [
                "Response Message",
                str(event.get("response_message") or "NOT AVAILABLE")
            ]
        ]

        table = Table(
            incident_data,
            colWidths=[45 * mm, 115 * mm]
        )

        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#142B45")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#E8EEF5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ])
        )

        story.append(table)
        story.append(Spacer(1, 8 * mm))

    story.append(Spacer(1, 5 * mm))

    story.append(
        Paragraph(
            "NOTICE: Master Node acknowledgement confirms message "
            "receipt only. This report does not confirm rescue dispatch "
            "or guarantee trekker safety.",
            styles["Italic"]
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer.getvalue()


# -----------------------------------------------------
# CUSTOM TACTICAL DESIGN
# -----------------------------------------------------

st.markdown("""
<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
    --background: #08111f;
    --panel: #111f32;
    --panel2: #172a40;
    --border: #263e58;
    --cyan: #42d9e8;
    --green: #42d99b;
    --orange: #ffb454;
    --red: #ff657b;
    --purple: #b49aff;
    --muted: #91a5bb;
    --white: #f2f7fc;
}

.stApp {
    background: var(--background);
    color: var(--white);
    font-family: 'Inter', sans-serif;
}

[data-testid="stHeader"] {
    background: rgba(8,17,31,0.95);
}

[data-testid="stSidebar"] {
    background: #0d1a2b;
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] * {
    color: var(--white);
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1500px;
}

h1, h2, h3, h4 {
    color: var(--white) !important;
    font-weight: 700 !important;
}

p {
    color: #c0cfdd;
}

.small-label {
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

.hero-title {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: 2px;
    color: var(--cyan);
}

.hero-subtitle {
    font-size: 11px;
    letter-spacing: 2px;
    color: var(--muted);
}

.panel {
    background: linear-gradient(145deg, #14253a, #101d2f);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 19px;
    margin-bottom: 12px;
}

.panel-title {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.4px;
    color: var(--muted);
    margin-bottom: 12px;
}

.metric-card {
    background: linear-gradient(145deg, #172b42, #101d2e);
    border: 1px solid var(--border);
    border-radius: 13px;
    padding: 17px;
    min-height: 112px;
}

.metric-label {
    color: var(--muted);
    font-size: 11px;
    letter-spacing: 1px;
    font-weight: 700;
}

.metric-value {
    font-size: 23px;
    font-weight: 800;
    margin-top: 10px;
}

.metric-foot {
    font-size: 11px;
    color: var(--muted);
    margin-top: 5px;
}

.cyan { color: var(--cyan); }
.green { color: var(--green); }
.orange { color: var(--orange); }
.red { color: var(--red); }
.purple { color: var(--purple); }

.status-dot {
    display: inline-block;
    height: 8px;
    width: 8px;
    border-radius: 50%;
    margin-right: 7px;
}

.dot-green { background: var(--green); }
.dot-orange { background: var(--orange); }
.dot-red { background: var(--red); }
.dot-cyan { background: var(--cyan); }

.status-line {
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}

.status-line:last-child {
    border-bottom: none;
}

.event-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    border-bottom: 1px solid var(--border);
    padding: 12px 0;
    font-size: 12px;
}

.event-row:last-child {
    border-bottom: none;
}

.demo-banner {
    background: #302818;
    border: 1px solid #74542a;
    border-radius: 9px;
    padding: 11px 14px;
    color: #ffcf81;
    font-size: 12px;
    margin-bottom: 18px;
}

.footer {
    text-align: center;
    color: #60758c;
    font-size: 10px;
    letter-spacing: 1px;
    margin-top: 40px;
    padding: 20px;
}

div[data-testid="stMetric"] {
    background: #14253a;
    border: 1px solid var(--border);
    padding: 15px;
    border-radius: 12px;
}

div[data-testid="stMetricLabel"] {
    color: var(--muted);
}

div[data-testid="stMetricValue"] {
    color: var(--cyan);
}

button[data-baseweb="tab"] {
    color: var(--white);
}

</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------
# REUSABLE DISPLAY FUNCTIONS
# -----------------------------------------------------

def metric_card(label, value, color, foot):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {color}">{value}</div>
        <div class="metric-foot">{foot}</div>
    </div>
    """, unsafe_allow_html=True)


def panel_start(title):
    st.markdown(
        f'<div class="panel"><div class="panel-title">{title}</div>',
        unsafe_allow_html=True
    )


def panel_end():
    st.markdown("</div>", unsafe_allow_html=True)


def status_line(name, value, color):
    st.markdown(f"""
    <div class="status-line">
        <span>{name}</span>
        <span style="float:right;">
            <span class="status-dot dot-{color}"></span>
            <b>{value}</b>
        </span>
    </div>
    """, unsafe_allow_html=True)


def section_title(title, subtitle=""):
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)


def status_color(value):
    if value in ["CONNECTED", "ONLINE", "ACTIVE"]:
        return "green"

    elif value in ["DISCONNECTED", "OFFLINE"]:
        return "red"

    else:
        return "orange"


# =====================================================
# SIDEBAR
# =====================================================

with st.sidebar:

    st.markdown("""
    <div style="padding:12px 4px 20px 4px;">
        <div style="font-size:25px;font-weight:800;
        color:#42d9e8;letter-spacing:2px;">
            🏔️ ALPINE
        </div>
        <div style="font-size:11px;font-weight:700;
        color:#91a5bb;letter-spacing:3px;">
            MESH COMMAND
        </div>
        <div style="font-size:9px;color:#60758c;
        margin-top:7px;">
            EXPEDITION CONTROL SYSTEM
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    page = st.radio(
        "COMMAND NAVIGATION",
        [
            "Overview",
            "Live Tracking",
            "Network Operations",
            "Trekker Monitoring",
            "Environment",
            "Emergency Centre",
            "Analytics",
            "System Settings"
        ],
        label_visibility="visible"
    )

    st.markdown("---")

    st.markdown("##### MASTER NODE")

    st.markdown(
        f'<span class="status-dot dot-{status_color(MASTER_STATUS)}"></span>'
        f'<span class="{status_color(MASTER_STATUS)}">'
        f'MASTER {MASTER_STATUS}</span>',
        unsafe_allow_html=True
    )

    st.caption(f"ID: {MASTER_ID}")
    st.caption("Interface: USB SERIAL")
    st.caption(f"Port: {SERIAL_PORT}")

    st.markdown("---")
    st.caption("ALPINE MESH | LIVE HARDWARE")


# =====================================================
# MAIN HEADER
# =====================================================

col_brand, col_time = st.columns([3, 1])

with col_brand:
    st.markdown(
        '<div class="hero-title">ALPINE MESH</div>'
        '<div class="hero-subtitle">'
        'TACTICAL EXPEDITION COMMAND CENTRE'
        '</div>',
        unsafe_allow_html=True
    )

with col_time:
    st.markdown(
        '<div style="text-align:right;color:#91a5bb;'
        'font-size:12px;">SYSTEM INTERFACE</div>'
        f'<div style="text-align:right;font-size:17px;'
        f'font-weight:700;color:#42d9e8;">'
        f'{datetime.now().strftime("%H:%M:%S")}</div>',
        unsafe_allow_html=True
    )

st.markdown("---")


# =====================================================
# PAGE 1: OVERVIEW
# =====================================================

if page == "Overview":

    section_title(
        "COMMAND OVERVIEW",
        "Live telemetry from the ALPINE MESH Master Node."
    )

    a, b, c, d = st.columns(4)

    with a:
        metric_card(
            "MASTER NODE",
            MASTER_STATUS,
            status_color(MASTER_STATUS),
            MASTER_ID
        )

    with b:
        metric_card(
            "TREKKER NODES",
            str(TREKKER_COUNT),
            "cyan",
            f"{len(recent_nodes)} recently heard"
        )

    with c:
        metric_card(
            "USB SERIAL",
            USB_STATUS,
            status_color(USB_STATUS),
            f"{SERIAL_PORT} | {BAUD_RATE} baud"
        )

    with d:
        metric_card(
            "MASTER UPTIME",
            format_uptime(MASTER_UPTIME),
            "cyan",
            "ESP32 reported uptime"
        )

    st.markdown("### SYSTEM COMMUNICATION")

    left, right = st.columns(2)

    with left:
        panel_start("COMMUNICATION CHANNELS")

        status_line(
            "USB SERIAL",
            USB_STATUS,
            status_color(USB_STATUS)
        )

        status_line(
            "ESP-NOW",
            ESP_STATUS,
            status_color(ESP_STATUS)
        )

        status_line(
            "LoRa SX1262",
            LORA_STATUS,
            status_color(LORA_STATUS)
        )

        panel_end()

    with right:
        panel_start("MASTER NODE TELEMETRY")

        status_line("Node ID", MASTER_ID, "cyan")

        status_line(
            "Node Status",
            MASTER_STATUS,
            status_color(MASTER_STATUS)
        )

        status_line("Hardware", "ESP32-S3", "cyan")

        status_line(
            "Last Received",
            latest_data.get("received_at", "WAITING")
            if latest_data else "WAITING",
            "cyan"
        )

        panel_end()

    st.markdown("### TREKKER NETWORK SUMMARY")

    x, y, z = st.columns(3)

    with x:
        metric_card(
            "RECENTLY HEARD",
            len(recent_nodes),
            "green",
            "Within 30 seconds"
        )

    with y:
        metric_card(
            "DELAYED",
            len(delayed_nodes),
            "orange",
            "31–60 seconds"
        )

    with z:
        metric_card(
            "NO RECENT TELEMETRY",
            len(stale_nodes),
            "red",
            "More than 60 seconds"
        )

    st.caption(
        "These indicators describe communication freshness only. "
        "They do not establish a trekker's physical safety."
    )

    st.markdown("### LIVE MASTER NODE MESSAGE")

    if latest_data:
        st.success("Live telemetry received from MASTER_01")
        st.json(latest_data)
    else:
        st.warning(
            "Waiting for the first message from the Master Node."
        )

    st.markdown("### SERIAL COMMUNICATION STATISTICS")

    x, y, z = st.columns(3)

    with x:
        metric_card(
            "VALID MESSAGES",
            serial_stats.get("valid_messages", 0),
            "green",
            "Successfully parsed JSON"
        )

    with y:
        metric_card(
            "INVALID MESSAGES",
            serial_stats.get("invalid_messages", 0),
            "orange",
            "Messages that failed parsing"
        )

    with z:
        metric_card(
            "CONNECTION",
            "ACTIVE" if serial_stats.get("connected", False)
            else "OFFLINE",
            "green" if serial_stats.get("connected", False)
            else "red",
            SERIAL_PORT
        )

    if serial_stats.get("last_error"):
        st.warning(
            f"Serial service message: {serial_stats['last_error']}"
        )


# =====================================================
# PAGE 2: LIVE TRACKING
# =====================================================

elif page == "Live Tracking":

    section_title(
        "LIVE TRACKING",
        "GPS position and expedition route monitoring."
    )

    a, b, c = st.columns(3)

    with a:
        metric_card(
            "GPS FIX",
            "UNAVAILABLE",
            "orange",
            "Awaiting GNSS receiver"
        )

    with b:
        metric_card(
            "TRACKER NODES",
            str(TREKKER_COUNT),
            "cyan",
            "Nodes discovered through telemetry"
        )

    with c:
        metric_card(
            "ROUTE STATUS",
            "STANDBY",
            "orange",
            "No active route"
        )

    st.markdown("### EXPEDITION MAP")

    panel_start("GPS POSITION DISPLAY")

    st.markdown("""
    <div style="height:300px;display:flex;
    align-items:center;justify-content:center;
    background:linear-gradient(135deg,#10263a,#0b1727);
    border:1px dashed #34536d;border-radius:10px;
    text-align:center;flex-direction:column;">
        <div style="font-size:48px;">🛰️</div>
        <div style="color:#42d9e8;font-size:16px;
        font-weight:700;margin-top:10px;">
            GPS MAP AWAITING DATA
        </div>
        <div style="color:#91a5bb;font-size:12px;
        margin-top:8px;">
            Connect a GNSS-enabled trekker node
            to display real coordinates.
        </div>
    </div>
    """, unsafe_allow_html=True)

    panel_end()

    st.info(
        "No map position is being fabricated. "
        "Real GPS coordinates will be displayed after GNSS integration."
    )


# =====================================================
# PAGE 3: NETWORK OPERATIONS
# =====================================================

elif page == "Network Operations":

    section_title(
        "NETWORK OPERATIONS",
        "Master Node communication and hardware connectivity."
    )

    a, b, c = st.columns(3)

    with a:
        metric_card(
            "USB SERIAL",
            USB_STATUS,
            status_color(USB_STATUS),
            f"{SERIAL_PORT} | {BAUD_RATE} baud"
        )

    with b:
        metric_card(
            "ESP-NOW",
            ESP_STATUS,
            status_color(ESP_STATUS),
            "Master Node reported status"
        )

    with c:
        metric_card(
            "LoRa SX1262",
            LORA_STATUS,
            status_color(LORA_STATUS),
            "Master Node reported status"
        )

    st.markdown("### COMMUNICATION MATRIX")

    left, right = st.columns(2)

    with left:

        panel_start("HARDWARE INTERFACES")

        status_line(
            "USB Serial",
            USB_STATUS,
            status_color(USB_STATUS)
        )

        status_line(
            "ESP-NOW",
            ESP_STATUS,
            status_color(ESP_STATUS)
        )

        status_line(
            "SX1262 LoRa",
            LORA_STATUS,
            status_color(LORA_STATUS)
        )

        panel_end()

    with right:

        panel_start("MASTER NODE INFORMATION")

        status_line("Node ID", MASTER_ID, "cyan")

        status_line(
            "Node Status",
            MASTER_STATUS,
            status_color(MASTER_STATUS)
        )

        status_line("Hardware", "ESP32-S3", "cyan")
        status_line("Serial Port", SERIAL_PORT, "cyan")
        status_line("Baud Rate", str(BAUD_RATE), "cyan")

        panel_end()

    st.markdown("### SERIAL DATA MONITOR")

    if latest_data:
        st.success("Master Node data stream available")
        st.json(latest_data)
    else:
        st.warning("No Master Node messages received yet.")

    st.markdown("### NETWORK STATISTICS")

    x, y, z = st.columns(3)

    with x:
        metric_card(
            "VALID PACKETS",
            serial_stats.get("valid_messages", 0),
            "green",
            "Successfully parsed JSON messages"
        )

    with y:
        metric_card(
            "INVALID PACKETS",
            serial_stats.get("invalid_messages", 0),
            "orange",
            "Unparsed messages"
        )

    with z:
        metric_card(
            "REMOTE GATEWAY",
            "NOT CONFIGURED",
            "orange",
            "Backhaul integration pending"
        )

    st.info(
        "ESP-NOW and LoRa statuses are currently reported by "
        "the Master Node firmware. Wireless communication "
        "has not yet been independently tested."
    )


# =====================================================
# PAGE 4: TREKKER MONITORING
# =====================================================

elif page == "Trekker Monitoring":

    section_title(
        "TREKKER MONITORING",
        "Individual status and telemetry of registered Trekker Nodes."
    )

    total_nodes = len(trekker_nodes)

    a, b, c, d = st.columns(4)

    a.metric("REGISTERED TREKKER NODES", total_nodes)
    b.metric("RECENTLY HEARD", len(recent_nodes))
    c.metric("DELAYED", len(delayed_nodes))
    d.metric("NO RECENT TELEMETRY", len(stale_nodes))

    st.divider()

    st.subheader("TREKKER NODE STATUS")

    if trekker_nodes:

        for node in trekker_nodes:

            node_id = node.get("node_id", "UNKNOWN")
            node_status = node.get("status", "UNKNOWN")
            received_at = node.get("received_at", "UNKNOWN")

            age = get_node_age(node, current_time)
            health = get_node_health(age)

            with st.container(border=True):

                st.markdown(f"### {node_id}")

                if health["status"] == "RECENTLY HEARD":
                    st.success("RECENT TELEMETRY RECEIVED")

                elif health["status"] == "DELAYED":
                    st.warning(
                        "DELAYED TELEMETRY — CHECK COMMUNICATION"
                    )

                elif health["status"] == "NO RECENT TELEMETRY":
                    st.error(
                        "NO RECENT TELEMETRY — CHECK CONNECTION"
                    )

                else:
                    st.warning("TELEMETRY TIME UNKNOWN")

                col1, col2 = st.columns(2)

                with col1:

                    st.write("**Communication health**")
                    st.write(health["status"])

                    st.write("**Reported node status**")
                    st.write(node_status)

                    st.write("**Last received**")
                    st.write(received_at)

                with col2:

                    st.write("**Time since last packet**")

                    if age is not None:
                        st.write(f"{age:.1f} seconds")
                    else:
                        st.write("UNKNOWN")

                    st.write("**Node role**")
                    st.write(node.get("role", "UNKNOWN"))

                    st.write("**Data source**")

                    data_mode = str(
                        node.get("data_mode", "UNSPECIFIED")
                    ).upper()

                    if data_mode == "SIMULATED":
                        st.warning("SIMULATED DATA")
                    elif data_mode == "LIVE":
                        st.success("LIVE DATA")
                    else:
                        st.info("SOURCE NOT SPECIFIED")

                st.write("**AVAILABLE SENSOR DATA**")

                sensor_fields = [
                    "latitude",
                    "longitude",
                    "altitude",
                    "temperature",
                    "pressure",
                    "humidity",
                    "heart_rate",
                    "spo2",
                    "battery",
                    "fall_detected"
                ]

                available_fields = {
                    field: node[field]
                    for field in sensor_fields
                    if field in node
                }

                if available_fields:
                    st.json(available_fields)
                else:
                    st.info(
                        "No trekker sensor readings are available "
                        "in this packet yet."
                    )

                with st.expander("VIEW COMPLETE TELEMETRY PACKET"):
                    st.json(node)

    else:

        st.info(
            "NO TREKKER TELEMETRY RECEIVED YET. "
            "The page will populate when the Master Node "
            "forwards Trekker Node messages."
        )

    st.divider()

    st.caption(
        "RECENTLY HEARD: packet received within 30 seconds. "
        "DELAYED: packet received 31–60 seconds ago. "
        "NO RECENT TELEMETRY: more than 60 seconds since the last packet. "
        "These are communication indicators only, not proof of "
        "the trekker's physical safety or an automatic SOS."
    )

    st.caption(
        "The thresholds are initial settings. Adjust them when "
        "the actual Trekker Node reporting interval is established."
    )


# =====================================================
# PAGE 5: ENVIRONMENT
# =====================================================

elif page == "Environment":

    section_title(
        "ENVIRONMENTAL MONITORING",
        "Environmental conditions collected by trekker sensors."
    )

    a, b, c = st.columns(3)

    with a:
        metric_card(
            "TEMPERATURE",
            "-- °C",
            "cyan",
            "Waiting for sensor data"
        )

    with b:
        metric_card(
            "PRESSURE",
            "-- hPa",
            "purple",
            "Waiting for sensor data"
        )

    with c:
        metric_card(
            "ALTITUDE",
            "-- m",
            "orange",
            "Waiting for GNSS / barometer"
        )

    st.markdown("### SENSOR STATUS")

    panel_start("ENVIRONMENTAL SENSORS")

    status_line("BMP280", "NOT CONNECTED", "orange")
    status_line("GNSS receiver", "NOT CONNECTED", "orange")
    status_line("Environmental telemetry", "WAITING", "orange")

    panel_end()
    st.divider()

    st.subheader("INCIDENT REPORT EXPORT")

    pdf_events = serial_service.get_alert_history(limit=1000) or []

    pdf_data = generate_emergency_pdf(pdf_events)

    st.download_button(
        label="DOWNLOAD EMERGENCY INCIDENT REPORT",
        data=pdf_data,
        file_name="alpine_mesh_emergency_report.pdf",
        mime="application/pdf",
        use_container_width=True
    )

    st.caption(
        "This PDF is a locally generated incident record. "
        "It does not represent an actual rescue dispatch."
    )
#=====================================================

# =====================================================
# PAGE 6: EMERGENCY CENTRE
# =====================================================

elif page == "Emergency Centre":

    section_title(
        "EMERGENCY RESPONSE CENTRE",
        "Emergency alert transmission and persistent event monitoring."
    )

    # Retrieve permanent alert history from SQLite.
    alert_history = serial_service.get_alert_history(limit=100) or []

    # -------------------------------
    # EXPORT EMERGENCY EVENT HISTORY
    # -------------------------------

    if alert_history:

        csv_buffer = io.StringIO()

        export_fields = [
            "event_id",
            "event_type",
            "severity",
            "created_at",
            "status",
            "acknowledgement",
            "response_message"
        ]

        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=export_fields,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(alert_history)

        st.download_button(
            label="⬇️ Download Emergency Event History",
            data=csv_buffer.getvalue(),
            file_name="alpine_mesh_emergency_history.csv",
            mime="text/csv",
            use_container_width=True
        )

    else:
        st.info("No emergency events available to export yet.")

    # -------------------------------
    # ALERT SUMMARY
    # -------------------------------

    acknowledged_count = sum(
        1 for event in alert_history
        if event.get("status") == "ACKNOWLEDGED"
    )

    failed_count = sum(
        1 for event in alert_history
        if event.get("status") == "FAILED"
    )

    pending_count = sum(
        1 for event in alert_history
        if event.get("status") == "PENDING"
    )

    a, b, c, d = st.columns(4)

    with a:
        metric_card(
            "TOTAL ALERTS",
            str(len(alert_history)),
            "cyan",
            "Saved in SQLite database"
        )

    with b:
        metric_card(
            "ACKNOWLEDGED",
            str(acknowledged_count),
            "green",
            "Master confirmations"
        )

    with c:
        metric_card(
            "FAILED",
            str(failed_count),
            "red",
            "Unconfirmed transmissions"
        )

    with d:
        metric_card(
            "PENDING",
            str(pending_count),
            "orange",
            "Awaiting acknowledgement"
        )

    st.markdown("### TRANSMIT EMERGENCY ALERT")

    st.warning(
        "Development interface only. This system does not "
        "contact emergency services or guarantee rescue assistance."
    )

    with st.container(border=True):

        st.markdown("#### NEW EMERGENCY EVENT")

        with st.form("emergency_alert_form"):

            event_type = st.selectbox(
                "EMERGENCY TYPE",
                ["LANDSLIDE", "ACCIDENT"]
            )

            severity = st.selectbox(
                "SEVERITY",
                ["CRITICAL", "HIGH", "MEDIUM"]
            )

            st.caption(
                "A unique event ID will be generated automatically."
            )

            submitted = st.form_submit_button(
                "TRANSMIT ALERT TO MASTER NODE",
                type="primary",
                use_container_width=True
            )

        if submitted:

            if not serial_stats.get("connected", False):

                st.error(
                    "MASTER NODE DISCONNECTED. "
                    "Check the USB serial connection."
                )

            else:

                with st.spinner(
                    "Transmitting alert and waiting for acknowledgement..."
                ):

                    try:
                        success, message, event_id = (
                            serial_service.send_alert(
                                event_type=event_type,
                                severity=severity,
                                timeout=10
                            )
                        )

                        if success:
                            st.success(
                                f"MASTER ACKNOWLEDGEMENT RECEIVED | "
                                f"EVENT ID: {event_id}"
                            )
                            st.info(message)

                        else:
                            st.error(
                                f"ALERT NOT CONFIRMED | "
                                f"EVENT ID: {event_id}"
                            )
                            st.warning(message)

                    except Exception as error:
                        st.error(
                            f"Alert transmission error: {error}"
                        )

    # -------------------------------
    # MASTER NODE CONNECTION
    # -------------------------------

    st.markdown("### MASTER NODE CONNECTION")

    left, right = st.columns(2)

    with left:
        status_line(
            "USB SERIAL",
            USB_STATUS,
            status_color(USB_STATUS)
        )

        status_line(
            "MASTER NODE",
            MASTER_STATUS,
            status_color(MASTER_STATUS)
        )

    with right:
        status_line("SERIAL PORT", SERIAL_PORT, "cyan")
        status_line("BAUD RATE", str(BAUD_RATE), "cyan")

    # -------------------------------
    # PERMANENT ALERT HISTORY
    # -------------------------------

    st.markdown("### PERMANENT EMERGENCY EVENT HISTORY")

    if alert_history:

        for event in alert_history:

            with st.container(border=True):

                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(
                        f"**{event.get('event_type', 'UNKNOWN')}** "
                        f"| {event.get('severity', 'UNKNOWN')}"
                    )

                    st.caption(
                        f"Event ID: {event.get('event_id', 'UNKNOWN')}"
                    )

                    st.caption(
                        f"Date: {event.get('created_at', 'UNKNOWN')}"
                    )

                    st.caption(
                        f"Master acknowledgement: "
                        f"{event.get('acknowledgement') or 'NONE'}"
                    )

                    st.caption(
                        event.get("response_message") or ""
                    )

                with col2:
                    event_status = event.get("status", "UNKNOWN")

                    if event_status == "ACKNOWLEDGED":
                        st.success("ACKNOWLEDGED")
                    elif event_status == "PENDING":
                        st.warning("PENDING")
                    else:
                        st.error(event_status)

    else:
        st.info(
            "No emergency alerts have been recorded in the database yet."
        )

    st.caption(
        "Alert records are stored locally in SQLite and remain "
        "available after dashboard restarts. An acknowledgement "
        "confirms Master Node receipt, not rescue dispatch."
    )


# =====================================================
# PAGE 7: ANALYTICS
# =====================================================

elif page == "Analytics":

    section_title(
        "SYSTEM ANALYTICS",
        "Persistent emergency activity, communication analytics "
        "and Master Node telemetry."
    )

    # =====================================================
    # EMERGENCY EVENT ANALYTICS
    # =====================================================

    st.markdown("### EMERGENCY EVENT ANALYTICS")

    emergency_events = (
        serial_service.get_alert_history(limit=1000) or []
    )

    total_emergency_events = len(emergency_events)

    acknowledged_events = sum(
        1 for event in emergency_events
        if event.get("status") == "ACKNOWLEDGED"
    )

    failed_events = sum(
        1 for event in emergency_events
        if event.get("status") == "FAILED"
    )

    pending_events = sum(
        1 for event in emergency_events
        if event.get("status") == "PENDING"
    )

    acknowledgement_rate = (
        (acknowledged_events / total_emergency_events) * 100
        if total_emergency_events > 0 else 0
    )

    a, b, c, d = st.columns(4)

    a.metric("TOTAL ALERTS", total_emergency_events)
    b.metric("ACKNOWLEDGED", acknowledged_events)
    c.metric("FAILED", failed_events)
    d.metric(
        "ACKNOWLEDGEMENT RATE",
        f"{acknowledgement_rate:.1f}%"
    )

    st.caption(
        "Acknowledgement confirms receipt by the Master Node only. "
        "It does not confirm rescue dispatch or trekker safety."
    )

    if emergency_events:

        st.markdown("#### EVENT TYPE DISTRIBUTION")

        event_type_counts = {}

        for event in emergency_events:
            event_type = event.get("event_type", "UNKNOWN")
            event_type_counts[event_type] = (
                event_type_counts.get(event_type, 0) + 1
            )

        st.bar_chart(event_type_counts)

        st.markdown("#### SEVERITY DISTRIBUTION")

        severity_counts = {}

        for event in emergency_events:
            severity = event.get("severity", "UNKNOWN")
            severity_counts[severity] = (
                severity_counts.get(severity, 0) + 1
            )

        st.bar_chart(severity_counts)

        st.markdown("#### EVENT STATUS DISTRIBUTION")

        status_counts = {
            "ACKNOWLEDGED": acknowledged_events,
            "FAILED": failed_events,
            "PENDING": pending_events
        }

        st.bar_chart(status_counts)

    else:
        st.info(
            "No emergency events have been recorded yet. "
            "Recorded events will appear here."
        )

    st.divider()

    # =====================================================
    # SEARCHABLE EMERGENCY EVENT LOG
    # =====================================================

    st.markdown("### SEARCHABLE EMERGENCY EVENT LOG")

    if emergency_events:

        filter_col1, filter_col2, filter_col3 = st.columns(3)

        event_types = sorted(set(
            event.get("event_type", "UNKNOWN")
            for event in emergency_events
        ))

        severities = sorted(set(
            event.get("severity", "UNKNOWN")
            for event in emergency_events
        ))

        statuses = sorted(set(
            event.get("status", "UNKNOWN")
            for event in emergency_events
        ))

        with filter_col1:
            selected_event_type = st.selectbox(
                "EVENT TYPE",
                ["ALL"] + event_types,
                key="analytics_event_type_filter"
            )

        with filter_col2:
            selected_severity = st.selectbox(
                "SEVERITY",
                ["ALL"] + severities,
                key="analytics_severity_filter"
            )

        with filter_col3:
            selected_status = st.selectbox(
                "STATUS",
                ["ALL"] + statuses,
                key="analytics_status_filter"
            )

        search_query = st.text_input(
            "SEARCH EVENT ID OR EVENT DETAILS",
            placeholder="Enter event ID, type or keyword...",
            key="analytics_event_search"
        ).strip().lower()

        filtered_events = []

        for event in emergency_events:

            if (
                selected_event_type != "ALL"
                and event.get("event_type") != selected_event_type
            ):
                continue

            if (
                selected_severity != "ALL"
                and event.get("severity") != selected_severity
            ):
                continue

            if (
                selected_status != "ALL"
                and event.get("status") != selected_status
            ):
                continue

            searchable_text = " ".join([
                str(event.get("event_id", "")),
                str(event.get("event_type", "")),
                str(event.get("severity", "")),
                str(event.get("status", "")),
                str(event.get("created_at", "")),
                str(event.get("acknowledgement", "")),
                str(event.get("response_message", ""))
            ]).lower()

            if search_query and search_query not in searchable_text:
                continue

            filtered_events.append(event)

        st.caption(
            f"Showing {len(filtered_events)} of "
            f"{total_emergency_events} recorded events."
        )

        if filtered_events:

            for event in filtered_events:

                event_id = event.get("event_id", "UNKNOWN")
                event_type = event.get("event_type", "UNKNOWN")
                severity = event.get("severity", "UNKNOWN")
                status = event.get("status", "UNKNOWN")
                created_at = event.get("created_at", "UNKNOWN")

                with st.expander(
                    f"{event_id} | {event_type} | {status}"
                ):

                    detail_col1, detail_col2 = st.columns(2)

                    with detail_col1:
                        st.write("**EVENT ID**")
                        st.write(event_id)

                        st.write("**EVENT TYPE**")
                        st.write(event_type)

                        st.write("**SEVERITY**")
                        st.write(severity)

                    with detail_col2:
                        st.write("**STATUS**")
                        st.write(status)

                        st.write("**CREATED AT**")
                        st.write(created_at)

                    st.write("**ACKNOWLEDGEMENT**")
                    st.write(
                        event.get("acknowledgement") or "NOT AVAILABLE"
                    )

                    st.write("**RESPONSE MESSAGE**")
                    st.write(
                        event.get("response_message") or "NOT AVAILABLE"
                    )

        else:
            st.info(
                "No emergency events match the selected filters."
            )

    else:
        st.info(
            "The searchable event log will become available "
            "when the first emergency event is recorded."
        )

    st.divider()

    # =====================================================
    # ORIGINAL TELEMETRY ANALYTICS
    # =====================================================

    persisted_messages = serial_service.get_persisted_messages(limit=20)
    valid_messages = serial_stats.get("valid_messages", 0)
    invalid_messages = serial_stats.get("invalid_messages", 0)
    storage_errors = serial_stats.get("storage_errors", 0)

    connection_active = serial_stats.get("connected", False)

    last_received = (
        latest_data.get("received_at", "UNKNOWN")
        if latest_data else "WAITING"
    )

    a, b, c, d = st.columns(4)

    a.metric("VALID MESSAGES", valid_messages)
    b.metric("INVALID MESSAGES", invalid_messages)
    c.metric("RECENT DB RECORDS", len(persisted_messages))
    d.metric("STORAGE ERRORS", storage_errors)

    st.divider()

    # =====================================================
    # NETWORK ANALYTICS
    # =====================================================

    st.subheader("NETWORK ANALYTICS")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**MASTER CONNECTION**")
        st.write("ONLINE" if connection_active else "OFFLINE")

        st.write("**SERIAL PORT**")
        st.write(serial_stats.get("port", "UNKNOWN"))

    with col2:
        st.write("**LAST PACKET RECEIVED**")
        st.write(last_received)

        st.write("**DATABASE FILE**")
        st.write(serial_stats.get("database_path", "UNKNOWN"))

    st.divider()

    # =====================================================
    # TREKKER NETWORK ANALYTICS
    # =====================================================

    st.subheader("TREKKER NETWORK ANALYTICS")

    x, y, z = st.columns(3)

    x.metric("REGISTERED NODES", TREKKER_COUNT)
    y.metric("RECENTLY HEARD", len(recent_nodes))
    z.metric("NO RECENT TELEMETRY", len(stale_nodes))

    st.divider()

    # =====================================================
    # MASTER UPTIME TREND
    # =====================================================

    st.subheader("MASTER UPTIME TREND")

    chart_messages = persisted_messages[::-1]
    uptime_values = []

    for message in chart_messages:

        try:
            uptime = int(message.get("uptime_ms", 0))

            if uptime >= 0:
                uptime_values.append(uptime)

        except (ValueError, TypeError):
            continue

    if uptime_values:

        minimum = min(uptime_values)
        maximum = max(uptime_values)

        for index, uptime in enumerate(uptime_values):

            if maximum == minimum:
                bar_length = 20
            else:
                bar_length = int(
                    5 + ((uptime - minimum) / (maximum - minimum)) * 35
                )

            st.write(
                f"Packet {index + 1:02d}  "
                f"`{uptime:,} ms`  "
                f"{'█' * bar_length}"
            )

    else:
        st.info("No saved uptime records available yet.")

    st.caption(
        "This chart shows saved Master Node uptime, not radio signal strength."
    )

    st.divider()

    # =====================================================
    # TELEMETRY DATA EXPORT
    # =====================================================

    st.subheader("TELEMETRY DATA EXPORT")

    csv_data = serial_service.export_telemetry_csv()

    if csv_data is not None:

        st.download_button(
            label="DOWNLOAD TELEMETRY CSV",
            data=csv_data,
            file_name="alpine_mesh_telemetry.csv",
            mime="text/csv",
            use_container_width=True
        )

    else:
        st.error("Unable to generate telemetry CSV.")

    st.divider()

    # =====================================================
    # SAVED TELEMETRY HISTORY
    # =====================================================

    st.subheader("SAVED TELEMETRY HISTORY")

    if persisted_messages:

        for index, message in enumerate(persisted_messages[:10]):

            received_at = message.get("received_at", "UNKNOWN")
            uptime = message.get("uptime_ms", "UNKNOWN")
            database_id = message.get("database_id", "UNKNOWN")

            with st.expander(
                f"DB RECORD {database_id} | {received_at}"
            ):
                st.json(message)
                st.caption(f"Uptime: {uptime} ms")

    else:
        st.info(
            "No saved telemetry records found. "
            "Connect the Master Node and wait for heartbeat messages."
        )

    st.divider()

    st.caption(
        "Telemetry is saved in the local SQLite database. "
        "The most recent 20 records are loaded for this analytics view."
    )


# =====================================================
# PAGE 8: SYSTEM SETTINGS
# =====================================================

elif page == "System Settings":

    section_title(
        "SYSTEM SETTINGS",
        "Local interface and hardware connection configuration."
    )

    panel_start("MASTER NODE CONFIGURATION")

    st.markdown("**Node ID:** MASTER_01")
    st.markdown("**Hardware:** Heltec WiFi LoRa 32 V3")
    st.markdown("**Microcontroller:** ESP32-S3")
    st.markdown("**Radio:** SX1262")
    st.markdown(f"**Serial port:** {SERIAL_PORT}")
    st.markdown(f"**Serial baud rate:** {BAUD_RATE}")

    panel_end()

    panel_start("SERIAL CONNECTION STATUS")

    status_line(
        "Connection",
        USB_STATUS,
        status_color(USB_STATUS)
    )

    status_line("Serial Port", SERIAL_PORT, "cyan")
    status_line("Baud Rate", str(BAUD_RATE), "cyan")

    status_line(
        "Serial Service",
        "RUNNING" if serial_stats.get("connected", False)
        else "NOT CONNECTED",
        "green" if serial_stats.get("connected", False)
        else "red"
    )

    panel_end()

    panel_start("TREKKER NODE HEALTH SETTINGS")

    st.markdown(
        f"**Recently heard threshold:** {RECENT_THRESHOLD} seconds"
    )

    st.markdown(
        f"**Delayed threshold:** {DELAYED_THRESHOLD} seconds"
    )

    st.markdown(
        f"**Registered Trekker Nodes:** {TREKKER_COUNT}"
    )

    panel_end()

    st.info(
        "The serial connection is currently configured in app.py. "
        "Changing the port or baud rate requires updating the "
        "configuration and restarting the dashboard."
    )

    if serial_stats.get("last_error"):
        st.warning(
            f"Connection information: {serial_stats['last_error']}"
        )


# =====================================================
# FOOTER
# =====================================================

st.markdown("""
<div class="footer">
    ALPINE MESH COMMAND CENTRE | LIVE HARDWARE VERSION<br>
    TACTICAL EXPEDITION MONITORING INTERFACE
</div>
""", unsafe_allow_html=True)


# =====================================================
# FOOTER
# =====================================================
st.markdown("""
<div class="footer">
    ALPINE MESH COMMAND CENTRE | LIVE HARDWARE VERSION<br>
    TACTICAL EXPEDITION MONITORING INTERFACE
</div>
""", unsafe_allow_html=True)