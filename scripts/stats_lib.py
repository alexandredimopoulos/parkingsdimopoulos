"""Librairie de statistiques (DM1).

Fonctions demandées :
1) moyenne
2) ecart_type
3) variance
4) covariance
5) coefficient de corrélation
6) matrice de corrélation (NxN)

Les calculs sont faits "à la main" (sans numpy/pandas) :
- variance population : (1/n) * Σ (xi - m)^2
- covariance population : (1/n) * Σ (xi - mx) (yi - my)
- corrélation : cov / (σx * σy)

Si une liste est vide, une ValueError est levée.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence


def _as_list(values: Iterable[float]) -> List[float]:
    lst = list(values)
    if len(lst) == 0:
        raise ValueError("Liste vide")
    return lst


def moyenne(values: Iterable[float]) -> float:
    vals = _as_list(values)
    return sum(vals) / len(vals)


def variance(values: Iterable[float]) -> float:
    vals = _as_list(values)
    m = moyenne(vals)
    return sum((x - m) ** 2 for x in vals) / len(vals)


def ecart_type(values: Iterable[float]) -> float:
    return math.sqrt(variance(values))


def covariance(x: Iterable[float], y: Iterable[float]) -> float:
    xs = _as_list(x)
    ys = _as_list(y)
    if len(xs) != len(ys):
        raise ValueError("Listes de tailles différentes")
    mx = moyenne(xs)
    my = moyenne(ys)
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / len(xs)


def correlation(x: Iterable[float], y: Iterable[float]) -> float:
    """Coefficient de corrélation de Pearson.

    Retourne 0.0 si l'écart-type d'une des séries est nul.
    """
    xs = _as_list(x)
    ys = _as_list(y)
    if len(xs) != len(ys):
        raise ValueError("Listes de tailles différentes")

    sx = ecart_type(xs)
    sy = ecart_type(ys)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return covariance(xs, ys) / (sx * sy)


def matrice_correlation(series: Sequence[Sequence[float]]) -> List[List[float]]:
    """Matrice NxN des corrélations entre N séries."""
    if len(series) == 0:
        raise ValueError("Aucune série")
    n = len(series)
    mat: List[List[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            mat[i][j] = correlation(series[i], series[j])
    return mat
