# 🔌 Hardened Dual Serial SDN Bridge

This project bridges **two Somfy SDN RS485 networks over TCP/IP** (typically **SDN** and **DDNG** sides) using a **resilient async architecture** with automatic reconnects, message forwarding, and emoji-rich logging.

It is designed for use with **TCP-Serial bridges** (e.g., Waveshare RS485-to-TCP) and includes hardened features for unattended operation in automation environments.

---

## 🚀 Features

- 🔄 **Bi-directional message forwarding** between SDN and DDNG
- 🕓 **Automatic reconnect** with increasing back-off
- 📤 **Queued sending with rate limit** to avoid bus flooding
- 💓 **Keepalive pings** to detect dead links
- 🔀 **Node type remapping** for compatibility between SDN and DDNG
- ⚠️ **Graceful handling of malformed / partial messages**
- 🧑‍💻 **Verbose emoji logging** for easy debugging

---

## 📁 Project Structure

dual-serial-sdn-bridge/
│
├── bridge.py # Main bridge application
├── somfy/
│ ├── protocol.py # SDN protocol implementation
│ ├── messages.py # SDN message registry (auto-registers)
│ └── helpers.py # Utilities for SDN message parsing
│
├── config.py # Configuration constants (MQTT placeholders)
├── requirements.txt # Python dependencies
└── README.md # You’re here!

---

## 🧰 Requirements

- Python 3.10+
- Two RS485-to-TCP devices (e.g., Waveshare)
- Existing SDN and/or DDNG installation

---

## 🛠️ Installation

```bash
git clone https://github.com/yourname/dual-serial-sdn-bridge.git
cd dual-serial-sdn-bridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
📦 requirements.txt
Copy
Edit
paho-mqtt
(MQTT not actively used yet — placeholder for future extension)

🖥️ Running the Bridge

python3 bridge.py
You’ll see logs like:


🔄 SDN attempting connection to 192.168.0.221:4196
✅ SDN connected to 192.168.0.221:4196
💓 SDN keepalive sent
← SDN Raw: F0F0F0...
➡️ DDNG Queued send: <Lock Node 3>
Terminate with Ctrl+C for graceful shutdown.

🔄 Message Flow
Source	Condition	Destination
SDN	dest == [0xFF, 0xFF, 0xF0]	DDNG
DDNG	Always forwards	SDN

🔧 Node Type Remapping
DDNG → SDN: node_type 2 ➔ 0 and ACK requested

SDN → DDNG: For broadcast, src_node_type ➔ 2

🔥 Dynamic Resilience
Buffer overflow protection (max buffer size enforced)

Connection idle detection via keepalive failure

Graceful task cancellation on shutdown

Reconnect loop with exponential backoff

💡 Tip
This is hardened for dockerized environments where failure is expected to trigger container restart.

📜 License
MIT License © 2025 Hiren Amin