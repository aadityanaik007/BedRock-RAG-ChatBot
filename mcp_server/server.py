import json
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("parking-support-tools")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "mock_data"


def load_json(filename: str):
    with open(DATA_DIR / filename, "r", encoding="utf-8") as file:
        return json.load(file)


@mcp.tool()
def get_parking_session(session_id: str):
    """Look up a parking session by ID (e.g. SES-1002): status, garage, plate, entry/exit times, validation, entry/exit events (with plate-read confidence), processing errors and the IDs of its payment transactions."""
    sessions = load_json("sessions.json")

    for session in sessions:
        if session["session_id"] == session_id:
            return session

    return {
        "error": "session_not_found",
        "session_id": session_id,
    }


@mcp.tool()
def get_payment_transaction(transaction_id: str):
    """Look up a payment transaction by ID (e.g. TXN-9001): amount, internal status, gateway status, error code and message, payment method, attempt number, idempotency key and whether it settled."""
    transactions = load_json("transactions.json")

    for transaction in transactions:
        if transaction["transaction_id"] == transaction_id:
            return transaction

    return {
        "error": "transaction_not_found",
        "transaction_id": transaction_id,
    }


@mcp.tool()
def get_garage_rate(garage_id: str):
    """Look up a garage's rate configuration by ID (e.g. GAR-01): hourly standard and validated rates, validation window, daily max, any event pricing and the billing rules used to calculate a charge."""
    rates = load_json("rates.json")

    for rate in rates:
        if rate["garage_id"] == garage_id:
            return rate

    return {
        "error": "garage_rate_not_found",
        "garage_id": garage_id,
    }


@mcp.tool()
def get_device_status(garage_id: str):
    """Look up the device health for a garage by ID (e.g. GAR-01): entry gate, exit gate, plate-recognition camera and payment terminal status, last-seen time and recent errors."""
    devices = load_json("devices.json")

    for device in devices:
        if device["garage_id"] == garage_id:
            return device

    return {
        "error": "device_not_found",
        "garage_id": garage_id,
    }


if __name__ == "__main__":
    mcp.run()