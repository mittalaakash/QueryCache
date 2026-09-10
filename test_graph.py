"""Self-check for the graph's control flow: interrupt + approve/edit/reject resume.
Uses a stub LLM so it runs with no Ollama server needed.
"""

from langgraph.types import Command

from graph import build_graph


class StubLLM:
    def invoke(self, messages):
        class R:
            content = "stub"

        return R()


def _run(action, data=None, thread_id="t1"):
    g = build_graph(StubLLM())
    config = {"configurable": {"thread_id": thread_id}}
    g.invoke({"goal": "3 day trip to Lisbon"}, config=config)
    return g.invoke(
        Command(resume={"action": action, "data": data or {}}), config=config
    )


def test_pauses_before_booking():
    g = build_graph(StubLLM())
    config = {"configurable": {"thread_id": "pause"}}
    g.invoke({"goal": "3 day trip to Lisbon"}, config=config)
    state = g.get_state(config)
    assert state.next == ("human_review",), state.next


def test_approve_reaches_booking():
    out = _run("approve", thread_id="approve")
    assert "final" in out
    assert "Booked!" in out["final"]


def test_reject_ends_without_booking():
    out = _run("reject", thread_id="reject")
    assert "final" not in out
    assert out["decision"] == "reject"


def test_edit_uses_edited_values():
    out = _run("edit", data={"budget": "$500 total"}, thread_id="edit")
    assert "$500 total" in out["final"]


if __name__ == "__main__":
    test_pauses_before_booking()
    test_approve_reaches_booking()
    test_reject_ends_without_booking()
    test_edit_uses_edited_values()
    print("all graph tests passed")
