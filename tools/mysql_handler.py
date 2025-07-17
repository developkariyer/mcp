import os
import asyncio
import aiomysql
import json
from mcp_server import Tool, ToolDefinition, ToolFunction, ToolProperties, ToolParameter

ALLOWED_TABLES_CONFIG = None
db_tables_env = os.getenv("DB_TABLES")
if db_tables_env:
    try:
        ALLOWED_TABLES_CONFIG = json.loads(db_tables_env)
        if not isinstance(ALLOWED_TABLES_CONFIG, dict):
            print(f" MCP-Warning :: DB_TABLES in .env is not a valid JSON object (dict). Ignoring whitelist.")
            ALLOWED_TABLES_CONFIG = None
    except json.JSONDecodeError:
        print(f" MCP-Warning :: Could not parse DB_TABLES in .env. It's not valid JSON. Ignoring whitelist.")
        ALLOWED_TABLES_CONFIG = None

DB_POOL = None

async def on_startup():
    """Creates the database connection pool when the application starts."""
    global DB_POOL
    print("INFO:     Initializing MySQL connection pool...")
    try:
        DB_POOL = await aiomysql.create_pool(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            db=os.getenv("DB_NAME"),
            autocommit=True
        )
        print("INFO:     MySQL connection pool initialized successfully.")
    except Exception as e:
        print(f"FATAL: Could not create database connection pool: {e}")

async def on_shutdown():
    """Closes the database connection pool when the application shuts down."""
    global DB_POOL
    if DB_POOL:
        DB_POOL.close()
        await DB_POOL.wait_closed()
        print("INFO:     MySQL connection pool closed.")

async def _get_mysql_schema_information(table_name: str | None = None) -> str:
    """Retrieves and formats allowlisted schema information."""
    if not DB_POOL:
        return "Error: Database connection is not available."
    query = "SELECT TABLE_NAME, TABLE_COMMENT, COLUMN_NAME, COLUMN_COMMENT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s"
    params = [os.getenv("DB_NAME")]
    if table_name:
        query += " AND TABLE_NAME = %s"
        params.append(table_name)
    query += " ORDER BY TABLE_NAME, ORDINAL_POSITION;"
    async with DB_POOL.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, tuple(params))
            results = await cursor.fetchall()
    schema_map = {}
    for row in results:
        t_name = row['TABLE_NAME']
        if ALLOWED_TABLES_CONFIG:
            if t_name not in ALLOWED_TABLES_CONFIG: continue
            allowed_cols = ALLOWED_TABLES_CONFIG[t_name]
            c_name = row['COLUMN_NAME']
            if "*" not in allowed_cols and c_name not in allowed_cols: continue
        if t_name not in schema_map:
            schema_map[t_name] = {"table_comment": row['TABLE_COMMENT'], "columns": []}
        schema_map[t_name]['columns'].append(
            {"column_name": row['COLUMN_NAME'], "column_comment": row['COLUMN_COMMENT']})
    if not schema_map:
        return "No schema information found for the tables/columns in the whitelist."
    return json.dumps(schema_map, indent=2)

FORBIDDEN_KEYWORDS = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'GRANT', 'REVOKE'}

async def _run_mysql_query(query: str) -> str:
    """Executes a read-only SQL query."""
    if not DB_POOL:
        return "Error: Database connection is not available."
    if any(keyword in query.upper().split() for keyword in FORBIDDEN_KEYWORDS):
        return "Error: Query contains forbidden keywords. Only SELECT statements are allowed."
    try:
        async with DB_POOL.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                timeout = int(os.getenv("DB_QUERY_TIMEOUT", 10))
                await asyncio.wait_for(cursor.execute(query), timeout=timeout)
                result = await cursor.fetchall()
                return json.dumps(result, default=str)
    except asyncio.TimeoutError:
        return f"Error: Query timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing query: {e}"

schema_tool_def = ToolDefinition(
    function=ToolFunction(
        name="get_mysql_schema_information",
        description="Retrieves the schema for whitelisted database tables, essential for constructing correct queries.",
        parameters=ToolProperties(properties={
            "table_name": ToolParameter(type="string", description="Optional. The specific table to get schema for.")})
    )
)

query_tool_def = ToolDefinition(
    function=ToolFunction(
        name="run_mysql_query",
        description="Executes a read-only SQL SELECT query and returns the result as a JSON array.",
        parameters=ToolProperties(
            properties={"query": ToolParameter(type="string", description="The SQL SELECT statement to execute.")},
            required=["query"])
    )
)

tools = [
    Tool(definition=schema_tool_def, executor=_get_mysql_schema_information),
    Tool(definition=query_tool_def, executor=_run_mysql_query)
]