"""Étape 4b : trois compléments à l'analyse de l'étape 4.

1. Redéploiement : combien d'enseignants peut-on déplacer, sans recruter, des provinces les mieux dotées
   vers les provinces en déficit ? Les provinces donneuses gardent au plus `seuil` élèves par maître
   à l'horizon (effectifs du scénario tendanciel), pour ne pas créer de nouveau déficit.
2. Robustesse de l'indice de priorité : les 8 critères ont le même poids. On tire 10 000 pondérations au hasard
   (loi de Dirichlet uniforme : toutes les pondérations positives de somme 1 sont également probables) et on
   mesure, pour chaque province, la part des tirages où elle reste dans les 10 premières.
3. Découpage administratif de 2025 (17 régions, 47 provinces) : les résultats par ancienne province sont
   reportés sur les nouvelles. Seules deux anciennes provinces ont été coupées (Soum et Tapoa) : leurs valeurs
   sont réparties au prorata de la superficie, faute de population par nouvelle province.

Entrées : sorties des étapes 3b et 4.   Sorties : data/04_analyse
Lancement :  python src/etape04b_redeploiement_robustesse_decoupage.py
"""
from datetime import datetime

import numpy as np
import pandas as pd

import config
from etape04_besoins_allocation import COMPOSANTES, PARAMS, allouer_optimise, lire

SEUILS_REDEPLOIEMENT = (50, 55)   # élèves par maître que les provinces donneuses gardent au plus (norme nationale : 50)
SEUIL_REFERENCE = 50
TIRAGES = 10_000
GRAINE = 2026


def donneurs(eleves, maitres, seuil):
    """Enseignants en surplus : au-delà de ce qu'il faut pour rester à `seuil` élèves par maître."""
    return (maitres - np.ceil(eleves / seuil)).clip(lower=0)


def redeploiement(b):
    a = PARAMS["annee_cible"]
    el, m = b[f"eleves_{a}_tendanciel"], b.maitres
    deficit = b[f"deficit_maitres_{a}_tendanciel"].sum()
    poids = 1 + PARAMS["poids_equite"] * b.indice_priorite / 100
    lignes, j = [], ["", "## 1. Redéploiement des enseignants avant recrutement",
                     f"Effectifs {a} du scénario tendanciel. Une province donne ses maîtres en surplus tant qu'elle reste "
                     f"sous le seuil indiqué ; les maîtres libérés vont aux provinces en déficit selon la méthode optimisée "
                     f"(les donneuses ne reçoivent rien).", "",
                     "| Seuil des donneuses | Enseignants redéployables | Provinces donneuses | Part du déficit national couverte |",
                     "|---|---|---|---|"]
    for seuil in SEUILS_REDEPLOIEMENT:
        sur = donneurs(el, m, seuil)
        pool = int(sur.sum())
        p_don = poids.where(sur == 0, 0.0)
        recu = allouer_optimise(el, m - sur, p_don, pool, PARAMS["rem_cible"], 1) if pool else pd.Series(0, index=b.index)
        j.append(f"| {seuil} élèves par maître | {pool:_} | {int((sur > 0).sum())} | {pool / deficit * 100:.1f} % |".replace("_", " ").replace(".", ","))
        for p in b.index:
            lignes.append({"seuil_donneuses": seuil, "province": p, "region": b.region[p], "maitres_2024": m[p],
                           "eleves_2030_tendanciel": el[p], "enseignants_donnes": int(sur[p]), "enseignants_recus": int(recu[p]),
                           "ratio_avant": round(el[p] / m[p], 1),
                           "ratio_apres": round(el[p] / (m[p] - sur[p] + recu[p]), 1)})
    d = pd.DataFrame(lignes)
    ref = d[d.seuil_donneuses == SEUIL_REFERENCE]
    j += ["", f"Avec le seuil de {SEUIL_REFERENCE} : donneuses — "
          + ", ".join(f"{r.province} ({r.enseignants_donnes})" for r in ref[ref.enseignants_donnes > 0].sort_values("enseignants_donnes", ascending=False).itertuples())
          + " ; principales bénéficiaires — "
          + ", ".join(f"{r.province} (+{r.enseignants_recus})" for r in ref[ref.enseignants_recus > 0].sort_values("enseignants_recus", ascending=False).head(5).itertuples()) + ".",
          "", f"Conclusion : le déficit est général. Le redéploiement est gratuit et doit venir en premier, mais il ne couvre "
          f"qu'une petite part du besoin : le recrutement reste indispensable."]
    return d, j


def robustesse(b):
    z = np.column_stack([b[f"score_{c}"].to_numpy() / 100 for c in COMPOSANTES])     # 45 x 8
    rng = np.random.default_rng(GRAINE)
    w = rng.dirichlet(np.ones(len(COMPOSANTES)), TIRAGES)                              # tirages x 8
    rangs = (-(z @ w.T)).argsort(axis=0).argsort(axis=0) + 1                            # 45 x tirages
    r = pd.DataFrame({"province": b.index, "region": b.region.values, "rang_poids_egaux": b.rang_priorite.values,
                      "part_tirages_top10": (rangs <= 10).mean(axis=1).round(3),
                      "rang_median": np.median(rangs, axis=1),
                      "rang_p05": np.percentile(rangs, 5, axis=1), "rang_p95": np.percentile(rangs, 95, axis=1)})
    r = r.sort_values(["part_tirages_top10", "rang_median"], ascending=[False, True])
    noyau = r[r.part_tirages_top10 >= 0.9].province.tolist()
    top10 = set(b.sort_values("indice_priorite", ascending=False).head(10).index)
    j = ["", "## 2. Robustesse de l'indice de priorité",
         f"{TIRAGES:_} pondérations tirées au hasard (loi de Dirichlet uniforme sur les {len(COMPOSANTES)} critères, graine {GRAINE}). "
         f"Pour chaque province : part des tirages où elle est dans les 10 premières, et rang entre le 5e et le 95e centile.".replace("_", " "), "",
         "| Province | Rang (poids égaux) | Dans le top 10 | Rang médian | Rang (5 %-95 %) |", "|---|---|---|---|---|"]
    for x in r.head(15).itertuples():
        j.append(f"| {x.province} | {x.rang_poids_egaux} | {x.part_tirages_top10:.0%} | {x.rang_median:.0f} | {x.rang_p05:.0f}-{x.rang_p95:.0f} |")
    j += ["", f"Noyau dur (dans le top 10 dans au moins 90 % des tirages) : {', '.join(noyau) or 'aucune'}.",
          f"Provinces du top 10 (poids égaux) présentes dans le top 10 dans au moins la moitié des tirages : "
          f"{sum(r.set_index('province').loc[list(top10), 'part_tirages_top10'] >= 0.5)} sur 10.",
          "Conclusion : le choix des poids change l'ordre à l'intérieur du groupe de tête, pas sa composition."]
    return r, j


def decoupage_2025(b):
    a = PARAMS["annee_cible"]
    c = lire("*correspondance-provinces-2025*.csv", "transformation")
    c["part"] = c.superficie_km2 / c.groupby("province").superficie_km2.transform("sum")
    sommes = ["eleves_2024", "maitres", "salles", "salles_durables", "ecoles", "edi_primaire_T",
              f"eleves_{a}_tendanciel", f"deficit_maitres_{a}_tendanciel", f"deficit_salles_{a}_tendanciel",
              "alloc_enseignants_tendanciel", "alloc_salles_tendanciel"]
    d = c.merge(b[sommes + ["indice_priorite", "rang_priorite", "tbs_2024", "rem_2024"]], left_on="province", right_index=True)
    for col in sommes:
        d[col] = (d[col] * d.part).round(0)
    d = d.rename(columns={"province": "ancienne_province", "region": "ancienne_region"})
    prov = d[["region_2025", "province_2025", "pcode_2025", "ancienne_province", "ancienne_region", "part"] + sommes
             + ["indice_priorite", "rang_priorite", "tbs_2024", "rem_2024"]].sort_values(["region_2025", "province_2025"])
    reg = d.groupby("region_2025")[sommes].sum()
    reg["eleves_par_maitre_2024"] = (reg.eleves_2024 / reg.maitres).round(1)
    reg["indice_priorite_moyen"] = d.groupby("region_2025").apply(
        lambda g: np.average(g.indice_priorite, weights=g.eleves_2024), include_groups=False).round(1)
    reg["provinces"] = d.groupby("region_2025").province_2025.apply(lambda s: ", ".join(sorted(s)))
    reg = reg.sort_values("indice_priorite_moyen", ascending=False).reset_index()
    j = ["", "## 3. Résultats dans le découpage de 2025 (17 régions, 47 provinces)",
         "Les 45 anciennes provinces correspondent chacune à une nouvelle, sauf le Soum (Djelgodji, Karo-Peli) et la Tapoa "
         "(Dyamongou, Gobnangou), réparties au prorata de la superficie. Ratios et indice : ceux de l'ancienne province.", "",
         f"| Région 2025 | Élèves 2024-2025 | Élèves par maître | Indice moyen | Déficit maîtres {a} | Enseignants attribués | Salles attribuées |",
         "|---|---|---|---|---|---|---|"]
    for x in reg.itertuples():
        j.append(f"| {x.region_2025} | {x.eleves_2024:_.0f} | {x.eleves_par_maitre_2024:.1f} | {x.indice_priorite_moyen:.0f} | "
                 f"{getattr(x, f'deficit_maitres_{a}_tendanciel'):_.0f} | {x.alloc_enseignants_tendanciel:_.0f} | {x.alloc_salles_tendanciel:_.0f} |".replace("_", " "))
    j.append("")
    j.append("Indice moyen : moyenne des indices provinciaux pondérée par les élèves de 2024-2025.")
    return prov, reg, j


def principal():
    b = lire("*besoins-2030-priorites-province*.csv", "analyse").set_index("province")
    j = [f"# Journal de l'étape 4b — redéploiement, robustesse, découpage 2025", f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}"]
    red, j1 = redeploiement(b)
    rob, j2 = robustesse(b)
    prov, reg, j3 = decoupage_2025(b)
    j += j1 + j2 + j3
    sorties = [(red, "redeploiement-enseignants"), (rob, "robustesse-indice-priorite"),
               (prov, "resultats-provinces-2025"), (reg, "resultats-regions-2025")]
    for d, nom in sorties:
        d.to_csv(config.nom_fichier("analyse", "scientist", nom), index=False, encoding="utf-8")
    config.nom_fichier("analyse", "scientist", "journal-redeploiement-robustesse-decoupage", ext="md").write_text("\n".join(j), encoding="utf-8")
    print("\n".join(j))


if __name__ == "__main__":
    principal()
