"""Analyse des corrélations voiture ↔ vélo.

Objectif :
- lire l'historique CSV (data/historique_parkings.csv)
- calculer la corrélation de Pearson entre variations (Δ) de places libres
  d'un parking voiture et d'une station vélo
- intégrer une contrainte géographique (distance) via metadata.json
- générer des fichiers JSON consommés par le site :

    docs/data/correlations_7.json
    docs/data/correlations_14.json
    docs/data/correlations_21.json
    docs/data/correlations_30.json

Le site permet ensuite de choisir la fenêtre temporelle.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import (
    DEFAULT_MAX_DISTANCE_KM,
    DISTANCE_WEIGHT_KM,
    HISTORY_CSV,
    METADATA_JSON,
    MIN_ABS_CORRELATION_TO_SHOW,
    MIN_COMMON_POINTS,
    TOP_N_PAIRS,
)
from geo import haversine_km
from stats_lib import correlation
from utils import load_json, make_timestamp, max_timestamp_in_csv, read_semicolon_csv, save_json


# Fenêtres proposées (en jours) pour le select côté site
LOOKBACK_OPTIONS = [7, 14, 21, 30]


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

        # S'il y a des doublons au même timestamp, on garde le dernier
        series[typ][name][ts] = free_i

    return series


def _compute_deltas(series: Dict[Any, int]) -> Dict[Any, int]:
    """Retourne dict timestamp -> delta (t - t-1)."""
    ts_sorted = sorted(series.keys())
    deltas: Dict[Any, int] = {}
    for i in range(1, len(ts_sorted)):
        t_prev = ts_sorted[i - 1]
        t_cur = ts_sorted[i]
        deltas[t_cur] = series[t_cur] - series[t_prev]
    return deltas


def _coord(meta: Dict[str, Any], typ: str, name: str) -> Optional[Tuple[float, float]]:
    """Extrait (lat, lon) depuis metadata.json."""
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


def _output_path(days: int) -> Path:
    # On écrit directement dans docs/data/
    return Path("docs") / "data" / f"correlations_{days}.json"


def compute_for_days(
    csv_rows: List[Dict[str, str]],
    meta: Dict[str, Any],
    latest_ts: Optional[Any],
    days: int,
) -> Dict[str, Any]:
    """Calcule l'objet JSON correlations_* pour une fenêtre donnée."""
    cutoff_ts = None
    if latest_ts is not None:
        cutoff_ts = latest_ts - timedelta(days=days)

    series = _load_time_series(csv_rows, cutoff_ts)

    car_deltas = {name: _compute_deltas(ts_map) for name, ts_map in series["Voiture"].items() if len(ts_map) >= 2}
    bike_deltas = {name: _compute_deltas(ts_map) for name, ts_map in series["Velo"].items() if len(ts_map) >= 2}

    cars = sorted(car_deltas.keys())
    bikes = sorted(bike_deltas.keys())

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
                # Pondération géographique (plus c'est loin, plus le score baisse)
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

    # Pour la heatmap, on fabrique la matrice en s'appuyant sur la liste pairs
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

    out = {
        "generated_at": (latest_ts.isoformat() if latest_ts is not None else None),
        "lookback_days": days,
        "min_common_points": MIN_COMMON_POINTS,
        "distance_weight_km": DISTANCE_WEIGHT_KM,
        "default_filters": {
            "max_distance_km": DEFAULT_MAX_DISTANCE_KM,
            "min_abs_correlation": MIN_ABS_CORRELATION_TO_SHOW,
        },
        "cars": cars,
        "bikes": bikes,
        "matrix": matrix,
        "pairs": pairs_sorted,
        "top_global": top_global,
        "counts": {"cars": len(cars), "bikes": len(bikes), "pairs_computed": len(pairs)},
    }

    return out


def main() -> None:
    # Lecture historique + metadata
    csv_rows = read_semicolon_csv(HISTORY_CSV)
    meta = load_json(METADATA_JSON, default={"Voiture": {}, "Velo": {}})
    latest_ts = max_timestamp_in_csv(HISTORY_CSV)

    # Génération de plusieurs fenêtres
    for days in LOOKBACK_OPTIONS:
        out = compute_for_days(csv_rows, meta, latest_ts, days)
        save_json(_output_path(days), out)
        print(f"OK - correlations_{days}.json écrit (paires: {out['counts']['pairs_computed']})")


if __name__ == "__main__":
    main()
