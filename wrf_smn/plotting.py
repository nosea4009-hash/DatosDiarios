"""
plotting.py
===========

Generacion del mapa final: estetica clasica de MetPy, con:

- Fondo de continente en ``config.COLOR_TIERRA`` (#f2eeed) y de
  oceano/rios/lagos en ``config.COLOR_AGUA`` (#dce6f0).
- Recuadro blanco alrededor del mapa (fondo de figura blanco + spine
  negro delimitando el area de ploteo).
- Colorbar vertical a la derecha con la etiqueta de la variable.
- Titulo superior en Tahoma Bold indicando variable + fecha.
- Nombres de ciudades en negro con contorno blanco (fuente Tahoma Bold) y
  un pequeno circulo blanco de borde negro marcando su ubicacion exacta.
- Grilla de lat/lon en los 4 bordes, escala grafica y flecha de norte,
  al estilo de mapas meteorologicos profesionales (ver imagen de
  referencia adjuntada por el usuario).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cartopy.io.shapereader as shpreader
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from matplotlib.patheffects import withStroke
from shapely.ops import unary_union
from shapely.vectorized import contains as shapely_contains

from . import cities as cities_mod
from . import config
from . import zoom as zoom_mod
from .reader import CampoGrillado

try:
    from metpy.plots import ctables as metpy_ctables
except ImportError:  # pragma: no cover
    metpy_ctables = None


# ---------------------------------------------------------------------------
# Proyeccion nativa del modelo WRF-SMN
# ---------------------------------------------------------------------------


def proyeccion_wrf() -> ccrs.LambertConformal:
    # NOTA: cartopy.LambertConformal usa un parametro `cutoff` (por defecto
    # -30, pensado para dominios del hemisferio norte) que recorta la
    # proyeccion en la latitud opuesta al `central_latitude`. Como el
    # dominio del WRF-SMN esta en el hemisferio sur, hay que moverlo a un
    # valor cercano al ecuador (-5) para no perder territorio. Este mismo
    # valor es el que usa el tutorial oficial del SMN
    # (T2m_streamlines, https://odp-aws-smn.github.io/documentation_wrf_det/).
    return ccrs.LambertConformal(
        central_longitude=config.WRF_PROJ_CENTRAL_LON,
        central_latitude=config.WRF_PROJ_CENTRAL_LAT,
        standard_parallels=config.WRF_PROJ_STANDARD_PARALLELS,
        globe=ccrs.Globe(ellipse=None, semimajor_axis=config.WRF_PROJ_EARTH_RADIUS,
                          semiminor_axis=config.WRF_PROJ_EARTH_RADIUS),
        cutoff=-5,
    )


# ---------------------------------------------------------------------------
# Colormaps / normas por variable
# ---------------------------------------------------------------------------


def _construir_cmap_temperatura(niveles: np.ndarray) -> tuple[mcolors.BoundaryNorm, mcolors.Colormap]:
    base = plt.get_cmap("RdYlBu_r")
    n_bins = len(niveles) - 1
    colores = base(np.linspace(0.02, 0.98, n_bins))
    cmap = mcolors.ListedColormap(colores)
    cmap.set_under(base(0.0))
    cmap.set_over(base(1.0))
    norm = mcolors.BoundaryNorm(niveles, cmap.N)
    return norm, cmap


def _construir_cmap_precipitacion(niveles: np.ndarray) -> tuple[mcolors.BoundaryNorm, mcolors.Colormap]:
    if metpy_ctables is not None:
        try:
            norm, cmap = metpy_ctables.registry.get_with_boundaries(
                "precipitation", niveles
            )
            return norm, cmap
        except Exception:
            pass
    # Fallback si metpy no esta disponible: escala secuencial azul/verde/violeta
    base = plt.get_cmap("gist_ncar")
    n_bins = len(niveles) - 1
    colores = base(np.linspace(0.05, 0.95, n_bins))
    cmap = mcolors.ListedColormap(colores)
    norm = mcolors.BoundaryNorm(niveles, cmap.N)
    return norm, cmap


def _norm_cmap_para(variable: str, niveles: np.ndarray):
    if variable == "precip":
        return _construir_cmap_precipitacion(niveles)
    return _construir_cmap_temperatura(niveles)


_GEOMETRIA_TIERRA_CACHE = None


def _geometria_tierra():
    """Carga (con cache en memoria) el poligono unificado de continentes
    de Natural Earth, usado para enmascarar el campo sobre el oceano.

    El modelo WRF-SMN calcula Tmin/Tmax/PP tambien sobre el mar, pero el
    usuario pidio que el oceano/rios/lagos se vean siempre con el color
    de agua (#dce6f0) para mantener la estetica clasica de MetPy, en vez
    de mostrar la sombra de la variable meteorologica sobre el agua.
    """
    global _GEOMETRIA_TIERRA_CACHE
    if _GEOMETRIA_TIERRA_CACHE is None:
        shp = shpreader.natural_earth(
            resolution="10m", category="physical", name="land"
        )
        geometrias = list(shpreader.Reader(shp).geometries())
        _GEOMETRIA_TIERRA_CACHE = unary_union(geometrias)
    return _GEOMETRIA_TIERRA_CACHE


def _enmascarar_oceano(lon: np.ndarray, lat: np.ndarray, data: np.ndarray) -> np.ndarray:
    """Devuelve una copia de ``data`` con NaN en los puntos sobre el oceano
    (fuera del poligono de continentes), para que se vea el color de agua
    de fondo en lugar de la sombra de la variable."""
    tierra = _geometria_tierra()
    es_tierra = shapely_contains(tierra, lon, lat)
    data_enmascarada = np.where(es_tierra, data, np.nan)
    return data_enmascarada


def _extent_proyectado_desde_grilla(
    extent_lonlat: tuple[float, float, float, float],
    campo: CampoGrillado,
) -> tuple[float, float, float, float]:
    """Calcula el extent en coordenadas nativas (x0, x1, y0, y1, metros)
    correspondiente a un extent en lat/lon, usando la grilla real de datos.

    IMPORTANTE: no conviene transformar geometricamente solo las 4 esquinas
    (o el borde) de la caja lat/lon a la proyeccion Lambert Conformal: como
    los meridianos se curvan en esta proyeccion, ese bounding box queda
    notoriamente mas grande que el area real cubierta por los datos (se ve
    un efecto de "recuadro" mucho mayor que la mancha de colores). En
    cambio, se usa la grilla nativa (x, y) del propio NetCDF y se recorta
    en base a que lat/lon (2D) caigan dentro del rango pedido: esto da un
    bounding box ajustado a los datos reales, igual de preciso que el
    utilizado por el tutorial oficial del SMN para el dominio completo
    (https://odp-aws-smn.github.io/documentation_wrf_det/T2m_streamlines/).
    """
    lon_min, lon_max, lat_min, lat_max = extent_lonlat

    mascara = (
        (campo.lon >= lon_min) & (campo.lon <= lon_max)
        & (campo.lat >= lat_min) & (campo.lat <= lat_max)
    )
    if not mascara.any():
        raise ValueError(
            "El extent solicitado no intersecta con el dominio de datos del "
            "WRF-SMN (Argentina, Chile, Uruguay, Paraguay y zonas linderas)."
        )

    X, Y = np.meshgrid(campo.x, campo.y)
    x0, x1 = float(X[mascara].min()), float(X[mascara].max())
    y0, y1 = float(Y[mascara].min()), float(Y[mascara].max())
    return x0, x1, y0, y1


# ---------------------------------------------------------------------------
# Utilidades de mapa base
# ---------------------------------------------------------------------------


def _agregar_mapa_base(ax) -> None:
    ax.add_feature(
        cfeature.LAND.with_scale("10m"),
        facecolor=config.COLOR_TIERRA,
        zorder=0,
    )
    ax.add_feature(
        cfeature.OCEAN.with_scale("10m"),
        facecolor=config.COLOR_AGUA,
        zorder=0,
    )
    ax.add_feature(
        cfeature.LAKES.with_scale("10m"),
        facecolor=config.COLOR_AGUA,
        edgecolor=config.COLOR_AGUA,
        zorder=0,
    )
    ax.add_feature(
        cfeature.RIVERS.with_scale("10m"),
        edgecolor=config.COLOR_AGUA,
        linewidth=0.8,
        zorder=1,
    )
    ax.add_feature(
        cfeature.BORDERS.with_scale("10m"),
        edgecolor=config.COLOR_BORDES_PAIS,
        linewidth=config.LINEWIDTH_PAISES,
        zorder=3,
    )
    ax.add_feature(
        cfeature.STATES.with_scale("10m"),
        edgecolor=config.COLOR_BORDES_PROV,
        linewidth=config.LINEWIDTH_PROVINCIAS,
        facecolor="none",
        zorder=2,
    )
    ax.coastlines(resolution="10m", linewidth=config.LINEWIDTH_COSTAS,
                  color=config.COLOR_BORDES_PAIS, zorder=3)


def _agregar_gridlines(ax) -> None:
    gl = ax.gridlines(
        crs=ccrs.PlateCarree(),
        draw_labels=True,
        linewidth=0.5,
        color="gray",
        alpha=0.4,
        linestyle="--",
        x_inline=False,
        y_inline=False,
    )
    gl.top_labels = True
    gl.right_labels = True
    gl.bottom_labels = True
    gl.left_labels = True
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {"size": config.FONTSIZE_GRIDLINES, "color": "black",
                        "family": config.FUENTE_REGULAR}
    gl.ylabel_style = {"size": config.FONTSIZE_GRIDLINES, "color": "black",
                        "family": config.FUENTE_REGULAR}
    gl.xlocator = mticker.MaxNLocator(6)
    gl.ylocator = mticker.MaxNLocator(6)


def _agregar_recuadro_blanco(fig, ax) -> None:
    """Aplica la estetica de 'recuadro blanco' clasica de MetPy."""
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    try:
        ax.spines["geo"].set_edgecolor("black")
        ax.spines["geo"].set_linewidth(1.4)
    except Exception:
        for spine in ax.spines.values():
            spine.set_edgecolor("black")
            spine.set_linewidth(1.4)


def _agregar_flecha_norte(ax) -> None:
    ax.annotate(
        "N",
        xy=(0.965, 0.94), xycoords="axes fraction",
        xytext=(0.965, 0.88), textcoords="axes fraction",
        ha="center", va="center",
        fontsize=12, fontweight="bold", fontfamily=config.FUENTE_BOLD,
        color="black",
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.6,
                         shrinkA=0, shrinkB=2),
        zorder=20,
    )


def _distancia_redonda_km(ancho_dominio_km: float) -> int:
    objetivo = ancho_dominio_km * 0.22
    opciones = [10, 20, 25, 50, 100, 150, 200, 250, 300, 400, 500, 750, 1000]
    mejor = min(opciones, key=lambda v: abs(v - objetivo))
    return mejor


def _agregar_escala(ax, proyeccion) -> None:
    """Barra de escala aproximada en km, usando que la proyeccion Lambert
    del WRF-SMN esta definida en metros (ver config.WRF_PROJ_EARTH_RADIUS).
    """
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    ancho_m = x1 - x0
    ancho_km = ancho_m / 1000.0
    distancia_km = _distancia_redonda_km(ancho_km)
    distancia_m = distancia_km * 1000.0

    margen_x = x0 + 0.06 * (x1 - x0)
    margen_y = y0 + 0.055 * (y1 - y0)

    ax.plot(
        [margen_x, margen_x + distancia_m], [margen_y, margen_y],
        color="black", linewidth=2.0, solid_capstyle="butt", zorder=20,
    )
    for frac in (0.0, 0.5, 1.0):
        ax.plot(
            [margen_x + frac * distancia_m] * 2,
            [margen_y - 0.006 * (y1 - y0), margen_y + 0.006 * (y1 - y0)],
            color="black", linewidth=1.4, zorder=20,
        )
    ax.text(
        margen_x, margen_y + 0.014 * (y1 - y0), "0",
        ha="center", va="bottom", fontsize=7.5, fontfamily=config.FUENTE_REGULAR,
        zorder=20,
    )
    ax.text(
        margen_x + distancia_m, margen_y + 0.014 * (y1 - y0),
        f"{distancia_km} km",
        ha="center", va="bottom", fontsize=7.5, fontfamily=config.FUENTE_REGULAR,
        zorder=20,
    )


# ---------------------------------------------------------------------------
# Ciudades
# ---------------------------------------------------------------------------


def _dibujar_ciudades(
    fig,
    ax,
    extent: tuple[float, float, float, float],
    maximo_ciudades: int = 45,
) -> None:
    """Dibuja marcadores + etiquetas de ciudades, evitando solapamientos.

    El anti-solapamiento se hace midiendo el bounding box REAL de cada
    etiqueta de texto ya renderizada (via ``Text.get_window_extent``), en
    lugar de estimar el ancho a partir de la cantidad de caracteres. Esto
    evita que nombres largos como "San Nicolas de los Arroyos" se solapen
    con ciudades vecinas, algo que una heuristica por longitud de string
    no detecta con precision.
    """
    lon_min, lon_max, lat_min, lat_max = extent
    catalogo = cities_mod.cargar_ciudades()
    visibles = cities_mod.filtrar_por_extent(catalogo, lon_min, lon_max, lat_min, lat_max, margen_grados=0.0)
    if not visibles:
        return

    area_deg2 = abs(lon_max - lon_min) * abs(lat_max - lat_min)
    visibles = cities_mod.limitar_cantidad(visibles, maximo_ciudades, area_deg2)

    proyeccion = ax.projection
    pc = ccrs.PlateCarree()

    orden_prioridad = {"capital_nacional": 0, "capital_provincial": 1, "ciudad": 2}
    visibles_ordenadas = sorted(
        visibles, key=lambda c: orden_prioridad.get(c.categoria, 3)
    )

    # Forzar un primer render para poder medir tamanos de texto reales.
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    efecto_contorno = [withStroke(linewidth=2.6, foreground=config.COLOR_CONTORNO_TEXTO_CIUDAD)]
    padding_px = 3.0

    bboxes_aceptados: list = []

    for c in visibles_ordenadas:
        x, y = proyeccion.transform_point(c.lon, c.lat, pc)

        texto = ax.annotate(
            c.nombre,
            xy=(x, y), xycoords="data",
            xytext=(0, -9), textcoords="offset points",
            ha="center", va="top",
            fontsize=config.FONTSIZE_CIUDAD,
            fontfamily=config.FUENTE_BOLD,
            fontweight="bold",
            color=config.COLOR_TEXTO_CIUDAD,
            path_effects=efecto_contorno,
            zorder=16,
        )

        bbox = texto.get_window_extent(renderer=renderer).expanded(1.0, 1.0)
        bbox = bbox.padded(padding_px)

        solapa = any(bbox.overlaps(otro) for otro in bboxes_aceptados)
        if solapa:
            texto.remove()
            continue

        bboxes_aceptados.append(bbox)
        ax.plot(
            x, y, marker="o",
            markersize=6.5 if c.categoria != "ciudad" else 5.5,
            markerfacecolor=config.COLOR_MARCADOR_RELLENO,
            markeredgecolor=config.COLOR_MARCADOR_BORDE,
            markeredgewidth=1.0,
            zorder=15,
        )


# ---------------------------------------------------------------------------
# Titulo
# ---------------------------------------------------------------------------


def _texto_fecha_validez(campo: CampoGrillado) -> str:
    if campo.variable == "precip":
        ini = campo.fecha_validez_inicio
        fin = campo.fecha_validez_fin
        return f"{ini:%Y%m%d %H}Z - {fin:%Y%m%d %H}Z"
    fecha = campo.fecha_validez_inicio.date()
    return f"{fecha:%Y%m%d}"


def _agregar_titulo(fig, ax, campo: CampoGrillado, titulo_variable: str) -> None:
    """Dibuja titulo + subtitulo ancaldos al eje del mapa (``ax``), no a la
    figura completa.

    IMPORTANTE: no usar ``fig.text()`` con coordenadas fijas de figura
    (0-1) para el titulo. Cartopy reposiciona el GeoAxes dentro de la
    figura para mantener el aspecto real de los datos (aspect='equal'); en
    recortes muy alargados (p. ej. zoom a una provincia angosta y alta
    como Buenos Aires) el eje termina ocupando una fraccion de figura
    distinta a la esperada, y un titulo con posicion fija se solapa con
    las etiquetas de la grilla de coordenadas superior. Al usar
    ``ax.transAxes`` con ``clip_on=False``, el titulo queda siempre
    correctamente ubicado por encima del mapa, sin importar donde termine
    posicionado el eje.
    """
    fecha_txt = _texto_fecha_validez(campo)
    titulo = f"{titulo_variable} correspondiente a ({fecha_txt})"
    subtitulo = (
        f"Modelo WRF 4km - SMN | Ciclo {campo.ciclo}Z del "
        f"{campo.fecha_init:%d/%m/%Y}"
    )

    ax.text(
        0.5, 1.085, titulo,
        transform=ax.transAxes,
        ha="center", va="bottom",
        fontsize=config.FONTSIZE_TITULO,
        fontfamily=config.FUENTE_BOLD,
        fontweight="bold",
        color="black",
        clip_on=False,
    )
    ax.text(
        0.5, 1.045, subtitulo,
        transform=ax.transAxes,
        ha="center", va="bottom",
        fontsize=config.FONTSIZE_SUBTITULO,
        fontfamily=config.FUENTE_REGULAR,
        color="#333333",
        clip_on=False,
    )


# ---------------------------------------------------------------------------
# Funcion principal
# ---------------------------------------------------------------------------


def graficar_campo(
    campo: CampoGrillado,
    ruta_salida: Path,
    extent: Optional[tuple[float, float, float, float]] = None,
    region_zoom: Optional[zoom_mod.RegionZoom] = None,
    max_ciudades: int = 45,
) -> Path:
    """Genera y guarda el mapa final en PNG.

    Parameters
    ----------
    campo : CampoGrillado
        Resultado de reader.leer_tmin_tmax / leer_precipitacion_acumulada.
    ruta_salida : Path
        Ruta del PNG a generar.
    extent : (lon_min, lon_max, lat_min, lat_max), opcional
        Recorte manual del mapa. Si no se especifica y hay region_zoom, se
        usa el extent de la region. Si ninguno se especifica, se usa el
        dominio completo del modelo.
    region_zoom : RegionZoom, opcional
        Resultado de zoom.cargar_region_zoom(); si se pasa, se dibuja el
        contorno de la region sobre el mapa.
    max_ciudades : int
        Cantidad maxima de ciudades a rotular.
    """
    info = config.get_variable_info(campo.variable)

    if extent is None:
        if region_zoom is not None:
            extent = (region_zoom.lon_min, region_zoom.lon_max,
                      region_zoom.lat_min, region_zoom.lat_max)
        else:
            extent = (config.DOMINIO_LON_MIN, config.DOMINIO_LON_MAX,
                      config.DOMINIO_LAT_MIN, config.DOMINIO_LAT_MAX)

    lon_min, lon_max, lat_min, lat_max = extent

    proyeccion = proyeccion_wrf()

    fig = plt.figure(figsize=config.FIGSIZE, dpi=config.DPI)
    ax = fig.add_axes([0.07, 0.05, 0.78, 0.85], projection=proyeccion)

    x0, x1, y0, y1 = _extent_proyectado_desde_grilla(
        (lon_min, lon_max, lat_min, lat_max), campo
    )
    ax.set_extent([x0, x1, y0, y1], crs=proyeccion)

    _agregar_mapa_base(ax)

    # --- Downsampling adaptativo segun el nivel de zoom -------------------
    area_total = abs(config.DOMINIO_LON_MAX - config.DOMINIO_LON_MIN) * \
        abs(config.DOMINIO_LAT_MAX - config.DOMINIO_LAT_MIN)
    area_extent = abs(lon_max - lon_min) * abs(lat_max - lat_min)
    fraccion = min(1.0, area_extent / area_total) if area_total > 0 else 1.0
    stride = 1 if fraccion < 0.35 else (2 if fraccion < 0.7 else 3)

    lat_s = campo.lat[::stride, ::stride]
    lon_s = campo.lon[::stride, ::stride]
    data_s = campo.data[::stride, ::stride]
    data_s = _enmascarar_oceano(lon_s, lat_s, data_s)

    if campo.variable == "precip":
        # Los pixeles sin lluvia (por debajo del primer nivel de la
        # escala) se dejan como NaN para que se vea el color de tierra de
        # fondo (#f2eeed) en lugar de pintarlos blancos con la paleta de
        # precipitacion.
        primer_nivel = float(info.niveles[0])
        data_s = np.where(data_s <= primer_nivel, np.nan, data_s)

    norm, cmap = _norm_cmap_para(campo.variable, info.niveles)

    malla = ax.pcolormesh(
        lon_s, lat_s, data_s,
        transform=ccrs.PlateCarree(),
        cmap=cmap, norm=norm,
        shading="auto",
        zorder=4,
    )

    if region_zoom is not None:
        ax.add_geometries(
            region_zoom.gdf.geometry,
            crs=ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="black",
            linewidth=1.6,
            zorder=6,
        )

    _agregar_gridlines(ax)
    _agregar_recuadro_blanco(fig, ax)
    _agregar_flecha_norte(ax)
    _agregar_escala(ax, proyeccion)
    _dibujar_ciudades(fig, ax, extent, maximo_ciudades=max_ciudades)
    _agregar_titulo(fig, ax, campo, info.titulo)

    cax = fig.add_axes([0.87, 0.08, 0.03, 0.78])
    cbar = fig.colorbar(malla, cax=cax, extend="both", ticks=info.niveles)
    cbar.set_label(
        info.etiqueta_colorbar,
        fontsize=config.FONTSIZE_COLORBAR_LABEL,
        fontfamily=config.FUENTE_BOLD,
        fontweight="bold",
    )
    cbar.ax.tick_params(labelsize=config.FONTSIZE_COLORBAR_TICKS)
    for tick_label in cbar.ax.get_yticklabels():
        tick_label.set_fontfamily(config.FUENTE_REGULAR)
    cbar.outline.set_edgecolor("black")
    cbar.outline.set_linewidth(1.0)

    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta_salida, dpi=config.DPI, facecolor="white",
                bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return ruta_salida
