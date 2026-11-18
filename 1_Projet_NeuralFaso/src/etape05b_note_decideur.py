"""Étape 5b : note d'une page pour le décideur (HTML imprimable, et PDF si Chrome ou Edge est installé).

Tous les chiffres sont lus dans les sorties des étapes 4 et 4b (hypothèses de référence : horizon 2030,
scénario tendanciel, norme nationale de 50 élèves par maître et par salle, budget = 50 % du déficit).

Entrées : data/04_analyse, data/03_transformation.   Sorties : data/05_interpretation/…_note-decideur_v1.html (+ .pdf)
Lancement :  python src/etape05b_note_decideur.py
"""
import json
import math
import shutil
import subprocess
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd

import config
from etape04_besoins_allocation import PARAMS, SEUILS
from etape04b_redeploiement_robustesse_decoupage import SEUIL_REFERENCE, TIRAGES

ORDRE_ACTIONS = ["Rouvrir et sécuriser les écoles", "Recruter et affecter des enseignants",
                 "Construire ou remplacer des salles", "Renforcer l'accueil des élèves déplacés"]
RAMPE = ["#FFF6CF", "#FCD116", "#F5A623", "#E5631E", "#CE1126", "#7E0A1A"]


def lire(motif, dossier):
    f = sorted(config.DOSSIERS[dossier].glob(motif))
    if not f:
        raise SystemExit(f"Introuvable : {motif} — lancez les étapes précédentes.")
    return f[-1]


def nf(x, d=0):
    return f"{x:_.{d}f}".replace("_", "\u202f").replace(".", ",")


def pc(x, d=0):
    return nf(x * 100, d) + " %"


def titre(s):
    return " ".join(m.capitalize() for m in str(s).lower().split(" "))


def couleur(t):
    t = max(0.0, min(1.0, t))
    i = min(len(RAMPE) - 2, int(t * (len(RAMPE) - 1)))
    f = t * (len(RAMPE) - 1) - i
    a, b = RAMPE[i], RAMPE[i + 1]
    c = [round(int(a[k:k + 2], 16) * (1 - f) + int(b[k:k + 2], 16) * f) for k in (1, 3, 5)]
    return "#" + "".join(f"{v:02x}" for v in c)


def carte_svg(geo, indice, W=330, H=245):
    anneaux = lambda g: [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    pts = [pt for f in geo["features"] for poly in anneaux(f["geometry"]) for pt in poly[0]]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    k = math.cos((y0 + y1) / 2 * math.pi / 180)
    s = min((W - 8) / ((x1 - x0) * k), (H - 8) / (y1 - y0))
    ox, oy = (W - (x1 - x0) * k * s) / 2, (H - (y1 - y0) * s) / 2
    pr = lambda x, y: f"{ox + (x - x0) * k * s:.1f},{oy + (y1 - y) * s:.1f}"
    lo, hi = min(indice.values()), max(indice.values())
    chemins = []
    for f in geo["features"]:
        d = "".join("M" + "L".join(pr(*c) for c in ring) + "Z" for poly in anneaux(f["geometry"]) for ring in poly)
        v = indice.get(f["properties"]["province"], lo)
        chemins.append(f'<path d="{d}" fill="{couleur((v - lo) / (hi - lo))}" stroke="#fff" stroke-width=".6"/>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg">{"".join(chemins)}</svg>'


def principal():
    a = PARAMS["annee_cible"]
    b = pd.read_csv(lire("*besoins-2030-priorites-province*.csv", "analyse")).set_index("province")
    rob = pd.read_csv(lire("*robustesse-indice-priorite*.csv", "analyse")).set_index("province")
    red = pd.read_csv(lire("*redeploiement-enseignants*.csv", "analyse"))
    syn = pd.read_csv(lire("*synthese-allocation*.csv", "analyse"))
    reg = pd.read_csv(lire("*resultats-regions-2025*.csv", "analyse"))
    corr = pd.read_csv(lire("*correspondance-provinces-2025*.csv", "transformation"))
    geo = json.loads(lire("*fond-de-carte-provinces-simplifie*.geojson", "transformation").read_text(encoding="utf-8"))

    s_ens = syn[(syn.scenario == "tendanciel") & (syn.ressource == "enseignants")].iloc[0]
    s_sal = syn[(syn.scenario == "tendanciel") & (syn.ressource == "salles")].iloc[0]
    secu = b[b.actions_recommandees.str.contains(ORDRE_ACTIONS[0], regex=False)].sort_values("indice_priorite", ascending=False)
    red_ref = red[red.seuil_donneuses == SEUIL_REFERENCE]
    pool = int(red_ref.enseignants_donnes.sum())
    donneuses = red_ref[red_ref.enseignants_donnes > 0].sort_values("enseignants_donnes", ascending=False).province.map(titre).tolist()
    ret = {k: b[f"{k}_{a}_retour"].sum() - b[f"{k}_{a}_tendanciel"].sum() for k in ("eleves", "deficit_maitres", "deficit_salles")}
    region25 = corr.groupby("province").region_2025.first()
    noyau = rob[rob.part_tirages_top10 >= 0.9].index.map(titre).tolist()

    courts = dict(zip(ORDRE_ACTIONS, ["Rouvrir et sécuriser", "Recruter", "Construire", "Accueillir les déplacés"]))

    def action_principale(txt):
        return courts.get(next((x for x in ORDRE_ACTIONS if x in txt), ""), "Maintenir")

    top = b.sort_values("indice_priorite", ascending=False).head(10)
    lignes = "".join(
        f"<tr><td>{int(r.rang_priorite)}</td><td style='white-space:nowrap'><b>{titre(p)}</b> <span class='p'>{escape(region25.get(p, ''))}</span></td>"
        f"<td class='n'>{r.indice_priorite:.0f}</td><td class='n'>{pc(rob.part_tirages_top10[p])}</td>"
        f"<td style='white-space:nowrap'>{action_principale(r.actions_recommandees)}</td><td class='n'>{r.rem_2024:.0f}</td>"
        f"<td class='n'>+{nf(r.alloc_enseignants_tendanciel)}</td><td class='n'>+{nf(r.alloc_salles_tendanciel)}</td></tr>"
        for p, r in top.iterrows())
    regions = ", ".join(f"{r.region_2025} ({r.indice_priorite_moyen:.0f})" for r in reg.head(5).itertuples())

    html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Note au décideur : salles et enseignants du primaire</title>
<style>
@page{{size:A4;margin:11mm 12mm}}
*{{box-sizing:border-box}}body{{margin:0;font:9.6pt/1.38 "Segoe UI",Arial,sans-serif;color:#1B2B22}}
.bandeau{{display:flex;justify-content:space-between;align-items:end;border-bottom:4px solid #00843D;padding-bottom:6px;margin-bottom:8px}}
.bandeau h1{{margin:0;font-size:17pt;line-height:1.05;color:#0F2419}} .bandeau .s{{color:#CE1126;font-weight:700;font-size:8.5pt;letter-spacing:.3px}}
.bandeau .d{{text-align:right;font-size:8pt;color:#55665C}}
.message{{background:#0F2419;color:#fff;border-radius:7px;padding:8px 12px;font-size:11pt;font-weight:600;margin-bottom:8px}}
.message b{{color:#FCD116}}
.grille{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-bottom:8px}}
.dec{{border:1px solid #DDE4DF;border-top:4px solid #00843D;border-radius:6px;padding:6px 8px}} .dec.d1{{border-top-color:#CE1126}} .dec.d3{{border-top-color:#23406E}}
.dec .t{{font-size:7.5pt;font-weight:700;color:#55665C;text-transform:uppercase}} .dec h2{{font-size:11pt;margin:2px 0 3px;line-height:1.15}}
.dec p{{margin:0 0 3px;font-size:8.6pt}}
.duo{{display:grid;grid-template-columns:1.6fr 1fr;gap:12px;align-items:start}}
h3{{font-size:10pt;margin:2px 0 4px;color:#00592A}}
table{{width:100%;border-collapse:collapse;font-size:8.2pt}} th{{text-align:left;color:#55665C;border-bottom:1.5px solid #DDE4DF;padding:2px 3px;font-weight:600}}
td{{border-bottom:1px solid #EEF1EF;padding:2px 3px;vertical-align:top}} .n{{text-align:right;white-space:nowrap}} .p{{color:#55665C;font-size:7.4pt}}
.leg{{display:flex;align-items:center;gap:5px;font-size:7.4pt;color:#55665C}} .leg i{{flex:1;height:6px;border-radius:3px;background:linear-gradient(90deg,{",".join(RAMPE)})}}
ul{{margin:0;padding-left:14px}} li{{margin-bottom:2px}}
.pied{{margin-top:7px;border-top:1px solid #DDE4DF;padding-top:4px;font-size:7.2pt;color:#55665C}}
</style></head><body>
<div class="bandeau"><div><div class="s">DATA CHALLENGE BURKINA 2026 · DÉFI 3</div>
<h1>Une salle et un maître pour chaque enfant : où affecter les moyens d'ici {a}</h1></div>
<div class="d">Note au décideur<br>Novembre 2026</div></div>

<div class="message">En {a}, il manquera <b>{nf(s_ens.deficit_national)} enseignants</b> et <b>{nf(s_sal.deficit_national)} salles</b> au primaire si la scolarisation reste à son niveau actuel.
À budget égal, une répartition optimisée ramène le pire ratio de <b>{s_ens.prorata_ratio_maximal:.0f} à {s_ens.optimise_ratio_maximal:.0f} élèves par maître</b> : {int(s_ens.optimise_provinces_au_dela_du_seuil) or "aucune"} province{"s" if s_ens.optimise_provinces_au_dela_du_seuil > 1 else ""} au-delà de {int(s_ens.optimise_seuil_critique)}, contre {int(s_ens.prorata_provinces_au_dela_du_seuil)} avec une répartition au prorata.
Avec une norme « qualité » de {PARAMS['rem_qualite']}, il faudrait {nf(b[f"deficit_maitres_{a}_tendanciel_qualite"].sum())} enseignants et {nf(b[f"deficit_salles_{a}_tendanciel_qualite"].sum())} salles.</div>

<div class="grille">
<div class="dec d1"><div class="t">1 · D'abord</div><h2>Rouvrir et sécuriser les écoles dans {len(secu)} provinces</h2>
<p>Moins de {SEUILS['tbs_securite']} % des enfants y vont à l'école. Elles sont passées de {nf(secu.eleves_ref.sum())} à {nf(secu.eleves_2024.sum())} élèves depuis {PARAMS['annee_reference']}.</p>
<p><b>Où :</b> {", ".join(titre(p) for p in secu.index)}.</p>
<p><b>Préparer le retour :</b> retrouver les taux de {PARAMS['annee_reference']} demande {nf(ret['deficit_maitres'])} enseignants et {nf(ret['deficit_salles'])} salles de plus ({nf(ret['eleves'])} élèves).</p></div>
<div class="dec d2"><div class="t">2 · Enseignants</div><h2>Redéployer {pool}, puis recruter {nf(s_ens.budget)} enseignants</h2>
<p>Le redéploiement depuis {", ".join(donneuses)} est gratuit mais ne couvre que {pc(pool / s_ens.deficit_national, 1)} du déficit.</p>
<p>Recrutement : la moitié du déficit, affectée selon la méthode optimisée (tableau ci-dessous).</p></div>
<div class="dec d3"><div class="t">3 · Salles de classe</div><h2>Construire {nf(s_sal.budget)} salles</h2>
<p>Y compris le remplacement de {nf(b.salles_paille_banco.sum())} salles en paille ou en banco.</p>
<p>Le pire ratio passe de {s_sal.prorata_ratio_maximal:.0f} élèves par salle (prorata) à {s_sal.optimise_ratio_maximal:.0f} (méthode optimisée).</p></div>
</div>

<div class="duo"><div>
<h3>Les 10 provinces prioritaires</h3>
<table><tr><th>#</th><th>Province <span class="p">région 2025</span></th><th class="n">Indice</th><th class="n">Top 10*</th><th>D'abord</th><th class="n">Élèves/maître</th><th class="n">+ Maîtres</th><th class="n">+ Salles</th></tr>{lignes}</table>
<p class="p" style="margin:3px 0 0">* Part des {nf(TIRAGES)} pondérations des 8 critères testées où la province reste dans les 10 premières. Enseignants et salles : moyens attribués d'ici {a}.</p>
</div><div>
<h3>Indice de priorité par province</h3>{carte_svg(geo, b.indice_priorite.to_dict())}
<div class="leg"><span>{b.indice_priorite.min():.0f}</span><i></i><span>{b.indice_priorite.max():.0f}</span></div>
<h3 style="margin-top:6px">Pourquoi ces résultats sont fiables</h3>
<ul><li>Sources officielles : DGESS (annuaires 2017-2018 et 2024-2025), INSD (projections 2020-2035), rapport ESU de février 2026.</li>
<li>Contrôles automatiques : sommes des provinces, public + privé, garçons + filles : aucun écart. Le TBS recalculé retrouve celui de la DGESS dans les 13 régions.</li>
<li>Indice robuste : {", ".join(noyau)} sont dans le top 10 pour plus de 90 % des pondérations ; les 10 y restent pour au moins la moitié.</li>
<li>Découpage 2025 : régions les plus prioritaires : {escape(regions)}.</li></ul>
</div></div>

<div class="pied">Hypothèses : horizon {a} (année scolaire {a}-{a + 1}), taux de scolarisation de {PARAMS['annee_base']} maintenu, norme nationale de {PARAMS['rem_cible']} élèves par maître et par salle (tableaux de bord DGESS ; {PARAMS['rem_qualite']} en scénario « qualité »),
salles en paille ou banco non comptées, budget simulé = {pc(PARAMS['budget_part_deficit'])} du déficit. Limites : projections INSD antérieures aux déplacements de population ; indice de parité seulement régional.
L'application d'aide à la décision (même dossier) permet de changer chaque hypothèse.</div>
</body></html>"""
    out = config.nom_fichier("interpretation", "analyst", "note-decideur", ext="html")
    out.write_text(html, encoding="utf-8")
    print(f"Note écrite : {out.relative_to(config.RACINE)}")

    navigateurs = [shutil.which(n) for n in ("chrome", "msedge", "google-chrome", "chromium")] + [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    nav = next((n for n in navigateurs if n and Path(n).exists()), None)
    if nav:
        pdf = out.with_suffix(".pdf")
        subprocess.run([nav, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", out.resolve().as_uri()], capture_output=True, timeout=120)
        print(f"PDF écrit : {pdf.relative_to(config.RACINE)}" if pdf.exists() else "PDF non produit : imprimez la page HTML en PDF.")
    else:
        print("Chrome ou Edge introuvable : ouvrez la page HTML et imprimez-la en PDF.")


if __name__ == "__main__":
    principal()
