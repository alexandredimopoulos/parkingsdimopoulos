"""Petites fonctions utilitaires (I/O, normalisation, etc.)."""

from __future__ import annotations

import csv
import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class CsvRow:
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    type: str  # "Voiture" | "Velo"
    name: str
    free: int
    total: int


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def strip_accents(text: str) -> str:
    """Supprime les accents (utile pour matcher 'Comédie' et 'Comedie')."""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if not unicodedata.combining(ch))


def normalize_key(text: str) -> str:
    """Normalise une chaîne pour servir de clé de comparaison.

    - minuscules
    - sans accents
    - suppression de certains caractères
    """
    t = strip_accents(text).lower().strip()
    # On garde lettres / chiffres, on remplace le reste par des espaces
    cleaned = []
    for ch in t:
        if ch.isalnum():
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def prop_value(x: Any) -> Any:
    """Extrait `value` si l'objet ressemble à un attribut NGSI."""
    if isinstance(x, dict) and "value" in x:
        return x["value"]
    return x


def safe_int(x: Any, default: int = 0) -> int:
    """Convertit en int si possible."""
    try:
        if x is None:
            return default
        return int(float(x))
    except (ValueError, TypeError):
        return default


def read_semicolon_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        return list(reader)


def append_semicolon_csv(path: Path, rows: List[CsvRow], header: List[str]) -> None:
    ensure_parent_dir(path)
    file_exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        if not file_exists:
            writer.writerow(header)
        for r in rows:
            writer.writerow([r.date, r.time, r.type, r.name, r.free, r.total])


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: Any) -> None:
    ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_canonical_name_maps(history_csv: Path) -> Dict[str, Dict[str, str]]:
    """Construit un mapping pour stabiliser les noms entre runs.

    Retour:
        {
          "Voiture": {"comedie": "Comedie", ...},
          "Velo": {"comedie": "Comédie", ...}
        }
    """
    rows = read_semicolon_csv(history_csv)
    mapping: Dict[str, Dict[str, str]] = {"Voiture": {}, "Velo": {}}

    for r in rows:
        typ = r.get("Type", "").strip()
        name = r.get("Nom", "").strip()
        if not typ or not name:
            continue
        if typ not in mapping:
            mapping[typ] = {}
        key = normalize_key(name)
        # on garde le premier nom rencontré comme canonique
        mapping[typ].setdefault(key, name)

    return mapping


def make_timestamp(date_str: str, time_str: str) -> datetime:
    """Parse le couple Date/Heure du CSV."""
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def max_timestamp_in_csv(history_csv: Path) -> Optional[datetime]:
    """Retourne le timestamp le plus récent trouvé dans le CSV."""
    rows = read_semicolon_csv(history_csv)
    best: Optional[datetime] = None
    for r in rows:
        d = r.get("Date")
        t = r.get("Heure")
        if not d or not t:
            continue
        try:
            ts = make_timestamp(d, t)
        except ValueError:
            continue
        if best is None or ts > best:
            best = ts
    return best


def existing_keys_for_timestamp(history_csv: Path, date_str: str, time_str: str) -> set[Tuple[str, str]]:
    """Renvoie les (Type, Nom) déjà présents à ce timestamp."""
    keys: set[Tuple[str, str]] = set()
    if not history_csv.exists():
        return keys

    with history_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            if r.get("Date") == date_str and r.get("Heure") == time_str:
                typ = (r.get("Type") or "").strip()
                name = (r.get("Nom") or "").strip()
                if typ and name:
                    keys.add((typ, name))
    return keys
