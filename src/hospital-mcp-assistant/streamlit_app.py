"""Streamlit chat for the Hospital MCP Assistant."""

import asyncio

from groq import Groq
import streamlit as st

from hospital_mcp.client import HospitalMCPClient
from hospital_mcp.config import load_host_settings
from hospital_mcp.errors import ConfigurationError
from hospital_mcp.host import (
    MAX_TOOL_ROUNDS, MUTATING_TOOLS, SYSTEM_PROMPT, execute_tool, mcp_tools_to_groq,
)

st.set_page_config(page_title="Hospital Assistant", page_icon="✚", layout="wide")
st.html("""
<style>
.stMainBlockContainer {max-width: 64rem; padding-top: clamp(3rem, 7vh, 6rem);}
.hospital-header {
    background: linear-gradient(115deg, #103d40, #14625c);
    color: #fff; padding: clamp(1.5rem, 4vw, 3rem);
    border-radius: 1.25rem; margin-bottom: 1rem;
}
.hospital-header h1 {
    font-family: Georgia, serif; font-weight: 500; color: inherit;
    font-size: clamp(2.2rem, 5vw, 3.8rem); padding: 0; line-height: 1.12;
}
.hospital-header p {color: #dbefea; margin: .85rem 0 0; max-width: 45ch;}
[data-testid="stChatMessage"] {border-radius: 1rem; padding: 1.15rem;}
[data-testid="stSidebar"] .stButton button,
.st-key-starters button {border-radius: .75rem;}
.st-key-starters button {min-height: 4rem;}
</style>
""")
state = st.session_state
state.setdefault("messages", [{"role": "system", "content": SYSTEM_PROMPT}])
state.setdefault("chat_history", [])
state.setdefault("rounds", 0)

try:
    settings = load_host_settings()
except ConfigurationError:
    st.error("Set GROQ_API_KEY in the app environment to start chatting.")
    st.stop()

with st.sidebar:
    st.subheader("✚  Hospital workspace")
    models = list(dict.fromkeys([settings.groq_model, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]))
    model = st.selectbox("Choose a model", models)
    if st.button("New Chat", icon=":material/add:", use_container_width=True):
        state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        state.rounds = 0
    st.divider()
    st.subheader("Recent chats")
    if not state.chat_history:
        st.caption("Your chats will appear here.")
    for title in reversed(state.chat_history[-10:]):
        st.text(title)

st.html("""
<header class="hospital-header">
  <h1>Hospital Assistant</h1>
  <p>Look up hospital records and manage appointments in the demo database.</p>
</header>
""")
starter = None
if len(state.messages) == 1:
    with st.container(key="starters"):
        st.subheader("Where would you like to start?")
        options = [
            ("Find a doctor", "stethoscope", "Help me find a doctor by specialty."),
            ("Look up lab results", "science", "Help me look up a patient's lab results."),
            ("Book an appointment", "calendar_month", "Help me schedule an appointment."),
        ]
        for column, (label, icon, question) in zip(st.columns(3), options):
            if column.button(label, icon=f":material/{icon}:", use_container_width=True):
                starter = question
for message in state.messages:
    if message["role"] in ("assistant", "user") and message.get("content"):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def remaining_calls():
    for index in range(len(state.messages) - 1, -1, -1):
        message = state.messages[index]
        if message["role"] != "tool":
            completed = len(state.messages) - index - 1
            return message.get("tool_calls", [])[completed:]
    return []


def generate(client, tools):
    calls = {}
    content = ""
    with st.chat_message("assistant"):
        placeholder = st.empty()
        with client.chat.completions.create(
            model=model, messages=state.messages, tools=tools, stream=True,
        ) as stream:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content += delta.content
                    placeholder.markdown(content)
                for part in delta.tool_calls or []:
                    call = calls.setdefault(part.index, {
                        "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                    })
                    if part.id:
                        call["id"] = part.id
                    if part.function:
                        call["function"]["name"] += part.function.name or ""
                        call["function"]["arguments"] += part.function.arguments or ""
    message = {"role": "assistant", "content": content or None}
    if calls:
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    elif not content:
        message["content"] = "I could not produce a response."
    return message


async def advance(decision=None):
    async with HospitalMCPClient() as mcp:
        tools = mcp_tools_to_groq(await mcp.list_tools())
        names = {tool["function"]["name"] for tool in tools}
        with Groq(api_key=settings.groq_api_key) as client:
            while True:
                for call in remaining_calls():
                    name = call["function"]["name"]
                    if name in MUTATING_TOOLS and decision is None:
                        return
                    result = await execute_tool(mcp, call, names, lambda *_: decision is True)
                    decision = None
                    state.messages.append({"role": "tool", "tool_call_id": call["id"],
                                           "name": name, "content": result})
                if state.rounds >= MAX_TOOL_ROUNDS:
                    state.messages.append({"role": "assistant", "content": "Please simplify the request."})
                    return
                reply = generate(client, tools)
                state.messages.append(reply)
                state.rounds += 1
                if not reply.get("tool_calls"):
                    return


calls = remaining_calls()
decision = None
if calls and calls[0]["function"]["name"] in MUTATING_TOOLS:
    function = calls[0]["function"]
    with st.container(border=True):
        st.subheader("Review appointment change")
        st.write(function["name"].replace("_", " ").capitalize())
        st.code(function["arguments"], language="json")
        approve, decline = st.columns(2)
    if approve.button("Approve", type="primary", use_container_width=True):
        decision = True
    elif decline.button("Decline", use_container_width=True):
        decision = False
    else:
        st.stop()
elif state.messages[-1]["role"] in ("user", "tool") or calls:
    if not st.button("Retry response"):
        st.stop()
else:
    typed_prompt = st.chat_input("Ask about records or appointments…")
    prompt = starter or typed_prompt
    if not prompt:
        st.stop()
    if len(state.messages) == 1:
        state.chat_history.append(prompt[:50])
    state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    state.rounds = 0

try:
    asyncio.run(advance(decision))
except Exception:
    st.error("Could not finish the response. Check the Groq and hospital MCP connections.")
    if st.button("Continue"):
        st.rerun()
else:
    st.rerun()
