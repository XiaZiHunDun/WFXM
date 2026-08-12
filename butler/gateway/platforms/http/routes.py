"""FastAPI routes for Butler HTTP API."""

from __future__ import annotations

from pydantic import BaseModel

from .adapter import handle_command, handle_message


class ChatRequest(BaseModel):
    message: str
    session_key: str = "default"
    external_id: str = ""


class ChatResponse(BaseModel):
    response: str


class CommandRequest(BaseModel):
    command: str
    session_key: str = "default"
    external_id: str = ""


class CommandResponse(BaseModel):
    response: str


def register_routes(app) -> None:
    """Register HTTP API routes on a FastAPI app."""

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        response = handle_message(
            request.message,
            session_key=request.session_key,
            platform="http",
            external_id=request.external_id,
        )
        return ChatResponse(response=response)

    @app.post("/api/command", response_model=CommandResponse)
    async def command(request: CommandRequest) -> CommandResponse:
        response = handle_command(
            request.command,
            session_key=request.session_key,
            platform="http",
            external_id=request.external_id,
        )
        return CommandResponse(response=response)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "butler"}
