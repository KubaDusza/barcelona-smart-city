"""
Barcelona Smart City — chat Lambda
Agentic loop: Claude (bedrock-runtime) + data tools via MCP server + virtual display tools.
"""
import json
import math
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

SYSTEM = """You are a Barcelona city assistant with live data tools AND map/chart display tools.

## Data tools
You have access to live city data: Bicing bikes, transit routing, air quality, weather, UV, pollen.

## Display tools (ALWAYS use these to show results visually)
- **show_on_map**: Add pins, show routes, or pan the map. Call this whenever your answer involves locations.
- **show_chart**: Display a chart (bar, line, doughnut). Call this for comparisons, trends, or multi-value data.

NOTE: For transit routes (get_transit_route), the route is AUTOMATICALLY drawn on the map with clickable route options in the chat. You do NOT need to call show_on_map for routes — just call get_transit_route and the UI handles it. You should still call show_on_map to pin the origin and destination.

## Key Barcelona coordinates
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

## Rules — STRICT, follow exactly
1. ALWAYS VISUALIZE. Every response MUST call show_chart and/or show_on_map. No exceptions. If you have numeric data, make a chart. If you have locations, pin the map. If you have both, do both.
2. ALWAYS call show_on_map with action "clear" FIRST before adding new pins — start fresh each turn. Only skip the clear if the user explicitly says "also show" or "add to the map".
3. Your text reply MUST be 2-3 sentences MAX. Reference the visualization: "Check the chart below — UV peaks at 9 around noon. Wear SPF 50 if you're out 10am-4pm." NEVER write markdown tables, numbered lists, or bullet points that duplicate visualized data.
4. For transit routes: just call get_transit_route. The route cards and map polylines are generated automatically. Then pin origin (green) and destination (red) with show_on_map.
5. For outdoor activity questions, check weather + UV + air quality + pollen together, then make a multi-dataset chart comparing them.
6. Respond in the same language the user writes in.
7. Use colors: green (#2d7d46) for good/safe, red (#e63946) for bad/dangerous, blue (#2563eb) for neutral/info, orange (#f4a261) for moderate/warning.
8. Chart design: use meaningful labels, include units. For time-series (UV forecast, pollen forecast), use line charts. For comparing stations/locations, use bar charts. For proportions, use doughnut.
9. NEVER write long paragraphs. The chart and map ARE your answer. Text is only for interpretation and actionable advice that can't be shown visually.
10. Only ONE chart can be displayed at a time. If you have multiple datasets (e.g. UV + pollen), combine them into ONE chart with multiple datasets. Never call show_chart twice — the second call replaces the first."""

DISPLAY_TOOLS = [
    {
        "name": "show_on_map",
        "description": "Control the interactive map. Actions: 'clear' (remove all markers/routes), 'add_pins' (add location markers), 'pan_to' (move map view to a location). Do NOT use for transit routes — those are drawn automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["clear", "add_pins", "pan_to"],
                    "description": "The map action to perform"
                },
                "pins": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"},
                            "label": {"type": "string"},
                            "color": {"type": "string", "description": "CSS color, e.g. '#e63946' for red, '#2d7d46' for green, '#2563eb' for blue"}
                        },
                        "required": ["lat", "lon", "label"]
                    },
                    "description": "Array of pins to add (for action 'add_pins')"
                },
                "lat": {"type": "number", "description": "Latitude for pan_to"},
                "lon": {"type": "number", "description": "Longitude for pan_to"},
                "zoom": {"type": "integer", "description": "Zoom level for pan_to (default 14)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "show_chart",
        "description": "Display a chart below the map. Supports bar, line, and doughnut chart types. Use for comparisons, trends, or multi-value data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "doughnut"],
                    "description": "Type of chart"
                },
                "title": {
                    "type": "string",
                    "description": "Chart title"
                },
                "data": {
                    "type": "object",
                    "description": "Chart.js data object with 'labels' array and 'datasets' array. Each dataset has 'label', 'data' (number array), and optionally 'backgroundColor'.",
                    "properties": {
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "datasets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "data": {"type": "array", "items": {"type": "number"}},
                                    "backgroundColor": {},
                                    "borderColor": {"type": "string"},
                                    "fill": {"type": "boolean"}
                                }
                            }
                        }
                    }
                }
            },
            "required": ["chart_type", "title", "data"]
        }
    }
]

DISPLAY_TOOL_NAMES = {t["name"] for t in DISPLAY_TOOLS}

MODE_COLORS = {
    "walk": "#6b7280",
    "subway": "#7c3aed",
    "bus": "#2563eb",
    "tram": "#059669",
    "rail": "#b45309",
}

LINE_COLORS = {
    "L1": "#e63946", "L2": "#9b59b6", "L3": "#2d7d46", "L4": "#f4a261",
    "L5": "#2563eb", "L6": "#7c3aed", "L7": "#b45309", "L8": "#ec4899",
    "L9": "#f97316", "L9N": "#f97316", "L9S": "#f97316",
    "L10": "#06b6d4", "L10N": "#06b6d4", "L10S": "#06b6d4",
    "L11": "#84cc16",
}


def decode_polyline(encoded, precision=6):
    """Decode a Transitous encoded polyline (precision 6) to [[lat, lon], ...]."""
    inv = 1.0 / (10 ** precision)
    decoded = []
    previous = [0, 0]
    i = 0
    while i < len(encoded):
        for dim in range(2):
            shift = 0
            result = 0
            while True:
                b = ord(encoded[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            if result & 1:
                result = ~result
            result >>= 1
            previous[dim] += result
        decoded.append([previous[0] * inv, previous[1] * inv])
    return decoded


def extract_route_data(result_parsed):
    """Extract route visualization data from a get_transit_route result."""
    routes = result_parsed.get("routes", [])
    if not routes:
        return None

    route_options = []
    for idx, route in enumerate(routes):
        legs_data = []
        for leg in route.get("legs", []):
            mode = leg.get("mode", "walk")
            line = leg.get("line", "")
            polyline_enc = leg.get("_polyline")
            latlngs = decode_polyline(polyline_enc) if polyline_enc else []

            color = LINE_COLORS.get(line, MODE_COLORS.get(mode, "#2563eb"))
            dashed = mode == "walk"

            legs_data.append({
                "mode": mode,
                "line": line,
                "headsign": leg.get("headsign", ""),
                "from": leg.get("from", ""),
                "to": leg.get("to", ""),
                "duration_min": leg.get("duration_min", 0),
                "distance_m": leg.get("distance_m", 0),
                "stops": leg.get("stops", 0),
                "latlngs": latlngs,
                "color": color,
                "dashed": dashed,
            })

        route_options.append({
            "index": idx,
            "total_min": route.get("total_min"),
            "transfers": route.get("transfers", 0),
            "legs": legs_data,
        })

    return {"type": "routes", "routes": route_options}


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
    ] + DISPLAY_TOOLS

    return _tools_cache


def call_mcp_tool(name: str, arguments: dict) -> str:
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


def agentic_loop(user_message: str, history: list, user_location: dict | None = None) -> tuple[str, list, list]:
    tools = get_bedrock_tools()
    messages = history + [{"role": "user", "content": user_message}]
    tool_calls_log = []
    ui_commands = []

    system = SYSTEM
    if user_location and "lat" in user_location and "lon" in user_location:
        system += (
            f"\n\nUSER'S CURRENT LOCATION: lat={user_location['lat']:.5f}, lon={user_location['lon']:.5f} "
            f"(GPS from browser). Use these coordinates as origin when the user says "
            f"'my location', 'from here', 'how do I get to...', or similar without specifying an origin."
        )

    for _ in range(8):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": system,
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
            return text, tool_calls_log, ui_commands

        tool_results = []
        for block in content:
            if block["type"] != "tool_use":
                continue
            tool_name = block["name"]
            tool_input = block["input"]

            if tool_name in DISPLAY_TOOL_NAMES:
                if tool_name == "show_on_map":
                    ui_commands.append({"type": "map", "action": tool_input.get("action"), **tool_input})
                elif tool_name == "show_chart":
                    ui_commands.append({"type": "chart", **tool_input})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": json.dumps({"status": "displayed"}),
                })
            else:
                result_text = call_mcp_tool(tool_name, tool_input)
                try:
                    result_parsed = json.loads(result_text)
                except Exception:
                    result_parsed = result_text

                # Auto-generate route visualization for transit routes
                if tool_name == "get_transit_route" and isinstance(result_parsed, dict):
                    route_data = extract_route_data(result_parsed)
                    if route_data:
                        ui_commands.append(route_data)

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
        messages.append({"role": "user", "content": tool_results})

    return "Sorry, I hit the tool call limit. Please try a simpler question.", tool_calls_log, ui_commands


def lambda_handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method")
              or event.get("httpMethod", "POST"))

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
        user_message = body.get("message", "").strip()
        history = body.get("history", [])
        user_location = body.get("user_location")

        if not user_message:
            return {"statusCode": 400, "headers": CORS_HEADERS,
                    "body": json.dumps({"error": "message is required"})}

        response_text, tool_calls, ui_commands = agentic_loop(user_message, history, user_location)

        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "response": response_text,
                "tool_calls": tool_calls,
                "ui_commands": ui_commands,
            }),
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": str(e)}),
        }
