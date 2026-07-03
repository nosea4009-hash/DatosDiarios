"""
cities.py
=========

Manejo del catalogo de ciudades argentinas que se dibujan sobre el mapa:
carga desde CSV, filtrado por extent visible y un algoritmo simple de
anti-solapamiento de etiquetas (evita que los nombres de ciudad se pisen
entre si cuando estan muy juntas, sobre todo al hacer zoom).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class Ciudad:
    nombre: str
    provincia: str
    lat: float
    lon: float
    categoria: str


def cargar_ciudades(ruta_csv: Path | None = None) -> list[Ciudad]:
    """Lee el catalogo de ciudades desde un CSV.

    Columnas esperadas: ciudad, provincia, lat, lon, categoria
    """
    ruta_csv = ruta_csv or config.CIUDADES_CSV
    ciudades: list[Ciudad] = []
    with open(ruta_csv, newline="", encoding="utf-8") as f:
        lector = csv.DictReader(f)
        for fila in lector:
            ciudades.append(
                Ciudad(
                    nombre=fila["ciudad"].strip(),
                    provincia=fila["provincia"].strip(),
                    lat=float(fila["lat"]),
                    lon=float(fila["lon"]),
                    categoria=fila.get("categoria", "ciudad").strip(),
                )
            )
    return ciudades


def filtrar_por_extent(
    ciudades: list[Ciudad],
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    margen_grados: float = 0.5,
) -> list[Ciudad]:
    """Devuelve solo las ciudades dentro (o cerca) del extent visible."""
    lon_min -= margen_grados
    lon_max += margen_grados
    lat_min -= margen_grados
    lat_max += margen_grados
    return [
        c
        for c in ciudades
        if lon_min <= c.lon <= lon_max and lat_min <= c.lat <= lat_max
    ]


def limitar_cantidad(
    ciudades: list[Ciudad], maximo: int, extent_area_deg2: float
) -> list[Ciudad]:
    """Prioriza capitales cuando hay demasiadas ciudades para el area visible.

    Al hacer zoom a un municipio chico interesa ver todas las localidades
    cercanas, pero en el mapa completo de Argentina mostrar >80 ciudades
    saturaria el plot. Se usa el area visible (en grados^2) como proxy del
    nivel de zoom.
    """
    if len(ciudades) <= maximo:
        return ciudades

    orden_prioridad = {"capital_nacional": 0, "capital_provincial": 1, "ciudad": 2}
    ciudades_ordenadas = sorted(
        ciudades, key=lambda c: orden_prioridad.get(c.categoria, 3)
    )
    return ciudades_ordenadas[:maximo]


def evitar_solapamiento(
    posiciones_pixel: list[tuple[float, float]],
    tamanos_texto: list[tuple[float, float]],
    distancia_minima: float = 4.0,
) -> list[bool]:
    """Algoritmo simple O(n^2) de anti-solapamiento basado en distancia.

    Dada una lista de posiciones (x, y) en pixeles y el tamano aproximado
    (ancho, alto) de cada etiqueta, devuelve una mascara booleana indicando
    que etiquetas conservar (True = mostrar), descartando las que se
    superponen con una ya aceptada (se prioriza el orden de la lista, que
    debe venir pre-ordenada por importancia).
    """
    aceptadas: list[tuple[float, float, float, float]] = []  # x0,x1,y0,y1
    mascara = [False] * len(posiciones_pixel)

    for i, (x, y) in enumerate(posiciones_pixel):
        w, h = tamanos_texto[i]
        x0, x1 = x - w / 2 - distancia_minima, x + w / 2 + distancia_minima
        y0, y1 = y - h / 2 - distancia_minima, y + h / 2 + distancia_minima

        solapa = False
        for (ax0, ax1, ay0, ay1) in aceptadas:
            if x0 < ax1 and x1 > ax0 and y0 < ay1 and y1 > ay0:
                solapa = True
                break

        if not solapa:
            mascara[i] = True
            aceptadas.append((x0, x1, y0, y1))

    return mascara
