# DatosDiarios

Generador de mapas de **Temperatura Minima**, **Temperatura Maxima** y
**Precipitacion Acumulada** a partir del modelo **WRF 4km del SMN**
(Servicio Meteorologico Nacional de Argentina), publicado de forma
gratuita en el bucket de AWS Open Data:

- Bucket S3: https://smn-ar-wrf.s3.amazonaws.com/index.html#DATA/WRF/DET/
- Documentacion del dataset: https://odp-aws-smn.github.io/documentation_wrf_det/
- Registro AWS Open Data: https://registry.opendata.aws/smn-ar-wrf-dataset/

Los mapas se generan con una estetica clasica de MetPy: recuadro blanco,
colorbar a la derecha, titulo superior, ciudades rotuladas con circulo +
contorno blanco, grilla de coordenadas, flecha de norte y escala grafica.
Colores de fondo personalizables (continente `#f2eeed`, agua `#dce6f0`) y
tipografia Tahoma / Tahoma Bold (con fallback automatico si no estan
instaladas en el sistema).

Ademas permite hacer **zoom a un municipio, departamento o region**
cargando un archivo `.geojson` propio (por ejemplo, capas de INDEC, IGN, o
cualquier geojson de limites administrativos), recortando el mapa a su
extent y dibujando su contorno.

## Instalacion

### Opcion recomendada: Miniconda3

```bash
conda env create -f environment.yml
conda activate wrf-smn
```

En VSCode: `Ctrl+Shift+P` -> **Python: Select Interpreter** -> elegir el
interprete del entorno `wrf-smn`.

### Alternativa: pip

```bash
python -m venv .venv
source .venv/bin/activate   # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> Nota: en Windows, si `pip install cartopy` falla por dependencias
> nativas (GEOS/PROJ), se recomienda usar conda/mamba en su lugar.

### Fuentes Tahoma / Tahoma Bold

El script intenta usar las fuentes `Tahoma` y `Tahoma Bold`. Si ya las
tenes instaladas en tu PC (caso tipico en Windows), matplotlib las
detecta automaticamente. Si no estan disponibles, el script cae en una
fuente de reemplazo (`DejaVu Sans`) sin fallar.

Si instalaste Tahoma recientemente y VSCode/matplotlib no la detecta,
limpiá el cache de fuentes de matplotlib:

```bash
python -c "import matplotlib; import shutil; shutil.rmtree(matplotlib.get_cachedir())"
```

## Uso rapido

```bash
# Temperatura minima del dia siguiente al ciclo 00Z de una fecha dada
python main.py --variable tmin --fecha 2026-07-03 --ciclo 00 --dia 1

# Temperatura maxima
python main.py --variable tmax --fecha 2026-07-03 --ciclo 00 --dia 1

# Precipitacion acumulada en las primeras 24 horas de pronostico
python main.py --variable precip --fecha 2026-07-03 --ciclo 00 \
    --plazo-inicio 0 --plazo-fin 24
```

Los PNG se guardan en `salidas/` y los NetCDF descargados se cachean en
`cache/` (no se vuelven a descargar si ya existen; usar `--forzar-descarga`
para refrescarlos).

## Zoom a municipios / regiones (.geojson)

1. Coloca tu(s) archivo(s) `.geojson` en `data/geojson/`.
2. Listalos con:

   ```bash
   python main.py --listar-geojson
   ```

3. Generá el mapa con zoom:

   ```bash
   python main.py --variable tmin --fecha 2026-07-03 --ciclo 00 --dia 1 \
       --geojson data/geojson/mi_departamento.geojson
   ```

   Si el geojson contiene varias regiones (por ejemplo, todos los
   departamentos de una provincia) y queres una sola, filtra por nombre:

   ```bash
   python main.py --variable tmin --fecha 2026-07-03 --ciclo 00 --dia 1 \
       --geojson data/geojson/departamentos_cordoba.geojson \
       --geojson-filtro "Rio Cuarto"
   ```

El mapa recorta automaticamente al area de la region (con un margen) y
dibuja su contorno en negro sobre el mapa, junto con las ciudades
cercanas de `data/ciudades_ar.csv`.

Fuentes utiles para descargar geojson de municipios/departamentos de
Argentina: IGN (https://www.ign.gob.ar/), INDEC, o portales de datos
abiertos provinciales/municipales.

## Todas las opciones

```bash
python main.py --help
```

| Opcion | Descripcion |
|---|---|
| `--variable` | `tmin`, `tmax` o `precip` (requerido) |
| `--fecha` | Fecha de inicializacion del ciclo, `YYYY-MM-DD` (default: hoy) |
| `--ciclo` | `00`, `06`, `12` o `18` UTC (default: `00`) |
| `--dia` | Solo tmin/tmax: plazo en dias (0-3, default: 1) |
| `--plazo-inicio` / `--plazo-fin` | Solo precip: ventana horaria del acumulado |
| `--geojson` | Ruta a un `.geojson` para hacer zoom |
| `--geojson-filtro` | Filtro de nombre si el geojson tiene varias regiones |
| `--extent` | Recorte manual: `LON_MIN LON_MAX LAT_MIN LAT_MAX` |
| `--max-ciudades` | Cantidad maxima de ciudades a rotular (default: 45) |
| `--salida` | Nombre/ruta del PNG de salida |
| `--forzar-descarga` | Ignora la cache y vuelve a descargar |
| `--listar-geojson` | Lista los `.geojson` disponibles y termina |

## Estructura del proyecto

```
DatosDiarios/
├── main.py                  # Punto de entrada
├── requirements.txt
├── environment.yml
├── wrf_smn/
│   ├── config.py            # Colores, fuentes, metadata de variables, proyeccion
│   ├── downloader.py        # Descarga + cache de NetCDF del bucket del SMN
│   ├── reader.py            # Lectura de Tmin/Tmax/PP con netCDF4
│   ├── cities.py             # Catalogo de ciudades + anti-solapamiento
│   ├── zoom.py               # Carga de geojson para zoom a regiones
│   ├── plotting.py           # Generacion del mapa (estetica MetPy)
│   └── cli.py                 # Interfaz de linea de comandos
├── data/
│   ├── ciudades_ar.csv       # Catalogo de ciudades argentinas
│   └── geojson/               # Coloca aca tus geojson de municipios/regiones
├── cache/                     # NetCDF descargados (gitignored)
└── salidas/                   # PNG generados (gitignored)
```

## Notas sobre los datos del SMN

- Resolucion espacial: 4 km, proyeccion Lambert Conformal Conic
  (`central_lon=-65`, `central_lat=-35`, `standard_parallel=-35`).
- Ciclos de pronostico: 00, 06, 12 y 18 UTC, con lead time maximo de 72 h.
- `Tmin`/`Tmax` (archivos `24H`) son temperaturas diarias: `Tmin` del dia X
  corresponde a la minima entre las 00 y 12 UTC de ese dia; `Tmax` del dia
  X corresponde a la maxima entre las 12 UTC del dia X y las 00 UTC del
  dia X+1.
- `PP` (archivos `01H`) es la precipitacion caida en esa hora especifica
  (no acumulada corrida); por eso, para un acumulado en una ventana hay
  que sumar los archivos horarios de esa ventana (lo hace
  `reader.leer_precipitacion_acumulada` automaticamente).

Ver la documentacion oficial para mas detalle:
https://odp-aws-smn.github.io/documentation_wrf_det/Formato_de_datos/
