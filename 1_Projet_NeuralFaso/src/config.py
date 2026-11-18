"""Paramètres communs du projet. Modifiez EQUIPE avec le code reçu sur la plateforme."""
from pathlib import Path

EQUIPE = "NeuralFaso"  # nom de l'équipe (sans espace ni tiret bas : le tiret bas sépare les champs du nom de fichier)
DEFI = "D3"
VERSION = "v1"

RACINE = Path(__file__).resolve().parents[1]
DATA = RACINE / "data"
DOSSIERS = {
    "collecte": DATA / "01_collecte",
    "nettoyage": DATA / "02_nettoyage",
    "transformation": DATA / "03_transformation",
    "analyse": DATA / "04_analyse",
    "interpretation": DATA / "05_interpretation",
}
ETAPES = {
    "collecte": "01-collecte",
    "nettoyage": "02-nettoyage",
    "transformation": "03-transformation",
    "analyse": "04-analyse",
    "interpretation": "05-interpretation",
}

# Fichier principal fourni par les organisateurs (à copier dans data/01_collecte)
_candidats = sorted(DOSSIERS["collecte"].glob("DONNEES_STATIST*.xlsx"))
FICHIER_DGESS = _candidats[0] if _candidats else DOSSIERS["collecte"] / "DONNEES_STATISTIQUES.xlsx"


def nom_fichier(etape: str, role: str, description: str, ext: str = "csv", version: str = VERSION) -> Path:
    """Construit un nom conforme au modèle EQUIPE_ETAPE_DEFI_ROLE_description_vN."""
    description = description.lower().replace(" ", "-").replace("_", "-")
    nom = f"{EQUIPE}_{ETAPES[etape]}_{DEFI}_{role}_{description}_{version}.{ext}"
    return DOSSIERS[etape] / nom
