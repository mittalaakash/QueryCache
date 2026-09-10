"""FastAPI backend: streams the LangGraph trip-planner run to a browser over
Server-Sent Events, pausing at the human_review interrupt until the client
posts a resume decision."""

import json
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from langgraph.types import Command

from graph import build_graph

load_dotenv()

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

llm = ChatOllama(model="llama3.2", temperature=0.3)
graph = build_graph(llm)
# No-ops (logs a warning, sends nothing) if LANGFUSE_PUBLIC_KEY/SECRET_KEY aren't set.
langfuse_handler = LangfuseCallbackHandler()


@app.get("/")
def index():
    return FileResponse("static/index.html")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _stream_and_report(config: dict, input_):
    async for chunk in graph.astream(input_, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            payload = chunk["__interrupt__"][0].value
            yield _sse({"type": "interrupt", "data": payload})
        else:
            [(node, output)] = chunk.items()
            yield _sse({"type": "step", "node": node, "data": output})

    state = graph.get_state(config)
    if not state.next:
        yield _sse({"type": "done", "data": state.values})


@app.post("/run/start")
async def start(req: Request):
    body = await req.json()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "callbacks": [langfuse_handler]}
    return StreamingResponse(
        _stream_and_report(config, {"goal": body["goal"]}),
        media_type="text/event-stream",
        headers={"X-Thread-Id": thread_id},
    )


@app.post("/run/{thread_id}/resume")
async def resume(thread_id: str, req: Request):
    body = await req.json()
    config = {"configurable": {"thread_id": thread_id}, "callbacks": [langfuse_handler]}
    return StreamingResponse(
        _stream_and_report(
            config,
            Command(resume={"action": body["action"], "data": body.get("data", {})}),
        ),
        media_type="text/event-stream",
    )
