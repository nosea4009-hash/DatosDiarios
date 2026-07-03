"""
cli.py
======

Interfaz de linea de comandos. Ver ``main.py`` en la raiz del repo para el
punto de entrada ejecutable.

Ejemplos de uso
----------------

Temperatura minima del dia siguiente al ciclo 00Z de hoy, mapa completo:

    python main.py --variable tmin --fecha 2026-07-03 --ciclo 00 --dia 1

Temperatura maxima, con zoom a un solo municipio/departamento via geojson:

    python main.py --variable tmax --fecha 2026-07-03 --ciclo 00 --dia 1 \\
        --geojson data/geojson/pergamino.geojson

Temperatura minima, con zoom a una PROVINCIA COMPLETA (mostrando el
contorno de todos sus departamentos), a partir de un geojson que contiene
los departamentos de toda Argentina o de varias provincias:

    python main.py --variable tmin --fecha 2026-07-03 --ciclo 00 --dia 1 \\
        --geojson data/geojson/departamentos_argentina.geojson \\
        --geojson-provincia "Buenos Aires"

Precipitacion acumulada en las primeras 24 horas de pronostico:

    python main.py --variable precip --fecha 2026-07-03 --ciclo 00 \\
        --plazo-inicio 0 --plazo-fin 24

Listar los geojson disponibles para zoom:

    python main.py --listar-geojson
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import config, plotting, reader, zoom as zoom_mod


def _parsear_fecha(valor: str) -> dt.date:
    try:
        return dt.datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Fecha invalida '{valor}'. Formato esperado: YYYY-MM-DD"
        ) from exc


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wrf_smn",
        description=(
            "Genera mapas de Temperatura Minima, Temperatura Maxima o "
            "Precipitacion Acumulada a partir del modelo WRF 4km del SMN "
            "(bucket publico de AWS)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--variable", choices=config.VARIABLES_VALIDAS,
        help="Variable a graficar: tmin, tmax o precip.",
    )
    parser.add_argument(
        "--fecha", type=_parsear_fecha, default=dt.date.today(),
        help="Fecha de inicializacion del ciclo (YYYY-MM-DD). Default: hoy.",
    )
    parser.add_argument(
        "--ciclo", choices=config.CICLOS_VALIDOS, default="00",
        help="Ciclo de inicializacion UTC (00, 06, 12, 18). Default: 00.",
    )
    parser.add_argument(
        "--dia", type=int, default=1,
        help=(
            "Solo para tmin/tmax: plazo en dias (0=dia de inicializacion, "
            "1, 2 o 3). Default: 1."
        ),
    )
    parser.add_argument(
        "--plazo-inicio", type=int, default=None,
        help="Solo para precip: plazo horario inicial del acumulado (ej. 0).",
    )
    parser.add_argument(
        "--plazo-fin", type=int, default=None,
        help="Solo para precip: plazo horario final del acumulado (ej. 24).",
    )
    parser.add_argument(
        "--geojson", type=str, default=None,
        help=(
            "Ruta a un archivo .geojson (municipio, departamento, region) "
            "para hacer zoom automatico y dibujar su contorno sobre el mapa."
        ),
    )
    parser.add_argument(
        "--geojson-filtro", type=str, default=None,
        help=(
            "Si el geojson contiene varias regiones, texto para filtrar "
            "por nombre de departamento/municipio (busqueda parcial, "
            "insensible a mayusculas). Muestra solo ese departamento."
        ),
    )
    parser.add_argument(
        "--geojson-provincia", type=str, default=None,
        help=(
            "Si el geojson contiene todos los departamentos de Argentina "
            "(o de varias provincias), texto para filtrar por PROVINCIA "
            "(busqueda parcial, insensible a mayusculas). Hace zoom a la "
            "provincia completa manteniendo visibles los contornos de "
            "TODOS sus departamentos. Tiene prioridad sobre --geojson-filtro."
        ),
    )
    parser.add_argument(
        "--extent", type=float, nargs=4, default=None,
        metavar=("LON_MIN", "LON_MAX", "LAT_MIN", "LAT_MAX"),
        help="Recorte manual del mapa en grados decimales.",
    )
    parser.add_argument(
        "--max-ciudades", type=int, default=45,
        help="Cantidad maxima de ciudades a rotular en el mapa. Default: 45.",
    )
    parser.add_argument(
        "--salida", type=str, default=None,
        help="Ruta del PNG de salida. Default: autogenerada en salidas/.",
    )
    parser.add_argument(
        "--forzar-descarga", action="store_true",
        help="Ignora la cache local y vuelve a descargar los NetCDF.",
    )
    parser.add_argument(
        "--listar-geojson", action="store_true",
        help=f"Lista los .geojson disponibles en {config.GEOJSON_DIR} y termina.",
    )

    return parser


def _sanear_nombre_archivo(texto: str) -> str:
    """Reemplaza caracteres no validos en nombres de archivo de Windows
    (``< > : " / \\ | ? *``) y espacios, para evitar errores como
    ``[Errno 22] Invalid argument`` al guardar el PNG."""
    caracteres_invalidos = '<>:"/\\|?*'
    texto_saneado = texto
    for caracter in caracteres_invalidos:
        texto_saneado = texto_saneado.replace(caracter, "")
    return texto_saneado.strip().replace(" ", "_")


def _nombre_salida_por_defecto(variable: str, fecha: dt.date, ciclo: str,
                                sufijo_zoom: str = "") -> str:
    base = f"{variable}_{fecha:%Y%m%d}_{ciclo}Z{sufijo_zoom}.png"
    return base


def ejecutar(argv: list[str] | None = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.listar_geojson:
        archivos = zoom_mod.listar_geojson_disponibles(config.GEOJSON_DIR)
        if not archivos:
            print(f"No hay archivos .geojson en {config.GEOJSON_DIR}")
            print(
                "Coloca ahi tus archivos de municipios/regiones (formato "
                ".geojson) y volve a correr con --listar-geojson."
            )
        else:
            print(f"Archivos .geojson disponibles en {config.GEOJSON_DIR}:")
            for a in archivos:
                print(f"  - {a.name}")
        return 0

    if not args.variable:
        parser.error("--variable es requerido (tmin, tmax o precip)")

    region_zoom = None
    if args.geojson:
        try:
            region_zoom = zoom_mod.cargar_region_zoom(
                args.geojson,
                filtro_nombre=args.geojson_filtro,
                filtro_provincia=args.geojson_provincia,
            )
        except Exception as exc:
            print(f"Error al cargar el geojson '{args.geojson}': {exc}", file=sys.stderr)
            return 1
        print(
            f"Zoom aplicado a region '{region_zoom.nombre}' -> "
            f"lon[{region_zoom.lon_min:.2f}, {region_zoom.lon_max:.2f}] "
            f"lat[{region_zoom.lat_min:.2f}, {region_zoom.lat_max:.2f}]"
        )

    extent = tuple(args.extent) if args.extent else None

    try:
        if args.variable in ("tmin", "tmax"):
            campo = reader.leer_tmin_tmax(
                fecha_init=args.fecha,
                ciclo=args.ciclo,
                variable=args.variable,
                dia_offset=args.dia,
                forzar_descarga=args.forzar_descarga,
            )
        else:
            plazo_inicio = args.plazo_inicio if args.plazo_inicio is not None else 0
            plazo_fin = args.plazo_fin if args.plazo_fin is not None else 24
            campo = reader.leer_precipitacion_acumulada(
                fecha_init=args.fecha,
                ciclo=args.ciclo,
                plazo_inicio_h=plazo_inicio,
                plazo_fin_h=plazo_fin,
                forzar_descarga=args.forzar_descarga,
            )
    except Exception as exc:
        print(f"Error al leer los datos del WRF-SMN: {exc}", file=sys.stderr)
        return 1

    if args.salida:
        ruta_salida = config.OUTPUT_DIR / args.salida if not args.salida.startswith("/") \
            else __import__("pathlib").Path(args.salida)
    else:
        sufijo_zoom = f"_{_sanear_nombre_archivo(region_zoom.nombre)}" if region_zoom else ""
        nombre = _nombre_salida_por_defecto(args.variable, args.fecha, args.ciclo, sufijo_zoom)
        ruta_salida = config.OUTPUT_DIR / nombre

    try:
        ruta_final = plotting.graficar_campo(
            campo,
            ruta_salida=ruta_salida,
            extent=extent,
            region_zoom=region_zoom,
            max_ciudades=args.max_ciudades,
        )
    except Exception as exc:
        print(f"Error al generar el grafico: {exc}", file=sys.stderr)
        return 1

    print(f"Mapa generado correctamente: {ruta_final}")
    return 0


def main() -> None:
    sys.exit(ejecutar())
