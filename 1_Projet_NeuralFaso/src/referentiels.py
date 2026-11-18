"""Référentiels utilisés pour harmoniser les libellés."""
import re
import unicodedata


def sans_accent(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", str(texte))
    return "".join(c for c in texte if not unicodedata.combining(c))


def cle(texte) -> str:
    """Forme de comparaison : majuscules, sans accent, espaces et tirets normalisés."""
    t = sans_accent(texte).upper().replace("’", "'").replace("\xa0", " ")
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# 13 anciennes régions (découpage utilisé par les annuaires 2016-2025)
REGIONS_13 = [
    "BOUCLE DU MOUHOUN", "CASCADES", "CENTRE", "CENTRE-EST", "CENTRE-NORD",
    "CENTRE-OUEST", "CENTRE-SUD", "EST", "HAUTS-BASSINS", "NORD",
    "PLATEAU CENTRAL", "SAHEL", "SUD-OUEST",
]
VARIANTES_REGION = {
    "HAUT-BASSINS": "HAUTS-BASSINS",
    "HAUTS BASSINS": "HAUTS-BASSINS",
    "BOUCLE DE MOUHOUN": "BOUCLE DU MOUHOUN",
    "PLATEAU-CENTRAL": "PLATEAU CENTRAL",
    "CENTRE EST": "CENTRE-EST", "CENTRE NORD": "CENTRE-NORD",
    "CENTRE OUEST": "CENTRE-OUEST", "CENTRE SUD": "CENTRE-SUD",
    "SUD OUEST": "SUD-OUEST",
}
LIBELLES_NATIONAL = {"NATIONAL", "BURKINA FASO", "BURKINA", "TOTAL GENERAL", "ENSEMBLE"}

STATUTS = {"PUBLIC": "Public", "PRIVE": "Prive", "COMMUNAUTAIRE": "Communautaire"}
MILIEUX = {"URBAIN": "Urbain", "RURAL": "Rural", "INDETERMINE": "Indetermine"}
CLASSES = {
    "CP1": "CP1", "CP2": "CP2", "CE1": "CE1", "CE2": "CE2", "CM1": "CM1", "CM2": "CM2",
    "PETITE SECTION": "Petite section", "MOYENNE SECTION": "Moyenne section",
    "GRANDE SECTION": "Grande section",
}
SEXES = {"G": "G", "GARCONS": "G", "GARCON": "G", "M": "G", "MASCULIN": "G",
         "F": "F", "FILLES": "F", "FILLE": "F", "FEMININ": "F",
         "T": "T", "TOTAL": "T", "ENSEMBLE": "T"}


def region_canonique(valeur):
    k = cle(valeur)
    k = VARIANTES_REGION.get(k, k)
    if k in REGIONS_13:
        return k
    if k in LIBELLES_NATIONAL:
        return "NATIONAL"
    return None


def est_libelle_total(valeur) -> bool:
    k = cle(valeur)
    return k.startswith("TOTAL") or k in LIBELLES_NATIONAL


def annee_scolaire(valeur):
    """Convertit 2016, '2015-2016', '2015/16', '2024/25'... en '2015-2016'.

    Une année seule (ex. 2016) désigne l'année de fin : session d'examen
    ou fin d'année scolaire. Retourne None si aucune année n'est reconnue.
    """
    if valeur is None:
        return None
    if isinstance(valeur, (int, float)) and 1990 <= int(valeur) <= 2100:
        fin = int(valeur)
        return f"{fin - 1}-{fin}"
    texte = str(valeur).strip()
    m = re.match(r"^(\d{4})\s*[-/]\s*(\d{2,4})", texte)
    if m:
        debut = int(m.group(1))
        return f"{debut}-{debut + 1}"
    m = re.match(r"^(\d{4})(?!\d)", texte)
    if m:
        fin = int(m.group(1))
        return f"{fin - 1}-{fin}"
    return None
