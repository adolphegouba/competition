# NeuralFaso_02-nettoyage_D3_engineer_nettoyage-dgess_v1.py
# Nom d'origine dans le projet : src/etape02_nettoyage_dgess.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 2 : nettoyage du fichier statistique DGESS (préscolaire et primaire, 2016-2025).

Ce que fait le script :
  1. repère chaque tableau dans chaque feuille (ligne commençant par « Tableau ») ;
  2. lit les deux mises en page rencontrées : colonnes G/F/T sous chaque année,
     ou une colonne SEXE avec une colonne par année ;
  3. remet tout en format long : une ligne = un indicateur, une région ou une
     catégorie, un sexe, une année scolaire ;
  4. harmonise les libellés (régions, sexe, statut, milieu, classe, années) ;
  5. sépare les lignes détaillées des lignes de total, puis contrôle que les
     totaux du fichier correspondent à la somme des détails ;
  6. écrit les fichiers propres, un journal de nettoyage et un dictionnaire.

Lancement :  python src/etape02_nettoyage_dgess.py  [chemin_du_fichier.xlsx]
"""
import sys
from collections import defaultdict
from datetime import datetime

import openpyxl
import pandas as pd

import config
from referentiels import (CLASSES, MILIEUX, REGIONS_13, SEXES, STATUTS, VARIANTES_REGION,
                          annee_scolaire, cle, est_libelle_total, region_canonique)

TOTAL = "_TOTAL_"
DIMENSIONS = ["region", "statut", "milieu", "classe"]
INDICATEURS_COMPTAGE = {"effectif", "nouveaux_inscrits_cp1", "nb_ecoles", "nb_salles",
                        "nb_enseignants"}

journal = []          # lignes du journal de nettoyage
anomalies = []        # anomalies détaillées (deviennent un CSV)


def note(texte):
    journal.append(texte)


def anomalie(feuille, tableau, nature, detail):
    anomalies.append({"feuille": feuille, "tableau": tableau, "nature": nature, "detail": detail})


# ---------------------------------------------------------------------------
# Identification des tableaux
# ---------------------------------------------------------------------------
def indicateur_depuis_titre(titre: str) -> str:
    t = cle(titre)
    regles = [
        ("IPS DU TBA", "ips_tba"), ("IPS DU TBS", "ips_tbs"), ("IPS DU TAP", "ips_tap"),
        ("IPS DU TBPS", "ips_tbps"), ("IPS", "ips"),
        ("NOUVEAUX INSCRITS", "nouveaux_inscrits_cp1"),
        ("TBPS", "tbps"), ("PRESCOLARISATION", "tbps"),
        ("TBA", "tba"), ("TBS", "tbs"),
        ("ACHEVEMENT", "taux_achevement"), ("TAP", "taux_achevement"),
        ("REUSSITE", "taux_reussite_cep"),
        ("NOMBRE D'ECOLES", "nb_ecoles"), ("NOMBRE DE STRUCTURES", "nb_ecoles"),
        ("NOMBRE DE SALLES", "nb_salles"), ("SALLES DE CLASSE", "nb_salles"),
        ("ENSEIGNANTS", "nb_enseignants"), ("EDUCATEURS", "nb_enseignants"),
        ("EFFECTIFS", "effectif"),
    ]
    for motif, code in regles:
        if motif in t:
            return code
    # repli : un code construit à partir du titre
    corps = t.split(":", 1)[-1]
    corps = corps.replace("EVOLUTION", "").split(" DE 20")[0]
    mots = [m for m in corps.lower().replace("'", " ").split() if m not in {"du", "de", "des", "la", "le", "l", "d"}]
    return "_".join(mots[:5]) or "indicateur"


def type_dimension(valeurs, entete):
    """Devine la nature d'une colonne d'après ses valeurs (l'en-tête peut être faux)."""
    cles = [cle(v) for v in valeurs if v is not None and not est_libelle_total(v)]
    if not cles:
        return "autre"
    scores = {
        "region": sum((VARIANTES_REGION.get(k, k) in REGIONS_13) for k in cles),
        "statut": sum(k in STATUTS for k in cles),
        "milieu": sum(k in MILIEUX for k in cles),
        "classe": sum(k in CLASSES for k in cles),
        "sexe": sum(k in SEXES for k in cles),
    }
    meilleur = max(scores, key=scores.get)
    if scores[meilleur] >= 0.6 * len(cles):
        return meilleur
    return "autre_" + (cle(entete).lower().replace(" ", "_") if entete else "colonne")


def nombre(valeur):
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)):
        return float(valeur)
    texte = str(valeur).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if texte in {"", "-", "–", "nd", "ND", "n.d."}:
        return None
    try:
        return float(texte)
    except ValueError:
        return "NON_NUMERIQUE"


def ligne_vide(ligne):
    return all(c is None or str(c).strip() == "" for c in ligne)


def lire_tableau(lignes, debut, nom_feuille):
    """Lit un tableau à partir de la ligne de titre. Retourne (enregistrements, ligne suivante)."""
    titre = str(lignes[debut][0]).strip()
    num = titre.split(":")[0].replace("\xa0", " ").strip()
    ref = f"{nom_feuille} / {num}"
    indicateur = indicateur_depuis_titre(titre)
    cycle = "prescolaire" if ("PRESCOLAIRE" in cle(titre) or cle(nom_feuille) == "PRESCOLAIRE") else "primaire"

    h = debut + 1
    entete = list(lignes[h])
    # colonnes « année » : on ignore tout texte ajouté après l'année dans la cellule
    annees = {}
    for j, cellule in enumerate(entete):
        if j == 0:
            continue
        a = annee_scolaire(cellule)
        if a:
            annees[j] = a
            if isinstance(cellule, str) and len(cellule.strip()) > 12:
                anomalie(nom_feuille, ref, "en-tete_texte_parasite",
                         f"colonne {j + 1} : texte supplémentaire après l'année, seule l'année est conservée")
    if not annees:
        anomalie(nom_feuille, ref, "tableau_ignore", "aucune colonne d'année reconnue")
        return [], h + 1
    premiere = min(annees)

    # mise en page à colonnes G/F/T ?
    sous_entete = list(lignes[h + 1]) if h + 1 < len(lignes) else []
    triplets = any(cle(c) in {"G", "F", "T"} for c in sous_entete[premiere:] if c is not None)
    colonnes = {}  # indice de colonne -> (année, sexe ou None)
    if triplets:
        courante = None
        for j in range(premiere, len(sous_entete)):
            if j in annees:
                courante = annees[j]
            s = sous_entete[j]
            if courante and s is not None and cle(s) in SEXES:
                colonnes[j] = (courante, SEXES[cle(s)])
        depart = h + 2
    else:
        colonnes = {j: (a, None) for j, a in annees.items()}
        depart = h + 1

    nb_dims = premiere
    entetes_dims = [entete[j] for j in range(nb_dims)]

    # lecture des lignes avec report des libellés de cellules fusionnées
    brutes = []
    dernier = [None] * nb_dims
    i = depart
    while i < len(lignes):
        ligne = list(lignes[i]) + [None] * max(0, len(entete) - len(lignes[i]))
        if ligne_vide(ligne):
            break
        if isinstance(ligne[0], str) and cle(ligne[0]).startswith("TABLEAU"):
            break
        if any(isinstance(c, str) and len(c) > 150 for c in ligne):
            anomalie(nom_feuille, ref, "cellule_texte_long_ignoree", f"ligne {i + 1}")
            i += 1
            continue
        for j in range(nb_dims):
            if ligne[j] is not None and str(ligne[j]).strip() != "":
                dernier[j] = ligne[j]
                for k in range(j + 1, nb_dims):
                    if ligne[k] is None:
                        dernier[k] = None
        dims = list(dernier)
        valeurs = {j: nombre(ligne[j]) if j < len(ligne) else None for j in colonnes}
        if all(v is None for v in valeurs.values()):
            anomalie(nom_feuille, ref, "ligne_sans_valeur", f"ligne {i + 1} : {dims}")
            i += 1
            continue
        brutes.append((i + 1, dims, valeurs))
        i += 1

    # nature de chaque colonne de dimension, d'après les valeurs
    natures = []
    for j in range(nb_dims):
        natures.append(type_dimension([b[1][j] for b in brutes], entetes_dims[j]))
    if any(n.startswith("autre") for n in natures):
        anomalie(nom_feuille, ref, "dimension_non_reconnue", f"{list(zip(entetes_dims, natures))}")
    for j, n in enumerate(natures):
        e = cle(entetes_dims[j]) if entetes_dims[j] else ""
        attendu = {"REGION": "region", "REGIONS": "region", "STATUT": "statut", "MILIEU": "milieu",
                   "NIVEAU": "classe", "SEXE": "sexe"}.get(e)
        if attendu and attendu != n:
            anomalie(nom_feuille, ref, "en-tete_trompeur",
                     f"colonne « {entetes_dims[j]} » contient en réalité des valeurs de type {n}")

    enregistrements = []
    for num_ligne, dims, valeurs in brutes:
        rec = {d: None for d in DIMENSIONS}
        sexe_ligne = None
        totaux = []
        valide = True
        sous_total = False   # ligne « Total <libellé> » : total d'une catégorie précise
        for j, nature in enumerate(natures):
            v = dims[j]
            if nature == "sexe":
                sexe_ligne = SEXES.get(cle(v)) if v is not None else None
                continue
            if v is None:
                continue
            k_v = cle(v)
            if k_v.startswith("TOTAL ") and k_v not in {"TOTAL GENERAL"}:
                reste = k_v[len("TOTAL "):].strip()
                table_ref = {"statut": STATUTS, "milieu": MILIEUX, "classe": CLASSES}.get(nature)
                if nature == "region" and region_canonique(reste) in REGIONS_13:
                    rec["region"] = region_canonique(reste)
                    sous_total = True
                    continue
                if table_ref and reste in table_ref:
                    rec[nature] = table_ref[reste]
                    sous_total = True
                    continue
            if nature == "region":
                r = region_canonique(v)
                if r == "NATIONAL" or (r is None and est_libelle_total(v)):
                    rec["region"] = TOTAL
                    totaux.append("region")
                elif r is None:
                    anomalie(nom_feuille, ref, "region_inconnue", f"ligne {num_ligne} : « {v} »")
                    valide = False
                else:
                    rec["region"] = r
            elif nature in ("statut", "milieu", "classe"):
                table = {"statut": STATUTS, "milieu": MILIEUX, "classe": CLASSES}[nature]
                k = cle(v)
                if est_libelle_total(v):
                    rec[nature] = TOTAL
                    totaux.append(nature)
                elif k in table:
                    rec[nature] = table[k]
                else:
                    anomalie(nom_feuille, ref, f"{nature}_inconnu", f"ligne {num_ligne} : « {v} »")
                    valide = False
            else:
                rec[nature] = str(v).strip()
        if not valide:
            continue
        if sous_total or totaux:
            # sur une ligne de total, les autres dimensions du tableau laissées vides sont totalisées
            for nature in natures:
                if nature in DIMENSIONS and rec[nature] is None:
                    rec[nature] = TOTAL
                    totaux.append(nature)
        for j, (annee, sexe_col) in colonnes.items():
            v = valeurs.get(j)
            if v is None:
                continue
            if v == "NON_NUMERIQUE":
                anomalie(nom_feuille, ref, "valeur_non_numerique", f"ligne {num_ligne}, colonne {j + 1}")
                continue
            sexe = sexe_col or sexe_ligne or "T"
            enregistrements.append({
                "source_feuille": nom_feuille, "source_tableau": num, "cycle": cycle,
                "indicateur": indicateur, **rec, "sexe": sexe, "annee_scolaire": annee,
                "valeur": v, "dims_totalisees": "+".join(totaux),
                "ligne_source": num_ligne,
            })
    note(f"- {ref} : « {titre[:110]} » → indicateur `{indicateur}`, {len(enregistrements)} valeurs, "
         f"{'colonnes G/F/T' if triplets else 'colonne sexe ou sans sexe'}, dimensions {natures}")
    return enregistrements, i


def lire_classeur(chemin):
    wb = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
    tout = []
    for ws in wb.worksheets:
        lignes = [tuple(r) for r in ws.iter_rows(values_only=True)]
        i = 0
        trouves = 0
        while i < len(lignes):
            premiere = lignes[i][0] if lignes[i] else None
            if isinstance(premiere, str) and cle(premiere).startswith("TABLEAU"):
                recs, i = lire_tableau(lignes, i, ws.title)
                tout.extend(recs)
                trouves += 1
            else:
                i += 1
        if trouves == 0:
            anomalie(ws.title, "-", "feuille_sans_tableau", "aucun tableau détecté")
    return pd.DataFrame(tout)


# ---------------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------------
def controles(df):
    resultats = []
    base = df[df["indicateur"].isin(INDICATEURS_COMPTAGE)].copy()
    cles_communes = ["source_feuille", "source_tableau", "indicateur", "annee_scolaire"]

    # 1. Garçons + filles = total
    pivot = base.pivot_table(index=cles_communes + DIMENSIONS, columns="sexe", values="valeur",
                             aggfunc="sum", dropna=False).reset_index()
    if {"G", "F", "T"} <= set(pivot.columns):
        p = pivot.dropna(subset=["G", "F", "T"])
        p = p.assign(ecart=(p["G"] + p["F"] - p["T"]))
        ko = p[p["ecart"].abs() > 0.5]
        resultats.append(("G + F = T", len(p), len(ko)))
        for _, r in ko.head(200).iterrows():
            anomalie(r["source_feuille"], r["source_tableau"], "controle_sexe",
                     f"{r['annee_scolaire']} {[r[d] for d in DIMENSIONS if pd.notna(r[d])]} : "
                     f"G+F={r['G'] + r['F']:.0f} ≠ T={r['T']:.0f}")

    # 2. Somme des détails = ligne de total, dimension par dimension
    for dim in DIMENSIONS:
        autres = [d for d in DIMENSIONS if d != dim]
        tot = base[base[dim] == TOTAL]
        det = base[base[dim].notna() & (base[dim] != TOTAL)]
        if tot.empty or det.empty:
            continue
        cle_g = cles_communes + ["sexe"] + autres
        somme = det.fillna({d: "-" for d in autres}).groupby(cle_g)["valeur"].sum().rename("somme_details")
        t = tot.fillna({d: "-" for d in autres}).set_index(cle_g)["valeur"].rename("total_fichier")
        comp = pd.concat([somme, t], axis=1, join="inner").reset_index()
        comp["ecart"] = comp["somme_details"] - comp["total_fichier"]
        ko = comp[comp["ecart"].abs() > 0.5]
        resultats.append((f"somme des {dim}s = total", len(comp), len(ko)))
        for _, r in ko.head(200).iterrows():
            anomalie(r["source_feuille"], r["source_tableau"], f"controle_total_{dim}",
                     f"{r['annee_scolaire']} sexe {r['sexe']} : somme {r['somme_details']:.0f} "
                     f"≠ total {r['total_fichier']:.0f} (écart {r['ecart']:+.0f})")

    # 3. Valeurs hors plage pour les taux et indices
    plages = {"tba": (0, 250), "tbs": (0, 250), "tbps": (0, 100), "taux_achevement": (0, 250),
              "taux_reussite_cep": (0, 100), "ips_tba": (0.3, 2), "ips_tbs": (0.3, 2),
              "ips_tap": (0.3, 2), "ips": (0.3, 2)}
    for ind, (bas, haut) in plages.items():
        sous = df[df["indicateur"] == ind]
        ko = sous[(sous["valeur"] < bas) | (sous["valeur"] > haut)]
        if len(sous):
            resultats.append((f"{ind} dans [{bas} ; {haut}]", len(sous), len(ko)))
        for _, r in ko.iterrows():
            anomalie(r["source_feuille"], r["source_tableau"], "valeur_hors_plage",
                     f"{ind} {r['region']} {r['sexe']} {r['annee_scolaire']} = {r['valeur']:.2f}")

    # 4. Ruptures fortes d'une année à l'autre (information, pas une erreur)
    det = base[base["dims_totalisees"] == ""].sort_values("annee_scolaire")
    grp = det.groupby(["source_tableau", "indicateur"] + [d for d in DIMENSIONS] + ["sexe"], dropna=False)
    n_rupt = 0
    for keys, g in grp:
        g = g.sort_values("annee_scolaire")
        var = g["valeur"].pct_change()
        for (_, r), v in zip(g.iterrows(), var):
            if pd.notna(v) and abs(v) >= 0.30 and r["sexe"] == "T":
                n_rupt += 1
                anomalie(r["source_feuille"], r["source_tableau"], "rupture_forte_info",
                         f"{r['indicateur']} {r['region'] or ''} {r['statut'] or ''} {r['milieu'] or ''} "
                         f"{r['annee_scolaire']} : {v:+.0%} par rapport à l'année précédente")
    resultats.append(("ruptures ≥ 30 % signalées (information)", len(det), n_rupt))
    return resultats


# ---------------------------------------------------------------------------
def principal(chemin):
    note(f"# Journal de nettoyage — fichier DGESS préscolaire et primaire 2016-2025")
    note(f"Exécuté le {datetime.now():%d/%m/%Y à %H:%M}. Fichier source : `{chemin.name}`\n")
    note("## Tableaux lus")
    df = lire_classeur(chemin)
    if df.empty:
        raise SystemExit("Aucune donnée lue : vérifiez le chemin du fichier.")

    # doublons exacts
    avant = len(df)
    df = df.drop_duplicates(subset=["source_tableau", "source_feuille", "indicateur", *DIMENSIONS,
                                    "sexe", "annee_scolaire"])
    if avant != len(df):
        note(f"\n{avant - len(df)} doublons exacts supprimés.")

    df["niveau_geo"] = df["region"].map(lambda r: "regional" if r in REGIONS_13 else "national")
    detail = df[df["dims_totalisees"] == ""].copy()
    totaux = df[df["dims_totalisees"] != ""].copy()

    note("\n## Contrôles")
    note("| Contrôle | Comparaisons | Écarts |\n|---|---|---|")
    for nom, n, ko in controles(df):
        note(f"| {nom} | {n} | {ko} |")

    note("\n## Règles appliquées")
    note("- Format long : une ligne par indicateur, catégorie, sexe et année scolaire.")
    note("- Années notées `AAAA-AAAA` (année scolaire). Une année seule (ex. 2016) est lue comme "
         "l'année de fin : 2016 → 2015-2016 ; pour le CEP, c'est la session de fin d'année.")
    note("- Régions : 13 anciennes régions, libellés harmonisés (ex. HAUT-BASSINS → HAUTS-BASSINS). "
         "« NATIONAL », « Burkina Faso » et « Total général » sont traités comme des totaux.")
    note("- Sexe : G (garçons), F (filles), T (total).")
    note("- Les lignes de total sont retirées des données détaillées et conservées à part "
         "pour les contrôles.")
    note("- La nature de chaque colonne est déduite de ses valeurs, et non de son en-tête "
         "(un en-tête « REGION » contenant Urbain/Rural est reclassé en milieu).")
    note("- Seule l'année est conservée dans les en-têtes contenant du texte supplémentaire.")

    note(f"\n## Résultat\n- {len(detail)} valeurs détaillées, {len(totaux)} valeurs de total.")
    note(f"- {len(anomalies)} remarques consignées dans le fichier des anomalies.")
    resume = pd.DataFrame(anomalies).groupby("nature").size() if anomalies else pd.Series(dtype=int)
    for nature, n in resume.items():
        note(f"  - {nature} : {n}")

    colonnes = ["cycle", "indicateur", "region", "statut", "milieu", "classe", "sexe",
                "annee_scolaire", "valeur", "niveau_geo", "source_feuille", "source_tableau",
                "ligne_source"]
    sorties = {
        "detail": config.nom_fichier("nettoyage", "engineer", "dgess-prescolaire-primaire-propres"),
        "totaux": config.nom_fichier("nettoyage", "engineer", "dgess-lignes-total-controle"),
        "anomalies": config.nom_fichier("nettoyage", "engineer", "dgess-anomalies"),
        "journal": config.nom_fichier("nettoyage", "engineer", "journal-nettoyage-dgess", ext="md"),
    }
    config.DOSSIERS["nettoyage"].mkdir(parents=True, exist_ok=True)
    detail[colonnes].sort_values(["indicateur", "cycle", "region", "annee_scolaire"]).to_csv(
        sorties["detail"], index=False, encoding="utf-8")
    totaux[colonnes + ["dims_totalisees"]].to_csv(sorties["totaux"], index=False, encoding="utf-8")
    pd.DataFrame(anomalies, columns=["feuille", "tableau", "nature", "detail"]).to_csv(
        sorties["anomalies"], index=False, encoding="utf-8")
    sorties["journal"].write_text("\n".join(journal), encoding="utf-8")
    print("\n".join(journal[-12:]))
    print("\nFichiers écrits :")
    for p in sorties.values():
        print(" -", p.relative_to(config.RACINE))


if __name__ == "__main__":
    chemin = config.Path(sys.argv[1]) if len(sys.argv) > 1 else config.FICHIER_DGESS
    principal(chemin)
