"""Multi-agent trip planner graph: planner -> budget -> itinerary -> human_review -> booking/END.

Demonstrates LangGraph + LangChain multi-agent orchestration with a human-in-the-loop
checkpoint (approve / edit / reject) before the final "booking" step.
"""

from typing import Any, NotRequired, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import traceable


class TripState(TypedDict):
    goal: str
    plan: str
    budget: str
    itinerary: str
    decision: NotRequired[str]
    final: NotRequired[str]


def _ask(llm: Any, prompt: str) -> str:
    return llm.invoke([HumanMessage(content=prompt)]).content


def build_graph(llm: Any):
    """llm just needs an `.invoke(messages) -> object with .content`, so tests
    can swap in a stub instead of a real Ollama model."""

    @traceable(name="planner_doing_its_work", tags=["planner"])
    def planner(state: TripState) -> dict:
        plan = _ask(
            llm,
            f"Trip goal: {state['goal']}\n"
            "In 2-3 sentences, sketch a rough plan (destination, length, style of trip).",
        )
        return {"plan": plan}

    @traceable(name="budget_agent_doing_its_work", tags=["budget"])
    def budget_agent(state: TripState) -> dict:
        budget = _ask(
            llm,
            f"Trip goal: {state['goal']}\nPlan: {state['plan']}\n"
            "Give a short, itemized budget estimate (2-4 lines).",
        )
        return {"budget": budget}

    @traceable(name="itinerary_agent_doing_its_work", tags=["itinerary"])
    def itinerary_agent(state: TripState) -> dict:
        itinerary = _ask(
            llm,
            f"Trip goal: {state['goal']}\nPlan: {state['plan']}\n"
            "Write a short day-by-day itinerary (2-4 lines).",
        )
        return {"itinerary": itinerary}

    @traceable(name="human_review_doing_its_work", tags=["human"])
    def human_review(state: TripState) -> dict:
        result = interrupt({
            "plan": state["plan"],
            "budget": state["budget"],
            "itinerary": state["itinerary"],
        })
        action = result["action"]
        if action == "edit":
            data = result.get("data", {})
            return {
                "decision": "approve",
                "budget": data.get("budget", state["budget"]),
                "itinerary": data.get("itinerary", state["itinerary"]),
            }
        return {"decision": action}

    def route_after_review(state: TripState) -> str:
        return END if state["decision"] == "reject" else "booking"

    def booking(state: TripState) -> dict:
        return {
            "final": f"Booked!\nItinerary: {state['itinerary']}\nBudget: {state['budget']}"
        }

    graph = StateGraph(TripState)
    graph.add_node("planner", planner)
    graph.add_node("budget_agent", budget_agent)
    graph.add_node("itinerary_agent", itinerary_agent)
    graph.add_node("human_review", human_review)
    graph.add_node("booking", booking)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "budget_agent")
    graph.add_edge("budget_agent", "itinerary_agent")
    graph.add_edge("itinerary_agent", "human_review")
    graph.add_conditional_edges("human_review", route_after_review, ["booking", END])
    graph.add_edge("booking", END)

    return graph.compile(checkpointer=MemorySaver())
