# from typing import TypedDict, Annotated, Optional
# from langgraph.graph import add_messages, StateGraph, END
# from langchain_openai import ChatOpenAI
# from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
# from dotenv import load_dotenv
# from langchain_community.tools.tavily_search import TavilySearchResults
# from fastapi import FastAPI, Query
# from fastapi.responses import StreamingResponse
# from fastapi.middleware.cors import CORSMiddleware
# import json
# from uuid import uuid4
# from langgraph.checkpoint.memory import MemorySaver
# import os
# load_dotenv()

# # Initialize memory saver for checkpointing
# memory = MemorySaver()

# class State(TypedDict):
#     messages: Annotated[list, add_messages]

# search_tool = TavilySearchResults(
#     max_results=4,
# )

# tools = [search_tool]
# print("KEY:", os.getenv("OPENROUTER_API_KEY"))
# llm = ChatOpenAI(
#     model="deepseek/deepseek-r1",   # or any OpenRouter model you want
#     api_key=os.getenv("OPENROUTER_API_KEY"),
#     base_url="https://openrouter.ai/api/v1",
#     temperature=0.2,
# )


# llm_with_tools = llm.bind_tools(tools=tools)

# async def model(state: State):
#     result = await llm_with_tools.ainvoke(state["messages"])
#     return {
#         "messages": [result], 
#     }

# async def tools_router(state: State):
#     last_message = state["messages"][-1]

#     if(hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0):
#         return "tool_node"
#     else: 
#         return END
    
# async def tool_node(state):
#     """Custom tool node that handles tool calls from the LLM."""
#     # Get the tool calls from the last message
#     tool_calls = state["messages"][-1].tool_calls
    
#     # Initialize list to store tool messages
#     tool_messages = []
    
#     # Process each tool call
#     for tool_call in tool_calls:
#         tool_name = tool_call["name"]
#         tool_args = tool_call["args"]
#         tool_id = tool_call["id"]
        
#         # Handle the search tool
#         if tool_name == "tavily_search_results_json":
#             # Execute the search tool with the provided arguments
#             search_results = await search_tool.ainvoke(tool_args)
            
#             # Create a ToolMessage for this result
#             tool_message = ToolMessage(
#                 content=str(search_results),
#                 tool_call_id=tool_id,
#                 name=tool_name
#             )
            
#             tool_messages.append(tool_message)
    
#     # Add the tool messages to the state
#     return {"messages": tool_messages}

# graph_builder = StateGraph(State)

# graph_builder.add_node("model", model)
# graph_builder.add_node("tool_node", tool_node)
# graph_builder.set_entry_point("model")

# graph_builder.add_conditional_edges("model", tools_router)
# graph_builder.add_edge("tool_node", "model")

# graph = graph_builder.compile(checkpointer=memory)

# app = FastAPI()

# # Add CORS middleware with settings that match frontend requirements
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  
#     allow_credentials=True,
#     allow_methods=["*"],  
#     allow_headers=["*"], 
#     expose_headers=["Content-Type"], 
# )

# def serialise_ai_message_chunk(chunk): 
#     if(isinstance(chunk, AIMessageChunk)):
#         return chunk.content
#     else:
#         raise TypeError(
#             f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
#         )

# async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
#     is_new_conversation = checkpoint_id is None
    
#     if is_new_conversation:
#         # Generate new checkpoint ID for first message in conversation
#         new_checkpoint_id = str(uuid4())

#         config = {
#             "configurable": {
#                 "thread_id": new_checkpoint_id
#             }
#         }
        
#         # Initialize with first message
#         events = graph.astream_events(
#             {"messages": [HumanMessage(content=message)]},
#             version="v2",
#             config=config
#         )
        
#         # First send the checkpoint ID
#         yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
#     else:
#         config = {
#             "configurable": {
#                 "thread_id": checkpoint_id
#             }
#         }
#         # Continue existing conversation
#         events = graph.astream_events(
#             {"messages": [HumanMessage(content=message)]},
#             version="v2",
#             config=config
#         )

#     async for event in events:
#         event_type = event["event"]
        
#         if event_type == "on_chat_model_stream":
#             chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
#             # Escape single quotes and newlines for safe JSON parsing
#             safe_content = chunk_content.replace("'", "\\'").replace("\n", "\\n")
            
#             yield f"data: {{\"type\": \"content\", \"content\": \"{safe_content}\"}}\n\n"
            
#         elif event_type == "on_chat_model_end":
#             # Check if there are tool calls for search
#             tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
#             search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            
#             if search_calls:
#                 # Signal that a search is starting
#                 search_query = search_calls[0]["args"].get("query", "")
#                 # Escape quotes and special characters
#                 safe_query = search_query.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
#                 yield f"data: {{\"type\": \"search_start\", \"query\": \"{safe_query}\"}}\n\n"
                
#         elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
#             # Search completed - send results or error
#             output = event["data"]["output"]
            
#             # Check if output is a list 
#             if isinstance(output, list):
#                 # Extract URLs from list of search results
#                 urls = []
#                 for item in output:
#                     if isinstance(item, dict) and "url" in item:
#                         urls.append(item["url"])
                
#                 # Convert URLs to JSON and yield them
#                 urls_json = json.dumps(urls)
#                 yield f"data: {{\"type\": \"search_results\", \"urls\": {urls_json}}}\n\n"
    
#     # Send an end event
#     yield f"data: {{\"type\": \"end\"}}\n\n"

# @app.get("/chat_stream/{message}")
# async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
#     return StreamingResponse(
#         generate_chat_responses(message, checkpoint_id), 
#         media_type="text/event-stream"
#     )

# # SSE - server-sent events 
# @app.get("/")
# async def root():
#     return {"message": "FastAPI is running", "endpoints": ["/chat_stream/{message}"]}
from typing import TypedDict, Annotated, Optional
from uuid import uuid4
import json
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import add_messages, StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------
# Environment & LLM Setup
# ---------------------------------------------------------------------
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("WARNING: OPENROUTER_API_KEY is not set. LLM calls will fail.")

memory = MemorySaver()


class State(TypedDict):
    messages: Annotated[list, add_messages]


search_tool = TavilySearchResults(max_results=4)
tools = [search_tool]

llm = ChatOpenAI(
    model="deepseek/deepseek-r1",
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    temperature=0.2,
)

llm_with_tools = llm.bind_tools(tools=tools)


async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [result]}


async def tools_router(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tool_node"
    return END


async def tool_node(state: State):
    """Custom tool node that handles tool calls from the LLM."""
    tool_calls = state["messages"][-1].tool_calls
    tool_messages = []

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        if tool_name == "tavily_search_results_json":
            search_results = await search_tool.ainvoke(tool_args)

            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name,
            )
            tool_messages.append(tool_message)

    return {"messages": tool_messages}


graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph = graph_builder.compile(checkpointer=memory)

# ---------------------------------------------------------------------
# FastAPI App & CORS
# ---------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or [frontend_url] in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"],
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def serialise_ai_message_chunk(chunk: AIMessageChunk) -> str:
    """
    Convert AIMessageChunk content to a plain string.
    Handles both string content and list-of-dicts content.
    """
    if not isinstance(chunk, AIMessageChunk):
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )

    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # LangChain sometimes returns [{"type": "text", "text": "..."}]
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content)


def _escape_for_json(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


# ---------------------------------------------------------------------
# SSE Generator
# ---------------------------------------------------------------------
async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    """
    Streams events to the client as Server-Sent Events (SSE).
    Types: checkpoint, content, search_start, search_results, end, error
    """

    try:
        is_new_conversation = checkpoint_id is None

        if is_new_conversation:
            new_checkpoint_id = str(uuid4())
            config = {"configurable": {"thread_id": new_checkpoint_id}}

            events = graph.astream_events(
                {"messages": [HumanMessage(content=message)]},
                version="v2",
                config=config,
            )

            # First send the checkpoint ID
            yield (
                f'data: {{"type": "checkpoint", '
                f'"checkpoint_id": "{_escape_for_json(new_checkpoint_id)}"}}\n\n'
            )
        else:
            config = {"configurable": {"thread_id": checkpoint_id}}
            events = graph.astream_events(
                {"messages": [HumanMessage(content=message)]},
                version="v2",
                config=config,
            )

        async for event in events:
            event_type = event["event"]

            if event_type == "on_chat_model_stream":
                chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
                safe_content = _escape_for_json(chunk_content)

                yield (
                    f'data: {{"type": "content", '
                    f'"content": "{safe_content}"}}\n\n'
                )

            elif event_type == "on_chat_model_end":
                output = event["data"]["output"]
                tool_calls = getattr(output, "tool_calls", []) or []
                search_calls = [
                    call
                    for call in tool_calls
                    if call.get("name") == "tavily_search_results_json"
                ]

                if search_calls:
                    search_query = search_calls[0]["args"].get("query", "")
                    safe_query = _escape_for_json(search_query)
                    yield (
                        f'data: {{"type": "search_start", '
                        f'"query": "{safe_query}"}}\n\n'
                    )

            elif event_type == "on_tool_end" and event.get("name") == "tavily_search_results_json":
                output = event["data"]["output"]

                urls = []
                if isinstance(output, list):
                    for item in output:
                        if isinstance(item, dict) and "url" in item:
                            urls.append(item["url"])

                urls_json = json.dumps(urls)
                yield f'data: {{"type": "search_results", "urls": {urls_json}}}\n\n'

        # When we exhaust events, send end
        yield 'data: {"type": "end"}\n\n'

    except Exception as e:
        # Log error server-side
        print("Error in generate_chat_responses:", repr(e))

        # Send error event to frontend
        error_msg = _escape_for_json(str(e))
        yield f'data: {{"type": "error", "error": "{error_msg}"}}\n\n'
        yield 'data: {"type": "end"}\n\n'


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/chat_stream/{message}")
async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/")
async def root():
    return {"message": "FastAPI is running", "endpoints": ["/chat_stream/{message}"]}
