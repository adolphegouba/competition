# NeuralFaso_02-nettoyage_D3_engineer_extraction-annuaires_v1.py
# Nom d'origine dans le projet : src/etape02b_extraction_annuaires.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 2b : extraction des tableaux utiles au Défi 3 dans les annuaires DGESS du primaire.

Source : CSV du Data Pack (PDF convertis : document ; page ; ligne ; nb_cellules ; c1 ... cN),
placés dans data/01_collecte/annuaires/.

Tableaux extraits, par province et par statut (numéros de l'annuaire 2024-2025) :
  - I.1   écoles, salles de classe, groupes pédagogiques, maîtres, élèves, ratio élèves/maître
  - V.5   pourcentage d'élèves selon la distance parcourue (< 3 km, 3-5 km, > 5 km)
  - VI.4.1 nature et état des murs des salles de classe (dur, semi-dur, paille/banco ; bon, mauvais)
La numérotation change d'une édition à l'autre (en 2017-2018 : II.1, VI.5 et VII.4.1, et le I.1 ne porte
que sur les 43 communes prioritaires) : chaque tableau est donc repéré par son titre, pas par son numéro.

Lancement :  python src/etape02b_extraction_annuaires.py
"""
import csv
import re
from datetime import datetime

import pandas as pd

import config
from referentiels import cle

csv.field_size_limit(10_000_000)

# 45 provinces de l'ancien découpage, rattachées aux 13 anciennes régions
PROVINCES = {
    "BOUCLE DU MOUHOUN": ["BALE", "BANWA", "KOSSI", "MOUHOUN", "NAYALA", "SOUROU"],
    "CASCADES": ["COMOE", "LERABA"],
    "CENTRE": ["KADIOGO"],
    "CENTRE-EST": ["BOULGOU", "KOULPELOGO", "KOURITTENGA"],
    "CENTRE-NORD": ["BAM", "NAMENTENGA", "SANMATENGA"],
    "CENTRE-OUEST": ["BOULKIEMDE", "SANGUIE", "SISSILI", "ZIRO"],
    "CENTRE-SUD": ["BAZEGA", "NAHOURI", "ZOUNDWEOGO"],
    "EST": ["GNAGNA", "GOURMA", "KOMANDJARI", "KOMPIENGA", "TAPOA"],
    "HAUTS-BASSINS": ["HOUET", "KENEDOUGOU", "TUY"],
    "NORD": ["LOROUM", "PASSORE", "YATENGA", "ZONDOMA"],
    "PLATEAU CENTRAL": ["GANZOURGOU", "KOURWEOGO", "OUBRITENGA"],
    "SAHEL": ["OUDALAN", "SENO", "SOUM", "YAGHA"],
    "SUD-OUEST": ["BOUGOURIBA", "IOBA", "NOUMBIEL", "PONI"],
}
REGION_DE = {p: r for r, ps in PROVINCES.items() for p in ps}
VARIANTES_PROV = {"LES BALE": "BALE", "KOURITENGA": "KOURITTENGA", "HOUËT": "HOUET",
                  "KOMONDJARI": "KOMANDJARI", "SANMATENGA ": "SANMATENGA"}
REGIONS = set(PROVINCES) | {"HAUT-BASSINS", "PLATEAU-CENTRAL"}
STATUTS = {"PUBLIC": "Public", "PRIVE": "Prive", "TOTAL": "Total"}

anomalies = []


def nombre(texte):
    t = str(texte).replace("\xa0", "").replace(" ", "").replace("%", "").replace(",", ".")
    if t in {"", "-"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def province(texte):
    k = cle(texte)
    k = VARIANTES_PROV.get(k, k)
    return k if k in REGION_DE else None


def region(texte):
    k = cle(texte).replace("HAUT-BASSINS", "HAUTS-BASSINS").replace("PLATEAU-CENTRAL", "PLATEAU CENTRAL")
    return k if k in PROVINCES else None


def lire_csv(chemin):
    lignes = []
    with open(chemin, encoding="utf-8-sig", newline="") as f:
        lecteur = csv.reader(f, delimiter=";")
        next(lecteur, None)
        for r in lecteur:
            if len(r) < 5:
                continue
            cellules = [c.strip() for c in r[4:] if c and c.strip()]
            cellules = [c for c in cellules if len(c) < 200]   # écarte les cellules de texte libre très longues
            if cellules:
                lignes.append((int(r[1]), int(r[2]), cellules))
    return lignes


def annee_document(lignes, nom):
    for _, _, c in lignes[:80]:
        m = re.search(r"(20\d\d)\s*[/-]\s*(20\d\d)", " ".join(c))
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"(20\d\d)_(20\d\d)", nom)
    return f"{m.group(1)}-{m.group(2)}" if m else "inconnue"


def pages_du_tableau(lignes, motif):
    """Pages dont l'en-tête contient le motif (titre du tableau répété en haut de page)."""
    pages = set()
    for page, num, c in lignes:
        if num <= 6 and re.search(motif, cle(" ".join(c))):
            pages.add(page)
    return sorted(pages)


def sous_section(texte):
    k = cle(texte)
    if re.search(r"PUBLIC\s*\+\s*PRIV", k) or "URBAIN+ RURAL" in k:
        return "Public+Prive"
    for mot, lab in (("PUBLIC", "Public"), ("PRIVE", "Prive"), ("URBAIN", "Urbain"), ("RURAL", "Rural")):
        if re.search(rf"^[IVX\. \d]+\s*{mot}\b", k):
            return lab
    return None


# ---------------------------------------------------------------------------
def extraire_i1(lignes, annee, doc):
    """I.1 : écoles, salles, groupes pédagogiques, maîtres, élèves, ratio — par province et statut."""
    res = []
    # titre complet : exclut le tableau des « 43 communes prioritaires » (… SALLES DE CLASSE SOUS-PAILLOTE …)
    pages = pages_du_tableau(lignes, r"^[IVX]+\.\d+ NOMBRE D'ECOLES, DE SALLES DE CLASSE, D'ELEVES")
    reg = prov = None
    for page, num, c in lignes:
        if page not in pages or num <= 4:
            continue
        if len(c) == 1 and region(c[0]):
            reg, prov = region(c[0]), None
            continue
        tete = cle(c[0])
        if province(c[0]) or tete.startswith("TOTAL REGION") or tete.startswith("TOTAL NATIONAL") or tete == "BURKINA FASO":
            if province(c[0]):
                prov = province(c[0])
                reg = REGION_DE[prov]
            else:
                prov = "_TOTAL_REGION_" if "REGION" in tete else "_TOTAL_NATIONAL_"
            c = c[1:]
        if not c or cle(c[0]) not in STATUTS:
            continue
        valeurs = [nombre(x) for x in c[1:]]
        if len(valeurs) < 6 or any(v is None for v in valeurs[:6]):
            anomalies.append({"annee": annee, "tableau": "I.1", "page": page, "ligne": num, "probleme": "ligne incomplète", "contenu": " | ".join(c)[:120]})
            continue
        res.append({"annee_scolaire": annee, "region": reg, "province": prov, "statut": STATUTS[cle(c[0])],
                    "nb_ecoles": valeurs[0], "nb_salles": valeurs[1], "nb_groupes_pedagogiques": valeurs[2],
                    "nb_maitres": valeurs[3], "nb_eleves": valeurs[4], "ratio_eleves_maitre_source": valeurs[5],
                    "source": f"{doc} p.{page}"})
    return pd.DataFrame(res)


def extraire_v5(lignes, annee, doc):
    """V.5 : % d'élèves selon la distance parcourue."""
    res = []
    pages = pages_du_tableau(lignes, r"^[IVX]+\.\d+ POURCENTAGE DES ELEVES SELON LA DISTANCE")
    sect = reg = None
    for page, num, c in lignes:
        if page not in pages:
            continue
        s = sous_section(c[0]) if len(c) <= 2 else None
        if s and re.match(r"^[IVX]+\.\d+\.\d", cle(c[0])):
            sect = s
            continue
        if len(c) == 1 and region(c[0]):
            reg = region(c[0])
            continue
        p = province(c[0])
        tete = cle(c[0])
        if not (p or tete.startswith("TOTAL REGION")) or len(c) < 5:
            continue
        v = [nombre(x) for x in c[1:5]]
        if any(x is None for x in v):
            continue
        res.append({"annee_scolaire": annee, "region": REGION_DE.get(p, reg), "province": p or "_TOTAL_REGION_",
                    "champ": sect, "pct_moins_3km": v[0], "pct_3_5km": v[1], "pct_plus_5km": v[2],
                    "nb_eleves": v[3], "source": f"{doc} p.{page}"})
    return pd.DataFrame(res)


def extraire_vi41(lignes, annee, doc):
    """VI.4.1 : nature et état des murs des salles de classe."""
    res = []
    pages = pages_du_tableau(lignes, r"^[IVX]+\.\d+\.\d+\.? NATURE ET ETAT DES MURS")
    # Le premier bloc n'a pas d'étiquette dans le PDF 2024-2025 ; d'après la table des matières,
    # l'ordre est VI.4.1.1 Public, VI.4.1.2 Privé, VI.4.1.3 Public + privé.
    sect, reg = "Public", None
    for page, num, c in lignes:
        if page not in pages:
            continue
        if len(c) <= 2 and re.match(r"^[IVX]+\.\d+\.\d+\.\d", cle(c[0])):
            sect = sous_section(c[0]) or sect
            continue
        if len(c) == 1 and region(c[0]):
            reg = region(c[0])
            continue
        p = province(c[0])
        tete = cle(c[0])
        if not (p or tete.startswith("TOTAL REGION")) or len(c) < 9:
            continue
        v = [nombre(x) for x in c[1:9]]
        if any(x is None for x in v):
            continue
        res.append({"annee_scolaire": annee, "region": REGION_DE.get(p, reg), "province": p or "_TOTAL_REGION_",
                    "champ": sect, "salles_murs_dur": v[0], "salles_murs_semi_dur": v[1],
                    "salles_murs_paille_banco": v[2], "salles_murs_indetermine": v[3],
                    "salles_etat_bon": v[4], "salles_etat_mauvais": v[5], "salles_etat_indetermine": v[6],
                    "nb_salles": v[7], "source": f"{doc} p.{page}"})
    return pd.DataFrame(res)


def controler(df, cles, valeurs, nom):
    """Somme des provinces = ligne « Total Région »."""
    if df.empty:
        return 0, 0
    det = df[~df["province"].str.startswith("_")]
    tot = df[df["province"] == "_TOTAL_REGION_"]
    s = det.groupby(cles)[valeurs].sum()
    t = tot.groupby(cles)[valeurs].sum()
    comp = s.merge(t, left_index=True, right_index=True, suffixes=("", "_total"))
    n_ko = 0
    for v in valeurs:
        ecart = (comp[v] - comp[v + "_total"]).abs()
        for idx in ecart[ecart > 0.5].index:
            n_ko += 1
            anomalies.append({"annee": idx[0], "tableau": nom, "page": "-", "ligne": "-", "probleme": "somme provinces ≠ total région",
                              "contenu": f"{idx} {v} : {comp.loc[idx, v]:.0f} vs {comp.loc[idx, v + '_total']:.0f}"})
    return len(comp) * len(valeurs), n_ko


def principal():
    dossier = config.DOSSIERS["collecte"] / "annuaires"
    fichiers = sorted(dossier.glob("*.csv"))
    if not fichiers:
        raise SystemExit(f"Aucun CSV d'annuaire dans {dossier}")
    i1, v5, vi = [], [], []
    journal = [f"# Journal d'extraction — annuaires du primaire (DGESS)", f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}", "",
               "| Fichier | Année | I.1 lignes | V.5 lignes | VI.4.1 lignes |", "|---|---|---|---|---|"]
    for f in fichiers:
        lignes = lire_csv(f)
        annee = annee_document(lignes, f.name)
        doc = f.stem.split("_")[0]
        a, b, c = extraire_i1(lignes, annee, doc), extraire_v5(lignes, annee, doc), extraire_vi41(lignes, annee, doc)
        i1.append(a); v5.append(b); vi.append(c)
        journal.append(f"| {f.name[:60]} | {annee} | {len(a)} | {len(b)} | {len(c)} |")
    i1 = pd.concat(i1, ignore_index=True)
    v5 = pd.concat(v5, ignore_index=True)
    vi = pd.concat(vi, ignore_index=True)

    journal += ["", "## Contrôles", "| Contrôle | Comparaisons | Écarts |", "|---|---|---|"]
    if not i1.empty:
        n, ko = controler(i1, ["annee_scolaire", "region", "statut"],
                          ["nb_ecoles", "nb_salles", "nb_groupes_pedagogiques", "nb_maitres", "nb_eleves"], "I.1")
        journal.append(f"| I.1 somme des provinces = total région | {n} | {ko} |")
        # public + privé = total
        d = i1.pivot_table(index=["annee_scolaire", "province"], columns="statut", values="nb_eleves", aggfunc="sum")
        if {"Public", "Prive", "Total"} <= set(d.columns):
            ecart = (d["Public"].fillna(0) + d["Prive"].fillna(0) - d["Total"]).abs()
            journal.append(f"| I.1 public + privé = total (élèves) | {len(d)} | {int((ecart > 0.5).sum())} |")
        # ratio recalculé
        i1["ratio_eleves_maitre"] = (i1["nb_eleves"] / i1["nb_maitres"]).round(2)
        i1["ratio_eleves_salle"] = (i1["nb_eleves"] / i1["nb_salles"]).round(2)
        i1["ratio_eleves_groupe"] = (i1["nb_eleves"] / i1["nb_groupes_pedagogiques"]).round(2)
        diff = (i1["ratio_eleves_maitre"] - i1["ratio_eleves_maitre_source"]).abs()
        journal.append(f"| I.1 ratio élèves/maître recalculé = publié (±0,1) | {len(i1)} | {int((diff > 0.1).sum())} |")
        nb_prov = i1.loc[~i1["province"].str.startswith("_"), "province"].nunique()
        journal.append(f"| I.1 provinces trouvées (attendu 45) | 45 | {45 - nb_prov} |")
    if not vi.empty:
        n, ko = controler(vi, ["annee_scolaire", "region", "champ"], ["salles_murs_paille_banco", "nb_salles"], "VI.4.1")
        journal.append(f"| VI.4.1 somme des provinces = total région | {n} | {ko} |")
    if not v5.empty:
        s = (v5["pct_moins_3km"] + v5["pct_3_5km"] + v5["pct_plus_5km"])
        journal.append(f"| V.5 pourcentages qui totalisent 100 (±0,2) | {len(v5)} | {int(((s - 100).abs() > 0.2).sum())} |")

    out = config.DOSSIERS["nettoyage"]
    out.mkdir(parents=True, exist_ok=True)
    sorties = [
        (i1, config.nom_fichier("nettoyage", "engineer", "annuaires-ecoles-salles-maitres-province")),
        (v5, config.nom_fichier("nettoyage", "engineer", "annuaires-distance-domicile-ecole-province")),
        (vi, config.nom_fichier("nettoyage", "engineer", "annuaires-etat-salles-province")),
        (pd.DataFrame(anomalies), config.nom_fichier("nettoyage", "engineer", "annuaires-anomalies")),
    ]
    for d, p in sorties:
        d.to_csv(p, index=False, encoding="utf-8")
    journal += ["", "Règles : nombres « 1 039 » et « 62,6 » convertis ; lignes « Total Région » gardées pour contrôle "
                "(province = _TOTAL_REGION_) ; ratios recalculés à partir des comptages ; province rattachée à son "
                "ancienne région (13 régions, 45 provinces).",
                "VI.4.1 : le premier bloc de pages n'a pas d'étiquette de statut dans le PDF ; il est classé « Public » "
                "d'après l'ordre de la table des matières (VI.4.1.1 Public, VI.4.1.2 Privé, VI.4.1.3 Public + privé)."]
    p = config.nom_fichier("nettoyage", "engineer", "journal-extraction-annuaires", ext="md")
    p.write_text("\n".join(journal), encoding="utf-8")
    print("\n".join(journal))


if __name__ == "__main__":
    principal()
