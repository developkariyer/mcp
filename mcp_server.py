import importlib
import pathlib
from typing import Callable
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, SkipValidation

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

def discover_and_register_tools():
    """
    Dynamically discovers tools from the 'tools' directory.
    It can handle files that provide a single 'tool' object or a list/tuple of 'tools'.
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
            if not tools_to_register:
                print(f"Warning: No valid 'tool' or 'tools' object found in {module_name}")
                continue
            for tool_instance in tools_to_register:
                if isinstance(tool_instance, Tool):
                    tool_name = tool_instance.definition.function.name
                    TOOLS_REGISTRY[tool_name] = {
                        "definition": tool_instance.definition,
                        "executor": tool_instance.executor
                    }
                    print(f"Successfully registered tool: '{tool_name}' from {module_name}")
                else:
                    print(f"Warning: Found an invalid tool object in {module_name}")
        except ImportError as e:
            print(f"Error importing {module_name}: {e}")

app = FastAPI(
    title="Modular MCP Server",
    description="A modular MCP server that automatically discovers and serves tools.",
    version="2.0.0"
)

@app.on_event("startup")
def on_startup():
    """Register tools when the application starts up."""
    TOOLS_REGISTRY.clear()
    discover_and_register_tools()

@app.get("/mcp/v1/tools", response_model=list[ToolDefinition], summary="MCP Tool Discovery")
async def get_tools():
    """MCP Discovery Endpoint to list all dynamically loaded tools."""
    return [tool["definition"] for tool in TOOLS_REGISTRY.values()]


@app.post("/mcp/v1/tools/{tool_name}:execute", response_model=ToolExecutionResponse, summary="MCP Tool Execution")
async def execute_tool(tool_name: str, request: ToolExecutionRequest):
    """MCP Execution Endpoint to run a specific tool from the registry."""
    if tool_name not in TOOLS_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    tool_executor = TOOLS_REGISTRY[tool_name]["executor"]
    try:
        result = tool_executor(**request.arguments)
        return ToolExecutionResponse(result=result)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid arguments for tool '{tool_name}': {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred while executing the tool: {e}")
