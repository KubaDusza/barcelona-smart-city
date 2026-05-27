# Barcelona Smart City — Agent Context

## AWS State (as of 2026-05-20)

- **Account:** `724440691846`, region `eu-west-1`, IAM user `smart_city`
- **MCP endpoint:** `https://4um7sjanuc.execute-api.eu-west-1.amazonaws.com/mcp`  
  (old endpoint `9llxtl8mm3` is gone — update any configs referencing it)
- All 7 DynamoDB tables active: `BicingStations`, `TransitStops`, `ScheduleCache`, `AirQualityReadings`, `WeatherData`, `UVData`, `PollenData`
- All 6 Lambda functions deployed and running on schedule: `smart-city-bicing-ingest` (every 5 min), `smart-city-air-quality-ingest`, `smart-city-weather-ingest`, `smart-city-uv-ingest`, `smart-city-pollen-ingest` (all hourly), `smart-city-mcp-server`

## What Was Changed

### `aws/deploy.sh`
Not modified from original. Uses `pip` (not `pip3`).

### `aws/scripts/load_gtfs.py`
Modified to handle missing `stop_times.txt` via a TMB API fallback. When `stop_times.txt` is absent, it:
1. Fetches all 113 bus lines from `api.tmb.cat/v1/transit/linies/bus/{codi}/parades`
2. Fetches 140 metro stations from `api.tmb.cat/v1/transit/estacions` (has PICTO field with line names)
3. Maps GTFS `stop_code` → `CODI_PARADA` for bus, and `P.{CODI_GRUP_ESTACIO}` for metro parent stations

## Known Issues / Gotchas

### `stop_times.txt` is missing from the repo
Gitignored (too large). The modified `load_gtfs.py` handles this via TMB API. If you ever get the real file, just drop it in `docs/gtfs/` and re-run `python3 aws/scripts/load_gtfs.py` — it will take priority automatically.

### Always activate the venv before running `deploy.sh`
Mac doesn't have `pip` in PATH by default. The deploy script needs it.
```bash
source venv/bin/activate
bash aws/deploy.sh <target>
```
If the venv doesn't exist yet: `python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip`

### `get_transit_route` returns `duration: null`
The Transitous API response doesn't include a duration field in the format the code expects. Routes and legs are correct. Not critical for the demo but worth fixing if needed.

### `verify_data.py` checks for `NoiseData` table
That table doesn't exist (noise vertical was never implemented). The script will print `NOT FOUND` for it — ignore it.

### `requirements.txt` has `fastapi==0.136.1` which doesn't exist on PyPI
Don't `pip install -r requirements.txt` on Python 3.9. The `requirements.txt` is only needed for the local demo app (`dev/local-demo/app.py`), not for the Lambda deploys.

## Re-deploying from scratch

```bash
source venv/bin/activate
bash aws/setup.sh                    # creates tables + IAM roles
bash aws/deploy.sh all               # deploys all Lambdas + API Gateway
python3 aws/scripts/load_gtfs.py     # loads 3,453 transit stops (uses TMB API for routes)
# Seed data immediately (don't wait for EventBridge):
for fn in bicing-ingest air-quality-ingest weather-ingest uv-ingest pollen-ingest; do
  aws lambda invoke --function-name smart-city-$fn --payload '{}' --region eu-west-1 /tmp/out.json
done
```
