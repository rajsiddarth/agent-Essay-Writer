# app.py
import ast
import json
from typing import Any, Dict, List

import streamlit as st
from my_Agent import run_once, continue_run, list_threads  

st.set_page_config(page_title="Agent Essay Writer", layout="wide")

def parse_node_input(raw: str) -> Any:
    """
    Accepts strings like:
      "planner"                       -> "planner"
      "('research_plan',)"            -> ('research_plan',)
      "['research_plan', 'generate']" -> ['research_plan', 'generate']
      '{"go_to": "generate"}'         -> {'go_to': 'generate'}
    Falls back to the original string if parsing fails.
    """
    try:
        if raw.strip().startswith(("{", "[", "(")) and raw.strip().endswith(("}", "]", ")")):
            return ast.literal_eval(raw)
    except Exception:
        pass
    return raw


def init_state():
    if "live_output" not in st.session_state:
        st.session_state.live_output = ""
    if "content" not in st.session_state:
        st.session_state.content = {}
    if "count" not in st.session_state:
        st.session_state.count = 1
    if "thread" not in st.session_state:
        # default to first thread id
        threads = list_threads()
        st.session_state.thread = threads[0] if threads else "0"
    if "draft_rev" not in st.session_state:
        st.session_state.draft_rev = 0


init_state()


# ------------------------------
# Sidebar controls
# ------------------------------
st.sidebar.header("Manage Agent")
st.sidebar.caption("Interrupt after state")

interrupts = {
    "planner": st.sidebar.checkbox("planner", value=True),
    "research_plan": st.sidebar.checkbox("research_plan", value=True),
    "generate": st.sidebar.checkbox("generate", value=True),
    "reflect": st.sidebar.checkbox("reflect", value=True),
    "research_critique": st.sidebar.checkbox("research_critique", value=True),
}

st.sidebar.divider()
if st.sidebar.button("🧹 Clear session"):
    for k in ["live_output", "content", "count", "thread", "draft_rev"]:
        if k in st.session_state:
            del st.session_state[k]
    st.rerun()


# ------------------------------
# Main controls
# ------------------------------
st.title("Agent Essay Writer")

essay_topic = st.text_input("Essay Topic", value="Pizza Shop")

col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
with col1:
    last_node = st.text_input("last node", value="planner")
with col2:
    next_node_raw = st.text_input("next node", value="('research_plan',)")
with col3:
    # Keep thread selection in sync with session
    threads = list_threads()
    current_thread_idx = 0
    if st.session_state.thread in threads:
        current_thread_idx = threads.index(st.session_state.thread)
    thread = st.selectbox("Thread", options=threads or ["0"], index=current_thread_idx)
    st.session_state.thread = thread
with col4:
    draft_rev = st.number_input(
        "Draft Rev",
        min_value=0,
        step=1,
        value=int(st.session_state.draft_rev),
        help="Revision number for the essay draft.",
    )
with col5:
    count = st.number_input(
        "count",
        min_value=0,
        step=1,
        value=int(st.session_state.count),
        help="A simple step counter you can use for iterations.",
    )

cgen, ccont = st.columns([1, 1])
do_generate = cgen.button("Generate Essay", type="primary")
do_continue = ccont.button("Continue Essay")

# Parsed next_node
next_node = parse_node_input(next_node_raw)


# ------------------------------
# Actions
# ------------------------------
if do_generate:
    try:
        ints = [k for k, v in interrupts.items() if v]
        res = run_once(
            essay_topic=essay_topic,
            last_node=last_node,
            next_node=next_node,
            thread_id=st.session_state.thread,
            draft_rev=int(draft_rev),
            count=int(count),
            interrupts=ints,
        )
        st.session_state.live_output = res.get("live_output", "")
        st.session_state.content = res.get("content", {})
        st.session_state.count = int(res.get("count", count))
        st.session_state.draft_rev = int(res.get("draft_rev", draft_rev))
        st.success("Agent run completed.")
    except Exception as e:
        st.error(f"Error during Generate: {e}")

if do_continue:
    try:
        res = continue_run(
            thread_id=st.session_state.thread,
            draft_rev=int(draft_rev),
            count=int(count),
        )
        st.session_state.live_output = res.get("live_output", "")
        st.session_state.content = res.get("content", {})
        st.session_state.count = int(res.get("count", count))
        st.session_state.draft_rev = int(res.get("draft_rev", draft_rev))
        st.success("Agent continued.")
    except Exception as e:
        st.error(f"Error during Continue: {e}")


# ------------------------------
# Output
# ------------------------------
st.subheader("Live Agent Output")
st.text_area("Output", st.session_state.live_output, height=160)

tabs = st.tabs(["Plan", "Research Content", "Draft", "Critique", "StateSnapshots", "Raw JSON"])

content = st.session_state.content or {}
plan = content.get("plan", "")
research = content.get("research_content", [])
draft_text = content.get("draft", "")
critique = content.get("critique", "")
snapshots = content.get("state_snapshots", [])
queries = content.get("queries", [])
revision_number = content.get("revision_number", st.session_state.draft_rev)
max_revisions = content.get("max_revisions", 2)

with tabs[0]:
    st.text_area("Plan", plan, height=220)
    if queries:
        st.caption("Planned / recent queries:")
        st.code("\n".join(map(str, queries)))

with tabs[1]:
    st.json(research, expanded=False)

with tabs[2]:
    st.text_area("Draft", draft_text, height=300)
    col_dl1, col_dl2 = st.columns([1, 1])
    with col_dl1:
        st.download_button(
            "⬇️ Download draft (.md)",
            data=draft_text or "",
            file_name=f"draft_rev_{revision_number}.md",
            mime="text/markdown",
            disabled=not draft_text,
        )
    with col_dl2:
        st.download_button(
            "⬇️ Download plan+research (.json)",
            data=json.dumps({"plan": plan, "research": research}, indent=2),
            file_name=f"plan_research_rev_{revision_number}.json",
            mime="application/json",
        )
    st.caption(f"Revision {revision_number} / max {max_revisions}")

with tabs[3]:
    st.text_area("Critique", critique, height=220)

with tabs[4]:
    st.json(snapshots, expanded=False)

with tabs[5]:
    st.code(json.dumps(content, indent=2), language="json")
