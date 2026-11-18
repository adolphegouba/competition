"""Prépare le dossier ENVOI_PLATEFORME pour la plateforme equation.

Range les livrables selon le document du challenge (dépôts par étape, noms
EQUIPE_ETAPE_DEFI_ROLE_description_vN, LISEZ-MOI, documentation de 15 pages au plus) et selon
les trois rubriques du formulaire de dépôt (Données, Code, Documentation : 20 fichiers et
50 Mo par fichier au plus). Le projet lui-même n'est pas modifié.

Lancement :  python preparer_envoi.py   (après lancer_tout.ps1 et doc/imprimer_documentation.py)
"""
import shutil
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE / "src"))
import config  # noqa: E402

NOM = config.EQUIPE
ENVOI = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else RACINE / "ENVOI_PLATEFORME"  # dossier de sortie (facultatif)
FICHE = RACINE / "src" / "fiche"  # textes de la fiche, recopiés à chaque préparation
LIMITE_FICHIERS, LIMITE_OCTETS = 20, 50 * 1024 * 1024
DOC_PDF = RACINE / "doc" / f"{NOM}_D3_documentation_v1.docx"
DOC_PDF2 = RACINE / "doc" / f"{NOM}_D3_documentation_v1.pdf"

# scripts de la solution : nom d'origine -> nom déposé (modèle EQUIPE_ETAPE_DEFI_ROLE_description_vN)
SCRIPTS = [
    ("etape01_inventaire_sources", f"{NOM}_01-collecte_D3_engineer_inventaire-sources_v1"),
    ("etape02_nettoyage_dgess", f"{NOM}_02-nettoyage_D3_engineer_nettoyage-dgess_v1"),
    ("etape02b_extraction_annuaires", f"{NOM}_02-nettoyage_D3_engineer_extraction-annuaires_v1"),
    ("etape02c_projections_population", f"{NOM}_02-nettoyage_D3_engineer_projections-population_v1"),
    ("etape02d_extraction_esu", f"{NOM}_02-nettoyage_D3_engineer_extraction-esu_v1"),
    ("etape03_transformation", f"{NOM}_03-transformation_D3_analyst_panel-region-ratios_v1"),
    ("etape03b_fond_de_carte", f"{NOM}_03-transformation_D3_architect_fond-de-carte_v1"),
    ("etape03c_ecoles_accessibilite", f"{NOM}_03-transformation_D3_architect_ecoles-accessibilite_v1"),
    ("etape04_besoins_allocation", f"{NOM}_04-analyse_D3_scientist_besoins-priorites-allocation_v1"),
    ("etape04b_redeploiement_robustesse_decoupage", f"{NOM}_04-analyse_D3_scientist_redeploiement-robustesse-decoupage_v1"),
    ("etape05_application", f"{NOM}_05-interpretation_D3_analyst_application-aide-decision_v1"),
    ("etape05b_note_decideur", f"{NOM}_05-interpretation_D3_analyst_note-decideur_v1"),
]

# résultats de l'analyse déposés un par un (les plus utiles au jury)
RESULTATS = ("besoins-2030-priorites-province", "allocation-optimisee-vs-prorata", "synthese-allocation",
             "redeploiement-enseignants", "robustesse-indice-priorite", "resultats-provinces-2025",
             "resultats-regions-2025", "zones-candidates-nouvelles-ecoles")

GUIDE = f"""COMMENT DÉPOSER SUR LA PLATEFORME
================================

1_Données        -> « Ajouter un fichier : Données »        (sélectionner tous les fichiers du dossier)
2_Code           -> « Ajouter un fichier : Code »
3_Documentation  -> « Ajouter un fichier : Documentation »

Les fichiers suivent le modèle du challenge : {NOM}_ÉTAPE_D3_RÔLE_description_v1
Une archive par étape ; chaque archive contient le dossier de l'étape.
  01-collecte        toutes les données brutes utilisées pour le défi 3, telles que reçues, et leur inventaire
  02-nettoyage       données propres, anomalies, journaux de nettoyage
  03-transformation  panel région-année, ratios, fond de carte, correspondance 2025, écoles géolocalisées
  04-analyse         besoins 2030, priorités, répartition, redéploiement, robustesse, résultats 2025
  05-interpretation  application d'aide à la décision et note au décideur

2_Code : les 12 scripts en clair, renommés selon la nomenclature, et le projet complet à relancer (zip).
NE PAS décompresser les zips dans ce dossier : les déposer tels quels.

4_Fiche
  1_Declaration_IA_obligatoire_….txt -> champ « Déclaration d'usage de l'intelligence artificielle »
  2_Commentaire_jury_….txt           -> champ « Commentaire pour le jury »
  3_Lien_application.txt             -> champ « Lien » (lien Netlify de l'application)

5_Site_a_heberger (NE PAS déposer sur la plateforme)
  L'application sous le nom index.html, pour Netlify : glisser ce dossier dans « Deploys ».

Enfin : « Enregistrer la fiche », puis « Envoyer la solution ».
"""


def sortie(dossier: str, motif: str) -> Path:
    f = sorted(config.DOSSIERS[dossier].glob(f"{NOM}_*{motif}*"))
    if not f:
        raise SystemExit(f"Introuvable dans {dossier} : {motif}. Lancez d'abord lancer_tout.ps1.")
    return f[-1]


def zipper(zip_path: Path, fichiers: dict):
    """fichiers : {chemin dans l'archive: fichier source}."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in fichiers.items():
            z.write(src, arc)


def principal():
    if not DOC_PDF.exists():
        raise SystemExit(f"Documentation absente : lancez d'abord  python doc/imprimer_documentation.py")
    shutil.rmtree(ENVOI, ignore_errors=True)
    don, code, docu, fiche, site = (ENVOI / d for d in
                                    ("1_Données", "2_Code", "3_Documentation", "4_Fiche", "5_Site_a_heberger"))
    for d in (don, code, docu, fiche, site):
        d.mkdir(parents=True)

    # 1. Données : une archive par étape du parcours, avec le dossier de l'étape à l'intérieur
    #    01 : toutes les données brutes utilisées pour le défi 3 (telles que reçues) et leur inventaire
    brutes = config.DOSSIERS["collecte"]
    fichiers = {f"data/01_collecte/{f.relative_to(brutes).as_posix()}": f for f in sorted(brutes.rglob("*"))
                if f.is_file() and f.name != ".gitkeep" and not f.name.startswith(("Neural_faso", "EXX"))}  # anciens préfixes exclus
    zipper(don / f"{NOM}_01-collecte_D3_engineer_donnees-brutes-utilisees_v1.zip", fichiers)
    #    02 à 05 : les fichiers produits par l'équipe à chaque étape, avec les journaux de contrôle
    for etape, dossier, role, desc in (("02-nettoyage", "nettoyage", "engineer", "donnees-propres-et-journaux"),
                                       ("03-transformation", "transformation", "architect", "panel-ratios-carte-ecoles"),
                                       ("04-analyse", "analyse", "scientist", "besoins-priorites-repartition"),
                                       ("05-interpretation", "interpretation", "analyst", "application-et-note")):
        d = config.DOSSIERS[dossier]
        fichiers = {f"data/{d.name}/{f.name}": f for f in sorted(d.glob(f"{NOM}_*"))}
        zipper(don / f"{NOM}_{etape}_D3_{role}_{desc}_v1.zip", fichiers)
    # 2. Code : chaque script de la solution en clair, renommé selon la nomenclature (lecture directe par le jury),
    #    plus une seule archive : le projet complet avec les noms d'origine, prêt à relancer (les scripts s'importent
    #    entre eux par leur nom d'origine ; le gabarit .html, Leaflet et le lanceur .ps1 ne sont pas acceptés seuls).
    src = RACINE / "src"
    rel = lambda f: f.relative_to(RACINE).as_posix()
    for origine, nom in SCRIPTS:
        f = src / f"{origine}.py"
        if not f.exists():
            raise SystemExit(f"Script introuvable : {f}")
        entete = (f"# {nom}.py\n# Nom d'origine dans le projet : src/{origine}.py (nom à garder pour relancer).\n"
                  f"# Le projet complet, prêt à relancer, est dans {NOM}_D3_architect_projet-complet-a-relancer_v1.zip\n\n")
        (code / f"{nom}.py").write_text(entete + f.read_text(encoding="utf-8"), encoding="utf-8")
    projet = {n: RACINE / n for n in ("lancer_tout.ps1", "requirements.txt", "preparer_envoi.py")}
    for f in sorted(src.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            projet[rel(f)] = f
    for f in sorted((RACINE / "doc").rglob("*")):
        if f.is_file() and f.suffix == ".md":  # dictionnaire des variables
            projet[rel(f)] = f
    for d in config.DOSSIERS.values():
        if (d / ".gitkeep").exists():
            projet[rel(d / ".gitkeep")] = d / ".gitkeep"
    zipper(code / f"{NOM}_D3_architect_projet-complet-a-relancer_v1.zip", projet)
    app = sortie("interpretation", "application-aide-decision")

    # 3. Documentation : la documentation finale en Word et en PDF (la note au décideur est dans l'archive 05)
    shutil.copyfile(DOC_PDF, docu / DOC_PDF.name)
    shutil.copyfile(DOC_PDF2, docu / DOC_PDF2.name)

    # 4. Fiche : un fichier par champ, à copier-coller
    for nom, champ in (("declaration_ia.txt", "1_Declaration_IA_obligatoire"), ("commentaire_jury.txt", "2_Commentaire_jury")):
        t = (FICHE / nom).read_text(encoding="utf-8").strip()
        (fiche / f"{champ}_{len(t)}-caracteres.txt").write_text(t, encoding="utf-8")
    (fiche / "3_Lien_application.txt").write_text("Coller ici le lien Netlify de l'application (https://….netlify.app).\n",
                                                  encoding="utf-8")

    # 5. Site à héberger
    shutil.copyfile(app, site / "index.html")
    (ENVOI / "COMMENT_DEPOSER.txt").write_text(GUIDE, encoding="utf-8")

    # Contrôles : nombre, taille, noms de fichiers conformes (pas d'espace ni d'accent)
    envoyes = [f for d in (don, code, docu) for f in d.iterdir()]
    trop_gros = [f.name for f in envoyes if f.stat().st_size > LIMITE_OCTETS]
    mal_nommes = [f.name for f in envoyes if (" " in f.name or not f.name.isascii()
                                                                            or not f.name.startswith(NOM + "_"))]
    total = sum(f.stat().st_size for f in envoyes)
    print(f"{len(envoyes)} fichiers à envoyer (limite {LIMITE_FICHIERS}), {total / 1024 / 1024:.1f} Mo au total.")
    for d in (don, code, docu, fiche, site):
        print(f"\n{d.name}/")
        for f in sorted(d.iterdir()):
            print(f"  {f.name}  ({f.stat().st_size // 1024} Ko)")
    if len(envoyes) > LIMITE_FICHIERS or trop_gros or mal_nommes:
        raise SystemExit(f"\nPROBLÈME : {len(envoyes)} fichiers ; trop gros : {trop_gros} ; noms non conformes : {mal_nommes}")
    print("\nTous les contrôles sont bons. Dossier prêt :", ENVOI)


if __name__ == "__main__":
    principal()
