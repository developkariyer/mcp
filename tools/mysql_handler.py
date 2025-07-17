# tools/mysql_handler.py

import os
import asyncio
import aiomysql
import json
from mcp_server import Tool, ToolDefinition, ToolFunction, ToolProperties, ToolParameter

# --- 1. Whitelist Configuration (NEW) ---
# This block runs ONCE when the module is imported at server startup.
ALLOWED_TABLES_CONFIG = None
db_tables_env = os.getenv("DB_TABLES")
if db_tables_env:
    try:
        ALLOWED_TABLES_CONFIG = json.loads(db_tables_env)
        # We expect a dictionary, e.g., {"table_name": ["col1", "col2"]}
        if not isinstance(ALLOWED_TABLES_CONFIG, dict):
            print(f" MCP-Warning :: DB_TABLES in .env is not a valid JSON object (dict). Ignoring whitelist.")
            ALLOWED_TABLES_CONFIG = None
    except json.JSONDecodeError:
        # This handles the "broken value" case and throws the requested warning.
        print(f" MCP-Warning :: Could not parse DB_TABLES in .env. It's not valid JSON. Ignoring whitelist.")
        ALLOWED_TABLES_CONFIG = None

# --- 2. Database Connection Pool ---
# This remains unchanged.
DB_POOL = None
async def get_db_pool():
    global DB_POOL
    if DB_POOL is None:
        try:
            DB_POOL = await aiomysql.create_pool(
                host=os.getenv("DB_HOST", "127.0.0.1"),
                port=int(os.getenv("DB_PORT", 3306)),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASS"),
                db=os.getenv("DB_NAME"),
                autocommit=True
            )
        except Exception as e:
            print(f"FATAL: Could not create database connection pool: {e}")
    return DB_POOL

# --- 3. Tool Logic (get_mysql_schema_information is updated) ---

async def _get_mysql_schema_information(table_name: str | None = None) -> str:
    """
    Retrieves and formats whitelisted schema information (table and column comments).
    """
    pool = await get_db_pool()
    if not pool:
        return "Error: Database connection is not available."

    # The base query remains efficient, fetching all data first.
    # We will filter it in Python based on our config.
    query = """
        SELECT 
            TABLE_NAME, TABLE_COMMENT, COLUMN_NAME, COLUMN_COMMENT 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = %s
    """
    params = [os.getenv("DB_NAME")]
    if table_name:
        query += " AND TABLE_NAME = %s"
        params.append(table_name)
    
    query += " ORDER BY TABLE_NAME, ORDINAL_POSITION;"

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, tuple(params))
            results = await cursor.fetchall()

    if not results:
        return f"No schema information found for database '{os.getenv('DB_NAME')}'."

    # --- Whitelist Filtering Logic (NEW) ---
    schema_map = {}
    for row in results:
        t_name = row['TABLE_NAME']
        
        # If a whitelist exists, check if the table is allowed
        if ALLOWED_TABLES_CONFIG:
            if t_name not in ALLOWED_TABLES_CONFIG:
                continue # Skip this table entirely
            
            allowed_cols = ALLOWED_TABLES_CONFIG[t_name]
            c_name = row['COLUMN_NAME']
            
            # Check if the column is allowed (either by name or by wildcard "*")
            if "*" not in allowed_cols and c_name not in allowed_cols:
                continue # Skip this column

        # If we passed the filters (or if there's no whitelist), add the info
        if t_name not in schema_map:
            schema_map[t_name] = {
                "table_comment": row['TABLE_COMMENT'],
                "columns": []
            }
        schema_map[t_name]['columns'].append({
            "column_name": row['COLUMN_NAME'],
            "column_comment": row['COLUMN_COMMENT']
        })
    
    if not schema_map:
        return "No schema information found for the tables and columns specified in the whitelist."

    return json.dumps(schema_map, indent=2)


# --- (_run_mysql_query function remains completely unchanged) ---
FORBIDDEN_KEYWORDS = {'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'GRANT', 'REVOKE'}
async def _run_mysql_query(query: str) -> str:
    # ... (no changes here) ...
    if any(keyword in query.upper().split() for keyword in FORBIDDEN_KEYWORDS):
        return "Error: Query contains forbidden keywords. Only SELECT statements are allowed."
    pool = await get_db_pool()
    if not pool:
        return "Error: Database connection is not available."
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                timeout = int(os.getenv("DB_QUERY_TIMEOUT", 10))
                await asyncio.wait_for(cursor.execute(query), timeout=timeout)
                result = await cursor.fetchall()
                return json.dumps(result, default=str)
    except asyncio.TimeoutError:
        return f"Error: Query timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing query: {e}"

# --- 4. Tool Definitions (no changes needed) ---
schema_tool_def = ToolDefinition(#...
    function=ToolFunction(
        name="get_mysql_schema_information",
        description="Retrieves the schema (table and column comments) for whitelisted database tables, essential for constructing correct queries.",
        parameters=ToolProperties(
            properties={
                "table_name": ToolParameter(
                    type="string", 
                    description="Optional. The specific table to get schema for. If omitted, returns schema for all allowed tables."
                )
            }
        )
    )
)
query_tool_def = ToolDefinition(#...
    function=ToolFunction(
        name="run_mysql_query",
        description="Executes a read-only SQL SELECT query against the database and returns the result as a JSON array.",
        parameters=ToolProperties(
            properties={
                "query": ToolParameter(type="string", description="The SQL SELECT statement to execute.")
            },
            required=["query"]
        )
    )
)

# --- 5. The Registration Object (no changes needed) ---
tools = [
    Tool(definition=schema_tool_def, executor=_get_mysql_schema_information),
    Tool(definition=query_tool_def, executor=_run_mysql_query)
]
