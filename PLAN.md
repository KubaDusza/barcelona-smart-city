# Barcelona Smart City — Final Presentation Plan
**UPC CCBDA · Team 11 · Deadline: 2026-05-29**

---

## The story we're telling

> **"We built a live Barcelona city data platform and showed that one standard data layer can power multiple real AI applications — a web dashboard where an AI agent controls an interactive map in real time, and a Telegram bot for on-the-go city queries — all running on AWS with zero proprietary lock-in."**

The arc:
1. **Data layer** — 6 live data types (Bicing, transit, air quality, weather, UV, pollen), ingested on AWS, stored in DynamoDB, exposed as an MCP server. Already done and running.
2. **Any AI can use it** — we demonstrated this with claude.ai connecting to our MCP endpoint and answering real questions. The data layer is model-agnostic.
3. **Now we build our own AI applications on top** — using AWS Bedrock. Two real apps:
   - A **web dashboard** where an AI agent has live city data *and* can control the map (show routes, drop pins, overlay data layers)
   - A **Telegram bot** where users can ask city questions and subscribe to air quality / pollen alerts
4. **Why Bedrock?** We're fully inside AWS. Bedrock gives us Claude (or any foundation model) without model hosting, billing, or auth management — and Bedrock AgentCore lets us wire our MCP server as the agent's toolset in a few lines of config.

---

## How Bedrock Agents work (technical briefing)

Bedrock AgentCore (GA October 2025) is AWS's managed agent orchestration layer. You give it an instruction prompt and a set of tools; it handles the reasoning loop — deciding which tools to call, calling them, and assembling a final answer.

The key point for us: **AgentCore Gateway supports MCP servers natively**. That means our existing MCP endpoint can be wired directly into a Bedrock Agent with no rewiring of our data layer. Setup effort is roughly 1–2 hours for a working agent.

```
User input
    │
    ▼
Bedrock Agent (instruction prompt + model)
    │  decides which tool to call, in a loop
    ▼
AgentCore Gateway ──► our MCP server
                         └── 11 tools → DynamoDB / live APIs
    │
    ▼
Answer streamed back to the calling app
```

---

## What we're building

### App 1 — AI Map Dashboard (web app)

A public-facing website where a chatbot has live city data *and can control the map*. The key differentiator from the current demo is that the AI doesn't just reply with text — it acts on the map and generates visual output in response to natural language.

**Required:**
- Uses AWS Bedrock (any model) and our MCP server
- Has an interactive map the AI can control: show locations, routes, and data overlays
- AI can generate dynamic dashboards — charts, metric cards — in response to a query
- Publicly hosted on AWS (not running locally)

**Nice to have:**
- Conversation memory across sessions
- Bedrock Guardrails (block off-topic queries)
- RAG over static Barcelona neighbourhood info

---

### App 2 — Telegram Bot *(proposed for José)*

A Telegram bot users can message to ask about Barcelona city conditions, plus an optional alert subscription system.

**Required:**
- Uses AWS Bedrock and our MCP server
- Users can send messages and get real city data answers
- Deployed publicly (not running locally)

**Nice to have:**
- Users can subscribe to alerts for air quality or pollen crossing a threshold in a chosen area
- Subscription management commands (`/subscribe`, `/unsubscribe`, `/status`)
- Formatted, readable responses (Telegram supports markdown)

---

## Required vs nice-to-have (summary)

### Hard requirements (presentation must show these)
- [ ] At least one application uses **AWS Bedrock** (model invocation)
- [ ] At least one application uses **Bedrock Agents** or AgentCore (orchestration loop, not just raw API)
- [ ] Both apps connect to **our MCP server** as the data source
- [ ] Both apps are **deployed on AWS** (not running locally during demo)
- [ ] The web app **AI controls the map** (this is the key differentiator vs current demo)
- [ ] The Telegram bot **responds to messages** with real city data

### Strong nice-to-haves (do if time allows)
- [ ] Bedrock Knowledge Base (RAG) for static Barcelona info
- [ ] Telegram alert subscription system
- [ ] Bedrock Guardrails on one app
- [ ] Conversation memory / multi-turn context in Telegram bot
- [ ] Dashboard panel with auto-generated charts in web app

### Skip for now
- Noise data (Sentilo is dead)
- Auth / login on web app
- Mobile app

---

## Task breakdown

Assignments TBD by the team — tasks are listed by area, not person. Exception: **Telegram bot is proposed for José** since he's already been experimenting with it.

### Bedrock Agent setup
- Set up a Bedrock Agent connected to our MCP server
- Write the agent instruction prompt for a Barcelona city assistant
- Verify it correctly uses our tools and returns useful answers

### Web app (rewrite)
- Has an interactive map and a chat interface
- AI agent can control the map in response to user queries (show locations, routes, data overlays)
- AI can generate dynamic dashboards with charts and metric cards
- Publicly hosted on AWS

### Agent prompt tuning
- Agent handles composite queries well ("Is today a good day to be outside?" should trigger weather + UV + pollen + air quality together)

### Alert system
- Users can subscribe to air quality or pollen alerts for a chosen area
- System checks readings periodically and notifies subscribers when thresholds are crossed

### Air quality polish
- Expand coverage beyond the current 4 stations so more of Barcelona is answered accurately

### José — Telegram bot *(proposed)*
- Bot responds to user messages with real city data via Bedrock + our MCP server
- Deployed publicly
- *(Nice to have)* Alert subscriptions — users can subscribe/unsubscribe and receive threshold alerts

---

## Timeline (2 weeks to May 29)

| Days | Milestone |
|------|-----------|
| 1–2 | Bedrock Agent up, connected to MCP, responding via `invoke_agent` |
| 1–3 | Telegram bot responding to messages via Bedrock |
| 3–5 | Web app: map + chat working, AI can drop pins and show routes |
| 3–5 | Dashboard panel working in web app |
| 5–7 | Both apps deployed publicly on AWS |
| 7–10 | Alert system |
| 10–12 | End-to-end demo rehearsal, edge case fixes |
| 12–14 | Presentation slides updated, final polish |

---

## Demo flow for final presentation

1. **Slide: what we built** — MCP server, 6 data types, live since May 2026
2. **Live: Telegram bot** — send a message live, show instant response with real data
3. **Live: web app** — type "Show me air quality near Eixample and mark it on the map" → pins appear in real time
4. **Live: composite query** — "Is it safe to go cycling in Barcelona this afternoon?" → agent calls weather + UV + air quality + Bicing, responds with map pins and a dashboard chart
5. **Slide: architecture** — data pipeline → Bedrock Agent → two apps
6. **Slide: Bedrock** — why AgentCore, what the orchestration loop does
7. **Q&A**

---

## Shared resources

- **MCP endpoint:** `https://9llxtl8mm3.execute-api.eu-west-1.amazonaws.com/mcp`
- **AWS account:** 539592518821, region eu-west-1
- **Bedrock model:** `eu.anthropic.claude-sonnet-4-6` (eu-west-1)
- **Repo:** `https://github.com/KubaDusza/barcelona-smart-city`
- **Credentials:** ask Jakub for AWS access keys
