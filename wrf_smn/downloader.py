"""
downloader.py
==============

Descarga (con cache local) de archivos NetCDF del bucket publico de AWS
del SMN.

Estructura de rutas en el bucket (ver
https://odp-aws-smn.github.io/documentation_wrf_det/Estructura_de_datos/):

    DATA/WRF/DET/{YYYY}/{MM}/{DD}/{ciclo}/WRFDETAR_{frecuencia}_{YYYYMMDD}_{ciclo}_{plazo}.nc

- frecuencia: "24H" (diarios: Tmin/Tmax), "01H" (horarios: PP, T2, viento...),
  "10M" (cada 10 minutos).
- plazo: 3 digitos. Para "24H" va de 000 a 003 (dias). Para "01H"/"10M" va de
  000 a 072/073 (horas).
"""

from __future__ import annotations

import datetime as dt
import urllib.request
import urllib.error
from pathlib import Path

from . import config


class DescargaError(RuntimeError):
    """Error al descargar o localizar un archivo del bucket del SMN."""


def _url_para(fecha: dt.date, ciclo: str, frecuencia: str, plazo: int) -> str:
    """Construye la URL publica (https) de un archivo NetCDF del bucket."""
    yyyy = f"{fecha.year:04d}"
    mm = f"{fecha.month:02d}"
    dd = f"{fecha.day:02d}"
    fecha_str = f"{yyyy}{mm}{dd}"
    nombre = f"WRFDETAR_{frecuencia}_{fecha_str}_{ciclo}_{plazo:03d}.nc"
    return (
        f"{config.S3_HTTPS_BASE}/{config.S3_BASE_PREFIX}/"
        f"{yyyy}/{mm}/{dd}/{ciclo}/{nombre}"
    )


def _ruta_cache_para(fecha: dt.date, ciclo: str, frecuencia: str, plazo: int) -> Path:
    yyyy = f"{fecha.year:04d}"
    mm = f"{fecha.month:02d}"
    dd = f"{fecha.day:02d}"
    fecha_str = f"{yyyy}{mm}{dd}"
    nombre = f"WRFDETAR_{frecuencia}_{fecha_str}_{ciclo}_{plazo:03d}.nc"
    destino = config.CACHE_DIR / fecha_str / ciclo
    destino.mkdir(parents=True, exist_ok=True)
    return destino / nombre


def descargar_archivo(
    fecha: dt.date,
    ciclo: str,
    frecuencia: str,
    plazo: int,
    forzar: bool = False,
    timeout: int = 120,
) -> Path:
    """Descarga (o reutiliza cache) un archivo NetCDF del bucket del SMN.

    Parameters
    ----------
    fecha : datetime.date
        Fecha de inicializacion del ciclo de pronostico (no la fecha de
        validez del dato).
    ciclo : str
        Hora de inicializacion del ciclo: "00", "06", "12" o "18".
    frecuencia : str
        "24H", "01H" o "10M".
    plazo : int
        Plazo de pronostico. Para "24H" son dias (0-3). Para "01H"/"10M"
        son horas (0-72/73).
    forzar : bool
        Si True, descarga aunque exista en cache.
    timeout : int
        Timeout de red en segundos.

    Returns
    -------
    Path al archivo NetCDF local.
    """
    if ciclo not in config.CICLOS_VALIDOS:
        raise ValueError(
            f"Ciclo '{ciclo}' invalido. Opciones: {config.CICLOS_VALIDOS}"
        )

    destino = _ruta_cache_para(fecha, ciclo, frecuencia, plazo)
    if destino.exists() and not forzar:
        return destino

    url = _url_para(fecha, ciclo, frecuencia, plazo)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as respuesta:
            contenido = respuesta.read()
    except urllib.error.HTTPError as exc:
        raise DescargaError(
            f"No se encontro el archivo en el bucket del SMN.\n"
            f"URL: {url}\n"
            f"HTTP {exc.code}: {exc.reason}\n"
            f"Verifica que la fecha/ciclo/plazo existan (los datos se "
            f"publican con algunas horas de demora y el lead time maximo "
            f"es de 72 horas)."
        ) from exc
    except urllib.error.URLError as exc:
        raise DescargaError(
            f"No se pudo conectar al bucket del SMN ({url}): {exc.reason}"
        ) from exc

    tmp = destino.with_suffix(".tmp")
    tmp.write_bytes(contenido)
    tmp.rename(destino)
    return destino


def descargar_lote(
    fecha: dt.date,
    ciclo: str,
    frecuencia: str,
    plazos: list[int],
    forzar: bool = False,
) -> list[Path]:
    """Descarga varios plazos de una misma frecuencia (usado para acumular PP)."""
    rutas = []
    for plazo in plazos:
        rutas.append(
            descargar_archivo(fecha, ciclo, frecuencia, plazo, forzar=forzar)
        )
    return rutas
