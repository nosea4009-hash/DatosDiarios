"""
reader.py
=========

Lectura de los NetCDF del WRF-SMN con netCDF4 (sin depender de xarray).

Provee dos funciones principales:

- ``leer_tmin_tmax``: lee Tmin o Tmax desde un archivo "24H" para un
  "dia_offset" (0 = dia de inicializacion, 1 = dia siguiente, ...).
- ``leer_precipitacion_acumulada``: suma la variable PP de los archivos
  "01H" entre dos plazos horarios (ambos inclusive del lado derecho, tal
  cual la convencion de acumulacion del SMN: PP en el plazo P es la lluvia
  caida entre P-1 y P).

Todas las funciones devuelven lat/lon (grillas 2D, en grados) y el campo
2D de la variable ya en las unidades finales (degC o mm), junto con
metadata de fecha de validez para el titulo del plot.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import netCDF4 as nc
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Falta la libreria 'netCDF4'. Instalala con:\n"
        "    conda install -c conda-forge netcdf4\n"
        "o bien:\n"
        "    pip install netCDF4"
    ) from exc

from . import config, downloader


@dataclass
class CampoGrillado:
    """Resultado de una lectura: campo 2D + coordenadas + metadata."""

    lat: np.ndarray
    lon: np.ndarray
    x: np.ndarray
    y: np.ndarray
    data: np.ndarray            # 2D, ya en unidades finales
    variable: str                # clave interna: tmin/tmax/precip
    fecha_init: dt.date
    ciclo: str
    fecha_validez_inicio: dt.datetime
    fecha_validez_fin: dt.datetime
    proyeccion_attrs: dict


def _abrir(ruta: Path) -> "nc.Dataset":
    return nc.Dataset(ruta)


def _leer_coords(dataset: "nc.Dataset") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    lat = np.array(dataset.variables["lat"][:])
    lon = np.array(dataset.variables["lon"][:])
    x = np.array(dataset.variables["x"][:])
    y = np.array(dataset.variables["y"][:])
    return lat, lon, x, y


def _leer_proyeccion_attrs(dataset: "nc.Dataset") -> dict:
    """Extrae los atributos de la variable auxiliar Lambert_Conformal."""
    try:
        lc = dataset.variables["Lambert_Conformal"]
        return {a: getattr(lc, a) for a in lc.ncattrs()}
    except KeyError:
        # Fallback a los valores fijos conocidos del modelo (ver config.py)
        return {
            "standard_parallel": list(config.WRF_PROJ_STANDARD_PARALLELS),
            "longitude_of_central_meridian": config.WRF_PROJ_CENTRAL_LON,
            "latitude_of_projection_origin": config.WRF_PROJ_CENTRAL_LAT,
            "earth_radius": config.WRF_PROJ_EARTH_RADIUS,
        }


def leer_tmin_tmax(
    fecha_init: dt.date,
    ciclo: str,
    variable: str,
    dia_offset: int = 1,
    forzar_descarga: bool = False,
) -> CampoGrillado:
    """Lee Tmin o Tmax desde un archivo WRFDETAR_24H.

    Parameters
    ----------
    fecha_init : date
        Fecha de inicializacion del ciclo (no la fecha de validez).
    ciclo : str
        "00", "06", "12" o "18".
    variable : str
        "tmin" o "tmax".
    dia_offset : int
        Plazo en dias: 0 (dia de inicializacion), 1, 2 o 3.
    """
    if variable not in ("tmin", "tmax"):
        raise ValueError("variable debe ser 'tmin' o 'tmax'")

    info = config.get_variable_info(variable)
    ruta = downloader.descargar_archivo(
        fecha_init, ciclo, info.nombre_archivo, dia_offset, forzar=forzar_descarga
    )
    ds = _abrir(ruta)
    try:
        lat, lon, x, y = _leer_coords(ds)
        data = np.array(ds.variables[info.variable_nc][0, :, :], dtype=float)
        proyeccion_attrs = _leer_proyeccion_attrs(ds)

        # 'time' esta expresado en horas desde fecha_init (00 UTC del dia de
        # inicializacion, segun la convencion del dataset).
        horas = float(np.array(ds.variables["time"][:])[0])
        base = dt.datetime.combine(fecha_init, dt.time(0, 0))
        fecha_validez = base + dt.timedelta(hours=horas)
    finally:
        ds.close()

    if variable == "tmin":
        inicio_validez = fecha_validez.replace(hour=0)
        fin_validez = fecha_validez.replace(hour=12)
    else:
        inicio_validez = fecha_validez.replace(hour=12)
        fin_validez = inicio_validez + dt.timedelta(hours=12)

    return CampoGrillado(
        lat=lat,
        lon=lon,
        x=x,
        y=y,
        data=data,
        variable=variable,
        fecha_init=fecha_init,
        ciclo=ciclo,
        fecha_validez_inicio=inicio_validez,
        fecha_validez_fin=fin_validez,
        proyeccion_attrs=proyeccion_attrs,
    )


def leer_precipitacion_acumulada(
    fecha_init: dt.date,
    ciclo: str,
    plazo_inicio_h: int,
    plazo_fin_h: int,
    forzar_descarga: bool = False,
) -> CampoGrillado:
    """Suma la variable PP de los archivos "01H" entre dos plazos horarios.

    La convencion del SMN es que PP en el archivo de plazo P contiene la
    lluvia caida entre P-1 y P (no es un acumulado corrido). Por lo tanto
    para obtener la precipitacion acumulada en una ventana se deben sumar
    los archivos ``plazo_inicio_h + 1`` hasta ``plazo_fin_h`` (inclusive).

    Ejemplo: para el acumulado del primer dia de pronostico de un ciclo 00
    UTC, usar plazo_inicio_h=0, plazo_fin_h=24 (suma los plazos 1..24).
    """
    if plazo_fin_h <= plazo_inicio_h:
        raise ValueError("plazo_fin_h debe ser mayor que plazo_inicio_h")

    plazos = list(range(plazo_inicio_h + 1, plazo_fin_h + 1))
    rutas = downloader.descargar_lote(
        fecha_init, ciclo, "01H", plazos, forzar=forzar_descarga
    )

    acumulado = None
    lat = lon = x = y = None
    proyeccion_attrs = {}

    for ruta in rutas:
        ds = _abrir(ruta)
        try:
            if lat is None:
                lat, lon, x, y = _leer_coords(ds)
                proyeccion_attrs = _leer_proyeccion_attrs(ds)
            pp = np.array(ds.variables["PP"][0, :, :], dtype=float)
        finally:
            ds.close()
        pp = np.nan_to_num(pp, nan=0.0)
        acumulado = pp if acumulado is None else acumulado + pp

    base = dt.datetime.combine(fecha_init, dt.time(0, 0))
    inicio_validez = base + dt.timedelta(hours=plazo_inicio_h)
    fin_validez = base + dt.timedelta(hours=plazo_fin_h)

    return CampoGrillado(
        lat=lat,
        lon=lon,
        x=x,
        y=y,
        data=acumulado,
        variable="precip",
        fecha_init=fecha_init,
        ciclo=ciclo,
        fecha_validez_inicio=inicio_validez,
        fecha_validez_fin=fin_validez,
        proyeccion_attrs=proyeccion_attrs,
    )
