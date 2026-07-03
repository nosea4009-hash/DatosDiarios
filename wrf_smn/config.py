"""
config.py
=========

Configuracion centralizada del proyecto: paleta de colores, tipografias,
metadata de variables meteorologicas, proyeccion del modelo WRF-SMN y
rutas por defecto.

Todo lo que sea "estetica" del mapa (colores de fondo, agua, fuentes,
tamanos) vive aca para que sea facil de tunear sin tocar el resto del
codigo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import matplotlib.font_manager as fm
import numpy as np

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = PROJECT_ROOT / "cache"          # NetCDF descargados
OUTPUT_DIR = PROJECT_ROOT / "salidas"       # PNG generados
GEOJSON_DIR = DATA_DIR / "geojson"          # geojson de municipios/regiones del usuario
CIUDADES_CSV = DATA_DIR / "ciudades_ar.csv"

for _dir in (DATA_DIR, CACHE_DIR, OUTPUT_DIR, GEOJSON_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Bucket S3 publico del SMN (Open Data Program de AWS)
# https://registry.opendata.aws/smn-ar-wrf-dataset/
# ---------------------------------------------------------------------------

S3_BUCKET = "smn-ar-wrf"
S3_BASE_PREFIX = "DATA/WRF/DET"
S3_HTTPS_BASE = f"https://{S3_BUCKET}.s3.amazonaws.com"

# Ciclos de inicializacion validos (UTC)
CICLOS_VALIDOS = ("00", "06", "12", "18")

# ---------------------------------------------------------------------------
# Colores solicitados por el usuario
# ---------------------------------------------------------------------------

COLOR_TIERRA = "#f2eeed"     # continente / mapa base
COLOR_AGUA = "#dce6f0"       # oceano, rios, lagos
COLOR_BORDES_PAIS = "#4d4d4d"
COLOR_BORDES_PROV = "#8c8c8c"
COLOR_RECUADRO = "#000000"   # contorno del recuadro blanco exterior
COLOR_TEXTO_CIUDAD = "#000000"
COLOR_CONTORNO_TEXTO_CIUDAD = "#ffffff"
COLOR_MARCADOR_RELLENO = "#ffffff"
COLOR_MARCADOR_BORDE = "#000000"

# ---------------------------------------------------------------------------
# Tipografia: Tahoma / Tahoma Bold (instaladas localmente por el usuario).
# Si no estan disponibles en el sistema (p. ej. Linux/CI) se hace fallback
# automatico a DejaVu Sans para que el script nunca falle.
# ---------------------------------------------------------------------------


def _resolver_fuente(nombre_preferido: str, bold: bool) -> str:
    """Devuelve el nombre de familia de fuente a usar en matplotlib.

    Intenta usar la fuente preferida (Tahoma / Tahoma Bold). Si no esta
    instalada en el sistema, cae en una fuente de reemplazo para que el
    script siga funcionando en cualquier maquina.
    """
    disponibles = {f.name for f in fm.fontManager.ttflist}
    if nombre_preferido in disponibles:
        return nombre_preferido

    # Variantes comunes de nombre para Tahoma Bold segun el sistema
    if bold:
        for alt in ("Tahoma Bold", "Tahoma-Bold", "Tahoma"):
            if alt in disponibles:
                return alt
    else:
        if "Tahoma" in disponibles:
            return "Tahoma"

    # Fallback seguro, siempre presente en matplotlib
    return "DejaVu Sans"


FUENTE_REGULAR = _resolver_fuente("Tahoma", bold=False)
FUENTE_BOLD = _resolver_fuente("Tahoma Bold", bold=True)

# ---------------------------------------------------------------------------
# Proyeccion del modelo WRF-SMN (Lambert Conformal Conic)
# Fuente: atributos globales / variable Lambert_Conformal de los NetCDF,
# y https://odp-aws-smn.github.io/documentation_wrf_det/Formato_de_datos/
# ---------------------------------------------------------------------------

WRF_PROJ_STANDARD_PARALLELS = (-35.0, -35.0)
WRF_PROJ_CENTRAL_LON = -65.0
WRF_PROJ_CENTRAL_LAT = -34.99999
WRF_PROJ_EARTH_RADIUS = 6370000.0
WRF_DX_M = 4000.0
WRF_DY_M = 4000.0

# Dominio completo aproximado del modelo (para "extent" por defecto)
DOMINIO_LAT_MIN = -56.9
DOMINIO_LAT_MAX = -11.6
DOMINIO_LON_MIN = -94.4
DOMINIO_LON_MAX = -35.6


# ---------------------------------------------------------------------------
# Metadata de variables soportadas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariableInfo:
    """Metadata necesaria para leer y graficar una variable."""

    clave: str                      # identificador interno (tmin, tmax, precip)
    nombre_archivo: str             # prefijo de archivo NetCDF (24H o 01H)
    variable_nc: str                # nombre de la variable dentro del NetCDF
    titulo: str                     # texto que aparece arriba del plot
    etiqueta_colorbar: str          # texto de la colorbar
    unidad: str
    cmap: str                       # nombre de colormap o tabla de metpy
    vmin: Optional[float]
    vmax: Optional[float]
    niveles: Optional[np.ndarray]
    es_acumulada: bool = False      # True => hay que sumar plazos horarios


def _niveles_temperatura() -> np.ndarray:
    return np.arange(-20, 46, 2)


def _niveles_precipitacion() -> np.ndarray:
    return np.array(
        [0, 0.1, 1, 2, 4, 6, 8, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100,
         125, 150, 200, 250, 300]
    )


VARIABLES: dict[str, VariableInfo] = {
    "tmin": VariableInfo(
        clave="tmin",
        nombre_archivo="24H",
        variable_nc="Tmin",
        titulo="Temperatura Minima",
        etiqueta_colorbar="Temperatura (grados Celsius)",
        unidad="degC",
        cmap="RdBu_r",
        vmin=-20,
        vmax=45,
        niveles=_niveles_temperatura(),
    ),
    "tmax": VariableInfo(
        clave="tmax",
        nombre_archivo="24H",
        variable_nc="Tmax",
        titulo="Temperatura Maxima",
        etiqueta_colorbar="Temperatura (grados Celsius)",
        unidad="degC",
        cmap="RdBu_r",
        vmin=-20,
        vmax=45,
        niveles=_niveles_temperatura(),
    ),
    "precip": VariableInfo(
        clave="precip",
        nombre_archivo="01H",
        variable_nc="PP",
        titulo="Precipitacion Acumulada",
        etiqueta_colorbar="Precipitacion (mm, somb.)",
        unidad="mm",
        cmap="precipitation",
        vmin=0,
        vmax=300,
        niveles=_niveles_precipitacion(),
        es_acumulada=True,
    ),
}

VARIABLES_VALIDAS = tuple(VARIABLES.keys())


def get_variable_info(clave: str) -> VariableInfo:
    clave = clave.lower().strip()
    if clave not in VARIABLES:
        opciones = ", ".join(VARIABLES_VALIDAS)
        raise ValueError(f"Variable '{clave}' invalida. Opciones: {opciones}")
    return VARIABLES[clave]


# ---------------------------------------------------------------------------
# Ajustes generales de la figura
# ---------------------------------------------------------------------------

FIGSIZE = (11, 13)
DPI = 200
LINEWIDTH_COSTAS = 0.6
LINEWIDTH_PAISES = 0.9
LINEWIDTH_PROVINCIAS = 0.5
FONTSIZE_TITULO = 17
FONTSIZE_SUBTITULO = 11
FONTSIZE_CIUDAD = 8.5
FONTSIZE_COLORBAR_LABEL = 11
FONTSIZE_COLORBAR_TICKS = 9
FONTSIZE_GRIDLINES = 8
MARCADOR_CIUDAD_TAMANO = 28
