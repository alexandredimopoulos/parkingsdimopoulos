# Parkings Montpellier — site GitHub Pages + mises à jour horaires

Ce dépôt contient :

- un **historique CSV** (`data/historique_parkings.csv`)
- des **scripts Python** qui :
  - récupèrent les disponibilités en temps réel (parkings voitures + stations Vélomagg)
  - ajoutent une nouvelle ligne par parking/station à l'historique
  - recalculent les **corrélations** entre variations de places libres
- un **site statique** (`docs/`) publié via **GitHub Pages**

L'actualisation automatique est faite via un **GitHub Workflow** programmé toutes les heures.

---

## Publier le site sur GitHub Pages

1. Pousser ce repo sur GitHub
2. Dans **Settings → Pages** :
   - Source : `Deploy from a branch`
   - Branch : `main`
   - Folder : `/docs`
3. Attendre que GitHub Pages publie l'URL du site.

---

## Mise à jour automatique (GitHub Actions)

Le workflow `.github/workflows/update.yml` :

- tourne toutes les heures (cron)
- exécute :
  - `python scripts/update_data.py`
  - `python scripts/analyze_correlations.py`
- commit/push les changements générés (CSV + JSON dans `docs/data/...`).

---

## Structure

```
.
├── data/
│   ├── historique_parkings.csv
│   └── metadata.json               # généré/actualisé (coordonnées)
├── docs/
│   ├── index.html                  # site (GitHub Pages)
│   ├── .nojekyll
│   ├── assets/
│   │   ├── app.js
│   │   └── style.css
│   └── data/
│       ┬ latest_snapshot.json      # généré
│       ├ correlations.json         # généré
│       └ metadata.json             # copie (généré)
├── scripts/
│   ├── analyze_correlations.py
│   ├── config.py
│   ├── geo.py
│   ├── stats_lib.py
│   ├── update_data.py
│   └── utils.py
└── .github/
    └── workflows/
        └── update.yml
```

---

## Analyse : ce que signifie la corrélation

On calcule la corrélation de Pearson sur les **variations** (Δ) de places libres :

- Parking voiture : `Δ(places_libres_voiture)`
- Station vélo : `Δ(places_libres_velo)` (places de stationnement disponibles = `freeSlotNumber`)

Une corrélation **négative** signifie : quand l'un augmente, l'autre a tendance à diminuer.

On ajoute une logique géographique :

- on calcule la distance (km) entre parking voiture et station vélo
- le site filtre par défaut au delà d'une distance max (réglable sur la page)
- le score est pondéré : `score = |corr| * exp(-distance_km / DISTANCE_WEIGHT_KM)`

Les paramètres sont modifiables dans `scripts/config.py`.

---

## Lancer en local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/update_data.py
python scripts/analyze_correlations.py

cd docs
python -m http.server 8000
```

Puis ouvrir `http://localhost:8000`.

---

## Notes

- Les endpoints utilisés sont dans `scripts/config.py`.
- Si un endpoint change, le script essaie un fallback.
