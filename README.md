# Modular MCP Server

This is a modular, auto-discovering Model Context Protocol (MCP) server built with Python and FastAPI. It's designed to be a scalable foundation for providing tools to Large Language Models (LLMs).

## Features

-   **Auto-Discovery:** Automatically loads tools from the `/tools` directory on startup.
-   **Modular:** Tools are self-contained in their own files.
-   **Configurable:** Uses a `.env` file for all configuration.
-   **Secure:** Includes best practices like read-only database users and whitelisting.
-   **Performant:** Runs on a high-performance Unix socket and uses an async database connection pool.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd mcp
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure your environment:**
    ```bash
    cp .env.example .env
    ```
    Now, edit the `.env` file with your actual database credentials and settings.

## Running the Server

To run the server on a Unix socket:
```bash
uvicorn mcp_server:app --uds /tmp/mcp.sock
```

## Testing

You can test the running server using `curl`.

**Discover tools:**
```bash
curl --unix-socket /tmp/mcp.sock http://localhost/mcp/v1/tools | jq
```

**Execute a tool:**
```bash
curl -X POST \
  --unix-socket /tmp/mcp.sock \
  -H "Content-Type: application/json" \
  -d '{"arguments": {"timezone": "Europe/Istanbul"}}' \
  http://localhost/mcp/v1/tools/get_current_time:execute | jq
```
```

