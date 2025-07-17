import importlib
import pathlib
import asyncio
from typing import Callable
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, SkipValidation

from dotenv import load_dotenv
load_dotenv()

class ToolParameter(BaseModel):
    type: str
    description: str

class ToolProperties(BaseModel):
    properties: dict[str, ToolParameter]
    required: list[str] = []

class ToolFunction(BaseModel):
    name: str
    description: str
    parameters: ToolProperties

class ToolDefinition(BaseModel):
    function: ToolFunction

class ToolExecutionRequest(BaseModel):
    arguments: dict

class ToolExecutionResponse(BaseModel):
    result: str

class Tool(BaseModel):
    definition: ToolDefinition
    executor: SkipValidation[Callable]

TOOLS_REGISTRY = {}
STARTUP_HANDLERS = []
SHUTDOWN_HANDLERS = []

def discover_and_register_modules():
    """
    Dynamically discovers tools AND their lifecycle hooks from the 'tools' directory.
    """
    tools_dir = pathlib.Path(__file__).parent / "tools"
    for module_file in tools_dir.glob("*.py"):
        if module_file.name == "__init__.py":
            continue
        module_name = f"tools.{module_file.stem}"
        try:
            module = importlib.import_module(module_name)
            tools_to_register = []
            if hasattr(module, 'tool'):
                tools_to_register.append(getattr(module, 'tool'))
            elif hasattr(module, 'tools'):
                candidate = getattr(module, 'tools')
                if isinstance(candidate, (list, tuple)):
                    tools_to_register.extend(candidate)
            for tool_instance in tools_to_register:
                if isinstance(tool_instance, Tool):
                    tool_name = tool_instance.definition.function.name
                    TOOLS_REGISTRY[tool_name] = tool_instance
                    print(f"Successfully registered tool: '{tool_name}' from {module_name}")
            if hasattr(module, 'on_startup'):
                STARTUP_HANDLERS.append(getattr(module, 'on_startup'))
                print(f"Registered 'on_startup' handler from {module_name}")
            if hasattr(module, 'on_shutdown'):
                SHUTDOWN_HANDLERS.append(getattr(module, 'on_shutdown'))
                print(f"Registered 'on_shutdown' handler from {module_name}")
        except ImportError as e:
            print(f"Error importing {module_name}: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    TOOLS_REGISTRY.clear()
    STARTUP_HANDLERS.clear()
    SHUTDOWN_HANDLERS.clear()
    discover_and_register_modules()
    print("INFO:     Executing application startup handlers...")
    for handler in STARTUP_HANDLERS:
        await handler()
    yield
    print("INFO:     Executing application shutdown handlers...")
    for handler in SHUTDOWN_HANDLERS:
        await handler()

app = FastAPI(
    title="Modular MCP Server",
    description="A modular MCP server that automatically discovers and serves tools.",
    version="2.2.0",
    lifespan=lifespan
)

@app.get("/mcp/v1/tools", response_model=list[ToolDefinition], summary="MCP Tool Discovery")
async def get_tools():
    """MCP Discovery Endpoint to list all dynamically loaded tools."""
    return [tool.definition for tool in TOOLS_REGISTRY.values()]

@app.post("/mcp/v1/tools/{tool_name}:execute", response_model=ToolExecutionResponse, summary="MCP Tool Execution")
async def execute_tool(tool_name: str, request: ToolExecutionRequest):
    """MCP Execution Endpoint to run a specific tool from the registry."""
    if tool_name not in TOOLS_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    tool_executor = TOOLS_REGISTRY[tool_name].executor
    try:
        if asyncio.iscoroutinefunction(tool_executor):
            result = await tool_executor(**request.arguments)
        else:
            result = tool_executor(**request.arguments)
        return ToolExecutionResponse(result=result)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid arguments for tool '{tool_name}': {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while executing the tool: {e}")