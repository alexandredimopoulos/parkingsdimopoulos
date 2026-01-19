"""Récupération des données temps réel + mise à jour des fichiers.

Ce script est pensé pour tourner en GitHub Actions toutes les heures.

Il fait 3 choses :
1) Fetch des données voitures + vélos via l'API MMM
2) Append dans `data/historique_parkings.csv`
3) Met à jour les JSON consommés par le site (`docs/data/...`)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

from config import (
    BIKE_STATIONS_URLS,
    CAR_PARKINGS_URLS,
    DOCS_DATA_DIR,
    HISTORY_CSV,
    HTTP_TIMEOUT_SECONDS,
    LATEST_SNAPSHOT_JSON,
    METADATA_DOCS_JSON,
    METADATA_JSON,
    TIMEZONE,
)
from utils import (
    CsvRow,
    append_semicolon_csv,
    existing_keys_for_timestamp,
    load_canonical_name_maps,
    load_json,
    normalize_key,
    prop_value,
    safe_int,
    save_json,
)


CSV_HEADER = ["Date", "Heure", "Type", "Nom", "Places_Libres", "Places_Totales"]


def _get_tz() -> ZoneInfo:
    """Retourne le fuseau configuré, ou UTC si indisponible."""
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")


def _fetch_json_first_working(urls: List[str]) -> Tuple[str, Any]:
    """Essaie plusieurs endpoints (fallback). Retourne (url_utilisee, payload_json)."""
    last_error: Optional[Exception] = None
    for url in urls:
        try:
            resp = requests.get(
                url,
                timeout=HTTP_TIMEOUT_SECONDS,
                headers={"User-Agent": "parking-correlation-site/1.0"},
            )
            resp.raise_for_status()
            return url, resp.json()
        except Exception as e:  # noqa: BLE001
            last_error = e
            continue

    raise RuntimeError(f"Aucun endpoint ne répond. Dernière erreur: {last_error}")


def _extract_point(entity: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Renvoie (lat, lon) si possible."""
    loc = prop_value(entity.get("location"))
    if isinstance(loc, dict) and "coordinates" in loc:
        coords = loc.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lon = coords[0]
            lat = coords[1]
            try:
                return float(lat), float(lon)
            except (TypeError, ValueError):
                return None
    return None


def _canonicalize_name(typ: str, raw_name: str, canonical_maps: Dict[str, Dict[str, str]]) -> str:
    key = normalize_key(raw_name)
    if typ in canonical_maps and key in canonical_maps[typ]:
        return canonical_maps[typ][key]
    return raw_name


def _parse_bike_entities(payload: Any, canonical_maps: Dict[str, Dict[str, str]]) -> Tuple[List[CsvRow], List[Dict[str, Any]]]:
    """Parse la réponse de /bikestation.

    On stocke les "places libres" = freeSlotNumber (places de stationnement disponibles).
    """
    rows: List[CsvRow] = []
    items: List[Dict[str, Any]] = []

    tz = _get_tz()
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    if not isinstance(payload, list):
        return rows, items

    for e in payload:
        if not isinstance(e, dict):
            continue

        # Nom station: dans address.value.streetAddress
        addr = prop_value(e.get("address"))
        raw_name = None
        if isinstance(addr, dict):
            raw_name = addr.get("streetAddress") or addr.get("street")
        raw_name = raw_name or str(prop_value(e.get("name")) or e.get("id") or "")
        raw_name = str(raw_name).strip()
        if not raw_name:
            continue

        name = _canonicalize_name("Velo", raw_name, canonical_maps)

        free = safe_int(prop_value(e.get("freeSlotNumber")))
        total = safe_int(prop_value(e.get("totalSlotNumber")))

        rows.append(CsvRow(date=date_str, time=time_str, type="Velo", name=name, free=free, total=total))

        pt = _extract_point(e)
        lat, lon = (pt if pt else (None, None))

        items.append(
            {
                "id": e.get("id"),
                "name": name,
                "free": free,
                "total": total,
                "lat": lat,
                "lon": lon,
                "status": prop_value(e.get("status")),
            }
        )

    rows.sort(key=lambda r: normalize_key(r.name))
    items.sort(key=lambda it: normalize_key(it["name"]))
    return rows, items


def _parse_car_entities(payload: Any, canonical_maps: Dict[str, Dict[str, str]]) -> Tuple[List[CsvRow], List[Dict[str, Any]]]:
    """Parse la réponse d'un endpoint de parkings voitures.

    On vise le modèle FIWARE OffStreetParking :
    - availableSpotNumber
    - totalSpotNumber
    """
    rows: List[CsvRow] = []
    items: List[Dict[str, Any]] = []

    tz = _get_tz()
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    if not isinstance(payload, list):
        return rows, items

    for e in payload:
        if not isinstance(e, dict):
            continue

        raw_name = prop_value(e.get("name"))
        if not raw_name:
            addr = prop_value(e.get("address"))
            if isinstance(addr, dict):
                raw_name = addr.get("streetAddress")
        raw_name = raw_name or e.get("id")
        raw_name = str(raw_name).strip()
        if not raw_name:
            continue

        name = _canonicalize_name("Voiture", raw_name, canonical_maps)

        free = safe_int(
            prop_value(e.get("availableSpotNumber"))
            if e.get("availableSpotNumber") is not None
            else prop_value(e.get("availableSlotNumber"))
        )

        total = safe_int(
            prop_value(e.get("totalSpotNumber"))
            if e.get("totalSpotNumber") is not None
            else prop_value(e.get("totalSlotNumber"))
        )

        if total <= 0:
            continue

        rows.append(CsvRow(date=date_str, time=time_str, type="Voiture", name=name, free=free, total=total))

        pt = _extract_point(e)
        lat, lon = (pt if pt else (None, None))

        items.append(
            {
                "id": e.get("id"),
                "name": name,
                "free": free,
                "total": total,
                "lat": lat,
                "lon": lon,
            }
        )

    rows.sort(key=lambda r: normalize_key(r.name))
    items.sort(key=lambda it: normalize_key(it["name"]))
    return rows, items


def _update_metadata(meta: Dict[str, Any], typ: str, items: List[Dict[str, Any]]) -> None:
    if typ not in meta:
        meta[typ] = {}
    for it in items:
        name = it.get("name")
        lat = it.get("lat")
        lon = it.get("lon")
        if not name:
            continue
        if lat is None or lon is None:
            meta[typ].setdefault(name, {})
            continue
        meta[typ][name] = {"lat": float(lat), "lon": float(lon), "id": it.get("id")}


def main() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    canonical_maps = load_canonical_name_maps(HISTORY_CSV)

    car_url, car_payload = _fetch_json_first_working(CAR_PARKINGS_URLS)
    bike_url, bike_payload = _fetch_json_first_working(BIKE_STATIONS_URLS)

    car_rows, car_items = _parse_car_entities(car_payload, canonical_maps)
    bike_rows, bike_items = _parse_bike_entities(bike_payload, canonical_maps)

    tz = _get_tz()
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    already = existing_keys_for_timestamp(HISTORY_CSV, date_str, time_str)
    to_append: List[CsvRow] = []
    for r in car_rows + bike_rows:
        if (r.type, r.name) not in already:
            to_append.append(r)

    if to_append:
        append_semicolon_csv(HISTORY_CSV, to_append, header=CSV_HEADER)

    meta = load_json(METADATA_JSON, default={"Voiture": {}, "Velo": {}, "generated_at": None})
    meta["generated_at"] = now.isoformat()
    meta["sources"] = {"cars": car_url, "bikes": bike_url}

    _update_metadata(meta, "Voiture", car_items)
    _update_metadata(meta, "Velo", bike_items)

    save_json(METADATA_JSON, meta)
    save_json(METADATA_DOCS_JSON, meta)

    snapshot = {
        "generated_at": now.isoformat(),
        "timezone": TIMEZONE,
        "sources": {"cars": car_url, "bikes": bike_url},
        "cars": car_items,
        "bikes": bike_items,
    }
    save_json(LATEST_SNAPSHOT_JSON, snapshot)

    print(f"OK - {len(to_append)} lignes ajoutées au CSV. Snapshot/metadata mis à jour.")


if __name__ == "__main__":
    main()
