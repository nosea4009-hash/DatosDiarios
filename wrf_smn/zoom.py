"""
zoom.py
=======

Soporte para hacer zoom a un municipio, departamento o region a partir de
un archivo .geojson provisto por el usuario (por ejemplo, capas de INDEC,
IGN o cualquier geojson de limites administrativos de Argentina).

Uso tipico:

    python main.py --variable tmin --geojson data/geojson/mi_municipio.geojson

El geojson se usa para:
1. Calcular automaticamente el "extent" (recorte de lat/lon) del mapa.
2. Dibujar el contorno del municipio/region sobre el mapa como referencia
   visual (linea negra fina).

Requiere geopandas + shapely (incluidas en requirements.txt).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import geopandas as gpd


@dataclass
class RegionZoom:
    """Resultado de cargar un geojson de zoom."""

    gdf: "gpd.GeoDataFrame"
    lon_min: float
    lon_max: float
    lat_min: float
    lat_max: float
    nombre: str


def _detectar_columna_nombre(gdf: "gpd.GeoDataFrame") -> Optional[str]:
    """Intenta adivinar la columna que contiene el nombre del municipio/region."""
    candidatos = [
        "nombre", "NOMBRE", "name", "NAME", "NAM", "nam",
        "departamen", "municipio", "MUNICIPIO", "nombre_dpt",
        "NOMBRE_DPT", "nombre_ar", "in1", "fna",
    ]
    for col in candidatos:
        if col in gdf.columns:
            return col
    # Si hay alguna columna de texto no geometrica, usar la primera
    for col in gdf.columns:
        if col != "geometry" and gdf[col].dtype == object:
            return col
    return None


def cargar_region_zoom(
    ruta_geojson: str | Path,
    margen_grados: float = 0.35,
    filtro_nombre: Optional[str] = None,
) -> RegionZoom:
    """Carga un geojson y calcula el extent (con margen) para hacer zoom.

    Parameters
    ----------
    ruta_geojson : str | Path
        Archivo .geojson con uno o mas poligonos (municipios, departamentos,
        provincias, cuencas, etc.).
    margen_grados : float
        Margen adicional (en grados) alrededor del bounding box del/los
        poligono(s), para que el recorte no quede exactamente pegado al
        borde de la region.
    filtro_nombre : str, opcional
        Si el geojson contiene varias regiones (ej. todos los municipios de
        una provincia) y se quiere hacer zoom a una sola, se puede pasar un
        texto (case-insensitive, busqueda parcial) que se busca en la
        columna de nombre detectada automaticamente.
    """
    ruta_geojson = Path(ruta_geojson)
    if not ruta_geojson.exists():
        raise FileNotFoundError(f"No se encontro el geojson: {ruta_geojson}")

    gdf = gpd.read_file(ruta_geojson)
    if gdf.empty:
        raise ValueError(f"El geojson {ruta_geojson} no contiene geometrias")

    # Asegurar CRS geografico (lat/lon, EPSG:4326)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    nombre_region = ruta_geojson.stem
    if filtro_nombre:
        col_nombre = _detectar_columna_nombre(gdf)
        if col_nombre is not None:
            mascara = gdf[col_nombre].astype(str).str.contains(
                filtro_nombre, case=False, na=False, regex=False
            )
            if mascara.any():
                gdf = gdf[mascara]
                nombre_region = str(gdf.iloc[0][col_nombre])
            else:
                raise ValueError(
                    f"No se encontro ninguna region que contenga "
                    f"'{filtro_nombre}' en la columna '{col_nombre}' del geojson"
                )
    elif len(gdf) == 1:
        col_nombre = _detectar_columna_nombre(gdf)
        if col_nombre is not None:
            nombre_region = str(gdf.iloc[0][col_nombre])

    lon_min, lat_min, lon_max, lat_max = gdf.total_bounds

    return RegionZoom(
        gdf=gdf,
        lon_min=float(lon_min) - margen_grados,
        lon_max=float(lon_max) + margen_grados,
        lat_min=float(lat_min) - margen_grados,
        lat_max=float(lat_max) + margen_grados,
        nombre=nombre_region,
    )


def listar_geojson_disponibles(directorio: Path) -> list[Path]:
    """Lista los .geojson / .json disponibles en el directorio de zoom."""
    if not directorio.exists():
        return []
    patrones = ("*.geojson", "*.json")
    archivos: list[Path] = []
    for patron in patrones:
        archivos.extend(sorted(directorio.glob(patron)))
    return archivos
