# Barcelona Smart City — Presenter Notes
**UPC CCBDA · Team 11 · May 2026**

Open `DEMO_SLIDES.html` in a browser. Press **Space/→** to advance, **F11** for fullscreen. Keep this file on a second screen or phone.

---

## Before You Present — Checklist

- [ ] `DEMO_SLIDES.html` open in Chrome/Firefox, F11 fullscreen
- [ ] Claude tab open at **claude.ai** with the MCP server already connected
  - Settings → Integrations → full URL already added and active
  - Verify: new chat, type anything — the 11 smart city tools should appear in the tool list
- [ ] Internet connection confirmed (tools call live AWS)
- [ ] `tinyurl.com/mwn6jzdt` bookmarked — opens the full MCP URL for audience copy-paste
- [ ] If demoing Claude Code CLI: `claude mcp list` shows `barcelona-smart-city`

---

## Slides Overview (6 slides)

1. Title
2. Architecture
3. Tools (live / stored)
4. **Accumulated Data** ← new: live charts from DynamoDB
5. Deployment & Ops
6. Try It

---

## Demo Flow — Slide by Slide

### Slide 1 — Title (10 sec)
> "We built a live Barcelona city data platform that gives Claude real-time awareness of the city — bikes, transport, air quality, UV, pollen, weather. All running on AWS, all open data, no API keys. I'll walk through how it works and then you can try it live."

---

### Slide 2 — Architecture (1 min)

Walk the top row left to right:
> "The top row is the ingest pipeline. External APIs on the left — Bicing, Barcelona's open data network, Open-Meteo, the Copernicus UV model. Five Lambda functions poll these on a schedule and write to seven DynamoDB tables. EventBridge is the trigger — Bicing every 5 minutes, everything else hourly."

Walk the bottom row:
> "The bottom row is the serve pipeline. When Claude wants data, it calls our MCP server — also a Lambda, behind API Gateway. The MCP server reads from the same DynamoDB tables and returns structured JSON."

> "Everything in eu-west-1. Pay-per-request DynamoDB and Lambda free tier — essentially zero cost at demo scale."

---

### Slide 3 — Tools (45 sec)

Point at the two columns:
> "Eleven tools in two categories. On the left — live tools. These call the external API or DynamoDB on every request and return current data. On the right — stored tools. These query the time-series snapshots we've been accumulating in DynamoDB since deployment. Each stored tool can go back up to 30 days."

> "No API keys for any source. All open data."

---

### Slide 4 — Accumulated Data (1 min)

Point at the charts:
> "These are real readings from our DynamoDB tables — not mock data. UV and pollen verticals were deployed around May 11th. We now have 49 UV readings and 48 pollen readings stored."

**UV chart:**
> "The UV chart shows two full days. May 12th was a clear day — peak UV index 7.6, which is 'very high' by WHO classification. May 13th was cloudier — peak dropped to 5.8. The daily bell curve is exactly what you'd expect: zero at night, rising from 6am, peaking around noon, gone by 7pm."

**Pollen chart:**
> "Pollen is more interesting. Only grass and olive are non-zero — the other four species are out of season for mid-May in Barcelona, which is correct. Olive had a spike to 37 grains per cubic metre at midnight on May 12th — that's the tail end of olive season. Grass is sitting in the low range, under the 10 grains threshold for 'moderate'. Both of these numbers came out of our PollenData DynamoDB table, stored hourly by a Lambda."

> "This slide demonstrates exactly why the historical pathway matters — these patterns only exist because the ingest Lambda was running silently in the background. You can't ask for it retroactively."

---

### Slide 5 — Deployment & Ops (30 sec)

> "Three commands to stand the whole thing up. `setup.sh` creates the tables and IAM roles — idempotent, safe to re-run. `deploy.sh all` packages and deploys all six Lambdas plus the API Gateway. `load_gtfs.py` is a one-time import of the 3,453 TMB transit stops."

> "The running infrastructure is fully managed. EventBridge fires the schedules, DynamoDB auto-expires rows after 30 days. `pause.sh` kills the schedules if you want to stop ingestion."

---

### Slide 6 — Try It (DEMO — 3–5 min)

> "The short URL just redirects to the full MCP endpoint — open it on a laptop, copy the URL, paste into claude.ai Settings → Integrations. Or one command in Claude Code CLI."

Switch to Claude and run:

**Prompt 1 — multi-tool environmental:**
> *"I'm going for a run in Barcelona tomorrow morning. Will the air quality and pollen be okay, or should I skip it?"*

Narrate while it runs:
> "Watch it compose multiple tools automatically — air quality, pollen, probably weather — from a single natural language question. No tool selection from the user."

**Prompt 2 — UV + practical:**
> *"I want to take my kids to Barceloneta beach this afternoon — is the UV too strong right now? What SPF do we need?"*

After response:
> "The burn time and SPF advice comes from the tool itself — it computes it using the Diffey formula and returns it as structured data. Claude just presents it."

---

## Key Phrases

| Moment | Say |
|--------|-----|
| On the contrast with plain Claude | *"Same model, same question — the difference is the server"* |
| On the data slide | *"This is what 2 days of passive collection looks like — we didn't do anything after deploying"* |
| On cost | *"Essentially zero cost at demo scale — pay-per-request DynamoDB, Lambda free tier"* |
| On MCP as standard | *"Build the server once — any MCP-compatible client gets it for free"* |
| On live data | *"Real data, right now — not training data, not cached, not estimated"* |
| If a tool is slow | *"Lambda cold start — first call takes about a second, then it's warm"* |
| On pollen zeros | *"Birch, ragweed, alder, mugwort are all zero — that's correct, they're out of season in mid-May in Barcelona"* |

---

## Fallback Prompts

```
Is today a good day to be outside in Barcelona?
Weather, UV, air quality, pollen — give me a full city health snapshot.
```
*(4 tools in one shot)*

```
Are there any Bicing bikes near Sagrada Família right now?
```
*(Fast, concrete, impossible for plain Claude)*

```
Show me the UV index trend in Barcelona over the last 48 hours.
```
*(Pulls from UVData DynamoDB — shows the two-day bell curve history live)*

---

## Data Status (as of May 14 2026)

| Table | Records | Span | Notes |
|-------|---------|------|-------|
| UVData | 49 hourly readings | May 11–13 | Peak 7.6 (very high) May 12 noon |
| PollenData | 48 hourly readings × 6 species | May 12–14 | Grass + olive non-zero; others 0 (out of season) |
| BicingStations | 30 days × 5-min snapshots | ongoing | Deployed earlier |
| AirQualityReadings | 30 days × hourly | ongoing | 9 stations, 4 pollutants |
| WeatherData | hourly | ongoing | |
| TransitStops | 3,453 stops | static | one-time GTFS load |

---

## What Each Teammate Built

| Person | Vertical | Owns |
|--------|----------|------|
| **Jakub** | Mobility + MCP server | Bicing, Transit, UV, Pollen Lambdas · `mcp_server.py` · `deploy.sh` · `setup.sh` |
| **Mark** | Air Quality | `air_quality_ingest` Lambda · `AirQualityReadings` table · `get_air_quality` tool |
| **Jia** | Weather | `weather_ingest` Lambda · `WeatherData` table · `get_weather` tool |
| **Jose** | Noise | Attempted — Sentilo platform data was mostly inactive (sensors listed but not reporting) |

---

## Technical Q&A Prep

**"Why DynamoDB and not a relational DB?"**
> Pay-per-request, no cluster, scales to zero. Access patterns are always PK + sort key range queries (station + time range) — a perfect fit. No joins needed anywhere.

**"Why Lambda for the MCP server?"**
> MCP is stateless JSON-RPC — no session to maintain between calls. Lambda handles cold starts in under a second. Cost is zero at demo scale.

**"Why not call APIs directly from Claude?"**
> Claude has no network access. MCP is the bridge. Also the historical data only exists because we've been collecting it — you can't retroactively query an API for data it didn't store.

**"Why FastMCP?"**
> It handles protocol negotiation, tool registration, and JSON Schema generation from Python type hints. The server code is almost entirely business logic, not protocol boilerplate.

**"Can other AI systems use this?"**
> Any MCP-compatible client. The protocol is open — OpenAI, Gemini, and others added MCP support in early 2025.

**"What about the olive pollen spike?"**
> The 37.4 grains/m³ reading at midnight May 12 is the tail end of the olive season — it's real model data from the CAMS Copernicus system. It dropped sharply the next day, consistent with the season ending.
