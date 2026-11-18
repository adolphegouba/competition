# NeuralFaso_03-transformation_D3_architect_fond-de-carte_v1.py
# Nom d'origine dans le projet : src/etape03b_fond_de_carte.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 3b : fond de carte des provinces, allégé, avec la correspondance ancien / nouveau découpage.

Source : COD-AB (IGB / OCHA), bfa_admin2.geojson du Data Pack, placé dans data/01_collecte/cartographie/.
Le fichier compte 47 provinces (découpage de 2025) ; chaque province porte le code de son ancienne
province (adm2_pcode_old). Les données éducatives suivant les 45 anciennes provinces, chaque polygone
reçoit le nom de son ancienne province : le Soum et la Tapoa, scindés en deux en 2025, sont donc
représentés par deux polygones chacun, portant la même valeur.

Sorties :
  - un GeoJSON simplifié (environ 1 km de tolérance) pour l'application ;
  - la table de correspondance anciennes / nouvelles provinces et régions.

Lancement :  python src/etape03b_fond_de_carte.py
"""
import json

import numpy as np
import pandas as pd

import config
from etape02b_extraction_annuaires import REGION_DE, VARIANTES_PROV
from referentiels import cle

TOLERANCE = 0.008   # degrés, environ 900 m


def douglas_peucker(points, tol):
    pts = np.asarray(points, dtype=float)
    if len(pts) < 4:
        return pts.tolist()
    garde = np.zeros(len(pts), dtype=bool)
    garde[0] = garde[-1] = True
    pile = [(0, len(pts) - 1)]
    while pile:
        a, b = pile.pop()
        if b <= a + 1:
            continue
        seg = pts[b] - pts[a]
        n = np.hypot(*seg)
        d = pts[a + 1:b] - pts[a]
        dist = np.abs(seg[0] * d[:, 1] - seg[1] * d[:, 0]) / n if n else np.hypot(d[:, 0], d[:, 1])
        i = int(np.argmax(dist))
        if dist[i] > tol:
            k = a + 1 + i
            garde[k] = True
            pile += [(a, k), (k, b)]
    res = np.round(pts[garde], 4).tolist()
    if len(res) < 4:   # un anneau doit garder au moins 4 points
        res = np.round(pts[np.linspace(0, len(pts) - 1, 4).astype(int)], 4).tolist()
    return res


def simplifier(geom):
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [douglas_peucker(r, TOLERANCE) for r in geom["coordinates"]]}
    return {"type": "MultiPolygon",
            "coordinates": [[douglas_peucker(r, TOLERANCE) for r in poly] for poly in geom["coordinates"]]}


def principal():
    src = config.DOSSIERS["collecte"] / "cartographie" / "bfa_admin2.geojson"
    g = json.load(open(src, encoding="utf-8"))
    sorties, table, inconnues = [], [], []
    for f in g["features"]:
        p = f["properties"]
        ancien = cle(p.get("adm2_name_old") or "")
        ancien = VARIANTES_PROV.get(ancien, ancien)
        ancien = {"OUBRITENGA": "OUBRITENGA", "KOURITENGA": "KOURITTENGA"}.get(ancien, ancien)
        if ancien not in REGION_DE:
            inconnues.append(p.get("adm2_name_old"))
        prop = {"province": ancien, "region": REGION_DE.get(ancien), "province_2025": p.get("adm2_name1"),
                "region_2025": p.get("adm1_name1"), "pcode_2025": p.get("adm2_pcode"), "pcode_ancien": p.get("adm2_pcode_old"),
                "superficie_km2": round(float(p.get("area_sqkm") or 0))}
        sorties.append({"type": "Feature", "properties": prop, "geometry": simplifier(f["geometry"])})
        table.append(prop)

    geo = config.nom_fichier("transformation", "architect", "fond-de-carte-provinces-simplifie", ext="geojson")
    geo.write_text(json.dumps({"type": "FeatureCollection", "features": sorties}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    t = pd.DataFrame(table)
    t.to_csv(config.nom_fichier("transformation", "architect", "correspondance-provinces-2025"), index=False, encoding="utf-8")
    print(f"{len(sorties)} polygones ; {t.province.nunique()} anciennes provinces reconnues (attendu 45) ; "
          f"non reconnues : {inconnues or 'aucune'} ; fichier allégé : {geo.stat().st_size // 1024} Ko")


if __name__ == "__main__":
    principal()
