# NeuralFaso_02-nettoyage_D3_engineer_extraction-esu_v1.py
# Nom d'origine dans le projet : src/etape02d_extraction_esu.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 2d : extraction du rapport mensuel « Éducation en situation d'urgence » (ESU, DGESS).

Source : CSV du Data Pack du rapport de février 2026, placé dans data/01_collecte/esu/.
Annexes lues, par province (découpage de 2025 : 17 régions, 47 provinces) :
  - Annexe 1 : structures réouvertes (cumul), primaire
  - Annexe 2 : structures délocalisées (cumul), primaire
  - Annexe 4 : élèves déplacés internes (EDI) du primaire, par sexe
Chaque province de 2025 est rattachée à son ancienne province grâce à la table de correspondance
de l'étape 3b (COD-AB), puis les valeurs sont additionnées par ancienne province.

Lancement :  python src/etape02d_extraction_esu.py   (après l'étape 3b)
"""
import csv
import re
from datetime import datetime

import pandas as pd

import config
from etape02b_extraction_annuaires import nombre
from referentiels import cle

csv.field_size_limit(10_000_000)
VARIANTES_2025 = {"KOOSIN": "KOSSIN", "KOMONDJARI": "KOMANDJARI"}


def correspondance():
    f = sorted(config.DOSSIERS["transformation"].glob("*correspondance-provinces-2025*.csv"))
    if not f:
        raise SystemExit("Lancez d'abord src/etape03b_fond_de_carte.py (table de correspondance).")
    t = pd.read_csv(f[-1])
    return {cle(n): (p, r) for n, p, r in zip(t.province_2025, t.province, t.region)}


def principal():
    corr = correspondance()
    fichiers = sorted((config.DOSSIERS["collecte"] / "esu").glob("*.csv"))
    if not fichiers:
        raise SystemExit("Placez le CSV du rapport ESU dans data/01_collecte/esu/")
    lignes_out, non_reconnues = [], set()
    for src in fichiers:
        annexe = None
        with open(src, encoding="utf-8-sig", newline="") as f:
            lecteur = csv.reader(f, delimiter=";")
            next(lecteur, None)
            for r in lecteur:
                if len(r) < 5:
                    continue
                c = [x.strip() for x in r[4:] if x and x.strip() and len(x) < 200]
                if not c:
                    continue
                m = re.match(r"(?i)^annexe\s*(\d)", c[0])
                if m:
                    annexe = int(m.group(1))
                    continue
                if annexe not in (1, 2, 4):
                    continue
                # repérer la province : la première cellule reconnue dans la table de correspondance
                # la province est la dernière cellule texte avant les nombres (la région peut porter
                # le même nom qu'une province, ex. « KADIOGO | KADIOGO » ou « SOUROU | NAYALA »)
                prov = None
                textes = [x for x in c if nombre(x) is None]
                if textes:
                    k = VARIANTES_2025.get(cle(textes[-1]), cle(textes[-1]))
                    if k in corr:
                        prov = k
                vals = [x for x in c if nombre(x) is not None]
                if prov is None:
                    if not cle(c[0]).startswith(("TOTAL", "REGION")) and len(c) > 2:
                        non_reconnues.add(c[0])
                    continue
                v = [nombre(x) for x in vals]
                if annexe in (1, 2) and len(v) >= 3:
                    mesure, valeur = ("structures_reouvertes_primaire" if annexe == 1 else "structures_delocalisees_primaire"), v[2]
                    lignes_out.append({"province_2025": prov, "mesure": mesure, "valeur": valeur})
                elif annexe == 4 and len(v) >= 3:
                    for s, val in zip(("G", "F", "T"), v[:3]):
                        lignes_out.append({"province_2025": prov, "mesure": f"edi_primaire_{s}", "valeur": val})
        mois = re.search(r"(?i)(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)_?(20\d\d)", src.name)
    d = pd.DataFrame(lignes_out).drop_duplicates()
    d["province"] = d.province_2025.map(lambda k: corr[k][0])
    d["region"] = d.province_2025.map(lambda k: corr[k][1])
    d["source"] = f"Rapport ESU {mois.group(1) + ' ' + mois.group(2) if mois else ''}".strip()
    large = d.pivot_table(index=["province", "region"], columns="mesure", values="valeur", aggfunc="sum").reset_index()

    j = [f"# Journal d'extraction — rapport ESU", f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}. Source : {', '.join(f.name for f in fichiers)}", "",
         f"- Provinces de 2025 lues : {d.province_2025.nunique()} ; anciennes provinces couvertes : {large.province.nunique()} sur 45.",
         f"- Totaux : EDI du primaire = {large.get('edi_primaire_T', pd.Series(dtype=float)).sum():,.0f} "
         f"(publié : 436 683) ; structures réouvertes du primaire = {large.get('structures_reouvertes_primaire', pd.Series(dtype=float)).sum():,.0f} "
         f"(publié : 1 840) ; délocalisées = {large.get('structures_delocalisees_primaire', pd.Series(dtype=float)).sum():,.0f} (publié : 492).".replace(",", " "),
         f"- Libellés non reconnus : {sorted(non_reconnues) or 'aucun'}",
         "- Les provinces absentes d'une annexe n'ont aucune valeur déclarée : elles sont mises à 0 à l'étape 4.",
         "- Attention : ces données datent de février 2026 (année 2025-2026), l'annuaire de 2024-2025."]
    large.to_csv(config.nom_fichier("nettoyage", "engineer", "esu-deplaces-structures-province"), index=False, encoding="utf-8")
    config.nom_fichier("nettoyage", "engineer", "journal-esu", ext="md").write_text("\n".join(j), encoding="utf-8")
    print("\n".join(j))


if __name__ == "__main__":
    principal()
