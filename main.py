#!/usr/bin/env python3
"""
main.py
=======

Punto de entrada del proyecto DatosDiarios / wrf_smn.

Genera mapas de Temperatura Minima, Temperatura Maxima o Precipitacion
Acumulada usando el modelo WRF 4km del SMN (bucket publico de AWS), con
estetica clasica de MetPy y posibilidad de hacer zoom a municipios o
regiones a partir de archivos .geojson.

Ejecutar `python main.py --help` para ver todas las opciones.
"""

from wrf_smn.cli import main

if __name__ == "__main__":
    main()
