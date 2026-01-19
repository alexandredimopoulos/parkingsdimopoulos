"""
scripts/analyze_saturation.py

Objectifs (7 derniers jours) :
1) Classement "parkings les plus saturés" pour :
   - Voiture
   - Vélo
   (basé sur taux d'occupation moyen + % du temps >= 90%)

2) Courbes :
   - occupation moyenne des parkings voitures de toute la ville (série temporelle)
   - occupation moyenne des parkings vélos de toute la ville (série temporelle)

Sortie (JSON consommé par le site) :
   docs/data/saturation_7d.json
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import HISTORY_CSV
from utils import make_timestamp, max_timestamp_in_csv, read_semicolon_csv, save_json


LOOKBACK_DAYS = 7
SAT_THRESHOLD = 0.90  # "saturé" si occupation >= 90%
OUT_JSON = Path("docs") / "data" / "saturation_7d.json"


def _to_float(x: str) -> Optional[float]:
    try:
        return float(x)
    except Exception:  # noqa: BLE001
        return None


def occ_from_free_total(free: float, total: float) -> Optional[float]:
    if total <= 0:
        return None
    occ = 1.0 - (free / total)
    if occ < 0:
        occ = 0.0
    if occ > 1:
        occ = 1.0
    return occ


def main() -> None:
    rows = read_semicolon_csv(HISTORY_CSV)
    latest_ts = max_timestamp_in_csv(HISTORY_CSV)

    if latest_ts is None:
        raise SystemExit("Historique vide : impossible de calculer la saturation.")

    cutoff = latest_ts - timedelta(days=LOOKBACK_DAYS)

    # series[type][name][ts] = (occ, total)
    series: Dict[str, Dict[str, Dict[Any, Tuple[float, float]]]] = {
        "Voiture": defaultdict(dict),
        "Velo": defaultdict(dict),
    }

    # Pour courbe ville : city[type][ts] = list of occ values across parkings
    city: Dict[str, Dict[Any, List[float]]] = {
        "Voiture": defaultdict(list),
        "Velo": defaultdict(list),
    }

    for r in rows:
        d = (r.get("Date") or "").strip()
        t = (r.get("Heure") or "").strip()
        typ = (r.get("Type") or "").strip()
        name = (r.get("Nom") or "").strip()
        free_s = (r.get("Places_Libres") or "").strip()
        total_s = (r.get("Places_Totales") or "").strip()

        if not d or not t or typ not in series or not name:
            continue

        try:
            ts = make_timestamp(d, t)
        except ValueError:
            continue

        if ts < cutoff:
            continue

        free = _to_float(free_s)
        total = _to_float(total_s)
        if free is None or total is None:
            continue

        occ = occ_from_free_total(free, total)
        if occ is None:
            continue

        # garde dernier point si doublon timestamp
        series[typ][name][ts] = (occ, total)

    # ---- Classements saturation
    def build_ranking(typ: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for name, ts_map in series[typ].items():
            if not ts_map:
                continue
            occ_values = [v[0] for _, v in sorted(ts_map.items(), key=lambda kv: kv[0])]
            n = len(occ_values)
            if n == 0:
                continue
            mean_occ = sum(occ_values) / n
            max_occ = max(occ_values)
            sat_pct = sum(1 for x in occ_values if x >= SAT_THRESHOLD) / n

            out.append(
                {
                    "name": name,
                    "mean_occ": round(mean_occ, 4),
                    "max_occ": round(max_occ, 4),
                    "sat_pct": round(sat_pct, 4),   # part du temps "saturé"
                    "n_points": n,
                }
            )

        # Tri principal : mean_occ desc, puis sat_pct desc, puis max_occ desc
        out.sort(key=lambda x: (x["mean_occ"], x["sat_pct"], x["max_occ"]), reverse=True)
        return out

    cars_rank = build_ranking("Voiture")
    bikes_rank = build_ranking("Velo")

    # ---- Courbes moyennes ville
    # On construit city[type][ts] = liste des occ de tous les parkings à ce ts
    for typ in ("Voiture", "Velo"):
        for name, ts_map in series[typ].items():
            for ts, (occ, _total) in ts_map.items():
                city[typ][ts].append(occ)

    def city_curve(typ: str) -> Dict[str, Any]:
        ts_sorted = sorted(city[typ].keys())
        x = []
        y = []
        for ts in ts_sorted:
            values = city[typ][ts]
            if not values:
                continue
            x.append(ts.isoformat())
            y.append(round(sum(values) / len(values), 4))
        return {"timestamps": x, "avg_occ": y}

    out = {
        "generated_at": latest_ts.isoformat(),
        "lookback_days": LOOKBACK_DAYS,
        "saturation_threshold": SAT_THRESHOLD,
        "rankings": {
            "cars": cars_rank,
            "bikes": bikes_rank,
        },
        "city_curves": {
            "cars": city_curve("Voiture"),
            "bikes": city_curve("Velo"),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    save_json(OUT_JSON, out)
    print(f"OK - écrit : {OUT_JSON} (cars={len(cars_rank)} bikes={len(bikes_rank)})")


if __name__ == "__main__":
    main()
