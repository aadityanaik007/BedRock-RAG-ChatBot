import logging
import os
from uuid import uuid4

import requests
import streamlit as st

from logging_config import setup_logging

setup_logging("ui.log")
logger = logging.getLogger("app")

API_URL = os.getenv("CHAT_API_URL", "http://localhost:8000")

UNAVAILABLE_MESSAGE = "Sorry, the support assistant is temporarily unavailable. Please try again in a few minutes."

st.set_page_config(page_title="Parking Support Chat", page_icon="🅿️", layout="wide")

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []


def send_message(text: str) -> dict:
    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={"message": text, "conversation_id": st.session_state.conversation_id},
            timeout=120,
        )
    except requests.exceptions.RequestException:
        logger.exception("Couldn't reach the chat backend at %s", API_URL)
        return {"role": "assistant", "content": UNAVAILABLE_MESSAGE}

    if not response.ok:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        logger.error("Chat backend returned %s: %s", response.status_code, detail or response.text)
        # The backend's string details are written for end users; anything else (e.g. validation errors) is not.
        return {"role": "assistant", "content": detail if isinstance(detail, str) else UNAVAILABLE_MESSAGE}

    return {"role": "assistant", "content": response.json().get("response", "")}


with st.sidebar:
    st.header("Conversation")

    if st.button("New conversation", use_container_width=True):
        st.session_state.conversation_id = str(uuid4())
        st.session_state.messages = []
        st.rerun()

    st.caption(f"ID: `{st.session_state.conversation_id}`")
    st.caption("Conversations are kept in the backend's memory and are lost when it restarts.")

    st.divider()
    st.subheader("Messages")
    if not st.session_state.messages:
        st.caption("No messages yet.")
    for msg in st.session_state.messages:
        icon = "👤" if msg["role"] == "user" else "🤖"
        text = msg["content"]
        st.caption(f"{icon} {text[:50] + '...' if len(text) > 50 else text}")

st.title("Parking Support Chatbot")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Ask about a parking session, payment, rate or device...."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = send_message(user_input)

    st.session_state.messages.append(reply)
    st.rerun()
