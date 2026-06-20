#!/usr/bin/env python3
"""
Script para descargar los últimos partidos de selecciones nacionales
y actualizar results.csv con los datos más recientes.
"""

import urllib.request
import shutil
import sys
import os
import csv
from datetime import datetime

# Forzar salida UTF-8 en Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# BASE_DIR es la carpeta del script (data/). RESULTS_CSV apunta a data/results.csv
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_CSV = os.path.join(BASE_DIR, "results.csv")

SOURCES = [
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv",
    "https://raw.githubusercontent.com/martj42/international-football-results/master/results.csv",
    "https://raw.githubusercontent.com/datasets/football-results/main/data/results.csv",
]

def download_results():
    """Intenta descargar el results.csv más reciente desde fuentes públicas."""
    for url in SOURCES:
        try:
            print(f"  Intentando: {url[:70]}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
            lines = content.strip().split("\n")
            if len(lines) < 100:
                print(f"  Datos insuficientes ({len(lines)} líneas), probando siguiente fuente...")
                continue
            print(f"  OK - {len(lines)-1:,} partidos encontrados")
            return content
        except Exception as e:
            print(f"  Fallo: {e}")
            continue
    return None

def save_with_backup(content):
    """Guarda el CSV creando un backup del anterior."""
    if os.path.exists(RESULTS_CSV):
        backup = RESULTS_CSV + ".bak"
        shutil.copy2(RESULTS_CSV, backup)
        print(f"  Backup creado: data/results.csv.bak")

    with open(RESULTS_CSV, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print(f"  results.csv guardado correctamente.")

def show_recent_matches(n=10):
    """Muestra los N partidos más recientes del CSV."""
    with open(RESULTS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    rows.sort(key=lambda x: x["date"], reverse=True)
    total = len(rows)
    latest_date = rows[0]["date"] if rows else "N/A"

    print(f"\n  Total de partidos en la base de datos: {total:,}")
    print(f"  Partido más reciente: {latest_date}")
    print()
    print(f"  {'Fecha':<12} {'Local':<22} {'Marcador':>8}  {'Visitante':<22} Torneo")
    print("  " + "-" * 85)

    for r in rows[:n]:
        home = r["home_team"][:21]
        away = r["away_team"][:21]
        score = f"{r['home_score']}-{r['away_score']}"
        tournament = r["tournament"][:25]
        print(f"  {r['date']:<12} {home:<22} {score:>8}  {away:<22} {tournament}")

    print("  " + "-" * 85)

def main():
    print("=" * 60)
    print("  Actualizando Partidos de Selecciones Nacionales")
    print("=" * 60)

    # --- Paso 1: Descargar ---
    print("\n[1/2] Descargando datos actualizados...")
    content = download_results()

    if content is None:
        print("\n[ERROR] No se pudo descargar desde ninguna fuente.")
        print("   Revisa tu conexion a internet e intentalo mas tarde.")
        return 1

    save_with_backup(content)

    # --- Paso 2: Mostrar partidos recientes ---
    print("\n[2/2] Partidos más recientes descargados:")
    show_recent_matches(10)

    print("\nDescarga completada. Los ratings Elo seran recalculados a continuacion.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
