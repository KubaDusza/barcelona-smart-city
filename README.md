# Barcelona Smart City — AI-Powered City Data Platform

**UPC CCBDA · Team 11 · May 2026**

A live city data infrastructure built entirely on AWS that makes six domains of real-time Barcelona urban data accessible to any AI assistant through the Model Context Protocol (MCP). The system ingests data continuously from Barcelona's public open APIs, stores it in Amazon DynamoDB, and exposes it via an MCP server deployed on AWS Lambda and API Gateway.

**Live chat app:** [dhioxm566jvi3.cloudfront.net](https://dhioxm566jvi3.cloudfront.net)  
**MCP endpoint:** `https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp`  
Connect from claude.ai, Claude Desktop, or VS Code to get Barcelona city data tools in any AI conversation.

---

## Team

| Name | Contribution |
|------|-------------|
| Jakub Dusza | Mobility (Bicing + Transit), MCP server, AWS infrastructure, public chat app |
| Mark Welf Atzberger | Air quality vertical, final report |
| Jia Lyu | Weather vertical, presentation |
| José Ricardo Arias Pérez | UV + Pollen verticals, Telegram bot |

---

## What a User Can Ask

- "Are there Bicing bikes available near Sagrada Família right now?"
- "Is today a good day to go for a run in Eixample?" (checks weather + UV + air quality + pollen)
- "What was the worst hour for NO₂ pollution in Gràcia this week?"
- "How do I get from UPC Campus Nord to Barceloneta by public transit?"
- "I'm allergic to grass pollen — how bad is today?"

---

## Project Structure

```
.
├── aws/                          # Production AWS infrastructure
│   ├── lambdas/
│   │   ├── bicing_ingest/        # Every 5 min → BicingStations
│   │   ├── air_quality_ingest/   # Hourly → AirQualityReadings
│   │   ├── weather_ingest/       # Hourly → WeatherData
│   │   ├── uv_ingest/            # Hourly → UVData
│   │   ├── pollen_ingest/        # Hourly → PollenData
│   │   └── chat/                 # Bedrock agentic loop (public chat API)
│   ├── policies/                 # IAM policy JSON files (least-privilege per Lambda)
│   ├── scripts/
│   │   ├── load_gtfs.py          # One-time: loads 3,453 TMB stops into TransitStops
│   │   └── verify_data.py        # Checks all tables have data
│   ├── setup.sh                  # Creates DynamoDB tables, IAM roles, S3
│   ├── deploy.sh                 # Packages + deploys all Lambdas + API Gateway
│   ├── pause.sh                  # Disable EventBridge schedules
│   └── teardown.sh               # Delete all AWS resources
│
├── webapp/                       # Public chat app (S3 + CloudFront CDN)
│   ├── index.html                # Single-page app: interactive map, AI chat, charts, routes
│   └── icon.svg                  # App icon
│
├── telegram-bot/                 # Telegram bot Lambda
│   ├── lambda_function.py
│   └── README.md
│
├── mcp_server.py                 # MCP server source (deployed as smart-city-mcp Lambda)
├── transit_route_tool.py         # Transitous routing wrapper (used by mcp_server)
├── requirements.txt              # Python dependencies (for local-demo)
│
├── dev/                          # Development artifacts
│   ├── exploration/              # Design-phase API research, prototypes, findings
│   └── local-demo/              # Local FastAPI dev server (Leaflet map + streaming AI)
│
└── docs/                         # Documentation, data, deliverables
    ├── gtfs/                     # Barcelona TMB GTFS feed (static transit data)
    ├── research/                 # Tutorial materials (Bedrock, MCP)
    ├── SmartCity_v4.pptx         # Final presentation
    ├── IQL_final_report.pdf      # Final report
    ├── AWS_SETUP.md              # AWS setup guide
    └── *.md                      # Per-vertical docs, planning, notes
```

---

## Architecture

```
DATA SOURCES (free, no API keys needed)
  Bicing GBFS · TMB GTFS · Open Data BCN · Open-Meteo · currentuvindex.com
                                    │
                                    ▼
INGESTION LAYER (AWS)
  EventBridge Schedules → Lambda ×5
    • bicing_ingest      (every 5 min)  → BicingStations
    • air_quality_ingest (every 1 hr)   → AirQualityReadings
    • weather_ingest     (every 1 hr)   → WeatherData
    • uv_ingest          (every 1 hr)   → UVData
    • pollen_ingest      (every 1 hr)   → PollenData
  One-time: load_gtfs.py              → TransitStops (3,453 stops)
                                    │
                                    ▼
STORAGE LAYER
  DynamoDB (eu-west-1, on-demand capacity, 30-day TTL)
    • BicingStations  • TransitStops  • ScheduleCache
    • AirQualityReadings  • WeatherData  • UVData  • PollenData
                                    │
                                    ▼
SERVING LAYER (MCP Server)
  API Gateway (HTTP API) → Lambda: mcp_server (Python, FastMCP)
    • 11 tools exposed via JSON-RPC 2.0
    • Reads from DynamoDB + calls live APIs (Transitous, UV, Pollen)
    • Stateless — each request is independent Lambda invocation
                                    │
                        ┌───────────┴───────────┐
                        ▼                       ▼
EXTERNAL MCP CLIENTS          BEDROCK CHAT APPLICATION
  • claude.ai                   CloudFront → S3 (static HTML/JS)
  • Claude Desktop              API Gateway → Lambda: smart-city-chat
  • VS Code                       bedrock-runtime.invoke_model (Claude Haiku)
  • Telegram Bot                  agentic loop (up to 8 rounds)
                                  HTTP POST → MCP server (tool calls)
```

---

## MCP Tools

| Tool | Domain | Data Source | Update Cadence |
|------|--------|-------------|----------------|
| `get_bicing` | Mobility | Bicing GBFS (citybik.es) | Every 5 min |
| `get_bicing_history` | Mobility | DynamoDB (BicingStations) | Every 5 min |
| `get_transit_nearby` | Mobility | DynamoDB (TransitStops) | Static GTFS |
| `get_transit_route` | Mobility | Transitous open router | Per request |
| `get_air_quality` | Air Quality | DynamoDB (AirQualityReadings) | Hourly |
| `get_air_quality_history` | Air Quality | DynamoDB (AirQualityReadings) | Hourly |
| `get_weather` | Weather | DynamoDB (WeatherData) | Hourly |
| `get_uv_index` | UV | currentuvindex.com (CAMS) | Per request |
| `get_uv_history` | UV | DynamoDB (UVData) | Hourly |
| `get_pollen` | Pollen | Open-Meteo CAMS | Per request |
| `get_pollen_history` | Pollen | DynamoDB (PollenData) | Hourly |

---

## AWS Resources

| Resource | Name | Purpose |
|----------|------|---------|
| DynamoDB (×7) | BicingStations, TransitStops, … | City data storage |
| Lambda (×5 ingest) | smart-city-*-ingest | Data collectors |
| Lambda (×1 MCP) | smart-city-mcp | MCP server handler |
| Lambda (×1 chat) | smart-city-chat | Bedrock agentic loop |
| API Gateway (×2) | MCP + chat endpoints | HTTPS routing |
| EventBridge (×6) | *-ingest-schedule | Trigger schedules |
| S3 | barcelona-smart-city-site-* | Static frontend |
| CloudFront | E2LPOSVMFTXZ34 | CDN + HTTPS |
| AgentCore Gateway | barcelona-smart-city-xwyxovrhex | Managed MCP proxy |
| IAM roles | smart-city-lambda-*-role | Least-privilege per Lambda |

Account `724440691846`, region `eu-west-1`. Fully serverless, pay-per-request, ~$0 at idle.

---

## User-Facing Surfaces

1. **Public web chat app** ([live](https://dhioxm566jvi3.cloudfront.net)) — interactive Leaflet map with pins/routes, Chart.js visualizations, AI chatbot with tool-use. Mobile-friendly. Geolocation-aware.
2. **MCP endpoint** (`https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp`) — any MCP-compatible AI client connects directly and gains all 11 city data tools. See [Connecting via MCP](#connecting-via-mcp) below.
3. **Telegram bot** — conversational interface via Telegram, backed by the same MCP tools.
4. **Local demo app** (`dev/local-demo/`) — FastAPI server with streaming responses, route planner, city data overlays. For development/presentations.

### Connecting via MCP

Any AI assistant that supports MCP can use the Barcelona Smart City tools. No API key needed.

**claude.ai (web):**
1. Open [claude.ai](https://claude.ai) and go to Settings → Integrations
2. Click "Add integration" → "Custom MCP server"
3. Enter the endpoint URL: `https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp`
4. Give it a name (e.g. "Barcelona Smart City")
5. Done — Claude now has access to all 11 city data tools in any conversation

**Claude Desktop:**
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "barcelona-smart-city": {
      "url": "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"
    }
  }
}
```

**VS Code (Claude Code / Copilot):**
Add to your project's `.mcp.json`:
```json
{
  "servers": {
    "barcelona-smart-city": {
      "url": "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"
    }
  }
}
```

---

## Quick Start

### Run the local demo
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
bash dev/local-demo/run.sh
# Open http://localhost:8765
```

### Deploy from scratch
```bash
source venv/bin/activate
bash aws/setup.sh                    # creates tables + IAM roles
bash aws/deploy.sh all               # deploys all Lambdas + API Gateway
python3 aws/scripts/load_gtfs.py     # loads transit stops

# Seed data immediately:
for fn in bicing-ingest air-quality-ingest weather-ingest uv-ingest pollen-ingest; do
  aws lambda invoke --function-name smart-city-$fn --payload '{}' --region eu-west-1 /tmp/out.json
done
```

### Connect an MCP client
Add to your Claude Desktop config (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "barcelona-smart-city": {
      "url": "https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp"
    }
  }
}
```

---

## Data Sources

| Domain | Source | API | Key Required |
|--------|--------|-----|:---:|
| Bicing | citybik.es GBFS mirror | `api.citybik.es/v2/networks/bicing` | No |
| Transit stops | TMB GTFS feed | Static file load | No |
| Transit routing | Transitous | `api.transitous.org/api/v1/plan` | No |
| Air quality | Open Data BCN (XVPCA) | CKAN datastore API | No |
| Weather | Open-Meteo | `api.open-meteo.com/v1/forecast` | No |
| UV index | currentuvindex.com | REST API (CAMS model) | No |
| Pollen | Open-Meteo CAMS | Air quality endpoint | No |

9 XVPCA air quality stations: Poblenou, Sants, Eixample, Gracia, Ciutadella, Vall Hebron, Palau Reial, Observatori Fabra, Navas.

---

## DynamoDB Schema

All tables use on-demand billing, 30-day TTL, and append-only writes.

- **BicingStations**: PK `station_id`, SK `updated_at` (Unix epoch). GSI `LatIndex` for spatial queries.
- **TransitStops**: PK `stop_id`, SK `feed_ver`. GSI `LatBucketIndex` for spatial queries.
- **AirQualityReadings**: PK `station_pollutant` (e.g. `43_NO2`), SK `hour_ts` (YYYYMMDDHH).
- **WeatherData**: PK `barcelona_center`, SK Unix timestamp.
- **UVData**: PK `barcelona_center`, SK `hour_ts`.
- **PollenData**: PK `barcelona_<species>`, SK `hour_ts`.
- **ScheduleCache**: Reserved for future GTFS schedule caching.
