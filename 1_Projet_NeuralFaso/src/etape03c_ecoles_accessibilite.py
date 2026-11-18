"""Étape 3c : écoles géolocalisées, enfants de 6-11 ans sur une grille fine, et zones éloignées de toute école.

Sources (à placer dans data/01_collecte/cartographie/, sans les renommer) :
  - hotosm_bfa_education_facilities_osm_geojson.zip : établissements d'enseignement d'OpenStreetMap (HOT, export HDX) ;
    on garde les « school » (le primaire et le secondaire ne sont pas distingués dans OSM) ;
  - bfa_ppp_2020_1km_UNadj_ASCII_XYZ.zip : population WorldPop 2020 sur une grille de 1 km (ajustée ONU).
Autres entrées : fond de carte des provinces (étape 3b), projections INSD (étape 2c), annuaire 2024-2025 (étape 2b).

Méthode :
  1. chaque école et chaque carré de 1 km est rattaché à sa province (test point dans polygone) ;
  2. la population WorldPop de chaque province est recalée sur les 6-11 ans de l'INSD en 2024 :
     enfants du carré = population du carré × (6-11 ans INSD de la province / population WorldPop de la province) ;
  3. distance de chaque carré à l'école OSM la plus proche (arbre k-d, distances en km) ;
  4. les carrés sont regroupés en mailles d'environ 5 km ; une maille est une « zone candidate » quand elle compte
     au moins SEUIL_ENFANTS enfants à plus de DISTANCE_KM d'une école connue ;
  5. fiabilité de chaque zone : « carte plus complète » si la province a au moins COUVERTURE_MIN de ses écoles dans OSM,
     « carte incomplète » sinon ; aucune zone n'est certaine : OSM ne recense qu'une partie des écoles ; aucune zone dans les provinces où moins de TBS_SECURITE % des enfants vont à l'école
     (la priorité y est de rouvrir les écoles existantes, que OSM cartographie souvent encore).

Limites (écrites dans le journal) : OSM ne recense pas toutes les écoles, surtout en zone rurale et en zone d'insécurité ;
une zone « loin d'une école connue » peut donc avoir une école non cartographiée. L'état des salles (paille, banco)
et les fermetures ne sont pas publiés école par école : ils restent au niveau de la province.

Lancement :  python src/etape03c_ecoles_accessibilite.py
"""
import io
import json
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config

DISTANCE_KM = 5          # seuil de la DGESS : « plus de 5 km » (tableau V.5 de l'annuaire)
SEUIL_ENFANTS = 150      # enfants de 6-11 ans éloignés dans une maille pour la retenir comme zone candidate
MAILLE_DEG = 0.05        # environ 5,5 km
COUVERTURE_MIN = 0.6     # écoles OSM / écoles de l'annuaire : en dessous, la carte des écoles est trop incomplète
TBS_SECURITE = 40        # provinces « rouvrir d'abord » (même seuil que l'étape 4) : pas de construction proposée
KM_LAT = 110.57
KM_LON = 111.32 * np.cos(np.radians(12.3))
CARTO = config.DOSSIERS["collecte"] / "cartographie"


def lire(motif, dossier):
    f = sorted(config.DOSSIERS[dossier].glob(motif))
    if not f:
        raise SystemExit(f"Introuvable : {motif} — lancez les étapes précédentes.")
    return f[-1]


def anneaux(geom):
    return [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]


def dans_polygone(x, y, anneau):
    """Test point dans polygone (rayon horizontal), vectorisé sur des tableaux numpy."""
    a = np.asarray(anneau)
    x1, y1, x2, y2 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
    dedans = np.zeros(len(x), dtype=bool)
    for i in range(len(x1)):
        traverse = ((y1[i] > y) != (y2[i] > y)) & (x < (x2[i] - x1[i]) * (y - y1[i]) / (y2[i] - y1[i] + 1e-15) + x1[i])
        dedans ^= traverse
    return dedans


def rattacher(lon, lat, geo):
    """Province (ancien découpage) de chaque point ; '' hors du pays."""
    prov = np.full(len(lon), "", dtype=object)
    for f in geo["features"]:
        for poly in anneaux(f["geometry"]):
            ext = np.asarray(poly[0])
            m = (lon >= ext[:, 0].min()) & (lon <= ext[:, 0].max()) & (lat >= ext[:, 1].min()) & (lat <= ext[:, 1].max()) & (prov == "")
            if m.any():
                idx = np.where(m)[0]
                ok = dans_polygone(lon[idx], lat[idx], ext)
                prov[idx[ok]] = f["properties"]["province"]
    return prov


def ecoles_osm():
    z = zipfile.ZipFile(CARTO / "hotosm_bfa_education_facilities_osm_geojson.zip")
    g = json.loads(z.read([n for n in z.namelist() if n.endswith("json")][0]))
    lignes = []
    for f in g["features"]:
        p = f["properties"]
        if (p.get("amenity") or p.get("building")) != "school" or not f.get("geometry"):
            continue
        geom = f["geometry"]
        c = np.asarray(geom["coordinates"] if geom["type"] == "Point" else anneaux(geom)[0][0], dtype=float).reshape(-1, 2)
        lon, lat = c[:, 0].mean(), c[:, 1].mean()
        lignes.append({"osm_id": p.get("id"), "nom": (p.get("name_fr") or p.get("name") or "").strip(),
                       "lon": round(lon, 5), "lat": round(lat, 5), "statut": p.get("operator_type") or "",
                       "commune": p.get("adm3_name") or "", "localite": p.get("addr_city") or ""})
    return regrouper_sites(pd.DataFrame(lignes).drop_duplicates(subset=["lon", "lat"]))


def regrouper_sites(df, rayon_km=0.2):
    """OSM décrit souvent chaque bâtiment d'une école : les points à moins de `rayon_km` l'un de l'autre
    (de proche en proche) forment un seul site d'école, placé à leur centre, avec le premier nom renseigné."""
    xy = np.column_stack([df.lon * KM_LON, df.lat * KM_LAT])
    parent = np.arange(len(df))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, k in cKDTree(xy).query_pairs(rayon_km):
        a, b = racine(i), racine(k)
        if a != b:
            parent[b] = a
    df = df.assign(site=[racine(i) for i in range(len(df))])
    # nom : de préférence un nom propre (« École primaire de Kaya B ») plutôt qu'un nom générique (« École »)
    generique = df.nom.str.lower().str.strip().isin(["ecole", "école", "ecole primaire", "école primaire", "school", "primary school", "ceg", "lycée", "lycee", "medersa", "médersa"])
    df["rang_nom"] = np.where(df.nom == "", 2, np.where(generique, 1, 0))
    meilleur = df.sort_values("rang_nom").groupby("site")
    vide = lambda c: df[c].where(df[c] != "")
    sites = df.groupby("site").agg(osm_id=("osm_id", "first"), lon=("lon", "mean"), lat=("lat", "mean"), points_osm=("osm_id", "size"))
    sites["nom"] = meilleur.nom.first()
    sites["statut"] = df.assign(v=vide("statut")).groupby("site").v.first().fillna("")
    sites["commune"] = df.assign(v=vide("commune")).groupby("site").v.first().fillna("")
    sites["localite"] = df.assign(v=vide("localite")).groupby("site").v.first().fillna("")
    noms = df.groupby("site").nom.apply(lambda s: " ".join(s).lower())
    sites["type"] = noms.map(type_ecole)
    return sites.round({"lon": 5, "lat": 5}).reset_index(drop=True)


def type_ecole(texte):
    """Type d'établissement déduit des noms OSM du site (OSM ne distingue pas les niveaux)."""
    if any(m in texte for m in ("medersa", "médersa", "franco-arabe", "franco arabe")):
        return "Médersa (franco-arabe)"
    if any(m in texte for m in ("ceg", "lycée", "lycee", "collège", "college", "post-primaire", "post primaire", "cem ")):
        return "Post-primaire ou secondaire"
    if any(m in texte for m in ("primaire", "ecole", "école", "ep ", "epp", "school")):
        return "École (probablement primaire)"
    return "Type non précisé"


def population():
    z = zipfile.ZipFile(CARTO / "bfa_ppp_2020_1km_UNadj_ASCII_XYZ.zip")
    p = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    p.columns = ["lon", "lat", "pop"]
    return p[p["pop"] > 0].reset_index(drop=True)


def principal():
    geo = json.loads(lire("*fond-de-carte-provinces-simplifie*.geojson", "transformation").read_text(encoding="utf-8"))
    j = ["# Journal de l'étape 3c — écoles géolocalisées et accessibilité", f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}", ""]

    ec = ecoles_osm()
    ec["province"] = rattacher(ec.lon.to_numpy(), ec.lat.to_numpy(), geo)
    ec = ec[ec.province != ""].reset_index(drop=True)

    pop = population()
    pop["province"] = rattacher(pop.lon.to_numpy(), pop.lat.to_numpy(), geo)
    pop = pop[pop.province != ""].reset_index(drop=True)

    pr = pd.read_csv(lire("*projections-population-2020-2035-province*.csv", "nettoyage"))
    enfants = pr[(pr.niveau == "province") & (pr.groupe_age == "6-11") & (pr.sexe == "T") & (pr.annee == 2024)].set_index("entite").population
    facteur = enfants / pop.groupby("province")["pop"].sum()
    pop["enfants_6_11"] = pop["pop"] * pop.province.map(facteur)

    arbre = cKDTree(np.column_stack([ec.lon * KM_LON, ec.lat * KM_LAT]))
    dist, _ = arbre.query(np.column_stack([pop.lon * KM_LON, pop.lat * KM_LAT]))
    # pour chaque école : école voisine la plus proche, enfants de 6-11 ans à moins de 3 km
    dv, _ = arbre.query(arbre.data, k=2)
    ec["ecole_voisine_km"] = dv[:, 1].round(1)
    arbre_pop = cKDTree(np.column_stack([pop.lon * KM_LON, pop.lat * KM_LAT]))
    enf = pop.enfants_6_11.to_numpy()
    ec["enfants_6_11_moins_3km"] = [round(enf[ix].sum()) for ix in arbre_pop.query_ball_point(arbre.data, r=3)]
    ec["lien_osm"] = "https://www.openstreetmap.org/" + ec.osm_id.astype(str)
    pop["distance_ecole_km"] = dist
    pop["loin"] = pop.distance_ecole_km > DISTANCE_KM

    # mailles d'environ 5 km
    pop["mx"] = np.floor(pop.lon / MAILLE_DEG).astype(int)
    pop["my"] = np.floor(pop.lat / MAILLE_DEG).astype(int)
    pop["enf_loin"] = pop.enfants_6_11 * pop.loin
    pop["enf_2km"] = pop.enfants_6_11 * (pop.distance_ecole_km > 2)
    pop["enf_3km"] = pop.enfants_6_11 * (pop.distance_ecole_km > 3)
    g = pop.groupby(["mx", "my"])
    m = pd.DataFrame({"enfants_6_11": g.enfants_6_11.sum(), "enfants_loin": g.enf_loin.sum(),
                      "enfants_plus_2km": g.enf_2km.sum(), "enfants_plus_3km": g.enf_3km.sum(),
                      "distance_moyenne_km": g.apply(lambda d: np.average(d.distance_ecole_km, weights=d.enfants_6_11), include_groups=False),
                      "province": g.province.agg(lambda s: s.value_counts().index[0])}).reset_index()
    m["lon"] = ((m.mx + 0.5) * MAILLE_DEG).round(4)
    m["lat"] = ((m.my + 0.5) * MAILLE_DEG).round(4)
    # centre de la zone éloignée : barycentre des carrés éloignés, pondéré par les enfants
    lo = pop[pop.loin].copy()
    lo["wx"], lo["wy"] = lo.lon * lo.enfants_6_11, lo.lat * lo.enfants_6_11
    c = lo.groupby(["mx", "my"])[["wx", "wy", "enfants_6_11"]].sum()
    c["lon_c"], c["lat_c"] = (c.wx / c.enfants_6_11).round(4), (c.wy / c.enfants_6_11).round(4)
    m = m.merge(c[["lon_c", "lat_c"]], left_on=["mx", "my"], right_index=True, how="left")
    zones = m[m.enfants_loin >= SEUIL_ENFANTS].copy()
    d_c, _ = arbre.query(np.column_stack([zones.lon_c * KM_LON, zones.lat_c * KM_LAT]))
    zones["ecole_la_plus_proche_km"] = d_c.round(1)
    zones = zones.sort_values("enfants_loin", ascending=False).reset_index(drop=True)
    zones["rang"] = zones.index + 1

    # synthèse par province
    i1 = pd.read_csv(lire("*annuaires-ecoles-salles-maitres-province*.csv", "nettoyage"))
    i1 = i1[(i1.annee_scolaire == "2024-2025") & (i1.statut == "Total") & ~i1.province.str.startswith("_")].set_index("province")
    s = pd.DataFrame({"ecoles_osm": ec.groupby("province").size(), "ecoles_primaires_annuaire": i1.nb_ecoles,
                      "enfants_6_11_2024": pop.groupby("province").enfants_6_11.sum().round(0),
                      "enfants_a_plus_de_5km": pop.groupby("province").enf_loin.sum().round(0),
                      "zones_candidates": zones.groupby("province").size()}).fillna(0)
    s["couverture_osm"] = (s.ecoles_osm / s.ecoles_primaires_annuaire).round(3)
    s["part_enfants_a_plus_de_5km"] = (s.enfants_a_plus_de_5km / s.enfants_6_11_2024).round(4)
    s.index.name = "province"
    tbs = (i1.nb_eleves / enfants.reindex(i1.index) * 100)
    s["tbs_2024"] = tbs.round(1)
    s["fiabilite"] = np.where(s.tbs_2024 < TBS_SECURITE, "rouvrir d'abord",
                              np.where(s.couverture_osm >= COUVERTURE_MIN, "carte plus complète", "carte incomplète"))
    zones["fiabilite"] = zones.province.map(s.fiabilite)
    zones = zones[zones.fiabilite != "rouvrir d'abord"].sort_values(["fiabilite", "enfants_loin"], ascending=[True, False]).reset_index(drop=True)
    zones["rang"] = zones.index + 1
    s["zones_candidates"] = zones.groupby("province").size().reindex(s.index).fillna(0)

    tr, an = config.DOSSIERS["transformation"], config.DOSSIERS["analyse"]
    ec[["osm_id", "nom", "type", "statut", "commune", "localite", "province", "points_osm", "ecole_voisine_km",
        "enfants_6_11_moins_3km", "lien_osm", "lon", "lat"]].to_csv(
        config.nom_fichier("transformation", "architect", "ecoles-osm-geolocalisees"), index=False, encoding="utf-8")
    m[["lon", "lat", "province", "enfants_6_11", "enfants_loin", "distance_moyenne_km", "enfants_plus_2km", "enfants_plus_3km"]].round(
        {"enfants_6_11": 1, "enfants_loin": 1, "distance_moyenne_km": 1, "enfants_plus_2km": 1, "enfants_plus_3km": 1}).to_csv(
        config.nom_fichier("transformation", "architect", "enfants-6-11-ans-grille-5km"), index=False, encoding="utf-8")
    s.reset_index().to_csv(config.nom_fichier("transformation", "architect", "accessibilite-ecoles-province"), index=False, encoding="utf-8")
    zones[["rang", "fiabilite", "province", "lon_c", "lat_c", "enfants_loin", "enfants_6_11", "ecole_la_plus_proche_km"]].rename(
        columns={"lon_c": "lon", "lat_c": "lat", "enfants_loin": "enfants_6_11_a_plus_de_5km", "enfants_6_11": "enfants_6_11_maille"}).round({"enfants_6_11_a_plus_de_5km": 0, "enfants_6_11_maille": 0}).to_csv(
        config.nom_fichier("analyse", "scientist", "zones-candidates-nouvelles-ecoles"), index=False, encoding="utf-8")

    tot = s.sum(numeric_only=True)
    n_rouvrir = int((s.fiabilite == "rouvrir d'abord").sum())
    j += ["## Données",
          f"- Points OSM « school » : {int(ec.points_osm.sum()):_}, regroupés en {len(ec):_} sites d'écoles (les points à moins de 200 m forment un même site : "
          f"OSM décrit souvent chaque bâtiment). Écoles primaires de l'annuaire 2024-2025 : {int(tot.ecoles_primaires_annuaire):_}. "
          f"OSM recense donc au plus {len(ec) / tot.ecoles_primaires_annuaire:.0%} des écoles, primaire et secondaire mélangés.",
          f"- Carrés de 1 km habités : {len(pop):_} ; enfants de 6-11 ans recalés sur l'INSD 2024 : {pop.enfants_6_11.sum():_.0f}.", "",
          "## Résultats",
          f"- Enfants de 6-11 ans à plus de {DISTANCE_KM} km d'une école connue : {pop.enf_loin.sum():_.0f} ({pop.enf_loin.sum() / pop.enfants_6_11.sum():.1%}).",
          f"- Ce chiffre est fortement surestimé, car OSM est incomplet : l'annuaire (tableau V.5) ne compte que 1 % environ d'élèves à plus de 5 km. "
          f"Même dans les {int((s.fiabilite == 'carte plus complète').sum())} provinces où la carte est plus complète "
          f"(au moins {COUVERTURE_MIN:.0%} des écoles cartographiées, hors provinces à rouvrir d'abord), "
          f"{s[s.fiabilite == 'carte plus complète'].enfants_a_plus_de_5km.sum():_.0f} enfants sont à plus de {DISTANCE_KM} km d'une école connue "
          f"({s[s.fiabilite == 'carte plus complète'].enfants_a_plus_de_5km.sum() / s[s.fiabilite == 'carte plus complète'].enfants_6_11_2024.sum():.1%}).",
          f"- Zones peuplées sans école sur la carte (au moins {SEUIL_ENFANTS} enfants à plus de {DISTANCE_KM} km d'une école connue, maille d'environ 5 km) : "
          f"{int((zones.fiabilite == 'carte plus complète').sum()):_} là où la carte est plus complète, {int((zones.fiabilite == 'carte incomplète').sum()):_} là où elle est incomplète ; "
          f"aucune dans les {n_rouvrir} provinces à rouvrir d'abord.",
          f"- Dans ces provinces, OSM recense souvent plus d'écoles que l'annuaire (Tapoa : {int(s.ecoles_osm.get('TAPOA', 0))} contre "
          f"{int(s.ecoles_primaires_annuaire.get('TAPOA', 0))}) : la carte garde les écoles d'avant la crise, dont beaucoup sont fermées.", "",
          "| Province | Fiabilité de la carte | Écoles OSM | Écoles (annuaire) | Couverture OSM | Enfants à plus de 5 km | Zones candidates |", "|---|---|---|---|---|---|---|"]
    for p, r in s.sort_values(["fiabilite", "enfants_a_plus_de_5km"], ascending=[True, False]).iterrows():
        j.append(f"| {p} | {r.fiabilite} | {r.ecoles_osm:_.0f} | {r.ecoles_primaires_annuaire:_.0f} | {r.couverture_osm:.0%} | {r.enfants_a_plus_de_5km:_.0f} "
                 f"({r.part_enfants_a_plus_de_5km:.0%}) | {r.zones_candidates:.0f} |")
    j += ["", "## Limites",
          "- OSM est incomplet, surtout en zone rurale et en zone d'insécurité : une zone « loin d'une école connue » peut avoir une école non cartographiée. "
          "La colonne « couverture OSM » indique où la carte est la plus fiable.",
          "- WorldPop 2020 ne tient pas compte des déplacements de population liés à l'insécurité.",
          "- L'état des salles (paille, banco) et les fermetures d'écoles ne sont pas publiés école par école : ils sont donnés par province.",
          "- Une zone peuplée sans école sur la carte est une piste à vérifier sur le terrain, pas un site de construction : "
          "il peut y exister une école non cartographiée. Avec la carte scolaire géolocalisée du ministère, la même méthode donnerait des sites fiables."]
    texte = "\n".join(j).replace("_", " ")
    config.nom_fichier("transformation", "architect", "journal-ecoles-accessibilite", ext="md").write_text(texte, encoding="utf-8")
    print(texte)


if __name__ == "__main__":
    principal()
