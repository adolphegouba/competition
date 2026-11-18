# NeuralFaso_02-nettoyage_D3_engineer_projections-population_v1.py
# Nom d'origine dans le projet : src/etape02c_projections_population.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 2c : extraction des projections démographiques 2020-2035 (INSD, RGPH 2019, volume 4).

Source : CSV du Data Pack NADA276_RGPH2019_Projections_2020-2035.csv, placé dans
data/01_collecte/projections/. Les chapitres 2 et 3 donnent, pour chaque région et chaque
province, la population par groupe d'âges et par sexe, année par année de 2020 à 2035.

Sortie : une ligne par niveau (région ou province), entité, groupe d'âges, année et sexe.
Groupes d'âges utiles au Défi 3 : 6-11 ans (âge officiel du primaire) et 3-5 ans (préscolaire).

Lancement :  python src/etape02c_projections_population.py
"""
import csv
import re
from datetime import datetime

import pandas as pd

import config
from etape02b_extraction_annuaires import PROVINCES, REGION_DE, nombre
from referentiels import cle

csv.field_size_limit(10_000_000)

VARIANTES = {"BALES": "BALE", "LES BALE": "BALE", "KOMONDJOARI": "KOMANDJARI", "KOURITENGA": "KOURITTENGA"}


def entite(texte):
    """Reconnaît l'en-tête de page : « Balés », « Région de la Boucle du Mouhoun »..."""
    k = cle(texte)
    m = re.match(r"^REGION (DE LA |DES |DU |DE L'|DE L’|DE )?(.+)$", k)
    if m:
        r = m.group(2).strip().replace("HAUT-BASSINS", "HAUTS-BASSINS")
        if r in PROVINCES:
            return "region", r
    k = VARIANTES.get(k, k)
    if k in REGION_DE:
        return "province", k
    return None, None


def groupe_age(texte):
    k = cle(texte).replace("ANS", "").replace("AN", "").strip()
    k = re.sub(r"\s*-\s*", "-", k)
    if k in {"TOTAL"}:
        return "total"
    if re.match(r"^80\s*ET\s*\+$", k):
        return "80+"
    if re.match(r"^\d{1,2}(-\d{1,2})?$", k):
        return k
    return None


def principal():
    fichiers = sorted((config.DOSSIERS["collecte"] / "projections").glob("*Projections*.csv"))
    if not fichiers:
        raise SystemExit("Placez NADA276_RGPH2019_Projections_2020-2035.csv dans data/01_collecte/projections/")
    src = fichiers[0]
    res = []
    with open(src, encoding="utf-8-sig", newline="") as f:
        lecteur = csv.reader(f, delimiter=";")
        next(lecteur, None)
        niveau = nom = None
        annees = []
        for r in lecteur:
            if len(r) < 5:
                continue
            page, num = int(r[1]), int(r[2])
            c = [x.strip() for x in r[4:] if x and x.strip() and len(x) < 200]
            if not c or page < 130:          # les tableaux régionaux commencent au chapitre 2
                continue
            if num == 1 and len(c) == 1:
                n, e = entite(c[0])
                if n:
                    niveau, nom, annees = n, e, []
                continue
            # ligne d'années (éventuellement précédée de « Groupes d'âges »)
            ans = [int(x) for x in c if re.fullmatch(r"20[23]\d", x)]
            if ans and len(ans) >= len(c) - 1:
                annees = ans
                continue
            if not (nom and annees):
                continue
            g = groupe_age(c[0])
            if not g:
                continue
            vals = [nombre(x) for x in c[1:]]
            if len(vals) != 3 * len(annees) or any(v is None for v in vals):
                continue
            for i, a in enumerate(annees):
                h, fe, ens = vals[3 * i: 3 * i + 3]
                for sexe, v in (("G", h), ("F", fe), ("T", ens)):
                    res.append({"niveau": niveau, "entite": nom,
                                "region": nom if niveau == "region" else REGION_DE[nom],
                                "groupe_age": g, "annee": a, "sexe": sexe, "population": v,
                                "source": f"{src.stem.split('_')[0]} p.{page}"})
    df = pd.DataFrame(res).drop_duplicates(subset=["niveau", "entite", "groupe_age", "annee", "sexe"])

    # correction des coquilles du document : quand l'ensemble ≠ hommes + femmes, l'ensemble est recalculé
    cles = ["niveau", "entite", "groupe_age", "annee"]
    w = df.pivot_table(index=cles, columns="sexe", values="population")
    fautes = w[(w["G"] + w["F"] - w["T"]).abs() > 1]
    corrections = []
    for idx, row in fautes.iterrows():
        rapport = row["G"] / row["F"] if row["F"] else 0
        echelle = (row["G"] + row["F"]) / row["T"] if row["T"] else 0
        if not (0.7 <= rapport <= 1.4 and 0.3 <= echelle <= 3.5):
            # garçons ou filles mal lus : on garde l'ensemble imprimé et on retire G et F
            m = (df[cles].apply(tuple, axis=1) == idx) & df.sexe.isin(["G", "F"])
            df = df[~m]
            corrections.append(f"  - {idx[1]} ({idx[0]}), {idx[2]} ans, {idx[3]} : hommes/femmes illisibles "
                               f"({row['G']:.0f} / {row['F']:.0f}), seul l'ensemble imprimé ({row['T']:.0f}) est gardé")
            continue
        m = (df[cles].apply(tuple, axis=1) == idx) & (df.sexe == "T")
        df.loc[m, "population"] = row["G"] + row["F"]
        corrections.append(f"  - {idx[1]} ({idx[0]}), {idx[2]} ans, {idx[3]} : ensemble imprimé {row['T']:.0f}, "
                           f"remplacé par hommes + femmes = {row['G'] + row['F']:.0f}")

    # contrôles
    j = [f"# Journal d'extraction — projections démographiques 2020-2035 (INSD)",
         f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}. Source : `{src.name}`", "",
         f"- Coquilles corrigées dans le document source : {len(corrections)}", *corrections,
         f"- {len(df)} valeurs ; {df[df.niveau == 'province'].entite.nunique()} provinces (attendu 45), "
         f"{df[df.niveau == 'region'].entite.nunique()} régions (attendu 13) ; années {df.annee.min()} à {df.annee.max()}.", ""]
    manque = df[df.groupe_age == "6-11"].groupby(["niveau", "entite"]).annee.nunique()
    manque = manque[manque < 16]
    j.append(f"- Entités sans les 16 années pour les 6-11 ans : {len(manque)} "
             + (f"({', '.join(f'{a}/{b}' for a, b in manque.index)})" if len(manque) else ""))
    t = df[(df.groupe_age == "6-11")].pivot_table(index=["niveau", "entite", "annee"], columns="sexe", values="population")
    ko = ((t["G"] + t["F"] - t["T"]).abs() > 1).sum()
    j.append(f"- Hommes + femmes = ensemble (6-11 ans) : {len(t)} comparaisons, {ko} écarts.")
    p = df[(df.niveau == "province") & (df.groupe_age == "6-11") & (df.sexe == "T")].groupby(["region", "annee"]).population.sum()
    rr = df[(df.niveau == "region") & (df.groupe_age == "6-11") & (df.sexe == "T")].set_index(["region", "annee"]).population
    comp = pd.concat([p.rename("somme_provinces"), rr.rename("region")], axis=1, join="inner")
    ecart = ((comp.somme_provinces - comp.region).abs() / comp.region)
    j.append(f"- Somme des provinces = région (6-11 ans, tolérance 0,5 %) : {len(comp)} comparaisons, "
             f"{int((ecart > 0.005).sum())} écarts ; écart maximal {ecart.max():.2%}.")
    j.append("")
    j.append("Note : les projections suivent les 13 anciennes régions et les 45 provinces, comme les données DGESS.")

    out = config.nom_fichier("nettoyage", "engineer", "projections-population-2020-2035-province")
    df.to_csv(out, index=False, encoding="utf-8")
    jp = config.nom_fichier("nettoyage", "engineer", "journal-projections", ext="md")
    jp.write_text("\n".join(j), encoding="utf-8")
    print("\n".join(j))


if __name__ == "__main__":
    principal()
