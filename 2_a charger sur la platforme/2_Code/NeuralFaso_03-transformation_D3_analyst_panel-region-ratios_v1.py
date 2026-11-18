# NeuralFaso_03-transformation_D3_analyst_panel-region-ratios_v1.py
# Nom d'origine dans le projet : src/etape03_transformation.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 3 : transformation — panel région × année et ratios de répartition des moyens.

Entrée  : données propres de l'étape 2 (format long).
Sortie  : un panel « une ligne = un cycle, une région, une année scolaire » avec
          les effectifs, les écoles, les salles, les taux et les ratios utiles au Défi 3,
          plus un panel national (somme des régions) et un dictionnaire des variables.

Lancement :  python src/etape03_transformation.py
"""
from datetime import datetime

import numpy as np
import pandas as pd

import config

DESCRIPTIONS = {
    "cycle": "Cycle d'enseignement (prescolaire, primaire)",
    "region": "Région (13 anciennes régions) ou NATIONAL",
    "annee_scolaire": "Année scolaire AAAA-AAAA",
    "annee": "Année de début de l'année scolaire (pour les graphiques)",
    "effectif_T": "Élèves inscrits, total", "effectif_G": "Élèves inscrits, garçons",
    "effectif_F": "Élèves inscrits, filles",
    "nouveaux_inscrits_cp1_T": "Nouveaux inscrits au CP1, total",
    "nouveaux_inscrits_cp1_F": "Nouveaux inscrits au CP1, filles",
    "nb_ecoles": "Nombre d'écoles (ou de structures au préscolaire), tous statuts",
    "nb_ecoles_public": "Nombre d'écoles publiques",
    "nb_ecoles_prive": "Nombre d'écoles privées",
    "nb_salles": "Nombre de salles de classe, tous statuts (disponible au préscolaire)",
    "nb_salles_public": "Nombre de salles de classe publiques",
    "tbs_T": "Taux brut de scolarisation, total (%)", "tbs_G": "TBS garçons (%)", "tbs_F": "TBS filles (%)",
    "tba_T": "Taux brut d'admission, total (%)",
    "taux_achevement_T": "Taux d'achèvement, total (%)", "taux_achevement_F": "Taux d'achèvement, filles (%)",
    "taux_reussite_cep_T": "Taux de réussite au CEP, total (%)",
    "ips_tbs": "Indice de parité filles/garçons du TBS", "ips_tba": "Indice de parité du TBA",
    "ips_tap": "Indice de parité du taux d'achèvement",
    "eleves_par_ecole": "Élèves par école (effectif_T / nb_ecoles)",
    "eleves_par_salle": "Élèves par salle de classe (effectif_T / nb_salles)",
    "part_filles": "Part des filles dans les effectifs (effectif_F / effectif_T)",
    "part_ecoles_privees": "Part des écoles privées (nb_ecoles_prive / nb_ecoles)",
    "ecart_tbs_g_f": "Écart de TBS garçons moins filles (points)",
    "var_effectif": "Variation des effectifs par rapport à l'année précédente",
    "var_ecoles": "Variation du nombre d'écoles par rapport à l'année précédente",
    "ecoles_max_historique": "Nombre maximal d'écoles atteint depuis 2015-2016",
    "ecoles_perdues": "Écoles en moins par rapport au maximum historique (fermetures probables)",
    "taux_ecoles_perdues": "ecoles_perdues / ecoles_max_historique",
    "eleves_par_ecole_rang": "Rang de la région (1 = plus forte charge par école) pour l'année",
}


def charger():
    fichiers = sorted(config.DOSSIERS["nettoyage"].glob(f"*_02-nettoyage_{config.DEFI}_engineer_dgess-prescolaire-primaire-propres_*.csv"))
    if not fichiers:
        raise SystemExit("Données propres introuvables : lancez d'abord src/etape02_nettoyage_dgess.py")
    return pd.read_csv(fichiers[-1], dtype={"annee_scolaire": str}), fichiers[-1].name


def pivot_simple(df, indicateur, avec_sexe=True):
    """Valeurs d'un indicateur sans autre dimension que la région (et le sexe)."""
    sous = df[(df["indicateur"] == indicateur) & df["statut"].isna() & df["milieu"].isna() & df["classe"].isna()]
    if sous.empty:
        return None
    if avec_sexe:
        p = sous.pivot_table(index=["cycle", "region", "annee_scolaire"], columns="sexe", values="valeur", aggfunc="first")
        p.columns = [f"{indicateur}_{s}" for s in p.columns]
    else:
        p = sous.groupby(["cycle", "region", "annee_scolaire"])["valeur"].first().to_frame(indicateur)
    return p


def comptage_par_statut(df, indicateur, nom):
    sous = df[(df["indicateur"] == indicateur) & df["statut"].notna() & (df["sexe"] == "T")]
    if sous.empty:
        return None
    total = sous.groupby(["cycle", "region", "annee_scolaire"])["valeur"].sum().to_frame(nom)
    par = sous.pivot_table(index=["cycle", "region", "annee_scolaire"], columns="statut", values="valeur", aggfunc="sum")
    par.columns = [f"{nom}_{c.lower()}" for c in par.columns]
    return total.join(par)


def construire_panel(df):
    reg = df[df["niveau_geo"] == "regional"].copy()
    morceaux = []
    for ind in ["effectif", "nouveaux_inscrits_cp1", "tbs", "tba", "taux_achevement", "taux_reussite_cep"]:
        p = pivot_simple(reg, ind)
        if p is not None:
            morceaux.append(p)
    for ind in ["ips_tbs", "ips_tba", "ips_tap"]:
        p = pivot_simple(reg, ind, avec_sexe=False)
        if p is not None:
            morceaux.append(p)
    # un effectif sans statut est déjà couvert ; les écoles et les salles sont ventilées par statut
    for ind, nom in [("nb_ecoles", "nb_ecoles"), ("nb_salles", "nb_salles")]:
        p = comptage_par_statut(reg, ind, nom)
        if p is not None:
            morceaux.append(p)
    panel = pd.concat(morceaux, axis=1).reset_index()
    return panel


def ajouter_ratios(panel):
    p = panel.sort_values(["cycle", "region", "annee_scolaire"]).copy()
    p["annee"] = p["annee_scolaire"].str[:4].astype(int)
    div = lambda a, b: np.where((b > 0) & pd.notna(b), a / b, np.nan)
    if {"effectif_T", "nb_ecoles"} <= set(p.columns):
        p["eleves_par_ecole"] = div(p["effectif_T"], p["nb_ecoles"])
    if {"effectif_T", "nb_salles"} <= set(p.columns):
        p["eleves_par_salle"] = div(p["effectif_T"], p["nb_salles"])
    if {"effectif_F", "effectif_T"} <= set(p.columns):
        p["part_filles"] = div(p["effectif_F"], p["effectif_T"])
    if {"nb_ecoles_prive", "nb_ecoles"} <= set(p.columns):
        p["part_ecoles_privees"] = div(p["nb_ecoles_prive"], p["nb_ecoles"])
    if {"tbs_G", "tbs_F"} <= set(p.columns):
        p["ecart_tbs_g_f"] = p["tbs_G"] - p["tbs_F"]
    g = p.groupby(["cycle", "region"], group_keys=False)
    if "effectif_T" in p:
        p["var_effectif"] = g["effectif_T"].pct_change()
    if "nb_ecoles" in p:
        p["var_ecoles"] = g["nb_ecoles"].pct_change()
        p["ecoles_max_historique"] = g["nb_ecoles"].cummax()
        p["ecoles_perdues"] = p["ecoles_max_historique"] - p["nb_ecoles"]
        p["taux_ecoles_perdues"] = div(p["ecoles_perdues"], p["ecoles_max_historique"])
    if "eleves_par_ecole" in p:
        p["eleves_par_ecole_rang"] = p.groupby(["cycle", "annee_scolaire"])["eleves_par_ecole"].rank(ascending=False, method="min")
    return p


def panel_national(panel):
    comptages = [c for c in panel.columns if c.startswith(("effectif_", "nouveaux_inscrits", "nb_ecoles", "nb_salles"))]
    nat = panel.groupby(["cycle", "annee_scolaire"])[comptages].sum(min_count=1).reset_index()
    nat.insert(1, "region", "NATIONAL")
    return ajouter_ratios(nat)


def principal():
    df, source = charger()
    panel = ajouter_ratios(construire_panel(df))
    nat = panel_national(panel)
    tout = pd.concat([panel, nat], ignore_index=True, sort=False)

    # descriptions des variantes par sexe non listées (ex. tba_G, tba_F)
    for c in list(tout.columns):
        if c not in DESCRIPTIONS and c[-2:] in ("_G", "_F") and c[:-2] + "_T" in DESCRIPTIONS:
            base = DESCRIPTIONS[c[:-2] + "_T"].replace(", total", "")
            DESCRIPTIONS[c] = f"{base}, {'garçons' if c.endswith('_G') else 'filles'}"
        if c == "nb_ecoles_communautaire":
            DESCRIPTIONS[c] = "Nombre de structures communautaires (préscolaire)"
        if c == "nb_salles_prive":
            DESCRIPTIONS[c] = "Nombre de salles de classe privées"
        if c == "nb_salles_communautaire":
            DESCRIPTIONS[c] = "Nombre de salles de classe communautaires"
    base_ordre = list(DESCRIPTIONS)
    ordre = sorted([c for c in tout.columns if c in DESCRIPTIONS],
                   key=lambda c: (base_ordre.index(c[:-2] + "_T") + 0.5) if (c[-2:] in ("_G", "_F") and c[:-2] + "_T" in base_ordre and c not in base_ordre[:base_ordre.index(c[:-2] + "_T") + 3]) else base_ordre.index(c))
    ordre += [c for c in tout.columns if c not in ordre]
    tout = tout[ordre].sort_values(["cycle", "region", "annee_scolaire"])
    num = tout.select_dtypes("number").columns
    tout[num] = tout[num].round(4)

    config.DOSSIERS["transformation"].mkdir(parents=True, exist_ok=True)
    sortie = config.nom_fichier("transformation", "analyst", "panel-region-annee-ratios")
    tout.to_csv(sortie, index=False, encoding="utf-8")

    dico = config.nom_fichier("transformation", "architect", "dictionnaire-panel", ext="md")
    lignes = ["# Dictionnaire des variables — panel région × année (étape 3)", "",
              f"Source : `{source}` (étape 2). Une ligne = un cycle, une région, une année scolaire. "
              "Les lignes NATIONAL sont la somme des 13 régions ; les taux nationaux ne sont pas recalculés.", "",
              "| Variable | Description | Valeurs manquantes |", "|---|---|---|"]
    for c in tout.columns:
        lignes.append(f"| `{c}` | {DESCRIPTIONS.get(c, '—')} | {int(tout[c].isna().sum())} |")
    dico.write_text("\n".join(lignes), encoding="utf-8")

    journal = config.nom_fichier("transformation", "analyst", "journal-transformation", ext="md")
    reg = tout[tout["region"] != "NATIONAL"]
    j = [f"# Journal de transformation — {datetime.now():%d/%m/%Y %H:%M}", "",
         f"- Source : `{source}`",
         f"- Panel : {len(tout)} lignes, {tout.shape[1]} variables, cycles {sorted(tout['cycle'].unique())}, "
         f"années {tout['annee_scolaire'].min()} à {tout['annee_scolaire'].max()}.",
         "- Écoles et salles : sommées sur les statuts (public, privé, communautaire).",
         "- Ratios calculés seulement quand le dénominateur est positif.",
         "- `ecoles_perdues` compare chaque année au maximum atteint depuis 2015-2016 : "
         "c'est un indicateur indirect des fermetures, pas un décompte officiel.", ""]
    if "eleves_par_ecole" in reg:
        der = reg[reg["annee_scolaire"] == reg["annee_scolaire"].max()]
        for cyc, g in der.groupby("cycle"):
            g = g.dropna(subset=["eleves_par_ecole"]).sort_values("eleves_par_ecole", ascending=False)
            if not g.empty:
                j.append(f"- {cyc}, {g['annee_scolaire'].iloc[0]} : élèves par école de "
                         f"{g['eleves_par_ecole'].min():.0f} à {g['eleves_par_ecole'].max():.0f} "
                         f"(plus forte charge : {g['region'].iloc[0]}).")
    journal.write_text("\n".join(j), encoding="utf-8")

    print("\n".join(j))
    print("\nFichiers écrits :")
    for p in (sortie, dico, journal):
        print(" -", p.relative_to(config.RACINE))


if __name__ == "__main__":
    principal()
