"""
scripts/load_gtfs.py
=====================
One-time script: loads TMB GTFS stops + route associations into DynamoDB.
Run this locally after setup.sh to populate the TransitStops table.

Usage:
    python3 aws/scripts/load_gtfs.py

Prerequisites:
    - GTFS files extracted at:  smart_city/gtfs/
    - AWS CLI configured with DynamoDB write access
    - boto3 installed:  pip install boto3

What it writes to TransitStops:
    PK stop_id  + SK feed_ver  (from feed_info.txt)
    All stop metadata + route_ids / route_names / modes sets
    TTL = feed end_date epoch + 7 days

Expected runtime: ~60 seconds (2,810 stops, batched writes)
"""

import csv
import os
import sys
import time
import urllib.request
import json
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import boto3

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GTFS_DIR   = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "gtfs")
TABLE_NAME = "TransitStops"
REGION     = os.environ.get("AWS_REGION", "eu-west-1")
BATCH_SIZE = 25  # DynamoDB BatchWriteItem limit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_csv(filename: str) -> list[dict]:
    path = os.path.join(GTFS_DIR, filename)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_date(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%Y%m%d").replace(tzinfo=timezone.utc)


ROUTE_TYPE_TO_MODE = {
    "0": "tram",
    "1": "metro",
    "2": "rail",
    "3": "bus",
    "4": "ferry",
    "7": "funicular",
}

# ---------------------------------------------------------------------------
# TMB API fallback: build stop_routes when stop_times.txt is absent
# ---------------------------------------------------------------------------
TMB_APP_ID  = "74309501"
TMB_APP_KEY = "c7234d6f7249b444f6158f41a0ad4fce"
TMB_BASE    = "https://api.tmb.cat/v1"


def _tmb_get(path: str):
    url = f"{TMB_BASE}{path}?app_id={TMB_APP_ID}&app_key={TMB_APP_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "smart-city-gtfs/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"    TMB API error {path}: {e}")
        return None


def _build_stop_routes_from_tmb_api(route_info: dict) -> defaultdict:
    """
    Builds stop_id → set(route_id) mapping using the TMB REST API.
    Uses /transit/linies/bus/{codi}/parades for bus lines and
    /transit/estacions for metro stations (matched via CODI_GRUP_ESTACIO).
    Returns a defaultdict(set) keyed by GTFS stop_id.
    """
    stop_routes: defaultdict = defaultdict(set)

    # Build codi_linia → route_id map from GTFS routes (format: 2.{codi}.{svc})
    codi_to_route: dict[int, str] = {}
    for route_id, info in route_info.items():
        parts = route_id.split(".")
        if len(parts) >= 2:
            try:
                codi_to_route[int(parts[1])] = route_id
            except ValueError:
                pass

    # ---- 1. Bus lines ----
    data = _tmb_get("/transit/linies")
    if not data:
        print("    WARNING: could not fetch TMB lines")
        return stop_routes

    bus_lines = [
        f["properties"] for f in data.get("features", [])
        if f["properties"]["NOM_TIPUS_TRANSPORT"] == "BUS"
    ]
    print(f"    Fetching stops for {len(bus_lines)} bus lines …")
    bus_stop_routes: dict[int, set] = defaultdict(set)  # codi_parada → route_ids

    for i, line in enumerate(bus_lines):
        codi_linia = line["CODI_LINIA"]
        nom_linia  = line["NOM_LINIA"]
        route_id   = codi_to_route.get(codi_linia)
        res = _tmb_get(f"/transit/linies/bus/{codi_linia}/parades")
        if not res:
            continue
        for feat in res.get("features", []):
            codi_parada = feat["properties"].get("CODI_PARADA")
            if codi_parada is not None:
                if route_id:
                    bus_stop_routes[codi_parada].add(route_id)
                else:
                    bus_stop_routes[codi_parada].add(nom_linia)
        if (i + 1) % 20 == 0:
            print(f"      … {i+1}/{len(bus_lines)} bus lines fetched")

    print(f"    {len(bus_stop_routes)} bus stops with route info")

    # ---- 2. Metro stations ----
    # /transit/estacions returns CODI_GRUP_ESTACIO and PICTO (e.g. "L1", "L2L4")
    # GTFS parent_station stop_id is "P.{CODI_GRUP_ESTACIO}"
    metro_data = _tmb_get("/transit/estacions")
    metro_station_routes: dict[int, set] = {}
    if metro_data:
        for feat in metro_data.get("features", []):
            p = feat["properties"]
            codi_grup = p.get("CODI_GRUP_ESTACIO")
            picto     = p.get("PICTO", "")
            if codi_grup and picto:
                # PICTO can be "L2L4" — split into individual line names
                lines = []
                for tok in ["L1","L2","L3","L4","L5","L9N","L9S","L10N","L10S","L11","FM","T1","T2","T3","T4","T5","T6"]:
                    if tok in picto:
                        lines.append(tok)
                # Find the GTFS route_id for each metro line
                route_ids_for_station = set()
                for lname in lines:
                    for rid, info in route_info.items():
                        if info["short_name"] == lname:
                            route_ids_for_station.add(rid)
                            break
                    else:
                        route_ids_for_station.add(lname)
                metro_station_routes[codi_grup] = route_ids_for_station
        print(f"    {len(metro_station_routes)} metro stations with route info")

    # ---- 3. Map to GTFS stop_ids ----
    # Bus stops: GTFS stop_code == CODI_PARADA (numeric string)
    # Metro parent stations: GTFS stop_id == "P.{CODI_GRUP_ESTACIO}"
    # Child stops of metro station inherit parent's routes
    gtfs_stops_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "gtfs", "stops.txt")
    with open(gtfs_stops_path, newline="", encoding="utf-8-sig") as fh:
        stops_csv = list(csv.DictReader(fh))

    # Build parent_station → child stop_ids map
    parent_children: defaultdict = defaultdict(set)
    for s in stops_csv:
        parent = s.get("parent_station", "").strip()
        if parent:
            parent_children[parent].add(s["stop_id"].strip())

    for s in stops_csv:
        stop_id   = s["stop_id"].strip()
        stop_code = s.get("stop_code", "").strip()

        # Bus: match by stop_code == CODI_PARADA
        try:
            codi_parada = int(stop_code)
            if codi_parada in bus_stop_routes:
                stop_routes[stop_id].update(bus_stop_routes[codi_parada])
        except (ValueError, TypeError):
            pass

        # Metro parent station: stop_id == "P.{codi_grup}"
        if stop_id.startswith("P."):
            try:
                codi_grup = int(stop_id[2:])
                if codi_grup in metro_station_routes:
                    routes = metro_station_routes[codi_grup]
                    stop_routes[stop_id].update(routes)
                    # propagate to all children
                    for child_id in parent_children.get(stop_id, set()):
                        stop_routes[child_id].update(routes)
            except ValueError:
                pass

    return stop_routes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  GTFS → DynamoDB loader (TransitStops)")
    print("=" * 60)

    # --- 1. Feed version + TTL ---
    print("\n[1/6] Reading feed_info.txt …")
    feed_rows = load_csv("feed_info.txt")
    if not feed_rows:
        sys.exit("ERROR: feed_info.txt is empty")
    feed      = feed_rows[0]
    feed_ver  = feed.get("feed_version", "unknown").strip()
    end_date  = feed.get("feed_end_date", "20261216").strip()
    ttl_epoch = int((parse_date(end_date) + timedelta(days=7)).timestamp())
    print(f"    feed_version : {feed_ver}")
    print(f"    feed_end     : {end_date}  →  TTL epoch {ttl_epoch}")

    # --- 2. Route type lookup ---
    print("\n[2/6] Reading routes.txt …")
    routes_rows = load_csv("routes.txt")
    route_info  = {}  # route_id → {short_name, mode}
    for r in routes_rows:
        rid  = r["route_id"].strip()
        mode = ROUTE_TYPE_TO_MODE.get(r.get("route_type", "3").strip(), "bus")
        route_info[rid] = {
            "short_name": r.get("route_short_name", "").strip(),
            "mode":       mode,
        }
    print(f"    {len(route_info)} routes loaded")

    # --- 3. Trip → route mapping ---
    print("\n[3/6] Reading trips.txt …")
    trips_rows = load_csv("trips.txt")
    trip_route = {r["trip_id"].strip(): r["route_id"].strip() for r in trips_rows}
    print(f"    {len(trip_route)} trips mapped")

    # --- 4. Stop → routes mapping (via stop_times if available, else TMB API) ---
    stop_routes: dict[str, set[str]] = defaultdict(set)
    st_path = os.path.join(GTFS_DIR, "stop_times.txt")
    if os.path.exists(st_path):
        print("\n[4/6] Reading stop_times.txt (large file, ~30s) …")
        with open(st_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stop_id = row["stop_id"].strip()
                trip_id = row["trip_id"].strip()
                route_id = trip_route.get(trip_id)
                if route_id:
                    stop_routes[stop_id].add(route_id)
        print(f"    {len(stop_routes)} stops have route associations")
    else:
        print("\n[4/6] stop_times.txt not found — fetching route info from TMB API …")
        stop_routes = _build_stop_routes_from_tmb_api(route_info)
        print(f"    {len(stop_routes)} stops have route associations (via TMB API)")

    # --- 5. Load stops ---
    print("\n[5/6] Reading stops.txt …")
    stops_rows = load_csv("stops.txt")
    print(f"    {len(stops_rows)} stops loaded")

    # --- 6. Write to DynamoDB ---
    print("\n[6/6] Writing to DynamoDB TransitStops …")
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table    = dynamodb.Table(TABLE_NAME)

    written  = 0
    skipped  = 0
    batch    = []

    def flush(b: list):
        nonlocal written
        with table.batch_writer() as bw:
            for item in b:
                bw.put_item(Item=item)
        written += len(b)

    for stop in stops_rows:
        stop_id = stop.get("stop_id", "").strip()
        if not stop_id:
            skipped += 1
            continue

        try:
            lat = float(stop.get("stop_lat", 0))
            lon = float(stop.get("stop_lon", 0))
        except ValueError:
            skipped += 1
            continue

        # Build route sets for this stop
        rids   = stop_routes.get(stop_id, set())
        rnames = {route_info[r]["short_name"] for r in rids if r in route_info and route_info[r]["short_name"]}
        modes  = {route_info[r]["mode"]       for r in rids if r in route_info}

        item = {
            "stop_id":       stop_id,
            "feed_ver":      feed_ver,
            "stop_code":     stop.get("stop_code", "").strip(),
            "stop_name":     stop.get("stop_name", "").strip(),
            "stop_lat":      Decimal(str(lat)),
            "stop_lon":      Decimal(str(lon)),
            "lat_bucket":    str(round(lat, 2)),
            "location_type": int(stop.get("location_type", 0) or 0),
            "parent_station":stop.get("parent_station", "").strip(),
            "wheelchair":    int(stop.get("wheelchair_boarding", 0) or 0),
            "ttl":           ttl_epoch,
        }

        # DynamoDB StringSet requires at least 1 element
        if rids:
            item["route_ids"]   = rids
        if rnames:
            item["route_names"] = rnames
        if modes:
            item["modes"]       = modes
            item["primary_mode"] = next(iter(modes))

        batch.append(item)
        if len(batch) >= BATCH_SIZE:
            flush(batch)
            batch = []
            if written % 500 == 0:
                print(f"    … {written} stops written")

    if batch:
        flush(batch)

    print(f"\n    Written : {written}")
    print(f"    Skipped : {skipped}")
    print(f"    Table   : {TABLE_NAME}")
    print("\nGTFS load complete.")


if __name__ == "__main__":
    main()
