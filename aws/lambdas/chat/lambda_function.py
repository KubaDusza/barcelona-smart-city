"""
Barcelona Smart City — chat Lambda
Agentic loop: Claude (bedrock-runtime) + tools via our MCP server.
"""
import json
import os
import urllib.request
import urllib.error
import boto3

MCP_URL  = "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"
MODEL_ID = os.environ.get("MODEL_ID", "eu.anthropic.claude-haiku-4-5-20251001-v1:0")
REGION   = os.environ.get("AWS_REGION", "eu-west-1")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Content-Type": "application/json",
}

SYSTEM = """You are a helpful Barcelona city assistant. You have access to live city data tools covering bikes, transit, air quality, weather, UV index, and pollen.

Key Barcelona locations (use these coordinates when mentioned):
- Sagrada Família: 41.4036, 2.1744
- Plaça Catalunya: 41.3869, 2.1699
- Barceloneta: 41.3807, 2.1897
- UPC Campus Nord: 41.3887, 2.1125
- Gràcia: 41.4025, 2.1567
- Sants station: 41.3794, 2.1405
- Eixample: 41.3918, 2.1596
- Passeig de Gràcia: 41.3927, 2.1649
- Born: 41.3851, 2.1820
- Poble Sec: 41.3733, 2.1599

When asked about outdoor activities, always check weather + UV + air quality + pollen together.
Be concise and conversational. Use plain language — avoid raw numbers without context.
Respond in the same language the user writes in."""


def mcp_post(body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        MCP_URL, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


_tools_cache: list | None = None


def get_bedrock_tools() -> list:
    global _tools_cache
    if _tools_cache is not None:
        return _tools_cache

    mcp_post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "clientInfo": {"name": "barcelona-chat", "version": "1.0"},
                         "capabilities": {}}})

    resp = mcp_post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    mcp_tools = resp.get("result", {}).get("tools", [])

    _tools_cache = [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
        }
        for t in mcp_tools
    ]
    return _tools_cache


def call_mcp_tool(name: str, arguments: dict) -> str:
    # Re-initialize per call (MCP server is stateless Lambda)
    mcp_post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "clientInfo": {"name": "barcelona-chat", "version": "1.0"},
                         "capabilities": {}}})

    resp = mcp_post({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                     "params": {"name": name, "arguments": arguments}})

    content = resp.get("result", {}).get("content", [])
    if resp.get("result", {}).get("isError"):
        return json.dumps({"error": content[0].get("text", "tool error") if content else "tool error"})
    return content[0].get("text", "{}") if content else "{}"


def agentic_loop(user_message: str, history: list) -> tuple[str, list]:
    tools = get_bedrock_tools()
    messages = history + [{"role": "user", "content": user_message}]
    tool_calls_log = []

    for _ in range(8):  # max 8 rounds
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "system": SYSTEM,
            "tools": tools,
            "messages": messages,
        }
        resp = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
        stop_reason = result.get("stop_reason")
        content = result.get("content", [])

        if stop_reason != "tool_use":
            text = next((b["text"] for b in content if b["type"] == "text"), "")
            return text, tool_calls_log

        tool_results = []
        for block in content:
            if block["type"] != "tool_use":
                continue
            tool_name  = block["name"]
            tool_input = block["input"]
            result_text = call_mcp_tool(tool_name, tool_input)
            try:
                result_parsed = json.loads(result_text)
            except Exception:
                result_parsed = result_text
            tool_calls_log.append({
                "tool": tool_name,
                "input": tool_input,
                "result": result_parsed,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": result_text,
            })

        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user",      "content": tool_results})

    return "Sorry, I hit the tool call limit. Please try a simpler question.", tool_calls_log


def lambda_handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method")
              or event.get("httpMethod", "POST"))

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
        user_message = body.get("message", "").strip()
        history      = body.get("history", [])

        if not user_message:
            return {"statusCode": 400, "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "message is required"})}

        response_text, tool_calls = agentic_loop(user_message, history)

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"response": response_text, "tool_calls": tool_calls}),
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
