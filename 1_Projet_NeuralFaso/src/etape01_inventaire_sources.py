"""Étape 1 : inventaire des données brutes (collecte).

Liste chaque fichier brut de data/01_collecte avec son producteur, sa publication, son année,
l'endroit où le trouver, sa taille et les étapes qui l'utilisent. Les fichiers bruts ne sont pas modifiés.

Sortie : data/01_collecte/…_01-collecte_D3_engineer_inventaire-sources_v1.csv
Lancement :  python src/etape01_inventaire_sources.py
"""
import hashlib

import pandas as pd

import config

# motif du nom de fichier -> (producteur, publication, année, où le trouver, étapes qui l'utilisent)
SOURCES = [
    ("DONNEES_STATIST*.xlsx", "DGESS, ministère de l'Éducation nationale",
     "Données statistiques du préscolaire et du primaire 2015-2016 à 2024-2025", "2025",
     "Espace challenge de la plateforme equation (données principales)", "2, 3, 4"),
    ("annuaires/CNS530*.csv", "DGESS/MEBAPLN", "Annuaire statistique de l'enseignement primaire 2024-2025 (CNS530)", "2025",
     "Data Pack du challenge (Drive), version CSV", "2b, 3c, 4"),
    ("annuaires/CNS521*.csv", "DGESS/MENA", "Annuaire statistique de l'enseignement primaire 2017-2018 (CNS521)", "2018",
     "Data Pack du challenge (Drive), version CSV", "2b, 4"),
    ("projections/NADA276*.csv", "INSD", "RGPH 2019, volume 4 : projections démographiques 2020-2035 (NADA276)", "2022",
     "Data Pack du challenge (Drive), version CSV", "2c, 3c, 4"),
    ("esu/*ESU*.csv", "DGESS", "Rapport statistique mensuel de l'éducation en situation d'urgence, février 2026", "2026",
     "Data Pack du challenge (Drive), version CSV", "2d, 4"),
    ("cartographie/bfa_admin2.geojson", "IGB et OCHA", "Limites administratives COD-AB du Burkina Faso, niveau province", "2025",
     "https://data.humdata.org/dataset/cod-ab-bfa", "3b, 3c"),
    ("cartographie/hotosm_bfa_education_facilities*.zip", "Contributeurs OpenStreetMap, export HOT",
     "Établissements d'enseignement du Burkina Faso (licence ODbL)", "2026",
     "https://data.humdata.org/dataset/hotosm_bfa_education_facilities", "3c"),
    ("cartographie/bfa_ppp_2020_1km*.zip", "WorldPop, Université de Southampton",
     "Population 2020 sur une grille de 1 km, ajustée ONU", "2020",
     "https://hub.worldpop.org/geodata/listing?id=75", "3c"),
]


def principal():
    racine = config.DOSSIERS["collecte"]
    lignes = []
    for motif, prod, pub, an, ou, etapes in SOURCES:
        fichiers = sorted(racine.glob(motif))
        if not fichiers:
            lignes.append({"fichier": motif, "present": "non", "producteur": prod, "publication": pub, "annee": an,
                           "ou_le_trouver": ou, "etapes_utilisatrices": etapes})
            continue
        for f in fichiers:
            lignes.append({"fichier": f.relative_to(racine).as_posix(), "present": "oui", "producteur": prod, "publication": pub,
                           "annee": an, "ou_le_trouver": ou, "etapes_utilisatrices": etapes,
                           "taille_ko": f.stat().st_size // 1024, "sha1": hashlib.sha1(f.read_bytes()).hexdigest()})
    d = pd.DataFrame(lignes)
    out = config.nom_fichier("collecte", "engineer", "inventaire-sources")
    d.to_csv(out, index=False, encoding="utf-8")
    manquants = d[d.present == "non"]
    print(f"Inventaire écrit : {out.name} ({len(d)} sources, {len(manquants)} manquante(s)).")
    if len(manquants):
        print("Manquant :", ", ".join(manquants.fichier))


if __name__ == "__main__":
    principal()
