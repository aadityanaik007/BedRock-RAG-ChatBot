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