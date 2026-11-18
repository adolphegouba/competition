# NeuralFaso_04-analyse_D3_scientist_besoins-priorites-allocation_v1.py
# Nom d'origine dans le projet : src/etape04_besoins_allocation.py (nom à garder pour relancer).
# Le projet complet, prêt à relancer, est dans NeuralFaso_D3_architect_projet-complet-a-relancer_v1.zip

"""Étape 4 : besoins en salles et en enseignants à l'horizon 2030, indice de priorité et allocation optimale.

Entrées (étape 2) : annuaire 2024-2025 par province (I.1, V.5, VI.4.1), projections INSD 2020-2035,
                    et le panel régional de l'étape 3 (indice de parité du TBS).
Sorties (data/04_analyse) :
  - besoins par province en 2030, selon deux scénarios de scolarisation ;
  - indice de priorité par province (0 à 100) et ses composantes ;
  - allocation d'un budget de salles et d'enseignants : méthode optimisée contre répartition au prorata.

Hypothèses (modifiables ci-dessous, toutes documentées dans le journal) :
  - norme de 50 élèves par maître : « norme nationale » rappelée par les tableaux de bord du primaire
    de la DGESS (2016-2017, 2023-2024) ; une norme « qualité » de 40 est calculée en sensibilité ;
  - même norme pour les salles (un groupe de 50 élèves par salle) ; `groupes_par_salle` règle la double vacation
    (1 = un groupe pédagogique par salle, cible du PSEF ; 2 = double flux généralisé).
    Le journal donne aussi le déficit de salles si la pratique observée en 2024-2025 se maintient ;
  - année scolaire 2024-2025 rapportée à la population 2024 : convention de la DGESS, vérifiée
    région par région dans le journal (écart nul avec 2024, plus de 2 points avec 2025) ;
  - scénario « rattrapage » : chaque province atteint au moins 100 % de TBS en 2030 ;
  - scénario « retour » : chaque province retrouve au moins son TBS d'avant la crise (2017-2018) ;
  - les salles en paille ou banco sont à remplacer et ne comptent pas comme capacité durable.

Lancement :  python src/etape04_besoins_allocation.py
"""
import heapq
from datetime import datetime

import numpy as np
import pandas as pd

import config

PARAMS = {
    "annee_base": "2024-2025",
    "annee_reference": "2017-2018",   # annuaire le plus ancien disponible, pour mesurer l'évolution
    "pop_base": 2024,
    "annee_cible": 2030,
    "rem_cible": 50,              # élèves par maître : norme nationale (tableaux de bord DGESS)
    "eleves_par_salle_cible": 50,
    "rem_qualite": 40,            # scénario « qualité » : 40 élèves par maître et par salle
    "groupes_par_salle": 1.0,     # 1 = sans double vacation ; >1 = une salle accueille plusieurs groupes
    "tbs_minimum_2030": 100.0,    # scénario rattrapage
    "budget_part_deficit": 0.5,   # budget simulé = 50 % du déficit national
    "poids_equite": 1.0,          # 0 = efficacité seule ; plus grand = priorité aux provinces défavorisées
    "pas_allocation": 5,          # unités allouées à chaque itération (le même pas que l'application)
}

COMPOSANTES = {
    "rem_2024": "Élèves par maître (2024-2025)",
    "eleves_par_salle_durable": "Élèves par salle durable (hors paille et banco)",
    "part_salles_precaires": "Part des salles en paille, banco ou en mauvais état",
    "part_eleves_plus_3km": "Part des élèves à plus de 3 km de l'école",
    "ecart_tbs_100": "Écart du TBS à 100 %",
    "croissance_pop_6_11": "Croissance des 6-11 ans de 2024 à 2030",
    "desavantage_filles": "Désavantage des filles (1 - indice de parité du TBS de la région)",
    "part_eleves_deplaces": "Élèves déplacés internes accueillis, rapportés aux élèves de 2024-2025 (ESU, février 2026)",
}

SCENARIOS = ("tendanciel", "rattrapage", "retour")

# seuils des types d'action recommandés (documentés dans le journal)
SEUILS = {"tbs_securite": 40, "part_deplaces": 0.10, "rem": 50, "eleves_par_salle": 50, "salles_precaires": 0.25}


def lire(motif, dossier="nettoyage"):
    f = sorted(config.DOSSIERS[dossier].glob(motif))
    if not f:
        raise SystemExit(f"Fichier introuvable : {motif} — lancez les étapes précédentes.")
    return pd.read_csv(f[-1])


def base_province():
    i1 = lire("*annuaires-ecoles-salles-maitres-province*.csv")
    i1 = i1[(i1.annee_scolaire == PARAMS["annee_base"]) & ~i1.province.str.startswith("_")]
    tot = i1[i1.statut == "Total"].set_index("province")
    pub = i1[i1.statut == "Public"].set_index("province")
    b = pd.DataFrame({
        "region": tot.region, "ecoles": tot.nb_ecoles, "salles": tot.nb_salles,
        "groupes_pedagogiques": tot.nb_groupes_pedagogiques, "maitres": tot.nb_maitres,
        "eleves_2024": tot.nb_eleves, "groupes_par_salle_2024": (tot.nb_groupes_pedagogiques / tot.nb_salles).round(3),
        "part_public": (pub.nb_eleves / tot.nb_eleves).round(3),
    })
    # évolution depuis l'annuaire de référence (si disponible) : écoles, élèves, maîtres
    tout = lire("*annuaires-ecoles-salles-maitres-province*.csv")
    ref = tout[(tout.annee_scolaire == PARAMS["annee_reference"]) & (tout.statut == "Total") & ~tout.province.str.startswith("_")].set_index("province")
    for c, nom in (("nb_ecoles", "ecoles"), ("nb_salles", "salles"), ("nb_maitres", "maitres"), ("nb_eleves", "eleves")):
        b[f"{nom}_ref"] = ref[c].reindex(b.index) if len(ref) else np.nan
        cur = b["eleves_2024"] if nom == "eleves" else b[nom]
        b[f"variation_{nom}_depuis_ref"] = (cur / b[f"{nom}_ref"] - 1).round(4)
    vi = lire("*annuaires-etat-salles-province*.csv")
    vi = vi[(vi.annee_scolaire == PARAMS["annee_base"]) & (vi.champ == "Public+Prive") & ~vi.province.str.startswith("_")].set_index("province")
    b["salles_paille_banco"] = vi.salles_murs_paille_banco
    b["salles_mauvais_etat"] = vi.salles_etat_mauvais
    v5 = lire("*annuaires-distance-domicile-ecole-province*.csv")
    v5 = v5[(v5.annee_scolaire == PARAMS["annee_base"]) & (v5.champ == "Public+Prive") & ~v5.province.str.startswith("_")].set_index("province")
    b["part_eleves_plus_3km"] = ((v5.pct_3_5km + v5.pct_plus_5km) / 100).round(4)
    b["part_eleves_plus_5km"] = (v5.pct_plus_5km / 100).round(4)

    pr = lire("*projections-population-2020-2035-province*.csv")
    pr = pr[(pr.niveau == "province") & (pr.groupe_age == "6-11")]
    for an in (2020, PARAMS["pop_base"], PARAMS["annee_cible"]):
        s = pr[pr.annee == an].pivot_table(index="entite", columns="sexe", values="population")
        b[f"pop_6_11_{an}"] = s["T"]
        b[f"pop_6_11_filles_{an}"] = s.get("F")

    # élèves déplacés internes et structures réouvertes ou délocalisées (étape 2d), si disponible
    try:
        esu = lire("*esu-deplaces-structures-province*.csv").set_index("province")
        for c in ("edi_primaire_T", "edi_primaire_F", "structures_reouvertes_primaire", "structures_delocalisees_primaire"):
            b[c] = esu.get(c).reindex(b.index).fillna(0) if c in esu else 0
    except SystemExit:
        for c in ("edi_primaire_T", "edi_primaire_F", "structures_reouvertes_primaire", "structures_delocalisees_primaire"):
            b[c] = 0

    # indice de parité du TBS de la région (étape 3), si disponible
    try:
        panel = lire("*panel-region-annee-ratios*.csv", "transformation")
        ips = panel[(panel.cycle == "primaire") & (panel.annee_scolaire == PARAMS["annee_base"])].set_index("region")["ips_tbs"]
        b["ips_tbs_region"] = b.region.map(ips)
    except SystemExit:
        b["ips_tbs_region"] = np.nan
    return b


def besoins(b):
    a = PARAMS["annee_cible"]
    b["tbs_2024"] = (b.eleves_2024 / b[f"pop_6_11_{PARAMS['pop_base']}"] * 100).round(1)
    b["croissance_pop_6_11"] = (b[f"pop_6_11_{a}"] / b[f"pop_6_11_{PARAMS['pop_base']}"] - 1).round(4)
    b["rem_2024"] = (b.eleves_2024 / b.maitres).round(1)
    b["salles_durables"] = b.salles - b.salles_paille_banco.fillna(0)
    b["eleves_par_salle_durable"] = (b.eleves_2024 / b.salles_durables).round(1)
    b["part_salles_precaires"] = ((b.salles_paille_banco.fillna(0) + b.salles_mauvais_etat.fillna(0)) / b.salles).clip(upper=1).round(4)
    b["ecart_tbs_100"] = (100 - b.tbs_2024).clip(lower=0)
    b["desavantage_filles"] = (1 - b.ips_tbs_region).clip(lower=0).fillna(0)
    b["part_eleves_deplaces"] = (b.edi_primaire_T / b.eleves_2024).round(4)

    b = avant_crise(b)
    tbs_scen = {"tendanciel": b.tbs_2024,
                "rattrapage": np.maximum(b.tbs_2024, PARAMS["tbs_minimum_2030"]),
                "retour": np.maximum(b.tbs_2024, b.tbs_ref.fillna(0))}
    for nom, tbs in tbs_scen.items():
        b[f"tbs_{a}_{nom}"] = tbs.round(1)
        el = (b[f"pop_6_11_{a}"] * tbs / 100).round(0)
        b[f"eleves_{a}_{nom}"] = el
        b[f"maitres_requis_{a}_{nom}"] = np.ceil(el / PARAMS["rem_cible"])
        b[f"salles_requises_{a}_{nom}"] = np.ceil(el / (PARAMS["eleves_par_salle_cible"] * PARAMS["groupes_par_salle"]))
        # sensibilité : la double vacation observée en 2024-2025 (au moins 1 groupe par salle) se maintient
        b[f"deficit_salles_{a}_{nom}_pratique_2024"] = (np.ceil(el / (PARAMS["eleves_par_salle_cible"]
                                                        * b.groupes_par_salle_2024.clip(lower=1))) - b.salles_durables).clip(lower=0)
        b[f"deficit_maitres_{a}_{nom}"] = (b[f"maitres_requis_{a}_{nom}"] - b.maitres).clip(lower=0)
        b[f"deficit_salles_{a}_{nom}"] = (b[f"salles_requises_{a}_{nom}"] - b.salles_durables).clip(lower=0)
    return b


def avant_crise(b):
    """TBS de l'année de référence (2017-2018) par province, pour le scénario « retour ».
    Les projections INSD commencent en 2020 : la population 6-11 ans de 2017 est déduite, pour chaque région,
    des effectifs et du TBS publiés par la DGESS (population = élèves / TBS), puis répartie entre les provinces
    selon leur part dans la population régionale des 6-11 ans en 2020."""
    b["pop_6_11_ref_estimee"] = np.nan
    b["tbs_ref"] = np.nan
    if b["eleves_ref"].isna().all():
        return b
    try:
        panel = lire("*panel-region-annee-ratios*.csv", "transformation")
    except SystemExit:
        return b
    p = panel[(panel.cycle == "primaire") & (panel.annee_scolaire == PARAMS["annee_reference"])].set_index("region")
    pop_region = p.effectif_T / p.tbs_T * 100
    part = b.pop_6_11_2020 / b.groupby("region").pop_6_11_2020.transform("sum")
    b["pop_6_11_ref_estimee"] = (b.region.map(pop_region) * part).round(0)
    b["tbs_ref"] = (b.eleves_ref / b.pop_6_11_ref_estimee * 100).round(1)
    return b


def scenario_retour(b):
    a = PARAMS["annee_cible"]
    if b["tbs_ref"].isna().all():
        return ["", "## Scénario « retour »", "Annuaire de référence absent : scénario non calculé."]
    d = b[f"eleves_{a}_retour"] - b[f"eleves_{a}_tendanciel"]
    j = ["", f"## Scénario « retour » : retrouver le TBS de {PARAMS['annee_reference']}",
         f"Hypothèse : si la sécurité revient, chaque province retrouve au moins son taux brut de scolarisation de "
         f"{PARAMS['annee_reference']}. La population de 6-11 ans de {PARAMS['annee_reference'][:4]} est estimée à partir "
         f"des effectifs et des TBS régionaux publiés par la DGESS (population = élèves / TBS), répartie entre provinces "
         f"selon leur part dans la population de 2020 (premières projections INSD).", "",
         f"Par rapport au scénario tendanciel, {d.sum():_.0f} élèves de plus en {a}, dans {int((d > 0).sum())} provinces. "
         f"Il faut alors {b[f'deficit_maitres_{a}_retour'].sum() - b[f'deficit_maitres_{a}_tendanciel'].sum():_.0f} enseignants "
         f"et {b[f'deficit_salles_{a}_retour'].sum() - b[f'deficit_salles_{a}_tendanciel'].sum():_.0f} salles de plus.".replace("_", " "), "",
         f"| Province | TBS {PARAMS['annee_reference']} | TBS {PARAMS['annee_base']} | Élèves de plus en {a} | Enseignants de plus | Salles de plus |",
         "|---|---|---|---|---|---|"]
    for p in d.sort_values(ascending=False).head(12).index:
        r = b.loc[p]
        j.append(f"| {p} | {r.tbs_ref:.0f} % | {r.tbs_2024:.0f} % | {d[p]:_.0f} | "
                 f"{r[f'deficit_maitres_{a}_retour'] - r[f'deficit_maitres_{a}_tendanciel']:_.0f} | "
                 f"{r[f'deficit_salles_{a}_retour'] - r[f'deficit_salles_{a}_tendanciel']:_.0f} |".replace("_", " "))
    j += ["", "Lecture : ce scénario chiffre ce que coûterait le retour à l'école des enfants qui l'ont quittée "
          "à cause de l'insécurité. Il sert à préparer la réouverture, pas à la remplacer."]
    return j


def indice_priorite(b):
    z = pd.DataFrame(index=b.index)
    for c in COMPOSANTES:
        v = b[c].astype(float)
        z[c] = 0.0 if v.max() == v.min() else (v - v.min()) / (v.max() - v.min())
    b["indice_priorite"] = (z.mean(axis=1) * 100).round(1)
    b["rang_priorite"] = b.indice_priorite.rank(ascending=False, method="min").astype(int)
    for c in COMPOSANTES:
        b[f"score_{c}"] = (z[c] * 100).round(1)
    return b


def types_action(b):
    """Recommandation lisible par un décideur : une province peut en cumuler plusieurs."""
    def actions(r):
        a = []
        if r.tbs_2024 < SEUILS["tbs_securite"]:
            a.append("Rouvrir et sécuriser les écoles")
        if r.part_eleves_deplaces >= SEUILS["part_deplaces"]:
            a.append("Renforcer l'accueil des élèves déplacés")
        if r.rem_2024 > SEUILS["rem"]:
            a.append("Recruter et affecter des enseignants")
        if r.eleves_par_salle_durable > SEUILS["eleves_par_salle"] or r.part_salles_precaires > SEUILS["salles_precaires"]:
            a.append("Construire ou remplacer des salles")
        return " ; ".join(a) or "Maintenir le niveau actuel"
    b["actions_recommandees"] = b.apply(actions, axis=1)
    return b


def controle_tbs(b):
    """Quelle population rapporter à l'année scolaire 2024-2025 ? On compare aux TBS publiés par la DGESS."""
    try:
        panel = lire("*panel-region-annee-ratios*.csv", "transformation")
    except SystemExit:
        return []
    pan = panel[(panel.cycle == "primaire") & (panel.annee_scolaire == PARAMS["annee_base"])].set_index("region")
    pr = lire("*projections-population-2020-2035-province*.csv")
    pr = pr[(pr.niveau == "region") & (pr.groupe_age == "6-11") & (pr.sexe == "T")].pivot_table(index="entite", columns="annee", values="population")
    a0 = PARAMS["pop_base"]
    d = pd.DataFrame({"dgess": pan.tbs_T, "eleves": pan.effectif_T}).dropna().join(pr[[a0, a0 + 1]], how="inner")
    d["avec_pop_n"] = d.eleves / d[a0] * 100
    d["avec_pop_n1"] = d.eleves / d[a0 + 1] * 100
    d["avec_moyenne"] = d.eleves / ((d[a0] + d[a0 + 1]) / 2) * 100
    e = {c: (d[c] - d.dgess).abs().mean() for c in ("avec_pop_n", "avec_pop_n1", "avec_moyenne")}
    j = ["", f"## Contrôle : quelle population pour l'année scolaire {PARAMS['annee_base']} ?",
         f"TBS recalculé (élèves DGESS / population INSD des 6-11 ans) comparé au TBS publié par la DGESS, {len(d)} régions.", "",
         f"| Région | TBS DGESS | pop. {a0} | pop. {a0 + 1} | moyenne {a0}-{a0 + 1} |", "|---|---|---|---|---|"]
    j += [f"| {r} | {v.dgess:.2f} | {v.avec_pop_n:.2f} | {v.avec_pop_n1:.2f} | {v.avec_moyenne:.2f} |" for r, v in d.iterrows()]
    j += [f"| **Écart absolu moyen** | — | {e['avec_pop_n']:.2f} | {e['avec_pop_n1']:.2f} | {e['avec_moyenne']:.2f} |", "",
          f"Conclusion : la DGESS rapporte l'année scolaire N-(N+1) à la population de l'année N (rentrée d'octobre N). "
          f"Le projet suit cette convention, et la reprend pour l'horizon : l'année {PARAMS['annee_cible']} désigne "
          f"l'année scolaire {PARAMS['annee_cible']}-{PARAMS['annee_cible'] + 1}."]
    return j


def double_vacation(b):
    """Sensibilité du déficit de salles à l'hypothèse « un groupe pédagogique par salle »."""
    a, g = PARAMS["annee_cible"], b.groupes_par_salle_2024
    j = ["", "## Sensibilité : double vacation",
         f"En {PARAMS['annee_base']}, on compte {b.groupes_pedagogiques.sum() / b.salles.sum():.2f} groupe pédagogique par salle au niveau national "
         f"(de {g.min():.2f} à {g.max():.2f} selon la province ; {int((g > 1.05).sum())} provinces au-dessus de 1,05). "
         f"Hypothèse retenue : {PARAMS['groupes_par_salle']} groupe(s) par salle.", "",
         "| Scénario | Déficit de salles, hypothèse retenue | Déficit si la pratique de 2024-2025 se maintient | Écart |", "|---|---|---|---|"]
    for scen in SCENARIOS:
        d0, d1 = b[f"deficit_salles_{a}_{scen}"].sum(), b[f"deficit_salles_{a}_{scen}_pratique_2024"].sum()
        j.append(f"| {scen} | {d0:,.0f} | {d1:,.0f} | {d1 - d0:+,.0f} ({(d1 - d0) / d0:+.0%}) |".replace(",", " "))
    j += ["", "La double vacation réduit le besoin de salles, mais elle raccourcit le temps d'apprentissage. "
          "Le PSEF la traite comme une mesure de transition : la norme d'un groupe par salle reste la cible. "
          "L'application permet de changer ce paramètre."]
    return j


def norme_qualite(b):
    """Sensibilité : besoins si l'on vise 40 élèves par maître et par salle au lieu de la norme nationale."""
    a, q = PARAMS["annee_cible"], PARAMS["rem_qualite"]
    j = ["", f"## Scénario « qualité » : {q} élèves par maître et par salle",
         f"La norme nationale ({PARAMS['rem_cible']}) sert de référence. Avec une norme de {q}, plus exigeante, les besoins deviennent :", "",
         f"| Scénario de scolarisation | Déficit de maîtres (norme {PARAMS['rem_cible']}) | Déficit de maîtres (norme {q}) | "
         f"Déficit de salles (norme {PARAMS['rem_cible']}) | Déficit de salles (norme {q}) |", "|---|---|---|---|---|"]
    for scen in SCENARIOS:
        el = b[f"eleves_{a}_{scen}"]
        b[f"deficit_maitres_{a}_{scen}_qualite"] = (np.ceil(el / q) - b.maitres).clip(lower=0)
        b[f"deficit_salles_{a}_{scen}_qualite"] = (np.ceil(el / (q * PARAMS["groupes_par_salle"])) - b.salles_durables).clip(lower=0)
        j.append(f"| {scen} | {b[f'deficit_maitres_{a}_{scen}'].sum():_.0f} | {b[f'deficit_maitres_{a}_{scen}_qualite'].sum():_.0f} | "
                 f"{b[f'deficit_salles_{a}_{scen}'].sum():_.0f} | {b[f'deficit_salles_{a}_{scen}_qualite'].sum():_.0f} |".replace("_", " "))
    j += ["", "Le classement des provinces ne dépend pas de la norme (l'indice de priorité n'utilise que la situation observée) ; "
          "seuls les volumes à recruter et à construire changent. L'application permet de choisir l'une ou l'autre norme."]
    return j


def evolution(b):
    """Évolution par province entre l'annuaire de référence et l'année de base (écoles, élèves, maîtres)."""
    if b["ecoles_ref"].isna().all():
        return ["", f"## Évolution depuis {PARAMS['annee_reference']}", "Annuaire de référence absent : section non calculée."]
    r0, r1 = PARAMS["annee_reference"], PARAMS["annee_base"]
    nat = {n: (b[n if n != "eleves" else "eleves_2024"].sum(), b[f"{n}_ref"].sum()) for n in ("ecoles", "salles", "maitres", "eleves")}
    j = ["", f"## Évolution de {r0} à {r1} (annuaires DGESS, public + privé)",
         "National : " + " ; ".join(f"{n} {v0:,.0f} → {v1:,.0f} ({v1 / v0 - 1:+.1%})".replace(",", " ")
                                     for n, (v1, v0) in nat.items()) + ".",
         f"Élèves par maître : {nat['eleves'][1] / nat['maitres'][1]:.1f} → {nat['eleves'][0] / nat['maitres'][0]:.1f}.", "",
         "Provinces qui ont perdu le plus d'élèves (fermetures d'écoles, insécurité, déplacements) :", "",
         "| Province | Région | Écoles | Élèves | Maîtres | Indice de priorité |", "|---|---|---|---|---|---|"]
    for p, r in b.sort_values("variation_eleves_depuis_ref").head(10).iterrows():
        j.append(f"| {p} | {r.region} | {r.ecoles_ref:.0f} → {r.ecoles:.0f} ({r.variation_ecoles_depuis_ref:+.0%}) | "
                 f"{r.eleves_ref:,.0f} → {r.eleves_2024:,.0f} ({r.variation_eleves_depuis_ref:+.0%}) | "
                 f"{r.variation_maitres_depuis_ref:+.0%} | {r.indice_priorite:.0f} (rang {r.rang_priorite}) |".replace(",", " "))
    corr = b[["variation_eleves_depuis_ref", "indice_priorite"]].corr().iloc[0, 1]
    j += ["", f"Corrélation entre la variation des élèves et l'indice de priorité : {corr:.2f}. "
          "Cette évolution n'entre pas dans l'indice (qui décrit la situation de l'année de base) : elle sert à vérifier "
          "que les provinces prioritaires sont bien celles où l'école a reculé."]
    return j


def cout(eleves, capacite, norme):
    """Élèves au-delà de la norme, pondérés par l'ampleur du dépassement (fonction convexe)."""
    if capacite <= 0:
        return eleves * eleves / norme
    exces = max(0.0, eleves - norme * capacite)
    return exces * (eleves / capacite) / norme


def allouer_optimise(eleves, capacite, poids, budget, norme, pas):
    """Allocation gloutonne : à chaque pas, l'unité va là où elle réduit le plus le coût pondéré.
    Pour une fonction de coût convexe et séparable, cette méthode donne l'optimum (aux arrondis du pas près)."""
    ajout = {p: 0 for p in eleves.index}
    tas = []
    for p in eleves.index:
        gain = poids[p] * (cout(eleves[p], capacite[p], norme) - cout(eleves[p], capacite[p] + pas, norme))
        heapq.heappush(tas, (-gain, p))
    reste = budget
    while reste > 0 and tas:
        g, p = heapq.heappop(tas)
        if -g <= 0:
            break
        u = min(pas, reste)
        ajout[p] += u
        reste -= u
        c = capacite[p] + ajout[p]
        gain = poids[p] * (cout(eleves[p], c, norme) - cout(eleves[p], c + pas, norme))
        heapq.heappush(tas, (-gain, p))
    return pd.Series(ajout)


def allouer_prorata(eleves, budget):
    part = eleves / eleves.sum()
    brut = np.floor(part * budget)
    reste = int(budget - brut.sum())
    ordre = (part * budget - brut).sort_values(ascending=False).index[:reste]
    brut[ordre] += 1
    return brut


def mesures(eleves, capacite, norme):
    """Indicateurs d'une répartition ; une province est « critique » au-delà de la norme + 10."""
    ratio = eleves / capacite
    return {
        "eleves_au_dela_de_la_norme": float(np.maximum(0, eleves - norme * capacite).sum()),
        "seuil_critique": norme + 10,
        "provinces_au_dela_du_seuil": int((ratio > norme + 10).sum()),
        "ratio_maximal": float(ratio.max()),
        "ecart_type_ratio": float(ratio.std()),
    }


def principal():
    a = PARAMS["annee_cible"]
    b = types_action(indice_priorite(besoins(base_province())))
    poids = 1 + PARAMS["poids_equite"] * b.indice_priorite / 100
    j = [f"# Journal de l'étape 4 — besoins {a}, priorités et allocation", f"Exécuté le {datetime.now():%d/%m/%Y %H:%M}", "",
         "## Hypothèses", *[f"- `{k}` = {v}" for k, v in PARAMS.items()], ""]
    j.append(f"- Contrôle : TBS recalculé 2024-2025, national = {b.eleves_2024.sum() / b[f'pop_6_11_{PARAMS['pop_base']}'].sum() * 100:.1f} %.")

    j += controle_tbs(b) + double_vacation(b) + [""]
    lignes_alloc, synthese = [], []
    for scen in SCENARIOS:
        el = b[f"eleves_{a}_{scen}"]
        for ressource, cap, defi in (("enseignants", b.maitres, f"deficit_maitres_{a}_{scen}"),
                                    ("salles", b.salles_durables, f"deficit_salles_{a}_{scen}")):
            norme = PARAMS["rem_cible"] if ressource == "enseignants" else PARAMS["eleves_par_salle_cible"] * PARAMS["groupes_par_salle"]
            budget = int(round(b[defi].sum() * PARAMS["budget_part_deficit"]))
            opt = allouer_optimise(el, cap, poids, budget, norme, PARAMS["pas_allocation"])
            pro = allouer_prorata(el, budget)
            b[f"alloc_{ressource}_{scen}"] = opt
            b[f"alloc_prorata_{ressource}_{scen}"] = pro
            m0, m1, m2 = mesures(el, cap, norme), mesures(el, cap + pro, norme), mesures(el, cap + opt, norme)
            synthese.append({"scenario": scen, "ressource": ressource, "budget": budget,
                             "deficit_national": int(b[defi].sum()),
                             **{f"sans_allocation_{k}": v for k, v in m0.items()},
                             **{f"prorata_{k}": v for k, v in m1.items()},
                             **{f"optimise_{k}": v for k, v in m2.items()}})
            for p in b.index:
                lignes_alloc.append({"scenario": scen, "ressource": ressource, "province": p, "region": b.region[p],
                                     "capacite_2024": cap[p], "eleves_2030": el[p],
                                     "allocation_prorata": pro[p], "allocation_optimisee": opt[p],
                                     "ratio_apres_prorata": round(el[p] / (cap[p] + pro[p]), 1),
                                     "ratio_apres_optimise": round(el[p] / (cap[p] + opt[p]), 1)})
            gain = m1["eleves_au_dela_de_la_norme"] - m2["eleves_au_dela_de_la_norme"]
            j.append(f"- {scen}, {ressource} : budget {budget:,} ({PARAMS['budget_part_deficit']:.0%} du déficit de {int(b[defi].sum()):,}). "
                     f"Élèves au-delà de la norme : {m0['eleves_au_dela_de_la_norme']:,.0f} sans allocation, "
                     f"{m1['eleves_au_dela_de_la_norme']:,.0f} au prorata, {m2['eleves_au_dela_de_la_norme']:,.0f} optimisé "
                     f"({gain:,.0f} de moins). Ratio maximal : {m1['ratio_maximal']:.0f} au prorata contre "
                     f"{m2['ratio_maximal']:.0f} optimisé.".replace(",", " "))

    j += evolution(b) + scenario_retour(b) + norme_qualite(b)
    j += ["", "## Types d'action recommandés", f"Seuils : {SEUILS}"]
    for act in ["Rouvrir et sécuriser les écoles", "Renforcer l'accueil des élèves déplacés", "Recruter et affecter des enseignants", "Construire ou remplacer des salles"]:
        ps = b.index[b.actions_recommandees.str.contains(act, regex=False)]
        j.append(f"- {act} ({len(ps)}) : {', '.join(sorted(ps))}")
    j += ["", "## Provinces prioritaires (indice de priorité)"]
    for p, r in b.sort_values("indice_priorite", ascending=False).head(10).iterrows():
        j.append(f"- {r.rang_priorite}. {p} ({r.region}) : {r.indice_priorite:.0f}/100 — {r.rem_2024:.0f} élèves/maître, "
                 f"{r.part_salles_precaires:.0%} de salles précaires, TBS {r.tbs_2024:.0f} %")

    out = config.DOSSIERS["analyse"]
    out.mkdir(parents=True, exist_ok=True)
    b.reset_index().rename(columns={"index": "province"}).to_csv(
        config.nom_fichier("analyse", "scientist", "besoins-2030-priorites-province"), index=False, encoding="utf-8")
    pd.DataFrame(lignes_alloc).to_csv(config.nom_fichier("analyse", "scientist", "allocation-optimisee-vs-prorata"), index=False, encoding="utf-8")
    pd.DataFrame(synthese).to_csv(config.nom_fichier("analyse", "scientist", "synthese-allocation"), index=False, encoding="utf-8")
    config.nom_fichier("analyse", "scientist", "journal-besoins-allocation", ext="md").write_text("\n".join(j), encoding="utf-8")
    print("\n".join(j))


if __name__ == "__main__":
    principal()
