#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obtiene estadisticas REALES de tiro del Mundial desde FBref (2018, 2022, 2026)
usando soccerdata, y calcula un proxy de xG basado en rendimiento real
en Copa del Mundo (goles/90min, precision de remate).

NOTA: FBref no publica xG oficial para el Mundial, pero si los goles reales,
tiros y precision de remate por equipo, que son datos mas fiables que las
estimaciones históricas del modelo anterior.

Uso:
    python data/fetch_fbref_xg.py

Requiere:
    pip install soccerdata pandas
"""

import json
import sys
import io
import os
from pathlib import Path
from datetime import datetime

# Forzar salida UTF-8 en Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_DIR = Path(__file__).parent
XG_OUTPUT = BASE_DIR / "xg_by_team.json"

# Mapeo nombre FBref -> slug proyecto
FBREF_NAME_TO_SLUG = {
    "United States": "usa",
    "Mexico": "mexico",
    "Canada": "canada",
    "Panama": "panama",
    "Honduras": "honduras",
    "Costa Rica": "costa-rica",
    "Jamaica": "jamaica",
    "Haiti": "haiti",
    "Trinidad and Tobago": "trinidad-and-tobago",
    "Guatemala": "guatemala",
    "El Salvador": "el-salvador",
    "Curacao": "curacao",
    "Curazao": "curacao",
    "Argentina": "argentina",
    "Brazil": "brazil",
    "Colombia": "colombia",
    "Ecuador": "ecuador",
    "Paraguay": "paraguay",
    "Uruguay": "uruguay",
    "Chile": "chile",
    "Peru": "peru",
    "Bolivia": "bolivia",
    "Venezuela": "venezuela",
    "Germany": "germany",
    "Austria": "austria",
    "Belgium": "belgium",
    "Bosnia and Herzegovina": "bosnia-and-herzegovina",
    "Croatia": "croatia",
    "Scotland": "scotland",
    "Spain": "spain",
    "France": "france",
    "England": "england",
    "Norway": "norway",
    "Netherlands": "netherlands",
    "Poland": "poland",
    "Portugal": "portugal",
    "Czech Republic": "czech-republic",
    "Czechia": "czech-republic",
    "Sweden": "sweden",
    "Switzerland": "switzerland",
    "Turkey": "turkey",
    "Serbia": "serbia",
    "Denmark": "denmark",
    "Iceland": "iceland",
    "Wales": "wales",
    "Russia": "russia",
    "Ukraine": "ukraine",
    "Slovakia": "slovakia",
    "Slovenia": "slovenia",
    "Hungary": "hungary",
    "Romania": "romania",
    "Greece": "greece",
    "Albania": "albania",
    "North Macedonia": "north-macedonia",
    "Finland": "finland",
    "Georgia": "georgia",
    "Kosovo": "kosovo",
    "Armenia": "armenia",
    "Azerbaijan": "azerbaijan",
    "Saudi Arabia": "saudi-arabia",
    "Australia": "australia",
    "Qatar": "qatar",
    "South Korea": "south-korea",
    "Korea Republic": "south-korea",
    "United Arab Emirates": "uae",
    "Iraq": "iraq",
    "IR Iran": "iran",
    "Iran": "iran",
    "Japan": "japan",
    "Jordan": "jordan",
    "China PR": "china",
    "Uzbekistan": "uzbekistan",
    "Kazakhstan": "kazakhstan",
    "Algeria": "algeria",
    "Cape Verde": "cape-verde",
    "Ivory Coast": "ivory-coast",
    "Cote d'Ivoire": "ivory-coast",
    "Egypt": "egypt",
    "Ghana": "ghana",
    "Morocco": "morocco",
    "DR Congo": "dr-congo",
    "Democratic Republic of the Congo": "dr-congo",
    "South Africa": "south-africa",
    "Tunisia": "tunisia",
    "Senegal": "senegal",
    "Cameroon": "cameroon",
    "Nigeria": "nigeria",
    "Mali": "mali",
    "Burkina Faso": "burkina-faso",
    "New Zealand": "new-zealand",
}


def to_slug(name: str) -> str:
    clean = name.replace("\u00e7", "c").replace("\u00f4", "o").replace("\u2019", "'")
    if clean in FBREF_NAME_TO_SLUG:
        return FBREF_NAME_TO_SLUG[clean]
    if name in FBREF_NAME_TO_SLUG:
        return FBREF_NAME_TO_SLUG[name]
    return name.lower().replace(" ", "-").replace("'", "").replace(".", "")


def get_val(row, key_tuple, default=None):
    """Obtiene valor de fila con clave MultiIndex o simple."""
    if key_tuple in row.index:
        try:
            v = row[key_tuple]
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default
    return default


def fetch_fbref_wc_stats():
    """
    Descarga estadisticas reales del Mundial desde FBref.
    Calcula xG proxy basado en:
      - Goles reales por 90 min (rendimiento en WC)
      - Ajustado por precision de remate (G/Sh)
    
    Estructura de columnas FBref (MultiIndex):
      ('team', '')         -> nombre del equipo
      ('90s', '')          -> minutos equivalentes a 90 jugados
      ('Standard', 'Gls') -> goles marcados
      ('Standard', 'Sh')  -> tiros totales
      ('Standard', 'SoT') -> tiros a puerta
      ('Standard', 'G/Sh')-> goles por tiro
      ('Standard', 'G/SoT')-> goles por tiro a puerta
    """
    try:
        import soccerdata as sd
    except ImportError:
        print("ERROR: soccerdata no instalado.")
        return {}

    print("=" * 60)
    print("Descargando estadisticas del Mundial desde FBref")
    print("  Temporadas: 2018, 2022, 2026")
    print("  Fuente: FBref (datos reales de partidos)")
    print("=" * 60)

    # Columnas MultiIndex conocidas
    COL_TEAM  = ('team', '')
    COL_90S   = ('90s', '')
    COL_GLS   = ('Standard', 'Gls')
    COL_SH    = ('Standard', 'Sh')
    COL_SOT   = ('Standard', 'SoT')
    COL_GSH   = ('Standard', 'G/Sh')
    COL_GSOT  = ('Standard', 'G/SoT')
    COL_CRS   = ('Performance', 'Crs')

    # Peso por temporada (mas reciente = mas relevante)
    SEASON_WEIGHT = {"2026": 1.0, "2022": 0.85, "2018": 0.65}

    # Acumulador ponderado por equipo
    # slug -> {weighted_xg_sum, weighted_xga_sum, weight_sum, match_count, seasons}
    accumulator = {}

    for season in ["2026", "2022", "2018"]:
        sw = SEASON_WEIGHT[season]
        print(f"\n[{season}] Descargando (peso={sw})...")
        try:
            fbref = sd.FBref(leagues=["INT-World Cup"], seasons=[season])
            df_sh = fbref.read_team_season_stats(stat_type="shooting")
            df_misc = fbref.read_team_season_stats(stat_type="misc")

            if df_sh is None or df_sh.empty:
                print(f"  [{season}] Sin datos de tiro.")
                continue

            df = df_sh.copy()
            if df_misc is not None and not df_misc.empty:
                df[COL_CRS] = df_misc[COL_CRS]

            df = df.reset_index()
            rows_ok = 0

            for _, row in df.iterrows():
                try:
                    team_name = str(row.get(COL_TEAM, "")).strip()
                    if not team_name or team_name == "nan":
                        continue

                    team_slug = to_slug(team_name)

                    # Minutos jugados (en unidades de 90 min)
                    nineties = get_val(row, COL_90S, default=1.0)
                    if not nineties or nineties <= 0:
                        continue

                    # Estadisticas de tiro y centros
                    gls    = get_val(row, COL_GLS, default=0.0)
                    sh     = get_val(row, COL_SH,  default=0.0)
                    sot    = get_val(row, COL_SOT, default=0.0)
                    g_sh   = get_val(row, COL_GSH, default=0.0)
                    g_sot  = get_val(row, COL_GSOT, default=0.0)
                    crs    = get_val(row, COL_CRS, default=0.0)

                    # === Calcular proxy de xG por 90 min ===
                    # Base: goles marcados por 90 min reales en el Mundial
                    gls_per_90 = gls / nineties

                    # Ajuste por eficiencia de remate:
                    # Si G/SoT > 0.25 (muy eficiente), el equipo superó su xG real
                    # Si G/SoT < 0.20 (ineficiente), probablemente merecio mas
                    # Usamos tiros/90 * factor de conversion estimado como corrector
                    avg_conv_rate = 0.096  # conversion media global por tiro
                    if sh > 0:
                        shot_based_xg = (sh / nineties) * avg_conv_rate
                    else:
                        shot_based_xg = gls_per_90

                    # Mezcla 60% goles reales + 40% basado en tiros
                    xg_proxy = 0.60 * gls_per_90 + 0.40 * shot_based_xg

                    # xG en contra (estimado por goles concedidos)
                    xga_proxy = None

                    # Acumular con peso de temporada
                    if team_slug not in accumulator:
                        accumulator[team_slug] = {
                            "xg_sum": 0.0,
                            "sh_sum": 0.0,
                            "crs_sum": 0.0,
                            "weight_sum": 0.0,
                            "match_count": 0,
                            "seasons": []
                        }

                    accumulator[team_slug]["xg_sum"] += xg_proxy * sw
                    accumulator[team_slug]["sh_sum"] += (sh / nineties) * sw
                    accumulator[team_slug]["crs_sum"] += (crs / nineties) * sw
                    accumulator[team_slug]["weight_sum"] += sw
                    accumulator[team_slug]["match_count"] += max(1, int(round(nineties)))
                    if season not in accumulator[team_slug]["seasons"]:
                        accumulator[team_slug]["seasons"].append(season)

                    rows_ok += 1

                except Exception as exc:
                    continue

            print(f"  [{season}] OK -> {rows_ok} equipos")

        except Exception as e:
            print(f"  [{season}] Error: {e}")
            continue

    if not accumulator:
        print("\nERROR: No se obtuvieron datos de FBref.")
        return {}

    # Calcular xG y estadísticas de córner final ponderado
    result = {}
    for team_slug, acc in accumulator.items():
        if acc["weight_sum"] > 0:
            xg_final = acc["xg_sum"] / acc["weight_sum"]
            sh_final = acc["sh_sum"] / acc["weight_sum"]
            crs_final = acc["crs_sum"] / acc["weight_sum"]
            result[team_slug] = {
                "xg_overall": round(xg_final, 3),
                "xg_home":    round(xg_final * 1.08, 3),
                "xg_away":    round(xg_final * 0.92, 3),
                "xga_overall": None,
                "shots_per_90": round(sh_final, 3),
                "crosses_per_90": round(crs_final, 3),
                "matches_played": acc["match_count"],
                "seasons": acc["seasons"],
                "source": "fbref_world_cup"
            }

    print(f"\nResultados obtenidos para {len(result)} selecciones:")
    for team, d in sorted(result.items(), key=lambda x: x[1]["xg_overall"], reverse=True)[:16]:
        seasons_str = "+".join(d["seasons"])
        print(f"  {team:<25}  xG/90={d['xg_overall']:.3f}  Sh/90={d['shots_per_90']:.2f}  Crs/90={d['crosses_per_90']:.2f}  [{seasons_str}]")

    return result


def merge_with_existing(fbref_stats: dict) -> dict:
    existing = {}
    if XG_OUTPUT.exists():
        with open(XG_OUTPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
            existing = data.get("teams", {})

    print(f"\nFusionando con datos existentes ({len(existing)} equipos)...")

    merged = dict(existing)
    upgraded = 0
    added = 0

    for team_slug, new_data in fbref_stats.items():
        if team_slug in merged:
            old_source = merged[team_slug].get("source", "estimated")
            old_xg = merged[team_slug].get("xg_overall") or new_data["xg_overall"]
            old_xga = merged[team_slug].get("xga_overall")

            if old_source == "fbref_world_cup":
                # Si ya era de FBref WC, usamos directamente el nuevo cálculo limpio (que también incluye los centros)
                blended_xg = new_data["xg_overall"]
            else:
                # 70% FBref WC real + 30% estimado histórico
                blended_xg = round(0.70 * new_data["xg_overall"] + 0.30 * old_xg, 3)

            merged[team_slug] = {
                "xg_home":    round(blended_xg * 1.08, 3),
                "xg_away":    round(blended_xg * 0.92, 3),
                "xg_overall": blended_xg,
                "xga_overall": old_xga,  # conservar xGA existente
                "shots_per_90": new_data["shots_per_90"],
                "crosses_per_90": new_data["crosses_per_90"],
                "matches_played": new_data["matches_played"],
                "seasons": new_data["seasons"],
                "source": "fbref_world_cup"
            }
            upgraded += 1
        else:
            merged[team_slug] = new_data
            added += 1


    print(f"  Actualizados con datos FBref WC: {upgraded}")
    print(f"  Equipos nuevos:                  {added}")
    print(f"  Total en base de datos:          {len(merged)}")
    return merged


def main():
    print("\n" + "=" * 60)
    print("  FBref World Cup Stats Fetcher - Predictor Mundial 2026")
    print("=" * 60)

    fbref_stats = fetch_fbref_wc_stats()

    if not fbref_stats:
        print("\nNo se pudieron obtener datos de FBref.")
        print("El archivo xg_by_team.json no ha sido modificado.")
        return 1

    merged = merge_with_existing(fbref_stats)

    output = {
        "last_updated": datetime.now().isoformat(),
        "methodology": (
            "xG calculado a partir de datos reales del Mundial en FBref "
            "(goles/90min + eficiencia de remate), mezclado con historial estimado. "
            "source='fbref_world_cup' indica datos reales de Copa del Mundo."
        ),
        "fbref_teams_count": len(fbref_stats),
        "total_teams": len(merged),
        "teams": merged
    }

    with open(XG_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDatos guardados en: {XG_OUTPUT}")
    print(f"  Equipos con datos FBref WC: {len(fbref_stats)}")
    print(f"  Total en base de datos:     {len(merged)}")
    print("\nListo! El predictor usa rendimiento real del Mundial para calcular xG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
