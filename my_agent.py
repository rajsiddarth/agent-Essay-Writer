# my_agent.py
"""
Wraps the LangGraph essay writer into simple functions used by Streamlit.
Expects environment variables:
  - OPENAI_API_KEY (if using OpenAI via LangChain)
  - TAVILY_API_KEY (for Tavily search)
"""

import os
import json
from typing import List, Dict, Any
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage, ChatMessage
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()

class AgentState(TypedDict):
    task: str
    plan: str
    research_content: List[dict]
    draft: str
    critique: str
    state_snapshots: List[dict]
    queries: List[str]
    max_revisions: int
    revision_number: int

#Prompt for the llm that will give a plan for the essay
PLAN_PROMPT = """You are an expert writer tasked with writing a high level outline of an essay. \
Write such an outline for the user provided topic. Give an outline of the essay along with any relevant notes \
or instructions for the sections."""

#Will write the essay given all the content that was researched
WRITER_PROMPT = """You are an essay assistant tasked with writing excellent 5-paragraph essays.\
Generate the best essay possible for the user's request and the initial outline. \
If the user provides critique, respond with a revised version of your previous attempts. \
Utilize all the information below as needed: 

------

{content}"""

#Controls how we are critiquing the draft of the essay
REFLECTION_PROMPT = """You are a teacher grading an essay submission. \
Generate critique and recommendations for the user's submission. \
Provide detailed recommendations, including requests for length, depth, style, etc."""


#Given a plan we pass queries to Tavilly
RESEARCH_PLAN_PROMPT = """You are a researcher charged with providing information that can \
be used when writing the following essay. Generate a list of search queries that will gather \
any relevant information. Only generate 3 queries max."""


#It works on a critique
RESEARCH_CRITIQUE_PROMPT = """You are a researcher charged with providing information that can \
be used when making any requested revisions (as outlined below). \
Generate a list of search queries that will gather any relevant information. Only generate 3 queries max."""

from pydantic import BaseModel, Field  
# We want to get a list of strings from llm 
class Queries(BaseModel):
    queries: List[str]

from tavily import TavilyClient
tkey = os.environ.get("TAVILY_API_KEY")
if not tkey:
    raise RuntimeError("TAVILY_API_KEY not set in environment.")
tavily = TavilyClient(api_key=tkey)



openai_key = os.environ.get("OPENAI_API_KEY")
if not openai_key:
    raise RuntimeError("Missing OPENAI_API_KEY in environment.")
model = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=openai_key)


#Creating all the nodes

#Passing the system prompt and human prompt to the plan node
def plan_node(state: AgentState):
    messages = [
        SystemMessage(content=PLAN_PROMPT), 
        HumanMessage(content=state['task'])
    ]
    response = model.invoke(messages)
    return {"plan": response.content}

#This node takes in the plan and does initial research using Tavily
#Output is the list of content that we are going to use to write the essay.

def research_plan_node(state: AgentState):
    queries = model.with_structured_output(Queries).invoke([
        SystemMessage(content=RESEARCH_PLAN_PROMPT),
        HumanMessage(content=state['task'])
    ])
    content = state.get("content", [])
    for q in queries.queries:
        response = tavily.search(query=q, max_results=2)
        for r in response['results']:
            content.append(r['content'])
    return {"content": content}

#We now have the plan and content. This node will write a draft
#The response will be a draft
def generation_node(state: AgentState):
    content = "\n\n".join(state['content'] or [])
    user_message = HumanMessage(
        content=f"{state['task']}\n\nHere is my plan:\n\n{state['plan']}")
    messages = [
        SystemMessage(
            content=WRITER_PROMPT.format(content=content)
        ),
        user_message
        ]
    response = model.invoke(messages)
    return {
        "draft": response.content, 
        "revision_number": state.get("revision_number", 1) + 1
    }

#Reflection will take in the draft, reflection prompt and will generate the critique
def reflection_node(state: AgentState):
    messages = [
        SystemMessage(content=REFLECTION_PROMPT), 
        HumanMessage(content=state['draft'])
    ]
    response = model.invoke(messages)
    return {"critique": response.content}

# Passing in the critique from reflection node,we update the content
def research_critique_node(state: AgentState):
    queries = model.with_structured_output(Queries).invoke([
        SystemMessage(content=RESEARCH_CRITIQUE_PROMPT),
        HumanMessage(content=state['critique'])
    ])
    content = state['content'] or []
    for q in queries.queries:
        response = tavily.search(query=q, max_results=2)
        for r in response['results']:
            content.append(r['content'])
    return {"content": content}

#Ends if > than the max_revisions
def should_continue(state):
    if state["revision_number"] > state["max_revisions"]:
        return END
    return "reflect"
    
#Building the graph
builder = StateGraph(AgentState)# Initialize the graph with agent state
#Adding nodes
builder.add_node("planner", plan_node)
builder.add_node("generate", generation_node)
builder.add_node("reflect", reflection_node)
builder.add_node("research_plan", research_plan_node)
builder.add_node("research_critique", research_critique_node)
builder.set_entry_point("planner") #Initial entry point


#Adding conditional edge after generate. We either reflect or end.On reflect we go to the reflect node.
builder.add_conditional_edges(
    "generate", 
    should_continue, 
    {END: END, "reflect": "reflect"}
)

''' Adding edges
After planning we go to research plan , theen generate, then reflect ->research critique
'''
builder.add_edge("planner", "research_plan")
builder.add_edge("research_plan", "generate")
builder.add_edge("reflect", "research_critique")
builder.add_edge("research_critique", "generate")

graph = builder.compile(checkpointer=memory)


# ----- Thin convenience layer used by app.py -----

def list_threads() -> List[str]:
    return ["0"]

def _initial_state(topic: str, max_revisions: int, revision_number: int) -> Dict[str, Any]:
    """Create a fresh AgentState for a new/first run."""
    return {
        "task": topic,
        "plan": "",
        "research_content": [],
        "draft": "",
        "critique": "",
        "state_snapshots": [],
        "queries": [],
        "max_revisions": max_revisions,
        "revision_number": revision_number,
    }

def run_once(
    *,
    essay_topic: str,
    last_node: str,
    next_node: str | tuple | list,
    thread_id: str,
    draft_rev: int,
    count: int,
    interrupts: List[str],
) -> Dict[str, Any]:
    """
    Kicks off/advances the graph once and returns a dict the Streamlit UI expects.
    """
    # Ensure graph exists
    if "graph" not in globals():
        raise RuntimeError("Graph is not initialized.")

    # Build initial state. You can feed other fields if your nodes expect them.
    state = _initial_state(essay_topic, max_revisions=2, revision_number=draft_rev)

    #  map interrupts into config if you use them in your nodes
    cfg = {"configurable": {"thread_id": str(thread_id)}}

    result_state = graph.invoke(state, cfg)

    # Pulling fields for the UI
    content = {
        "plan": result_state.get("plan", ""),
        "research_content": result_state.get("research_content", []),
        "draft": result_state.get("draft", ""),
        "critique": result_state.get("critique", ""),
        "state_snapshots": result_state.get("state_snapshots", []),
        "queries": result_state.get("queries", []),
        "revision_number": result_state.get("revision_number", draft_rev),
        "max_revisions": result_state.get("max_revisions", 2),
        "count": count,
    }

    live_output = f"Ran graph for topic='{essay_topic}' in thread={thread_id}"

    return {
        "live_output": live_output,
        "content": content,
        "next_node": next_node,   # UI echo; your graph controls the real flow
        "last_node": last_node,
        "thread": thread_id,
        "draft_rev": content["revision_number"],
        "count": count,
    }

