"""Configuration centrale du projet.

Le projet :
- récupère des données temps réel (parkings voitures + stations Vélomagg)
- stocke un historique en CSV
- calcule des corrélations entre variations de places libres
- publie une page statique (GitHub Pages) qui lit des JSON générés

Tout ce qui est "paramètre" est regroupé ici.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


# -----------------------------
# Données locales (repo)
# -----------------------------
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"

HISTORY_CSV = DATA_DIR / "historique_parkings.csv"
METADATA_JSON = DATA_DIR / "metadata.json"

LATEST_SNAPSHOT_JSON = DOCS_DATA_DIR / "latest_snapshot.json"
CORRELATIONS_JSON = DOCS_DATA_DIR / "correlations.json"
METADATA_DOCS_JSON = DOCS_DATA_DIR / "metadata.json"


# -----------------------------
# API temps réel
# -----------------------------
# Remarque : l'écosystème MMM propose plusieurs endpoints. On garde une liste
# pour pouvoir tenter un fallback si l'un d'eux change.

CAR_PARKINGS_URLS = [
    "https://portail-api-data.montpellier3m.fr/offstreetparking?limit=1000",
    "https://portail-api-data.montpellier3m.fr/parkingspaces?limit=1000",
]

BIKE_STATIONS_URLS = [
    "https://portail-api-data.montpellier3m.fr/bikestation?limit=1000",
]

HTTP_TIMEOUT_SECONDS = 25


# -----------------------------
# Analyse / corrélations
# -----------------------------
# Fenêtre d'analyse (en jours) : on ne calcule pas forcément sur tout l'historique
# pour rester "réactif" (et éviter des corrélations figées).
LOOKBACK_DAYS = 21

# Nombre minimum de points communs (après alignement temporel) pour accepter
# une corrélation.
MIN_COMMON_POINTS = 40

# Distance max (km) par défaut, utilisée côté site pour filtrer ce qui est
# "logique" géographiquement.
DEFAULT_MAX_DISTANCE_KM = 2.0

# Paramètre de pondération distance (km). Score = |r| * exp(-d / DISTANCE_WEIGHT_KM)
DISTANCE_WEIGHT_KM = 1.0

# Filtrage d'affichage par défaut
MIN_ABS_CORRELATION_TO_SHOW = 0.25
TOP_N_PAIRS = 50


# -----------------------------
# Temps
# -----------------------------
# Format IANA pour `zoneinfo.ZoneInfo`
TIMEZONE = "Europe/Paris"
