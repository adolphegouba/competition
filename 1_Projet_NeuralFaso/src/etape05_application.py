"""Étape 5 : génération de l'application d'aide à la décision (une page HTML autonome).

La page contient ses données et ses calculs : elle s'ouvre dans n'importe quel navigateur,
sans connexion ni installation. Elle reprend exactement les règles de l'étape 4
(besoins, indice de priorité, allocation optimisée contre prorata) pour que le décideur
puisse changer les hypothèses lui-même.

Entrées : sorties des étapes 2c, 3b, 4 et 4b.   Sortie : data/05_interpretation/…_application-aide-decision_v1.html
Lancement :  python src/etape05_application.py
"""
import json
from datetime import datetime

import pandas as pd

import config
from etape04_besoins_allocation import COMPOSANTES, PARAMS, SEUILS
from etape04b_redeploiement_robustesse_decoupage import SEUIL_REFERENCE, TIRAGES

GABARIT = config.RACINE / "src" / "gabarit_application.html"


def carte_ecoles(lire):
    """Données de l'onglet « Carte des écoles » (étape 3c), en tableaux compacts."""
    ec = pd.read_csv(lire("*ecoles-osm-geolocalisees*.csv", "transformation")).fillna("")
    gr = pd.read_csv(lire("*enfants-6-11-ans-grille-5km*.csv", "transformation"))
    zo = pd.read_csv(lire("*zones-candidates-nouvelles-ecoles*.csv", "analyse"))
    ac = pd.read_csv(lire("*accessibilite-ecoles-province*.csv", "transformation"))
    return {
        "ecoles": [[r.lat, r.lon, str(r.nom)[:60], r.province, r.type, str(r.commune), str(r.statut), int(r.points_osm),
                    float(r.ecole_voisine_km), int(r.enfants_6_11_moins_3km), r.lien_osm] for r in ec.itertuples()],
        "grille": [[r.lat, r.lon, round(r.enfants_6_11), round(r.enfants_loin)] for r in gr.itertuples() if r.enfants_6_11 >= 1],
        "zones": [[int(r.rang), r.fiabilite, r.province, r.lat, r.lon, int(r.enfants_6_11_a_plus_de_5km), r.ecole_la_plus_proche_km]
                  for r in zo.itertuples()],
        "acces": {r.province: {"ecoles_osm": int(r.ecoles_osm), "couverture": r.couverture_osm, "fiabilite": r.fiabilite,
                               "enfants_loin": int(r.enfants_a_plus_de_5km), "part_loin": r.part_enfants_a_plus_de_5km}
                  for r in ac.itertuples()},
    }


def principal():
    def lire(motif, dossier):
        f = sorted(config.DOSSIERS[dossier].glob(motif))
        if not f:
            raise SystemExit(f"Introuvable : {motif} — lancez les étapes précédentes.")
        return f[-1]

    b = pd.read_csv(lire("*besoins-2030-priorites-province*.csv", "analyse"))
    rob = pd.read_csv(lire("*robustesse-indice-priorite*.csv", "analyse"))
    b = b.merge(rob[["province", "part_tirages_top10", "rang_median", "rang_p05", "rang_p95"]], on="province", how="left")
    corr = pd.read_csv(lire("*correspondance-provinces-2025*.csv", "transformation"))
    corr["part"] = (corr.superficie_km2 / corr.groupby("province").superficie_km2.transform("sum")).round(4)
    pr = pd.read_csv(lire("*projections-population-2020-2035-province*.csv", "nettoyage"))
    pr = pr[(pr.niveau == "province") & (pr.groupe_age == "6-11") & (pr.sexe == "T") & (pr.annee >= PARAMS["pop_base"])]
    pop = pr.pivot_table(index="entite", columns="annee", values="population")
    geo = json.loads(lire("*fond-de-carte-provinces-simplifie*.geojson", "transformation").read_text(encoding="utf-8"))

    champs = ["province", "region", "ecoles", "salles", "groupes_pedagogiques", "groupes_par_salle_2024", "maitres", "eleves_2024", "part_public", "salles_paille_banco",
              "salles_mauvais_etat", "salles_durables", "part_eleves_plus_3km", "part_eleves_plus_5km", "edi_primaire_T",
              "structures_reouvertes_primaire", "structures_delocalisees_primaire", "ips_tbs_region", "tbs_2024",
              "rem_2024", "eleves_par_salle_durable", "part_salles_precaires", "desavantage_filles", "part_eleves_deplaces",
              "ecoles_ref", "eleves_ref", "maitres_ref", "variation_ecoles_depuis_ref", "variation_eleves_depuis_ref",
              "variation_maitres_depuis_ref", "tbs_ref", "part_tirages_top10", "rang_median", "rang_p05", "rang_p95"]
    provinces = []
    for _, r in b.iterrows():
        d = {c: (None if pd.isna(r[c]) else (r[c].item() if hasattr(r[c], "item") else r[c])) for c in champs}
        d["pop_6_11"] = {int(a): int(v) for a, v in pop.loc[r.province].items()}
        provinces.append(d)

    donnees = {
        "genere_le": f"{datetime.now():%d/%m/%Y}",
        "annee_base": PARAMS["annee_base"], "annee_reference": PARAMS["annee_reference"], "pop_base": PARAMS["pop_base"],
        "params": PARAMS, "seuils": SEUILS, "composantes": COMPOSANTES,
        "provinces": provinces, "geo": geo,
        "decoupage": corr[["province", "province_2025", "region_2025", "part"]].to_dict(orient="records"),
        "robustesse": {"tirages": TIRAGES}, "seuil_redeploiement": SEUIL_REFERENCE,
    }
    donnees.update(carte_ecoles(lire))
    js = json.dumps(donnees, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = GABARIT.read_text(encoding="utf-8").replace("/*__DONNEES__*/null", js)
    vendor = config.RACINE / "src" / "vendor"
    html = (html.replace("/*__LEAFLET_CSS__*/", (vendor / "leaflet.css").read_text(encoding="utf-8"))
                .replace("/*__LEAFLET_JS__*/", (vendor / "leaflet.js").read_text(encoding="utf-8").replace("</script", "<\\/script")))
    out = config.nom_fichier("interpretation", "analyst", "application-aide-decision", ext="html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Application écrite : {out.relative_to(config.RACINE)} ({out.stat().st_size // 1024} Ko). "
          "Double-cliquez dessus pour l'ouvrir dans le navigateur.")


if __name__ == "__main__":
    principal()
