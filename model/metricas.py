"""Métricas de concentración compartidas por el pipeline y el tablero (antes en dashboard/motor.py)."""
import numpy as np


def hhi(valores) -> float:
    """Índice de Herfindahl-Hirschman en escala 0-10,000 (participaciones al cuadrado × 10,000)."""
    v = np.asarray(valores, dtype=float)
    v = v[v > 0]
    if v.sum() == 0:
        return 0.0
    s = v / v.sum()
    return float((s ** 2).sum() * 1e4)


def pct_top(valores, n: int = 5) -> float:
    """Porcentaje del total que concentran los n mayores."""
    v = np.sort(np.asarray(valores, dtype=float))[::-1]
    return float(v[:n].sum() / v.sum() * 100) if v.sum() else 0.0


def lorenz(valores) -> tuple[np.ndarray, np.ndarray]:
    v = np.sort(np.asarray(valores, dtype=float))
    x = np.linspace(0, 1, len(v) + 1)
    y = np.concatenate([[0], np.cumsum(v) / v.sum()]) if v.sum() else x
    return x, y


def gini(valores) -> float:
    x, y = lorenz(valores)
    return float(1 - 2 * np.trapezoid(y, x))
