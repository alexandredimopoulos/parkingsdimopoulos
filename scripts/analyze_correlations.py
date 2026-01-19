"""Analyse des corrélations voiture ↔ vélo.

Objectif :
- utiliser l'historique CSV (data/historique_parkings.csv)
- calculer la corrélation de Pearson entre variations (Δ) de places libres
  d'un parking voiture et d'une station vélo
- produire un JSON (docs/data/correlations.json) lu par le site

Logique géographique :
- on calcule une distance (km) avec des coordonnées (lat/lon) stockées dans
  data/metadata.json (généré par update_data.py).
- côté site, on filtre (par défaut) les paires trop éloignées.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from config import (
    CORRELATIONS_JSON,
    DEFAULT_MAX_DISTANCE_KM,
    DISTANCE_WEIGHT_KM,
    HISTORY_CSV,
    LOOKBACK_DAYS,
    METADATA_JSON,
    MIN_ABS_CORRELATION_TO_SHOW,
    MIN_COMMON_POINTS,
    TOP_N_PAIRS,
)
from geo import haversine_km
from stats_lib import correlation
from utils import load_json, make_timestamp, max_timestamp_in_csv, read_semicolon_csv, save_json


def _load_time_series(csv_rows: List[Dict[str, str]], cutoff_ts: Optional[Any]) -> Dict[str, Dict[str, Dict[Any, int]]]:
    """Retourne series[type][name][timestamp] = free."""
    series: Dict[str, Dict[str, Dict[Any, int]]] = {"Voiture": defaultdict(dict), "Velo": defaultdict(dict)}

    for r in csv_rows:
        d = (r.get("Date") or "").strip()
        t = (r.get("Heure") or "").strip()
        typ = (r.get("Type") or "").strip()
        name = (r.get("Nom") or "").strip()
        free = (r.get("Places_Libres") or "").strip()
        if not d or not t or not typ or not name:
            continue
        try:
            ts = make_timestamp(d, t)
        except ValueError:
            continue
        if cutoff_ts is not None and ts < cutoff_ts:
            continue
        try:
            free_i = int(float(free))
        except ValueError:
            continue
        if typ not in series:
            continue

        # Si doublon (même timestamp), on garde le dernier
        series[typ][name][ts] = free_i

    return series


def _compute_deltas(series: Dict[Any, int]) -> Dict[Any, int]:
    """Retourne dict timestamp -> delta entre t et t-1."""
    ts_sorted = sorted(series.keys())
    deltas: Dict[Any, int] = {}
    for i in range(1, len(ts_sorted)):
        t_prev = ts_sorted[i - 1]
        t_cur = ts_sorted[i]
        deltas[t_cur] = series[t_cur] - series[t_prev]
    return deltas


def _coord(meta: Dict[str, Any], typ: str, name: str) -> Optional[Tuple[float, float]]:
    d = meta.get(typ, {}).get(name)
    if not isinstance(d, dict):
        return None
    lat = d.get("lat")
    lon = d.get("lon")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def main() -> None:
    csv_rows = read_semicolon_csv(HISTORY_CSV)
    latest_ts = max_timestamp_in_csv(HISTORY_CSV)
    cutoff_ts = None
    if latest_ts is not None:
        cutoff_ts = latest_ts - timedelta(days=LOOKBACK_DAYS)

    series = _load_time_series(csv_rows, cutoff_ts)

    car_deltas = {name: _compute_deltas(ts_map) for name, ts_map in series["Voiture"].items() if len(ts_map) >= 2}
    bike_deltas = {name: _compute_deltas(ts_map) for name, ts_map in series["Velo"].items() if len(ts_map) >= 2}

    cars = sorted(car_deltas.keys())
    bikes = sorted(bike_deltas.keys())

    meta = load_json(METADATA_JSON, default={"Voiture": {}, "Velo": {}})

    pairs: List[Dict[str, Any]] = []

    for car_name, car_delta_map in car_deltas.items():
        car_xy = _coord(meta, "Voiture", car_name)
        for bike_name, bike_delta_map in bike_deltas.items():
            common_ts = sorted(set(car_delta_map.keys()) & set(bike_delta_map.keys()))
            n = len(common_ts)
            if n < MIN_COMMON_POINTS:
                continue

            x = [car_delta_map[ts] for ts in common_ts]
            y = [bike_delta_map[ts] for ts in common_ts]

            r = correlation(x, y)

            bike_xy = _coord(meta, "Velo", bike_name)
            distance_km: Optional[float] = None
            if car_xy and bike_xy:
                distance_km = haversine_km(car_xy[0], car_xy[1], bike_xy[0], bike_xy[1])

            score = abs(r)
            if distance_km is not None:
                score = abs(r) * math.exp(-distance_km / DISTANCE_WEIGHT_KM)

            pairs.append(
                {
                    "car": car_name,
                    "bike": bike_name,
                    "r": round(float(r), 4),
                    "abs_r": round(float(abs(r)), 4),
                    "distance_km": round(float(distance_km), 3) if distance_km is not None else None,
                    "n": n,
                    "score": round(float(score), 4),
                }
            )

    pair_map = {(p["car"], p["bike"]): p for p in pairs}

    matrix: List[List[Optional[float]]] = []
    for car_name in cars:
        row: List[Optional[float]] = []
        for bike_name in bikes:
            p = pair_map.get((car_name, bike_name))
            row.append(p["r"] if p is not None else None)
        matrix.append(row)

    pairs_sorted = sorted(pairs, key=lambda p: p["score"], reverse=True)

    top_global = [
        p
        for p in pairs_sorted
        if p["abs_r"] >= MIN_ABS_CORRELATION_TO_SHOW
        and (p["distance_km"] is None or p["distance_km"] <= DEFAULT_MAX_DISTANCE_KM)
    ][:TOP_N_PAIRS]

    by_car: Dict[str, List[Dict[str, Any]]] = {}
    for car_name in cars:
        lst = [p for p in pairs_sorted if p["car"] == car_name]
        by_car[car_name] = lst[:10]

    by_bike: Dict[str, List[Dict[str, Any]]] = {}
    for bike_name in bikes:
        lst = [p for p in pairs_sorted if p["bike"] == bike_name]
        by_bike[bike_name] = lst[:10]

    out = {
        "generated_at": (latest_ts.isoformat() if latest_ts is not None else None),
        "lookback_days": LOOKBACK_DAYS,
        "min_common_points": MIN_COMMON_POINTS,
        "distance_weight_km": DISTANCE_WEIGHT_KM,
        "default_filters": {"max_distance_km": DEFAULT_MAX_DISTANCE_KM, "min_abs_correlation": MIN_ABS_CORRELATION_TO_SHOW},
        "cars": cars,
        "bikes": bikes,
        "matrix": matrix,
        "pairs": pairs_sorted,
        "top_global": top_global,
        "by_car": by_car,
        "by_bike": by_bike,
        "counts": {"cars": len(cars), "bikes": len(bikes), "pairs_computed": len(pairs)},
    }

    save_json(CORRELATIONS_JSON, out)
    print(f"OK - corrélations calculées: {len(pairs)} paires")


if __name__ == "__main__":
    main()
