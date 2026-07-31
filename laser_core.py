# -*- coding: utf-8 -*-
"""
laser_core.py -- Atelier Laser (FreeCAD Workbench)
© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Logique métier pure (aucun code d'interface ici -- cf. task_panels.py pour
les panneaux de tâches et commands.py pour les commandes/icônes) pour tout
le pipeline laser, du motif 2D au G-code, en 5 modes :

  1. GÉNÉRER HACHURES 2D -- 3 types : parallèles (boustrophédon/zigzag,
     défaut), croisées (2 passes à angle+90, réutilise le même générateur
     sans rien changer), défocus (remplissage noir plein -- mêmes
     hachures parallèles, mais l'espacement visé désormais un point laser
     volontairement ÉLARGI PAR DÉFOCUS (bec écarté du foyer, faisceau qui
     diverge) au lieu d'un point net : un seul passage suffit alors à
     noircir toute la surface, au lieu de dizaines de traits fins très
     rapprochés. Remplace l'ancien remplissage par contours concentriques,
     retiré (peu fiable : échouait sur les angles aigus d'une police et
     sur les formes à plusieurs largeurs). Le défocus nécessaire est
     calculé à partir de DEUX MESURES RÉELLES du point laser (au foyer,
     puis à un défocus de test connu) et non d'un angle de divergence
     deviné -- cf. defocus_divergence_half_angle / defocus_for_fill_spacing
     -- la même logique "mesure réelle plutôt qu'hypothèse" que la
     calibration de kerf du mode 3). Crée un objet "Hachures_..." (vert)
     dans le document. Étape de préparation, pas de G-code généré ici.

  2. PROJETER SUR SURFACE 3D -- colle un motif 2D (texte, hachures) sur
     une surface 3D de référence (sphère, vague...) par raycast vertical
     ('common' sur le solide -- plus fiable que distToShape pour ce cas).
     Échantillonnage par DISTANCE (pas Deflection : une droite 2D n'a
     aucune courbure à approximer, Deflection ne donnerait que 2 points
     -> corde droite sous la courbure réelle). Crée "Motif_Projete" (rouge).
     Étape de préparation, pas de G-code généré ici.

  3. MOTIF DE CALIBRATION KERF -- crée un carré test dans le document
     (taille réglable). Le découper en mode 5 avec Compensation de kerf
     = 0, mesurer la pièce obtenue au pied à coulisse : kerf = taille
     dessinée - taille mesurée. Aucune sélection requise pour ce mode.

  3b. GRILLE DE TEST PUISSANCE/VITESSE -- génère en un seul job une grille
     de cellules couvrant une plage de puissance (colonnes) x vitesse
     (lignes), en gravure (remplissage hachures -- parallèles, croisées
     ou défocus, mêmes 3 types que le mode 1) ou en découpe (contour
     carré, comme le mode 3). Chaque cellule est gravée/découpée UNE FOIS
     avec SA PROPRE puissance/vitesse (puissance croissante en X, vitesse
     croissante en Y). En remplissage Défocus, les cellules sont gravées
     à un Z différent (bec écarté du foyer) des étiquettes, qui restent
     TOUJOURS nettes au foyer normal -- au plus deux hauteurs de travail
     pour tout le job (cf. cell_z_offset dans generate_gcode_test_grid).
     En plus de la position, chaque colonne/ligne est étiquetée
     directement sur la pièce (ex: "S400", "F1500") avec une police
     vectorielle "7 segments" maison tracée en Part.Edge -- pas de
     fichier de police externe requis, contrairement à un ShapeString
     classique (cf. build_test_grid_axis_labels / text_to_edges) : le
     jeu de caractères nécessaire est minuscule (chiffres + S + F), un
     ShapeString aurait ajouté une dépendance à une police installée
     sans rien apporter ici. Étiquettes gravées à puissance/vitesse
     FIXES séparées des cellules testées (pas au hasard d'une valeur en
     cours de test). Ordre optionnel optimisé par plus proche voisin
     (comme le mode 3, appliqué séparément par hauteur de Z pour ne
     jamais mélanger cellules et étiquettes). La vue Rapport imprime
     aussi la grille complète avant génération. Aucune sélection requise
     (comme le mode 3).

  4. MARQUAGE SUR SURFACE COURBE -- à partir des objets projetés par le
     mode 2 : chaînage des segments connectés, transit continu à hauteur
     de travail + marge fixe, sonde exacte optionnelle si l'objet 3D
     d'origine est aussi sélectionné, sinon interpolation.

  5. DÉCOUPE MULTI-PASSES SUR MATÉRIAU PLAT -- mêmes segments/chaînage.
     Z=0 = LE BEC TOUCHE LA SURFACE du matériau (zéro au papier -- PAS le
     foyer). Dans cette convention, Z reste TOUJOURS POSITIF : le bec ne
     descend jamais sous la surface, c'est la lumière qui converge plus
     bas, à travers l'air, jusqu'au foyer. La hauteur du bec calculée
     depuis l'épaisseur EST directement la valeur "cale" du tableau
     constructeur reconstitué (vérifiée sur les 6 lignes du tableau
     LT-80W-AA-PRO) -- c'était déjà son rôle physique d'origine (écarter
     le bec de la pièce). Elle descend PROGRESSIVEMENT VERS ZÉRO (jamais
     en dessous, butée de sécurité SAFE_MIN_NOZZLE_HEIGHT_MM) au fil des
     passes, à mesure que le foyer doit suivre le fond de coupe. Recherche
     web faite sur les capacités réelles de coupe multi-passes pour ce
     laser précis : voir MAX_THICKNESS_WARNING_MM et RECOMMENDED_MAX_STEP_MM
     plus bas pour le détail et les sources.

     NOUVEAUTÉS DÉCOUPE (testées en isolation avant intégration -- voir
     compute_nesting_depths, offset_chain_kerf, order_chains_for_cutting) :
     - Puissance par passe : rampe linéaire optionnelle de la puissance
       de la 1ère à la dernière passe (au lieu d'une valeur fixe).
     - Trous/îlots avant le contour englobant : classification par
       imbrication (comparaison d'AIRE entre chaînes -- une simple
       comparaison centre-dans-polygone est trompeuse quand deux formes
       sont concentriques, le centre d'un grand contour peut tomber
       géométriquement DANS un petit trou sans y être "imbriqué").
       Boucle principale restructurée en chaîne-par-chaîne (toutes les
       passes d'une chaîne avant la suivante) : nécessaire pour que
       "avant" ait un sens physique réel, sinon la pièce intérieure ne
       serait jamais réellement détachée avant le contour extérieur.
     - Compensation de kerf : décalage par bissectrice per-sommet,
       extérieur agrandi / trous rétrécis, corrigé par le sens de
       parcours de chaque chaîne. Angles très réflexes : butée de
       sécurité sur l'angle (sous-compensation locale plutôt qu'un pic
       à l'infini) -- pas un offset de polygone garanti sans
       auto-intersection dans tous les cas, mais correct pour les
       contours usuels (texte, formes géométriques simples).
     - Optimisation de l'ordre par proximité : plus proche voisin
       (heuristique gloutonne, pas un TSP exact), à l'intérieur de
       chaque palier d'imbrication si les deux options sont actives.

CHAMPS G-CODE PERSONNALISÉ (modes 4 et 5) : texte libre inséré tel
quel avant le début du job (après G21/G90/G94 et la remontée de sécurité
initiale) et après la fin du job (après le désarmement, avant M2) -- pour
toute instruction particulière (ex: attente, message, M-code spécifique).

APERÇU CADRAGE (modes 3b, 4 et 5, bouton dédié) : génère un FICHIER
G-CODE SÉPARÉ qui trace uniquement le rectangle englobant du motif,
laser éteint -- à lancer seul sur la machine pour vérifier le
positionnement AVANT de lancer le vrai job. Volontairement PAS embarqué
au début du fichier du job réel (risque de le lancer en pensant
vérifier alors que le laser va réellement graver/découper juste après,
sans reprise de main entre les deux) -- cf. frame_only dans
generate_gcode_curved / generate_gcode_flat_multipass /
generate_gcode_test_grid, qui réutilise le même calcul de Z de sécurité
que le job réel plutôt que de le redupliquer.

ESTIMATION DE TEMPS (modes 4 et 5, automatique) : affichée dans la vue
Rapport après génération. Approximative : reparcourt le G-code déjà
généré (G1 selon distance/avance programmée, G0 à une vitesse rapide
SUPPOSÉE de 6000mm/min -- la vraie vitesse rapide de la machine n'est
pas connue ici, ajuster RAPID_FEED si besoin), ignore
accélérations/décélérations réelles. Vérifiée par calcul à la main sur
un G-code de test avant intégration.

NOZZLE (bec LT-80W-AA-PRO, mesures fournies) :
  Cône du foyer vers le haut : diamètre 5mm -> 16mm sur 18mm de hauteur,
  puis cylindre 16mm sur 18mm (le tube d'air démarre 1mm au-dessus du
  sommet du cône, déjà dans l'enveloppe du cylindre -- pas modélisé à
  part). En mode courbe, le transit vérifie désormais, en plus du point
  central, le dégagement à 8mm de rayon (sommet du cône) dans 4
  directions, et relève le Z de transit si nécessaire. Vérifié sur une
  sphère de 50mm avec ce bec : le contrôle ne change quasiment rien sauf
  à moins de 0.1mm du bord visible -- le budget de 18mm de hauteur de
  cône est large par rapport à cette courbure. Utile comme filet de
  sécurité réel, plus qu'un facteur limitant sur cet objet précis.
  Cette vérification n'est active QUE si une sonde exacte (objet 3D de
  référence) est disponible -- pas de double approximation sur de
  l'interpolation. Pendant la GRAVURE elle-même (pas le transit), le Z
  est imposé par le focus correct : un désaccord avec le bec y est
  seulement signalé (avertissement), jamais corrigé automatiquement,
  puisque changer le Z pendant la gravure changerait le focus.

Stratégie relais/faisceau (modes 4 et 5) : M3 $1 une seule fois par
job, modulation S0/S<puissance>, relais AUX3 automatique via
spindle.1.on (rien à piloter manuellement pour ça).

------------------------------------------------------------------------
UTILISATION : chaque mode est une icône/entrée de menu séparée dans la
barre d'outils "Atelier Laser" (cf. commands.py). Sélectionner les
objets voulus AVANT de cliquer sur l'icône (chaque mode a ses propres
attentes de sélection, voir le message si rien n'est sélectionné).
------------------------------------------------------------------------
"""

import bisect
import heapq
import math
import json
import os
import re
import unicodedata
import zipfile
import FreeCAD
import Part
from collections import defaultdict

# Version de l'atelier -- SOURCE UNIQUE, affichée dans le bandeau des
# panneaux et l'en-tête des G-codes. À incrémenter à chaque publication,
# EN MÊME TEMPS que <version> dans package.xml (gestionnaire d'extensions
# FreeCAD), le badge du site (docs/index.html) et la ligne du README.
VERSION = "2.11.0"

# Translittérations non gérées par la décomposition NFKD (qui ne sépare
# pas ces caractères en base ASCII + accent), pour l'assainisseur LinuxCNC.
_LINUXCNC_FALLBACK = str.maketrans({
    "–": "-", "—": "-",       # tirets demi/cadratin
    "’": "'", "‘": "'",       # apostrophes typographiques
    "…": "...", "×": "x", "°": "deg", "µ": "u",
})


def sanitize_gcode_for_linuxcnc(text):
    """Rend le G-code digeste pour l'interpréteur RS274 de LinuxCNC :

    1. Parenthèses imbriquées dans les commentaires : LinuxCNC ferme un
       commentaire au PREMIER ')' et prend la suite de la ligne pour du
       code -- un libellé comme « passe(s) », « operation(s) » ou
       « (par bande de Z) » provoquait donc une erreur. Toute parenthèse
       INTERNE à un commentaire devient crochet [ ].
    2. Caractères non-ASCII (accents français) : RS274 rejette les octets
       non ASCII -- ils sont translittérés (é->e, ç->c...).

    Idempotent (ré-assainir un texte déjà propre ne change rien), donc sûr
    à appliquer plusieurs fois (job combiné = corps déjà assainis)."""
    text = text.translate(_LINUXCNC_FALLBACK)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    out = []
    for line in text.split("\n"):
        start = line.find("(")
        if start == -1:
            out.append(line)
            continue
        # Un seul commentaire par ligne dans le G-code généré (au plus
        # « CODE (commentaire) ») : le contenu va du premier '(' au
        # DERNIER ')', ses parenthèses internes sont neutralisées.
        end = line.rfind(")")
        if end <= start:
            out.append(line)
            continue
        content = line[start + 1:end].replace("(", "[").replace(")", "]")
        out.append(line[:start] + "(" + content + ")" + line[end + 1:])
    # Espaces de fin de ligne : sans effet pour LinuxCNC, mais le dialecte
    # GRBL (sélecteur de broche vide) en laisserait après S/M3/M5.
    return "\n".join(l.rstrip() for l in out)


_GCODE_XY_RX = re.compile(r'([XY])(-?\d+\.?\d*)')


def _gcode_code_part(line):
    """Partie d'une ligne de G-code AVANT un éventuel commentaire."""
    c = line.find("(")
    return line if c == -1 else line[:c]


def gcode_bbox_xy(gcode):
    """Emprise (min_x, max_x, min_y, max_y) du G-code, ou None si aucune
    coordonnée X/Y trouvée. Même lecture que translate_gcode_origin/
    shift_gcode_xy : uniquement les mots X/Y de la partie code de chaque
    ligne."""
    xs, ys = [], []
    for line in (gcode or "").split("\n"):
        for m in _GCODE_XY_RX.finditer(_gcode_code_part(line)):
            (xs if m.group(1) == "X" else ys).append(float(m.group(2)))
    if not xs and not ys:
        return None
    return (min(xs) if xs else 0.0, max(xs) if xs else 0.0,
            min(ys) if ys else 0.0, max(ys) if ys else 0.0)


def shift_gcode_xy(gcode, dx, dy):
    """Décale les mots X/Y de la partie CODE de chaque ligne de (dx, dy) mm.
    Ne touche pas Z, I/J (relatifs), F, S, P ni les commentaires -- sûr tel
    quel : les générateurs discrétisent tout en G1 (aucun arc G2/G3 dont les
    I/J absolus devraient suivre). Sert à poser plusieurs motifs déjà
    générés côte à côte dans un même fichier sans qu'ils se recouvrent (cf.
    generate_gcode_planches_combinees). Renvoie le texte inchangé si vide ou
    si le décalage est nul."""
    if not gcode or (abs(dx) < 1e-9 and abs(dy) < 1e-9):
        return gcode or ""

    def _shift(line):
        c = line.find("(")
        code = line if c == -1 else line[:c]
        rest = "" if c == -1 else line[c:]

        def _repl(m):
            val = float(m.group(2)) + (dx if m.group(1) == "X" else dy)
            if abs(val) < 5e-5:
                val = 0.0
            return "%s%.4f" % (m.group(1), val)
        return _GCODE_XY_RX.sub(_repl, code) + rest

    return "\n".join(_shift(line) for line in gcode.split("\n"))


def translate_gcode_origin(gcode):
    """Recadre le G-code pour que le coin BAS-GAUCHE du parcours (min X,
    min Y) tombe sur (0,0). Le job démarre alors au zéro pièce quel que
    soit l'endroit où le dessin est posé dans le document FreeCAD --
    on n'a plus à placer la géométrie pile sur l'origine. Idempotent une
    fois recadré (min = 0 -> décalage nul). Renvoie le texte inchangé s'il
    n'y a aucune coordonnée."""
    if not gcode:
        return gcode
    bbox = gcode_bbox_xy(gcode)
    if bbox is None:
        return gcode
    xmin, _, ymin, _ = bbox
    return shift_gcode_xy(gcode, -xmin, -ymin)


# Persistance des champs G-code avant/après entre deux exécutions de la
# macro (un run de macro FreeCAD repart de zéro à chaque fois, rien ne
# reste en mémoire Python d'une exécution à l'autre -- il faut un vrai
# fichier sur disque).
CONFIG_FILE = os.path.join(FreeCAD.getUserAppDataDir(), "laser_atelier_config.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        # Fichier présent mais illisible (JSON corrompu...) : avertir au
        # lieu d'échouer en silence -- la PROCHAINE sauvegarde (un simple
        # OK de panneau) repartirait d'un config vide et écraserait le
        # fichier, perdant tous les préréglages matériau sans un mot.
        FreeCAD.Console.PrintWarning(
            "Config {} illisible ({}) : réglages par défaut utilisés. "
            "Sauvegarder depuis l'atelier écrasera ce fichier (préréglages "
            "compris) -- à récupérer/supprimer à la main d'abord si besoin.\n".format(
                CONFIG_FILE, exc))
        return {}


def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Impossible de sauvegarder la config : {}\n".format(exc))


# --------------------------------------------------------------------------
# Photos de résultats (test / calibration)
# --------------------------------------------------------------------------
# On garde une LISTE de photos par « clé » (mode + éventuel matériau, ex.
# « testgrid:MDF ») pour comparer le rendu au réel plus tard. Les fichiers
# vivent DANS le dossier de l'atelier (à côté du code, pour être conservés
# avec lui même si la photo d'origine est effacée) ; la config ne stocke,
# sous le bloc « photos », qu'une liste par clé d'entrées {"file": nom de
# fichier relatif, "description": texte libre -- ex. le défocus/focale
# utilisé, pour ne plus s'y perdre quand on en garde plusieurs}. Un ancien
# enregistrement mono-photo (simple chaîne) ou une liste de noms sans
# description est migré à la volée par `_photo_list`.
# Pas de Qt ici : la vignette est peinte dans le panneau.
PHOTOS_DIRNAME = "photos_resultats"
_WORKBENCH_DIR = os.path.dirname(os.path.abspath(__file__))
_photos_migrated = False


def photos_dir():
    """Dossier des photos de résultats, DANS le dossier de l'atelier (créé au
    besoin). Migre une fois d'un ancien emplacement (app-data) si besoin."""
    d = os.path.join(_WORKBENCH_DIR, PHOTOS_DIRNAME)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Dossier photos indisponible ({}).\n".format(exc))
    _migrate_old_photos(d)
    return d


def _migrate_old_photos(new_dir):
    """Déplace une seule fois (par session) les photos d'un ancien emplacement
    (app-data/laser_atelier_photos) vers le dossier de l'atelier."""
    global _photos_migrated
    if _photos_migrated:
        return
    _photos_migrated = True
    old = os.path.join(FreeCAD.getUserAppDataDir(), "laser_atelier_photos")
    if not os.path.isdir(old) or os.path.abspath(old) == os.path.abspath(new_dir):
        return
    try:
        for fn in os.listdir(old):
            src, dst = os.path.join(old, fn), os.path.join(new_dir, fn)
            if os.path.isfile(src) and not os.path.exists(dst):
                with open(src, "rb") as a, open(dst, "wb") as b:
                    b.write(a.read())
                os.remove(src)
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Migration des photos ignorée ({}).\n".format(exc))


def export_all(dest_path):
    """Exporte TOUS les réglages (config JSON) + toutes les photos de
    résultats dans une archive .zip à `dest_path` -- à ranger en lieu sûr.
    Restauration : dézipper « laser_atelier_config.json » dans le dossier
    app-data de FreeCAD et le dossier « photos_resultats » dans l'atelier.
    Renvoie (ok, message)."""
    try:
        nph = 0
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.isfile(CONFIG_FILE):
                z.write(CONFIG_FILE, "laser_atelier_config.json")
            pd = photos_dir()
            if os.path.isdir(pd):
                for fn in sorted(os.listdir(pd)):
                    fp = os.path.join(pd, fn)
                    if os.path.isfile(fp):
                        z.write(fp, "{}/{}".format(PHOTOS_DIRNAME, fn))
                        nph += 1
        return True, "Sauvegarde créée : réglages + {} photo(s)\n{}".format(nph, dest_path)
    except Exception as exc:
        return False, "Échec de l'export : {}".format(exc)


def import_all(src_path):
    """Restaure une sauvegarde .zip créée par export_all : REMPLACE la config
    (tous les réglages) et rétablit les photos de l'archive. Destructif pour
    les réglages ; applique les nouveaux réglages tout de suite. Renvoie
    (ok, message)."""
    try:
        if not zipfile.is_zipfile(src_path):
            return False, "Ce fichier n'est pas une archive .zip valide."
        with zipfile.ZipFile(src_path) as z:
            names = z.namelist()
            cfg_bytes = None
            if "laser_atelier_config.json" in names:
                cfg_bytes = z.read("laser_atelier_config.json")
                json.loads(cfg_bytes.decode("utf-8"))   # valide AVANT d'écrire
            pd = photos_dir()
            nph = 0
            for n in names:
                if n.startswith(PHOTOS_DIRNAME + "/") and not n.endswith("/"):
                    base = os.path.basename(n)           # anti « zip-slip »
                    if base:
                        with open(os.path.join(pd, base), "wb") as dst:
                            dst.write(z.read(n))
                        nph += 1
            if cfg_bytes is not None:
                with open(CONFIG_FILE, "wb") as dst:
                    dst.write(cfg_bytes)
                _apply_settings_config()                 # applique tout de suite
        return True, "Sauvegarde restaurée : réglages{} + {} photo(s).".format(
            "" if cfg_bytes is not None else " (absents de l'archive)", nph)
    except Exception as exc:
        return False, "Échec de l'import : {}".format(exc)


def _photo_safe(cle):
    """Base de nom de fichier sûre dérivée de la clé (tout caractère non
    alphanumérique devient « _ », ex. « testgrid:MDF » -> « testgrid_MDF »)."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in cle) or "photo"


def _photo_list(cle):
    """Entrées {"file": nom de fichier relatif, "description": texte libre}
    mémorisées pour `cle`, dans l'ordre d'ajout (migre à la volée une
    ancienne valeur mono-photo, ou une liste de noms sans description)."""
    rec = (load_config().get("photos") or {}).get(cle)
    if not rec:
        return []
    if isinstance(rec, str):
        rec = [rec]
    return [e if isinstance(e, dict) else {"file": e, "description": ""} for e in rec]


def result_photos(cle):
    """Photos mémorisées pour `cle`, dans l'ordre d'ajout : liste de
    {"path": chemin absolu, "file": nom relatif, "description": texte libre
    -- ex. le défocus/focale utilisé, utile pour s'y retrouver quand on en
    garde plusieurs}. Ne garde que les fichiers réellement présents."""
    d = photos_dir()
    out = []
    for e in _photo_list(cle):
        p = os.path.join(d, e["file"])
        if os.path.isfile(p):
            out.append({"path": p, "file": e["file"], "description": e.get("description", "")})
    return out


def add_result_photo(cle, source_path, description=""):
    """Copie `source_path` dans le dossier photos et l'AJOUTE (avec sa
    description, optionnelle) à la liste de `cle`. Renvoie le chemin absolu
    stocké, ou None en cas d'échec."""
    ext = os.path.splitext(source_path)[1].lower() or ".jpg"
    base = _photo_safe(cle)
    d = photos_dir()
    # numéro libre GLOBAL (toutes extensions confondues) : Photo 1, 2, 3…
    stems = {os.path.splitext(fn)[0] for fn in os.listdir(d)} if os.path.isdir(d) else set()
    n = 1
    while "{}_{}".format(base, n) in stems:
        n += 1
    dest_rel = "{}_{}{}".format(base, n, ext)
    dest_abs = os.path.join(d, dest_rel)
    try:
        with open(source_path, "rb") as src:
            data = src.read()
        with open(dest_abs, "wb") as dst:
            dst.write(data)
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Photo non enregistrée ({}).\n".format(exc))
        return None
    cfg = load_config()
    photos = cfg.setdefault("photos", {})
    lst = _photo_list(cle)
    lst.append({"file": dest_rel, "description": description})
    photos[cle] = lst
    save_config(cfg)
    return dest_abs


def set_photo_description(cle, filename, description):
    """Change la description mémorisée de la photo `filename` (nom ou
    chemin) de `cle`. Sans effet si cette photo n'est pas dans la liste."""
    cfg = load_config()
    photos = cfg.setdefault("photos", {})
    lst = _photo_list(cle)
    target = os.path.basename(filename)
    for e in lst:
        if os.path.basename(e["file"]) == target:
            e["description"] = description
            photos[cle] = lst
            save_config(cfg)
            return


def delete_result_photo(cle, filename=None):
    """Oublie une photo de `cle` : `filename` (nom OU chemin) désigne la photo
    à retirer ; None les retire toutes. Supprime le fichier + met à jour la
    config."""
    cfg = load_config()
    photos = cfg.get("photos") or {}
    lst = _photo_list(cle)
    if not lst:
        return
    d = photos_dir()
    if filename is None:
        remove, keep = lst, []
    else:
        target = os.path.basename(filename)
        remove = [e for e in lst if os.path.basename(e["file"]) == target]
        keep = [e for e in lst if os.path.basename(e["file"]) != target]
    for e in remove:
        try:
            os.remove(os.path.join(d, e["file"]))
        except OSError:
            pass
    if keep:
        photos[cle] = keep
    else:
        photos.pop(cle, None)
    cfg["photos"] = photos
    save_config(cfg)


# ==========================================================================
# CONFIGURATION COMMUNE (les deux modes)
# ==========================================================================
# Dialecte G-code cible -- réglable en Préférences, PAR PROFIL laser :
#   "linuxcnc" (défaut) : multi-broche $n, T/M6 + G43 H, G64, M3.
#   "grbl"              : GRBL 1.1 classique -- pas de sélecteur de broche,
#     pas de changement d'outil ni de compensation (T/M6/G43 omis), pas de
#     G64 (le lissage de trajectoire est natif, réglé par la junction
#     deviation $11 du contrôleur), armement en M4 (mode laser $32=1 :
#     puissance asservie à la vitesse réelle, comme le HAL PrintNC --
#     l'interdit « jamais de G4 faisceau allumé » s'applique pareil).
#     Prérequis côté machine : $32=1, $30 = échelle S max des Préférences.
#   "grblhal"           : comme "grbl" (M4, pas de $n, pas de G64), MAIS
#     avec le changement d'outil et la compensation T/M6 + G43 H comme
#     LinuxCNC -- grblHAL les supporte quand la table d'outils est
#     compilée (option N_TOOLS). Offsets X/Y + Z par outil comme sur la
#     PrintNC.
GCODE_DIALECT = "linuxcnc"
SPINDLE_SELECT = "$1"
ARM_DWELL_S = 2.0
LASER_TOOL = 100     # numéro (tool.tbl) de l'outil laser -- réglable en Préférences
S_MAX = 1000.0       # échelle de puissance max de la broche laser (valeur S pleine
                     # puissance) -- dépend de la config machine, réglable en Préférences
# Tolérance de lissage de trajectoire (G64 P) des jobs laser, en mm : écart
# maximal toléré à l'intérieur d'un angle pour ne pas avoir à s'y arrêter.
# 0,05 mm est très en dessous du trait brûlé le plus fin mesuré (0,10 mm) et
# 50 fois sous le plus large (2,60 mm) : invisible sur la pièce. Voir
# cmd_path_blend() pour le piège du G64 nu et de l'héritage machine.
PATH_BLEND_TOLERANCE_MM = 0.05


def cmd_tool_comp():
    """Sélection et compensation de l'outil laser en tête de chaque job :
    T<laser> M6 charge l'outil (si le changement d'outil est manuel,
    LinuxCNC demande confirmation -- rappel utile de monter le laser ;
    si T<laser> est déjà chargé, c'est transparent), puis G43 H<laser>
    applique ses offsets X/Y (tool.tbl) et son Z palpé. Sans cela, le Z
    de foyer et les XY seraient interprétés en coordonnées broche, pas
    nez laser. Fonction (pas une constante) pour suivre le numéro
    d'outil des Préférences (LASER_TOOL), réglé PAR PROFIL laser.
    En dialecte GRBL : simple commentaire (pas de table d'outils).
    En grblHAL : T/M6 + G43 H comme LinuxCNC (table d'outils compilée)."""
    if GCODE_DIALECT == "grbl":
        return "(dialecte GRBL : pas de changement d'outil ni de compensation)"
    return ("T{n} M6 (outil laser)\n"
            "G43 H{n} (compensation T{n})".format(n=int(LASER_TOOL)))


def cmd_path_blend():
    """« G64 P<tolérance> » (trajectoire continue LinuxCNC), ou None en
    dialecte GRBL/grblHAL : ils ne connaissent pas G64 (erreur), leur
    planificateur lisse nativement (réglage $11, junction deviation).

    ATTENTION au sens du P, contre-intuitif : un G64 NU ne veut pas dire
    « pas de lissage » mais « lisse à la vitesse maximale, SANS borne de
    déviation ». Ajouter P ne relâche donc pas la machine, il la BORNE.
    Et un job qui n'émet aucun G64 hérite de la ligne de démarrage de la
    machine (RS274NGC_STARTUP_CODE) : sur la PrintNC c'est G64 P0.001,
    soit 1 µm, ce qui force un quasi-arrêt à chaque changement de
    direction -- des dizaines de milliers de fois sur une gravure hachurée.

    D'où PATH_BLEND_TOLERANCE_MM : borné, mais à une valeur sans effet
    visible sur une brûlure large de 0,10 à 2,60 mm."""
    if GCODE_DIALECT in ("grbl", "grblhal"):
        return None
    return "G64 P{:.3f}".format(PATH_BLEND_TOLERANCE_MM)


_CMD_ARM_LINUXCNC = "S0 {sel}\nM67 E0 Q0\nM3 {sel}\nG4 P{dwell:.1f}"
# GRBL en mode laser ($32=1) : M4 = puissance asservie à la vitesse réelle
# (S0 pendant l'armement -> faisceau éteint). {sel} vide en GRBL.
_CMD_ARM_GRBL = "S0\nM4 (armement mode laser GRBL)\nG4 P{dwell:.1f}"
# M3/M5 restent dans tous les cas : c'est l'interlock du laser, pas la
# puissance. Seul le canal de la VALEUR bascule.
_CMD_DISARM_S = "S0 {sel}\nM67 E0 Q0\nM5 {sel}"
# GRBL/grblHAL ne connaissent pas M67 : leur desarmement ne doit surtout pas
# porter la ligne de neutralisation, sinon chaque job finit sur une erreur de
# commande inconnue. Trouve le 30/07/2026 en RELISANT pour la premiere fois ce
# que le dialecte GRBL emet vraiment -- la ligne avait ete ajoutee une heure
# plus tot dans le desarmement PARTAGE, et rien ne l aurait signale : personne
# n avait jamais lance ce dialecte.
_CMD_DISARM_GRBL = "S0 {sel}\nM5 {sel}"
# Les variantes M67 de l'armement et du desarmement sont RIGOUREUSEMENT les
# memes que celles en S direct, et c'est le correctif : chacune neutralise LES
# DEUX canaux, pas seulement le sien.
#
# Le HAL de la PrintNC ADDITIONNE `spindle.1.speed-out` et
# `motion.analog-out-00` (un sum2), ce qui permet de basculer le reglage sans
# recabler. Mais les deux canaux PERSISTENT : un job interrompu en plein vol
# laisse SA valeur en place. Un job M67 avorte a S..Q600, suivi d'un job en S
# direct, aurait donc grave a S+600 partout -- trop fort, et sans un mot. La
# reciproque etait vraie aussi. Chaque job part maintenant des deux canaux a
# zero, quoi qu'ait laisse le precedent.
_CMD_ARM_M67 = _CMD_ARM_LINUXCNC
_CMD_DISARM_M67 = _CMD_DISARM_S
_CMD_BEAM_ON_S = "S{power:.0f} {sel}"
_CMD_BEAM_ON_M67 = "M67 E0 Q{power:.0f}"
_CMD_BEAM_OFF_S = "S0 {sel}"
_CMD_BEAM_OFF_M67 = "M67 E0 Q0"

CMD_ARM = _CMD_ARM_LINUXCNC
CMD_DISARM = _CMD_DISARM_S
CMD_BEAM_ON = _CMD_BEAM_ON_S
CMD_BEAM_OFF = _CMD_BEAM_OFF_S

# --- Canal de la PUISSANCE : S direct, ou M67 synchronisé -----------------
# PROUVÉ le 30/07/2026 sur la PrintNC, par deux fichiers de géométrie
# rigoureusement identique (200 segments de 0,30 mm en X à F800, G64 P0.050,
# laser désarmé) : celui à `S` CONSTANT passe fluide, celui à `S` DIFFÉRENT à
# chaque bloc SACCADE. Un mot `S` entre deux G1 fait donc arrêter la machine,
# même sur des segments parfaitement colinéaires. Conséquence chiffrée : un
# portrait de 172 614 blocs de 0,30 mm annoncé 1h30 et parti pour 4 h, soit
# ~76 ms par bloc là où 0,30 mm à F800 en demande 22 -- et 55 ms est exactement
# le temps d'un déplacement de 0,30 mm avec ARRÊT AUX DEUX BOUTS à 400 mm/s².
#
# `M67 E<n> Q<v>` est la sortie analogique SYNCHRONISÉE avec le mouvement : la
# valeur est appliquée au début du bloc suivant sans vider la file de
# trajectoire. (`M68` est la variante immédiate, et elle ARRÊTE le mouvement --
# ne pas les confondre.) On garde un escalier de puissance, un palier par
# segment, mais la machine ne s'arrête plus entre les paliers.
#
# `M3`/`M5` ne changent pas : c'est `spindle.1.on` qui ferme l'interlock du
# laser. Seul le canal de la VALEUR bascule.
POWER_M67 = False                     # False = S direct (défaut, inchangé)
M67_ANALOG_INDEX = 0                  # E<n> de motion.analog-out-NN


def cmd_power_prefix(power):
    """Ligne(s) à émettre AVANT le mouvement pour poser la puissance.

    Vide en mode S direct (la puissance voyage sur le G1 lui-même) ; un
    `M67` en mode synchronisé, car M67 ne peut PAS tenir sur la ligne du G1 --
    il s'applique au bloc suivant, il lui faut donc sa propre ligne."""
    if POWER_M67:
        return ["M67 E{:.0f} Q{:.0f}".format(M67_ANALOG_INDEX, power)]
    return []


def cmd_power_suffix(power):
    """Ce qui s'ajoute au mouvement lui-même : « S<v> <sel> » en direct, rien
    en M67. Toujours utilisé AVEC `cmd_power_prefix`, jamais seul."""
    if POWER_M67:
        return ""
    return "S{:.0f} {}".format(power, SPINDLE_SELECT)

# --- Réglages utilisateur -------------------------------------------------
# Chaque réglage listé dans _USER_SETTINGS (plus bas) est surchargeable
# SANS TOUCHER AU CODE : via le panneau Préférences de l'atelier (icône
# engrenage), ou à la main dans laser_atelier_config.json, clé "settings" :
#
#   {"settings": {"gcode_dir": "/mnt/srv-partage/Gcode",
#                 "rapid_feed_mm_min": 6000.0, ...}}
#
# Les valeurs ci-dessous (et SPINDLE_SELECT/ARM_DWELL_S plus haut,
# SAFE_MIN_NOZZLE_HEIGHT_MM etc. plus bas) ne sont que les défauts.
GCODE_DIR = "/mnt/srv-partage/Gcode"  # dossier proposé par défaut à la sauvegarde G-code
SECTIONS_ACCORDEON = True             # panneaux : ouvrir une section replie les autres
                                      # (décochable dans Préférences > Interface)
GCODE_PRE_GLOBAL = ""                 # G-code personnalisé GLOBAL inséré avant chaque job
GCODE_POST_GLOBAL = ""                # ... et après chaque job (Préférences ; un seul couple
                                      # pour tous les modes, inséré une fois par job)
def inserer_gcode_perso_global(gcode):
    """Insère le G-code personnalisé GLOBAL (Préférences) dans un programme
    COMPLET, au moment de l'écriture du fichier -- un seul point d'insertion
    pour tous les modes, une seule fois par job (y compris job combiné) :

    - le bloc « avant » juste AVANT l'armement du laser (première commande
      d'armement, CMD_ARM) ; à défaut, après la première ligne ;
    - le bloc « après » juste AVANT la fin de programme (dernier M2) ; à
      défaut, à la fin.

    Sans effet si les deux réglages sont vides. Le texte inséré est assaini
    (accents, parenthèses imbriquées) comme le reste du programme."""
    avant = (GCODE_PRE_GLOBAL or "").strip()
    apres = (GCODE_POST_GLOBAL or "").strip()
    if not gcode or not (avant or apres):
        return gcode
    lignes = gcode.split("\n")
    if avant:
        # CMD_ARM est un gabarit ("M3 S0 {sel}...") : on cible son préfixe
        # littéral, avant le premier champ de format.
        cible = (CMD_ARM or "").split("\n")[0].split("{")[0].strip()
        idx = next((i for i, l in enumerate(lignes)
                    if cible and l.strip().startswith(cible)), 1)
        lignes[idx:idx] = ["(-- G-code personnalisé (avant) --)", avant]
    if apres:
        idx = next((i for i in range(len(lignes) - 1, -1, -1)
                    if lignes[i].strip() == "M2"), len(lignes))
        lignes[idx:idx] = ["(-- G-code personnalisé (après) --)", apres]
    return sanitize_gcode_for_linuxcnc("\n".join(lignes))


GCODE_ORIGIN_BBOX = True              # recadrer chaque G-code écrit pour que le coin bas-
                                      # gauche du parcours (min X, min Y) tombe sur (0,0) :
                                      # le job démarre au zéro pièce quel que soit l'endroit
                                      # du dessin dans le document (Projection et Test
                                      # d'offsets exclus, cf. _write_gcode_with_dialog)
RAPID_FEED_MM_MIN = 6000.0            # vitesse rapide supposée (G0) pour l'estimation de durée
TRAVEL_CLEARANCE_MM = 10.0            # marge de survol ajoutée au Z de travail pour les
                                      # transits/début/fin de job (modes grille et découpe à
                                      # plat -- les modes courbes ont leur champ Marge de
                                      # sécurité par panneau). 0 = transits au Z de travail.
FRAME_POWER = 0.0                     # puissance (S) du faisceau pendant l'aperçu cadrage :
                                      # 0 = laser éteint (défaut), sinon TRÈS FAIBLE (S5-S20)
                                      # juste pour visualiser la zone de travail sans marquer
FRAME_FEED_MM_MIN = 1500.0            # vitesse du tracé de cadrage quand le faisceau est allumé
Z_MAX_FEED_MM_MIN = 1500.0            # vitesse max supposée de l'axe Z (mm/min) -- sert
                                      # uniquement à AVERTIR quand un trait en vague demande
                                      # plus vite (LinuxCNC ralentira le trajet pour respecter
                                      # la vraie limite machine, rien de dangereux)
ACCEL_MM_S2 = 600.0                   # accélération machine RÉELLE (mm/s2) pour l'estimation
                                      # de durée -- n'affecte jamais le G-code. Doit valoir le
                                      # MAX_ACCELERATION du .ini LinuxCNC : à 800 alors que la
                                      # PrintNC tournait à 400, toute estimation sortait deux
                                      # fois trop optimiste, et d'autant plus que le job est
                                      # fait de segments courts (là où l'accélération fait tout
                                      # le temps).
                                      #
                                      # Historique, parce que ce nombre a déjà menti deux fois :
                                      # 800 (jamais vérifié) -> 400 (relevé le 30/07/2026, la
                                      # machine y était) -> 600 (remora-flexi.ini du dépôt
                                      # printnc-config dit MAX_ACCELERATION = 600 sur tous
                                      # les axes). Le seul bon réflexe est de LIRE le .ini,
                                      # jamais de supposer.
                                      #
                                      # Attention si ce chiffre est réexaminé : le portrait
                                      # qui a fait trouver M67 mesurait ~76 ms/bloc pour
                                      # 22,5 ms de coupe pure. Un aller-retour complet sur
                                      # 0,30 mm coûte 54,8 ms à 400 mais 44,7 à 600 -- la
                                      # mesure colle mieux à 400. Soit le Pi tournait encore
                                      # sur une ancienne config, soit l'arrêt-redémarrage
                                      # n'explique pas tout l'écart. Ça ne change rien au
                                      # correctif (M67 supprime l'arrêt quel que soit a),
                                      # seulement à l'estimation de durée.
Z_WORK_MM = 8.0                       # Z de travail (foyer) proposé par défaut dans les
                                      # panneaux -- propriété machine (focale du nez avec le
                                      # zéro Z sur la surface), une seule valeur à entretenir
TRANSIT_MARGIN_MM = 0.5               # marge de survol par défaut des modes marquage (au-
                                      # dessus du Z de travail / du relief pour les transits)
# --- Calibration du point laser (défocus) : PROPRIÉTÉ MACHINE, mesurée
# une fois avec la Bande de calibration défocus puis saisie ici (via les
# Préférences) -- utilisée par Hachures 2D, Gravure remplie, Grille de
# test et le style Vague, au lieu d'être resaisie dans chaque panneau.
SPOT_FOCUS_MM = 0.15                  # diamètre du point AU FOYER (mesuré)
SPOT_TEST_DEFOCUS_MM = 3.0            # défocus de test de la 2e mesure (mm)
SPOT_TEST_DIAMETER_MM = 1.0           # diamètre du point mesuré à ce défocus de test
LABEL_POWER = 600.0                   # étiquettes gravées des tests/planches : puissance (S)
LABEL_FEED = 800.0                    # ... et vitesse d'avance (mm/min) -- par laser, réglés
                                      # une fois dans les Préférences

# (clé JSON, nom de la globale à surcharger, conversion, validation)
_USER_SETTINGS = (
    ("gcode_dialect", "GCODE_DIALECT", lambda v: str(v).strip().lower(),
     lambda v: v in ("linuxcnc", "grbl", "grblhal")),
    ("puissance_par_m67", "POWER_M67", bool, lambda v: isinstance(v, bool)),
    ("gcode_dir", "GCODE_DIR", str, lambda v: bool(v.strip())),
    ("gcode_origin_bbox", "GCODE_ORIGIN_BBOX", bool, lambda v: isinstance(v, bool)),
    ("sections_accordeon", "SECTIONS_ACCORDEON", bool, lambda v: isinstance(v, bool)),
    ("gcode_pre_global", "GCODE_PRE_GLOBAL", str, lambda v: isinstance(v, str)),
    ("gcode_post_global", "GCODE_POST_GLOBAL", str, lambda v: isinstance(v, str)),
    ("spindle_select", "SPINDLE_SELECT", str, lambda v: bool(v.strip())),
    ("laser_tool", "LASER_TOOL", int, lambda v: 1 <= v <= 999),
    ("s_max", "S_MAX", float, lambda v: v > 0),
    ("arm_dwell_s", "ARM_DWELL_S", float, lambda v: v >= 0),
    ("rapid_feed_mm_min", "RAPID_FEED_MM_MIN", float, lambda v: v > 0),
    ("travel_clearance_mm", "TRAVEL_CLEARANCE_MM", float, lambda v: v >= 0),
    ("label_power", "LABEL_POWER", float, lambda v: 0 <= v),
    ("label_feed", "LABEL_FEED", float, lambda v: v > 0),
    ("frame_power", "FRAME_POWER", float, lambda v: v >= 0),
    ("frame_feed_mm_min", "FRAME_FEED_MM_MIN", float, lambda v: v > 0),
    ("z_max_feed_mm_min", "Z_MAX_FEED_MM_MIN", float, lambda v: v > 0),
    ("accel_mm_s2", "ACCEL_MM_S2", float, lambda v: v > 0),
    ("z_work_mm", "Z_WORK_MM", float, lambda v: -100 <= v <= 500),
    ("transit_margin_mm", "TRANSIT_MARGIN_MM", float, lambda v: v >= 0),
    ("spot_focus_mm", "SPOT_FOCUS_MM", float, lambda v: v > 0),
    ("spot_test_defocus_mm", "SPOT_TEST_DEFOCUS_MM", float, lambda v: v > 0),
    ("spot_test_diameter_mm", "SPOT_TEST_DIAMETER_MM", float, lambda v: v > 0),
    ("safe_min_nozzle_height_mm", "SAFE_MIN_NOZZLE_HEIGHT_MM", float, lambda v: v >= 0),
    ("max_thickness_warning_mm", "MAX_THICKNESS_WARNING_MM", float, lambda v: v > 0),
    ("recommended_max_step_mm", "RECOMMENDED_MAX_STEP_MM", float, lambda v: v > 0),
)


def _apply_settings_config():
    """Surcharge les réglages utilisateur depuis la config JSON (clé
    "settings"). Valeur invalide : avertissement et valeur par défaut
    conservée -- même politique que le profil de bec."""
    # Repartir des valeurs LinuxCNC par défaut pour ce que le dialecte
    # surcharge : une bascule grbl -> linuxcnc doit tout restaurer.
    global SPINDLE_SELECT, CMD_ARM, CMD_BEAM_ON, CMD_BEAM_OFF, CMD_DISARM
    global GCODE_DIALECT, POWER_M67
    GCODE_DIALECT = "linuxcnc"
    SPINDLE_SELECT = "$1"
    CMD_ARM = _CMD_ARM_LINUXCNC
    CMD_BEAM_ON = _CMD_BEAM_ON_S
    CMD_BEAM_OFF = _CMD_BEAM_OFF_S
    CMD_DISARM = _CMD_DISARM_S
    POWER_M67 = False
    settings = load_config().get("settings")
    if not isinstance(settings, dict):
        return
    for key, global_name, cast, valid in _USER_SETTINGS:
        if key not in settings:
            continue
        try:
            value = cast(settings[key])
            if not valid(value):
                raise ValueError(value)
        except Exception:
            FreeCAD.Console.PrintWarning(
                "Réglage '{}' invalide dans la config ({!r}) : valeur par "
                "défaut conservée.\n".format(key, settings[key]))
            continue
        globals()[global_name] = value
    # Surcharges des dialectes GRBL/grblHAL (après la boucle :
    # GCODE_DIALECT est lu depuis la config, le reste en découle).
    if GCODE_DIALECT in ("grbl", "grblhal"):
        SPINDLE_SELECT = ""
        CMD_ARM = _CMD_ARM_GRBL
        # GRBL ne connaît pas M67 : la puissance y reste sur le mot S, et son
        # desarmement ne doit pas porter la ligne de neutralisation.
        POWER_M67 = False
        CMD_DISARM = _CMD_DISARM_GRBL
    if POWER_M67:
        # L'armement garde M3 (interlock), mais la puissance passe par M67 :
        # un S0 résiduel serait inoffensif, il serait surtout MENSONGER.
        CMD_ARM = _CMD_ARM_M67
        CMD_BEAM_ON = _CMD_BEAM_ON_M67
        CMD_BEAM_OFF = _CMD_BEAM_OFF_M67
        CMD_DISARM = _CMD_DISARM_M67


def current_settings():
    """Valeurs effectives des réglages utilisateur ({clé JSON: valeur}) --
    pour préremplir le panneau Préférences."""
    return {key: globals()[global_name] for key, global_name, _, _ in _USER_SETTINGS}


def save_settings(new_settings):
    """Écrit les réglages (clés JSON de _USER_SETTINGS) dans la config et
    les applique immédiatement -- pas besoin de redémarrer FreeCAD. Les
    réglages PAR laser (PER_LASER_KEYS) sont aussi recopiés dans le profil
    laser actif, pour qu'il reste à jour."""
    cfg = load_config()
    _ensure_lasers(cfg)
    stored = cfg.get("settings")
    if not isinstance(stored, dict):
        stored = {}
    stored.update(new_settings)
    cfg["settings"] = stored
    prof = cfg.get("lasers", {}).get(cfg.get("active_laser"))
    if isinstance(prof, dict):
        prof_settings = prof.get("settings") or {}
        for k in PER_LASER_KEYS:
            if k in new_settings:
                prof_settings[k] = new_settings[k]
        prof["settings"] = prof_settings
    save_config(cfg)
    _apply_settings_config()


def current_nozzle():
    """Profil de bec effectif, en diamètres/hauteur (mm) -- pour
    préremplir le panneau Préférences."""
    return {"bottom_diameter_mm": NOZZLE_CONE_BOTTOM_RADIUS * 2.0,
            "top_diameter_mm": NOZZLE_CONE_TOP_RADIUS * 2.0,
            "height_mm": NOZZLE_CONE_HEIGHT}


def save_nozzle(bottom_diameter_mm, top_diameter_mm, height_mm):
    """Écrit le profil de bec dans la config (clé "nozzle", même format
    que la surcharge manuelle documentée plus bas) et le réapplique. Le
    profil est aussi recopié dans le profil laser actif."""
    cfg = load_config()
    _ensure_lasers(cfg)
    noz = {"bottom_diameter_mm": bottom_diameter_mm,
           "top_diameter_mm": top_diameter_mm,
           "height_mm": height_mm}
    cfg["nozzle"] = noz
    prof = cfg.get("lasers", {}).get(cfg.get("active_laser"))
    if isinstance(prof, dict):
        prof["nozzle"] = dict(noz)
    save_config(cfg)
    _apply_nozzle_config()


# ==========================================================================
# PROFILS LASER (multi-module)
# ==========================================================================
# Un « profil laser » regroupe les réglages PROPRES à un module laser donné
# (numéro d'outil, calibration du point, Z de travail, échelle S, puissance
# de cadrage, profil du bec). Les réglages de NIVEAU MACHINE (dossier G-code,
# sélecteur broche, cinématique, sécurité) restent communs à tous les lasers.
# Objectif : pouvoir ajouter un 2e module (ex. un IR 1064 nm en T101 à côté
# du bleu en T100) et basculer d'un clic. Le laser actif est reflété dans les
# clés « settings »/« nozzle » de la config (valeurs effectives), de sorte
# que tout le reste du code continue de les lire sans rien changer.
# NOTE : le nuancier et les préréglages matériau restent pour l'instant
# communs -- les rattacher au laser actif est le développement suivant.
PER_LASER_KEYS = ("laser_tool", "s_max", "spot_focus_mm", "spot_test_defocus_mm",
                  "spot_test_diameter_mm", "z_work_mm", "frame_power",
                  "label_power", "label_feed", "gcode_dialect")


def _laser_slug(name):
    """Identifiant court ASCII (clé JSON) à partir d'un nom libre."""
    s = "".join(c.lower() if (c.isalnum() and ord(c) < 128) else "_" for c in name)
    s = "_".join(p for p in s.split("_") if p)
    return s or "laser"


def _current_per_laser(cfg):
    """(réglages PAR laser, profil de bec) effectifs -- pour amorcer un
    profil à partir de l'état courant."""
    settings = cfg.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    key_to_global = {jk: gn for jk, gn, _, _ in _USER_SETTINGS}
    per = {}
    for k in PER_LASER_KEYS:
        per[k] = settings[k] if k in settings else globals()[key_to_global[k]]
    noz = cfg.get("nozzle")
    if not isinstance(noz, dict):
        noz = current_nozzle()
    return per, dict(noz)


def _is_per_laser_data_key(k):
    """Clés de config qui sont des DONNÉES par laser (à ranger dans le profil
    du laser actif) : nuancier, largeurs brûlées, préréglages matériau. Un
    laser bleu 450 nm et un IR 1064 nm n'ont ni les mêmes gris, ni les mêmes
    largeurs, ni les mêmes puissances/vitesses pour un même matériau."""
    return k in ("nuancier", "burn_widths") or k.startswith("presets_")


def _mirror_data_to_active_laser(cfg):
    """Recopie les blocs de données par-laser du top-level vers le profil du
    laser actif (miroir, comme settings/nozzle)."""
    prof = cfg.get("lasers", {}).get(cfg.get("active_laser"))
    if not isinstance(prof, dict):
        return
    for k in [k for k in list(prof) if _is_per_laser_data_key(k)]:
        del prof[k]
    for k in list(cfg):
        if _is_per_laser_data_key(k):
            prof[k] = cfg[k]


def _ensure_lasers(cfg):
    """Migre une config à plat vers la structure à profils : crée un profil
    « Bleu 450 nm » à partir des réglages actuels si « lasers » est absent.
    Range aussi les données par-laser (nuancier/largeurs/préréglages) dans le
    profil actif si elles sont encore seulement au top-level (config
    « scaffold »). Mute cfg, renvoie True si modifié (à sauvegarder)."""
    lasers = cfg.get("lasers")
    if isinstance(lasers, dict) and lasers:
        changed = False
        if cfg.get("active_laser") not in lasers:
            cfg["active_laser"] = next(iter(lasers))
            changed = True
        prof = lasers.get(cfg.get("active_laser"))
        if isinstance(prof, dict) and not any(_is_per_laser_data_key(k) for k in prof):
            for k in list(cfg):
                if _is_per_laser_data_key(k):
                    prof[k] = cfg[k]
                    changed = True
        return changed
    per, noz = _current_per_laser(cfg)
    prof = {"name": "Bleu 450 nm", "settings": per, "nozzle": noz}
    for k in list(cfg):
        if _is_per_laser_data_key(k):
            prof[k] = cfg[k]
    cfg["lasers"] = {"bleu": prof}
    cfg["active_laser"] = "bleu"
    return True


def ensure_laser_profiles():
    """Garantit la présence des profils laser dans la config (migration
    idempotente) et persiste si besoin. À appeler à l'ouverture des
    Préférences."""
    cfg = load_config()
    if _ensure_lasers(cfg):
        save_config(cfg)


def laser_profiles():
    """Liste ordonnée [(id, nom), ...] des profils laser."""
    cfg = load_config()
    _ensure_lasers(cfg)
    return [(lid, prof.get("name", lid)) for lid, prof in cfg["lasers"].items()]


def active_laser_id():
    cfg = load_config()
    _ensure_lasers(cfg)
    return cfg.get("active_laser")


def active_laser_name():
    cfg = load_config()
    _ensure_lasers(cfg)
    lid = cfg.get("active_laser")
    return cfg["lasers"].get(lid, {}).get("name", lid)


def set_active_laser(laser_id):
    """Rend un profil actif : recopie ses réglages PAR laser dans les
    réglages effectifs (settings + nozzle) et les applique. True si OK."""
    cfg = load_config()
    _ensure_lasers(cfg)
    prof = cfg["lasers"].get(laser_id)
    if prof is None:
        return False
    settings = cfg.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings.update(prof.get("settings", {}))
    cfg["settings"] = settings
    if isinstance(prof.get("nozzle"), dict):
        cfg["nozzle"] = dict(prof["nozzle"])
    # données par laser : nuancier / largeurs / préréglages du profil visé
    for k in [k for k in list(cfg) if _is_per_laser_data_key(k)]:
        del cfg[k]
    for k, v in prof.items():
        if _is_per_laser_data_key(k):
            cfg[k] = v
    cfg["active_laser"] = laser_id
    save_config(cfg)
    _apply_settings_config()
    _apply_nozzle_config()
    return True


def add_laser(name, clone_from=None):
    """Crée un profil laser en copiant les réglages PAR laser de clone_from
    (ou du laser actif si None). Ne bascule PAS dessus. Renvoie son id."""
    cfg = load_config()
    _ensure_lasers(cfg)
    lasers = cfg["lasers"]
    src = clone_from if clone_from in lasers else cfg.get("active_laser")
    src_prof = lasers.get(src, {})
    if src_prof.get("settings"):
        per = dict(src_prof["settings"])
        noz = dict(src_prof.get("nozzle") or current_nozzle())
    else:
        per, noz = _current_per_laser(cfg)
    lid = _laser_slug(name)
    base, n = lid, 2
    while lid in lasers:
        lid = "{}_{}".format(base, n)
        n += 1
    lasers[lid] = {"name": name, "settings": per, "nozzle": noz}
    save_config(cfg)
    return lid


def rename_laser(laser_id, name):
    cfg = load_config()
    _ensure_lasers(cfg)
    if laser_id in cfg["lasers"]:
        cfg["lasers"][laser_id]["name"] = name
        save_config(cfg)
        return True
    return False


def delete_laser(laser_id):
    """Supprime un profil (refusé sur le dernier restant). Si c'était le
    laser actif, bascule sur un autre et applique son profil."""
    cfg = load_config()
    _ensure_lasers(cfg)
    lasers = cfg["lasers"]
    if laser_id not in lasers or len(lasers) <= 1:
        return False
    del lasers[laser_id]
    if cfg.get("active_laser") == laser_id:
        new_active = next(iter(lasers))
        cfg["active_laser"] = new_active
        prof = lasers[new_active]
        settings = cfg.get("settings") or {}
        settings.update(prof.get("settings", {}))
        cfg["settings"] = settings
        if isinstance(prof.get("nozzle"), dict):
            cfg["nozzle"] = dict(prof["nozzle"])
        for k in [k for k in list(cfg) if _is_per_laser_data_key(k)]:
            del cfg[k]
        for k, v in prof.items():
            if _is_per_laser_data_key(k):
                cfg[k] = v
    save_config(cfg)
    _apply_settings_config()
    _apply_nozzle_config()
    return True

CHAIN_TOLERANCE = 0.001        # mm : jonction exacte entre segments d'origine
DISCRETIZE_DISTANCE = 0.3      # mm : résolution de tracé (Distance, pas
                                # Deflection -- une droite parfaite n'a
                                # aucune courbure à approximer, Deflection
                                # ne donnerait que 2 points)
TRANSIT_SAMPLE_STEP = 2.0      # mm : résolution du suivi de courbure en transit (mode courbe)
MESH_PROBE_DEVIATION_MM = 0.05 # mm : écart max entre le maillage de sonde et
                                # la vraie surface (tessellation OpenCascade,
                                # voir _MeshZProbe) -- l'erreur Z introduite est
                                # bornée par cette valeur, négligeable face à la
                                # tolérance de focus du laser (~0.1mm) et au
                                # cône de 16mm du bec
NOZZLE_CHECK_INTERVAL_MM = 1.5 # mm : espacement minimal entre deux contrôles
                                # de dégagement du bec pendant la gravure
                                # (indépendant de DISCRETIZE_DISTANCE -- un
                                # contrôle tous les 0.3mm pour un cône de
                                # 16mm de diamètre est un gaspillage pur)

# --- Profil du bec (par défaut : LT-80W-AA-PRO, pièce carrée retirée) ---
# Ces valeurs par défaut sont surchargeables SANS TOUCHER AU CODE dans
# laser_atelier_config.json (dossier de configuration utilisateur de
# FreeCAD), clé "nozzle" :
#
#   {"nozzle": {"bottom_diameter_mm": 5.0,
#               "top_diameter_mm": 16.0,
#               "height_mm": 18.0}}
#
# Pour un bec en TUBE DROIT (section constante jusqu'en bas, sans cône),
# mettre bottom_diameter_mm = top_diameter_mm = diamètre du tube -- le
# modèle conique dégénère alors correctement en cylindre : toute matière
# plus haute que la pointe sous l'empreinte du tube déclenche le
# relevage, ce qui est le comportement attendu. Pour un tube de section
# RECTANGULAIRE, entrer la DIAGONALE de la section : le modèle est de
# révolution, la diagonale couvre le pire cas quelle que soit
# l'orientation du tube par rapport au déplacement.
NOZZLE_CONE_BOTTOM_RADIUS = 2.5   # mm, rayon au point le plus bas du cône (5mm de diamètre)
NOZZLE_CONE_TOP_RADIUS = 8.0      # mm, rayon au sommet du cône (16mm de diamètre)
NOZZLE_CONE_HEIGHT = 18.0         # mm, hauteur du cône (cylindre au-dessus, même rayon)
NOZZLE_CHECK_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _apply_nozzle_config():
    """Surcharge le profil du bec depuis la config JSON (clé "nozzle",
    cf. commentaire ci-dessus). Valeurs invalides (diamètre bas > haut,
    valeurs nulles ou négatives) : avertissement et retour aux valeurs
    par défaut -- un profil de bec faux rendrait le contrôle
    anti-collision silencieusement inopérant."""
    global NOZZLE_CONE_BOTTOM_RADIUS, NOZZLE_CONE_TOP_RADIUS, NOZZLE_CONE_HEIGHT
    noz = load_config().get("nozzle")
    if not isinstance(noz, dict):
        return
    try:
        bottom_r = float(noz.get("bottom_diameter_mm", NOZZLE_CONE_BOTTOM_RADIUS * 2)) / 2.0
        top_r = float(noz.get("top_diameter_mm", NOZZLE_CONE_TOP_RADIUS * 2)) / 2.0
        height = float(noz.get("height_mm", NOZZLE_CONE_HEIGHT))
    except (TypeError, ValueError):
        FreeCAD.Console.PrintWarning(
            "Config 'nozzle' illisible dans {} -- profil de bec par défaut conservé.\n".format(CONFIG_FILE))
        return
    if bottom_r <= 0 or top_r < bottom_r or height <= 0:
        FreeCAD.Console.PrintWarning(
            "Config 'nozzle' incohérente (il faut 0 < bottom_diameter_mm <= top_diameter_mm "
            "et height_mm > 0) -- profil de bec par défaut conservé.\n")
        return
    NOZZLE_CONE_BOTTOM_RADIUS = bottom_r
    NOZZLE_CONE_TOP_RADIUS = top_r
    NOZZLE_CONE_HEIGHT = height


_apply_nozzle_config()


def nozzle_h_min(radius):
    """Hauteur minimale (au-dessus du foyer) à laquelle la matière solide
    du bec commence, pour un rayon horizontal donné."""
    if radius <= NOZZLE_CONE_BOTTOM_RADIUS:
        return 0.0
    if radius >= NOZZLE_CONE_TOP_RADIUS:
        return NOZZLE_CONE_HEIGHT
    t = (radius - NOZZLE_CONE_BOTTOM_RADIUS) / (NOZZLE_CONE_TOP_RADIUS - NOZZLE_CONE_BOTTOM_RADIUS)
    return t * NOZZLE_CONE_HEIGHT


def nozzle_clearance_z(x, y, z_center, height_probe, margin):
    """Vérifie le dégagement du bec (modèle conique) autour de (x,y), pas
    seulement au centre. Renvoie le Z (natif) à utiliser -- relevé si un
    point voisin, à un rayon où le bec est déjà large, s'avère plus haut
    que prévu."""
    best = z_center
    h_min = nozzle_h_min(NOZZLE_CONE_TOP_RADIUS)
    for dx, dy in NOZZLE_CHECK_DIRECTIONS:
        ox = x + dx * NOZZLE_CONE_TOP_RADIUS
        oy = y + dy * NOZZLE_CONE_TOP_RADIUS
        z_off = height_probe(ox, oy)
        if z_off is None:
            continue
        required = z_off + margin - h_min
        if required > best:
            best = required
    return best


# ==========================================================================
# SEGMENTS / CHAÎNAGE (commun aux deux modes)
# ==========================================================================
def get_all_edges_from_selection(selection):
    """Récupère tous les segments des objets/sous-éléments sélectionnés.
    `.Edges` récupère déjà tout, quelle que soit la profondeur
    d'imbrication -- pas de récursion manuelle sur SubShapes (double
    comptage garanti sinon). Un sous-élément qui n'est PAS une arête
    (Face, Wire...) fournit ses arêtes de BORD : sélectionner la face
    d'un tracé SVG importé (« Face1 », l'objet EST une face) revient à
    marquer son contour -- sinon aucune arête n'était collectée et le
    marquage se plaignait « aucun segment trouvé »."""
    all_edges = []
    for sel_obj in selection:
        obj = sel_obj.Object
        subnames = sel_obj.SubElementNames if sel_obj.HasSubObjects else []
        if subnames:
            for sub in subnames:
                shape = obj.getSubObject(sub)
                if isinstance(shape, Part.Edge):
                    all_edges.append(shape)
                elif shape is not None and getattr(shape, "Edges", None):
                    all_edges.extend(shape.Edges)
        elif hasattr(obj, 'Shape'):
            all_edges.extend(obj.Shape.Edges)
    return all_edges


def _round_key(p, ndigits=4):
    return (round(p.x, ndigits), round(p.y, ndigits), round(p.z, ndigits))


def chain_edges(edges, distance=DISCRETIZE_DISTANCE, tolerance=CHAIN_TOLERANCE):
    """Discrétise chaque edge puis regroupe ceux qui se touchent bout à
    bout (jonction exacte, à `tolerance` près) en chaînes continues.
    Testé (50 essais aléatoires, ordre/sens mélangés) avant intégration."""
    segments = []
    for e in edges:
        try:
            pts = e.discretize(Distance=distance)
        except Exception:
            # Arête dégénérée (longueur quasi nulle, BSpline malade d'un
            # import SVG) : on retombe sur ses sommets plutôt que de faire
            # échouer toute la génération.
            pts = [v.Point for v in getattr(e, "Vertexes", [])]
        if len(pts) >= 2:
            segments.append(pts)

    index = defaultdict(list)
    for idx, seg in enumerate(segments):
        index[_round_key(seg[0])].append((idx, 'start'))
        index[_round_key(seg[-1])].append((idx, 'end'))

    used = [False] * len(segments)
    chains = []

    for i in range(len(segments)):
        if used[i]:
            continue
        used[i] = True
        chain = list(segments[i])

        extended = True
        while extended:
            extended = False
            for (j, which) in index.get(_round_key(chain[-1]), []):
                if used[j]:
                    continue
                seg = segments[j]
                if which == 'start':
                    chain.extend(seg[1:])
                else:
                    chain.extend(list(reversed(seg))[1:])
                used[j] = True
                extended = True
                break

        extended = True
        while extended:
            extended = False
            for (j, which) in index.get(_round_key(chain[0]), []):
                if used[j]:
                    continue
                seg = segments[j]
                if which == 'end':
                    chain[0:0] = seg[:-1]
                else:
                    chain[0:0] = list(reversed(seg))[:-1]
                used[j] = True
                extended = True
                break

        chains.append(chain)

    return chains


def order_chains_by_proximity(chains):
    """Réordonne des chaînes (chacune une liste de points, typiquement la
    sortie de chain_edges) par PLUS PROCHE VOISIN GLOUTON : à chaque étape,
    part de la fin de la chaîne précédente et choisit la chaîne restante
    la plus proche, dans le sens (normal ou inversé) qui minimise le saut.
    Le tracé de chaque chaîne n'est jamais modifié, seul son SENS peut
    l'être -- sans effet sur le rendu pour tous les styles de trait
    existants (le style "degrade" calcule son décalage depuis la position
    de chaque point, pas depuis l'ordre de parcours).

    Distance en XY seulement (le Z suit le relief séparément pendant le
    transit, cf. la boucle de generate_gcode_curved -- même convention).

    Sur un remplissage complexe (hachures coupées par des trous : orbites,
    cavités...), le zigzag ligne-par-ligne de generate_hatch_edges seul
    laisse de GROS sauts d'un bout à l'autre de la pièce dès qu'une ligne
    a un nombre de segments différent de la précédente -- mesuré sur le
    crâne réel de l'atelier (9268 chaînes) : 56 m de trajet à vide ramenés
    à 5,1 m (-91 %), pour une longueur gravée rigoureusement identique.

    La recherche du plus proche passe par une GRILLE (même idée que les
    bandes de generate_hatch_edges) explorée en anneaux croissants autour
    du point courant : on s'arrête dès que le meilleur candidat trouvé est
    plus près que le bord du prochain anneau. Le critère retenu est donc
    le même qu'une recherche exhaustive, sans son coût quadratique -- 25 s
    -> 0,16 s sur ce crâne, assez rapide pour tourner à chaque génération
    sans figer l'interface. À une nuance près : sur des hachures régulières
    les ex æquo exacts sont fréquents, et grille et parcours exhaustif ne
    les départagent pas dans le même ordre -- d'où un trajet final qui peut
    différer de ~1 % dans un sens ou dans l'autre. Sans importance ici (les
    deux restent à -91 %), mais c'est pourquoi un test ne peut comparer les
    deux au millimètre que sur des points sans ex æquo."""
    remaining = list(chains)
    if not remaining:
        return []

    xs = [p.x for c in remaining for p in (c[0], c[-1])]
    ys = [p.y for c in remaining for p in (c[0], c[-1])]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    # Maille visant une grille ~racine(n) x racine(n) : assez fine pour
    # que le premier anneau suffise presque toujours, assez large pour ne
    # pas parcourir des milliers de cases vides. Dimensionnée sur la plus
    # grande ÉTENDUE et non sur l'aire : des chaînes toutes alignées (une
    # seule ligne de hachure, un texte sur une ligne) donnent une aire
    # nulle, donc une maille microscopique et une explosion du nombre
    # d'anneaux à parcourir.
    etendue = max(x1 - x0, y1 - y0, 1e-9)
    maille = max(etendue / max(int(math.sqrt(len(remaining))), 1), 1e-6)

    def _case(p):
        return (int((p.x - x0) / maille), int((p.y - y0) / maille))

    grille = defaultdict(list)
    for idx, c in enumerate(remaining):
        grille[_case(c[0])].append((idx, 0))
        grille[_case(c[-1])].append((idx, 1))

    prise = [False] * len(remaining)
    prise[0] = True
    ordered = [remaining[0]]
    cur = remaining[0][-1]

    for _ in range(len(remaining) - 1):
        cx, cy = _case(cur)
        best_idx, best_dist, best_rev = None, None, False
        anneau = 0
        while True:
            for ix in range(cx - anneau, cx + anneau + 1):
                for iy in range(cy - anneau, cy + anneau + 1):
                    # Anneau = bord du carré seulement (l'intérieur a déjà
                    # été vu au tour précédent).
                    if anneau and abs(ix - cx) != anneau and abs(iy - cy) != anneau:
                        continue
                    for (idx, bout) in grille.get((ix, iy), ()):
                        if prise[idx]:
                            continue
                        p = remaining[idx][0] if bout == 0 else remaining[idx][-1]
                        d = math.hypot(p.x - cur.x, p.y - cur.y)
                        if best_dist is None or d < best_dist:
                            best_dist, best_idx, best_rev = d, idx, bout == 1
            # Tout ce qui reste dehors est à plus de anneau*maille : dès que
            # le candidat trouvé fait mieux, inutile d'élargir.
            if best_dist is not None and best_dist <= anneau * maille:
                break
            anneau += 1
        prise[best_idx] = True
        chain = remaining[best_idx]
        if best_rev:
            chain = list(reversed(chain))
        ordered.append(chain)
        cur = chain[-1]
    return ordered


# ==========================================================================
# TEXTE MONO-TRAIT (police Hershey Sans 1-stroke)
# ==========================================================================
# Un vrai « trait simple » pour graver du texte : chaque lettre est dessinée
# d'un seul trait par branche (comme un traceur à plume), pas en contour
# rempli. Les glyphes vivent dans hershey_font.py (données Hershey, domaine
# public). On produit des arêtes Part que l'utilisateur grave ensuite avec
# le mode Marquage (styles, suivi de surface, préréglages, job combiné).

# Polices mono-trait disponibles (clé interne -> libellé affiché). Chacune
# vit dans son propre module hershey_font[_clé].py (même structure : GLYPHES/
# CAP_HEIGHT/ADV_DEFAULT), généré depuis la police SVG Hershey correspondante
# -- voir hershey_font.py pour la provenance. "sans" est le défaut historique ;
# n'ajouter ici que des polices réellement MONO-TRAIT (un seul passage de
# plume) -- la plupart des variantes Hershey "Med"/"Bold"/"Serif" dessinent
# en fait CHAQUE trait en double (façon contour) et ne conviennent pas à ce
# mode, qui a précisément pour but de l'éviter.
HERSHEY_FONTS = {
    "sans": "Hershey Sans (bâton, défaut)",
    "script": "Hershey Script (cursive)",
}


def _hershey_module(font):
    """Module de données (GLYPHES/CAP_HEIGHT/ADV_DEFAULT) pour la police
    mono-trait `font` (clé de HERSHEY_FONTS). Repli silencieux sur la
    police par défaut si la clé est inconnue ou son module introuvable ;
    si la police par défaut elle-même est introuvable, l'exception remonte
    (les appelants savent déjà l'afficher proprement)."""
    import importlib
    nom = "hershey_font_" + font if font and font != "sans" else "hershey_font"
    try:
        return importlib.import_module(nom)
    except Exception:
        if font != "sans":
            return _hershey_module("sans")
        raise


def _mono_line_width(line, hf, scale, char_spacing):
    """Largeur (mm) d'UNE ligne de texte mono-trait -- factorisé pour que
    single_line_text_to_edges et single_line_text_extent ne dupliquent pas
    le même parcours caractère par caractère."""
    x = 0.0
    for ch in line:
        g = hf.GLYPHES.get(ch)
        x += (g[0] if g else hf.ADV_DEFAULT) * scale + char_spacing
    return x - char_spacing if line else 0.0


def single_line_text_to_edges(text, height=10.0, char_spacing=0.0,
                              line_spacing=1.6, z=0.0, x0=0.0, y0=0.0,
                              align="left", font="sans"):
    """Texte -> arêtes Part en police mono-trait. `height` = hauteur de
    capitale (mm) ; `char_spacing` = espace ajouté entre lettres (mm) ;
    `line_spacing` = interligne en multiples de la hauteur ; `font` = clé de
    HERSHEY_FONTS. `align` : "left" (défaut, la ligne part de x0),
    "center"/"right" (calée sur la plus large du bloc), ou "justify" (les
    espaces internes sont étirés pour atteindre la largeur de la plus
    longue -- sans effet sur une ligne d'un seul mot, faute d'espace à
    étirer) -- ou une LISTE d'un de ces mots par ligne (alignement
    indépendant par ligne, comme un traitement de texte ; une liste plus
    courte que le nombre de lignes complète en "left"). L'alignement ne
    change jamais l'encombrement global (seule la position des lignes les
    plus courtes bouge à l'intérieur). Origine : ligne de base de la 1re
    ligne en (x0, y0) (lettres au-dessus), lignes suivantes en dessous.
    Renvoie [] si la police est absente ou le texte vide."""
    try:
        hf = _hershey_module(font)
    except Exception:
        FreeCAD.Console.PrintError(
            "Police mono-trait indisponible (hershey_font.py manquant).\n")
        return []
    scale = float(height) / float(hf.CAP_HEIGHT)
    line_pitch = line_spacing * height
    lines = text.replace("\r", "").split("\n")
    widths = [_mono_line_width(line, hf, scale, char_spacing) for line in lines]
    maxw = max(widths) if widths else 0.0
    if isinstance(align, (list, tuple)):
        aligns = list(align) + ["left"] * (len(lines) - len(align))
    else:
        aligns = [align] * len(lines)
    edges = []
    y_line = y0
    for line, lw, al in zip(lines, widths, aligns):
        n_spaces = line.count(" ")
        extra = 0.0
        if al == "center":
            x = x0 + (maxw - lw) / 2.0
        elif al == "right":
            x = x0 + (maxw - lw)
        elif al == "justify" and n_spaces > 0 and lw < maxw - 1e-6:
            x = x0
            extra = (maxw - lw) / n_spaces
        else:
            x = x0
        for ch in line:
            g = hf.GLYPHES.get(ch)
            if g is None:
                x += hf.ADV_DEFAULT * scale + char_spacing + (extra if ch == " " else 0.0)
                continue
            adv, strokes = g
            for st in strokes:
                pts = [FreeCAD.Vector(x + px * scale, y_line + py * scale, z)
                       for px, py in st]
                for i in range(len(pts) - 1):
                    if pts[i].distanceToPoint(pts[i + 1]) > 1e-7:
                        edges.append(Part.LineSegment(pts[i], pts[i + 1]).toShape())
            x += adv * scale + char_spacing + (extra if ch == " " else 0.0)
        y_line -= line_pitch
    return edges


def single_line_text_extent(text, height=10.0, char_spacing=0.0, line_spacing=1.6,
                            font="sans"):
    """(largeur_mm, hauteur_mm) approximative du texte mono-trait, sans
    construire d'arêtes -- pour l'aperçu d'encombrement du panneau. Valable
    quel que soit l'alignement (qui ne change pas l'encombrement global)."""
    try:
        hf = _hershey_module(font)
    except Exception:
        return 0.0, 0.0
    scale = float(height) / float(hf.CAP_HEIGHT)
    lines = text.replace("\r", "").split("\n") or [""]
    maxw = max((_mono_line_width(line, hf, scale, char_spacing) for line in lines),
              default=0.0)
    h = height + (len(lines) - 1) * line_spacing * height
    return maxw, h


def create_single_line_text_object(text, height=10.0, char_spacing=0.0,
                                   line_spacing=1.6, align="left", obj=None,
                                   font="sans"):
    """Crée (ou met à jour si `obj` est fourni -- aperçu en direct pendant
    la frappe, cf. TaskPanelText) un objet fil « TexteTraitSimple » (texte
    en police mono-trait `font`, clé de HERSHEY_FONTS) dans le document, à
    sélectionner puis graver avec Marquage. Texte vide ou sans caractère
    traçable : vide la forme de `obj` (sans le supprimer) plutôt que
    d'échouer. Renvoie (objet, erreur)."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None, "Ouvre (ou crée) un document d'abord."
    edges = (single_line_text_to_edges(text, height, char_spacing, line_spacing,
                                       align=align, font=font)
              if (text or "").strip() else [])
    if not edges:
        if obj is not None:
            obj.Shape = Part.Compound([])
            doc.recompute()
        return obj, ("Saisis un texte." if not (text or "").strip()
                     else "Aucun caractère traçable dans ce texte.")
    if obj is None:
        obj = doc.addObject("Part::Feature", "TexteTraitSimple")
    obj.Shape = Part.Compound(edges)
    premiere = next((l for l in text.splitlines() if l.strip()), "texte")
    obj.Label = "Texte « {} »".format(premiere.strip()[:24])
    doc.recompute()
    return obj, None


# ==========================================================================
# MODE 0a : GÉNÉRATION DE HACHURES 2D (adapté de hachure.fcmacro)
# ==========================================================================
def _plane_basis(face):
    """Repère local (U, V) d'une face plane. Gère aussi les faces
    GÉOMÉTRIQUEMENT planes portées par une surface non-Plane (import
    SVG/DXF : souvent des B-splines planes, sans attribut Axis) : la
    normale est prise au milieu du domaine paramétrique, l'origine au
    centre de masse."""
    surf = face.Surface
    if hasattr(surf, "Axis") and hasattr(surf, "Position"):
        normal = FreeCAD.Vector(surf.Axis).normalize()
        origin = FreeCAD.Vector(surf.Position)
    else:
        u0, u1, v0, v1 = face.ParameterRange
        normal = FreeCAD.Vector(
            face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)).normalize()
        origin = FreeCAD.Vector(face.CenterOfMass)
    ref = FreeCAD.Vector(1, 0, 0)
    if abs(normal.dot(ref)) > 0.9:
        ref = FreeCAD.Vector(0, 1, 0)
    u_axis = normal.cross(ref).normalize()
    v_axis = normal.cross(u_axis).normalize()
    return origin, u_axis, v_axis


def _to_uv(point, origin, u_axis, v_axis):
    d = point - origin
    return d.dot(u_axis), d.dot(v_axis)


def _to_xyz(u, v, origin, u_axis, v_axis):
    return origin + u_axis * u + v_axis * v


def _aire_signee_2d(pts):
    """Aire signée d'un polygone fermé [(x, y), ...] (positive = CCW)."""
    s = 0.0
    for i in range(len(pts) - 1):
        s += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return s / 2.0


def _point_dans_polygone(x, y, pts):
    """Parité des croisements (even-odd) : le point est-il dans le polygone ?"""
    dedans = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            if x < xi + (y - yi) / (yj - yi) * (xj - xi):
                dedans = not dedans
        j = i
    return dedans


def _faces_rapides_depuis_fils(wires, deflection=0.02):
    """Construit les faces (extérieur + trous, îlots compris) SANS
    FaceMakerBullseye, dont le tri d'imbrication est en O(n²) coûteux
    (mesuré : 10,5 s sur un tracé SVG importé de 179 fils, contre 0,4 s
    ici, pour un hachurage strictement identique).

    Chemin : chaque fil est re-polygonisé (flèche `deflection` mm, même
    ordre de grandeur que la tolérance d'import SVG) ; un fil dont la
    face solo ne se tessellise pas (auto-intersection...) est réparé par
    fix(), qui le scinde en fils simples ; l'imbrication est classée en
    pur Python (parité des contenances, préfiltre par bbox) ; chaque fil
    de profondeur paire devient une face Part.Face([extérieur CCW] +
    [trous directs CW]) -- l'orientation explicite est OBLIGATOIRE, sans
    elle les trous s'ADDITIONNENT à l'aire au lieu de se soustraire.

    Renvoie la liste de faces, ou None si le lot ne s'y prête pas
    (fils non coplanaires en Z, réparation impossible, tessellation ou
    aire finale incohérentes) : l'appelant retombe alors sur Bullseye.
    Restriction assumée : plan Z=constante uniquement (imports SVG/DXF,
    sketches XY) -- un plan quelconque part sur Bullseye."""
    try:
        polys = []          # [(points 2D CCW fermés, z)]
        z_ref = None
        for w in wires:
            pts = w.discretize(Deflection=deflection)
            if len(pts) < 3:
                return None
            if pts[0].distanceToPoint(pts[-1]) > 1e-6:
                pts.append(pts[0])
            for p in pts:
                if z_ref is None:
                    z_ref = p.z
                elif abs(p.z - z_ref) > 1e-6:
                    return None  # pas coplanaire en Z : Bullseye
            polys.append([(p.x, p.y) for p in pts])

        # Test solo : la face d'un fil sain se tessellise. Sinon le fil
        # s'auto-intersecte : fix() le répare en le SCINDANT en fils
        # simples (c'est ce que Bullseye faisait silencieusement).
        # ATTENTION : l'aire signée ne sert qu'à ORIENTER -- un nœud
        # papillon a une aire signée quasi NULLE (ses lobes s'annulent)
        # tout en couvrant une vraie surface, il passe donc lui aussi
        # par la réparation, pas à la poubelle.
        sains = []
        for p2 in polys:
            aire = _aire_signee_2d(p2)
            if abs(aire) > 1e-9:
                p2o = p2 if aire > 0 else p2[::-1]
                wpoly = Part.makePolygon(
                    [FreeCAD.Vector(x, y, z_ref) for x, y in p2o])
                fsolo = Part.Face(wpoly)
                if fsolo.isValid() and len(fsolo.tessellate(0.05)[1]) > 0:
                    sains.append(p2o)
                    continue
            else:
                try:
                    fsolo = Part.Face(Part.makePolygon(
                        [FreeCAD.Vector(x, y, z_ref) for x, y in p2]))
                except Exception:
                    continue  # fil réellement dégénéré : rien à remplir
            frep = fsolo.copy()
            frep.fix(deflection, 1e-7, deflection)
            if not frep.isValid():
                if abs(aire) < 1e-3:
                    continue  # sliver irréparable : le contour le couvre
                return None
            for wf in frep.Wires:
                pts = wf.discretize(Deflection=deflection)
                if pts[0].distanceToPoint(pts[-1]) > 1e-6:
                    pts.append(pts[0])
                p2f = [(p.x, p.y) for p in pts]
                aire_f = _aire_signee_2d(p2f)
                if abs(aire_f) < 1e-3:
                    continue
                sains.append(p2f if aire_f > 0 else p2f[::-1])
        if not sains:
            return None

        # Imbrication : profondeur = nombre de polygones contenant le
        # premier sommet (les fils ne se croisent pas entre eux, comme
        # l'exige déjà Bullseye) ; préfiltre bbox avant le test exact.
        bbs = [(min(x for x, y in p), min(y for x, y in p),
                max(x for x, y in p), max(y for x, y in p)) for p in sains]
        n = len(sains)
        contenants = [[] for _ in range(n)]
        for i in range(n):
            xi, yi = sains[i][0]
            for j in range(n):
                if i == j:
                    continue
                b, bi = bbs[j], bbs[i]
                if not (b[0] <= bi[0] and bi[2] <= b[2]
                        and b[1] <= bi[1] and bi[3] <= b[3]):
                    continue
                if _point_dans_polygone(xi, yi, sains[j]):
                    contenants[i].append(j)
        prof = [len(c) for c in contenants]

        faces = []
        aire_attendue = 0.0
        for i in range(n):
            if prof[i] % 2:
                continue
            ws = [Part.makePolygon(
                [FreeCAD.Vector(x, y, z_ref) for x, y in sains[i]])]
            aire_attendue += _aire_signee_2d(sains[i])
            for k in range(n):
                if prof[k] == prof[i] + 1 and i in contenants[k]:
                    ws.append(Part.makePolygon(
                        [FreeCAD.Vector(x, y, z_ref)
                         for x, y in sains[k][::-1]]))
                    aire_attendue -= _aire_signee_2d(sains[k])
            faces.append(Part.Face(ws))

        # Contrôle final : tessellation non vide (le hachurage repose
        # dessus) et aire cohérente avec les polygones. isValid() peut
        # rester False (fils tangents entre eux) sans gêner le pipeline.
        if not faces:
            return None
        for f in faces:
            if len(f.tessellate(0.05)[1]) == 0:
                return None
        aire = sum(f.Area for f in faces)
        if aire_attendue <= 0 or abs(aire - aire_attendue) > 0.005 * aire_attendue:
            return None
        return faces
    except Exception:
        return None


def _faces_from_any_shape(shape, label="?"):
    """Faces planes fermées d'une forme QUELCONQUE : faces existantes,
    fils fermés (Sketch/Draft), ou ARÊTES LIBRES chaînées en fils
    (Compound d'un import DXF/SVG : ni faces ni fils, juste des edges --
    Part.sortEdges les regroupe, les chaînes fermées deviennent des
    faces via Bullseye, trous compris). Au-delà de quelques fils, un
    chemin rapide sans Bullseye prend le relais (cf.
    _faces_rapides_depuis_fils), avec repli Bullseye au moindre doute."""
    if shape is None:
        return []
    if getattr(shape, "Faces", None):
        return list(shape.Faces)
    # Compound de compounds (Motif_Projete depuis v1.79.5) : chaque
    # sous-compound est UN motif d'origine -- ses faces se reconstruisent
    # INDÉPENDAMMENT, sinon le pair/impair global sur l'ensemble des fils
    # inverse des zones (sémantique SVG : un remplissage par <path>,
    # superposés ensuite).
    if getattr(shape, "ShapeType", "") == "Compound":
        sous_compounds = [s for s in getattr(shape, "SubShapes", [])
                          if getattr(s, "ShapeType", "") == "Compound"]
        if sous_compounds:
            faces = []
            for s in sous_compounds:
                faces.extend(_faces_from_any_shape(s, label))
            restes = [s for s in shape.SubShapes
                      if getattr(s, "ShapeType", "") != "Compound"]
            if restes:
                faces.extend(_faces_from_any_shape(Part.Compound(restes), label))
            return faces
    wires = [w for w in getattr(shape, "Wires", []) if w.isClosed()]
    if not wires and getattr(shape, "Edges", None):
        for grp in Part.sortEdges(list(shape.Edges)):
            try:
                w = Part.Wire(grp)
                if w.isClosed():
                    wires.append(w)
            except Exception:
                pass
    if not wires:
        return []
    if len(wires) >= 12:
        # Le tri d'imbrication de Bullseye devient prohibitif quand les
        # fils se comptent en dizaines (imports SVG/DXF) : chemin rapide
        # d'abord, il rend None au moindre doute.
        rapides = _faces_rapides_depuis_fils(wires)
        if rapides:
            return rapides
    try:
        return list(Part.makeFace(wires, "Part::FaceMakerBullseye").Faces)
    except Exception:
        # Fils incompatibles en un seul appel (plans/imbrications mêlés) :
        # une face par fil, les trous sont alors perdus mais on grave.
        faces = []
        for w in wires:
            try:
                faces.extend(Part.makeFace([w], "Part::FaceMakerBullseye").Faces)
            except Exception:
                pass
        if not faces:
            FreeCAD.Console.PrintWarning(
                "Impossible de créer une face à partir de : {} (contours "
                "ouverts ?)\n".format(label))
        return faces


def get_faces_from_selection_for_hatch(selection):
    """Extrait les faces planes fermées depuis la sélection : Face directe,
    Draft/Part avec faces, Sketch à fils fermés, ou Compound d'arêtes
    (import DXF/SVG) -- sélection entière ou sous-éléments (une face, des
    arêtes formant un contour fermé)."""
    faces = []
    for sel_obj in selection:
        obj = sel_obj.Object
        subnames = sel_obj.SubElementNames if sel_obj.HasSubObjects else []
        if subnames:
            sub_shapes = [obj.getSubObject(sub) for sub in subnames]
            sub_shapes = [sh for sh in sub_shapes if sh is not None]
            direct = [sh for sh in sub_shapes if getattr(sh, "ShapeType", "") == "Face"]
            for sh in direct:
                faces.append(sh)
            rest = [sh for sh in sub_shapes if getattr(sh, "ShapeType", "") != "Face"]
            if rest:
                # Arêtes/fils sélectionnés : les chaîner ENSEMBLE (un contour
                # cliqué arête par arête doit former une seule face).
                edges = []
                for sh in rest:
                    edges.extend(getattr(sh, "Edges", []) or [])
                if edges:
                    comp = Part.Compound(edges)
                    faces.extend(_faces_from_any_shape(comp, obj.Label))
        elif hasattr(obj, 'Shape'):
            faces.extend(_faces_from_any_shape(obj.Shape, obj.Label))
    return faces


def generate_hatch_edges(faces, spacing, angle_deg):
    """Génère les lignes de hachure (Boustrophédon/zigzag), renvoie une
    liste de Part.Edge.

    Le découpage de chaque ligne par les faces (trous inclus) se fait par
    tessellation des faces UNE FOIS puis clipping paramétrique 2D de la
    ligne contre chaque triangle (intersection d'intervalles par
    demi-plans, quelques flops par triangle) -- remplace l'ancienne
    opération booléenne OpenCascade `common` PAR LIGNE ET PAR FACE
    (mesurée au profileur à 90%+ du temps : des dizaines de milliers
    d'appels sur un remplissage fin de texte). Les faces étant planes,
    la tessellation est exacte sur le plan ; seule la polygonisation des
    bords courbes introduit un écart, borné par MESH_PROBE_DEVIATION_MM
    (négligeable face au kerf)."""
    if not faces:
        return []

    origin, u_axis, v_axis = _plane_basis(faces[0])

    umin, umax, vmin, vmax = [], [], [], []
    for f in faces:
        bb = f.BoundBox
        for x in (bb.XMin, bb.XMax):
            for y in (bb.YMin, bb.YMax):
                for z in (bb.ZMin, bb.ZMax):
                    u, v = _to_uv(FreeCAD.Vector(x, y, z), origin, u_axis, v_axis)
                    umin.append(u); umax.append(u)
                    vmin.append(v); vmax.append(v)

    u_min, u_max = min(umin), max(umax)
    v_min, v_max = min(vmin), max(vmax)
    cu, cv = (u_min + u_max) / 2.0, (v_min + v_max) / 2.0
    diag = math.hypot(u_max - u_min, v_max - v_min) + spacing * 2.0

    ang = math.radians(angle_deg)
    dir_line = (math.cos(ang), math.sin(ang))
    dir_step = (-math.sin(ang), math.cos(ang))

    # Tessellation des faces en triangles 2D (UV), orientés CCW
    tris = []
    for f in faces:
        verts, facets = f.tessellate(MESH_PROBE_DEVIATION_MM)
        uv = [_to_uv(p, origin, u_axis, v_axis) for p in verts]
        for i1, i2, i3 in facets:
            a, b, c = uv[i1], uv[i2], uv[i3]
            det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
            if abs(det) < 1e-12:
                continue
            if det < 0:
                b, c = c, b
            tris.append((a, b, c))

    # Index 1D : chaque triangle est rangé dans les bandes de hachures
    # (indices i) que couvre sa projection sur dir_step -- chaque ligne ne
    # teste ensuite que les triangles de sa propre bande.
    n_lines = int(diag / spacing) + 2
    bands = defaultdict(list)
    for idx, (a, b, c) in enumerate(tris):
        offs = [(p[0] - cu) * dir_step[0] + (p[1] - cv) * dir_step[1] for p in (a, b, c)]
        i0 = int(math.ceil((min(offs) - 1e-9) / spacing))
        i1 = int(math.floor((max(offs) + 1e-9) / spacing))
        for i in range(max(i0, -n_lines), min(i1, n_lines) + 1):
            bands[i].append(idx)

    hatch_edges = []
    half = diag / 2.0

    for i in range(-n_lines, n_lines + 1):
        cands = bands.get(i)
        if not cands:
            continue
        offset = i * spacing
        # Ligne paramétrée P(t) = p1 + dir_line * t, t dans [0, diag]
        p1u = cu + dir_step[0] * offset - dir_line[0] * half
        p1v = cv + dir_step[1] * offset - dir_line[1] * half

        # Clipping de [0, diag] par les 3 demi-plans de chaque triangle
        intervals = []
        for idx in cands:
            a, b, c = tris[idx]
            t_lo, t_hi = 0.0, diag
            for (ax, ay), (bx, by) in ((a, b), (b, c), (c, a)):
                ex, ey = bx - ax, by - ay
                c0 = ex * (p1v - ay) - ey * (p1u - ax)
                c1 = ex * dir_line[1] - ey * dir_line[0]
                if abs(c1) < 1e-15:
                    if c0 < 0.0:
                        t_lo, t_hi = 1.0, 0.0  # ligne entièrement dehors
                        break
                    continue
                t_cross = -c0 / c1
                if c1 > 0.0:
                    if t_cross > t_lo:
                        t_lo = t_cross
                else:
                    if t_cross < t_hi:
                        t_hi = t_cross
                if t_lo >= t_hi:
                    break
            if t_hi - t_lo > 1e-9:
                intervals.append((t_lo, t_hi))

        if not intervals:
            continue

        # Fusion des intervalles contigus (triangles adjacents d'une même
        # face partagent leurs arêtes : leurs intervalles se touchent)
        intervals.sort()
        merged = [list(intervals[0])]
        for t0, t1 in intervals[1:]:
            if t0 <= merged[-1][1] + 1e-6:
                if t1 > merged[-1][1]:
                    merged[-1][1] = t1
            else:
                merged.append([t0, t1])

        segs = [m for m in merged if m[1] - m[0] > 1e-6]
        if i % 2 != 0:
            segs = [(t1, t0) for (t0, t1) in reversed(segs)]

        for t0, t1 in segs:
            pa = _to_xyz(p1u + dir_line[0] * t0, p1v + dir_line[1] * t0, origin, u_axis, v_axis)
            pb = _to_xyz(p1u + dir_line[0] * t1, p1v + dir_line[1] * t1, origin, u_axis, v_axis)
            hatch_edges.append(Part.LineSegment(pa, pb).toShape())

    return hatch_edges


# ==========================================================================
# REMPLISSAGE PAR DÉFOCUS (remplace le remplissage concentrique)
# ==========================================================================
# Principe : au foyer, le point laser est étroit -- bon pour un trait fin,
# mais il faudrait des dizaines de hachures très rapprochées pour noircir
# une surface entière sans laisser de bandes non brûlées. En éloignant le
# bec du foyer (défocus), le faisceau diverge et le point s'élargit : les
# MÊMES hachures parallèles (cf. generate_hatch_edges, aucune nouvelle
# géométrie nécessaire) espacées d'à peine moins que ce point élargi
# suffisent alors à noircir toute la face en un seul passage. Seul le Z de
# travail change, pas le tracé 2D.
#
# MODÈLE : cône de divergence linéaire (cohérent avec le modèle déjà
# utilisé pour le bec physique, cf. nozzle_h_min plus haut) :
#   diamètre(z) = diamètre_foyer + 2 * |z| * tan(demi-angle de divergence)
# Aucune fiche technique de divergence n'existe pour ce module laser
# précis -- plutôt que de deviner un angle (qui varie énormément d'un
# module à l'autre), le demi-angle est calculé à partir de DEUX MESURES
# RÉELLES du point (au foyer, puis à un défocus de test connu), exactement
# comme le motif de calibration kerf (mode 3) mesure le kerf réel au lieu
# de le deviner. C'est la méthode la plus fiable possible sans fiche
# constructeur : elle capture le comportement réel de CE laser précis.
def defocus_divergence_half_angle(d_focus, d_calib, z_calib):
    """Demi-angle de divergence (radians) du cône du faisceau, déduit de
    deux mesures réelles : diamètre au foyer (d_focus, Z=0) et diamètre
    mesuré à un défocus de test z_calib (d_calib). Renvoie 0.0 si les
    mesures sont incohérentes (défocus de test nul, ou point pas plus
    large qu'au foyer -- un défocus ne resserre jamais un faisceau,
    mesure invalide dans ce cas)."""
    if z_calib <= 0 or d_calib <= d_focus:
        return 0.0
    return math.atan((d_calib - d_focus) / (2.0 * z_calib))


def spot_diameter_at_defocus(z, d_focus, half_angle):
    """Diamètre du point laser (mm) à une distance `z` (mm, valeur
    absolue) du foyer, selon le modèle conique calibré par
    defocus_divergence_half_angle."""
    return d_focus + 2.0 * abs(z) * math.tan(half_angle)


def calibrated_half_angle():
    """Demi-angle de divergence issu de la calibration du point stockée
    dans les Préférences (mesures de la Bande de calibration défocus) --
    le point d'entrée UNIQUE de la calibration pour tous les panneaux,
    au lieu de trois champs resaisis dans chacun."""
    return defocus_divergence_half_angle(
        SPOT_FOCUS_MM, SPOT_TEST_DIAMETER_MM, SPOT_TEST_DEFOCUS_MM)


def defocus_for_spot_diameter(d_target, d_focus, half_angle):
    """Défocus (mm, hauteur à remonter le bec au-dessus du foyer) pour
    obtenir un point de diamètre `d_target` -- inverse de
    spot_diameter_at_defocus. Renvoie 0.0 si la cible est <= au point au
    foyer (déjà le plus petit) et None si la calibration est invalide
    (demi-angle nul). Sert à saisir directement la LARGEUR du point
    (intuitif) plutôt que la hauteur de défocus."""
    if half_angle <= 1e-9:
        return None
    if d_target <= d_focus:
        return 0.0
    return (d_target - d_focus) / (2.0 * math.tan(half_angle))


def defocus_for_fill_spacing(spacing, d_focus, half_angle, overlap=0.85):
    """Défocus (mm, valeur absolue à AJOUTER au Z de travail/foyer)
    nécessaire pour qu'un remplissage par hachures parallèles espacées de
    `spacing` soit plein, sans bande non noircie entre deux traits. Le
    point vise un diamètre légèrement SUPÉRIEUR à l'espacement
    (`overlap` < 1, défaut 15% de recouvrement) : un diamètre tout juste
    égal à l'espacement ferait à peine se toucher les bords du point, là
    où l'intensité est la plus faible (profil d'intensité plus fort au
    centre qu'au bord) -- insuffisant en pratique pour noircir sans trace
    résiduelle. Renvoie None si la calibration est absente/invalide
    (demi-angle nul -- defocus_divergence_half_angle a échoué)."""
    if half_angle <= 1e-9:
        return None
    target = spacing / overlap
    if target <= d_focus:
        return 0.0
    return (target - d_focus) / (2.0 * math.tan(half_angle))


# --- Fluence (énergie déposée) : lien puissance <-> défocus ------------
# Défocaliser étale la MÊME puissance sur un point plus large : l'énergie
# reçue par unité de surface (la fluence) baisse, et sous un seuil le
# trait ne marque plus (constaté à l'usage). Pour un trait BALAYÉ à la
# vitesse v, avec un point de diamètre d et une puissance P, la fluence
# vaut :   F ∝ P / (d · v)
# Point subtil : l'aire du point grossit en d², MAIS le faisceau balaie
# chaque point plus longtemps quand il est large (temps de séjour ∝ d),
# donc la fluence ne chute qu'en 1/d, pas 1/d². Aucune constante optique
# absolue n'étant connue, on ne manipule que des RAPPORTS à un réglage de
# référence mesuré bon sur le matériau (même philosophie « on mesure, on
# ne devine pas » que le reste de l'atelier).
def line_fluence(power, feed, spot_diam):
    """Fluence relative (sans unité) d'un trait balayé : P / (d · v).
    Sert uniquement à comparer deux réglages entre eux."""
    if feed <= 0 or spot_diam <= 0:
        return 0.0
    return power / (spot_diam * feed)


def relative_line_fluence(power, feed, spot_diam,
                          ref_power, ref_feed, ref_spot):
    """Rapport de fluence entre le réglage (power, feed, spot) et une
    RÉFÉRENCE connue bonne (ref_*) : 1.0 = même énergie déposée qu'à la
    référence, < 1 = plus pâle (risque de ne pas marquer), > 1 = plus
    appuyé (risque de brûler). None si la référence est invalide."""
    ref = line_fluence(ref_power, ref_feed, ref_spot)
    if ref <= 0:
        return None
    return line_fluence(power, feed, spot_diam) / ref


def power_for_line_fluence(feed, spot_diam, ref_power, ref_feed, ref_spot, ratio=1.0):
    """Puissance (S) qui donne `ratio` fois la fluence de référence, à la
    vitesse et au diamètre de point donnés -- inversion de line_fluence :
      P = ratio · ref_power · (spot / ref_spot) · (feed / ref_feed)
    (la puissance monte proportionnellement au diamètre du point ET à la
    vitesse). None si la référence est invalide."""
    if ref_spot <= 0 or ref_feed <= 0 or ref_power <= 0:
        return None
    return ratio * ref_power * (spot_diam / ref_spot) * (feed / ref_feed)


def inset_face_robuste(face, inset, deflection=0.05):
    """Rentre une face de `inset` mm vers l'intérieur et renvoie la liste
    des faces résultantes.

    Ne JAMAIS appeler makeOffset2D directement sur des faces importées :
    BRepOffsetAPI_MakeOffset (OCC) SEGFAULTE durement sur certains contours
    BSpline/Bézier issus d'imports SVG -- ce n'est pas une exception Python,
    ça tue FreeCAD. On discrétise donc d'abord chaque fil en polygone
    (flèche `deflection` mm, invisible au laser : bien plus fin que le
    point) ; l'offset de polylignes, lui, est stable.

    Quand l'offset échoue quand même, deux situations bien distinctes :
    - forme FINE (largeur < 2*inset partout) : disparaître est normal,
      le contour gravé la noircit -> pas de remplissage ([]) ;
    - face LARGE mais récalcitrante (ex. tracé SVG importé à ~200 fils :
      OCC rend un offset nul en bloc) : ne rien remplir du tout serait
      absurde -> repli en remplissage SANS retrait ([face]), avec un
      avertissement console (la brûlure peut déborder d'environ `inset`
      mm du contour).
    Discriminant : une face ne peut légitimement disparaître sous le
    retrait que si aire <= ~périmètre*inset ; au-delà (marge x2), c'est
    un échec OCC, pas une forme fine."""
    try:
        # La structure de la face est CONNUE (OuterWire + trous) : la
        # face polygonale se reconstruit directement, extérieur CCW et
        # trous CW via l'aire signée, sans repayer le tri d'imbrication
        # de Bullseye (11 s sur une face de ~180 fils, pour rien).
        # L'orientation par aire signée suppose le plan XY (le seul cas
        # réel au laser) : une face dans un autre plan repart sur la
        # construction Bullseye historique.
        outer = face.OuterWire
        poly_ext = None
        poly_trous = []
        z_ref = None
        plan_xy = True
        for w in face.Wires:
            pts = w.discretize(Deflection=deflection)
            if len(pts) < 3:
                return []
            if pts[0].distanceToPoint(pts[-1]) > 1e-6:
                pts.append(pts[0])
            for p in pts:
                if z_ref is None:
                    z_ref = p.z
                elif abs(p.z - z_ref) > 1e-6:
                    plan_xy = False
            p2 = [(p.x, p.y) for p in pts]
            ccw = _aire_signee_2d(p2) > 0
            if w.isSame(outer):
                poly_ext = Part.makePolygon(pts if ccw else pts[::-1])
            else:
                poly_trous.append(Part.makePolygon(pts[::-1] if ccw else pts))
        if poly_ext is None:
            return []
        if plan_xy:
            poly_face = Part.Face([poly_ext] + poly_trous)
        else:
            poly_face = Part.makeFace([poly_ext] + poly_trous,
                                      "Part::FaceMakerBullseye")
        off = poly_face.makeOffset2D(-inset)
        if off.Faces:
            return list(off.Faces)
        raise ValueError("offset vide")
    except Exception:
        try:
            if face.Area > 2.0 * face.Length * inset:
                FreeCAD.Console.PrintWarning(
                    "Retrait de remplissage impossible sur une face de "
                    "{:.0f} mm2 ({} fils) : remplissage SANS retrait, la "
                    "brûlure peut déborder d'environ {:.2f} mm du "
                    "contour.\n".format(face.Area, len(face.Wires), inset))
                return [face]
        except Exception:
            pass
        return []  # trop fin : le contour couvre, pas de remplissage


def run_hatch_generation(selection, spacing, angle, fill_type="paralleles", inset=0.0,
                         contour=False):
    """Crée l'objet 'Hachures_...' dans le document (vert), comme
    hachure.fcmacro, avec 3 types de remplissage possibles :
    parallèles (défaut), croisées (2 passes à angle+90), défocus
    (remplissage noir plein -- même tracé que parallèles, seul le Z de
    travail change au moment de la gravure, cf. defocus_for_fill_spacing).

    inset : RETRAIT DU BORD (mm). Les hachures sont calculées sur les
    faces RENTRÉES de cette marge (makeOffset2D vers l'intérieur, même
    mécanique que la Gravure remplie) : le trait laser ayant une largeur
    (surtout en défocus / pointillé / vague, où le point est élargi), des
    hachures bord à bord font déborder la brûlure de la forme d'environ
    un rayon de point -- rentrer les hachures de ce rayon garde la
    brûlure À L'INTÉRIEUR du contour. 0 = bord à bord (historique). Une
    face plus fine que 2*inset disparaît du remplissage (comme en
    Gravure remplie).

    contour : ajoute aussi le CONTOUR de la forme (bord de chaque face,
    trous compris) au compound créé -- hachures + contour gravés ensuite
    en une seule opération Marquage. Le contour suit le bord ORIGINAL de
    la forme, PAS le bord rentré par `inset` (le retrait ne concerne que
    la brûlure du remplissage ; le contour, lui, dessine la forme).

    Renvoie l'objet créé, ou None en cas d'échec."""
    faces = get_faces_from_selection_for_hatch(selection)
    if not faces:
        return None, ("Aucune face 2D fermée trouvée dans la sélection. "
                      "Il faut des CONTOURS FERMÉS : une face, un sketch fermé, "
                      "ou un compound d'arêtes qui se referment (import DXF/SVG "
                      "aux contours ouverts = à réparer d'abord).")

    # Contour capturé AVANT le retrait : il suit le bord de la forme.
    contour_edges = ([e for f in faces for e in f.Edges] if contour else [])

    if inset > 0:
        inset_faces = []
        for f in faces:
            inset_faces.extend(inset_face_robuste(f, inset))
        if not inset_faces:
            return None, ("Retrait du bord trop grand : plus aucune surface à "
                          "hachurer (réduire le retrait ou agrandir la forme).")
        faces = inset_faces

    if fill_type == "croisees":
        edges = generate_hatch_edges(faces, spacing, angle) + generate_hatch_edges(faces, spacing, angle + 90.0)
    else:
        # "paralleles" et "defocus" partagent le même tracé (hachures
        # parallèles) -- cf. commentaire ci-dessus.
        edges = generate_hatch_edges(faces, spacing, angle)

    if not edges and not contour_edges:
        return None, "Aucune hachure générée (vérifie l'espacement ou la taille de la forme)."

    doc = FreeCAD.ActiveDocument
    hatch_compound = Part.Compound(edges + contour_edges)
    obj_name = "Hachures_{}_{}_{}deg".format(fill_type, spacing, angle).replace(".", "_").replace("-", "m")
    hatch_obj = doc.addObject("Part::Feature", obj_name)
    hatch_obj.Shape = hatch_compound
    if hasattr(hatch_obj, 'ViewObject'):
        hatch_obj.ViewObject.LineColor = (0.0, 0.8, 0.0)
        hatch_obj.ViewObject.LineWidth = 1.0
    doc.recompute()
    return hatch_obj, None


# ==========================================================================
# MODE 0b : PROJECTION SUR SURFACE 3D (adapté de Coller_hachures_sur_3D.fcmacro)
# ==========================================================================
PROJECTION_SAMPLE_DISTANCE = 1.0  # mm : Distance, pas Deflection -- une
                                   # droite 2D n'a aucune courbure à
                                   # approximer, Deflection ne donnerait
                                   # que 2 points (corde droite sous la
                                   # courbure réelle entre les deux).


def split_projection_selection(selection):
    """Classe la sélection en (motifs 2D, surface 3D de référence) pour le
    mode Projection. Un objet est "2D" si son épaisseur Z est quasi nulle
    (<0.1mm, même heuristique qu'avant) ; sinon c'est un candidat "surface"
    -- mais seulement s'il a au moins une Face. Un objet épais SANS face
    (ex: un ancien résultat de projection, un pur nuage d'arêtes) n'est ni
    un motif plat ni une vraie surface projetable : sa tessellation ne
    donnerait aucun triangle, donc rien à sonder -- il rend la sélection
    invalide plutôt que d'être accepté à tort comme référence. Permet de
    sélectionner PLUSIEURS motifs 2D en une seule fois (ex: un ShapeString
    + des hachures, chacun avec le même corps de référence sélectionné une
    seule fois puisque la sélection FreeCAD ne garde pas les doublons) et
    de les projeter tous ensemble sur la MÊME surface, au lieu de répéter
    l'opération motif par motif. Renvoie (liste d'objets 2D, objet 3D), ou
    (None, None) si la classification est ambiguë ou invalide."""
    motifs = []
    reference = None
    for sel_obj in selection:
        obj = sel_obj.Object
        shape = getattr(obj, 'Shape', None)
        if shape is None:
            continue
        bb = shape.BoundBox
        if bb.ZMax - bb.ZMin < 0.1:
            motifs.append(obj)
        elif shape.Faces:
            if reference is not None:
                return None, None
            reference = obj
        else:
            return None, None
    if reference is None or not motifs:
        return None, None
    return motifs, reference


def drop_edges_to_surface(edges_2d, shape_3d, mesh_probe=None):
    """Projette chaque point des lignes 2D sur la surface 3D via la sonde
    par maillage (_MeshZProbe : tessellation une fois, puis interpolation
    barycentrique par point -- remplace l'ancien raycast booléen
    OpenCascade par point, ~5ms chacun, qui coûtait plus d'une minute sur
    un remplissage dense). L'interpolation linéaire donne un Z continu :
    pas de tracé en dents de scie, l'écart à la vraie surface est borné
    par MESH_PROBE_DEVIATION_MM.

    mesh_probe : sonde _MeshZProbe(shape_3d) déjà construite, à passer
    quand l'appelant projette PLUSIEURS lots sur la même surface (un
    appel par motif dans run_projection) -- évite de re-tesseller la
    surface à chaque lot."""
    if mesh_probe is None:
        mesh_probe = _MeshZProbe(shape_3d)

    def probe(x, y):
        z = mesh_probe.z_at_or_none(x, y)
        if z is None:
            return None
        return FreeCAD.Vector(x, y, z)

    edges_3d = []
    for edge in edges_2d:
        pts = edge.discretize(Distance=PROJECTION_SAMPLE_DISTANCE)
        if len(pts) < 2:
            # Une arête PLUS COURTE que le pas d'échantillonnage ne rend
            # qu'UN seul point (mesuré : discretize(Distance=1.0) sur
            # 0,05 mm -> 1 point). La jeter perce la boucle du fil : le
            # fil devient OUVERT, la face disparaît du remplissage (fond
            # du dessin) ou son trou est avalé (détails blancs d'un
            # visage) -- les imports SVG à flèche fine regorgent de
            # micro-segments dans les zones très courbées. On retombe
            # sur les deux sommets de l'arête.
            pts = [v.Point for v in getattr(edge, "Vertexes", [])]
            if len(pts) < 2:
                continue

        pts_3d = [p for p in (probe(pt.x, pt.y) for pt in pts) if p is not None]

        if len(pts_3d) >= 2:
            for i in range(len(pts_3d) - 1):
                # Deux points consécutifs peuvent retomber sur le même point
                # mémoïsé (positions proches -> même cellule de cache) :
                # LineSegment refuse un segment de longueur nulle.
                if pts_3d[i].isEqual(pts_3d[i + 1], 1e-7):
                    continue
                edges_3d.append(Part.LineSegment(pts_3d[i], pts_3d[i + 1]).toShape())

    return edges_3d


def run_projection(selection):
    """Crée l'objet 'Motif_Projete' dans le document (rouge), comme
    Coller_hachures_sur_3D.fcmacro -- accepte PLUSIEURS motifs 2D en une
    seule sélection (ex: ShapeString + hachures), tous projetés ensemble
    sur la MÊME surface 3D de référence en un seul objet résultat, au lieu
    de répéter le mode motif par motif. Renvoie (objet, erreur)."""
    if len(selection) < 2:
        return None, "Sélectionne au moins un motif 2D et une surface 3D de référence."

    motif_objs, obj_3d = split_projection_selection(selection)
    if not motif_objs or obj_3d is None:
        return None, ("Impossible de distinguer le(s) motif(s) 2D de la surface 3D -- vérifie "
                       "qu'un seul objet de la sélection a une épaisseur significative "
                       "(la surface de référence) et que tous les autres sont plats (les motifs).")

    FreeCAD.Console.PrintMessage(
        "Extraction des lignes 2D... ({} motif(s))\n".format(len(motif_objs)))
    edges_2d = []
    lots_2d = []   # un lot d'arêtes PAR MOTIF, pour préserver le groupage
    for obj in motif_objs:
        if hasattr(obj.Shape, 'Edges') and obj.Shape.Edges:
            lots_2d.append(list(obj.Shape.Edges))
            edges_2d.extend(obj.Shape.Edges)
    if not edges_2d:
        return None, "Aucune ligne trouvée dans le(s) motif(s) 2D."

    FreeCAD.Console.PrintMessage("Calcul de la projection sur le 3D (raycast Z)...\n")
    # Projection PAR MOTIF, chaque lot devenant son propre sous-compound :
    # le remplissage pair/impair se calcule par tracé d'origine (comme un
    # lecteur SVG remplit chaque <path> indépendamment puis les
    # superpose). Tout fusionner en un compound plat recalculait la
    # parité GLOBALEMENT sur l'ensemble des fils : sur un dessin aux
    # tracés imbriqués (skull importé), -59 % de surface remplie mesurée,
    # zones inversées visibles à l'aperçu photo.
    probe = _MeshZProbe(obj_3d.Shape)
    groupes_3d = []
    for lot in lots_2d:
        edges_lot = drop_edges_to_surface(lot, obj_3d.Shape, probe)
        if edges_lot:
            groupes_3d.append(Part.Compound(edges_lot))
    edges_3d = groupes_3d
    if not edges_3d:
        # Diagnostic : la sonde échoue quand (x, y) est HORS de la
        # silhouette de la surface vue de dessus -- le Z du motif n'a
        # aucune importance. Donner les emprises réelles pour corriger.
        xs, ys = [], []
        for e in edges_2d:
            b = e.BoundBox
            xs.extend((b.XMin, b.XMax))
            ys.extend((b.YMin, b.YMax))
        sb = obj_3d.Shape.BoundBox
        return None, (
            "La projection a échoué : vu de DESSUS, aucun point du motif ne "
            "tombe sur la surface 3D.\n\n"
            "Emprise X/Y du motif :   X {:.1f} à {:.1f}   Y {:.1f} à {:.1f}\n"
            "Emprise X/Y de « {} » :   X {:.1f} à {:.1f}   Y {:.1f} à {:.1f}\n\n"
            "Déplace le motif (Placement) pour qu'il recouvre la surface en "
            "vue de dessus. Sa hauteur Z n'a pas d'importance : seule la "
            "position X/Y compte.".format(
                min(xs), max(xs), min(ys), max(ys),
                obj_3d.Label, sb.XMin, sb.XMax, sb.YMin, sb.YMax))

    doc = FreeCAD.ActiveDocument
    compound_3d = Part.Compound(edges_3d)
    new_obj = doc.addObject("Part::Feature", "Motif_Projete")
    new_obj.Shape = compound_3d
    # getattr et non hasattr : en headless (freecadcmd), ViewObject EXISTE
    # mais vaut None -- hasattr laisse alors passer un AttributeError.
    if getattr(new_obj, 'ViewObject', None) is not None:
        new_obj.ViewObject.LineColor = (1.0, 0.0, 0.0)
        new_obj.ViewObject.LineWidth = 2.0
    # Mémorise le solide d'origine : le motif projeté n'est qu'un compound
    # d'arêtes, sans aucune trace de la surface dont il vient -- sans ce
    # lien, retrouver une sonde de collision exacte plus tard obligerait à
    # RESÉLECTIONNER le solide à chaque génération (cf. split_selection).
    new_obj.addProperty(
        "App::PropertyLink", "LaserAtelierSurfaceRef", "LaserAtelier",
        "Solide 3D d'origine, mémorisé automatiquement à la projection "
        "pour retrouver la sonde de collision sans le réselectionner.")
    new_obj.LaserAtelierSurfaceRef = obj_3d
    # Recompute CIBLÉ sur le nouvel objet : un doc.recompute() global
    # forcerait aussi le recalcul de tout le reste du document (ex: un
    # Job CAM/Path avec Pocket_Shape), sans aucun rapport avec cet objet.
    doc.recompute([new_obj])
    return new_obj, None


# ==========================================================================
# MODE 0c : MOTIF DE CALIBRATION KERF
# ==========================================================================
def create_kerf_test_pattern(size):
    """Crée un carré de `size` mm de côté dans le document actif, pour
    calibrer le kerf : le découper en mode 4 avec Compensation de kerf =
    0 (pas de compensation), mesurer la pièce obtenue au pied à coulisse,
    puis kerf = size - mesure. Renvoie (objet, erreur)."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None, "Aucun document actif -- crée ou ouvre un document d'abord."

    half = size / 2.0
    pts = [
        FreeCAD.Vector(-half, -half, 0),
        FreeCAD.Vector(half, -half, 0),
        FreeCAD.Vector(half, half, 0),
        FreeCAD.Vector(-half, half, 0),
        FreeCAD.Vector(-half, -half, 0),
    ]
    edges = [Part.LineSegment(pts[i], pts[i + 1]).toShape() for i in range(4)]
    wire = Part.Wire(edges)

    obj_name = "Test_Kerf_{}mm".format(str(size).replace(".", "_"))
    obj = doc.addObject("Part::Feature", obj_name)
    obj.Shape = wire
    if hasattr(obj, 'ViewObject'):
        obj.ViewObject.LineColor = (1.0, 0.6, 0.0)
        obj.ViewObject.LineWidth = 2.0
    doc.recompute()
    return obj, None


def _fit_test_layout(tenon_w, tenon_h, n_slots, clearance_start, clearance_step):
    """Disposition du test d'ajustement tenon/mortaise (PUR, sans FreeCAD --
    testable en headless). Renvoie (rects, labels) :
      rects  = [(x0, y0, w, h, role), ...]  role = "tenon" | "mortaise"
      labels = [(texte, x, y, hauteur), ...]  (le jeu de chaque mortaise)
    Une rangée de mortaises au nominal du tenon MAIS agrandies d'un jeu
    croissant (clearance_start, +step, ...), étiquetées ; le tenon (pièce
    mâle) isolé au-dessus. Le « jeu » est l'écart mortaise - tenon (réparti
    moitié de chaque côté)."""
    gap = max(8.0, tenon_w * 0.5)   # matière entre deux mortaises
    label_h = 4.0
    rects, labels = [], []
    x = 0.0
    y_slots = label_h + 3.0
    max_h = 0.0
    for i in range(int(n_slots)):
        clr = clearance_start + i * clearance_step
        w, h = tenon_w + clr, tenon_h + clr
        rects.append((x, y_slots, w, h, "mortaise"))
        txt = "{:.2f}".format(clr).rstrip("0").rstrip(".") or "0"
        labels.append((txt, x, 0.0, label_h))
        max_h = max(max_h, h)
        x += w + gap
    y_tenon = y_slots + max_h + gap
    rects.append((0.0, y_tenon, tenon_w, tenon_h, "tenon"))
    return rects, labels


def create_fit_test_pattern(tenon_w=20.0, tenon_h=10.0, n_slots=5,
                            clearance_start=0.0, clearance_step=0.1):
    """Crée un test d'AJUSTEMENT tenon/mortaise dans le document actif : un
    tenon (pièce mâle) au nominal, et une rangée de mortaises (trous) au même
    nominal mais avec un jeu croissant, chacune étiquetée de son jeu en mm.
    À utiliser APRÈS avoir mesuré le kerf sur le carré : découper avec cette
    Compensation de kerf, puis insérer le tenon dans chaque mortaise pour
    retenir le jeu qui donne le bon ajustement.
    Crée DEUX objets : « Test_Ajustement_decoupe » (les contours seuls, à
    découper) et « Test_Ajustement_gravure » (le jeu sous chaque mortaise + la
    cote nominale sur le tenon, repère de la pièce de référence, à MARQUER à
    faible puissance -- opération distincte de la découpe). Renvoie (liste
    d'objets, erreur)."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None, "Aucun document actif -- cree ou ouvre un document d'abord."
    if int(n_slots) < 1:
        return None, "Il faut au moins une mortaise."
    if tenon_w <= 0 or tenon_h <= 0:
        return None, "Dimensions du tenon invalides."

    rects, labels = _fit_test_layout(tenon_w, tenon_h, int(n_slots),
                                     clearance_start, clearance_step)

    def rect_wire(x0, y0, w, h):
        p = [FreeCAD.Vector(x0, y0, 0), FreeCAD.Vector(x0 + w, y0, 0),
             FreeCAD.Vector(x0 + w, y0 + h, 0), FreeCAD.Vector(x0, y0 + h, 0),
             FreeCAD.Vector(x0, y0, 0)]
        return Part.Wire([Part.LineSegment(p[i], p[i + 1]).toShape() for i in range(4)])

    # DÉCOUPE : uniquement les contours (tenon + mortaises).
    cut_shapes = [rect_wire(x0, y0, w, h) for (x0, y0, w, h, _role) in rects]
    cut_obj = doc.addObject("Part::Feature", "Test_Ajustement_decoupe")
    cut_obj.Shape = Part.Compound(cut_shapes)
    if hasattr(cut_obj, 'ViewObject'):
        cut_obj.ViewObject.LineColor = (1.0, 0.6, 0.0)
        cut_obj.ViewObject.LineWidth = 2.0
    objs = [cut_obj]

    # GRAVURE (faible puissance, opération distincte de la découpe) : TOUT le
    # texte est marqué, pas coupé -- le jeu sous chaque mortaise + la cote
    # nominale sur le tenon (repère de la pièce de référence).
    engrave_shapes = []
    for (txt, lx, ly, lh) in labels:              # jeu de chaque mortaise
        engrave_shapes.extend(text_to_edges(txt, lx, ly, lh))
    tenon = next((r for r in rects if r[4] == "tenon"), None)
    if tenon is not None:
        tx, ty, tw, th_, _role = tenon
        mark_h = max(3.0, min(th_ * 0.5, tw * 0.45))
        mark_txt = "{:g}".format(tw)
        mark_w = text_width(mark_txt, mark_h)
        engrave_shapes.extend(text_to_edges(
            mark_txt, tx + (tw - mark_w) / 2.0, ty + (th_ - mark_h) / 2.0, mark_h))
    if engrave_shapes:
        eng_obj = doc.addObject("Part::Feature", "Test_Ajustement_gravure")
        eng_obj.Shape = Part.Compound(engrave_shapes)
        if hasattr(eng_obj, 'ViewObject'):
            eng_obj.ViewObject.LineColor = (0.2, 0.5, 1.0)
            eng_obj.ViewObject.LineWidth = 1.0
        objs.append(eng_obj)

    doc.recompute()
    return objs, None


# ==========================================================================
# MODE 0d : GRILLE DE TEST PUISSANCE / VITESSE (gravure ou découpe)
# ==========================================================================
# But : au lieu de tâtonner passe par passe sur la pièce finale, graver ou
# découper en UN SEUL job une grille de cellules couvrant toute une plage
# de puissance (colonnes, X croissant) x vitesse (lignes, Y croissant),
# puis choisir à l'œil la meilleure cellule sur le résultat physique. La
# POSITION de chaque cellule est déjà son étiquette, mais repérer un
# numéro de colonne/ligne demande de recompter depuis un bord -- chaque
# colonne/ligne est donc EN PLUS étiquetée directement sur la pièce (ex:
# "S400" sous la colonne, "F1500" à gauche de la ligne), cf.
# build_test_grid_axis_labels plus bas. Le nom de l'objet FreeCAD créé
# pour chaque cellule reprend aussi ses valeurs (ex:
# "Test_Gravure_L2_C3_S400_F1500", survolable dans l'arbre), et la vue
# Rapport imprime la grille complète ligne/colonne -> puissance/vitesse
# avant génération du G-code.
def build_test_grid_cells(mode, power_min, power_max, n_power,
                           feed_min, feed_max, n_feed,
                           cell_size, gap,
                           fill_type="paralleles",
                           hatch_spacing=0.2, hatch_angle=45.0,
                           fill_inset=0.0,
                           powers=None, feeds=None):
    """Construit la grille de cellules de test. mode: "gravure" (contour
    rempli, réutilise generate_hatch_edges sans rien changer -- 3 types
    de remplissage possibles comme le mode Hachures 2D : "paralleles",
    "croisees" (2 passes à angle+90) et "defocus", ce dernier partageant
    le MÊME tracé que "paralleles" -- seul le Z de gravure diffère, cf.
    cell_z_offset dans generate_gcode_test_grid) ou "decoupe" (contour
    carré simple, comme le motif de calibration kerf). Puissance
    croissante en colonnes (X), vitesse (feed) croissante en lignes (Y).

    fill_inset : marge (mm) dont la zone HACHURÉE est rentrée par rapport
    au carré de la cellule -- typiquement le RAYON du point laser. Le
    point a une largeur : les hachures allant bord à bord, la brûlure
    déborde du carré d'environ un rayon de point (très visible en
    défocus, où le point est large). En rentrant la zone hachurée d'un
    rayon, la brûlure (hachures + rayon de point) s'arrête pile au bord
    du carré / du cadre. N'affecte QUE le remplissage : le contour
    (border_edges, et le tracé de découpe) reste le carré plein.

    `powers` / `feeds` : listes EXPLICITES de paliers, qui remplacent alors
    le triplet min/max/nombre correspondant. Les paliers calculés sont
    répartis LINÉAIREMENT, ce qui ne sait pas produire une progression
    géométrique -- or les colonnes de saisie des largeurs brûlées en sont
    une (200, 400, 800, 1000, 1200, 1500, 3000). Sans ces listes, l'objectif « Largeurs
    brûlées — grille au foyer » gravait 400/1800/3200/4600/6000 : quatre
    vitesses sur cinq n'avaient AUCUNE colonne où être saisies, et la
    planche était donc inexploitable par le chemin prévu pour elle.

    Renvoie une liste de dicts :
    {row, col, power, feed, x0, y0, edges, border_edges}."""
    if powers:
        powers = [float(p) for p in powers]
        n_power = len(powers)
    if feeds:
        feeds = [float(f) for f in feeds]
        n_feed = len(feeds)
    n_power = max(1, int(n_power))
    n_feed = max(1, int(n_feed))
    step = cell_size + gap

    cells = []
    for row in range(n_feed):
        if feeds:
            feed = feeds[row]
        else:
            feed = feed_min if n_feed == 1 else feed_min + (feed_max - feed_min) * row / float(n_feed - 1)
        for col in range(n_power):
            if powers:
                power = powers[col]
            else:
                power = power_min if n_power == 1 else power_min + (power_max - power_min) * col / float(n_power - 1)
            x0 = col * step
            y0 = row * step

            pts = [
                FreeCAD.Vector(x0, y0, 0),
                FreeCAD.Vector(x0 + cell_size, y0, 0),
                FreeCAD.Vector(x0 + cell_size, y0 + cell_size, 0),
                FreeCAD.Vector(x0, y0 + cell_size, 0),
                FreeCAD.Vector(x0, y0, 0),
            ]
            square_edges = [Part.LineSegment(pts[i], pts[i + 1]).toShape() for i in range(4)]

            if mode == "gravure":
                # Face hachurée éventuellement rentrée d'un rayon de point
                # (fill_inset) pour que la brûlure ne déborde pas du carré.
                # Repli sur le carré plein si l'inset ne laisse pas de place.
                r = fill_inset if (fill_inset > 0 and cell_size - 2.0 * fill_inset > max(hatch_spacing, 0.5)) else 0.0
                if r > 0:
                    ipts = [
                        FreeCAD.Vector(x0 + r, y0 + r, 0),
                        FreeCAD.Vector(x0 + cell_size - r, y0 + r, 0),
                        FreeCAD.Vector(x0 + cell_size - r, y0 + cell_size - r, 0),
                        FreeCAD.Vector(x0 + r, y0 + cell_size - r, 0),
                        FreeCAD.Vector(x0 + r, y0 + r, 0),
                    ]
                    fill_edges = [Part.LineSegment(ipts[i], ipts[i + 1]).toShape() for i in range(4)]
                else:
                    fill_edges = square_edges
                face = Part.Face(Part.Wire(fill_edges))
                if fill_type == "croisees":
                    edges = (generate_hatch_edges([face], hatch_spacing, hatch_angle) +
                              generate_hatch_edges([face], hatch_spacing, hatch_angle + 90.0))
                else:
                    # "paralleles" et "defocus" partagent le même tracé
                    # (hachures parallèles) -- cf. mode Hachures 2D.
                    edges = generate_hatch_edges([face], hatch_spacing, hatch_angle)
                if not edges:
                    edges = square_edges  # repli : au moins le contour si le remplissage échoue
            else:
                edges = square_edges

            cells.append({
                "row": row, "col": col,
                "power": power, "feed": feed,
                "x0": x0, "y0": y0,
                "edges": edges,
                "border_edges": square_edges,  # contour carré, pour le cadre net au foyer
            })
    return cells


# --- Police vectorielle minimaliste "7 segments" (chiffres + S/F) -------
# But : étiqueter chaque colonne/ligne de la grille directement sur la
# pièce (ex: "S400", "F1500"), sans dépendre d'un fichier de police
# externe (TTF/OTF) comme le ferait un Draft.ShapeString classique -- le
# jeu de caractères nécessaire ici est minuscule (10 chiffres + S + F),
# une poignée de segments suffit, et le résultat reste portable d'une
# machine à l'autre sans jamais se demander si telle police est
# installée. Repère sur une boîte unité 1 (large) x 2 (haut), mise à
# l'échelle par _char_to_edges selon la hauteur demandée.
_FONT_SEGMENT_COORDS = {
    'top':          ((0.0, 2.0), (1.0, 2.0)),
    'top_left':     ((0.0, 2.0), (0.0, 1.0)),
    'top_right':    ((1.0, 2.0), (1.0, 1.0)),
    'middle':       ((0.0, 1.0), (1.0, 1.0)),
    'bottom_left':  ((0.0, 1.0), (0.0, 0.0)),
    'bottom_right': ((1.0, 1.0), (1.0, 0.0)),
    'bottom':       ((0.0, 0.0), (1.0, 0.0)),
}

_FONT_GLYPHS = {
    '0': ('top', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'bottom'),
    '1': ('top_right', 'bottom_right'),
    '2': ('top', 'top_right', 'middle', 'bottom_left', 'bottom'),
    '3': ('top', 'top_right', 'middle', 'bottom_right', 'bottom'),
    '4': ('top_left', 'top_right', 'middle', 'bottom_right'),
    '5': ('top', 'top_left', 'middle', 'bottom_right', 'bottom'),
    '6': ('top', 'top_left', 'middle', 'bottom_left', 'bottom_right', 'bottom'),
    '7': ('top', 'top_right', 'bottom_right'),
    '8': ('top', 'top_left', 'top_right', 'middle', 'bottom_left', 'bottom_right', 'bottom'),
    '9': ('top', 'top_left', 'top_right', 'middle', 'bottom_right', 'bottom'),
    # S/F : mêmes segments qu'un afficheur 7 segments classique (S se lit
    # comme un 5 stylisé, F comme un E sans barre du bas).
    'S': ('top', 'top_left', 'middle', 'bottom_right', 'bottom'),
    'F': ('top', 'top_left', 'middle', 'bottom_left'),
    '-': ('middle',),  # signe moins (Z négatif)
    # '.' n'est pas un segment : traité à part dans _char_to_edges.
}


def _char_to_edges(ch, x0, y0, height):
    """Trace un caractère de la police 7-segments à l'ancrage bas-gauche
    (x0, y0), mis à l'échelle à `height`. Renvoie [] pour un caractère
    non supporté (le curseur avance quand même dans text_to_edges, pour
    garder un espacement régulier même sur un caractère manquant)."""
    if ch == '.':
        # Point décimal : petit trait vertical au bas de la case (pas un
        # segment nommé de l'afficheur 7 segments).
        scale = height / 2.0
        p1 = FreeCAD.Vector(x0 + 0.2 * scale, y0, 0)
        p2 = FreeCAD.Vector(x0 + 0.2 * scale, y0 + 0.3 * scale, 0)
        return [Part.LineSegment(p1, p2).toShape()]
    segments = _FONT_GLYPHS.get(ch.upper())
    if not segments:
        return []
    scale = height / 2.0
    edges = []
    for name in segments:
        (ux0, uy0), (ux1, uy1) = _FONT_SEGMENT_COORDS[name]
        p1 = FreeCAD.Vector(x0 + ux0 * scale, y0 + uy0 * scale, 0)
        p2 = FreeCAD.Vector(x0 + ux1 * scale, y0 + uy1 * scale, 0)
        if p1.distanceToPoint(p2) < 1e-6:
            continue
        edges.append(Part.LineSegment(p1, p2).toShape())
    return edges


def text_char_width(height):
    return height / 2.0


def text_width(text, height, spacing_ratio=0.4):
    """Largeur totale (mm) qu'occuperait `text` à la hauteur donnée --
    utilisé pour centrer une étiquette (ex: sous une colonne) avant de
    tracer ses edges."""
    if not text:
        return 0.0
    char_width = text_char_width(height)
    spacing = char_width * spacing_ratio
    return len(text) * char_width + (len(text) - 1) * spacing


def text_to_edges(text, x0, y0, height, spacing_ratio=0.4):
    """Convertit `text` (chiffres 0-9, lettres S/F, plus '.' et '-' pour
    les hauteurs de la bande de calibration défocus) en une liste de
    Part.Edge, ancrée en bas-gauche à (x0, y0)."""
    char_width = text_char_width(height)
    spacing = char_width * spacing_ratio
    edges = []
    cursor_x = x0
    for ch in text:
        edges.extend(_char_to_edges(ch, cursor_x, y0, height))
        cursor_x += char_width + spacing
    return edges


def text_to_edges_vertical(text, x_center, y_top, height, vgap_ratio=0.3):
    """Comme text_to_edges mais empile les caractères VERTICALEMENT (de
    haut en bas), chacun centré horizontalement sur x_center. Pour des
    étiquettes qui tiennent dans un espacement HORIZONTAL serré -- ex. les
    graduations de puissance du test rampe, écrites verticalement faute de
    place à l'horizontale. y_top = haut du 1er caractère (le texte descend
    ensuite)."""
    char_w = text_char_width(height)
    vgap = height * vgap_ratio
    x0 = x_center - char_w / 2.0
    edges = []
    for i, ch in enumerate(text):
        y_bottom = y_top - (i + 1) * height - i * vgap
        edges.extend(_char_to_edges(ch, x0, y_bottom, height))
    return edges


def nice_axis_step(span, target_ticks=6):
    """Pas « rond » (1/2/2.5/5 x puissance de 10) pour graduer un axe de
    `span` en ~target_ticks intervalles -- graduations lisibles (100, 200,
    250, 500...) plutôt qu'un pas brut."""
    if span <= 0:
        return 1.0
    raw = span / float(target_ticks)
    mag = 10.0 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if m * mag >= raw:
            return m * mag
    return 10.0 * mag


def build_test_grid_axis_labels(cells, n_power, n_feed, cell_size, gap, label_height=None):
    """Construit les étiquettes d'axe de la grille de test : une par
    colonne de puissance (ex: "S400", sous la grille) et une par ligne de
    vitesse (ex: "F1500", à gauche de la grille) -- pour lire directement
    sur la pièce à quelle valeur correspond chaque colonne/ligne, sans
    avoir à recompter depuis un bord. Renvoie (power_labels, feed_labels),
    chacune une liste de dicts {index, text, edges}."""
    if label_height is None:
        label_height = max(1.5, min(cell_size * 0.35, 5.0))
    step = cell_size + gap
    margin = gap + label_height * 0.5

    by_col = {}
    by_row = {}
    for cell in cells:
        by_col.setdefault(cell["col"], cell)
        by_row.setdefault(cell["row"], cell)

    power_labels = []
    for col in range(n_power):
        text = "S{:.0f}".format(by_col[col]["power"])
        w = text_width(text, label_height)
        x0 = col * step + cell_size / 2.0 - w / 2.0
        y0 = -margin - label_height
        power_labels.append({"col": col, "text": text, "edges": text_to_edges(text, x0, y0, label_height)})

    feed_labels = []
    for row in range(n_feed):
        text = "F{:.0f}".format(by_row[row]["feed"])
        w = text_width(text, label_height)
        x0 = -margin - w
        y0 = row * step + cell_size / 2.0 - label_height / 2.0
        feed_labels.append({"row": row, "text": text, "edges": text_to_edges(text, x0, y0, label_height)})

    return power_labels, feed_labels


def create_test_grid_object(mode, cells):
    """Crée un objet par cellule dans le document (repérage visuel dans
    l'arbre/la vue 3D -- le nom de chaque objet reprend ses valeurs S/F).
    Renvoie (liste d'objets créés, erreur)."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None, "Aucun document actif -- crée ou ouvre un document d'abord."

    objs = []
    for cell in cells:
        name = "Test_{}_L{}_C{}_S{:.0f}_F{:.0f}".format(
            "Gravure" if mode == "gravure" else "Decoupe",
            cell["row"], cell["col"], cell["power"], cell["feed"]).replace(".", "_")
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = Part.Compound(cell["edges"])
        if hasattr(obj, 'ViewObject'):
            obj.ViewObject.LineColor = (0.0, 0.4, 1.0) if mode == "gravure" else (1.0, 0.6, 0.0)
            obj.ViewObject.LineWidth = 1.0
        objs.append(obj)
    doc.recompute()
    return objs, None


def create_test_grid_label_object(power_labels, feed_labels):
    """Crée un objet unique regroupant toutes les étiquettes d'axe
    (repérage visuel dans l'arbre/la vue 3D). Renvoie (objet ou None si
    aucune étiquette, erreur)."""
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return None, "Aucun document actif -- crée ou ouvre un document d'abord."

    edges = []
    for lbl in power_labels:
        edges.extend(lbl["edges"])
    for lbl in feed_labels:
        edges.extend(lbl["edges"])
    if not edges:
        return None, None

    obj = doc.addObject("Part::Feature", "Test_Grille_Etiquettes")
    obj.Shape = Part.Compound(edges)
    if hasattr(obj, 'ViewObject'):
        obj.ViewObject.LineColor = (0.1, 0.1, 0.1)
        obj.ViewObject.LineWidth = 1.5
    doc.recompute()
    return obj, None


def print_test_grid_legend(mode, cells, n_power, n_feed):
    """Imprime la grille complète (ligne/colonne -> puissance/vitesse)
    dans la vue Rapport, pour repérer chaque cellule sur la pièce
    physique après gravure/découpe (puissance croissante -> en colonnes/X,
    vitesse croissante ^ en lignes/Y)."""
    FreeCAD.Console.PrintMessage(
        "\n--- Grille de test {} ({} colonne(s) de puissance x {} ligne(s) de vitesse) ---\n".format(
            "gravure" if mode == "gravure" else "découpe", n_power, n_feed))
    FreeCAD.Console.PrintMessage(
        "Puissance croissante -> (colonnes, X) -- Vitesse croissante ^ (lignes, Y)\n")
    by_row = defaultdict(dict)
    for cell in cells:
        by_row[cell["row"]][cell["col"]] = cell
    for row in sorted(by_row, reverse=True):
        parts = ["L{}C{}:S{:.0f}/F{:.0f}".format(row, col, c["power"], c["feed"])
                 for col, c in sorted(by_row[row].items())]
        FreeCAD.Console.PrintMessage("  " + "  ".join(parts) + "\n")
    FreeCAD.Console.PrintMessage("--- fin grille ---\n\n")


def _apply_grid_line_style(chains, style, sp):
    """Applique un STYLE DE TRAIT au remplissage d'une cellule (à Z fixe) :
    plein (inchangé), tirets (tronçons espacés) ou pointillé (micro-traits).
    Renvoie une liste de chaînes (chacune gravée beam on/off). vague/dégradé
    sont des effets de défocus (Z) -> non proposés ici (grille à Z fixe)."""
    if style == "tirets":
        out = []
        for ch in chains:
            for piece, on in dash_chain(ch, sp.get("dash_len", 3.0), sp.get("gap_len", 2.0)):
                if on and len(piece) >= 2:
                    out.append(piece)
        return out
    if style == "pointille":
        out = []
        half = 0.15
        for ch in chains:
            dots = dot_positions(ch, sp.get("dot_spacing", 1.5))
            for i, d in enumerate(dots):
                ux, uy = dot_stroke_dir(dots, i)
                out.append([FreeCAD.Vector(d.x - ux * half, d.y - uy * half, d.z),
                            FreeCAD.Vector(d.x + ux * half, d.y + uy * half, d.z)])
        return out
    return chains


def generate_gcode_test_grid(cells, z_work, label_edges=None, label_power=None, label_feed=None,
                              cell_z_offset=0.0, use_proximity=False,
                              line_style="plein", line_style_params=None,
                              draw_border=False, z_border=None, border_power=300.0, border_feed=1000.0,
                              pre_gcode="", post_gcode="", frame_only=False, quiet=False, body_only=False,
                              min_safe_z=None):
    """G-code de la grille de test : chaque cellule est chaînée et
    gravée/découpée UNE SEULE FOIS avec SA PROPRE puissance/vitesse.

    Contrairement aux modes Courbe/Découpe (où Z suit une surface/varie
    par passe et un retrait complet entre chaînes est nécessaire pour
    dégager le bec), ce job ne connaît au plus que DEUX hauteurs de
    travail fixes (voir cell_z_offset) : un seul plongeon/une seule
    remontée par hauteur suffisent, jamais un aller-retour de sécurité
    entre chaque ligne/cellule comme le ferait le patron des autres modes
    appliqué sans réfléchir ici -- pure perte de temps sur un job qui peut
    déjà compter des centaines de chaînes (remplissage par hachures) : le
    laser ne touche jamais la matière (focus optique, pas fraisage), donc
    transiter faisceau éteint à la hauteur de gravure ne présente aucun
    risque de collision supplémentaire sur une pièce plate.

    label_edges : étiquettes d'axe (cf. build_test_grid_axis_labels),
    gravées à une puissance/vitesse FIXES (label_power/label_feed) --
    séparées des valeurs en cours de test, pour rester lisibles quelle
    que soit la plage testée (y compris à puissance minimale = 0).

    cell_z_offset : décalage (mm, ajouté à z_work) appliqué UNIQUEMENT
    aux cellules -- pour le remplissage Défocus (gravure), même principe
    que le mode Hachures 2D : le tracé reste identique, seul le Z de
    gravure change (bec écarté du foyer, faisceau élargi, cf.
    defocus_for_fill_spacing). Les étiquettes restent TOUJOURS au foyer
    normal (z_work), pour rester nettes/lisibles quel que soit le
    remplissage testé -- d'où 2 hauteurs possibles au lieu d'une seule
    quand cell_z_offset != 0 (un seul changement de Z entre les deux
    "bandes" cellules/étiquettes, pas un par cellule).

    use_proximity : réordonne les chaînes par plus proche voisin
    (heuristique gloutonne, comme le mode Découpe multi-passes) --
    appliquée SÉPARÉMENT à chaque bande de Z (cellules, puis étiquettes)
    pour ne jamais mélanger les deux bandes et garder un minimum de
    changements de Z.

    draw_border : grave le contour carré de chaque cellule (cadre net) à
    z_border (foyer, indépendant du Z des cellules -- qui peut être
    défocalisé), à border_power/border_feed. Utile surtout en remplissage
    Défocus, où les cellules sont floues : le cadre au foyer délimite
    nettement chaque carré. z_border partage le plus souvent le Z des
    étiquettes (toutes deux au foyer) -- émis dans la foulée, sans
    changement de Z superflu.

    frame_only : ne génère QUE le rectangle englobant de toute la grille
    (laser éteint), en réutilisant le même calcul de Z de sécurité que le
    job réel -- pour un fichier de VÉRIFICATION DE CADRAGE SÉPARÉ du job
    (à lancer seul sur la machine avant de lancer la grille pour de
    vrai).

    body_only : pour une OPÉRATION au sein d'un job combiné (cf.
    generate_gcode_combined) -- omet l'en-tête G21/G90/G94/M5 initial
    (émis une seule fois pour tout le job combiné), considère le laser
    DÉJÀ ARMÉ (pas de M3 ici, un seul armement pour tout le job combiné
    au lieu d'un par opération) et omet le désarmement/M2 final (émis
    une seule fois à la toute fin du job combiné).

    min_safe_z : plancher imposé à la hauteur de retrait -- cf.
    generate_gcode_curved pour l'explication complète (transit sûr entre
    opérations d'un job combiné)."""
    if label_power is None:
        label_power = LABEL_POWER
    if label_feed is None:
        label_feed = LABEL_FEED
    if not cells:
        return None

    z_cells = z_work + cell_z_offset

    def _order_band(band):
        # order_open_chains_by_proximity (pas order_chains_for_cutting) :
        # les traits de hachures sont des segments OUVERTS -- il faut
        # pouvoir entrer par n'importe laquelle de leurs deux extremites
        # pour enchainer en zigzag continu (fin d'un trait -> extremite
        # la plus proche du suivant), pas toujours revenir a une base
        # fixe comme le ferait l'ordonnancement pense pour des contours
        # FERMES de decoupe.
        if not use_proximity or len(band) < 2:
            return band
        chains_only = [item[0] for item in band]
        order = order_open_chains_by_proximity(chains_only)
        result = []
        for idx, reverse in order:
            chain, power, feed, comment = band[idx]
            if reverse:
                chain = list(reversed(chain))
            result.append((chain, power, feed, comment))
        return result

    # Cellules gravées UNE À UNE, dans l'ordre de lecture en partant du
    # BAS À GAUCHE : rangées de bas en haut (row croissant), et de gauche
    # à droite dans chaque rangée (col croissant). L'optimisation par
    # proximité, si activée, ne réordonne QUE les hachures À L'INTÉRIEUR
    # d'une même cellule -- jamais entre cellules. Auparavant elle
    # réordonnait toutes les hachures de toute la grille ensemble, ce qui
    # entrelaçait les cellules (trajet illisible, sauts partout, une même
    # cellule reprise en plusieurs fois).
    cell_band = []  # [(chain, power, feed, comment), ...] à z_cells
    lsp = dict(line_style_params or {})
    for cell in sorted(cells, key=lambda c: (c["row"], c["col"])):
        comment = "(-- Cellule L{} C{} : S={:.0f} F={:.0f} --)".format(
            cell["row"], cell["col"], cell["power"], cell["feed"])
        chains = _apply_grid_line_style(chain_edges(cell["edges"]), line_style, lsp)
        cell_chains = [(chain, cell["power"], cell["feed"], comment) for chain in chains]
        cell_band.extend(_order_band(cell_chains))

    label_band = []  # [(chain, power, feed, comment), ...] à z_work (toujours au foyer)
    if label_edges:
        label_comment = "(-- Étiquettes de repérage (puissance/vitesse) : S={:.0f} F={:.0f} --)".format(
            label_power, label_feed)
        for chain in chain_edges(label_edges):
            label_band.append((chain, label_power, label_feed, label_comment))
    label_band = _order_band(label_band)

    # Cadre net (contour carré au foyer) : même ordre de cellules que la
    # bande de remplissage. Un seul commentaire d'en-tête pour toute la
    # bande (pas un par cellule -- 100 lignes de commentaire en trop).
    #
    # z_border par défaut = LE foyer, lu au moment de l'appel. Il valait
    # 8.5 en dur dans la signature, une deuxième écriture de la même
    # constante : le jour où la focale change (8,5 -> 8,0 le 30/07/2026),
    # l'une bouge et l'autre reste. Un défaut d'argument ne peut pas
    # référencer Z_WORK_MM directement -- il serait figé à l'import, avant
    # que le profil du laser ne l'ait ajusté.
    if z_border is None:
        z_border = Z_WORK_MM
    border_band = []  # [(chain, power, feed, comment), ...] à z_border
    if draw_border:
        border_comment = "(-- Cadre net au foyer autour de chaque carré : S={:.0f} F={:.0f} Z={:.4f} --)".format(
            border_power, border_feed, z_border)
        for cell in sorted(cells, key=lambda c: (c["row"], c["col"])):
            for chain in chain_edges(cell["border_edges"]):
                border_band.append((chain, border_power, border_feed, border_comment))

    if not cell_band and not label_band and not border_band:
        return None

    z_safe = max(z_work, z_cells, z_border if draw_border else z_work) + TRAVEL_CLEARANCE_MM
    if min_safe_z is not None:
        z_safe = max(z_safe, min_safe_z)

    lines = []
    lines.append("(G-Code Laser - Grille de test puissance/vitesse)")
    lines.append("(Cellules : {})".format(len(cells)))
    if cell_z_offset:
        lines.append("(Z cellules (défocus) : {:.4f}mm -- Z étiquettes (foyer) : {:.4f}mm)".format(z_cells, z_work))
    else:
        lines.append("(Z de travail fixe : {:.4f}mm -- un seul plongeon/une seule remontée pour tout le job)".format(z_work))
    if use_proximity:
        lines.append("(Ordre : cellules par rangee du bas vers le haut, gauche a droite ; hachures optimisees dans chaque cellule)")
    else:
        lines.append("(Ordre : cellules par rangee du bas vers le haut, gauche a droite)")
    if draw_border:
        lines.append("(Cadre net : contour de chaque carre grave au foyer Z={:.4f}mm)".format(z_border))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        all_pts = [p for item in cell_band + label_band + border_band for p in item[0]]
        if all_pts:
            lines.extend(build_frame_trace(
                min(p.x for p in all_pts), max(p.x for p in all_pts),
                min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only
    current_z = [None]  # None = position de retrait -- liste pour rester mutable sans "nonlocal"

    def _travel_to(x, y, target_z):
        if current_z[0] != target_z:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_safe))
            lines.append("G0 Z{:.4f}".format(target_z))
            current_z[0] = target_z
        else:
            lines.append("G0 X{:.4f} Y{:.4f}".format(x, y))

    def _emit_band(band, target_z):
        nonlocal state_armed
        last_comment = None
        for chain, power, feed, comment in band:
            if comment != last_comment:
                lines.append(comment)
                last_comment = comment
            p0 = chain[0]
            _travel_to(p0.x, p0.y, target_z)

            if not state_armed:
                lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
                state_armed = True
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=power))

            for p in chain[1:]:
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(p.x, p.y, feed))

            lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))

    # Cellules d'abord (Z éventuellement défocalisé), puis les deux repères
    # au foyer (cadre, étiquettes) : s'ils partagent le même Z, current_z
    # évite tout retrait entre eux.
    _emit_band(cell_band, z_cells)
    _emit_band(border_band, z_border)
    _emit_band(label_band, z_work)

    if current_z[0] is not None:
        lines.append("G0 Z{:.4f}".format(z_safe))

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE 1 : MARQUAGE SUR SURFACE COURBE
# ==========================================================================
class _IDWHeight(object):
    """Estime la hauteur locale par pondération inverse à la distance sur
    le nuage de points déjà gravés. Repli si aucun objet 3D de référence
    n'est sélectionné."""

    def __init__(self, points, k=6, power=2.0):
        self.points = [(p.x, p.y, p.z) for p in points]
        self.k = min(k, len(self.points)) if self.points else 0
        self.power = power
        # Nuage PLAT (marquage/remplissage 2D : tous les Z identiques) :
        # l'IDW d'une constante EST cette constante. Sans ce raccourci,
        # chaque z_at rebalaye TOUT le nuage (mesuré ~25 ms sur un
        # remplissage de 150 000 points) ; à raison d'un appel par pas de
        # transit (~9 000 transits sur un tracé SVG dense), la génération
        # G-code figeait l'interface plusieurs minutes... pour interpoler
        # une valeur unique.
        self.z_constant = None
        if self.points:
            z0 = self.points[0][2]
            if all(abs(pz - z0) < 1e-9 for _, _, pz in self.points):
                self.z_constant = z0

    def z_at(self, x, y):
        if not self.points:
            return None
        if self.z_constant is not None:
            return self.z_constant
        dists = [((px - x) ** 2 + (py - y) ** 2, pz) for px, py, pz in self.points]
        # nsmallest (O(N log k)) au lieu d'un tri complet (O(N log N)) :
        # appelé à chaque pas de transit, sur un nuage qui peut compter
        # des dizaines de milliers de points projetés.
        nearest = heapq.nsmallest(self.k, dists, key=lambda t: t[0])
        for d2, z in nearest:
            if d2 < 1e-9:
                return z
        weights = [1.0 / (d2 ** (self.power / 2.0)) for d2, _ in nearest]
        wsum = sum(weights)
        return sum(w * z for w, (_, z) in zip(weights, nearest)) / wsum


class _MeshZProbe(object):
    """Sonde Z par projection verticale sur l'objet 3D de référence.

    Remplace l'ancien raycast par opération booléenne OpenCascade
    (`common` ligne/solide, ~5ms PAR POINT : sur un remplissage dense,
    des dizaines de milliers de points = plusieurs MINUTES de calcul,
    mesuré au profileur à 99% du temps total). Ici la surface est
    tessellée UNE FOIS en triangles (C++ OpenCascade, rapide), indexés
    dans une grille XY ; chaque requête Z se réduit alors à un test
    barycentrique 2D sur les quelques triangles de la cellule --
    quelques microsecondes, sans aucune opération géométrique.

    L'erreur Z est bornée par MESH_PROBE_DEVIATION_MM (écart maximal
    autorisé entre le maillage et la vraie surface), et l'interpolation
    linéaire dans chaque triangle donne un Z continu -- pas de
    mémoïsation par cellule, donc pas de tracé en dents de scie."""

    def __init__(self, shape_3d, deviation=MESH_PROBE_DEVIATION_MM):
        self.shape = shape_3d
        self.last_z = shape_3d.BoundBox.ZMax
        self.misses = 0

        verts, facets = shape_3d.tessellate(deviation)
        tris = []
        for i1, i2, i3 in facets:
            p1, p2, p3 = verts[i1], verts[i2], verts[i3]
            det = (p2.x - p1.x) * (p3.y - p1.y) - (p3.x - p1.x) * (p2.y - p1.y)
            if abs(det) < 1e-12:
                continue  # triangle vertical : invisible en projection Z
            tris.append((p1.x, p1.y, p1.z,
                         p2.x - p1.x, p2.y - p1.y, p2.z - p1.z,
                         p3.x - p1.x, p3.y - p1.y, p3.z - p1.z,
                         1.0 / det))
        self._tris = tris

        bb = shape_3d.BoundBox
        area = max(bb.XLength * bb.YLength, 1e-9)
        # ~4 triangles par cellule en moyenne : peu de candidats par
        # requête sans exploser le coût d'indexation
        self._cell = max(math.sqrt(area / max(len(tris), 1)) * 2.0, 1e-3)
        grid = defaultdict(list)
        for idx, t in enumerate(tris):
            x1, y1 = t[0], t[1]
            xs = (x1, x1 + t[3], x1 + t[6])
            ys = (y1, y1 + t[4], y1 + t[7])
            ix0 = int(math.floor(min(xs) / self._cell))
            ix1 = int(math.floor(max(xs) / self._cell))
            iy0 = int(math.floor(min(ys) / self._cell))
            iy1 = int(math.floor(max(ys) / self._cell))
            for ix in range(ix0, ix1 + 1):
                for iy in range(iy0, iy1 + 1):
                    grid[(ix, iy)].append(idx)
        self._grid = dict(grid)

    def matches(self, shape_3d):
        return self.shape is shape_3d

    def z_at_or_none(self, x, y):
        """Z de la surface sous (x,y), ou None hors de la silhouette.
        En cas de recouvrements (surplombs), renvoie le Z le plus haut,
        comme l'ancien raycast (max des intersections)."""
        cands = self._grid.get((int(math.floor(x / self._cell)),
                                int(math.floor(y / self._cell))))
        if not cands:
            return None
        eps = 1e-9
        best = None
        tris = self._tris
        for idx in cands:
            (x1, y1, z1, ux, uy, uz, vx, vy, vz, inv_det) = tris[idx]
            dx = x - x1
            dy = y - y1
            u = (dx * vy - dy * vx) * inv_det
            if u < -eps or u > 1.0 + eps:
                continue
            v = (dy * ux - dx * uy) * inv_det
            if v < -eps or u + v > 1.0 + eps:
                continue
            z = z1 + u * uz + v * vz
            if best is None or z > best:
                best = z
        return best

    def z_at(self, x, y):
        z = self.z_at_or_none(x, y)
        if z is None:
            self.misses += 1
            # Repli identique à l'ancienne sonde : dernière hauteur
            # connue (normal en bord de zone).
            return self.last_z
        self.last_z = z
        return z


def make_ray_probe(shape_3d):
    """Construit une sonde Z réutilisable pour `probe=` de
    generate_gcode_curved(_cut) -- à garder d'un appel à l'autre dans un
    panneau de tâches (aperçu durée/cadrage/trajet/génération finale) pour
    ne pas re-tesseller la surface à chaque recalcul alors que seul
    reference_shape en détermine le résultat (feed/z_focus/marge/
    puissance n'affectent que l'usage qui en est fait, pas la sonde
    elle-même)."""
    return _MeshZProbe(shape_3d)


def _est_reference_3d(shape):
    """Vrai objet 3D à sonder pour le Z : un solide, ou une géométrie
    ÉTENDUE EN Z (dôme, relief, plan incliné). Les faces PLATES à Z
    constant (tracés d'un SVG importé, sketch rempli...) sont des MOTIFS
    à graver, pas des références -- renvoie False pour elles.
    NB : le TYPE de surface ne compte pas -- l'importateur SVG pose ses
    faces sur des BSplineSurface géométriquement plates (ZLength = 0),
    un test « surface non plane » les prendrait toutes pour des reliefs.
    Seule l'étendue réelle en Z fait foi (tolérance 0,01 mm : bruit
    numérique d'une face plate, négligeable devant un vrai relief)."""
    if getattr(shape, "Solids", None):
        return True
    faces = getattr(shape, "Faces", None) or []
    if not faces:
        return False
    bb = getattr(shape, "BoundBox", None)
    return bool(bb is not None and bb.ZLength > 0.01)


def split_selection(selection):
    """Sépare la sélection entre objets-sources d'edges (à graver) et
    objet de référence 3D (à sonder pour le Z). Un objet n'est reconnu
    comme référence que s'il est RÉELLEMENT 3D (cf. _est_reference_3d) :
    les faces planes restent des sources de motif.

    Si aucun solide 3D n'est sélectionné à côté du motif, on retombe sur
    LaserAtelierSurfaceRef (mémorisé par run_projection à la création du
    motif projeté) : plus besoin de RESÉLECTIONNER le solide à chaque
    génération, seul le motif suffit. Absent sur les motifs créés avant
    cette mémorisation -- la sélection manuelle du solide reste alors le
    seul moyen d'activer la sonde exacte."""
    edge_sel = []
    reference_shape = None
    for sel_obj in selection:
        obj = sel_obj.Object
        shape = getattr(obj, 'Shape', None)
        if shape is not None and shape.Faces and _est_reference_3d(shape):
            if reference_shape is None:
                reference_shape = shape
            else:
                FreeCAD.Console.PrintWarning(
                    "Plusieurs objets 3D de référence sélectionnés -- '{}' ignoré.\n".format(obj.Label))
            continue
        edge_sel.append(sel_obj)
    if reference_shape is None:
        for sel_obj in edge_sel:
            ref_obj = getattr(sel_obj.Object, "LaserAtelierSurfaceRef", None)
            ref_shape = getattr(ref_obj, "Shape", None)
            if ref_shape is not None:
                reference_shape = ref_shape
                break
    return edge_sel, reference_shape


def generate_gcode_curved(edges, power, feed, z_focus, marge_survol, reference_shape=None,
                           style="plein", style_params=None,
                           pre_gcode="", post_gcode="", frame_only=False, quiet=False, body_only=False,
                           min_safe_z=None, probe=None, dose_spot_d=None, warnings_out=None):
    """style / style_params : style de trait ("plein" = trait continu
    historique, "tirets", "pointille", "vague" -- cf. la section STYLES DE
    TRAIT). Les styles suivent le RELIEF comme le trait plein : les tirets
    et la vague sont découpés/rééchantillonnés le long de la chaîne (Z
    natif interpolé), les points du pointillé se posent sur la surface
    (petits G0 directs entre points voisins -- distance trop courte pour
    qu'un relief passe entre deux points sous le bec). En "vague", le Z
    machine oscille de 0 à wave_amplitude AU-DESSUS du suivi de relief
    normal (foyer) -- la hauteur de sécurité en tient compte.

    frame_only : ne génère QUE le rectangle englobant (laser éteint),
    en réutilisant le même calcul de Z de sécurité que le job réel --
    pour un fichier de VÉRIFICATION DE CADRAGE SÉPARÉ du job (à lancer
    seul sur la machine avant de graver pour de vrai), plutôt qu'un
    aperçu embarqué au début du même fichier (facile à lancer par
    erreur en pensant vérifier alors que le laser va réellement graver
    juste après).

    quiet : coupe les avertissements Report View -- pour un appel
    d'APERÇU EN DIRECT (durée estimée recalculée à chaque changement de
    champ dans le panneau) qui ne doit pas spammer la vue Rapport du
    même avertissement a chaque frappe.

    body_only : pour une OPÉRATION au sein d'un job combiné (cf.
    generate_gcode_combined) -- omet l'en-tête G21/G90/G94/M5 initial
    (émis une seule fois pour tout le job combiné), considère le laser
    DÉJÀ ARMÉ (pas de M3 ici, un seul armement pour tout le job combiné
    au lieu d'un par opération) et omet le désarmement/M2 final (émis
    une seule fois à la toute fin du job combiné).

    min_safe_z : plancher imposé à la hauteur de retrait DE CETTE
    OPÉRATION SEULE -- dans un job combiné, chaque opération ne connaît
    QUE sa propre géométrie, donc sa propre hauteur de sécurité peut être
    plus basse que le relief de l'opération PRÉCÉDENTE à l'endroit où
    elle s'est arrêtée : sans plancher commun, la première remontée de la
    nouvelle opération replongerait tout droit vers le bas AU MAUVAIS
    ENDROIT (encore sur l'ancienne opération en X/Y) avant même d'avoir
    rejoint sa propre géométrie -- collision constatée en pratique
    (gravure puis découpe sur un même dôme). generate_gcode_combined
    calcule ce plancher comme le maximum des hauteurs de sécurité de
    TOUTES les opérations du job avant de générer quoi que ce soit
    (cf. _operation_intrinsic_safe_z).

    probe : sonde make_ray_probe(reference_shape) déjà construite, à
    réutiliser si l'appelant refait plusieurs appels successifs sur LE
    MÊME reference_shape (ex: aperçu durée recalculé à chaque frappe dans
    un panneau de tâches) -- évite de relancer tous les raycasts de
    surface à chaque appel alors que seule la géométrie de référence en
    détermine le résultat. Ignorée si son .shape ne correspond pas à
    reference_shape (sécurité si l'appelant se trompe de sonde)."""
    if not edges:
        return None

    chains = chain_edges(edges)
    dose_slowed = [0]
    if not chains:
        return None
    # Réordonne pour minimiser le trajet à vide entre chaînes disjointes
    # (hachures d'un remplissage complexe surtout) -- le tracé de chaque
    # chaîne n'est pas modifié, seul l'ORDRE et le SENS de parcours.
    chains = order_chains_by_proximity(chains)

    style_params = dict(style_params or {})
    dash_len = style_params.get("dash_len", 3.0)
    gap_len = style_params.get("gap_len", 2.0)
    dot_spacing = style_params.get("dot_spacing", 1.5)
    dot_dwell_s = style_params.get("dot_dwell_s", 0.05)
    wave_period = style_params.get("wave_period", 5.0)
    wave_amp = style_params.get("wave_amplitude", 0.0) if style == "vague" else 0.0

    if not quiet and style == "vague":
        peak = wave_peak_z_feed(wave_amp, feed, wave_period)
        if peak > Z_MAX_FEED_MM_MIN:
            FreeCAD.Console.PrintWarning(
                "Vague : vitesse Z crête ~{:.0f}mm/min > limite Z supposée "
                "({:.0f}mm/min, cf. Préférences) -- LinuxCNC ralentira le trajet "
                "pour suivre (pas de danger, job juste plus lent). Allonger la "
                "période ou réduire l'amplitude/le feed pour l'éviter.\n".format(
                    peak, Z_MAX_FEED_MM_MIN))

    all_pts = [p for chain in chains for p in chain]
    z_min = min(p.z for p in all_pts)
    z_max = max(p.z for p in all_pts)
    z_offset = z_focus - z_min
    z_safe_start_end = z_max + z_offset + wave_amp + marge_survol + 5.0
    if min_safe_z is not None:
        z_safe_start_end = max(z_safe_start_end, min_safe_z)

    if reference_shape is not None:
        if probe is not None and probe.matches(reference_shape):
            height_probe = probe
        else:
            height_probe = _MeshZProbe(reference_shape)
        probe_kind = "sonde exacte sur l'objet 3D sélectionné"
        nozzle_check_active = True
    else:
        height_probe = _IDWHeight(all_pts)
        probe_kind = "interpolation (aucun objet 3D de référence sélectionné)"
        nozzle_check_active = False  # pas de double approximation sur de l'interpolation

    def to_machine_z(z_native):
        return z_native + z_offset

    lines = []
    lines.append("(G-Code Laser - Marquage : chaînes + transit continu)")
    lines.append("(Chaînes : {} (à partir de {} segments d'origine))".format(len(chains), len(edges)))
    if style != "plein":
        style_names = {"tirets": "tirets", "pointille": "pointille",
                   "vague": "vague defocus, S compense en fluence",
                   "degrade": "degrade selon une DIRECTION (angle)",
                   "degrade_trace": "degrade le long du TRACE"}
        lines.append("(Style de trait : {})".format(style_names.get(style, style)))
        if style == "degrade_trace":
            sp = style_params or {}
            lines.append("(Fuseau : Z +{:.1f} -> +{:.1f}mm par trace{})".format(
                sp.get("deg_z_min", 0.0), sp.get("deg_z_max", 0.0),
                ", aller-retour sur boucle fermee"
                if sp.get("deg_aller_retour") else ""))
    lines.append("(Transit : hauteur de travail + {:.2f}mm, {})".format(marge_survol, probe_kind))
    lines.append("(Contrôle bec (cône {:.0f}mm) : {})".format(
        NOZZLE_CONE_TOP_RADIUS * 2, "actif" if nozzle_check_active else "inactif (pas de sonde exacte)"))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe_start_end))

    if frame_only:
        lines.extend(build_frame_trace(
            min(p.x for p in all_pts), max(p.x for p in all_pts),
            min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe_start_end))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only
    current_pos = None
    nozzle_marking_warnings = 0
    nozzle_marking_points = []
    check_state = {"last": None}

    def _mark_check(p):
        # Pendant la gravure, le Z est imposé par le focus correct : un
        # désaccord avec le bec est seulement signalé, jamais corrigé (le
        # corriger changerait le focus). Contrôlé tous les
        # NOZZLE_CHECK_INTERVAL_MM (pas à chaque point discrétisé --
        # inutile pour un cône de 16mm, et ruineux en performance sur un
        # remplissage dense). Les points signalés (coordonnées NATIVES,
        # avant to_machine_z) sont gardés pour create_collision_markers --
        # un chiffre seul ne dit pas OÙ regarder sur la pièce.
        nonlocal nozzle_marking_warnings
        if not nozzle_check_active:
            return
        lp = check_state["last"]
        if lp is not None and math.hypot(p.x - lp.x, p.y - lp.y) < NOZZLE_CHECK_INTERVAL_MM:
            return
        required = nozzle_clearance_z(p.x, p.y, p.z, height_probe.z_at, 0.0)
        if required > p.z + 0.05:
            nozzle_marking_warnings += 1
            nozzle_marking_points.append(FreeCAD.Vector(p.x, p.y, p.z))
        check_state["last"] = p

    beam_on = CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=power)
    beam_off = CMD_BEAM_OFF.format(sel=SPINDLE_SELECT)

    # Style "degrade" : le DÉFOCUS varie linéairement le long d'une
    # direction (deg_angle), de deg_z_min à deg_z_max (mm au-dessus du
    # suivi normal) -- hachures dont la largeur/l'intensité évoluent d'un
    # bord à l'autre de la pièce. Variation LENTE (à l'échelle de la
    # pièce), le Z suit sans peine contrairement à une modulation par
    # pixel. Projection normalisée sur l'emprise réelle des chaînes.
    deg_dz = None
    if style == "degrade" and chains:
        deg_dz = rampe_direction_dz(
            chains, style_params.get("deg_angle", 0.0),
            style_params.get("deg_z_min", 0.0),
            style_params.get("deg_z_max", 0.0))

    for chain in chains:
        p0 = chain[0]

        # Style « dégradé le long du tracé » : la rampe est PROPRE À CETTE
        # CHAÎNE (abscisse curviligne), contrairement à "degrade" dont la
        # projection est globale. D'où un calcul ici, dans la boucle, et
        # non une fermeture calculée une fois pour toutes.
        dzs_trace = None
        if style == "degrade_trace":
            dzs_trace = rampe_trace_dz(
                chain,
                style_params.get("deg_z_min", 0.0),
                style_params.get("deg_z_max", 0.0),
                bool(style_params.get("deg_aller_retour", False)))

        if current_pos is None:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(p0.x, p0.y, z_safe_start_end))
        else:
            dist = math.hypot(p0.x - current_pos.x, p0.y - current_pos.y)
            n_steps = max(1, int(dist / TRANSIT_SAMPLE_STEP))
            for k in range(1, n_steps + 1):
                t = k / float(n_steps)
                x = current_pos.x + (p0.x - current_pos.x) * t
                y = current_pos.y + (p0.y - current_pos.y) * t
                z_local = height_probe.z_at(x, y)
                if z_local is None:
                    z_local = p0.z
                if nozzle_check_active:
                    z_local = nozzle_clearance_z(x, y, z_local, height_probe.z_at, 0.0)
                lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(
                    x, y, to_machine_z(z_local) + marge_survol))

        # Style "degrade" : l'approche doit déjà inclure le décalage du
        # PREMIER point -- sinon le premier G1 (faisceau allumé, juste
        # après) saute d'un coup de Z natif à Z natif + deg_dz(p1) sur
        # ~DISCRETIZE_DISTANCE de déplacement XY, au lieu d'une transition
        # douce comme "vague" (qui, lui, part toujours de dz=0).
        z0_deg = deg_dz(p0) if style == "degrade" and deg_dz is not None else 0.0
        if dzs_trace is not None:
            z0_deg = dzs_trace[0]
        lines.append("G0 Z{:.4f}".format(to_machine_z(p0.z) + z0_deg))

        if not state_armed:
            lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
            state_armed = True

        check_state["last"] = p0

        if style == "pointille":
            # Points sur la surface : MICRO-TRAIT à chaque point (jamais
            # de G4 faisceau allumé, cf. dot_micro_stroke), petits G0
            # directs entre points voisins (dot_spacing) -- le suivi de
            # relief est porté par le Z de chaque point.
            dots = dot_positions(chain, dot_spacing)
            seg, f_dot = dot_micro_stroke(dot_spacing, dot_dwell_s)
            half = seg / 2.0
            for i, d in enumerate(dots):
                ux, uy = dot_stroke_dir(dots, i)
                lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(
                    d.x - ux * half, d.y - uy * half, to_machine_z(d.z)))
                _mark_check(d)
                lines.append(beam_on)
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    d.x + ux * half, d.y + uy * half, to_machine_z(d.z), f_dot))
                lines.append(beam_off)
        elif style == "tirets":
            for piece, on in dash_chain(chain, dash_len, gap_len):
                if on:
                    lines.append(beam_on)
                for p in piece[1:]:
                    _mark_check(p)
                    lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                        p.x, p.y, to_machine_z(p.z), feed))
                if on:
                    lines.append(beam_off)
        elif style == "vague":
            samples = wave_resample(chain, wave_period, wave_amp)
            s_wave = wave_fluence_powers(power, samples, wave_amp)
            lines.extend(cmd_power_prefix(s_wave[0]))
            if cmd_power_suffix(s_wave[0]):
                lines.append(cmd_power_suffix(s_wave[0]))
            for (p, dz), s_pt in zip(samples[1:], s_wave[1:]):
                _mark_check(p)
                lines.extend(cmd_power_prefix(s_pt))
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f} {}".format(
                    p.x, p.y, to_machine_z(p.z) + dz, feed,
                    cmd_power_suffix(s_pt)))
            lines.append(beam_off)
        elif style == "degrade_trace" and dzs_trace is not None:
            lines.append(beam_on)
            for p, dz in zip(chain[1:], dzs_trace[1:]):
                _mark_check(p)
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    p.x, p.y, to_machine_z(p.z) + dz, feed))
            lines.append(beam_off)
        elif style == "degrade" and deg_dz is not None:
            samples = chain      # déjà discrétisé dense (DISCRETIZE_DISTANCE)
            lines.append(beam_on)
            for p in samples[1:]:
                _mark_check(p)
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    p.x, p.y, to_machine_z(p.z) + deg_dz(p), feed))
            lines.append(beam_off)
        else:
            # DOSE : une chaine plus courte que le point (dose_spot_d,
            # diametre du point au Z de travail) recoit moins d'exposition
            # -- un point du materiau ne voit passer le faisceau que
            # L/point du temps normal (constate : hachures fines grises
            # dans les zones etroites d'un remplissage defocus). On
            # ralentit F proportionnellement (le HAL garde S plein a
            # vitesse atteinte) pour retablir la dose.
            chain_feed = feed
            if dose_spot_d and dose_spot_d > 0:
                clen = _chain_cumlen(chain)[-1]
                if 0 < clen < dose_spot_d:
                    chain_feed = max(feed * clen / dose_spot_d, 30.0)
                    dose_slowed[0] += 1
            lines.append(beam_on)
            for p in chain[1:]:
                _mark_check(p)
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    p.x, p.y, to_machine_z(p.z), chain_feed))
            lines.append(beam_off)

        current_pos = chain[-1]

    lines.append("G0 Z{:.4f}".format(z_safe_start_end))
    if dose_slowed[0]:
        lines.append("(Dose : {} chaine(s) plus courtes que le point "
                     "[{:.2f}mm] ralenties)".format(dose_slowed[0], dose_spot_d))

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")

    if not quiet and reference_shape is not None and height_probe.misses:
        FreeCAD.Console.PrintWarning(
            "{} points de transit sans intersection avec l'objet de référence "
            "(dernière hauteur connue réutilisée -- normal en bord de zone)\n".format(height_probe.misses))
    if not quiet and nozzle_marking_warnings:
        FreeCAD.Console.PrintWarning(
            "{} points de GRAVURE où le bec (cône) serait plus proche de la surface "
            "voisine que le point focal lui-même -- Z non modifié (focus imposé), "
            "à vérifier visuellement sur ces zones.\n".format(nozzle_marking_warnings))
    # La vue Rapport n'est pas toujours ouverte : le panneau appelant a
    # besoin de CE chiffre pour décider d'afficher une vraie fenêtre
    # d'avertissement, pas seulement un message de console.
    if warnings_out is not None:
        warnings_out["nozzle_marking_warnings"] = nozzle_marking_warnings
        warnings_out["nozzle_marking_points"] = nozzle_marking_points

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE 2 : DÉCOUPE MULTI-PASSES SUR MATÉRIAU PLAT
# ==========================================================================
# Tableau constructeur (doc LT-80W-AA-PRO) : épaisseur -> cale de réglage.
#
# CORRECTION IMPORTANTE (bug précédent) : Z=0 chez toi correspond au BEC
# qui touche la surface (zéro au papier), pas au foyer. Dans cette
# convention, Z doit rester POSITIF (le bec reste physiquement au-dessus
# de la matière) -- c'est la lumière qui converge plus bas, à travers
# l'air, jusqu'au foyer. La valeur "cale" du tableau constructeur EST
# directement cette hauteur bec-au-dessus-de-la-surface (c'était déjà son
# rôle physique d'origine : écarter le bec de la pièce de cette distance).
# Avec un axe Z piloté, plus besoin de cale physique : on commande cette
# même hauteur directement, et elle descend PROGRESSIVEMENT VERS ZÉRO
# (jamais en dessous) au fil des passes, à mesure que le foyer doit
# suivre le fond de coupe de plus en plus profond.
FOCUS_TABLE = {2: 7, 3: 7, 4: 5, 5: 5, 6: 5, 8: 4}  # épaisseur(mm) -> cale/hauteur bec(mm)

# Butée de sécurité : la hauteur du bec au-dessus de la surface ne
# descend JAMAIS en dessous de cette valeur, quelle que soit l'épaisseur
# ou le nombre de passes demandé -- garde-fou contre une collision même
# si le calcul "idéal" voudrait descendre plus bas (cf. avertissement
# imprimé si la butée est effectivement utilisée).
SAFE_MIN_NOZZLE_HEIGHT_MM = 1.5

# Plage testée par le constructeur : 2-8mm. Au-delà, extrapolation non
# vérifiée -- à confirmer par un essai. D'après les retours utilisateurs
# (forums LightBurn, Diode Laser Wiki, IndustryArena) pour un diode 10W
# comme le LT-80W-AA-PRO : le constructeur annonce 8mm (jusqu'à 8-10mm)
# en une passe ; au-delà, plusieurs passes sont nécessaires et la qualité
# (calcination) se dégrade progressivement. Le chiffre de "30mm max" vu
# sur certaines fiches produit n'est pas corroboré par des sources
# indépendantes -- à traiter avec prudence.
MAX_THICKNESS_WARNING_MM = 12.0

# Pas Z par passe : garder un pas modeste (0.5-1mm typique, cf. Diode
# Laser Wiki / LightBurn "Z step per pass") plutôt qu'un grand pas sur
# peu de passes. Certains utilisateurs expérimentés notent qu'un pas trop
# grand peut faire que les parois du trait déjà coupé (plus étroit)
# bloquent partiellement le faisceau sur les passes suivantes -- ce n'est
# pas rédhibitoire (LightBurn implémente la fonction en standard), mais
# mieux vaut plus de passes à pas modeste qu'une grosse division brute.
RECOMMENDED_MAX_STEP_MM = 1.5


def nozzle_height_for_thickness(thickness):
    """Hauteur du bec AU-DESSUS de la surface (Z=0 = bec touche la
    surface, valeurs POSITIVES uniquement), interpolée/extrapolée depuis
    le tableau constructeur."""
    keys = sorted(FOCUS_TABLE)
    if thickness <= keys[0]:
        return FOCUS_TABLE[keys[0]]
    if thickness >= keys[-1]:
        # extrapolation linéaire au-delà du dernier point mesuré -- non
        # vérifiée par le constructeur, cf. avertissement plus haut
        t0, t1 = keys[-2], keys[-1]
        p0, p1 = FOCUS_TABLE[t0], FOCUS_TABLE[t1]
        slope = (p1 - p0) / float(t1 - t0)
        return p1 + slope * (thickness - t1)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i], keys[i + 1]
        if t0 <= thickness <= t1:
            p0, p1 = FOCUS_TABLE[t0], FOCUS_TABLE[t1]
            frac = (thickness - t0) / float(t1 - t0)
            return p0 + frac * (p1 - p0)


def _point_in_polygon(x, y, poly):
    """Ray casting standard. poly : liste de (x,y)."""
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _polygon_area(poly):
    n = len(poly)
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def compute_nesting_depths(chains):
    """Profondeur d'imbrication de chaque chaîne (0 = contour extérieur,
    1 = trou, 2 = îlot dans un trou, etc.) -- is_hole = profondeur impaire.
    Compare par AIRE (une chaîne n'est testée que contre celles de plus
    grande aire) : sans ça, le centre d'un grand contour peut tomber
    géométriquement DANS un petit trou concentrique, donnant à tort une
    containment symétrique. Testé sur plusieurs cas avant intégration."""
    polys = [[(p.x, p.y) for p in chain] for chain in chains]
    areas = [_polygon_area(p) for p in polys]
    depths = []
    for i, poly_i in enumerate(polys):
        cx = sum(p[0] for p in poly_i) / len(poly_i)
        cy = sum(p[1] for p in poly_i) / len(poly_i)
        depth = 0
        for j, poly_j in enumerate(polys):
            if i == j or areas[j] <= areas[i]:
                continue
            if _point_in_polygon(cx, cy, poly_j):
                depth += 1
        depths.append(depth)
    return depths


def offset_chain_kerf(points, distance, is_hole):
    """Décale une chaîne fermée de `distance` : vers l'extérieur si
    is_hole=False (contour de pièce, compense le kerf pour sortir à la
    bonne cote), vers l'intérieur si is_hole=True (trou, pour que le trou
    fini ne soit pas agrandi par le kerf). Offset par bissectrice
    per-sommet, corrigé par le sens de parcours (winding) de la chaîne.
    Z préservé. Angles très réflexes: la butée cos_half évite un pic à
    l'infini, au prix d'une légère sous-compensation locale là où c'est
    le cas (compromis pragmatique, pas un offset de polygone garanti
    sans auto-intersection dans tous les cas de figure)."""
    if distance <= 0:
        return points
    pts2d = [(p.x, p.y) for p in points]
    z_list = [p.z for p in points]
    closed = len(pts2d) > 1 and math.hypot(pts2d[0][0] - pts2d[-1][0], pts2d[0][1] - pts2d[-1][1]) < 1e-9
    if closed:
        pts2d = pts2d[:-1]
        z_list = z_list[:-1]

    n = len(pts2d)
    if n < 3:
        return points

    area = 0.0
    for i in range(n):
        x1, y1 = pts2d[i]
        x2, y2 = pts2d[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    winding = 1.0 if area > 0 else -1.0
    sign = 1.0 if not is_hole else -1.0

    result = []
    for i in range(n):
        xp, yp = pts2d[(i - 1) % n]
        xc, yc = pts2d[i]
        xn, yn = pts2d[(i + 1) % n]

        d1x, d1y = xc - xp, yc - yp
        len1 = math.hypot(d1x, d1y) or 1e-9
        d1x, d1y = d1x / len1, d1y / len1
        d2x, d2y = xn - xc, yn - yc
        len2 = math.hypot(d2x, d2y) or 1e-9
        d2x, d2y = d2x / len2, d2y / len2

        n1x, n1y = winding * d1y, -winding * d1x
        n2x, n2y = winding * d2y, -winding * d2x

        bx, by = n1x + n2x, n1y + n2y
        blen = math.hypot(bx, by)
        if blen < 1e-9:
            bx, by = n1x, n1y
            blen = math.hypot(bx, by) or 1.0
        bx, by = bx / blen, by / blen

        cos_half = max(0.2, bx * n1x + by * n1y)
        scale = distance / cos_half

        result.append(FreeCAD.Vector(xc + sign * bx * scale, yc + sign * by * scale, z_list[i]))

    if closed:
        result.append(result[0])
    return result


def _lead_in_point(points, distance, is_hole):
    """Point d'AMORCE de découpe : décalé de `distance` du premier sommet
    de la chaîne fermée, VERS LA CHUTE (extérieur pour un contour de
    pièce, intérieur pour un trou -- même convention que
    offset_chain_kerf). Le laser s'allume là, dans la matière perdue,
    puis rejoint le contour : la verrue d'allumage (le laser marque
    toujours plus fort au point de départ) reste hors du bord fini.
    Renvoie None si la chaîne est trop courte pour calculer une normale."""
    pts2d = [(p.x, p.y) for p in points]
    closed = len(pts2d) > 1 and math.hypot(pts2d[0][0] - pts2d[-1][0],
                                           pts2d[0][1] - pts2d[-1][1]) < 1e-9
    if closed:
        pts2d = pts2d[:-1]
    n = len(pts2d)
    if n < 3:
        return None

    area = 0.0
    for i in range(n):
        x1, y1 = pts2d[i]
        x2, y2 = pts2d[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    winding = 1.0 if area > 0 else -1.0
    sign = 1.0 if not is_hole else -1.0

    xp, yp = pts2d[-1]
    xc, yc = pts2d[0]
    xn, yn = pts2d[1]
    d1x, d1y = xc - xp, yc - yp
    len1 = math.hypot(d1x, d1y) or 1e-9
    d1x, d1y = d1x / len1, d1y / len1
    d2x, d2y = xn - xc, yn - yc
    len2 = math.hypot(d2x, d2y) or 1e-9
    d2x, d2y = d2x / len2, d2y / len2
    n1x, n1y = winding * d1y, -winding * d1x
    n2x, n2y = winding * d2y, -winding * d2x
    bx, by = n1x + n2x, n1y + n2y
    blen = math.hypot(bx, by)
    if blen < 1e-9:
        bx, by, blen = n1x, n1y, math.hypot(n1x, n1y) or 1.0
    bx, by = bx / blen, by / blen
    return FreeCAD.Vector(xc + sign * bx * distance, yc + sign * by * distance,
                          points[0].z)


def split_closed_chain_tabs(chain, tab_count, tab_length):
    """Découpe une chaîne FERMÉE en morceaux [(sous-chaîne, faisceau
    allumé), ...] : `tab_count` zones d'ATTACHE de `tab_length` (faisceau
    éteint, la matière y reste) réparties régulièrement le long du
    périmètre, le reste coupé. La 1re attache est centrée à un
    demi-intervalle du point de départ (l'amorce/le départ restent en
    zone coupée). Renvoie None si le périmètre est trop court pour
    accueillir les attaches (au moins ~2mm coupés entre chacune)."""
    tab_count = max(1, int(tab_count))
    cum = _chain_cumlen(chain)
    total = cum[-1]
    if total <= tab_count * (tab_length + 2.0):
        return None
    pieces = []
    s = 0.0
    for i in range(tab_count):
        center = (i + 0.5) * total / tab_count
        a, b = center - tab_length / 2.0, center + tab_length / 2.0
        if a > s + 1e-9:
            pieces.append((slice_chain(chain, s, a, cum), True))
        pieces.append((slice_chain(chain, a, b, cum), False))
        s = b
    if s < total - 1e-9:
        pieces.append((slice_chain(chain, s, total, cum), True))
    return pieces


def replicate_edges(edges, nx, ny, dx, dy):
    """Réplique les edges en matrice nx x ny au pas (dx, dy) -- pour
    découper n copies d'une même pièce en un seul job. La copie (0,0)
    est l'originale (non copiée)."""
    nx = max(1, int(nx))
    ny = max(1, int(ny))
    if nx == 1 and ny == 1:
        return list(edges)
    out = []
    for i in range(nx):
        for j in range(ny):
            if i == 0 and j == 0:
                out.extend(edges)
                continue
            for e in edges:
                c = e.copy()
                c.translate(FreeCAD.Vector(i * dx, j * dy, 0))
                out.append(c)
    return out


def order_chains_for_cutting(chains, depths, use_hole_first, use_proximity):
    """Renvoie les INDICES des chaînes dans l'ordre de découpe : si
    use_hole_first, regroupe par palier de profondeur décroissante
    (le plus imbriqué d'abord) ; à l'intérieur de chaque palier (ou sur
    l'ensemble si use_hole_first=False), réordonne par plus proche
    voisin si use_proximity (heuristique gloutonne, pas un TSP exact --
    suffisant pour réduire les déplacements à vide sans coût de calcul
    exagéré)."""
    indices = list(range(len(chains)))
    if use_hole_first:
        indices.sort(key=lambda i: -depths[i])
        groups = []
        cur_depth, cur_group = None, []
        for i in indices:
            if depths[i] != cur_depth:
                if cur_group:
                    groups.append(cur_group)
                cur_group, cur_depth = [i], depths[i]
            else:
                cur_group.append(i)
        if cur_group:
            groups.append(cur_group)
    else:
        groups = [indices]

    final_order = []
    current_pos = None
    for group in groups:
        remaining = list(group)
        if use_proximity:
            while remaining:
                if current_pos is None:
                    nxt = remaining[0]
                else:
                    nxt = min(remaining, key=lambda i: (chains[i][0].x - current_pos[0]) ** 2 +
                                                        (chains[i][0].y - current_pos[1]) ** 2)
                final_order.append(nxt)
                remaining.remove(nxt)
                # Position APRES avoir parcouru la chaine choisie -- c'est
                # chains[nxt][-1] (fin), pas chains[nxt][0] (debut) : pour
                # un contour FERME (cas normal en decoupe) les deux sont
                # le meme point donc ca ne changeait rien, mais l'ancien
                # code utilisait quand meme le mauvais bout par principe.
                current_pos = (chains[nxt][-1].x, chains[nxt][-1].y)
        else:
            final_order.extend(remaining)
    return final_order


def order_open_chains_by_proximity(chains):
    """Ordonne des chaînes OUVERTES (segments non refermés, comme des
    traits de hachures) par plus proche voisin, en choisissant EN PLUS
    par quelle EXTRÉMITÉ entrer dans chacune (donc son sens de parcours).

    Différence avec order_chains_for_cutting : cette dernière est pensée
    pour des contours FERMÉS de découpe (chain[0] == chain[-1], donc le
    sens de parcours n'affecte pas la distance de transit) et entre
    toujours par chains[i][0]. Sur des hachures OUVERTES, ça casse le
    zigzag déjà présent dans generate_hatch_edges (chaque trait alterne
    de sens pour que sa fin soit proche du début du suivant) : le laser
    repartait à chaque fois à la base fixe du trait suivant au lieu
    d'enchaîner directement par l'extrémité la plus proche -- exactement
    le trajet en dents de scie que cette fonction évite.

    Renvoie une liste de (index_original, faut_inverser) dans l'ordre de
    parcours -- comme order_chains_for_cutting renvoie des indices plutôt
    que de recopier les chaînes, pour laisser l'appelant réassocier
    facilement ses propres métadonnées (puissance/vitesse/commentaire)
    à chaque chaîne d'origine."""
    remaining = list(range(len(chains)))
    order = []
    current_pos = None
    while remaining:
        if current_pos is None:
            nxt, reverse = remaining[0], False
        else:
            nxt, reverse, best_dist = None, False, None
            for i in remaining:
                c = chains[i]
                d_start = (c[0].x - current_pos[0]) ** 2 + (c[0].y - current_pos[1]) ** 2
                d_end = (c[-1].x - current_pos[0]) ** 2 + (c[-1].y - current_pos[1]) ** 2
                if best_dist is None or d_start < best_dist:
                    best_dist, nxt, reverse = d_start, i, False
                if d_end < best_dist:
                    best_dist, nxt, reverse = d_end, i, True
        order.append((nxt, reverse))
        remaining.remove(nxt)
        c = chains[nxt]
        current_pos = (c[0].x, c[0].y) if reverse else (c[-1].x, c[-1].y)
    return order


def build_frame_trace(min_x, max_x, min_y, max_y, z_height):
    """Trace le rectangle englobant du job pour vérifier le positionnement
    avant de lancer le job réel. Laser éteint (G0 uniquement) par défaut ;
    si FRAME_POWER > 0 (Préférences), le rectangle est parcouru faisceau
    allumé à cette puissance (G1 à FRAME_FEED_MM_MIN) pour VISUALISER la
    zone de travail sur la pièce -- à régler très faible (S5-S20), juste
    de quoi voir le point sans marquer. L'armement/l'extinction sont
    gérés ici : tous les appelants encadrent déjà ce bloc d'un M5 avant
    et d'un désarmement après."""
    corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y), (min_x, min_y)]
    if FRAME_POWER <= 0:
        lines = ["(-- Cadrage : vérification du positionnement, laser éteint --)"]
        for cx, cy in corners:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(cx, cy, z_height))
        return lines
    lines = ["(-- Cadrage : vérification du positionnement, faisceau de visée S{:.0f} --)".format(FRAME_POWER)]
    lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(corners[0][0], corners[0][1], z_height))
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=FRAME_POWER))
    for cx, cy in corners[1:]:
        lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.1f}".format(cx, cy, z_height, FRAME_FEED_MM_MIN))
    lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
    return lines


def parse_gcode_toolpath(gcode_text):
    """Reparcourt un G-code déjà généré par ce module (fonctionne sur son
    propre dialecte -- lignes G0/G1 avec X/Y/Z) et sépare les
    déplacements en deux catégories : RAPIDES (G0, laser éteint pendant
    le transit) et MARQUAGE/DÉCOUPE (G1, laser allumé). Pour un aperçu
    visuel direct du trajet dans la vue 3D de FreeCAD
    (cf. create_toolpath_preview_objects), sans avoir à ouvrir le
    fichier .ngc ni un simulateur externe. Renvoie (rapid_segments,
    mark_segments), chacune une liste de (FreeCAD.Vector début,
    FreeCAD.Vector fin)."""
    x = y = z = 0.0
    rapid_segments = []
    mark_segments = []
    for line in gcode_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("("):
            continue
        tokens = line.split()
        cmd = tokens[0]
        if cmd not in ("G0", "G1"):
            continue
        nx, ny, nz = x, y, z
        for tok in tokens[1:]:
            if not tok or tok[0] not in "XYZ":
                continue
            try:
                val = float(tok[1:])
            except ValueError:
                continue
            if tok[0] == 'X':
                nx = val
            elif tok[0] == 'Y':
                ny = val
            elif tok[0] == 'Z':
                nz = val
        p1 = FreeCAD.Vector(x, y, z)
        p2 = FreeCAD.Vector(nx, ny, nz)
        if p1.distanceToPoint(p2) > 1e-9:
            (rapid_segments if cmd == "G0" else mark_segments).append((p1, p2))
        x, y, z = nx, ny, nz
    return rapid_segments, mark_segments


def curved_native_z_offset(edges, z_focus):
    """Décalage (Z machine - Z natif du document) appliqué par
    generate_gcode_curved -- même calcul que z_offset dans cette
    fonction (z_focus - z_min des chaînes), exposé ici pour que
    l'APERÇU DE TRAJET (superposé au modèle 3D natif dans la vue 3D)
    puisse ramener le Z machine du G-code exporté au Z natif du document
    (cf. shift_segments_z). Le G-code réel envoyé à la machine reste en
    Z machine (calage sur le foyer), seul l'aperçu visuel en a besoin
    autrement."""
    chains = chain_edges(edges)
    if not chains:
        return 0.0
    z_min = min(p.z for chain in chains for p in chain)
    return z_focus - z_min


def shift_segments_z(segments, dz):
    """Décale de dz la coordonnée Z de chaque segment (paires de points
    telles que renvoyées par parse_gcode_toolpath) -- utilisé pour
    ramener un aperçu de trajet du repère machine au repère natif du
    document (cf. curved_native_z_offset)."""
    if not dz:
        return segments
    return [(FreeCAD.Vector(p1.x, p1.y, p1.z + dz), FreeCAD.Vector(p2.x, p2.y, p2.z + dz))
            for p1, p2 in segments]


def create_toolpath_preview_objects(doc, rapid_segments, mark_segments, name_prefix="Apercu_Trajet"):
    """Crée/remplace deux objets Part::Feature dans le document pour
    visualiser le trajet directement dans la vue 3D -- transits en gris
    fin (G0, laser éteint), marquage/découpe réel en rouge plus épais
    (G1, laser allumé). Supprime d'abord toute version précédente du
    même aperçu (même préfixe) pour ne pas accumuler les objets à chaque
    clic. Renvoie la liste des objets créés (peut être vide si aucun
    segment)."""
    for obj in list(doc.Objects):
        if obj.Name.startswith(name_prefix):
            doc.removeObject(obj.Name)

    objs = []
    if rapid_segments:
        edges = [Part.LineSegment(p1, p2).toShape() for p1, p2 in rapid_segments]
        obj = doc.addObject("Part::Feature", name_prefix + "_Transit")
        obj.Shape = Part.Compound(edges)
        if hasattr(obj, 'ViewObject'):
            obj.ViewObject.LineColor = (0.6, 0.6, 0.6)
            obj.ViewObject.LineWidth = 1.0
        objs.append(obj)
    if mark_segments:
        edges = [Part.LineSegment(p1, p2).toShape() for p1, p2 in mark_segments]
        obj = doc.addObject("Part::Feature", name_prefix + "_Marquage")
        obj.Shape = Part.Compound(edges)
        if hasattr(obj, 'ViewObject'):
            obj.ViewObject.LineColor = (0.9, 0.1, 0.1)
            obj.ViewObject.LineWidth = 2.0
        objs.append(obj)
    doc.recompute()
    return objs


def create_collision_markers(doc, points, name_prefix="Apercu_Collision"):
    """Crée/remplace un objet Part::Feature marquant, en magenta bien
    visible (couleur absente du reste de l'aperçu : gris transit, rouge
    marquage/découpe), chaque point où le bec (cône anti-collision)
    serait trop proche de la surface voisine (cf. warnings_out de
    generate_gcode_curved / generate_gcode_curved_cut) -- un chiffre seul
    ne dit pas OÙ regarder sur la pièce. Supprime d'abord toute version
    précédente du même aperçu, même si `points` est vide (pour ne pas
    laisser des marqueurs obsolètes d'un essai précédent). Renvoie
    l'objet créé, ou None si `points` est vide."""
    for obj in list(doc.Objects):
        if obj.Name.startswith(name_prefix):
            doc.removeObject(obj.Name)
    if not points:
        return None
    verts = [Part.Vertex(p) for p in points]
    obj = doc.addObject("Part::Feature", name_prefix)
    obj.Shape = Part.Compound(verts)
    if hasattr(obj, 'ViewObject'):
        obj.ViewObject.PointColor = (1.0, 0.0, 0.8)
        obj.ViewObject.PointSize = 8
    doc.recompute()
    return obj


# ==========================================================================
# PRÉRÉGLAGES MATÉRIAU (puissance/vitesse/... sauvegardés par nom)
# ==========================================================================
# Réutilise le même fichier de config JSON que le G-code avant/après
# (load_config/save_config, cf. persistance en tête de fichier), sous une
# clé dédiée par catégorie -- "flat" (Découpe multi-passes) et "curved"
# (Marquage sur surface courbe) n'ont pas les mêmes champs, d'où des
# espaces de noms séparés plutôt qu'une liste commune.
def load_presets(category):
    """Renvoie le dict {nom: {champ: valeur, ...}} des préréglages
    sauvegardés pour cette catégorie."""
    cfg = load_config()
    return cfg.get("presets_" + category, {})


def save_preset(category, name, values):
    """Sauvegarde (ou remplace) un préréglage nommé pour cette
    catégorie."""
    cfg = load_config()
    _ensure_lasers(cfg)
    key = "presets_" + category
    presets = cfg.get(key, {})
    presets[name] = values
    cfg[key] = presets
    _mirror_data_to_active_laser(cfg)
    save_config(cfg)


def delete_preset(category, name):
    """Supprime un préréglage nommé, sans erreur s'il n'existe déjà
    plus."""
    cfg = load_config()
    _ensure_lasers(cfg)
    key = "presets_" + category
    presets = cfg.get(key, {})
    if name in presets:
        del presets[name]
        cfg[key] = presets
        _mirror_data_to_active_laser(cfg)
        save_config(cfg)


# --- Préréglages D'USINE (points de départ, toujours proposés) ----------
# Fournis avec l'atelier pour les modes de CALIBRATION, pour ne pas partir
# d'une page blanche. Ce sont des dicts {champ: valeur} dont les CLÉS
# correspondent aux `_last_fields` du panneau (index pour un combo, bool
# pour une case, nombre pour un champ). Non supprimables ; l'utilisateur
# peut en charger un, l'ajuster, puis le sauvegarder sous un autre nom
# (préréglage utilisateur, qui masque l'usine s'il porte le même nom).
_FACTORY_PRESETS = {
    "defocus_calib": {
        "Recherche du foyer (fin)": {
            "zstart": 0.0, "zstep": 0.5, "nmarks": 16, "length": 15.0,
            "rowgap": 6.0, "power": 300.0, "power_end": 300.0, "feed": 1000.0,
            "labels": True, "power_labels": True},
        "Divergence (large + rampe)": {
            "zstart": 0.0, "zstep": 2.0, "nmarks": 20, "length": 15.0,
            "rowgap": 8.0, "power": 250.0, "power_end": 800.0, "feed": 1000.0,
            "labels": True, "power_labels": True},
        "Balayage complet (0-45mm)": {
            "zstart": 0.0, "zstep": 3.0, "nmarks": 16, "length": 12.0,
            "rowgap": 9.0, "power": 300.0, "power_end": 1000.0, "feed": 1200.0,
            "labels": True, "power_labels": True},
    },
    "powerramp": {
        "Gravure MDF (puissance/vitesse)": {
            "length": 100.0, "nlines": 6, "gap": 8.0, "feed_min": 300.0, "feed_max": 1500.0,
            "power_min": 0.0, "power_max": 1000.0, "steps": 15, "zramp": False, "z_end": 14.0,
            "labels": True},
        "Marquage léger (rapide)": {
            "length": 100.0, "nlines": 6, "gap": 8.0, "feed_min": 1000.0, "feed_max": 6000.0,
            "power_min": 0.0, "power_max": 600.0, "steps": 15, "zramp": False, "z_end": 14.0,
            "labels": True},
        "Découpe fine (lent)": {
            "length": 100.0, "nlines": 5, "gap": 8.0, "feed_min": 100.0, "feed_max": 600.0,
            "power_min": 400.0, "power_max": 1000.0, "steps": 12, "zramp": False, "z_end": 14.0,
            "labels": True},
        "Défocus/largeur (rampe Z)": {
            "length": 120.0, "nlines": 5, "gap": 10.0, "feed_min": 300.0, "feed_max": 900.0,
            "power_min": 200.0, "power_max": 1000.0, "steps": 15, "zramp": True, "z_end": 40.0,
            "labels": True},
    },
    "offset_test": {
        "Croix standard (10 mm)": {
            "half": 10.0, "surface_z": 0.0, "mill_tool": 2, "rpm": 18000.0,
            "mill_feed": 600.0, "depth": 0.4, "zfocus": 8.0, "power": 300.0, "laser_feed": 1000.0},
        "Grande croix (20 mm)": {
            "half": 20.0, "surface_z": 0.0, "mill_tool": 2, "rpm": 18000.0,
            "mill_feed": 600.0, "depth": 0.4, "zfocus": 8.0, "power": 300.0, "laser_feed": 1000.0},
    },
    "photo": {
        # Chaque recette est ancrée sur une MESURE, jamais sur un essai
        # heureux. `mode` porte la CLÉ du tramage (cf. _TRAMAGES) et non son
        # rang : réorganiser la liste ne peut plus retourner une recette sur
        # un autre tramage, en silence.
        #
        # LA RÈGLE QUI LES GOUVERNE TOUTES : « largeur du point » pilote le
        # DÉFOCUS. Une recette CALIBRÉE doit donc se poser sur le défocus où
        # les tons du matériau ont été jugés, sinon la courbe ne s'applique
        # plus -- et l'erreur va comme le CARRÉ du rapport des diamètres.
        #   Hêtre : 10 tons à défocus 15,00 mm, F2000       -> point 1,16 mm
        #   MDF   : 34 tons à défocus 12,20 mm, F200 à 2000 -> point 1,00 mm
        # Le pas ne dépasse pas la largeur BRÛLÉE (0,80 mm mesuré aux deux
        # régimes), sans quoi il reste du bois nu entre les lignes.
        #
        # Gamma ramené à 1,0 partout. Le 1,5 hérité corrigeait des « photos
        # saturées » -- mais la recette MDF demandait un point de 0,80 mm,
        # soit un défocus de 8,75 quand son nuancier est mesuré à 12,20 :
        # 1,56x de densité de puissance en trop. Le gamma compensait le
        # mauvais régime au lieu de le corriger. Régime remis d'aplomb, un
        # gamma neutre redevient le bon point de départ -- à confirmer sur
        # une chute, comme toujours ici.
        "Portrait Hêtre -- lignes gravées (le plus sûr)": {
            # Le tramage retenu à l'atelier : le gris est une LARGEUR lue sur
            # les largeurs brûlées mesurées, sans nuancier, sans bois nu.
            # F800 = la plus rapide où le trait enfle encore à fond (au-delà
            # il plafonne : 0,23 mm à F1000, plat dès F1500). Pas 0,30 = le
            # trait le plus épais, donc le contraste MAXIMAL (67 points).
            # 120 mm de large : sous 100 mm le grain se voit plus que le sujet.
            "mode": "enfle", "material": u"Hêtre", "width": 120.0,
            "pitch": 0.30, "line_feed": 800.0, "line_min": 0.10,
            "spot_width": 0.0, "gamma": 1.0, "white": 5.0, "invert": False,
            "power": 1000.0, "dwell_min": 10.0, "dwell_max": 60.0,
            "dot_spacing": 1.27},
        "Portrait Hêtre -- lignes calibrées (nuancier)": {
            # Le régime EXACT des 10 tons Hêtre : défocus 15 (point 1,16) et
            # F2000. Changer l'un des deux sort de la courbe.
            "mode": "lignes", "material": u"Hêtre", "width": 120.0,
            "pitch": 0.80, "spot_width": 1.16, "line_feed": 2000.0,
            "gamma": 1.0, "white": 8.0, "invert": False, "power": 500.0,
            "dwell_min": 10.0, "dwell_max": 60.0, "line_min": 0.10,
            "dot_spacing": 1.27},
        "Similigravure Hêtre -- trame 45° (sans calibration)": {
            # Aucune calibration : le gris est une SURFACE. Mais la promesse
            # « couverture = noirceur » suppose que les lignes se TOUCHENT :
            # à S1000/F800 le trait brûlé mesure 0,30 mm, d'où le pas 0,30.
            # Espacement 1,27 mm -> maille k=3, soit 18 niveaux de gris.
            "mode": "simili", "material": u"Hêtre", "width": 120.0,
            "pitch": 0.30, "line_feed": 800.0, "power": 1000.0,
            "dot_spacing": 1.27, "spot_width": 0.0, "gamma": 1.0,
            "white": 5.0, "invert": False, "dwell_min": 10.0,
            "dwell_max": 60.0, "line_min": 0.10},
        "Artistique Hêtre -- gros points Z (vu de loin)": {
            # Le diamètre porte le gris, via la hauteur du point. Réglages de
            # la planche gravée le 30/07/2026 : pas 0,75, points 0,30 à 0,60.
            "mode": "zdots", "material": u"Hêtre", "width": 120.0,
            "pitch": 0.75, "spot_width": 0.60, "power": 300.0,
            "dwell_min": 10.0, "dwell_max": 60.0, "gamma": 1.0, "white": 5.0,
            "invert": False, "line_feed": 800.0, "line_min": 0.10,
            "dot_spacing": 1.27},
        "Portrait MDF -- lignes calibrées (nuancier)": {
            # Point 1,00 mm = défocus 12,20, le régime des 34 tons MDF
            # (c'était 0,80, donc 8,75 : hors domaine). F600 est dans leur
            # plage mesurée F200-2000.
            "mode": "lignes", "material": "MDF", "width": 80.0,
            "pitch": 0.80, "spot_width": 1.00, "line_feed": 600.0,
            "gamma": 1.0, "white": 8.0, "invert": False, "power": 500.0,
            "dwell_min": 10.0, "dwell_max": 60.0, "line_min": 0.10,
            "dot_spacing": 1.27},
        "Essai rapide -- points fins (brouillon)": {
            # Sans calibration ni matériau : pour dégrossir un cadrage ou un
            # gamma en quelques minutes. Une seule recette de brouillon --
            # les deux d'avant ne différaient que par la taille.
            "mode": "dither", "width": 60.0, "pitch": 0.40,
            "spot_width": 0.30, "line_feed": 1500.0, "gamma": 1.0,
            "white": 8.0, "invert": False, "power": 350.0,
            "dwell_min": 10.0, "dwell_max": 60.0, "line_min": 0.10,
            "dot_spacing": 1.27},
    },
    "kerf": {
        "Petit (10 mm)": {"size": 10.0},
        "Standard (20 mm)": {"size": 20.0},
        "Grand (50 mm)": {"size": 50.0},
    },
    "testgrid": {
        "Gravure MDF (départ)": {
            "mode": 0, "power_min": 200.0, "power_max": 1000.0, "power_steps": 5,
            "feed_min": 500.0, "feed_max": 3000.0, "feed_steps": 5, "cell_size": 10.0,
            "gap": 3.0, "zwork": 8.0, "filltype": 0, "hatch_spacing": 0.2, "hatch_angle": 45.0,
            "proximity": True, "labels": True,
            "border_enabled": True, "border_power": 300.0, "border_feed": 1000.0},
        "Découpe (départ)": {
            "mode": 1, "power_min": 500.0, "power_max": 1000.0, "power_steps": 4,
            "feed_min": 150.0, "feed_max": 700.0, "feed_steps": 5, "cell_size": 10.0,
            "gap": 4.0, "zwork": 8.0, "proximity": True, "labels": True,
            "border_enabled": False,
            "border_power": 300.0, "border_feed": 1000.0},
    },
}


# ----------------------------------------------------------------------------
# PARCOURS DE PREMIERE CALIBRATION
# ----------------------------------------------------------------------------
# Un nouvel utilisateur vient d'installer l'atelier et n'a RIEN reglé. Cette
# liste ordonnée lui dit quoi graver, DANS L'ORDRE, avec le préréglage d'usine
# (★) à charger, et où reporter le résultat. Le Guide rapide l'affiche en
# entier ; chaque panneau de calibration affiche son étape en tête.
# `n` = numéro d'étape (None = complément facultatif, hors numérotation).
# `portee` = "laser" (une fois pour ce laser, jamais à refaire pour un
# nouveau matériau) ou "materiau" (à refaire pour CHAQUE matériau) --
# affichée dans le bandeau (_calibration_banner) pour éviter de croire
# qu'un nouveau matériau oblige à tout reprendre depuis l'étape 1.
# `action` est TOUJOURS une liste (même à 1 élément) : une entrée à
# plusieurs actions distinctes s'affiche en lignes numérotées séparées
# (jamais une énumération aplatie dans une seule phrase/label).
CALIBRATION_JOURNEY = [
    {
        "n": 1,
        "portee": "laser",
        "mode": "Bande de calibration défocus",
        "but": "trouver le foyer et la divergence du faisceau",
        "action": [
            "charge le préréglage ★ « Recherche du foyer (fin) » pour le "
            "point le plus net",
            "charge le préréglage ★ « Divergence (large + rampe) » pour un "
            "point large mais toujours visible (la puissance y monte avec "
            "la hauteur -- sans ça, les traits très défocalisés ne "
            "marquent plus)",
        ],
        "reporter": "« ② Entrer les mesures » ci-dessous (ou Préférences → "
                    "Calibration du point)",
    },
    {
        "n": 2,
        "portee": "laser",
        "mode": "Test des offsets X/Y du laser",
        "but": "aligner l'axe du laser sur celui de la broche",
        "action": ["charge le préréglage ★ « Croix standard (10 mm) »"],
        "reporter": "tool.tbl (LinuxCNC ; à sauter en GRBL ou laser seul)",
    },
    {
        "n": 3,
        "portee": "materiau",
        "mode": "Grille de test puissance / vitesse",
        "but": "caractériser un matériau (largeurs brûlées + noirceurs)",
        # DEUX grilles, pas une : la version au foyer ne suffit pas. Une
        # largeur mesurée au foyer est rejetée par darkness_fluence_curve
        # (filtre z_offset > 0), donc un atelier qui s'arrête à la première
        # se retrouve avec une photo calibrée et un « ton sur mesure » muets,
        # sans que rien ne le signale -- c'est arrivé (83 tons de hêtre, 6
        # points de courbe tous à 100 %).
        # TROIS planches, et l'ordre compte. La version d'avant en demandait
        # deux et faisait juger la noirceur sur la planche en DÉFOCUS -- or
        # celle-ci grave des traits ISOLÉS espacés de 3 mm : on n'y juge pas
        # un aplat, et la largeur qu'on y mesure est celle d'un trait, pas
        # le pas d'un balayage. Un atelier qui suivait le parcours à la
        # lettre finissait donc sans un seul ton exploitable par
        # `darkness_fluence_curve`, sans que rien ne le signale.
        "action": [
            "choisis l'Objectif « Largeurs brûlées — grille au foyer » : ces "
            "largeurs-là calent le remplissage, le bouton « Auto (½ point) » "
            "des Hachures et le tramage « Lignes gravées »",
            "puis l'Objectif « Largeurs brûlées — grille en défocus » : les "
            "mêmes mesures au pied à coulisse, bec remonté -- c'est ce "
            "niveau qui cale un remplissage large",
            "puis l'Objectif « Noirceur — bande en balayage (photo "
            "calibrée) » : là on ne mesure plus, on JUGE la noirceur de "
            "chaque aplat. C'est ce "
            "couple noirceur + défocus + largeur qui, seul, fait marcher la "
            "gravure photo calibrée et le « ton sur mesure »",
        ],
        "reporter": "« ② Entrer les mesures » ci-dessous -- les largeurs dans "
                    "les grilles, les noirceurs dans « Noirceur jugée à "
                    "l'œil » juste en dessous (le mode Nuancier reste "
                    "l'endroit pour tout revoir et corriger)",
    },
    {
        "n": 4,
        "portee": "materiau",
        "mode": "Calibration kerf",
        "but": "mesurer le trait pour tenir les cotes",
        "action": ["charge le préréglage ★ « Standard (20 mm) » (test Carré)"],
        "reporter": "Compensation de kerf des modes de découpe",
    },
    {
        "n": None,
        "portee": "materiau",
        "mode": "Test rampe puissance / vitesse (lignes)",
        "but": "voir en continu où le trait apparaît et où il sature",
        "action": ["charge le préréglage ★ « Gravure MDF (puissance/vitesse) »"],
        "reporter": "« ② Reporter les tons retenus » ci-dessous -- complément de l'étape 3",
    },
]


def calibration_step_for(mode_titre):
    """Étape du parcours de calibration pour ce titre de panneau, ou None."""
    for etape in CALIBRATION_JOURNEY:
        if etape["mode"] == mode_titre:
            return etape
    return None


def calibration_numbered_steps():
    """Les étapes numérotées du parcours (hors compléments), dans l'ordre."""
    return [e for e in CALIBRATION_JOURNEY if e["n"] is not None]


def factory_presets(category):
    """Préréglages d'usine (dict {nom: valeurs}) d'une catégorie, dans
    l'ordre de définition."""
    return _FACTORY_PRESETS.get(category, {})


def all_presets(category):
    """Préréglages d'usine + utilisateur (l'utilisateur masque l'usine
    de même nom). Pour peupler le sélecteur d'un panneau."""
    merged = dict(_FACTORY_PRESETS.get(category, {}))
    merged.update(load_presets(category))
    return merged


# ==========================================================================
# NUANCIER MATÉRIAU (tons de gris MESURÉS)
# ==========================================================================
# La palette de gris calibrée d'un matériau : chaque TON = un réglage
# reproductible (puissance, vitesse, défocus) + ce qu'il produit RÉELLEMENT
# sur ce matériau, mesuré sur chute (noirceur en % à l'oeil : 0 = intact,
# 100 = noir max ; largeur du trait en mm). La noirceur n'est PAS linéaire
# avec la puissance (seuil, saturation, carbonisation) : plutôt que de la
# modéliser, on interpole entre les tons mesurés -- même philosophie « on
# mesure, on ne devine pas » que la calibration du point. Alimenté à la
# main depuis les grilles/rampes de test, via le panneau Nuancier.
#
# Ton = dict {"darkness": 0-100, "power": S, "feed": mm/min,
#             "z_offset": mm au-dessus du foyer (0 = net),
#             "width": largeur mesurée du trait en mm, "label": libre}.
def load_shades(material):
    """Liste des tons du matériau, triée par noirceur croissante."""
    cfg = load_config()
    shades = cfg.get("nuancier", {}).get(material, [])
    return sorted(shades, key=lambda s: s.get("darkness", 0))


def save_shades(material, shades):
    """Remplace la liste des tons du matériau (liste vide = suppression
    du matériau du nuancier)."""
    cfg = load_config()
    _ensure_lasers(cfg)
    nuancier = cfg.get("nuancier", {})
    if shades:
        nuancier[material] = shades
    else:
        nuancier.pop(material, None)
    cfg["nuancier"] = nuancier
    _mirror_data_to_active_laser(cfg)
    save_config(cfg)


def shade_materials():
    """Noms des matériaux présents dans le nuancier, triés."""
    return sorted(load_config().get("nuancier", {}))


# ==========================================================================
# LARGEURS BRÛLÉES MESURÉES (planche de calibration matériau, sections 1-2)
# ==========================================================================
# Table par matériau, alimentée par les mesures de la planche :
#   {"focus":   [{"power": S, "feed": F, "width": mm}, ...],
#    "defocus": [{"power": S, "feed": F, "width": mm, "z_offset": mm}, ...]}
# Constat (MDF, 21 juil. 2026) : au FOYER la largeur dépend surtout de la
# VITESSE (temps de chauffe), très peu de S -- 0,22 mm à F1500-F3000 pour
# TOUTES les puissances, 0,34 mm à F400/S1000, 0,16 mm à F6000. Le point
# optique réel est donc plus fin que la calibration (mesurée à basse
# vitesse, élargie thermiquement). Au DÉFOCUS, la brûlure ne remplit le
# point optique qu'à forte puissance (1,09 mm mesuré à S1000 pour 1,18
# optique ; 0,50 mm à S200 : seuls les bords chauds marquent).

# La section 2 mesure la brûlure à PLUSIEURS niveaux de défocus (mm
# au-dessus du foyer) : un remplissage gravé à un défocus quelconque
# interpole la largeur brûlée entre ces niveaux (burn_width_defocus_scaled),
# au lieu d'extrapoler depuis un seul point. Couvre du remplissage fin
# (~15) au très défocalisé (~50). Partagé par la planche, le dialogue de
# saisie et l'interpolation.
# Niveaux de défocus de la planche de calibration (section 2). DEUX niveaux
# suffisent : sur cette plage la largeur brûlée varie quasi linéairement avec
# le défocus (cône du point) -- une droite définie par 2 points. Hors [15, 36]
# le modèle extrapole optiquement. (On a retiré le 3e niveau, 50 mm : une
# brûlure économisée sans perte réelle.)
DEFOCUS_LEVELS_MM = (15.0, 36.0)


# Tolérance de rangement d'un défocus mesuré sur un niveau standard.
#
# Elle valait 5 mm, à une époque où seuls deux niveaux existaient et où
# toute mesure était censée venir de la Planche 2. Trop large dès que le
# niveau devient libre : un défocus 40 délibérément gravé et mesuré était
# rangé en 36, en silence, et allait polluer une grille où il n'avait rien
# à faire (c'est arrivé -- la mesure S716/F600 à 40 mm de la rampe du
# 30/07/2026 était relue comme une mesure à 36).
#
# 2 mm absorbent ce pour quoi le rangement existe -- l'imprécision d'une
# mesure ou d'un héritage (15,34 -> 15) -- sans jamais pouvoir confondre
# deux graduations de la rampe Z, espacées de 5 mm.
SNAP_DEFOCUS_TOLERANCE_MM = 2.0


def _snap_defocus_level(z):
    """Ramène un z_offset mesuré au niveau standard le plus proche
    (DEFOCUS_LEVELS_MM) s'il en est à moins de SNAP_DEFOCUS_TOLERANCE_MM --
    absorbe l'imprécision de mesure (ex. 15,34 -> 15) et aligne les données
    sur les colonnes de la grille de saisie. Laisse tel quel un z
    volontairement hors niveaux."""
    z = float(z or 0.0)
    if not DEFOCUS_LEVELS_MM:
        return z
    proche = min(DEFOCUS_LEVELS_MM, key=lambda lv: abs(lv - z))
    return (float(proche) if abs(proche - z) <= SNAP_DEFOCUS_TOLERANCE_MM
            else z)


def niveaux_defocus_mesures(material=None):
    """Niveaux de défocus réellement mesurés pour ce matériau, triés.

    La grille de saisie ② s'y accorde, au lieu des deux constantes
    historiques : une planche gravée à un défocus choisi doit avoir une
    grille où être saisie, sinon la mesure n'a nulle part où aller."""
    mat = _burn_width_material(material)
    if not mat:
        return []
    return sorted({round(float(p.get("z_offset", 0) or 0), 3)
                   for p in (load_burn_widths(mat).get("defocus") or [])
                   if float(p.get("z_offset", 0) or 0) > 0})


def _niveaux_exploitables(levels):
    """Parmi des niveaux {z: [points]}, ceux qui peuvent ANCRER
    l'interpolation : au moins deux puissances distinctes.

    Un niveau réduit à une seule puissance ne dit rien de la variation en
    S, et `_bilinear_burn` y renvoie donc la même largeur pour toutes les
    puissances -- ce qui APLATIT le modèle sur toute la plage qu'il borne.
    Mesuré sur le hêtre : les quatre points isolés relevés à la rampe Z
    (défocus 30, 40, 55, 60, une puissance chacun) faisaient tomber la
    largeur prédite à S1000/F200 de 2,26 à 1,50 mm à défocus 30 et de 3,80
    à 3,00 à défocus 55 ; deux pas de hachure (1,50 et 1,70 mm) n'avaient
    du coup plus AUCUN réglage mesuré capable de les couvrir.

    Ces mêmes points ont pourtant confirmé le modèle : au point exact
    mesuré, il annonçait 1,61 / 2,08 / 3,29 / 4,10 mm pour 1,50 / 2,00 /
    3,00 / 4,00 mesurés, soit +2 à +10 %. Ils ne sont donc pas faux, ils
    sont INCOMPLETS -- une mesure ne devient un niveau qu'à partir de deux
    puissances. Mesurer une deuxième puissance au même défocus suffit à
    faire compter le niveau pleinement.

    Repli : si AUCUN niveau n'est exploitable, on garde tout -- un modèle
    approximatif vaut mieux que pas de modèle."""
    riches = {z: pts for z, pts in levels.items()
              if len({round(float(p["power"]), 3) for p in pts}) >= 2}
    return riches or levels


def load_burn_widths(material):
    """Table des largeurs brûlées du matériau ({"focus": [...],
    "defocus": [...]}), ou {} si aucune mesure. Les niveaux de défocus mesurés
    sont ramenés au niveau standard le plus proche (cf. _snap_defocus_level) --
    migration transparente des anciennes mesures (ex. 15,34 -> 15)."""
    data = load_config().get("burn_widths", {}).get(material, {})
    dfc = data.get("defocus")
    if dfc:
        data = dict(data)
        data["defocus"] = [dict(p, z_offset=_snap_defocus_level(p.get("z_offset", 0.0)))
                           for p in dfc]
    return data


def save_burn_widths(material, data):
    """Remplace la table du matériau (données vides = suppression)."""
    cfg = load_config()
    _ensure_lasers(cfg)
    table = cfg.get("burn_widths", {})
    if data and (data.get("focus") or data.get("defocus")):
        table[material] = data
    else:
        table.pop(material, None)
    cfg["burn_widths"] = table
    _mirror_data_to_active_laser(cfg)
    save_config(cfg)


def burn_width_materials():
    """Matériaux ayant une table de largeurs brûlées, triés."""
    return sorted(load_config().get("burn_widths", {}))


def _burn_width_material(material):
    """Résout le matériau : explicite, ou l'unique matériau mesuré."""
    if material:
        return material
    mats = burn_width_materials()
    return mats[0] if len(mats) == 1 else None


def _bilinear_burn(pts, power, feed, key="width"):
    """Valeur `key` (largeur brûlée par défaut, ou noirceur du nuancier)
    interpolée BILINÉAIREMENT sur un nuage de points {power, feed, key} :
    S linéaire, F logarithmique (c'est le temps de chauffe qui pilote),
    bornée aux mesures. Dégénère proprement si un seul S ou un seul F
    mesuré (l'axe non couvert retombe sur la valeur mesurée). None si
    `pts` est vide.

    Le repli « plus proche voisin » sur les cases NON mesurées compare les
    deux axes dans la même géométrie que l'interpolation elle-même : S
    linéaire et F logarithmique, chacun rapporté à son étendue mesurée. Il
    comparait auparavant le couple `(|ΔS|, |ΔF|)` en LEXICOGRAPHIQUE, ce
    qui rend la puissance infiniment prioritaire sur la vitesse : un ton
    isolé au bout de l'axe des vitesses répondait alors pour TOUTE sa
    colonne de puissance. Sur le nuancier Hêtre au foyer (14 tons, 44 % de
    trous) le seul S1000 mesuré l'était à F6000 → `darkness_at` rendait
    **42 % à toutes les vitesses**, de F400 à F6000, et S1000 ressortait
    plus CLAIR que S800. Démenti à l'établi le 30/07/2026 : le carré plein
    S1000/F800 au foyer au pas 0,26 est sorti carbonisé, là où l'atelier
    annonçait 42 %. Sur les tables de largeurs (grilles quasi pleines : 1
    trou sur Hêtre, 0 sur MDF) la normalisation ne change aucune valeur."""
    if not pts:
        return None
    svals = sorted({float(p["power"]) for p in pts})
    fvals = sorted({float(p["feed"]) for p in pts})
    grid = {(float(p["power"]), float(p["feed"])): float(p[key])
            for p in pts}

    def _bracket(vals, x):
        x = min(max(x, vals[0]), vals[-1])
        for a, b in zip(vals, vals[1:]):
            if a <= x <= b:
                return a, b, x
        return vals[-1], vals[-1], x

    def _logf(f):
        return math.log(max(float(f), 1e-6))

    # Étendues mesurées, pour que les deux axes pèsent pareil dans le repli.
    etendue_s = (svals[-1] - svals[0]) or 1.0
    etendue_f = (_logf(fvals[-1]) - _logf(fvals[0])) or 1.0

    def _g(sv, fv):
        w = grid.get((sv, fv))
        if w is None:      # grille incomplète : plus proche voisin normalisé
            def _distance2(p):
                ds = (float(p["power"]) - sv) / etendue_s
                df = (_logf(p["feed"]) - _logf(fv)) / etendue_f
                return ds * ds + df * df
            w = float(min(pts, key=_distance2)[key])
        return w

    s1, s2, sx = _bracket(svals, float(power))
    f1, f2, fx = _bracket(fvals, float(feed))
    ts = 0.0 if s2 == s1 else (sx - s1) / (s2 - s1)
    tf = 0.0 if f2 == f1 else ((math.log(fx) - math.log(f1))
                               / (math.log(f2) - math.log(f1)))
    w1 = _g(s1, f1) * (1 - ts) + _g(s2, f1) * ts
    w2 = _g(s1, f2) * (1 - ts) + _g(s2, f2) * ts
    return w1 * (1 - tf) + w2 * tf


def burn_width_at(power, feed, material=None):
    """Largeur brûlée (mm) d'un trait au FOYER pour (S, F), interpolée
    bilinéairement sur la grille mesurée (bornée aux mesures). None si aucune
    table."""
    mat = _burn_width_material(material)
    if not mat:
        return None
    return _bilinear_burn(load_burn_widths(mat).get("focus") or [], power, feed)


def burn_width_defocus_at(power, material=None):
    """Largeur brûlée (mm) au DÉFOCUS standard du remplissage, interpolée
    LINÉAIREMENT en S sur les mesures (bornée). None si aucune table."""
    mat = _burn_width_material(material)
    if not mat:
        return None
    pts = sorted((load_burn_widths(mat).get("defocus") or []),
                 key=lambda p: float(p["power"]))
    if not pts:
        return None
    p = min(max(float(power), float(pts[0]["power"])),
            float(pts[-1]["power"]))
    for a, b in zip(pts, pts[1:]):
        pa, pb = float(a["power"]), float(b["power"])
        if pa <= p <= pb:
            t = 0.0 if pb == pa else (p - pa) / (pb - pa)
            return float(a["width"]) * (1 - t) + float(b["width"]) * t
    return float(pts[-1]["width"])


def burn_width_defocus_scaled(power, feed, defocus, material=None):
    """Largeur brûlée (mm) attendue au défocus `defocus` pour (S, F), INTERPOLÉE
    entre les niveaux de défocus mesurés (section 2 de la planche, cf.
    DEFOCUS_LEVELS_MM) :

    - à chaque niveau mesuré, la largeur est interpolée BILINÉAIREMENT en (S, F)
      -- comme burn_width_at au foyer (S linéaire, F logarithmique). Tant que la
      planche ne mesure qu'un feed au défocus (F fixe), le résultat ne dépend pas
      encore du feed ; il en dépendra dès qu'une planche multi-feed sera saisie ;
    - entre deux niveaux encadrants, interpolation linéaire en défocus ;
    - SOUS le premier niveau mesuré (cas du remplissage, quelques dixièmes
      de mm), interpolation entre la largeur MESURÉE AU FOYER (section 1 de
      la planche) et ce premier niveau -- au foyer la brûlure dépend du
      temps de chauffe, pas de l'optique, et elle est mesurée en direct ;
    - au-dessus du dernier niveau mesuré (ou sans mesure au foyer),
      extrapolation PROPORTIONNELLE au diamètre optique du point (modèle
      conique) depuis le niveau le plus proche.

    Constat planche : la brûlure réelle est plus étroite que le point
    optique (0,50 mm à S200 contre 1,18 mm optique) -- c'est elle qui
    décide si deux hachures voisines se rejoignent et du retrait du
    remplissage. None si aucune mesure (l'appelant retombe sur le modèle
    optique pur)."""
    mat = _burn_width_material(material)
    if not mat:
        return None
    table = load_burn_widths(mat)
    pts = table.get("defocus") or []
    if not pts:
        return None
    # Regroupe les mesures par niveau de défocus (z_offset), puis ne garde
    # que les niveaux capables d'ANCRER l'interpolation (cf.
    # _niveaux_exploitables : un niveau à une seule puissance aplatirait
    # toute la plage qu'il borne).
    levels = {}
    for p in pts:
        z = round(float(p.get("z_offset", 0.0) or 0.0), 3)
        if z > 0 and p.get("width"):
            levels.setdefault(z, []).append(p)
    levels = _niveaux_exploitables(levels)
    zs = sorted(levels)
    if not zs:
        return None

    def _w_at(z):
        """Largeur au niveau z pour (S, F), interpolée bilinéairement (S, F)."""
        return _bilinear_burn(levels[z], power, feed)

    ha = calibrated_half_angle()

    # Dans la plage mesurée : interpolation linéaire entre les deux niveaux
    # encadrants (exacte quand le défocus tombe sur un niveau).
    if zs[0] <= defocus <= zs[-1]:
        for za, zb in zip(zs, zs[1:]):
            if za <= defocus <= zb:
                t = 0.0 if zb == za else (defocus - za) / (zb - za)
                return _w_at(za) * (1 - t) + _w_at(zb) * t
        return _w_at(zs[0])
    # SOUS le premier niveau mesuré : c'est le cas normal du remplissage
    # (un pas de 0,26 mm ne demande que 0,10 mm de défocus). Là, la
    # brûlure n'est PAS régie par l'optique mais par le temps de chauffe
    # -- et elle est justement mesurée en direct au foyer (section 1 de la
    # planche). On interpole donc entre cette mesure et le premier niveau
    # de défocus, au lieu de faire redescendre le cône optique jusqu'à
    # z=0 : sur hêtre à S200/F1800 ce cône annonçait 0,21 mm là où la
    # planche mesure 0,10 mm (x2,1), d'où des remplissages rayés que
    # l'atelier croyait pleins.
    if defocus < zs[0]:
        w_foyer = _bilinear_burn(table.get("focus") or [], power, feed)
        if w_foyer is not None:
            t = max(0.0, min(1.0, defocus / zs[0]))
            return w_foyer * (1 - t) + _w_at(zs[0]) * t
    # Hors plage (ou un seul niveau) : extrapolation optique depuis le
    # niveau le plus proche.
    z0 = zs[0] if defocus < zs[0] else zs[-1]
    w0 = _w_at(z0)
    if not ha or ha <= 1e-9 or z0 <= 0:
        return w0
    spot0 = spot_diameter_at_defocus(z0, SPOT_FOCUS_MM, ha)
    if spot0 <= 0:
        return w0
    return w0 * spot_diameter_at_defocus(defocus, SPOT_FOCUS_MM, ha) / spot0


def burn_width_focus_max(material=None):
    """La plus GRANDE largeur brûlée mesurée au foyer (mm) -- l'enveloppe
    pour un retrait garanti quand S/F ne sont pas encore connus. None si
    aucune table."""
    mat = _burn_width_material(material)
    if not mat:
        return None
    pts = load_burn_widths(mat).get("focus") or []
    return max(float(p["width"]) for p in pts) if pts else None


def reglage_couvrant_le_pas(spacing, material=None, defocus=0.0):
    """Le réglage MESURÉ le plus RAPIDE dont la brûlure couvre un pas de
    hachure de `spacing` mm AU DÉFOCUS DE TRAVAIL -- la vraie réponse à un
    remplissage rayé. Quand le trait brûlé est plus étroit que le pas,
    l'atelier sait resserrer les hachures, mais cela rallonge le job
    d'autant ; graver un trait assez LARGE pour que deux passes voisines se
    rejoignent est presque toujours meilleur (plus rapide ET plus noir, la
    largeur venant d'une puissance plus forte).

    Le défocus compte : c'est l'espacement demandé qui le fixe (un pas de
    0,90 mm fait remonter le bec de 13 mm), et un trait qui ne fait que
    0,30 mm au foyer en fait 1,0 à ce défocus-là. On ne propose donc que
    des couples (S, F) réellement mesurés au niveau de défocus le PLUS
    PROCHE du défocus de travail -- section 1 de la planche près du foyer,
    section 2 au-delà -- puis on les évalue avec le même interpolateur que
    le verdict, pour que suggestion et verdict ne puissent pas se
    contredire.

    Renvoie {"power", "feed", "width"}, ou None si aucune mesure du
    matériau ne couvre ce pas -- il faut alors resserrer les hachures, ou
    mesurer d'autres réglages avec la planche de calibration."""
    mat = _burn_width_material(material)
    if not mat:
        return None
    table = load_burn_widths(mat)
    niveaux = sorted({round(float(p.get("z_offset", 0.0) or 0.0), 3)
                      for p in (table.get("defocus") or [])
                      if float(p.get("z_offset", 0.0) or 0.0) > 0})
    d = float(defocus or 0.0)
    pres_du_foyer = not niveaux or abs(d) <= min(abs(d - z) for z in niveaux)
    source = (table.get("focus") if pres_du_foyer else table.get("defocus")) or []
    couvrants = []
    for s, f in sorted({(float(p["power"]), float(p["feed"])) for p in source}):
        w = burn_width_defocus_scaled(s, f, d, mat)
        if w is not None and w >= spacing - 1e-9:
            couvrants.append((s, f, w))
    if not couvrants:
        return None
    # Le plus rapide d'abord (job le plus court) ; à vitesse égale, la
    # puissance la plus faible (moins de chaleur déposée hors du trait).
    s, f, w = max(couvrants, key=lambda t: (t[1], -t[0]))
    return {"power": s, "feed": f, "width": w}


def espacement_pour_reglage(power, feed, material=None, borne_haute=None):
    """L'INVERSE de reglage_couvrant_le_pas : là on part d'un pas voulu
    pour trouver un réglage qui le couvre ; ici on part d'un réglage déjà
    choisi (typiquement un ton du nuancier -- puissance et vitesse fixées)
    pour en déduire le plus GRAND pas de hachure qu'il couvre encore sans
    laisser de bande de bois nu -- l'espacement qui rend le remplissage
    plein sans le deviner à la main.

    Pourquoi une bissection et pas une simple inversion de la formule
    optique : le pas fixe le défocus via le cône optique du point
    (defocus_for_fill_spacing), mais la largeur RÉELLEMENT brûlée à ce
    défocus (burn_width_defocus_scaled) grossit plus lentement que ce
    cône -- c'est exactement l'écart que ces mesures corrigent. Partir de
    la largeur mesurée du ton et l'utiliser directement comme pas, ou
    inverser le cône optique pour retrouver le défocus exact du ton,
    donnent tous deux un pas TROP GÉNÉREUX dans la majorité des réglages
    mesurés (vérifié : 29 tons mesurés sur 41 sous-couvrent avec ces deux
    raccourcis, jusqu'à -0,11 mm) -- la seule façon fiable de le savoir
    est de rejouer le VRAI calcul (defocus_for_fill_spacing puis
    burn_width_defocus_scaled) et de chercher où il s'équilibre.

    Cherche par bissection la racine de f(pas) = largeur_brûlée(pas) -
    pas : positive près de zéro (au foyer la largeur mesurée est non
    nulle), et déjà mesurée négative au-delà pour la plupart des réglages
    -- sinon la fonction couvre encore à `borne_haute` (ou par défaut 3x
    la largeur au foyer), qui est alors renvoyée directement. None si
    aucune mesure du matériau ne permet de calculer une largeur (le pas
    voulu par l'appelant reste alors inchangé -- rien à proposer)."""
    ha = calibrated_half_angle()

    def _f(pas):
        d = defocus_for_fill_spacing(pas, SPOT_FOCUS_MM, ha)
        if d is None:
            return None
        burn = burn_width_defocus_scaled(power, feed, d, material)
        return None if burn is None else burn - pas

    haut = borne_haute
    if haut is None:
        foyer = burn_width_at(power, feed, material)
        if not foyer:
            return None
        # Garde-fou seulement pour la borne PAR DÉFAUT (une borne_haute
        # explicite de l'appelant, même très serrée, doit être respectée
        # telle quelle -- sinon un pas voulu délibérément fin serait
        # silencieusement élargi jusqu'au point au foyer).
        haut = max(foyer * 3.0, SPOT_FOCUS_MM)
    bas = 1e-3
    f_bas, f_haut = _f(bas), _f(haut)
    if f_bas is None or f_haut is None or f_bas < 0:
        return None
    if f_haut >= 0:
        return haut
    for _ in range(40):
        milieu = (bas + haut) / 2.0
        f_milieu = _f(milieu)
        if f_milieu is None:
            return bas
        if f_milieu >= 0:
            bas = milieu
        else:
            haut = milieu
    return bas


# Au-delà de ce rapport, le panneau de Gravure remplie signale que le
# remplissage coûte nettement plus que le noir mesuré le plus économe.
# Ce n'est PAS un seuil de carbonisation : rien ici ne prédit la brûlure.
# C'est un seuil de GASPILLAGE -- à puissance égale, le rapport d'énergie
# et le rapport de durée sont le même nombre (les deux valent 1/(pas x F)),
# donc doubler l'énergie double aussi le temps de gravure. Les mesures de
# l'atelier ne permettent pas mieux : sur MDF, des tons jugés 97 % tiennent
# à 4x le plus économe sans rien signaler, alors que sur Hêtre 2,8x a
# carbonisé -- le seuil de dommage dépend du matériau, pas ce rapport-ci.
SEUIL_ENERGIE_REMPLISSAGE = 2.0


def energie_surfacique(power, feed, spacing):
    """Énergie déposée par mm² d'aplat : `S / (pas x vitesse)`.

    INDICE, pas des joules -- `S` n'a pas d'unité physique (0..S_MAX). Seuls
    les RAPPORTS entre deux réglages du même laser ont un sens. C'est la
    même grandeur que la fluence surfacique utilisée par les tramages
    calibrés : ce qui gouverne l'énergie reçue par le bois n'est pas la
    largeur du trait mais de combien on AVANCE entre deux passes. None si
    un terme est nul."""
    if not spacing or not feed:
        return None
    return float(power) / (float(spacing) * float(feed))


def remplissage_noir_le_plus_econome(material, noirceur_min=95.0):
    """Parmi les tons MESURÉS jugés noirs (>= `noirceur_min` %), celui qui
    remplit un aplat avec le moins d'énergie par mm² -- donc aussi, à
    puissance égale, le plus rapide.

    Les deux côtés de la comparaison sont calculés de la MÊME façon : le
    pas retenu pour chaque ton est celui que `espacement_pour_reglage` lui
    donne, c'est-à-dire exactement le remplissage qu'on obtient en cliquant
    ce ton dans « Nuancier matériau ». Sans ça la comparaison n'aurait pas
    de sens -- la largeur stockée sur un ton est tantôt une largeur brûlée
    au pied à coulisse, tantôt le PAS d'une bande de calibration en
    balayage, et diviser par l'une puis par l'autre compare deux grandeurs
    différentes.

    Renvoie {"power", "feed", "spacing", "energie", "darkness", "z_offset"}
    ou None si le matériau n'a aucun ton noir dont le pas soit calculable.

    Coûteux (une bissection par candidat, ~12 ms) : à appeler une fois par
    matériau, pas dans un rafraîchissement d'aperçu."""
    meilleur = None
    for ton in load_shades(material):
        d = ton.get("darkness")
        s = float(ton.get("power", 0) or 0)
        f = float(ton.get("feed", 0) or 0)
        if d is None or float(d) < noirceur_min or s <= 0 or f <= 0:
            continue
        pas = espacement_pour_reglage(s, f, material,
                                      borne_haute=ton.get("width") or None)
        if not pas:
            continue
        e = energie_surfacique(s, f, pas)
        if e is None:
            continue
        if meilleur is None or e < meilleur["energie"]:
            meilleur = {"power": s, "feed": f, "spacing": pas, "energie": e,
                        "darkness": float(d),
                        "z_offset": float(ton.get("z_offset", 0) or 0)}
    return meilleur


def shade_for_darkness(material, target_pct):
    """Le ton mesuré dont la noirceur est LA PLUS PROCHE de target_pct
    (0-100), ou None si le matériau n'a aucun ton. Choix du plus proche
    plutôt qu'une interpolation : interpoler la puissance entre deux tons
    de vitesses différentes n'aurait pas de sens physique -- on reste sur
    des réglages réellement testés."""
    shades = load_shades(material)
    if not shades:
        return None
    return min(shades, key=lambda s: abs(s.get("darkness", 0) - target_pct))


def darkness_at(material, power, feed, z_offset=0.0):
    """Noirceur MESURÉE (0..100) attendue pour (S, F) au défocus `z_offset`,
    d'après le nuancier du matériau : les tons sont regroupés par niveau de
    défocus mesuré, on retient le niveau LE PLUS PROCHE du défocus demandé,
    puis interpolation bilinéaire en (S linéaire, F logarithmique), bornée
    aux mesures -- même mécanique que les largeurs brûlées (_bilinear_burn).
    Sert de teinte à l'aperçu photo : le modèle théorique de fluence
    surestime beaucoup la noirceur des tons clairs (5 % mesuré là où il
    prédit ~55 % sur MDF S400 F2000). None si le matériau n'a aucun ton
    exploitable (l'appelant retombe sur le modèle théorique)."""
    pts = [s for s in load_shades(material)
           if float(s.get("power", 0) or 0) > 0
           and float(s.get("feed", 0) or 0) > 0
           and s.get("darkness") is not None]
    if not pts:
        return None
    niveaux = {}
    for s in pts:
        z = round(float(s.get("z_offset", 0.0) or 0.0), 3)
        niveaux.setdefault(z, []).append(s)
    z_proche = min(niveaux, key=lambda z: abs(z - float(z_offset or 0.0)))
    d = _bilinear_burn(niveaux[z_proche], power, feed, key="darkness")
    return None if d is None else max(0.0, min(100.0, d))


def shade_feed_range(material, z_offset=0.0):
    """(vitesse_min, vitesse_max) réellement MESURÉES sur le matériau, au
    niveau de défocus le plus proche -- le même niveau que celui retenu par
    `darkness_at`. None si aucun ton exploitable.

    Sert à savoir si une teinte rendue par `darkness_at` est une mesure ou
    un bornage : hors de cette plage, `darkness_at` renvoie la valeur du
    bord sans le signaler, et deux régimes très différents ressortent
    identiques. Repéré le 29/07/2026 -- les micro-traits d'une trame de
    points tournent à F200-1200 alors que le nuancier Hêtre est mesuré de
    F650 à F2000 : tous les points d'un aperçu sortaient à 22 %."""
    pts = [s for s in load_shades(material)
           if float(s.get("power", 0) or 0) > 0
           and float(s.get("feed", 0) or 0) > 0
           and s.get("darkness") is not None]
    if not pts:
        return None
    niveaux = {}
    for s in pts:
        z = round(float(s.get("z_offset", 0.0) or 0.0), 3)
        niveaux.setdefault(z, []).append(s)
    z_proche = min(niveaux, key=lambda z: abs(z - float(z_offset or 0.0)))
    feeds = [float(s["feed"]) for s in niveaux[z_proche]]
    return min(feeds), max(feeds)


def shade_summary(shade):
    """Résumé court d'un ton pour un sélecteur : « 45% -- S600 F800
    déf 2.0 (0.80mm) »."""
    parts = "{:.0f}% -- S{:.0f} F{:.0f}".format(
        shade.get("darkness", 0), shade.get("power", 0), shade.get("feed", 0))
    if shade.get("z_offset", 0):
        parts += " déf {:.1f}".format(shade["z_offset"])
    if shade.get("width", 0):
        parts += " ({:.2f}mm)".format(shade["width"])
    if shade.get("label"):
        parts += " " + shade["label"]
    return parts


# --------------------------------------------------------------------------
# RÉGLAGES SÉLECTIONNABLES : nuancier + grille de largeurs, classés
# --------------------------------------------------------------------------
# Deux tables mesurent le même laser sur le même matériau, sans se recouvrir :
#   - le NUANCIER porte un jugement (noirceur 0-100 % à l'oeil) sur des
#     réglages retenus ; peu d'entrées ont une largeur (7 sur 83 en hêtre) ;
#   - la GRILLE DE LARGEURS mesure au pied à coulisse la largeur brûlée de
#     chaque croisement (S, F) à chaque niveau de défocus, sans noirceur.
# Les deux servent à choisir un réglage avant de graver, mais seul le
# nuancier était proposé dans les panneaux. On les EXPOSE ENSEMBLE plutôt
# que de recopier la grille dans le nuancier : la copie obligerait à
# inventer une noirceur (elles sont presque toutes noires), ce qui
# fausserait darkness_fluence_curve -- donc la photo calibrée et le « ton
# sur mesure » -- et allongerait de moitié une liste déjà difficile à
# parcourir. Lire les deux à la volée garde chaque table dans son rôle et
# rend la synchronisation automatique : ajouter ou retirer une mesure se
# voit aussitôt, sans code de recopie qui pourrait dériver.

# Bandes de classement. Bornes choisies sur les mesures réelles de
# l'atelier, pas rondes par principe : 0,30 mm est la largeur au foyer du
# hêtre à S1000/F800 (le trait « net » de référence), 1 mm la largeur
# obtenue vers 20 mm de défocus, au-delà de laquelle on est clairement en
# remplissage.
_BANDES_NOIRCEUR = ((25.0, "Clair (0-25 %)"), (60.0, "Moyen (25-60 %)"),
                    (90.0, "Foncé (60-90 %)"), (101.0, "Noir (90-100 %)"))
_BANDES_LARGEUR = ((0.30, "Trait fin (moins de 0,30 mm)"),
                   (1.0, "Trait moyen (0,30 à 1 mm)"),
                   (1e9, "Trait large (1 mm et plus)"))

CRITERES_CLASSEMENT = (
    ("noirceur", "Noirceur"),
    ("largeur", "Largeur de trait"),
    ("defocus", "Défocus"),
)


def _cle_reglage(power, feed, z_offset):
    """Identité d'un réglage : (S, F, défocus ramené au niveau standard).
    Sert à reconnaître qu'un point de la grille et un ton du nuancier
    décrivent la MÊME gravure."""
    return (round(float(power or 0.0), 1),
            round(float(feed or 0.0), 1),
            round(_snap_defocus_level(z_offset or 0.0), 1))


def reglages_disponibles(material):
    """Tous les réglages applicables pour ce matériau, tons du nuancier ET
    points mesurés de la grille de largeurs, en une seule liste.

    Chaque entrée garde les clés d'un ton (power, feed, z_offset, width,
    darkness, label) -- les appelants qui appliquent un ton n'ont donc rien
    à changer -- plus `origine` ("nuancier" ou "grille"). `darkness` vaut
    None pour un point de grille : sa noirceur n'a pas été jugée, et
    afficher 0 ou 100 serait une mesure inventée.

    TOUS les tons du nuancier sont conservés, y compris deux tons de même
    (S, F, défocus) : un même réglage peut avoir été jugé deux fois (le
    hêtre en compte 5 paires), c'est à l'utilisateur d'arbitrer dans le
    Nuancier, pas à cette fonction d'en perdre un en silence. Seul un point
    de GRILLE est écarté quand un ton décrit déjà le même réglage -- et il
    lui cède au passage sa largeur mesurée si le ton n'en avait pas."""
    tons = [dict(s, origine="nuancier") for s in load_shades(material)]
    cles_tons = {_cle_reglage(t.get("power"), t.get("feed"), t.get("z_offset"))
                 for t in tons}

    largeurs = {}
    points = []
    bw = load_burn_widths(material) or {}
    for p in (bw.get("focus") or []):
        points.append((p, 0.0))
    for p in (bw.get("defocus") or []):
        points.append((p, _snap_defocus_level(p.get("z_offset", 0.0))))
    for p, z in points:
        cle = _cle_reglage(p.get("power"), p.get("feed"), z)
        largeur = float(p.get("width") or 0.0)
        if largeur:
            largeurs.setdefault(cle, largeur)
        if cle in cles_tons:
            continue
        cles_tons.add(cle)
        tons.append({"power": float(p.get("power") or 0.0),
                     "feed": float(p.get("feed") or 0.0),
                     "z_offset": z, "width": largeur, "darkness": None,
                     "label": "", "origine": "grille"})

    # Un ton sans largeur en récupère une si la grille a mesuré le même
    # réglage : mesure déjà faite, aucune raison de la laisser inutilisée.
    for t in tons:
        if t.get("origine") == "nuancier" and not t.get("width"):
            l = largeurs.get(_cle_reglage(t.get("power"), t.get("feed"),
                                          t.get("z_offset")))
            if l:
                t["width"] = l
    return tons


def _bande(valeur, bandes, titre_absent):
    """(rang, titre) de la bande contenant `valeur` ; le groupe « non
    mesuré » est rangé en dernier (rang très grand) plutôt qu'en tête : ce
    sont les entrées dont on ne sait rien sur le critère demandé."""
    if not valeur:
        return (len(bandes), titre_absent)
    for i, (borne, titre) in enumerate(bandes):
        if valeur < borne:
            return (i, titre)
    return (len(bandes) - 1, bandes[-1][1])


def grouper_reglages(reglages, critere="noirceur"):
    """Groupe et trie des réglages selon `critere` ("noirceur", "largeur"
    ou "defocus"), et renvoie [(titre_du_groupe, [réglage, ...]), ...] dans
    l'ordre d'affichage. Le classement change de critère parce qu'on ne
    cherche pas toujours la même chose : une nuance pour un marquage, une
    largeur de trait pour un remplissage, un niveau de défocus pour
    retrouver une gravure déjà faite."""
    groupes = {}
    for r in reglages:
        if critere == "largeur":
            rang, titre = _bande(r.get("width"), _BANDES_LARGEUR,
                                 "Largeur non mesurée")
            tri = r.get("width") or 0.0
        elif critere == "defocus":
            # Ramené au niveau standard : un ton saisi à 15,34 mm et un point
            # de grille à 15,0 décrivent le même étage de la planche. Sans ce
            # calage ils formaient deux groupes distincts affichés tous les
            # deux « Défocus 15 mm ».
            z = _snap_defocus_level(float(r.get("z_offset") or 0.0))
            rang = z
            titre = "Au foyer (trait net)" if not z else "Défocus {:.0f} mm".format(z)
            tri = r.get("width") or 0.0
        else:
            rang, titre = _bande(r.get("darkness"), _BANDES_NOIRCEUR,
                                 "Noirceur non jugée")
            tri = r.get("darkness") or 0.0
        groupes.setdefault((rang, titre), []).append((tri, r))

    sortie = []
    for (_, titre), entrees in sorted(groupes.items()):
        entrees.sort(key=lambda x: (x[0], x[1].get("power") or 0.0))
        sortie.append((titre, [r for _, r in entrees]))
    return sortie


def resume_reglage(r, critere="noirceur"):
    """Libellé court d'un réglage dans un sélecteur, la valeur du critère
    de classement EN TÊTE : c'est elle qu'on parcourt des yeux quand on
    cherche « la largeur qu'il me faut » ou « la nuance qu'il me faut ».
    Une valeur non mesurée est affichée « -- » et jamais remplacée par un
    zéro, qui se lirait comme une mesure."""
    d, l = r.get("darkness"), r.get("width")
    txt_d = "-- %" if d is None else "{:.0f} %".format(d)
    txt_l = "-- mm" if not l else "{:.2f} mm".format(l)
    reglage = "S{:.0f} F{:.0f}".format(r.get("power") or 0, r.get("feed") or 0)
    if r.get("z_offset"):
        reglage += " déf {:.0f}".format(r["z_offset"])
    if critere == "largeur":
        tete, reste = txt_l, "{} · {}".format(reglage, txt_d)
    elif critere == "defocus":
        tete, reste = reglage, "{} · {}".format(txt_d, txt_l)
    else:
        tete, reste = txt_d, "{} · {}".format(reglage, txt_l)
    resume = "{} — {}".format(tete, reste)
    if r.get("label"):
        resume += " " + r["label"]
    return resume


def width_for_darkness(material, target_pct):
    """Largeur de trait BRÛLÉE mesurée pour viser une noirceur (%), par
    interpolation linéaire entre les tons, bornée aux extrêmes mesurés.
    Renvoie None si le matériau n'a pas au moins 2 tons exploitables.

    C'est le pendant indispensable de `fluence_for_darkness` : la fluence
    d'un ton vaut P/(largeur·vitesse), où la largeur est celle du trait
    RÉELLEMENT brûlé, mesurée au pied à coulisse. Elle varie fortement avec
    la puissance -- de 0,40 mm sur les tons clairs à 1,00 mm sur les noirs,
    pour un point optique de 1,16 mm : à faible puissance, seul le coeur du
    faisceau dépasse le seuil de brûlure.

    Réinverser la fluence avec autre chose que CETTE largeur casse
    l'identité qui fonde la courbe. Avec elle, S = fluence·largeur·vitesse
    redonne exactement P·vitesse/v, c'est-à-dire l'énergie par millimètre
    du ton qui a produit cette teinte -- vérifié sur les 6 tons du hêtre,
    à 2 % près. En utilisant le PAS de balayage à la place (v1.89.0), une
    cible à 10 % réclamait S230 au lieu de S120 : plus du double d'énergie,
    et la mire sortait noire sur toute sa longueur."""
    return interp_width_points(darkness_width_points(material), target_pct)


def darkness_width_points(material):
    """[(noirceur, largeur mesurée), ...] trié, mêmes tons exploitables que
    `darkness_fluence_curve`. À HISSER hors des boucles de pixels : lire la
    config pour chaque point d'une photo la rendrait inutilisable."""
    pts = [(float(s["darkness"]), float(s["width"]))
           for s in load_shades(material)
           if (s.get("z_offset", 0) or 0) > 0 and (s.get("width", 0) or 0) > 0
           and (s.get("feed", 0) or 0) > 0 and (s.get("power", 0) or 0) > 0]
    pts.sort(key=lambda p: p[0])
    return pts if len(pts) >= 2 else []


def interp_width_points(pts, target_pct):
    """Largeur interpolée dans `pts` (cf. darkness_width_points), bornée aux
    extrêmes mesurés -- pas d'extrapolation. None si moins de 2 points."""
    if not pts:
        return None
    t = min(max(float(target_pct), pts[0][0]), pts[-1][0])
    for (d0, w0), (d1, w1) in zip(pts, pts[1:]):
        if d0 <= t <= d1:
            if d1 - d0 < 1e-9:
                return (w0 + w1) / 2.0
            return w0 + (w1 - w0) * (t - d0) / (d1 - d0)
    return pts[-1][1]


def darkness_fluence_curve(material):
    """Courbe noirceur (%) -> fluence P/(d·v), interpolable, construite sur
    les tons MESURÉS du matériau. Seuls les tons en DÉFOCUS (z_offset > 0,
    largeur et vitesse connues) sont utilisés : un trait fin au foyer n'est
    pas comparable à l'œil avec un trait large (régime différent), il
    fausserait la courbe. La noirceur saturant avec l'énergie (au-delà du
    seuil de carbonisation, plus d'énergie ne noircit plus beaucoup), les
    inversions de mesure sont lissées par une régression isotone (PAVA :
    les voisins en violation sont moyennés) pour garantir une courbe
    croissante. Renvoie [(noirceur, fluence), ...] trié (>= 2 points), ou
    [] si le matériau n'a pas assez de tons exploitables."""
    pts = []
    for s in load_shades(material):
        if (s.get("z_offset", 0) > 0 and s.get("width", 0) > 0
                and s.get("feed", 0) > 0 and s.get("power", 0) > 0):
            pts.append((float(s["darkness"]),
                        line_fluence(s["power"], s["feed"], s["width"])))
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2:
        return []
    # Régression isotone (pool adjacent violators) sur la fluence.
    blocks = [[d, f, 1] for d, f in pts]   # [somme noirceur, somme fluence, n]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][1] / blocks[i][2] > blocks[i + 1][1] / blocks[i + 1][2]:
            blocks[i][0] += blocks[i + 1][0]
            blocks[i][1] += blocks[i + 1][1]
            blocks[i][2] += blocks[i + 1][2]
            del blocks[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1
    # Réétale la fluence lissée sur les noirceurs d'origine.
    smoothed = []
    k = 0
    for b in blocks:
        for _ in range(b[2]):
            smoothed.append((pts[k][0], b[1] / b[2]))
            k += 1
    return smoothed


def _pas_surfacique(pitch, line_width):
    """Distance qui gouverne l'énergie reçue PAR UNITÉ DE SURFACE en
    balayage : min(pas, largeur du trait).

    La courbe du nuancier est calibrée sur des traits ISOLÉS (fluence
    = P/(largeur·vitesse) d'un trait seul, mesuré espacé de 3 mm). En
    balayage, les lignes se recouvrent : avec un trait de 0,80 mm posé
    tous les 0,30 mm, chaque point du bois est repassé 2,7 fois. Convertir
    la fluence en S avec la LARGEUR délivre donc 2,7 fois trop d'énergie
    et tout sature en noir -- c'est ce qu'a montré la mire des tramages du
    29/07/2026, bande 3 entièrement noire alors que le G-code demandait
    bien un dégradé de S345 à S740.

    Ce qui compte n'est pas la largeur d'un trait mais de combien on
    AVANCE entre deux lignes : l'énergie surfacique vaut P/(pas·vitesse).
    D'où S = fluence · pas · vitesse, où la largeur disparaît d'elle-même.

    Le min() traite le cas inverse : si le pas dépasse la largeur, il reste
    du bois nu entre les lignes, la surface n'est plus couverte en continu
    et c'est alors la largeur du trait qui gouverne ce qui brûle."""
    return min(max(float(pitch), 1e-9), max(float(line_width), 1e-9))


def fluence_for_darkness(material, target_pct):
    """Fluence interpolée pour viser une noirceur (%) sur le matériau, à
    partir de la courbe mesurée (interpolation LINÉAIRE entre les tons,
    bornée aux extrêmes mesurés -- pas d'extrapolation). Renvoie
    (fluence, noirceur réellement visée après bornage) ou None."""
    curve = darkness_fluence_curve(material)
    if not curve:
        return None
    t = min(max(float(target_pct), curve[0][0]), curve[-1][0])
    for (d0, f0), (d1, f1) in zip(curve, curve[1:]):
        if d0 <= t <= d1:
            if d1 - d0 < 1e-9:
                return (f0 + f1) / 2.0, t
            r = (t - d0) / (d1 - d0)
            return f0 + (f1 - f0) * r, t
    return curve[-1][1], t


def feed_for_custom_shade(material, darkness_pct, width, power):
    """Ton SUR MESURE : pour une largeur de trait et une noirceur voulues,
    à puissance donnée, renvoie (vitesse, fluence, noirceur bornée) --
    inversion de fluence = P/(d·v). La largeur pilote le défocus (via la
    calibration du point) ; la vitesse pilote la noirceur. None si le
    nuancier n'a pas assez de tons en défocus, ou entrées invalides."""
    if width <= 0 or power <= 0:
        return None
    res = fluence_for_darkness(material, darkness_pct)
    if res is None:
        return None
    fluence, clamped = res
    if fluence <= 0:
        return None
    return power / (fluence * width), fluence, clamped


def estimate_job_time_seconds(gcode_text, rapid_feed=None, accel=None):
    """Estime le temps total du job en secondes, en reparcourant le
    G-code déjà généré : G1 selon la distance/avance programmée, G0 à
    une vitesse rapide SUPPOSÉE (RAPID_FEED_MM_MIN par défaut), G4 pris
    en compte.

    Tient compte des ACCÉLÉRATIONS (profil trapézoïdal, `accel` =
    ACCEL_MM_S2 par défaut, réglable dans les Préférences) : les
    mouvements consécutifs quasi colinéaires (< ~30 deg de changement de
    direction), de même type (G0/G1) et de même avance, sont fusionnés
    en une COURSE continue (le planificateur de LinuxCNC les enchaîne
    sans s'arrêter) ; chaque course paie un départ et un arrêt. Sans ça,
    l'estimation supposait la vitesse de croisière atteinte instantanément
    -- très optimiste sur un remplissage fait de milliers de traits
    courts, où la machine passe son temps à accélérer/freiner."""
    if rapid_feed is None:
        rapid_feed = RAPID_FEED_MM_MIN
    if accel is None:
        accel = ACCEL_MM_S2

    def run_time(dist_mm, feed_mm_min):
        # Profil trapézoïdal départ/arrêt : d >= v2/a -> plateau atteint,
        # sinon profil triangulaire (jamais à pleine vitesse).
        v = feed_mm_min / 60.0
        if v <= 0:
            return 0.0
        if accel <= 0:
            return dist_mm / v
        if dist_mm >= v * v / accel:
            return dist_mm / v + v / accel
        return 2.0 * math.sqrt(dist_mm / accel)

    total_seconds = 0.0
    last_x = last_y = last_z = 0.0
    current_feed = 1000.0
    puissance = 0.0
    # Course en cours : (is_g0, feed, S, distance cumulée, direction unitaire)
    run_is_g0 = None
    run_feed = None
    run_s = None
    run_dist = 0.0
    run_dir = None

    def flush_run():
        nonlocal total_seconds, run_is_g0, run_dist, run_dir, run_feed, run_s
        if run_dist > 0:
            total_seconds += run_time(run_dist, rapid_feed if run_is_g0 else run_feed)
        run_is_g0, run_feed, run_s, run_dist, run_dir = None, None, None, 0.0, None

    for line in gcode_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("("):
            continue
        if line.startswith("G4 "):
            for token in line.split():
                if token.startswith("P"):
                    try:
                        total_seconds += float(token[1:])
                    except ValueError:
                        pass
            continue
        is_g0 = line.startswith("G0")
        is_g1 = line.startswith("G1")
        if not (is_g0 or is_g1):
            continue
        x, y, z = last_x, last_y, last_z
        for token in line.split()[1:]:
            if not token:
                continue
            try:
                val = float(token[1:])
            except ValueError:
                continue
            if token[0] == 'X':
                x = val
            elif token[0] == 'Y':
                y = val
            elif token[0] == 'Z':
                z = val
            elif token[0] == 'F':
                current_feed = val
            elif token[0] == 'S':
                puissance = val
        dx, dy, dz = x - last_x, y - last_y, z - last_z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        last_x, last_y, last_z = x, y, z
        if dist < 1e-9:
            continue
        direction = (dx / dist, dy / dist, dz / dist)
        feed = rapid_feed if is_g0 else current_feed
        # Les lignes `M67 E0 Q<v>` ne sont PAS lues ici, et c'est VOULU :
        # M67 est synchronisé avec le mouvement, il ne rompt donc pas la
        # course. Le résultat est juste dans les deux modes -- 1h31 en M67
        # contre 3h41 en S direct sur le même portrait -- mais il l'est par
        # OMISSION. Quiconque « améliorerait » cet estimateur en lui faisant
        # lire les M67 comme des changements de puissance casserait
        # l'estimation du mode rapide sans s'en apercevoir. Ne pas le faire.
        #
        # Un CHANGEMENT DE PUISSANCE rompt la course. Mesuré le 30/07/2026
        # sur un portrait en lignes gravées : 172 614 blocs G1 de 0,30 mm de
        # médiane, gravés à F800, annoncés 1h30 et partis pour 4 h. Soit
        # ~76 ms par bloc là où 0,30 mm à F800 en demande 22 -- et 55 ms est
        # exactement le temps d'un déplacement de 0,30 mm avec ARRÊT AUX DEUX
        # BOUTS à 400 mm/s². La machine ne relie donc pas deux segments dont
        # le S diffère, même parfaitement colinéaires. Les supposer enchaînés
        # rendait l'estimation optimiste d'un facteur 3 sur tout tramage qui
        # module la puissance par pixel -- exactement les jobs les plus longs,
        # ceux où l'estimation sert à décider si on lance.
        cont = (run_dir is not None and run_is_g0 == is_g0
                and (is_g0 or (run_feed == feed and run_s == puissance))
                and (run_dir[0] * direction[0] + run_dir[1] * direction[1]
                     + run_dir[2] * direction[2]) > 0.87)
        if not cont:
            flush_run()
            run_is_g0, run_feed, run_s = is_g0, feed, puissance
        run_dist += dist
        run_dir = direction
    flush_run()
    return total_seconds


def format_duration(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return "{}h{:02d}m{:02d}s".format(h, m, s)
    return "{}m{:02d}s".format(m, s)


def generate_gcode_flat_multipass(edges, power, feed, thickness, n_passes,
                                   finish_feed=None, z_start=None,
                                   pre_gcode="", post_gcode="",
                                   power_end=None, kerf_width=0.0,
                                   use_hole_first=False, use_proximity=False,
                                   tab_count=0, tab_length=4.0, tab_height=1.0,
                                   lead_in_mm=0.0,
                                   frame_only=False, quiet=False, body_only=False, min_safe_z=None):
    """z_start=None : calcule automatiquement depuis l'épaisseur -- Z=0 =
    le bec touche la surface du matériau (zéro au papier), Z POSITIF =
    bec au-dessus de la surface. Donner z_start explicitement pour forcer
    une valeur (ex: calage manuel différent).

    power_end : si donné, la puissance varie linéairement de `power`
    (1ère passe) à `power_end` (dernière passe) au lieu de rester fixe.
    kerf_width : largeur de trait mesurée (mm) ; si > 0, chaque chaîne
    est décalée de kerf_width/2 (extérieur agrandi, trous rétrécis) pour
    que la pièce finie sorte à la bonne cote.
    use_hole_first : découpe les trous/îlots avant leur contour englobant
    (chaque chaîne termine TOUTES ses passes avant de passer à la
    suivante, pour que "avant" ait un sens physique réel).
    use_proximity : réordonne par plus proche voisin (heuristique) pour
    réduire les déplacements à vide.

    tab_count/tab_length/tab_height : ATTACHES (tabs). tab_count > 0
    laisse, sur chaque chaîne FERMÉE, tab_count ponts de tab_length mm
    non coupés (faisceau éteint en les traversant) sur les passes qui
    attaqueraient les derniers tab_height mm d'épaisseur -- la pièce
    reste solidaire de la planche par ces ponts (à couper au cutter
    ensuite) au lieu de tomber/bouger avant la fin du job. Chaînes
    ouvertes ou trop courtes : attaches ignorées (avertissement).

    lead_in_mm : AMORCE de découpe. > 0 = le faisceau s'allume à cette
    distance du contour, DANS LA CHUTE (extérieur d'un contour de pièce,
    intérieur d'un trou), puis rejoint le contour en coupant -- la verrue
    du point d'allumage (marquage renforcé au départ) reste hors du bord
    fini. Chaînes fermées uniquement.
    frame_only : ne génère QUE le rectangle englobant (laser éteint), en
    réutilisant le même calcul de Z de sécurité que le job réel -- pour
    un fichier de VÉRIFICATION DE CADRAGE SÉPARÉ du job (à lancer seul
    sur la machine avant de découper pour de vrai), plutôt qu'un aperçu
    embarqué au début du même fichier (facile à lancer par erreur en
    pensant vérifier alors que le laser va réellement découper juste
    après).

    quiet : coupe les avertissements Report View -- pour un appel
    d'APERÇU EN DIRECT (durée estimée recalculée à chaque changement de
    champ dans le panneau) qui ne doit pas spammer la vue Rapport du
    même avertissement à chaque frappe.

    body_only : pour une OPÉRATION au sein d'un job combiné (cf.
    generate_gcode_combined) -- omet l'en-tête G21/G90/G94/M5 initial
    (émis une seule fois pour tout le job combiné), considère le laser
    DÉJÀ ARMÉ (pas de M3 ici, un seul armement pour tout le job combiné
    au lieu d'un par opération) et omet le désarmement/M2 final (émis
    une seule fois à la toute fin du job combiné).

    min_safe_z : plancher imposé à la hauteur de retrait -- cf.
    generate_gcode_curved pour l'explication complète (transit sûr entre
    opérations d'un job combiné)."""
    if not edges:
        return None

    chains = chain_edges(edges)
    if not chains:
        return None

    # --- Imbrication (trous/îlots) : calculée AVANT le kerf, sur la
    # géométrie nominale (le décalage ne doit pas fausser la classification) ---
    depths = compute_nesting_depths(chains)

    # --- Compensation de kerf : extérieur agrandi, trous/îlots rétrécis ---
    if kerf_width > 0:
        chains = [offset_chain_kerf(c, kerf_width / 2.0, is_hole=(depths[i] % 2 == 1))
                  for i, c in enumerate(chains)]

    # --- Ordre de découpe : trous avant leur contour englobant, et/ou
    # réordonnement par proximité pour réduire les déplacements à vide ---
    if use_hole_first or use_proximity:
        order = order_chains_for_cutting(chains, depths, use_hole_first, use_proximity)
        chains = [chains[i] for i in order]
        depths = [depths[i] for i in order]

    if not quiet and thickness > MAX_THICKNESS_WARNING_MM:
        FreeCAD.Console.PrintWarning(
            "Épaisseur {:.1f}mm : au-delà de la plage testée par le constructeur (2-8mm) et "
            "des retours utilisateurs habituels pour ce laser (~8-10mm en plusieurs passes). "
            "Résultat incertain, à valider sur une chute avant la pièce réelle.\n".format(thickness))

    if z_start is None:
        z_start = nozzle_height_for_thickness(thickness)

    n_passes = max(1, int(n_passes))
    z_step = thickness / float(n_passes)
    if not quiet and z_step > RECOMMENDED_MAX_STEP_MM:
        FreeCAD.Console.PrintWarning(
            "Pas Z par passe = {:.2f}mm (au-delà du repère habituel ~{:.1f}mm). "
            "Envisager plus de passes pour un pas plus progressif -- un pas trop grand "
            "peut faire que les parois du trait déjà coupé gênent le faisceau sur "
            "les passes suivantes.\n".format(z_step, RECOMMENDED_MAX_STEP_MM))

    # Calcule le Z de chaque passe MAINTENANT (avant d'écrire le G-code)
    # pour pouvoir appliquer la butée de sécurité et avertir si elle est
    # utilisée.
    pass_heights = []
    clamped_passes = []
    for pass_idx in range(n_passes):
        raw = z_start - pass_idx * z_step
        used = max(SAFE_MIN_NOZZLE_HEIGHT_MM, raw)
        pass_heights.append(used)
        if used != raw:
            clamped_passes.append((pass_idx + 1, raw, used))

    if not quiet and clamped_passes:
        FreeCAD.Console.PrintWarning(
            "Butée de sécurité ({:.1f}mm) appliquée sur {} passe(s) -- le calcul "
            "'idéal' aurait demandé un dégagement plus faible (voire négatif), "
            "focus non optimal sur ces passes profondes mais bec garanti au-dessus "
            "de la surface. Détail : {}\n".format(
                SAFE_MIN_NOZZLE_HEIGHT_MM, len(clamped_passes),
                ", ".join("passe {} (voulu {:.2f}mm)".format(p, r) for p, r, u in clamped_passes)))

    z_safe = z_start + TRAVEL_CLEARANCE_MM
    if min_safe_z is not None:
        z_safe = max(z_safe, min_safe_z)

    lines = []
    lines.append("(G-Code Laser - Découpe multi-passes, Z progressif)")
    lines.append("(Chaînes : {} (à partir de {} segments d'origine))".format(len(chains), len(edges)))
    lines.append("(Épaisseur : {:.2f}mm sur {} passe(s), pas = {:.3f}mm/passe)".format(
        thickness, n_passes, z_step))
    lines.append("(Z=0 = bec touche la surface (zéro au papier). Z POSITIF = bec au-dessus.)")
    lines.append("(Hauteur bec 1ère passe (calculée) = {:.4f}mm)".format(z_start))
    if kerf_width > 0:
        lines.append("(Compensation de kerf : {:.3f}mm (décalage {:.3f}mm de chaque côté))".format(
            kerf_width, kerf_width / 2.0))
    if use_hole_first:
        lines.append("(Ordre : trous/îlots avant leur contour englobant)")
    if use_proximity:
        lines.append("(Ordre : optimisé par plus proche voisin)")
    if power_end is not None:
        lines.append("(Puissance : rampe de S{:.0f} (1ère passe) à S{:.0f} (dernière passe))".format(power, power_end))
    if tab_count > 0:
        lines.append("(Attaches : {} x {:.1f}mm par contour ferme, hauteur {:.1f}mm -- ponts a couper au cutter)".format(
            int(tab_count), tab_length, tab_height))
    if lead_in_mm > 0:
        lines.append("(Amorce : allumage a {:.1f}mm du contour, dans la chute)".format(lead_in_mm))
    if clamped_passes:
        lines.append("(ATTENTION : butée de sécurité {:.1f}mm appliquée sur {} passe(s), voir Rapport)".format(
            SAFE_MIN_NOZZLE_HEIGHT_MM, len(clamped_passes)))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        all_pts_flat = [p for c in chains for p in c]
        lines.extend(build_frame_trace(
            min(p.x for p in all_pts_flat), max(p.x for p in all_pts_flat),
            min(p.y for p in all_pts_flat), max(p.y for p in all_pts_flat), z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only
    tab_count = max(0, int(tab_count))
    tab_warned = False

    for ci, chain in enumerate(chains):
        closed = math.hypot(chain[0].x - chain[-1].x, chain[0].y - chain[-1].y) < 1e-6
        is_hole = (depths[ci] % 2 == 1) if ci < len(depths) else False

        lead_pt = None
        if lead_in_mm > 0 and closed:
            lead_pt = _lead_in_point(chain, lead_in_mm, is_hole)

        tab_pieces = None
        if tab_count > 0:
            if closed:
                tab_pieces = split_closed_chain_tabs(chain, tab_count, tab_length)
            if tab_pieces is None and not quiet and not tab_warned:
                FreeCAD.Console.PrintWarning(
                    "Attaches ignorées sur au moins une chaîne (ouverte, ou périmètre "
                    "trop court pour {} attache(s) de {:.1f}mm).\n".format(
                        tab_count, tab_length))
                tab_warned = True

        for pass_idx in range(n_passes):
            z_pass = pass_heights[pass_idx]
            is_last_pass = (pass_idx == n_passes - 1)
            pass_feed = finish_feed if (is_last_pass and finish_feed) else feed
            if power_end is not None and n_passes > 1:
                t = pass_idx / float(n_passes - 1)
                pass_power = power + (power_end - power) * t
            else:
                pass_power = power

            # Chaîne OUVERTE : passes en aller-retour (sens alterné) -- la
            # passe suivante repart de là où la précédente s'est arrêtée,
            # au lieu de retraverser la pièce faisceau allumé pour revenir
            # au début (bug historique : le G1 de reprise coupait tout
            # droit de la fin vers le début du trait).
            path = chain if (closed or pass_idx % 2 == 0) else list(reversed(chain))
            p0 = path[0]
            start_pt = lead_pt if lead_pt is not None else p0

            # Attaches actives sur les passes qui attaqueraient les
            # derniers tab_height mm d'épaisseur.
            tabs_this_pass = (tab_pieces is not None
                              and (pass_idx + 1) * z_step > thickness - tab_height + 1e-9)

            lines.append("(-- Passe {}/{} : Z={:.4f} F={:.0f} S={:.0f} --)".format(
                pass_idx + 1, n_passes, z_pass, pass_feed, pass_power))

            if pass_idx == 0:
                # Arrivée sur cette chaîne : retrait complet nécessaire
                # (on vient d'une autre chaîne, ou d'une position inconnue)
                lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(start_pt.x, start_pt.y, z_safe))
                lines.append("G0 Z{:.4f}".format(z_pass))
            else:
                # Passe suivante de la MÊME chaîne : le kerf est déjà
                # ouvert -- pas besoin de remonter. Avec amorce, retour au
                # point d'allumage (faisceau éteint, à plat dans la chute).
                if lead_pt is not None:
                    lines.append("G0 X{:.4f} Y{:.4f}".format(start_pt.x, start_pt.y))
                lines.append("G0 Z{:.4f}".format(z_pass))

            if not state_armed:
                lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
                state_armed = True
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=pass_power))

            if lead_pt is not None:
                # Amorce : rejoint le contour en coupant depuis la chute.
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    p0.x, p0.y, z_pass, pass_feed))

            if tabs_this_pass:
                for piece, on in tab_pieces:
                    if not on:
                        lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
                    for p in piece[1:]:
                        lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                            p.x, p.y, z_pass, pass_feed))
                    if not on:
                        lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=pass_power))
            else:
                for p in path[1:]:
                    lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(p.x, p.y, z_pass, pass_feed))

            lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))

            if is_last_pass:
                # Dernière passe de cette chaîne : retrait avant de passer
                # à la chaîne suivante (transit potentiellement sur une
                # autre zone, là ce retrait redevient nécessaire).
                lines.append("G0 Z{:.4f}".format(z_safe))

    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    if not body_only:
        lines.append("M2")

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE 3 : DÉCOUPE MULTI-PASSES SUR SURFACE COURBÉE
# ==========================================================================
# Hybride des deux modes précédents : le suivi de relief (sonde 3D/
# interpolation, calage Z natif -> machine) du mode 1 (Marquage courbe),
# combiné à la logique multi-passes/kerf/imbrication du mode 2 (Découpe
# multi-passes à plat). Chaque passe recule le foyer de z_step
# supplémentaires DANS la matière (comme le mode 2), tout en suivant le
# relief natif de la surface à chaque point (comme le mode 1) -- au lieu
# d'une seule hauteur de bec calculée sur une épaisseur nominale (mode 2,
# valable uniquement sur un matériau plat), une même profondeur de coupe
# est appliquée PARTOUT le long de la courbe.
#
# Contrairement au mode 1 (transit qui suit le relief en continu, pensé
# pour de nombreux petits segments de hachures), le transit ici retourne
# à une hauteur de sécurité GLOBALE entre chaque chaîne (comme le mode 2)
# -- plus simple et plus sûr pour un nombre modeste de contours de
# découpe fermés, et cohérent avec l'optimisation par proximité/imbrication
# héritée du mode 2 (qui suppose déjà ce comportement).
def generate_gcode_curved_cut(edges, power, feed, thickness, n_passes, z_focus, marge_survol,
                               reference_shape=None, finish_feed=None, power_end=None,
                               kerf_width=0.0, use_hole_first=False, use_proximity=False,
                               pre_gcode="", post_gcode="", frame_only=False, quiet=False, body_only=False,
                               min_safe_z=None, probe=None, warnings_out=None):
    """z_focus : même rôle que dans generate_gcode_curved -- Z natif du
    document qui met le laser au point (foyer) au niveau le plus bas du
    motif (1ère passe). Les passes suivantes reculent le foyer de
    pass_idx*z_step DANS la matière, en conservant le suivi du relief
    natif à chaque point de chaque chaîne.

    thickness/n_passes/finish_feed/power_end/kerf_width/use_hole_first/
    use_proximity : mêmes rôles et mêmes fonctions que dans
    generate_gcode_flat_multipass (nesting, offset de kerf, ordre de
    découpe).

    reference_shape : objet 3D optionnel pour une sonde EXACTE (sinon
    interpolation sur les points déjà projetés, cf. generate_gcode_curved)
    -- utilisée ici uniquement pour l'avertissement de dégagement du bec
    (le tracé lui-même suit le Z natif déjà porté par les chaînes,
    provenant du motif projeté).

    frame_only/quiet/body_only/min_safe_z : mêmes rôles que sur les
    autres modes (cf. generate_gcode_curved / generate_gcode_flat_multipass).

    probe : cf. generate_gcode_curved -- sonde make_ray_probe(reference_shape)
    à réutiliser entre appels successifs sur le même reference_shape."""
    if not edges:
        return None

    chains = chain_edges(edges)
    if not chains:
        return None

    depths = compute_nesting_depths(chains)

    if kerf_width > 0:
        chains = [offset_chain_kerf(c, kerf_width / 2.0, is_hole=(depths[i] % 2 == 1))
                  for i, c in enumerate(chains)]

    if use_hole_first or use_proximity:
        order = order_chains_for_cutting(chains, depths, use_hole_first, use_proximity)
        chains = [chains[i] for i in order]
        depths = [depths[i] for i in order]

    if not quiet and thickness > MAX_THICKNESS_WARNING_MM:
        FreeCAD.Console.PrintWarning(
            "Épaisseur {:.1f}mm : au-delà de la plage testée par le constructeur (2-8mm) et "
            "des retours utilisateurs habituels pour ce laser (~8-10mm en plusieurs passes). "
            "Résultat incertain, à valider sur une chute avant la pièce réelle.\n".format(thickness))

    n_passes = max(1, int(n_passes))
    z_step = thickness / float(n_passes)
    if not quiet and z_step > RECOMMENDED_MAX_STEP_MM:
        FreeCAD.Console.PrintWarning(
            "Pas Z par passe = {:.2f}mm (au-delà du repère habituel ~{:.1f}mm). "
            "Envisager plus de passes pour un pas plus progressif -- un pas trop grand "
            "peut faire que les parois du trait déjà coupé gênent le faisceau sur "
            "les passes suivantes.\n".format(z_step, RECOMMENDED_MAX_STEP_MM))

    all_pts = [p for c in chains for p in c]
    z_min = min(p.z for p in all_pts)
    z_max = max(p.z for p in all_pts)
    z_offset = z_focus - z_min
    z_safe = z_max + z_offset + marge_survol + 5.0
    if min_safe_z is not None:
        z_safe = max(z_safe, min_safe_z)

    if reference_shape is not None:
        if probe is not None and probe.matches(reference_shape):
            height_probe = probe
        else:
            height_probe = _MeshZProbe(reference_shape)
        probe_kind = "sonde exacte sur l'objet 3D sélectionné"
        nozzle_check_active = True
    else:
        height_probe = _IDWHeight(all_pts)
        probe_kind = "interpolation (aucun objet 3D de référence sélectionné)"
        nozzle_check_active = False

    def to_machine_z(z_native, pass_idx):
        return z_native + z_offset - pass_idx * z_step

    lines = []
    lines.append("(G-Code Laser - Découpe multi-passes sur surface courbée)")
    lines.append("(Chaînes : {} (à partir de {} segments d'origine))".format(len(chains), len(edges)))
    lines.append("(Épaisseur : {:.2f}mm sur {} passe(s), pas = {:.3f}mm/passe, suit le relief : {})".format(
        thickness, n_passes, z_step, probe_kind))
    if kerf_width > 0:
        lines.append("(Compensation de kerf : {:.3f}mm (décalage {:.3f}mm de chaque côté))".format(
            kerf_width, kerf_width / 2.0))
    if use_hole_first:
        lines.append("(Ordre : trous/îlots avant leur contour englobant)")
    if use_proximity:
        lines.append("(Ordre : optimisé par plus proche voisin)")
    if power_end is not None:
        lines.append("(Puissance : rampe de S{:.0f} (1ère passe) à S{:.0f} (dernière passe))".format(power, power_end))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(
            min(p.x for p in all_pts), max(p.x for p in all_pts),
            min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only
    nozzle_cut_warnings = 0
    nozzle_cut_points = []

    for chain in chains:
        closed = math.hypot(chain[0].x - chain[-1].x, chain[0].y - chain[-1].y) < 1e-6

        for pass_idx in range(n_passes):
            is_last_pass = (pass_idx == n_passes - 1)
            pass_feed = finish_feed if (is_last_pass and finish_feed) else feed
            if power_end is not None and n_passes > 1:
                t = pass_idx / float(n_passes - 1)
                pass_power = power + (power_end - power) * t
            else:
                pass_power = power

            # Chaîne OUVERTE : passes en aller-retour (sens alterné) --
            # même correction que la découpe à plat : sans ça, la reprise
            # de passe recoupait tout droit de la fin vers le début du
            # trait, faisceau allumé.
            path = chain if (closed or pass_idx % 2 == 0) else list(reversed(chain))
            p0 = path[0]

            lines.append("(-- Passe {}/{} : F={:.0f} S={:.0f} --)".format(
                pass_idx + 1, n_passes, pass_feed, pass_power))

            z_p0 = to_machine_z(p0.z, pass_idx)
            if pass_idx == 0:
                # Arrivée sur cette chaîne : retrait complet nécessaire
                # (on vient d'une autre chaîne, ou d'une position inconnue).
                lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(p0.x, p0.y, z_safe))
                lines.append("G0 Z{:.4f}".format(z_p0))
            else:
                # Passe suivante de la MÊME chaîne, même X,Y : pas besoin
                # de remonter, juste ajuster le Z directement.
                lines.append("G0 Z{:.4f}".format(z_p0))

            if not state_armed:
                lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
                state_armed = True
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=pass_power))

            last_check_pos = p0
            for p in path[1:]:
                # Contrôlé tous les NOZZLE_CHECK_INTERVAL_MM, pas à chaque
                # point discrétisé -- voir la même optimisation dans
                # generate_gcode_curved.
                if nozzle_check_active and math.hypot(p.x - last_check_pos.x, p.y - last_check_pos.y) >= NOZZLE_CHECK_INTERVAL_MM:
                    # Chaque passe rapproche physiquement le bec de la
                    # surface D'ORIGINE (le foyer recule de pass_idx*z_step
                    # dans la matière) -- le dégagement requis se resserre
                    # d'autant à chaque passe.
                    required = nozzle_clearance_z(p.x, p.y, p.z, height_probe.z_at, 0.0)
                    if required > p.z - pass_idx * z_step + 0.05:
                        nozzle_cut_warnings += 1
                        nozzle_cut_points.append(FreeCAD.Vector(p.x, p.y, p.z))
                    last_check_pos = p
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(
                    p.x, p.y, to_machine_z(p.z, pass_idx), pass_feed))

            lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))

            if is_last_pass:
                # Dernière passe de cette chaîne : retrait avant de passer
                # à la chaîne suivante.
                lines.append("G0 Z{:.4f}".format(z_safe))

    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    if not body_only:
        lines.append("M2")

    if not quiet and reference_shape is not None and height_probe.misses:
        FreeCAD.Console.PrintWarning(
            "{} points de vérification sans intersection avec l'objet de référence "
            "(dernière hauteur connue réutilisée -- normal en bord de zone)\n".format(height_probe.misses))
    if not quiet and nozzle_cut_warnings:
        FreeCAD.Console.PrintWarning(
            "{} points de DÉCOUPE où le bec (cône) serait plus proche de la surface "
            "voisine que ne le permet la profondeur de cette passe -- risque de collision "
            "à vérifier visuellement/physiquement sur ces zones (plus fréquent sur les "
            "dernières passes, le foyer reculant dans la matière).\n".format(nozzle_cut_warnings))
    if warnings_out is not None:
        warnings_out["nozzle_cut_warnings"] = nozzle_cut_warnings
        warnings_out["nozzle_cut_points"] = nozzle_cut_points

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : BANDE DE CALIBRATION DÉFOCUS
# ==========================================================================
def generate_gcode_defocus_calibration(z_start, z_step, n_marks, mark_length, row_gap,
                                       power, feed, power_end=None, draw_labels=True,
                                       draw_power_labels=True,
                                       label_power=None, label_feed=None, label_z=None,
                                       n_bands=1, feed_end=None, band_gap=5.0,
                                       plank_label=None,
                                       pre_gcode="", post_gcode="", frame_only=False, quiet=False,
                                       body_only=False):
    """Grave une rangée de courts traits, chacun à une hauteur de bec
    croissante (z_start, z_start+z_step, ...), à vitesse FIXE. Chaque trait
    est étiqueté à sa gauche par sa hauteur Z en mm entiers (la police
    vectorielle maison ne fait que les chiffres). En mesurant l'épaisseur de
    chaque trait, on lit d'un coup : le foyer (trait le plus fin) et la
    divergence -- de quoi remplir « point au foyer » + « défocus de test » /
    « point au défocus de test » une bonne fois. La hauteur de chaque trait
    est gravée à sa GAUCHE ; avec draw_power_labels, sa puissance (S) est
    aussi gravée à sa DROITE -- indispensable avec une rampe, sinon on ne
    sait pas quelle puissance a donné quel trait. Les étiquettes sont
    gravées à une hauteur fixe (label_z, défaut z_start) pour rester
    lisibles quel que soit le défocus du trait qu'elles désignent. Une
    graduation encore plus à gauche complète ces étiquettes : une amorce +
    son chiffre tous les 10 mm de Z pile (indépendant de z_step), pour situer
    une hauteur précise même entre deux traits.

    power / power_end : puissance du 1er trait, et du dernier. Plus le trait
    est défocalisé, plus la MÊME puissance est étalée sur un gros point,
    donc plus le trait est pâle -- jusqu'à disparaître. Une RAMPE
    (power_end > power) monte progressivement la puissance avec la hauteur
    pour que même les traits très défocalisés marquent, et restent
    mesurables. power_end=None -> puissance constante.

    n_bands / feed_end / band_gap : grave PLUSIEURS bandes côte à côte, une
    par VITESSE (feed pour la 1re, feed_end pour la dernière, interpolé),
    espacées horizontalement de band_gap mm. Chaque bande porte un libellé
    « F<vitesse> » au-dessus. On obtient d'un coup toutes les vitesses (donc
    tous les niveaux de gris/noir) sans relancer un job par vitesse.
    n_bands=1 (ou feed_end=None) -> une seule bande, comportement d'origine.

    plank_label : si fourni (ex. "3"), grave ce texte en gros au-dessus à
    gauche -- identifiant visuel de la planche quand plusieurs calibrations
    finissent sur la même chute (cf. generate_gcode_planche_spot). None (par
    défaut) -> rien de plus, comportement d'origine du panneau autonome
    « Bande de calibration défocus ».

    Le transit entre traits se fait DIRECTEMENT à la hauteur du trait
    suivant (laser éteint, pièce plate) -- pas de remontée au Z de sécurité
    entre chaque trait (inutile à plat, et lente).

    frame_only : ne trace que le rectangle englobant (cadrage séparé).

    body_only : pour une PLANCHE au sein d'un fichier combiné (cf.
    generate_gcode_planches_combinees) -- omet l'en-tête/l'armement/le
    désarmement/M2, même convention que sur les générateurs de mode."""
    if label_power is None:
        label_power = LABEL_POWER
    if label_feed is None:
        label_feed = LABEL_FEED
    n_marks = max(1, int(n_marks))
    n_bands = max(1, int(n_bands))
    def _mark_power(k):
        if power_end is None or n_marks < 2:
            return power
        return power + (power_end - power) * (k / float(n_marks - 1))
    def _band_feed(b):
        # Vitesse de la bande b : de `feed` (1re bande) à `feed_end`
        # (dernière), interpolé. n_bands<2 ou feed_end absent -> `feed`.
        if n_bands < 2 or feed_end is None:
            return feed
        return feed + (feed_end - feed) * (b / float(n_bands - 1))
    if label_z is None:
        label_z = z_start
    label_height = max(2.0, min(row_gap * 0.45, 5.0))

    # --- Géométrie d'UNE bande, en coordonnées locales (x_offset = 0) ---
    # Une bande = une colonne de traits (Y croissant = Z croissant). La
    # hauteur (Z) et la puissance (S) d'une rangée sont IDENTIQUES sur toutes
    # les bandes -> gravées UNE SEULE FOIS (inutile de les répéter). Seule la
    # vitesse (F) change d'une bande à l'autre : gravée au-dessus de chacune.
    multi = n_bands > 1
    local_marks = []                       # (chain, z, power) -- répliqué par bande
    for k in range(n_marks):
        z = z_start + k * z_step
        y = k * row_gap
        local_marks.append(([FreeCAD.Vector(0.0, y, 0.0), FreeCAD.Vector(mark_length, y, 0.0)],
                            z, _mark_power(k)))

    # Étiquettes de rangée (hauteur + puissance), gravées UNE FOIS. 1 bande :
    # hauteur à gauche, puissance à droite (comme avant). >1 bande : les deux
    # à GAUCHE (puissance en colonne extérieure, puis hauteur), sans répétition.
    z_texts = ["{:g}".format(round(z, 2)) for _, z, _ in local_marks]
    s_texts = ["S{:.0f}".format(mp) for _, _, mp in local_marks]
    zw_max = max([text_width(t, label_height) for t in z_texts]) if draw_labels else 0.0
    sw_max = max([text_width(t, label_height) for t in s_texts]) if draw_power_labels else 0.0
    z_col_x = -(zw_max + row_gap * 0.4)
    s_col_x = (z_col_x - (sw_max + row_gap * 0.4)) if multi else (mark_length + row_gap * 0.4)
    row_labels = []
    for k in range(n_marks):
        y = k * row_gap
        if draw_labels:
            row_labels.extend(chain_edges(text_to_edges(
                z_texts[k], z_col_x, y - label_height / 2.0, label_height)))
        if draw_power_labels:
            row_labels.extend(chain_edges(text_to_edges(
                s_texts[k], s_col_x, y - label_height / 2.0, label_height)))

    # Graduation continue de hauteur (Z), en plus des étiquettes par trait
    # ci-dessus : une amorce + son chiffre tous les 10 mm de Z PILE, quel
    # que soit z_step (qui ne tombe pas forcément sur des valeurs rondes) --
    # repère visuel pour situer une hauteur précise (ex. le foyer) même
    # entre deux traits, sans avoir à compter/interpoler les étiquettes.
    if draw_labels and n_marks > 1 and z_step > 0:
        grad_x = min(z_col_x, s_col_x) - row_gap * 0.5
        tick_len = row_gap * 0.3
        z_lo, z_hi = sorted((z_start, z_start + (n_marks - 1) * z_step))
        for cm in range(math.ceil(z_lo / 10.0), math.floor(z_hi / 10.0) + 1):
            z_grad = cm * 10.0
            y_grad = (z_grad - z_start) / z_step * row_gap
            row_labels.append([FreeCAD.Vector(grad_x, y_grad, 0.0),
                               FreeCAD.Vector(grad_x + tick_len, y_grad, 0.0)])
            txt = "{:g}".format(z_grad)
            row_labels.extend(chain_edges(text_to_edges(
                txt, grad_x - text_width(txt, label_height) - row_gap * 0.2,
                y_grad - label_height / 2.0, label_height)))

    # Pas horizontal entre bandes : largeur d'une bande (traits ou libellé de
    # vitesse, au plus large) + band_gap, pour un espace CONSTANT = band_gap.
    feed_label_y = n_marks * row_gap       # libellé de vitesse, au-dessus de la bande
    fw_max = text_width("F{:.0f}".format(max(feed, feed_end or feed)), label_height)
    band_pitch = max(mark_length, fw_max) + band_gap

    # --- Réplication : une bande de traits par vitesse, décalée en X ---
    def _shift(chain, dx):
        return [FreeCAD.Vector(p.x + dx, p.y, p.z) for p in chain]
    marks = []                    # (chain, z, feed, power)
    label_chains = list(row_labels)   # étiquettes de rangée (gravées une fois)
    for b in range(n_bands):
        dx = b * band_pitch
        fb = _band_feed(b)
        for chain, z, mp in local_marks:
            marks.append((_shift(chain, dx), z, fb, mp))
        # Vitesse de la bande, centrée au-dessus.
        ftext = "F{:.0f}".format(fb)
        fx = dx + (mark_length - text_width(ftext, label_height)) / 2.0
        label_chains.extend(chain_edges(text_to_edges(ftext, fx, feed_label_y, label_height)))

    if plank_label:
        # Numéro identifiant la planche (ex. « 3 »), même colonne que les
        # hauteurs Z (gauche), même rangée que le libellé de vitesse.
        label_chains.extend(chain_edges(text_to_edges(
            plank_label, z_col_x, feed_label_y, max(5.0, label_height * 1.5))))

    all_pts = [p for chain, _, _, _ in marks for p in chain] + [p for chain in label_chains for p in chain]
    z_safe = max([z for _, z, _, _ in marks] + [label_z]) + TRAVEL_CLEARANCE_MM

    lines = []
    if not body_only:
        lines.append("(G-Code Laser - Bande de calibration defocus)")
        if power_end is None:
            p_desc = "S{:.0f}".format(power)
        else:
            p_desc = "S{:.0f}->{:.0f} (rampe)".format(power, power_end)
        if n_bands > 1 and feed_end is not None:
            f_desc = "{} bandes F{:.0f}->{:.0f}".format(n_bands, feed, feed_end)
        else:
            f_desc = "F{:.0f}".format(feed)
        lines.append("(Traits : {} de Z={:.2f} a Z={:.2f} par pas de {:.2f}, {} -- {})".format(
            n_marks, z_start, z_start + (n_marks - 1) * z_step, z_step, p_desc, f_desc))
        lines.append("(Mesurer l'epaisseur de chaque trait : le plus fin = foyer)")
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(
            min(p.x for p in all_pts), max(p.x for p in all_pts),
            min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    started = [False]

    def _travel(x, y, target_z):
        # Transit à plat, laser éteint : on va DIRECTEMENT au trait suivant,
        # à sa hauteur -- pas de remontée au Z de sécurité entre chaque
        # trait. Seule la toute 1re approche part du Z de sécurité (le bec
        # peut venir de n'importe où) ; ensuite on enchaîne de hauteur en
        # hauteur sans va-et-vient.
        if not started[0]:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_safe))
            lines.append("G0 Z{:.4f}".format(target_z))
            started[0] = True
        else:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, target_z))

    def _emit(chain, p, f, target_z):
        p0 = chain[0]
        _travel(p0.x, p0.y, target_z)
        lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=p))
        for pt in chain[1:]:
            lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(pt.x, pt.y, target_z, f))
        lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))

    if not body_only:
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    lines.append("(===== Traits de calibration =====)")
    for chain, z, fb, mp in marks:
        _emit(chain, mp, fb, z)
    if label_chains:
        lines.append("(===== Etiquettes (hauteur en mm) =====)")
        for chain in label_chains:
            _emit(chain, label_power, label_feed, label_z)

    if started[0]:
        lines.append("G0 Z{:.4f}".format(z_safe))
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : TEST RAMPE PUISSANCE / VITESSE (LIGNES)
# ==========================================================================
def generate_gcode_power_ramp_lines(line_length, n_lines, feed_min, feed_max,
                                    power_min, power_max, z_work, line_gap,
                                    z_end=None, n_steps=40, draw_labels=True,
                                    label_power=None, label_feed=None,
                                    pre_gcode="", post_gcode="",
                                    frame_only=False, quiet=False):
    """Grave N longues lignes horizontales, une par VITESSE (feed_min ->
    feed_max, une ligne = une vitesse), chacune parcourue avec une
    PUISSANCE qui monte progressivement de power_min (gauche) à power_max
    (droite). On lit d'un coup, à chaque vitesse, à partir de quelle
    puissance le trait commence à marquer et où il sature -- le complément
    CONTINU de la grille de cellules discrètes. La rampe est approchée par
    n_steps petits segments à puissance croissante (un S par segment).

    z_end : si donné et différent de z_work, la HAUTEUR Z monte AUSSI le
    long de chaque ligne, de z_work (gauche = foyer) à z_end (droite) --
    en même temps que la puissance. On teste ainsi, à chaque vitesse,
    l'effet combiné puissance croissante + défocus croissant (le bec
    s'éloigne du foyer). z_end=None (ou = z_work) : hauteur constante au
    foyer (rampe de puissance seule).

    Étiquettes : la vitesse (F) à gauche de chaque ligne, et les bornes de
    puissance (Smin à gauche, Smax à droite) sous la première ligne. Si
    z_ramp, des traits verticaux CONTINUS traversent TOUTES les lignes de
    rampe tous les 5 mm pile de hauteur Z (chiffre au pied de chaque
    trait) : le défocus se lit directement en face de n'importe quelle
    ligne, à l'intersection. Gravées à label_power/label_feed FIXES, au
    foyer (z_work).

    frame_only : ne trace que le rectangle englobant (cadrage séparé)."""
    if label_power is None:
        label_power = LABEL_POWER
    if label_feed is None:
        label_feed = LABEL_FEED
    n_lines = max(1, int(n_lines))
    n_steps = max(2, int(n_steps))
    if line_length <= 0 or n_lines < 1:
        return None
    if z_end is None:
        z_end = z_work
    z_ramp = abs(z_end - z_work) > 1e-9

    lines_geo = []  # (y, feed)
    for i in range(n_lines):
        feed = feed_min if n_lines == 1 else feed_min + (feed_max - feed_min) * i / float(n_lines - 1)
        lines_geo.append((i * line_gap, feed))

    label_h = max(2.0, min(line_gap * 0.5, 6.0))
    label_chains = []  # liste de chaînes (chaque chaîne = liste de Vector)
    if draw_labels:
        for y, feed in lines_geo:
            text = "F{:.0f}".format(feed)
            w = text_width(text, label_h)
            label_chains.extend(chain_edges(
                text_to_edges(text, -(w + line_gap * 0.3), y - label_h / 2.0, label_h)))

        # Règle de graduation de puissance sous la 1re ligne (y=0) :
        # petits traits verticaux à des valeurs de S rondes le long de X,
        # étiquetés en chiffres VERTICAUX (empilés) pour tenir dans
        # l'espacement serré. Les bornes power_min/power_max sont toujours
        # marquées, plus des paliers ronds intermédiaires.
        tick_top = -line_gap * 0.25
        tick_len = label_h * 0.7
        grad_h = label_h * 0.8
        span = power_max - power_min

        tick_powers = [power_min, power_max]
        if span > 0:
            step = nice_axis_step(span)
            p = math.ceil((power_min + 1e-9) / step) * step
            while p < power_max - 1e-9:
                tick_powers.append(p)
                p += step
        # dédoublonnage (tolérance) + tri
        uniq = []
        for p in sorted(tick_powers):
            if not uniq or abs(p - uniq[-1]) > max(span * 0.02, 1e-6):
                uniq.append(p)

        # Position réelle du palier -- la trajectoire de puissance est un
        # ESCALIER (S posé au début de chaque bloc G1, cf. la boucle de
        # gravure plus bas, et tenu constant jusqu'à la fin du bloc), pas
        # une rampe continue : une interpolation linéaire sur toute la
        # longueur (comme avant) place la graduation dans un palier plus
        # FAIBLE que celui réellement gravé à cet endroit -- même défaut
        # que celui déjà corrigé pour la graduation Z ci-dessous, dont on
        # reprend ici le principe (reconstruire les vrais points de
        # rupture plutôt qu'une formule séparée).
        paliers_s = [(0.0, power_min)]
        for k in range(n_steps):
            t = k / float(n_steps - 1)
            paliers_s.append((line_length * (k + 1) / float(n_steps),
                              power_min + (power_max - power_min) * t))

        def _x_pour_power(p_val, _pts=paliers_s):
            if abs(p_val - power_min) < 1e-9:
                return 0.0
            if abs(p_val - power_max) < 1e-9:
                return line_length
            for (x0, _), (_, p1) in zip(_pts, _pts[1:]):
                if p1 >= p_val - 1e-9:
                    return x0
            return line_length

        for p in uniq:
            x_tick = _x_pour_power(p)
            # trait de graduation vertical
            label_chains.append([FreeCAD.Vector(x_tick, tick_top, 0.0),
                                 FreeCAD.Vector(x_tick, tick_top - tick_len, 0.0)])
            # valeur en chiffres empilés sous le trait
            label_chains.extend(chain_edges(text_to_edges_vertical(
                "{:.0f}".format(p), x_tick, tick_top - tick_len - grad_h * 0.4, grad_h)))

        # Graduation de hauteur (Z) : un trait vertical CONTINU tous les
        # 5 mm pile de Z, qui coupe TOUTES les lignes de rampe (pas une
        # simple amorce sous la 1re ligne comme la graduation de
        # puissance ci-dessus) -- on lit le défocus à l'intersection avec
        # n'importe quelle ligne, sans avoir à viser une règle éloignée.
        # Sa position en X est retrouvée sur la VRAIE trajectoire par
        # paliers du G-code (mêmes k/t que la boucle de gravure plus bas),
        # PAS une interpolation linéaire sur toute la longueur : le 1er
        # palier reste au foyer (t=0 en k=0), donc Z ne bouge pas du tout
        # sur le premier line_length/n_steps -- une règle linéaire naïve
        # plaçait la graduation en avance sur la hauteur réellement
        # atteinte à cet endroit.
        if z_ramp:
            points_z = [(0.0, z_work)]
            for k in range(n_steps):
                t = k / float(n_steps - 1)
                points_z.append((line_length * (k + 1) / float(n_steps),
                                 z_work + (z_end - z_work) * t))

            def _x_pour_z(z_val, _pts=points_z):
                if abs(z_val - z_work) < 1e-9:
                    return 0.0
                for (x0, z0), (x1, z1) in zip(_pts, _pts[1:]):
                    lo, hi = sorted((z0, z1))
                    if lo - 1e-9 <= z_val <= hi + 1e-9 and abs(z1 - z0) > 1e-9:
                        return x0 + (x1 - x0) * (z_val - z0) / (z1 - z0)
                return None

            max_digits = max((len(str(int(round(p)))) for p in uniq), default=1)
            z_row_bas = tick_top - tick_len - grad_h * (1.3 * max_digits + 1.0)
            y_haut_rampe = (n_lines - 1) * line_gap
            # Le chiffre gravé est le DÉFOCUS (z - z_work), pas la cote
            # machine, et les graduations tombent sur des défocus RONDS.
            # C'est le défocus que l'atelier demande partout ailleurs
            # (`z_offset` des tons et des largeurs brûlées,
            # `DEFOCUS_LEVELS_MM`, « Défocus des cellules ») ; la hauteur Z
            # absolue n'est saisie nulle part. Graduer tous les 5 mm de
            # HAUTEUR faisait tomber les traits sur les défocus 2, 7, 12,
            # 17 avec un foyer à 8 mm -- et le chiffre gravé « 15 »
            # désignait un défocus de 7. Reporté tel quel dans
            # « + Ajouter ce ton », `_snap_defocus_level` l'aurait rangé au
            # niveau 15 : des largeurs mesurées à 7 mm de défocus mélangées
            # à celles de 15, sans le moindre signe.
            sens = 1.0 if z_end >= z_work else -1.0
            for cm in range(1, int(math.floor(abs(z_end - z_work) / 5.0)) + 1):
                defocus = cm * 5.0
                x_tick = _x_pour_z(z_work + sens * defocus)
                if x_tick is None:
                    continue
                label_chains.append([FreeCAD.Vector(x_tick, y_haut_rampe, 0.0),
                                     FreeCAD.Vector(x_tick, z_row_bas - tick_len, 0.0)])
                label_chains.extend(chain_edges(text_to_edges_vertical(
                    "{:.0f}".format(defocus), x_tick,
                    z_row_bas - tick_len - grad_h * 0.4, grad_h)))

    all_pts = []
    for y, _ in lines_geo:
        all_pts.append(FreeCAD.Vector(0.0, y, 0.0))
        all_pts.append(FreeCAD.Vector(line_length, y, 0.0))
    for ch in label_chains:
        all_pts.extend(ch)
    z_safe = max(z_work, z_end) + TRAVEL_CLEARANCE_MM

    lines = []
    lines.append("(G-Code Laser - Test rampe puissance/vitesse (lignes))")
    lines.append("(Lignes : {} vitesses de F{:.0f} a F{:.0f})".format(
        n_lines, feed_min, feed_max if n_lines > 1 else feed_min))
    lines.append("(Puissance : rampe S{:.0f} (gauche) -> S{:.0f} (droite) sur {:.0f}mm, {} paliers)".format(
        power_min, power_max, line_length, n_steps))
    if z_ramp:
        lines.append("(Hauteur Z : rampe {:.2f}mm (gauche, foyer) -> {:.2f}mm (droite) le long de chaque ligne)".format(
            z_work, z_end))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    # G64 : mode trajectoire CONTINUE (path blending). Sans lui, LinuxCNC
    # peut faire un arrêt net (exact stop) à chaque petit segment de la
    # rampe -- d'où le trait qui avance par à-coups. En G64, les segments
    # colinéaires de la rampe s'enchaînent en un mouvement FLUIDE à vitesse
    # constante, seule la puissance change palier par palier.
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        if all_pts:
            lines.extend(build_frame_trace(
                min(p.x for p in all_pts), max(p.x for p in all_pts),
                min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    current_z = [None]  # None = retracté au Z de sécurité (position inconnue)

    def _travel(x, y, target_z):
        # Transit laser éteint. On ne se relève au Z de sécurité QUE si le
        # Z de destination diffère du Z courant (ex : après une ligne finie
        # en haut avec la rampe Z). Tant qu'on reste au même Z -- typique
        # des étiquettes, toutes au foyer -- on enchaîne à plat sans lever
        # le bec (sinon le laser remontait tout en haut entre CHAQUE petit
        # trait de lettre).
        if current_z[0] is None:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_safe))
            lines.append("G0 Z{:.4f}".format(target_z))
        elif abs(current_z[0] - target_z) > 1e-9:
            lines.append("G0 Z{:.4f}".format(z_safe))
            lines.append("G0 X{:.4f} Y{:.4f}".format(x, y))
            lines.append("G0 Z{:.4f}".format(target_z))
        else:
            lines.append("G0 X{:.4f} Y{:.4f}".format(x, y))
        current_z[0] = target_z

    lines.append("(===== Lignes a rampe de puissance =====)")
    beam_off = CMD_BEAM_OFF.format(sel=SPINDLE_SELECT)
    for y, feed in lines_geo:
        _travel(0.0, y, z_work)
        for k in range(n_steps):
            x1 = line_length * (k + 1) / float(n_steps)
            t = k / float(n_steps - 1)
            power = power_min + (power_max - power_min) * t
            # Puissance (S) sur la MÊME ligne que le mouvement : l'ordre
            # d'exécution RS274 applique S avant le déplacement du bloc,
            # donc la puissance du palier est posée puis le segment tracé
            # -- pas de bloc « S seul » qui pourrait casser l'enchaînement.
            if z_ramp:
                z_k = z_work + (z_end - z_work) * t
                lines.extend(cmd_power_prefix(power))
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f} {}".format(
                    x1, y, z_k, feed, cmd_power_suffix(power)))
            else:
                lines.extend(cmd_power_prefix(power))
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
                    x1, y, feed, cmd_power_suffix(power)))
        lines.append(beam_off)
        if z_ramp:
            current_z[0] = z_end  # la ligne s'est terminée en haut (droite)

    if label_chains:
        lines.append("(===== Etiquettes (vitesses + bornes de puissance) =====)")
        for ch in label_chains:
            # Étiquettes toujours au foyer (z_work) : le 1er transit après
            # les lignes en rampe retracte une seule fois, ensuite tout
            # s'enchaîne à plat.
            _travel(ch[0].x, ch[0].y, z_work)
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=label_power))
            for p in ch[1:]:
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(p.x, p.y, label_feed))
            lines.append(beam_off)

    if current_z[0] is not None:
        lines.append("G0 Z{:.4f}".format(z_safe))
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# STYLES DE TRAIT (tirets / pointillé / vague) -- travail À PLAT
# ==========================================================================
# Au lieu d'un trait continu, une chaîne peut être rendue en TIRETS
# (faisceau pulsé par segments le long du tracé, mouvement continu), en
# POINTILLÉ (vrais points ronds : arrêt + pulse G4 à chaque point -- plus
# lent mais points nets, et en défocus ça donne des gros points doux), ou
# en VAGUE (le Z oscille entre le foyer et un défocus max le long du
# tracé : le trait varie continûment en largeur ET en intensité, effet
# calligraphique). L'amplitude de la vague se calcule avec le modèle de
# défocus calibré (defocus_for_fill_spacing, overlap=1) à partir de la
# largeur max de trait voulue. Utilisé par la Gravure remplie (styles de
# remplissage et de contour).
def _chain_cumlen(chain):
    """Abscisse curviligne cumulée (2D, X/Y) de chaque point de la
    chaîne."""
    cum = [0.0]
    for i in range(1, len(chain)):
        cum.append(cum[-1] + math.hypot(chain[i].x - chain[i - 1].x,
                                        chain[i].y - chain[i - 1].y))
    return cum


def _point_at_s(chain, cum, s):
    """Point interpolé à l'abscisse curviligne s (Z interpolé aussi)."""
    if s <= 0:
        p = chain[0]
    elif s >= cum[-1]:
        p = chain[-1]
    else:
        i = bisect.bisect_right(cum, s)
        p0, p1 = chain[i - 1], chain[i]
        seg = cum[i] - cum[i - 1]
        t = (s - cum[i - 1]) / seg if seg > 0 else 0.0
        return FreeCAD.Vector(p0.x + (p1.x - p0.x) * t,
                              p0.y + (p1.y - p0.y) * t,
                              p0.z + (p1.z - p0.z) * t)
    return FreeCAD.Vector(p.x, p.y, p.z)


def slice_chain(chain, s0, s1, cum=None):
    """Sous-chaîne entre les abscisses curvilignes s0 et s1 (bornes
    interpolées, points intermédiaires d'origine conservés)."""
    if cum is None:
        cum = _chain_cumlen(chain)
    pts = [_point_at_s(chain, cum, s0)]
    for i in range(bisect.bisect_right(cum, s0), bisect.bisect_left(cum, s1)):
        pts.append(chain[i])
    pts.append(_point_at_s(chain, cum, s1))
    out = [pts[0]]
    for p in pts[1:]:
        if (math.hypot(p.x - out[-1].x, p.y - out[-1].y) > 1e-9
                or abs(p.z - out[-1].z) > 1e-9):
            out.append(p)
    if len(out) < 2:
        out = [pts[0], pts[-1]]
    return out


def dash_chain(chain, dash_len, gap_len):
    """Découpe la chaîne en morceaux alternés [(sous-chaîne, faisceau
    allumé), ...] couvrant tout le tracé : tirets de dash_len (allumé)
    séparés d'espaces de gap_len (éteint, parcourus au même feed pour un
    mouvement continu sans à-coups)."""
    cum = _chain_cumlen(chain)
    total = cum[-1]
    if total < 1e-9:
        return []
    pieces = []
    s, on = 0.0, True
    while s < total - 1e-9:
        ln = dash_len if on else gap_len
        e = min(s + ln, total)
        pieces.append((slice_chain(chain, s, e, cum), on))
        s, on = e, not on
    return pieces


def dot_micro_stroke(dot_spacing, dot_dwell_s):
    """Micro-trait remplaçant le G4 d'un point de pointillé : G4 faisceau
    allumé est INTERDIT sur cette machine (la puissance, asservie par la
    vitesse dans le HAL, tombe à 0 à l'arrêt -- cf. gros points photo).
    On grave donc un trait minuscule dont la durée de parcours reproduit
    le temps de pose demandé. Renvoie (longueur du trait, F)."""
    seg = max(0.05, min(0.3 * dot_spacing, 0.2))
    f_dot = max(1.0, seg / max(dot_dwell_s, 1e-3) * 60.0)
    return seg, f_dot


def dot_stroke_dir(dots, i):
    """Direction XY unitaire du micro-trait au point i, le long de la
    chaîne (vers un voisin) ; (1, 0) si dégénéré (point isolé)."""
    nb = dots[i + 1] if i + 1 < len(dots) else (dots[i - 1] if i > 0 else None)
    if nb is None:
        return 1.0, 0.0
    dx, dy = nb.x - dots[i].x, nb.y - dots[i].y
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return 1.0, 0.0
    return dx / n, dy / n


def dot_positions(chain, spacing):
    """Points régulièrement espacés (abscisse curviligne) le long de la
    chaîne, extrémités comprises. Sur une chaîne fermée, le point de
    fin (= point de départ) n'est pas doublé."""
    cum = _chain_cumlen(chain)
    total = cum[-1]
    if total < 1e-9:
        return [chain[0]]
    n = max(1, int(math.floor(total / spacing + 1e-9))) + 1
    pts = [_point_at_s(chain, cum, min(i * spacing, total)) for i in range(n)]
    closed = math.hypot(chain[0].x - chain[-1].x, chain[0].y - chain[-1].y) < 1e-6
    if closed and len(pts) > 1 and math.hypot(
            pts[-1].x - pts[0].x, pts[-1].y - pts[0].y) < spacing * 0.5:
        pts.pop()
    return pts


def chaine_fermee(chain, tol=1e-6):
    """La chaîne revient-elle sur son point de départ ? (XY seuls : un
    contour projeté sur un relief n'a pas le même Z aux deux bouts.)"""
    return (len(chain) > 2
            and math.hypot(chain[0].x - chain[-1].x,
                           chain[0].y - chain[-1].y) < tol)


def rampe_direction_dz(chains, angle_deg, dz_debut, dz_fin):
    """Fonction dz(point) du style « dégradé dans une DIRECTION » : le
    défocus suit la position projetée sur `angle_deg`, normalisée sur
    l'emprise de TOUTES les chaînes.

    SOURCE UNIQUE, comme `rampe_trace_dz` : le générateur ET l'aperçu
    photo passent par ici. L'aperçu peignait auparavant la MOYENNE des
    deux largeurs sur tout le tracé -- une ligne d'épaisseur constante là
    où la machine trace un dégradé, donc un aperçu qui ne montrait pas ce
    qu'on allait obtenir."""
    if not chains:
        return lambda p: dz_debut
    ang = math.radians(angle_deg or 0.0)
    ux, uy = math.cos(ang), math.sin(ang)
    projs = [p.x * ux + p.y * uy for c in chains for p in c]
    pmin = min(projs)
    span = max(max(projs) - pmin, 1e-9)

    def dz(p):
        return dz_debut + (dz_fin - dz_debut) * (
            (p.x * ux + p.y * uy - pmin) / span)
    return dz


def rampe_trace_dz(chain, dz_debut, dz_fin, aller_retour=False):
    """dz de CHAQUE point d'une chaîne, pour le style « dégradé le long du
    tracé » : le défocus suit l'ABSCISSE CURVILIGNE, du premier au dernier
    point du trait.

    À ne pas confondre avec le style « dégradé » historique, qui rampe
    selon une DIRECTION DE L'ESPACE (`deg_angle`) : sur une droite orientée
    comme cette direction les deux coïncident, mais sur une spirale ou une
    courbe qui revient sur elle-même, la largeur y suit la POSITION et non
    le parcours. C'est pour un fuseau franc du début à la fin d'un trait
    que ce style-ci existe.

    `aller_retour` ne concerne que les BOUCLES FERMÉES : une rampe simple
    y ramène `dz_fin` juste à côté de `dz_debut`, donc un ressaut visible
    au point de fermeture. En aller-retour, `dz_fin` est atteint à
    MI-PARCOURS et la boucle se referme sur sa largeur de départ, sans
    raccord. Sur une chaîne ouverte l'option est ignorée : elle
    contredirait « largeur à la fin ».

    Chaque chaîne porte sa rampe ENTIÈRE, indépendamment des autres --
    sélectionner deux traits donne deux fuseaux identiques, et le résultat
    ne dépend donc pas de l'ordre de parcours (que `order_chains_by_proximity`
    choisit pour le trajet, pas pour le dessin)."""
    cum = _chain_cumlen(chain)
    total = cum[-1]
    if total < 1e-9:
        return [dz_debut] * len(chain)
    boucle = aller_retour and chaine_fermee(chain)
    dzs = []
    for s in cum:
        u = s / total
        # Aller-retour : 0 -> 1 -> 0. Le sommet tombe exactement à u=0,5,
        # donc la largeur de fin est atteinte à mi-parcours.
        t = (1.0 - abs(1.0 - 2.0 * u)) if boucle else u
        dzs.append(dz_debut + (dz_fin - dz_debut) * t)
    return dzs


def wave_resample(chain, period, amplitude, step=None):
    """Rééchantillonne la chaîne et renvoie [(point, dz)] : dz oscille de
    0 (foyer, trait fin) à `amplitude` (défocus max, trait large et pâle)
    le long de l'abscisse curviligne. La période demandée est AJUSTÉE
    pour qu'un nombre ENTIER de vagues tienne exactement sur la chaîne
    (period_eff = L / round(L/period)) : le trait commence ET finit au
    foyer, et sur une chaîne fermée (cercle) la vague boucle sans
    couture. Constaté sans cet ajustement : 219,9 mm de circonférence /
    période 29 mm = 7,6 vagues -> la boucle se refermait en pleine
    montée (S fort + point large sur le départ fin) = grosseur au point
    de bouture."""
    cum = _chain_cumlen(chain)
    total = cum[-1]
    if total < 1e-9:
        return []
    if period > 0 and total > period / 2.0:
        period = total / max(1, int(round(total / period)))
    if step is None:
        step = max(min(period / 12.0, 1.0), 0.05)
    n = max(2, int(math.ceil(total / step)) + 1)
    out = []
    for i in range(n):
        s = total * i / float(n - 1)
        p = _point_at_s(chain, cum, s)
        dz = amplitude * 0.5 * (1.0 - math.cos(2.0 * math.pi * s / period))
        out.append((p, dz))
    return out


def wave_peak_z_feed(amplitude, feed, period):
    """Vitesse Z crête (mm/min) d'un trait en vague parcouru à `feed` --
    dérivée max de la sinusoïde : pi * amplitude * feed / période. À
    comparer à Z_MAX_FEED_MM_MIN : au-delà, LinuxCNC ralentit le trajet
    pour respecter la limite de l'axe Z (pas de danger, juste plus
    lent que le feed programmé)."""
    if period <= 0:
        return 0.0
    return math.pi * amplitude * feed / period


def wave_fluence_powers(power, samples, amplitude):
    """Puissances S (une par échantillon de wave_resample) compensées en
    FLUENCE le long d'une vague : le point s'élargit avec le défocus,
    donc S suit le diamètre du point (S = power au SOMMET, le plus
    large ; réduit au foyer où le point est fin). Sans compensation, la
    puissance fixe s'étale au sommet et la fluence s'effondre : le trait
    pâlit et s'amincit là où il devrait être le plus épais (ruban
    inversé, constaté sur MDF). Fluence constante = ton uniforme, seule
    la LARGEUR ondule. Calibration invalide ou amplitude nulle ->
    puissance constante (comportement historique)."""
    ha = calibrated_half_angle()
    if not amplitude or amplitude <= 0 or not ha:
        return [float(power)] * len(samples)
    d_max = spot_diameter_at_defocus(amplitude, SPOT_FOCUS_MM, ha)
    if d_max <= 0:
        return [float(power)] * len(samples)
    out = []
    for _p, dz in samples:
        d = spot_diameter_at_defocus(dz, SPOT_FOCUS_MM, ha)
        out.append(max(5.0, round(power * d / d_max / 5.0) * 5.0))
    return out


def generate_flat_styled_body(chains, power, feed, z_base, style="plein",
                              dash_len=3.0, gap_len=2.0,
                              dot_spacing=1.5, dot_dwell_s=0.05,
                              wave_period=5.0, wave_amplitude=0.0,
                              marge_survol=0.0, min_safe_z=None):
    """Corps G-code (équivalent body_only : ni en-tête, ni armement, ni
    M2) d'un tracé À PLAT au Z machine z_base, rendu avec un style de
    trait : "plein", "tirets", "pointille" ou "vague" (cf. le bloc de
    commentaires en tête de section). Pour "vague", z_base est le FOYER
    et le trait monte jusqu'à z_base + wave_amplitude. Transit faisceau
    éteint à plat (pièce plate) au-dessus du point le plus haut du trait
    + marge_survol. Renvoie None si aucune chaîne."""
    if not chains:
        return None
    amp = wave_amplitude if style == "vague" else 0.0
    z_top = z_base + amp
    z_safe = z_top + marge_survol + 5.0
    if min_safe_z is not None:
        z_safe = max(z_safe, min_safe_z)
    z_transit = z_top + marge_survol

    lines = ["G0 Z{:.4f}".format(z_safe)]
    started = [False]

    def _goto(x, y, z_target):
        # 1re approche depuis la hauteur de sécurité (le bec peut venir de
        # n'importe où) ; ensuite transit à plat, faisceau éteint.
        if not started[0]:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_safe))
            lines.append("G0 Z{:.4f}".format(z_target))
            started[0] = True
        elif abs(z_transit - z_target) < 1e-9:
            lines.append("G0 X{:.4f} Y{:.4f}".format(x, y))
        else:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_transit))
            lines.append("G0 Z{:.4f}".format(z_target))

    beam_on = CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=power)
    beam_off = CMD_BEAM_OFF.format(sel=SPINDLE_SELECT)

    if style == "pointille":
        seg, f_dot = dot_micro_stroke(dot_spacing, dot_dwell_s)
        half = seg / 2.0
        for chain in chains:
            dots = dot_positions(chain, dot_spacing)
            for i, p in enumerate(dots):
                ux, uy = dot_stroke_dir(dots, i)
                _goto(p.x - ux * half, p.y - uy * half, z_base)
                lines.append(beam_on)
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(
                    p.x + ux * half, p.y + uy * half, f_dot))
                lines.append(beam_off)
    elif style == "tirets":
        for chain in chains:
            pieces = dash_chain(chain, dash_len, gap_len)
            if not pieces:
                continue
            first = pieces[0][0][0]
            _goto(first.x, first.y, z_base)
            for piece, on in pieces:
                if on:
                    lines.append(beam_on)
                for p in piece[1:]:
                    lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(p.x, p.y, feed))
                if on:
                    lines.append(beam_off)
    elif style == "vague":
        for chain in chains:
            samples = wave_resample(chain, wave_period, wave_amplitude)
            if len(samples) < 2:
                continue
            s_wave = wave_fluence_powers(power, samples, wave_amplitude)
            p0, dz0 = samples[0]
            _goto(p0.x, p0.y, z_base + dz0)
            lines.extend(cmd_power_prefix(s_wave[0]))
            if cmd_power_suffix(s_wave[0]):
                lines.append(cmd_power_suffix(s_wave[0]))
            for (p, dz), s_pt in zip(samples[1:], s_wave[1:]):
                lines.extend(cmd_power_prefix(s_pt))
                lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f} {}".format(
                    p.x, p.y, z_base + dz, feed, cmd_power_suffix(s_pt)))
            lines.append(beam_off)
    else:  # "plein"
        for chain in chains:
            _goto(chain[0].x, chain[0].y, z_base)
            lines.append(beam_on)
            for p in chain[1:]:
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(p.x, p.y, feed))
            lines.append(beam_off)

    if started[0]:
        lines.append("G0 Z{:.4f}".format(z_safe))
    return "\n".join(lines)


# ==========================================================================
# MODE : GRAVURE REMPLIE (NOIR) -- remplissage défocus + contour au foyer
# ==========================================================================
def build_filled_engraving_edges(faces, spacing, angle_deg, fill_inset=0.0, add_perimeter=True):
    """À partir de faces 2D (texte/forme fermée), renvoie
    (fill_edges, contour_edges) :

    - contour_edges : les arêtes du bord de chaque face (contour extérieur
      + éventuels trous, ex. l'intérieur d'un « O »), à graver net au
      foyer.
    - fill_edges : les hachures de remplissage, calculées sur les faces
      RENTRÉES de fill_inset (le rayon du point laser élargi) par un offset
      2D vers l'intérieur -- pour que la brûlure (hachures + largeur du
      point) ne déborde pas du contour. Si l'offset échoue ou fait
      disparaître une face (trait plus fin que 2*fill_inset), cette face
      n'est simplement pas remplie : le contour (éventuellement un peu
      défocalisé) la noircit.

    add_perimeter : ajoute au remplissage le CONTOUR de la zone rentrée
    (les arêtes des faces insettées), tracé avec le faisceau de remplissage.
    Les hachures parallèles laissent sinon une fine bande non brûlée entre
    la dernière hachure et le bord (surtout sur les bords obliques) -- ce
    liseré suit le bord et le comble, pour un noir plein jusqu'au contour.

    L'appelant calcule fill_inset = rayon du point au défocus retenu
    (spot_diameter_at_defocus / 2)."""
    contour_edges = []
    fill_faces = []
    for f in faces:
        contour_edges.extend(f.Edges)
        if fill_inset > 0:
            # vide si trop fin -> pas de remplissage ici
            fill_faces.extend(inset_face_robuste(f, fill_inset))
        else:
            fill_faces.append(f)
    fill_edges = generate_hatch_edges(fill_faces, spacing, angle_deg) if fill_faces else []
    if add_perimeter:
        for f in fill_faces:
            fill_edges.extend(f.Edges)
    return fill_edges, contour_edges


def apply_fill_power_gradient(body, s_debut, s_fin, angle_deg):
    """Module la puissance d'un corps de G-code le long d'une direction :
    S varie linéairement de s_debut à s_fin entre les deux extrémités de
    la forme projetées sur la direction (angle en degrés dans le plan XY,
    0 = de gauche à droite, 90 = de bas en haut). Les S d'armement non
    nuls du corps sont MULTIPLIÉS par le rapport local -- une éventuelle
    compensation de fluence déjà appliquée est donc conservée -- et les
    S0 (faisceau coupé, transits) restent intacts. Le mot S est réémis à
    chaque segment G1 dont la valeur arrondie change."""
    import re as _re
    dx = math.cos(math.radians(angle_deg))
    dy = math.sin(math.radians(angle_deg))
    move_re = _re.compile(r"^G[01]\b")
    x_re = _re.compile(r"X(-?\d+\.?\d*)")
    y_re = _re.compile(r"Y(-?\d+\.?\d*)")
    s_re = _re.compile(r"^S(\d+\.?\d*)(?:\s|$)")
    lignes = body.split("\n")

    # Passe 1 : bornes de la projection sur la direction du dégradé.
    projs = []
    x = y = None
    for ligne in lignes:
        if move_re.match(ligne):
            mx, my = x_re.search(ligne), y_re.search(ligne)
            if mx:
                x = float(mx.group(1))
            if my:
                y = float(my.group(1))
            if x is not None and y is not None:
                projs.append(x * dx + y * dy)
    if not projs:
        return body
    tmin = min(projs)
    span = max(max(projs) - tmin, 1e-9)
    s0 = max(float(s_debut), 1e-9)

    # Passe 2 : réécriture. Les lignes d'armement S sont retenues et le S
    # local est émis avec le premier G1 qui suit (puis à chaque changement).
    out = []
    x = y = None
    base_s = None
    dernier_s = None
    for ligne in lignes:
        m = s_re.match(ligne.strip())
        if m:
            val = float(m.group(1))
            if val <= 0:
                base_s = None
                dernier_s = None
                out.append(ligne)
            else:
                base_s = val
            continue
        if move_re.match(ligne):
            mx, my = x_re.search(ligne), y_re.search(ligne)
            px, py = x, y
            if mx:
                x = float(mx.group(1))
            if my:
                y = float(my.group(1))
            if (base_s is not None and ligne.startswith("G1")
                    and x is not None and y is not None):
                xm = x if px is None else (x + px) / 2.0
                ym = y if py is None else (y + py) / 2.0
                t = ((xm * dx + ym * dy) - tmin) / span
                cible = s_debut + t * (float(s_fin) - float(s_debut))
                s_loc = max(0.0, min(base_s * cible / s0, S_MAX))
                s_int = int(round(s_loc))
                if dernier_s is None or s_int != dernier_s:
                    out.append("S{} {sel}".format(s_int, sel=SPINDLE_SELECT))
                    dernier_s = s_int
        out.append(ligne)
    return "\n".join(out)


def generate_gcode_filled_engraving(fill_edges, contour_edges, z_focus, defocus,
                                     fill_power, fill_feed,
                                     draw_contour=True, contour_power=300.0, contour_feed=1000.0,
                                     contour_z_offset=0.0, marge_survol=5.0,
                                     fill_style="plein", contour_style="plein",
                                     fill_style_params=None, contour_style_params=None,
                                     pre_gcode="", post_gcode="", frame_only=False, quiet=False,
                                     body_only=False, min_safe_z=None, header_note=None,
                                     grad_power_fin=None, grad_angle_deg=0.0):
    """Grave une forme/texte à plat en NOIR PLEIN : d'abord le remplissage
    par hachures gravé en DÉFOCUS (point élargi, cf. remplissage défocus du
    mode Hachures 2D -- fill_edges doivent déjà être rentrées d'un rayon de
    point par l'appelant pour ne pas déborder), PUIS le contour repassé
    NET AU FOYER par-dessus pour une arête propre. Un seul armement pour
    les deux.

    Deux hauteurs de travail : remplissage à z_focus + defocus, contour à
    z_focus + contour_z_offset (0 = foyer ; augmenter pour épaissir le
    trait du contour en le défocalisant légèrement). Les deux corps
    réutilisent generate_gcode_curved en marquage à PLAT (reference_shape
    = None) et body_only : un plancher de retrait commun (min_safe_z)
    garantit un transit sûr entre les deux hauteurs.

    fill_style / contour_style : style de trait ("plein" = comportement
    historique, "tirets", "pointille", "vague" -- cf. la section STYLES DE
    TRAIT). fill_style_params / contour_style_params : dict d'arguments
    nommés de generate_flat_styled_body (dash_len, gap_len, dot_spacing,
    dot_dwell_s, wave_period, wave_amplitude). En "vague", le Z de BASE
    du corps est le FOYER (z_focus) et le trait oscille jusqu'à
    z_focus + wave_amplitude -- defocus/contour_z_offset ne s'appliquent
    pas à ce style (la vague EST la modulation de défocus).

    frame_only : ne trace que le rectangle englobant (cadrage séparé).
    header_note : ligne de commentaire libre ajoutée à l'en-tête du G-code
    (ex. trace de la correction d'espacement par la largeur brûlée mesurée).
    grad_power_fin / grad_angle_deg : REMPLISSAGE EN DÉGRADÉ (style
    "plein" uniquement) -- la puissance du remplissage varie linéairement
    de fill_power à grad_power_fin le long de la direction grad_angle_deg
    (0 = de gauche à droite), via apply_fill_power_gradient."""
    fill_style_params = dict(fill_style_params or {})
    contour_style_params = dict(contour_style_params or {})

    z_fill = z_focus if fill_style == "vague" else z_focus + defocus
    z_contour = z_focus if contour_style == "vague" else z_focus + contour_z_offset
    z_fill_top = z_fill + (fill_style_params.get("wave_amplitude", 0.0)
                           if fill_style == "vague" else 0.0)
    z_contour_top = z_contour + (contour_style_params.get("wave_amplitude", 0.0)
                                 if contour_style == "vague" else 0.0)

    has_contour = bool(draw_contour and contour_edges)
    # Hauteur de sécurité commune (marquage à plat : Z natif = 0, donc
    # z_safe = niveau de travail + marge + 5, cf. generate_gcode_curved).
    # En vague, le "niveau de travail" est le sommet de l'oscillation.
    safe_levels = [z_fill_top] + ([z_contour_top] if has_contour else [])
    global_min_safe_z = max(safe_levels) + marge_survol + 5.0
    if min_safe_z is not None:
        global_min_safe_z = max(global_min_safe_z, min_safe_z)

    if not quiet:
        for what, style, params, feed in (
                ("remplissage", fill_style, fill_style_params, fill_feed),
                ("contour", contour_style, contour_style_params, contour_feed)):
            if style != "vague":
                continue
            peak = wave_peak_z_feed(params.get("wave_amplitude", 0.0), feed,
                                    params.get("wave_period", 5.0))
            if peak > Z_MAX_FEED_MM_MIN:
                FreeCAD.Console.PrintWarning(
                    "Vague ({}) : vitesse Z crête ~{:.0f}mm/min > limite Z supposée "
                    "({:.0f}mm/min, cf. Préférences) -- LinuxCNC ralentira le trajet "
                    "pour suivre (pas de danger, job juste plus lent que le feed "
                    "programmé). Allonger la période ou réduire l'amplitude/le feed "
                    "pour l'éviter.\n".format(what, peak, Z_MAX_FEED_MM_MIN))

    if frame_only:
        all_edges = list(fill_edges or []) + (list(contour_edges) if has_contour else [])
        chains = chain_edges(all_edges)
        if not chains:
            return None
        pts = [p for c in chains for p in c]
        lines = ["(G-Code Laser - Gravure remplie : cadrage)"]
        if not body_only:
            lines.append("G21")
            lines.append("G90")
            lines.append("G94")
            if cmd_path_blend():
                lines.append(cmd_path_blend())
            lines.append(cmd_tool_comp())
            lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
        lines.append("G0 Z{:.4f}".format(global_min_safe_z))
        lines.extend(build_frame_trace(
            min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts), global_min_safe_z))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    # Corps : remplissage d'abord, contour ensuite (repassé propre). Le
    # style "plein" garde le chemin historique (generate_gcode_curved à
    # plat) ; les autres styles passent par generate_flat_styled_body.
    def _make_body(edges, style, params, s_power, s_feed, z_base):
        if not edges:
            return None
        if style == "plein":
            ha = calibrated_half_angle()
            spot_d = (spot_diameter_at_defocus(z_base - z_focus,
                                               SPOT_FOCUS_MM, ha)
                      if ha else None)
            return generate_gcode_curved(
                edges, s_power, s_feed, z_base, marge_survol,
                reference_shape=None, body_only=True, quiet=quiet,
                min_safe_z=global_min_safe_z, dose_spot_d=spot_d)
        return generate_flat_styled_body(
            chain_edges(edges), s_power, s_feed, z_base, style,
            marge_survol=marge_survol, min_safe_z=global_min_safe_z, **params)

    bodies = []
    fill_body = _make_body(fill_edges, fill_style, fill_style_params,
                           fill_power, fill_feed, z_fill)
    if fill_body and grad_power_fin is not None and fill_style == "plein":
        fill_body = apply_fill_power_gradient(
            fill_body, fill_power, grad_power_fin, grad_angle_deg)
    if fill_body:
        bodies.append(("Remplissage defocus", fill_body))
    if has_contour:
        contour_body = _make_body(contour_edges, contour_style, contour_style_params,
                                  contour_power, contour_feed, z_contour)
        if contour_body:
            bodies.append(("Contour", contour_body))
    if not bodies:
        return None

    style_names = {"plein": "trait plein", "tirets": "tirets",
                   "pointille": "pointille", "vague": "vague defocus"}
    lines = []
    lines.append("(G-Code Laser - Gravure remplie noir)")
    lines.append("(Remplissage Z={:.4f} defocus={:.4f} S{:.0f} F{:.0f} style={})".format(
        z_fill, defocus, fill_power, fill_feed, style_names.get(fill_style, fill_style)))
    if grad_power_fin is not None and fill_style == "plein":
        lines.append("(Degrade de puissance : S{:.0f} -> S{:.0f}, direction {:.0f} deg)".format(
            fill_power, grad_power_fin, grad_angle_deg))
    if any(label == "Contour" for label, _ in bodies):
        lines.append("(Contour Z={:.4f} S{:.0f} F{:.0f} style={})".format(
            z_contour, contour_power, contour_feed, style_names.get(contour_style, contour_style)))
    if header_note:
        lines.append("({})".format(header_note))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
        if pre_gcode.strip():
            lines.append("(-- G-code personnalisé (avant) --)")
            lines.append(pre_gcode.strip())
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    for label, body in bodies:
        lines.append("(===== {} =====)".format(label))
        lines.append(body)
    if not body_only:
        if post_gcode.strip():
            lines.append("(-- G-code personnalisé (après) --)")
            lines.append(post_gcode.strip())
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : JOB COMBINÉ (PLUSIEURS OPÉRATIONS, UN SEUL ARMEMENT)
# ==========================================================================
# Chaque opération est un dict {"type": "curved"|"flat"|"testgrid",
# "label": str, "params": {...}} où "params" contient exactement les
# arguments nommés du générateur correspondant (generate_gcode_curved /
# generate_gcode_flat_multipass / generate_gcode_test_grid), SANS
# body_only/quiet/frame_only (ajoutés automatiquement ici). "type" est un
# identifiant fonctionnel (jamais accentué), "label" est un texte libre
# affiché à l'utilisateur (dans les commentaires G-code et l'aperçu de
# durée).
def _operation_intrinsic_safe_z(op_type, params):
    """Hauteur de sécurité (Z machine) qu'UNE SEULE opération utiliserait
    isolément -- même formule que le calcul interne de generate_gcode_curved
    / generate_gcode_curved_cut / generate_gcode_flat_multipass /
    generate_gcode_test_grid, dupliquée ici en version légère (sans
    générer tout le G-code) pour que generate_gcode_combined puisse
    calculer une hauteur de sécurité GLOBALE (le maximum sur toutes les
    opérations) AVANT de générer quoi que ce soit, et l'imposer comme
    plancher à chacune via min_safe_z. Renvoie None si la géométrie est
    vide/absente (opération qui de toute façon sera ignorée plus loin)."""
    if op_type in ("curved", "curved_cut"):
        edges = params.get("edges")
        if not edges:
            return None
        chains = chain_edges(edges)
        if not chains:
            return None
        all_pts = [p for chain in chains for p in chain]
        z_min = min(p.z for p in all_pts)
        z_max = max(p.z for p in all_pts)
        z_offset = params.get("z_focus", 0.0) - z_min
        # Manquait : le style "vague" grave plus haut de wave_amplitude
        # (cf. generate_gcode_curved) -- sans ce terme, une opération de
        # Marquage en Vague pouvait imposer un plancher trop bas au reste
        # du job combiné.
        style_params = params.get("style_params") or {}
        wave_amp = style_params.get("wave_amplitude", 0.0) if params.get("style") == "vague" else 0.0
        return z_max + z_offset + wave_amp + params.get("marge_survol", 0.0) + 5.0
    if op_type == "filled":
        # Même formule que generate_gcode_filled_engraving (version légère).
        fill_edges = params.get("fill_edges") or []
        contour_edges = params.get("contour_edges") or []
        has_contour = bool(params.get("draw_contour", True) and contour_edges)
        if not fill_edges and not has_contour:
            return None
        z_focus = params.get("z_focus", 0.0)
        fsp = dict(params.get("fill_style_params") or {})
        csp = dict(params.get("contour_style_params") or {})
        fill_style = params.get("fill_style", "plein")
        contour_style = params.get("contour_style", "plein")
        z_fill = z_focus if fill_style == "vague" else z_focus + params.get("defocus", 0.0)
        z_contour = (z_focus if contour_style == "vague"
                     else z_focus + params.get("contour_z_offset", 0.0))
        z_fill_top = z_fill + (fsp.get("wave_amplitude", 0.0)
                               if fill_style == "vague" else 0.0)
        z_contour_top = z_contour + (csp.get("wave_amplitude", 0.0)
                                     if contour_style == "vague" else 0.0)
        levels = [z_fill_top] + ([z_contour_top] if has_contour else [])
        return max(levels) + params.get("marge_survol", 5.0) + 5.0
    if op_type == "flat":
        z_start = params.get("z_start")
        if z_start is None:
            z_start = nozzle_height_for_thickness(params.get("thickness", 0.0))
        return z_start + TRAVEL_CLEARANCE_MM
    if op_type == "testgrid":
        cells = params.get("cells")
        if not cells:
            return None
        z_work = params.get("z_work", 0.0)
        z_levels = [z_work, z_work + params.get("cell_z_offset", 0.0)]
        if params.get("draw_border"):
            # Même formule que z_safe dans generate_gcode_test_grid : le
            # cadre au foyer a son propre Z, à compter dans le plancher.
            z_levels.append(params.get("z_border", 0.0))
        return max(z_levels) + TRAVEL_CLEARANCE_MM
    return None


def generate_gcode_combined(operations, pre_gcode="", post_gcode="", frame_only=False, quiet=False,
                             warnings_out=None, body_only=False):
    """Assemble plusieurs opérations (Marquage courbe / Découpe
    multi-passes / Grille de test, chacune avec ses propres paramètres)
    en UN SEUL job avec UN SEUL armement (M3) au tout début et UN SEUL
    désarmement (M5)/fin de programme (M2) à la toute fin -- au lieu
    d'un cycle armement/désarmement par opération, pour des transitions
    plus rapides entre opérations (le laser reste réputé prêt à tirer
    tout du long, cf. CMD_BEAM_ON/CMD_BEAM_OFF qui continuent de gérer
    la puissance réelle indépendamment de cet armement).

    frame_only : ne génère QU'UN SEUL rectangle englobant GLOBAL du job
    (l'emprise de toutes les opérations réunies, laser jamais armé), pour
    un fichier de vérification de cadrage séparé -- et non un rectangle
    par opération, qui ferait sautiller la tête d'un cadre à l'autre.

    warnings_out : si fourni, reçoit "nozzle_warnings" (compte total) et
    "nozzle_points" (liste de FreeCAD.Vector, coordonnées natives) en
    fusionnant marquage ET découpe de TOUTES les sous-opérations
    "curved"/"curved_cut" -- seules ces deux le supportent (cf.
    generate_gcode_curved / generate_gcode_curved_cut) ; le risque de
    collision est le même quelle que soit l'opération qui l'a détecté,
    pas la peine de les distinguer côté appelant.

    Une opération dont le générateur renvoie None (aucune géométrie,
    ex: sélection vide) est ignorée avec un avertissement (sauf si
    quiet).

    body_only : comme pour les générateurs de mode -- omet l'en-tête/
    l'armement/le désarmement/M2, pour que ce job combiné devienne à son
    tour le corps d'un ENSEMBLE encore plus large (cf.
    generate_gcode_planches_combinees, qui empile plusieurs planches de
    calibration -- elles-mêmes des jobs combinés -- sous un seul
    armement)."""
    if not operations:
        return None

    dispatch = {
        "curved": generate_gcode_curved,
        "curved_cut": generate_gcode_curved_cut,
        "flat": generate_gcode_flat_multipass,
        "testgrid": generate_gcode_test_grid,
        "filled": generate_gcode_filled_engraving,
    }

    # Hauteur de sécurité GLOBALE (max sur toutes les opérations),
    # calculée AVANT de générer quoi que ce soit et imposée comme
    # plancher (min_safe_z) à chaque opération -- sans ça, chaque
    # opération ne retombe qu'à SA PROPRE hauteur de sécurité en
    # commençant, potentiellement plus basse que le relief de
    # l'opération PRÉCÉDENTE à l'endroit où elle s'est arrêtée : la
    # nouvelle opération plonge alors tout droit vers le bas AU MAUVAIS
    # ENDROIT (encore sur l'ancienne opération en X/Y) avant même d'avoir
    # rejoint sa propre géométrie -- collision constatée en pratique
    # (gravure puis découpe sur un même dôme).
    safe_zs = [
        _operation_intrinsic_safe_z(op.get("type"), op.get("params", {}))
        for op in operations
    ]
    safe_zs = [z for z in safe_zs if z is not None]
    global_min_safe_z = max(safe_zs) if safe_zs else None

    bodies = []
    for i, op in enumerate(operations):
        op_type = op.get("type")
        label = op.get("label") or "Operation {}".format(i + 1)
        generator = dispatch.get(op_type)
        if generator is None:
            if not quiet:
                FreeCAD.Console.PrintWarning(
                    "Type d'opération inconnu ignoré dans le job combiné : {}\n".format(op_type))
            continue
        params = dict(op.get("params", {}))
        params["body_only"] = True
        params["quiet"] = quiet
        params["frame_only"] = frame_only
        if global_min_safe_z is not None:
            params["min_safe_z"] = global_min_safe_z
        op_warnings = None
        if warnings_out is not None and op_type in ("curved", "curved_cut"):
            op_warnings = {}
            params["warnings_out"] = op_warnings
        gcode = generator(**params)
        if not gcode:
            if not quiet:
                FreeCAD.Console.PrintWarning(
                    "Opération '{}' ignorée dans le job combiné (aucune géométrie générée).\n".format(label))
            continue
        bodies.append((label, gcode))
        if op_warnings:
            key_w = "nozzle_marking_warnings" if op_type == "curved" else "nozzle_cut_warnings"
            key_p = "nozzle_marking_points" if op_type == "curved" else "nozzle_cut_points"
            warnings_out["nozzle_warnings"] = warnings_out.get("nozzle_warnings", 0) + op_warnings.get(key_w, 0)
            warnings_out.setdefault("nozzle_points", []).extend(op_warnings.get(key_p, []))

    if not bodies:
        return None

    lines = []
    if not body_only:
        lines.append("(G-Code Laser - Job combiné : {} operation(s))".format(len(bodies)))
        for label, _ in bodies:
            lines.append("(  - {})".format(label))
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))

    if frame_only:
        # UN SEUL rectangle englobant GLOBAL (et non un par opération) : le
        # cadrage sert à vérifier que TOUT le job tient sur la pièce, en un
        # seul tour propre. On récupère l'emprise en relisant les cadrages
        # par opération déjà générés (chacun = 4 coins), puis on ne trace
        # que leur enveloppe commune. Pas de pré/post-code : simple contrôle
        # de position, comme sur les modes simples.
        xs, ys, zs = [], [], []
        for _, body in bodies:
            rapides, marques = parse_gcode_toolpath(body)
            for seg in rapides + marques:
                for pt in seg:
                    xs.append(pt.x)
                    ys.append(pt.y)
                    zs.append(pt.z)
        if not xs:
            return None
        z_cadrage = max(zs) if zs else (
            global_min_safe_z if global_min_safe_z is not None else 0.0)
        lines.append("(-- Cadrage : rectangle englobant global du job --)")
        lines.append("G0 Z{:.4f}".format(z_cadrage))
        lines.extend(build_frame_trace(
            min(xs), max(xs), min(ys), max(ys), z_cadrage))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if not body_only and pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    if not body_only:
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))

    for label, gcode in bodies:
        lines.append("(===== Operation : {} =====)".format(label))
        lines.append(gcode)

    if not body_only:
        if post_gcode.strip():
            lines.append("(-- G-code personnalisé (après) --)")
            lines.append(post_gcode.strip())

        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : GRAVURE PHOTO (TRAME DE POINTS)
# ==========================================================================
# Une image en niveaux de gris devient une grille de POINTS laser au pas
# `pitch` : c'est le motif "pointillé" poussé au bout -- chaque point
# encode la noirceur locale de l'image. Deux tramages :
#   - "duree"     : un point par case non blanche, durée du pulse (G4)
#                   proportionnelle à la noirceur (modulation d'amplitude,
#                   rendu doux, dépend de la réponse du matériau) ;
#   - "diffusion" : tramage Floyd-Steinberg -- points TOUS identiques
#                   (dwell_max), c'est leur DENSITÉ locale qui rend le
#                   gris (plus robuste : un point est brûlé ou pas, pas de
#                   demi-teinte à calibrer).
# L'image est fournie en NOIRCEUR (0..1, 1 = noir plein), lignes du HAUT
# vers le BAS -- la conversion image -> grille est faite par le panneau
# (QImage, couche UI) pour garder ce module sans dépendance Qt.
def floyd_steinberg_dither(darkness_rows):
    """Diffusion d'erreur Floyd-Steinberg sur une grille de noirceur
    (0..1). Renvoie une grille de 0/1 (1 = point gravé) : l'erreur de
    quantification de chaque case est répartie sur ses voisines pas
    encore traitées (7/16 à droite, 3/16-5/16-1/16 dessous), ce qui
    préserve la noirceur moyenne locale."""
    rows = [list(r) for r in darkness_rows]
    h = len(rows)
    w = len(rows[0]) if h else 0
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            old = rows[y][x]
            new = 1.0 if old >= 0.5 else 0.0
            out[y][x] = int(new)
            err = old - new
            if x + 1 < w:
                rows[y][x + 1] += err * (7.0 / 16.0)
            if y + 1 < h:
                if x > 0:
                    rows[y + 1][x - 1] += err * (3.0 / 16.0)
                rows[y + 1][x] += err * (5.0 / 16.0)
                if x + 1 < w:
                    rows[y + 1][x + 1] += err * (1.0 / 16.0)
    return out


def halftone_dots(darkness_rows, pitch, dwell_min_s, dwell_max_s,
                  mode="diffusion", white_threshold=0.08):
    """Liste des points [(x, y, dwell_s), ...] de la trame, dans l'ordre
    de parcours (serpentin : une ligne sur deux inversée, pour minimiser
    les transits). Partagée par le générateur G-code ET l'aperçu des
    points dans la vue 3D (même trame exactement). Image posée coin
    bas-gauche en X0 Y0."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1:
        return []
    dots = []
    if mode == "diffusion":
        binary = floyd_steinberg_dither(darkness_rows)
        for row in range(h):
            y = (h - 1 - row) * pitch
            cols = range(w) if row % 2 == 0 else range(w - 1, -1, -1)
            for col in cols:
                if binary[row][col]:
                    dots.append((col * pitch, y, dwell_max_s))
    else:
        for row in range(h):
            y = (h - 1 - row) * pitch
            cols = range(w) if row % 2 == 0 else range(w - 1, -1, -1)
            for col in cols:
                d = min(1.0, max(0.0, darkness_rows[row][col]))
                if d < white_threshold:
                    continue
                dots.append((col * pitch, y,
                             dwell_min_s + (dwell_max_s - dwell_min_s) * d))
    return dots


def micro_trait_oriente(dots, i, half):
    """(x_depart, x_arrivee) du micro-trait du point `i`, ORIENTÉ dans le
    sens de parcours de sa ligne.

    `halftone_dots` range déjà les points en serpentin (une ligne sur deux
    inversée) pour économiser du trajet. Mais graver chaque micro-trait
    toujours de gauche à droite ruine ce gain sur les lignes parcourues
    vers la gauche : la machine se place à x-half, brûle vers la droite,
    puis recule au-delà du point suivant. Un aller-retour par point, sur
    des dizaines de milliers de points."""
    x = dots[i][0]
    y = dots[i][1]
    vers_droite = True
    if i + 1 < len(dots) and abs(dots[i + 1][1] - y) < 1e-9:
        vers_droite = dots[i + 1][0] > x
    elif i > 0 and abs(dots[i - 1][1] - y) < 1e-9:
        vers_droite = dots[i - 1][0] < x
    return (x - half, x + half) if vers_droite else (x + half, x - half)


def generate_gcode_halftone(darkness_rows, pitch, z_work, power,
                            dwell_min_s, dwell_max_s,
                            mode="diffusion", white_threshold=0.08,
                            pre_gcode="", post_gcode="", frame_only=False, quiet=False):
    """G-code de gravure photo en trame de points (cf. bloc de
    commentaires ci-dessus). darkness_rows : grille de noirceur 0..1
    (lignes haut -> bas). L'image est posée coin bas-gauche en X0 Y0,
    parcourue en serpentin (une ligne sur deux inversée) pour minimiser
    les transits. white_threshold (mode duree) : noirceur en-dessous de
    laquelle AUCUN point n'est gravé -- évite de piqueter les blancs.
    Renvoie None si la grille est vide ou toute blanche."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1:
        return None

    dots = halftone_dots(darkness_rows, pitch, dwell_min_s, dwell_max_s,
                         mode=mode, white_threshold=white_threshold)
    if not dots:
        return None

    z_safe = z_work + TRAVEL_CLEARANCE_MM
    total_dwell = sum(dw for _, _, dw in dots)

    lines = []
    lines.append("(G-Code Laser - Gravure photo : trame de points)")
    lines.append("(Image : {} x {} cases au pas {:.2f}mm = {:.1f} x {:.1f}mm)".format(
        w, h, pitch, (w - 1) * pitch, (h - 1) * pitch))
    lines.append("(Tramage : {} -- {} points, {:.0f}s de pulses cumules)".format(
        "diffusion Floyd-Steinberg" if mode == "diffusion" else "duree variable",
        len(dots), total_dwell))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(0.0, (w - 1) * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    # Chaque point est un MICRO-TRAIT (pas un pulse G4 a l'arret) : meme
    # duree d'exposition, mais le faisceau BOUGE pendant le tir -- requis
    # par les machines dont la puissance est asservie a la vitesse reelle
    # (a l'arret, l'asservissement force la puissance a zero et un pulse
    # G4 ne grave rien) ; sans asservissement le rendu est identique.
    seg = max(0.05, min(0.3 * pitch, 0.2))
    half = seg / 2.0
    x0, y0, _ = dots[0]
    lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x0 - half, y0, z_safe))
    lines.append("G0 Z{:.4f}".format(z_work))
    beam_off = CMD_BEAM_OFF.format(sel=SPINDLE_SELECT)
    sel = SPINDLE_SELECT
    first = True
    for i, (x, y, dwell) in enumerate(dots):
        xa, xb = micro_trait_oriente(dots, i, half)
        if not first:
            lines.append("G0 X{:.4f} Y{:.4f}".format(xa, y))
        first = False
        f_dot = max(1.0, seg / max(dwell, 1e-3) * 60.0)
        lines.extend(cmd_power_prefix(power))
        lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
            xb, y, f_dot, cmd_power_suffix(power)))
        lines.append(beam_off)
    lines.append("G0 Z{:.4f}".format(z_safe))

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def _emit_raster_rows(lines, grid, pitch, z_work, z_safe, feed, y0=0.0):
    """Émission SERPENTIN partagée des trames en lignes (photo calibrée et
    diffusion en lignes) : grid[row][col] = S par cellule (0 = blanc). Une
    ligne = plages de S constant fusionnées en un G1 chacune (S0 inclus
    entre deux plages marquées : trajet fluide, faisceau coupé). Lignes
    toutes blanches sautées, G0 direct entre lignes."""
    sel = SPINDLE_SELECT
    h = len(grid)
    started = False
    for row in range(h):
        y = y0 + (h - 1 - row) * pitch
        cells = grid[row]
        nz = [c for c in range(len(cells)) if cells[c] > 0]
        if not nz:
            continue
        reverse = row % 2 == 1
        c0, c1 = nz[0], nz[-1]
        if not reverse:
            x_entry = c0 * pitch
            rng = range(c0, c1 + 1)
        else:
            x_entry = (c1 + 1) * pitch
            rng = range(c1, c0 - 1, -1)
        if not started:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x_entry, y, z_safe))
            lines.append("G0 Z{:.4f}".format(z_work))
            started = True
        else:
            lines.append("G0 X{:.4f} Y{:.4f}".format(x_entry, y))
        cur_s = None
        for c in rng:
            s = cells[c]
            edge = (c + 1) * pitch if not reverse else c * pitch
            if s != cur_s:
                lines.extend(cmd_power_prefix(s))
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
                    edge, y, feed, cmd_power_suffix(s)))
                cur_s = s
            else:
                # Prolonge le G1 courant : c'est TOUJOURS lines[-1], le M67
                # eventuel etant pose AVANT lui.
                lines[-1] = "G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
                    edge, y, feed, cmd_power_suffix(cur_s))
        lines.append(CMD_BEAM_OFF.format(sel=sel))
    lines.append("G0 Z{:.4f}".format(z_safe))


# --- Lignes gravées : le TRAIT ENFLE avec l'image -------------------------
# Ni puissance perçue ni trame : le gris est une LARGEUR de trait, donc de la
# géométrie -- comme la similigravure, mais en lignes continues. La ligne
# n'est jamais coupée : elle part d'une épaisseur minimale réglable dans les
# blancs et enfle jusqu'à la largeur maximale que le matériau donne.
#
# Ça se grave AU FOYER, et c'est contre-intuitif : les gros traits relevés en
# défocus par la rampe ne servent à rien ici. Ce qui fait le contraste n'est
# pas la largeur absolue mais le RAPPORT entre le trait le plus fin et le plus
# épais -- le pas vaut au moins le trait le plus large, donc la couverture va
# de fin/pas à épais/pas, et le contraste plafonne à 1 - fin/épais. Or en
# défocus le point est déjà large, sa taille est fixée par la géométrie du
# faisceau, et la puissance n'y change presque rien. Mesuré sur hêtre --
# défocus 36 : 1,90 à 2,60 mm, soit 1,4x seulement ; défocus 15 : 0,80 à
# 1,30 mm, 1,6x ; AU FOYER : 0,10 à 0,30 mm, 3,0x. Au foyer la largeur brûlée
# n'est pas la taille du point mais l'endroit où le profil du faisceau
# franchit le seuil de brûlure du bois -- et ce point-là se déplace beaucoup
# avec la puissance. D'où le contraste : 67 % contre 27 %.
#
# Deuxième fait mesuré : la vitesse ne change rien tant qu'on reste dessous
# (0,10 -> 0,30 identique à F200, F400 ET F800 -- autant prendre la plus
# rapide), mais à partir de F1500 la largeur est PLATE à 0,10 quelle que soit
# la puissance. Au-delà, le trait n'enfle plus du tout et le mode n'a plus
# d'objet.


def burn_width_power_table(material, feed, pas_s=5.0):
    """[(S, largeur brûlée), ...] au FOYER pour cette vitesse, échantillonné
    sur `burn_width_at` -- donc sur les mesures, jamais sur une formule
    parallèle. S croissant, largeur rendue monotone : une largeur qui
    redescendrait quand la puissance monte est une erreur de mesure, pas une
    propriété du bois. [] si le matériau n'a pas de table."""
    if feed <= 0:
        return []
    mesures = load_burn_widths(_burn_width_material(material) or "").get("focus")
    if not mesures:
        return []
    # Partir de la plus faible puissance MESURÉE, pas de S0 : sous la plage
    # mesurée `burn_width_at` borne et rend la largeur du bord, si bien que
    # S0 semble donner un trait de 0,10 mm alors qu'il ne grave rien. Le
    # tramage promet une ligne jamais coupée -- il ne doit jamais choisir
    # une puissance dont on ne sait rien.
    s_dep = min(float(e.get("power", 0) or 0) for e in mesures)
    n = int(S_MAX / max(pas_s, 1.0))
    table = []
    plafond = 0.0
    for k in range(n + 1):
        s = k * pas_s
        if s < s_dep - 1e-9:
            continue
        w = burn_width_at(s, feed, material)
        if w is None:
            return []
        plafond = max(plafond, float(w))
        table.append((s, plafond))
    return table


def burn_width_range(material, feed):
    """(largeur_mini, largeur_maxi) atteignables au foyer à cette vitesse,
    ou None. Les deux égales = le trait n'enfle plus, le tramage « lignes
    gravées » n'a plus d'objet (F >= 1500 sur hêtre : plat à 0,10 mm)."""
    table = burn_width_power_table(material, feed)
    if not table:
        return None
    return table[0][1], table[-1][1]


def swell_max_feed(material):
    """La vitesse mesurée la PLUS RAPIDE à laquelle le trait enfle encore,
    ou None. Sert à ne pas se contenter de dire « trop vite » : au-delà
    d'un seuil la largeur ne dépend plus de la puissance, et l'utile est
    de nommer la vitesse qui marche, pas celle qui échoue."""
    mat = _burn_width_material(material)
    mesures = load_burn_widths(mat or "").get("focus") if mat else None
    if not mesures:
        return None
    vitesses = sorted({float(e.get("feed", 0) or 0) for e in mesures},
                      reverse=True)
    for f in vitesses:
        if f <= 0:
            continue
        p = burn_width_range(material, f)
        if p and p[1] - p[0] > 1e-9:
            return f
    return None


def swell_refus_message(material, feed, power_max=None):
    """Pourquoi les « lignes gravées » refusent, et QUOI FAIRE. Un message
    qui dit seulement « trop vite » laisse l'utilisateur chercher la bonne
    valeur ; celui-ci la nomme."""
    # Un plafond de puissance trop bas ne laisse plus qu'un ou deux paliers
    # mesurés : la cause est alors le PLAFOND, pas la vitesse. Le dire,
    # sinon le message accuse la vitesse qui, elle, va très bien.
    if power_max is not None:
        table = burn_width_power_table(material, feed)
        if table and len([1 for s, _w in table if s <= float(power_max) + 1e-9]) < 2:
            bas = min((s for s, _w in table), default=0)
            return ("le plafond S{:.0f} est sous la plus faible puissance "
                    "mesurée (S{:.0f}) : il ne reste aucune plage où le trait "
                    "puisse enfler. Remonter le plafond."
                    .format(float(power_max), bas))
    plage = burn_width_range(material, feed)
    if plage is None:
        return ("aucune largeur brûlée mesurée pour « {} » -- passer par "
                "« Calibration du kerf » avant d'utiliser ce tramage."
                .format(material or "?"))
    rapide = swell_max_feed(material)
    if rapide is None:
        return ("sur « {} » le trait ne varie à AUCUNE vitesse mesurée : la "
                "table de largeurs est trop pauvre pour ce tramage."
                .format(material))
    return ("à F{:.0f} le trait mesure {:.2f} mm à toutes les puissances -- il "
            "n'enfle plus, ce tramage n'a plus d'objet. Descendre à "
            "F{:.0f}, la plus rapide où il enfle encore ({:.2f} à {:.2f} mm)."
            .format(feed, plage[0], rapide, *burn_width_range(material, rapide)))


def swell_power_levels(material, feed, line_min_mm, niveaux=256,
                       power_max=None):
    """Table noirceur -> S du tramage « lignes gravées ».

    SOURCE UNIQUE partagée par le générateur et l'aperçu photo. Renvoie
    (liste de `niveaux` valeurs de S, largeur_mini, largeur_maxi), ou None
    si le matériau n'a pas de table de largeurs ou si le trait n'enfle pas
    à cette vitesse.

    Indexer plutôt qu'inverser à chaque pixel : la table de largeurs se lit
    dans la config, une inversion par pixel coûterait aussi cher qu'une
    lecture de config par pixel.

    `power_max` PLAFONNE la puissance du trait le plus noir. La table ne
    connaît que la LARGEUR, jamais la PROFONDEUR : à pleine puissance sur
    hêtre à F800, le trait fait bien 0,30 mm mais il creuse, et la surface
    ressort striée (relevé à l'établi le 31/07/2026, en cours de gravure).
    Aucune mesure de l'atelier ne peut prédire ça -- d'où un plafond réglé
    à la main, et non un calcul. Plafonner rogne le haut de la plage : sur
    hêtre F800 au pas 0,30, S900 donne 0,28 mm au lieu de 0,30, soit 58
    points de contraste au lieu de 67. C'est le prix, et il est modeste."""
    table = burn_width_power_table(material, feed)
    if not table:
        return None
    if power_max is not None:
        # Le plafond retire des PALIERS MESURÉS, il n'invente pas une
        # largeur intermédiaire : on garde ce qui a été relevé au pied à
        # coulisse sous ce plafond.
        table = [(s, w) for s, w in table if s <= float(power_max) + 1e-9]
        if len(table) < 2:
            return None
    w_min_mes, w_max = table[0][1], table[-1][1]
    if w_max - w_min_mes < 1e-9:
        return None
    w_min = min(max(float(line_min_mm), w_min_mes), w_max)
    puissances = []
    i = 0
    for k in range(niveaux):
        cible = w_min + (w_max - w_min) * (k / float(niveaux - 1))
        while i < len(table) - 1 and table[i][1] < cible - 1e-9:
            i += 1
        puissances.append(int(round(table[i][0] / 5.0) * 5))
    return puissances, w_min, w_max


def swell_niveau(darkness, n, white_threshold=0.0):
    """Indice de palier d'une noirceur pour « lignes gravées », ou None si
    la case doit rester du BOIS NU.

    SOURCE UNIQUE, comme `swell_power_levels` : le générateur et l'aperçu
    photo passent tous deux par ici, sinon l'aperçu montrerait un fond
    blanc que la machine graverait quand même.

    Pourquoi ce seuil existe : le palier 0 n'est PAS « rien ». La table
    part de la puissance la plus basse réellement MESURÉE (S200 sur le
    hêtre de l'atelier), parce qu'un mode qui promet un trait continu ne
    doit pas choisir une puissance dont il ne sait rien. Conséquence, une
    case blanche pure gravait un trait de 0,10 mm -- au pas 0,30 cela fait
    **33 % du bois brûlé pour du blanc**, et l'en-tête du G-code l'annonçait
    déjà (« couverture 33 a 100 % ») sans que personne n'en fasse rien.
    Constaté sur une planche le 31/07/2026 : fond blanc sorti gris uni.

    Le mode a été conçu « jamais de bois nu », en réponse aux 27 % de
    planche vierge du portrait calibré. Mais ces trous-là étaient des
    MANQUES dans les demi-teintes ; laisser le fond blanc intact est
    l'inverse, c'est ce que « blanc » veut dire. À 0 (défaut), le
    comportement d'origine est conservé à l'identique.

    Au-dessus du seuil, la plage [seuil, 1] est REMAPPÉE sur les paliers
    [0, n-1]. Sans ça, un seuil à 8 % rendait les paliers 0 à 19
    inutilisables : la case la plus claire encore gravée sortait à
    0,116 mm au lieu de 0,10, soit 5 points de couverture gâchés et une
    partie de la plage de largeurs jamais employée. C'est aussi ce qui
    permet au fond « pointillé » de se RACCORDER exactement -- il plafonne
    à `w_min/pas`, et la branche continue repart de là. À seuil nul le
    remappage est l'identité, donc rien ne bouge."""
    d = min(1.0, max(0.0, float(darkness)))
    seuil = max(0.0, float(white_threshold))
    if seuil > 0.0 and d < seuil:
        return None
    t = (d - seuil) / (1.0 - seuil) if seuil < 1.0 else 1.0
    return max(0, min(n - 1, int(round(t * (n - 1)))))


# Matrice de Bayer 4x4, pour le fond « pointillé ». ORDONNÉE et non
# diffusion d'erreur : ce tramage n'en fait pas (un test le vérifie), une
# trame ordonnée est déterministe, ne bave pas d'une ligne sur l'autre et
# ne coûte rien par pixel.
_BAYER4 = ((0, 8, 2, 10),
           (12, 4, 14, 6),
           (3, 11, 1, 9),
           (15, 7, 13, 5))

FONDS_CLAIRS = ("nu", "pointille")


def swell_niveaux_grille(darkness_rows, n, white_threshold=0.0,
                         fond_clair="nu"):
    """Grille d'indices de palier (None = bois nu) pour « lignes gravées ».

    SOURCE UNIQUE du générateur ET de l'aperçu : le fond pointillé dépend
    de la POSITION de la case, donc il ne peut pas se décider case par case
    hors de la grille -- d'où cette fonction plutôt qu'un simple appel à
    `swell_niveau` de chaque côté.

    Deux façons de traiter ce qui passe sous le seuil de blanc :

    - `"nu"` : bois intact. Franc, mais c'est une MARCHE -- sous le seuil
      rien, au-dessus le trait apparaît d'un coup à `w_min/pas` de
      couverture (33 % sur hêtre au pas 0,30). Parfait sur un fond blanc
      franc, visible comme un contour sur un dégradé doux.
    - `"pointille"` : le trait le plus fin, mais INTERMITTENT, avec un
      rapport cyclique qui va de 0 au blanc pur à 1 juste sous le seuil.
      La couverture balaie alors continûment 0 → `w_min/pas` au lieu de
      sauter, ce qui rend la marche invisible. C'est le seul moyen de
      descendre sous le plancher du mode : la largeur ne peut pas, la
      table des largeurs s'arrêtant à la puissance la plus basse mesurée.

    À `white_threshold = 0` les deux se valent : rien ne passe sous le
    seuil, le faisceau n'est jamais coupé (comportement d'origine)."""
    seuil = max(0.0, float(white_threshold))
    pointille = (fond_clair == "pointille") and seuil > 0.0
    grille = []
    for y, row in enumerate(darkness_rows):
        ligne = []
        for x, d in enumerate(row):
            k = swell_niveau(d, n, seuil)
            if k is not None:
                ligne.append(k)
            elif pointille:
                # Rapport cyclique local, tramé par une matrice ordonnée :
                # la case est allumée au trait le PLUS FIN (palier 0) ou
                # laissée nue. La moyenne locale reproduit la noirceur.
                duty = min(1.0, max(0.0, float(d))) / seuil
                if duty > (_BAYER4[y % 4][x % 4] + 0.5) / 16.0:
                    ligne.append(0)
                else:
                    ligne.append(None)
            else:
                ligne.append(None)
        grille.append(ligne)
    return grille


def generate_gcode_photo_swell_lines(darkness_rows, pitch, z_work, feed,
                                     material, line_min_mm=0.10,
                                     pre_gcode="", post_gcode="",
                                     frame_only=False, quiet=False,
                                     white_threshold=0.0, fond_clair="nu",
                                     power_max=None):
    """Photo en LIGNES GRAVÉES : chaque ligne est balayée en continu au
    FOYER, et c'est l'ÉPAISSEUR du trait qui rend le gris -- fin dans les
    clairs, épais dans les foncés, comme une gravure sur cuivre. Aucun
    nuancier n'est consulté : la puissance de chaque pixel sort de la
    largeur brûlée MESURÉE (cf. swell_power_levels).

    `white_threshold` : sous cette noirceur, la case n'est plus gravée en
    continu. À 0 (défaut) le faisceau n'est jamais coupé, comportement
    d'origine. Au-delà, le faisceau s'éteint sur les plages claires -- mais
    le MOUVEMENT reste continu, `_emit_raster_rows` fusionnant les S0 dans
    le même balayage : la tête ne s'arrête pas, seule la lumière s'éteint.
    Cf. `swell_niveau` pour la raison (le palier 0 grave 33 % du bois au
    pas 0,30).

    `fond_clair` : ce qu'on fait de ce qui passe sous le seuil -- `"nu"`
    (bois intact, franc mais en marche) ou `"pointille"` (trait le plus fin
    en intermittence, la couverture balayant continûment 0 → w_min/pas).
    Cf. `swell_niveaux_grille`.

    Le pas doit valoir au moins la largeur maximale, sinon les traits se
    recouvrent dans les foncés et les lignes fondent en aplat -- le G-code
    le signale en commentaire. Renvoie None si grille vide, pas de table de
    largeurs, ou trait qui n'enfle plus (vitesse trop élevée)."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or pitch <= 0 or feed <= 0:
        return None
    niveaux = swell_power_levels(material, feed, line_min_mm,
                                 power_max=power_max)
    if niveaux is None:
        if not quiet:
            FreeCAD.Console.PrintWarning(
                "Lignes gravées : {}\n".format(
                    swell_refus_message(material, feed, power_max)))
        return None
    puissances, w_min, w_max = niveaux
    n = len(puissances)
    grid = [[0 if k is None else puissances[k] for k in ligne]
            for ligne in swell_niveaux_grille(darkness_rows, n,
                                              white_threshold, fond_clair)]

    z_safe = z_work + TRAVEL_CLEARANCE_MM
    lines = []
    lines.append("(G-Code Laser - Photo : lignes gravees, trait qui enfle)")
    lines.append("(Image : {} x {} px au pas {:.2f}mm, F{:.0f}, au foyer)".format(
        w, h, pitch, feed))
    lines.append("(Trait : {:.2f} a {:.2f} mm -- couverture {:.0f} a {:.0f} %)".format(
        w_min, w_max, 100.0 * w_min / pitch, 100.0 * min(1.0, w_max / pitch)))
    if power_max is not None and power_max < S_MAX - 1e-9:
        lines.append("(Puissance plafonnee a S{:.0f} ({:.0f} % de S{:.0f}) : "
                     "trait le plus noir bride pour ne pas creuser)".format(
                         float(power_max), 100.0 * float(power_max) / S_MAX,
                         S_MAX))
    # Ce plancher de couverture est la limite du mode : le trait le plus fin
    # noircit deja 33 % du bois au pas 0,30. Sans seuil, une case BLANCHE le
    # grave quand meme -- le dire dans le fichier, puisque c'est la que ca se
    # verifie.
    if white_threshold > 0.0 and fond_clair == "pointille":
        lines.append("(Seuil blanc {:.0f} % : sous cette noirceur, trait le "
                     "plus fin en POINTILLE degressif -- couverture continue "
                     "de 0 a {:.0f} %)".format(
                         100.0 * white_threshold, 100.0 * w_min / pitch))
    elif white_threshold > 0.0:
        lines.append("(Seuil blanc {:.0f} % : sous cette noirceur, bois NU "
                     "(faisceau coupe, mouvement continu))".format(
                         100.0 * white_threshold))
    elif w_min / pitch > 0.05:
        lines.append("(SANS seuil blanc : une case BLANCHE grave un trait de "
                     "{:.2f}mm, soit {:.0f} % de couverture)".format(
                         w_min, 100.0 * w_min / pitch))
    if w_max > pitch + 1e-9:
        lines.append("(ATTENTION : trait maxi {:.2f}mm > pas {:.2f}mm -- les "
                     "lignes se recouvrent dans les fonces)".format(w_max, pitch))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(0.0, w * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    _emit_raster_rows(lines, grid, pitch, z_work, z_safe, feed)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# --- Similigravure : trame AM à 45 degrés ---------------------------------
# Le gris ne vient ni de la puissance ni de la durée mais de la SURFACE d'un
# point toujours brûlé à fond. Une brûlure est une brûlure : plus besoin de
# nuancier calibré, et le seuil de brûlure du bois cesse de décider à notre
# place -- c'est exactement le défaut qui ruinait les demi-teintes des
# photos calibrées, où le fil du bois tranchait entre 10 et 30 % de noirceur.
#
# Trame à TANGENTE RATIONNELLE : la maille est portée par les vecteurs
# (k, k) et (-k, k) du réseau de pixels. En posant u = x+y et v = y-x, ces
# deux vecteurs deviennent (2k, 0) et (0, 2k) : la maille se lit en
# arithmétique entière exacte, l'angle vaut 45 degrés sans arrondi (donc
# pas de moiré), et elle compte 2k² pixels -- soit autant de niveaux de gris.
_AM_RANGS = {}


def am_screen_k(spacing_mm, pitch):
    """Ordre de maille k pour viser `spacing_mm` entre deux points, à un
    pas de trame donné. La période vaut k·√2·pas : k est donc arrondi, et
    l'espacement réellement obtenu se lit avec `am_screen_spacing`."""
    if pitch <= 0 or spacing_mm <= 0:
        return 2
    return max(2, int(round(spacing_mm / (pitch * math.sqrt(2.0)))))


def am_screen_spacing(k, pitch):
    """Espacement RÉEL entre deux points (mm) pour une maille d'ordre k."""
    return k * math.sqrt(2.0) * pitch


def am_screen_ranks(k):
    """{(u mod 2k, v mod 2k) -> rang} : ordre d'allumage des 2k² pixels
    d'une maille, du centre vers le bord.

    Le représentant de chaque classe est celui LE PLUS PROCHE DU CENTRE,
    pas le premier rencontré au balayage -- sans ça la maille n'est pas un
    pavé compact autour de son centre et les points sortent en losanges
    allongés au lieu de disques. Mémoïsé : la table ne dépend que de k."""
    table = _AM_RANGS.get(k)
    if table is not None:
        return table
    n = 2 * k * k
    proches = {}
    for y in range(-3 * k, 3 * k + 1):
        for x in range(-3 * k, 3 * k + 1):
            cle = ((x + y) % (2 * k), (y - x) % (2 * k))
            d2 = x * x + y * y
            if cle not in proches or d2 < proches[cle][0]:
                proches[cle] = (d2, x, y)
    # u et v ont toujours la même parité (u+v = 2y) : seules 2k² des 4k²
    # classes sont atteignables, ce qui est bien le compte attendu.
    if len(proches) != n:
        return {}
    ordre = sorted(proches.items(), key=lambda kv: kv[1][0])
    table = {cle: rang for rang, (cle, _p) in enumerate(ordre)}
    _AM_RANGS[k] = table
    return table


def am_halftone_screen(darkness_rows, k):
    """Grille binaire de la similigravure : True = pixel brûlé.

    Chaque maille allume ses N pixels les plus proches du centre, avec
    N = noirceur MOYENNE de la maille × 2k². La surface couverte vaut donc
    exactement la noirceur demandée -- la trame est linéaire par
    construction, sans courbe ni calibration."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    rangs = am_screen_ranks(k)
    if h < 1 or w < 1 or not rangs:
        return []
    n = 2 * k * k
    pas = 2 * k
    # Regroupement CENTRÉ sur les points du réseau, d'où le +k : les rangs
    # de `am_screen_ranks` sont classés autour du centre de maille, alors
    # qu'une simple division entière découpe des cases décalées d'une
    # demi-maille. Sans ce recentrage, le gris appliqué à un point vient
    # d'une zone voisine et non de l'endroit où le point sera brûlé --
    # l'image se décale d'une demi-maille et les points s'y étalent.
    cumul = {}
    for y in range(h):
        ligne = darkness_rows[y]
        for x in range(w):
            m = ((x + y + k) // pas, (y - x + k) // pas)
            a = cumul.get(m)
            if a is None:
                cumul[m] = [ligne[x], 1]
            else:
                a[0] += ligne[x]
                a[1] += 1
    seuils = {m: int(round(min(1.0, max(0.0, s / c)) * n))
              for m, (s, c) in cumul.items()}
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            m = ((x + y + k) // pas, (y - x + k) // pas)
            row.append(rangs[((x + y) % pas, (y - x) % pas)] < seuils.get(m, 0))
        out.append(row)
    return out


def generate_gcode_photo_am(darkness_rows, pitch, z_work, power, feed,
                            dot_spacing_mm=1.27, pre_gcode="", post_gcode="",
                            frame_only=False, quiet=False):
    """Photo en SIMILIGRAVURE : trame à 45 degrés dont le DIAMÈTRE des
    points porte le gris, comme une image de journal. Chaque point est
    brûlé à pleine puissance -- aucun nuancier n'est consulté, le gris est
    une surface, donc de la géométrie. Balayage continu (serpentin,
    faisceau allumé/éteint par pixel), même émission que la diffusion en
    lignes. À graver AU FOYER : le point doit être net, c'est lui le grain
    de la trame. Renvoie None si grille vide ou toute blanche."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or power <= 0 or feed <= 0 or pitch <= 0:
        return None
    k = am_screen_k(dot_spacing_mm, pitch)
    binaire = am_halftone_screen(darkness_rows, k)
    if not binaire:
        return None
    grid = [[int(power) if v else 0 for v in row] for row in binaire]
    if not any(any(c > 0 for c in row) for row in grid):
        return None

    z_safe = z_work + TRAVEL_CLEARANCE_MM
    lines = []
    lines.append("(G-Code Laser - Photo : similigravure, trame 45 degres)")
    lines.append("(Image : {} x {} px au pas {:.2f}mm, S{:.0f} F{:.0f})".format(
        w, h, pitch, power, feed))
    lines.append("(Trame : maille k={}, {:.2f}mm entre points, {} niveaux)".format(
        k, am_screen_spacing(k, pitch), 2 * k * k))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(0.0, w * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    _emit_raster_rows(lines, grid, pitch, z_work, z_safe, feed)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_photo_dither_lines(darkness_rows, pitch, z_work, power, feed,
                                      pre_gcode="", post_gcode="",
                                      frame_only=False, quiet=False):
    """Photo en POINTS rapides : l'image est tramée en points (diffusion
    Floyd-Steinberg, comme le tramage Diffusion) mais au lieu d'un pulse
    G4 par point (machine à l'arrêt), chaque ligne est balayée EN CONTINU
    (G64, serpentin) avec le faisceau ALLUMÉ/ÉTEINT par pixel à puissance
    FIXE -- le rendu points d'un tramage classique, à la vitesse d'un
    balayage. Point fin au foyer conseillé (z_work = foyer). Renvoie None
    si grille vide ou toute blanche."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or power <= 0 or feed <= 0:
        return None
    binary = floyd_steinberg_dither(darkness_rows)
    grid = [[int(power) if v else 0 for v in row] for row in binary]
    if not any(any(c > 0 for c in row) for row in grid):
        return None

    z_safe = z_work + TRAVEL_CLEARANCE_MM
    lines = []
    lines.append("(G-Code Laser - Photo : diffusion en lignes [points rapides])")
    lines.append("(Image : {} x {} px au pas {:.2f}mm, S{:.0f} F{:.0f})".format(
        w, h, pitch, power, feed))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(0.0, w * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    _emit_raster_rows(lines, grid, pitch, z_work, z_safe, feed)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def photo_line_power_fn(material, pitch, line_width, feed, white_threshold=0.05):
    """Fabrique la conversion noirceur (0..1) -> S du tramage « lignes
    calibrées ».

    SOURCE UNIQUE : le générateur de G-code ET l'aperçu photo passent tous
    les deux par ici. Un aperçu qui recalculerait sa propre version de
    cette conversion finirait par montrer autre chose que ce que la machine
    grave -- et il mentirait joliment, sans rien signaler.

    Renvoie (puissance, infos), ou None si le nuancier du matériau n'a pas
    2 tons en défocus exploitables. `puissance(d)` rend le S quantifié ;
    `infos` est un dict mis à jour au fil des appels :
    {"plafonnes": n} compte les pixels dont le S demandé dépassait S_MAX
    (leurs nuances s'écrasent toutes sur le même noir)."""
    curve = darkness_fluence_curve(material)
    if len(curve) < 2:
        return None
    dmin, fmin = curve[0]
    dmax, fmax = curve[-1]
    # Hissé hors de puissance() : appelée pour CHAQUE pixel, une lecture de
    # config par point rendrait la génération inutilisable.
    wpts = darkness_width_points(material)
    infos = {"plafonnes": 0}

    def puissance(d):
        t = min(max(d, 0.0), 1.0) * 100.0
        if t < white_threshold * 100.0:
            return 0
        if t <= dmin:
            fl = fmin * (t / dmin) if dmin > 0 else fmin
        elif t >= dmax:
            fl = fmax
        else:
            fl = None
            for (d0, f0), (d1, f1) in zip(curve, curve[1:]):
                if d0 <= t <= d1:
                    r = (t - d0) / (d1 - d0) if d1 > d0 else 0.5
                    fl = f0 + (f1 - f0) * r
                    break
            if fl is None:
                fl = fmax
        # Largeur MESURÉE du ton visé, jamais une largeur géométrique :
        # c'est elle qui figure au dénominateur de la fluence (cf.
        # width_for_darkness). Repli sur la géométrie si le matériau
        # n'a pas encore 2 tons exploitables.
        w = interp_width_points(wpts, t)
        s = fl * (w if w else _pas_surfacique(pitch, line_width)) * feed
        if s > S_MAX:
            infos["plafonnes"] += 1
            s = S_MAX
        return int(round(s / 5.0) * 5)      # quantifié : fusionne les segments

    return puissance, infos


def photo_line_tone_table(puissance, pas=0.002):
    """Table {S : noirceur RÉELLEMENT obtenue}, échantillonnée sur la
    fonction `puissance` elle-même -- jamais sur une formule parallèle.

    La noirceur retenue pour un S est le MILIEU de l'intervalle de
    noirceurs qui donnent ce S. Rend visibles les deux pertes du tramage
    calibré, que la noirceur demandée seule ne montre pas : le seuil blanc
    (S0 = bois nu) et le plafond S_MAX, où toutes les ombres s'écrasent sur
    la même valeur. Sert à peindre l'aperçu photo."""
    bornes = {}
    n = int(round(1.0 / max(pas, 1e-6)))
    for k in range(n + 1):
        d = min(1.0, k * pas)
        s = puissance(d)
        if s in bornes:
            bornes[s][1] = d
        else:
            bornes[s] = [d, d]
    return {s: (lo + hi) / 2.0 for s, (lo, hi) in bornes.items()}


def zdots_marks(darkness_rows, pitch, dot_min_mm, dot_max_mm,
                white_threshold=0.05):
    """Points du tramage GROS POINTS Z : [(x, y, diamètre_mm), ...] dans
    l'ordre de parcours (serpentin). Partagée par le générateur G-code ET
    l'aperçu photo, sur le modèle de `halftone_dots` -- le diamètre porte
    la noirceur, c'est donc lui que l'aperçu doit peindre."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or dot_max_mm <= dot_min_mm:
        return []
    marks = []
    for row in range(h):
        y = (h - 1 - row) * pitch
        cols = range(w) if row % 2 == 0 else range(w - 1, -1, -1)
        for col in cols:
            d = min(1.0, max(0.0, darkness_rows[row][col]))
            if d < white_threshold:
                continue
            marks.append((col * pitch, y,
                          dot_min_mm + (dot_max_mm - dot_min_mm) * d))
    return marks


def generate_gcode_photo_lines(darkness_rows, pitch, z_work, feed, line_width,
                               material, white_threshold=0.05,
                               pre_gcode="", post_gcode="", frame_only=False,
                               quiet=False):
    """Photo CALIBRÉE en lignes balayées : chaque ligne de l'image est
    parcourue en continu (serpentin), la puissance S modulée pixel par
    pixel pour viser la noirceur du pixel via la courbe noirceur->fluence
    du NUANCIER du matériau (tons mesurés, cf. darkness_fluence_curve).
    S = fluence(noirceur) · min(pas, largeur) · vitesse -- c'est le PAS qui
    gouverne l'énergie surfacique en balayage, pas la largeur du trait (cf.
    _pas_surfacique). Sous la noirceur minimale
    mesurée, la fluence est prolongée linéairement vers 0 (hautes lumières
    progressives) ; les S au-delà de S_MAX sont plafonnés (compteur en
    commentaire -- ralentir la vitesse si trop nombreux). G64 + S en ligne
    sur les G1 : mouvement fluide, pas d'arrêt entre pixels.
    line_width : largeur du trait (le défocus correspondant est à porter
    dans z_work par l'appelant). Renvoie None si grille vide, image toute
    blanche, ou nuancier insuffisant (< 2 tons en défocus)."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or line_width <= 0 or feed <= 0:
        return None
    conv = photo_line_power_fn(material, pitch, line_width, feed,
                               white_threshold)
    if conv is None:
        if not quiet:
            FreeCAD.Console.PrintWarning(
                "Photo calibrée : le nuancier « {} » n'a pas assez de tons en "
                "défocus (2 minimum) pour interpoler.\n".format(material))
        return None
    puissance, infos = conv

    # S par cellule, puis émission en serpentin par plages de S constant.
    grid = [[puissance(dv) for dv in row] for row in darkness_rows]
    if not any(any(s > 0 for s in row) for row in grid):
        return None
    clamped = [infos["plafonnes"]]

    z_safe = z_work + TRAVEL_CLEARANCE_MM
    lines = []
    lines.append("(G-Code Laser - Photo calibree : lignes, nuancier {})".format(material))
    lines.append("(Image : {} x {} px au pas {:.2f}mm, trait {:.2f}mm, F{:.0f})".format(
        w, h, pitch, line_width, feed))
    if clamped[0]:
        lines.append("(ATTENTION : {} pixel(s) plafonnes a S{:.0f} -- ralentir "
                     "la vitesse pour les rendre)".format(clamped[0], S_MAX))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(0.0, w * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    _emit_raster_rows(lines, grid, pitch, z_work, z_safe, feed)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_photo_zdots(darkness_rows, pitch, z_focus, power,
                               dot_min_mm, dot_max_mm, dwell_min_s, dwell_max_s,
                               white_threshold=0.05, pre_gcode="", post_gcode="",
                               frame_only=False, quiet=False):
    """Photo en GROS POINTS À TAILLE VARIABLE (trame artistique) : un point
    par cellule non blanche, dont le DIAMÈTRE rend la noirceur -- petit
    point net (foyer) pour les clairs, gros point défocalisé pour les
    foncés. La taille est obtenue par la HAUTEUR Z du point (cône calibré),
    le Z bougeant ENTRE les points (transits) -- jamais pendant le tir,
    donc aucune limite de vitesse Z ne s'applique. La durée d'exposition
    suit la surface du point (t ∝ d², bornée dwell_min..dwell_max) pour un
    noircissement homogène. De près : un semis de points ; de loin :
    l'image. Tir en micro-trait (compatible puissance asservie)."""
    h = len(darkness_rows)
    w = len(darkness_rows[0]) if h else 0
    if h < 1 or w < 1 or dot_max_mm <= dot_min_mm or power <= 0:
        return None
    half_angle = calibrated_half_angle()
    dots = []
    for x, y, dia in zdots_marks(darkness_rows, pitch, dot_min_mm, dot_max_mm,
                                 white_threshold):
        z = z_focus + (defocus_for_spot_diameter(dia, SPOT_FOCUS_MM, half_angle) or 0.0)
        r = (dia / dot_max_mm) ** 2
        dw = dwell_min_s + (dwell_max_s - dwell_min_s) * r
        dots.append((x, y, z, dw))
    if not dots:
        return None
    z_safe = max(z for _, _, z, _ in dots) + TRAVEL_CLEARANCE_MM
    lines = []
    lines.append("(G-Code Laser - Photo en gros points Z [taille variable])")
    lines.append("(Image : {} x {} px au pas {:.2f}mm, points {:.2f}..{:.2f}mm, S{:.0f})".format(
        w, h, pitch, dot_min_mm, dot_max_mm, power))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))
    if frame_only:
        lines.extend(build_frame_trace(0.0, w * pitch, 0.0, (h - 1) * pitch, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))
    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    sel = SPINDLE_SELECT
    # Micro-trait ORIENTÉ dans le sens de la ligne (cf. micro_trait_oriente) :
    # graver toujours vers la droite obligeait la machine à reculer avant
    # chaque point des lignes parcourues vers la gauche -- un aller-retour
    # par point, des dizaines de milliers de fois.
    seg = max(0.05, min(0.3 * pitch, 0.2))
    halfs = seg / 2.0
    first = True
    for i, (x, y, z, dw) in enumerate(dots):
        xa, xb = micro_trait_oriente(dots, i, halfs)
        lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(xa, y, z_safe if first else z))
        if first:
            lines.append("G0 Z{:.4f}".format(z))
            first = False
        f_dot = max(1.0, seg / max(dw, 1e-3) * 60.0)
        lines.extend(cmd_power_prefix(power))
        lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
            xb, y, f_dot, cmd_power_suffix(power)))
        lines.append(CMD_BEAM_OFF.format(sel=sel))
    lines.append("G0 Z{:.4f}".format(z_safe))
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_photo_sampler(pitch, z_work, dwell_min_s, dwell_max_s, power,
                                 feed, line_width, material,
                                 white_threshold=0.05, n_levels=10,
                                 patch_mm=8.0, band_h_mm=8.0, gap_mm=5.0,
                                 label_power=None, label_feed=None,
                                 dot_spacing_mm=1.27, line_min_mm=0.10,
                                 pre_gcode="", post_gcode="", frame_only=False,
                                 quiet=False):
    """MIRE COMPARATIVE des tramages photo : le même dégradé en paliers
    (n_levels patchs de patch_mm, 10%..100%) gravé par CHACUN des sept
    tramages, en bandes empilées étiquetées 1..7 :
      1 = Diffusion (points identiques)   2 = Durée variable
      3 = Lignes calibrées (nuancier)     4 = Diffusion en lignes
      5 = Gros points Z                   6 = Similigravure 45°
      7 = Lignes gravées (trait qui enfle)
    Un seul test pour comparer les styles et lire quels gris chaque tramage
    rend réellement sur le matériau.

    Chaque bande est gravée DANS SON PROPRE RÉGIME, ce qui est le seul moyen
    de comparer honnêtement : les bandes 6 et 7 au FOYER (leur grain doit
    être net, cf. les tramages correspondants), la bande 5 avec son Z par
    point, et la bande 7 à la vitesse la plus rapide où son trait enfle
    encore (`swell_max_feed`) plutôt qu'à la vitesse demandée -- au-delà,
    son trait est plat et la bande ne montrerait qu'un aplat, ou serait
    sautée. La vitesse réellement employée est écrite en tête.

    Les bandes 3 et 7 sont sautées, avec avertissement, si la donnée mesurée
    leur manque : 2 tons en défocus pour la première, une table de largeurs
    brûlées pour la seconde."""
    if label_power is None:
        label_power = LABEL_POWER
    if label_feed is None:
        label_feed = LABEL_FEED
    cols = max(2, int(round(n_levels * patch_mm / pitch)))
    rows_per = max(2, int(round(band_h_mm / pitch)))
    grid = [[(min(n_levels - 1, int(c * n_levels / cols)) + 1) / float(n_levels)
             for c in range(cols)] for _r in range(rows_per)]

    curve = darkness_fluence_curve(material) if material else []
    wpts = darkness_width_points(material) if material else []
    bands = [(0, "diffusion"), (1, "duree"), (2, "calibre"),
             (3, "dither_lignes"), (4, "zdots"), (5, "simili"), (6, "enfle")]
    band_step = band_h_mm + gap_mm
    total_h = len(bands) * band_step - gap_mm

    # Gros points Z : le diamètre porte le gris, via la hauteur du point.
    # Même repli que le panneau quand aucune largeur n'est demandée.
    dot_max = max(pitch * 0.9, SPOT_FOCUS_MM * 3)
    half_angle = calibrated_half_angle()
    # Lignes gravées : au foyer, et à la vitesse où le trait enfle encore.
    feed_enfle = swell_max_feed(material) if material else None
    if feed_enfle:
        feed_enfle = min(feed, feed_enfle)
    niveaux_enfle = (swell_power_levels(material, feed_enfle, line_min_mm)
                     if feed_enfle else None)

    # Le dégagement doit couvrir la bande la PLUS HAUTE, or les gros points Z
    # montent bien au-dessus de z_work (leur défocus fait leur diamètre) : le
    # calculer sur z_work seul ferait transiter le bec dans les points déjà
    # gravés.
    z_max = max(z_work, Z_WORK_MM)
    z_pt_max = Z_WORK_MM + (defocus_for_spot_diameter(
        dot_max, SPOT_FOCUS_MM, half_angle) or 0.0)
    z_safe = max(z_max, z_pt_max) + TRAVEL_CLEARANCE_MM

    lines = []
    lines.append("(G-Code Laser - Mire des tramages photo : degrade {}%..100%)".format(
        int(100.0 / n_levels)))
    lines.append("(1=Diffusion points  2=Duree variable  3=Lignes calibrees {}  4=Diffusion en lignes)".format(material or "-"))
    lines.append("(5=Gros points Z  6=Similigravure 45 deg  7=Lignes gravees [trait qui enfle])")
    lines.append("(Bandes 6 et 7 au foyer Z{:.2f} ; bande 7 a F{} au lieu de F{:.0f})".format(
        Z_WORK_MM, "{:.0f}".format(feed_enfle) if feed_enfle else "-", feed))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(-8.0, cols * pitch, 0.0, total_h, z_safe))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    sel = SPINDLE_SELECT

    def _emit_dots(dots, y_off):
        # Micro-traits, pas de pulse G4 : cf. generate_gcode_halftone.
        seg = max(0.05, min(0.3 * pitch, 0.2))
        half = seg / 2.0
        first = True
        for i, (x, y, dw) in enumerate(dots):
            xa, xb = micro_trait_oriente(dots, i, half)
            lines.append("G0 X{:.4f} Y{:.4f}{}".format(
                xa, y + y_off, " Z{:.4f}".format(z_work) if first else ""))
            first = False
            f_dot = max(1.0, seg / max(dw, 1e-3) * 60.0)
            lines.extend(cmd_power_prefix(power))
            lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
                xb, y + y_off, f_dot, cmd_power_suffix(power)))
            lines.append(CMD_BEAM_OFF.format(sel=sel))

    def _emit_zdots(marks, y_off):
        # Gros points Z : le Z bouge ENTRE les points (jamais pendant le
        # tir), et le micro-trait suit le sens du parcours -- exactement
        # generate_gcode_photo_zdots, dont c'est la seule copie tolérée
        # parce que la mire décale tout en Y.
        seg = max(0.05, min(0.3 * pitch, 0.2))
        half = seg / 2.0
        dots = [(x, y + y_off,
                 Z_WORK_MM + (defocus_for_spot_diameter(
                     dia, SPOT_FOCUS_MM, half_angle) or 0.0),
                 dwell_min_s + (dwell_max_s - dwell_min_s)
                 * (dia / dot_max) ** 2)
                for x, y, dia in marks]
        for i, (x, y, zz, dw) in enumerate(dots):
            xa, xb = micro_trait_oriente(dots, i, half)
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(xa, y, zz))
            f_dot = max(1.0, seg / max(dw, 1e-3) * 60.0)
            lines.extend(cmd_power_prefix(power))
            lines.append("G1 X{:.4f} Y{:.4f} F{:.0f} {}".format(
                xb, y, f_dot, cmd_power_suffix(power)))
            lines.append(CMD_BEAM_OFF.format(sel=sel))

    for b, kind in bands:
        y_off = (len(bands) - 1 - b) * band_step   # bande 1 en haut
        lines.append("(===== Bande {} : {} =====)".format(b + 1, kind))
        # Étiquette (chiffre) à gauche, gravée AU FOYER et non à z_work :
        # dans cette mire z_work est la hauteur DÉFOCALISÉE des bandes, un
        # chiffre y sortait large et baveux. Les bandes qui suivent
        # réimposent leur propre Z, le retour est donc implicite.
        for chain in chain_edges(text_to_edges(str(b + 1), -7.0,
                                               y_off + band_h_mm / 2.0 - 2.0, 4.0)):
            p0 = chain[0]
            lines.append("G0 Z{:.4f}".format(z_safe))
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(p0.x, p0.y, Z_WORK_MM))
            lines.append(CMD_BEAM_ON.format(sel=sel, power=label_power))
            for pt in chain[1:]:
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(pt.x, pt.y, label_feed))
            lines.append(CMD_BEAM_OFF.format(sel=sel))
        if kind == "diffusion":
            _emit_dots(halftone_dots(grid, pitch, dwell_max_s, dwell_max_s,
                                     mode="diffusion"), y_off)
        elif kind == "duree":
            _emit_dots(halftone_dots(grid, pitch, dwell_min_s, dwell_max_s,
                                     mode="duree", white_threshold=white_threshold), y_off)
        elif kind == "calibre":
            if len(curve) < 2:
                if not quiet:
                    FreeCAD.Console.PrintWarning(
                        "Mire : bande Lignes calibrées sautée (nuancier insuffisant).\n")
                continue
            level_s = {}
            sgrid = []
            for row in grid:
                srow = []
                for d in row:
                    if d not in level_s:
                        res = fluence_for_darkness(material, d * 100.0)
                        # Même règle que generate_gcode_photo_lines : la
                        # largeur MESURÉE du ton visé, pas une largeur
                        # géométrique (cf. width_for_darkness).
                        w = interp_width_points(wpts, d * 100.0)
                        sval = (min(S_MAX, res[0] * (w or _pas_surfacique(
                            pitch, line_width)) * feed) if res else 0)
                        level_s[d] = int(round(sval / 5.0) * 5)
                    srow.append(level_s[d])
                sgrid.append(srow)
            _emit_raster_rows(lines, sgrid, pitch, z_work, z_safe, feed, y0=y_off)
        elif kind == "dither_lignes":
            binary = floyd_steinberg_dither(grid)
            dgrid = [[int(power) if v else 0 for v in row] for row in binary]
            _emit_raster_rows(lines, dgrid, pitch, z_work, z_safe, feed, y0=y_off)
        elif kind == "zdots":
            _emit_zdots(zdots_marks(grid, pitch, SPOT_FOCUS_MM, dot_max,
                                    white_threshold), y_off)
        elif kind == "simili":
            # AU FOYER : c'est le point net qui fait le grain de la trame.
            binaire = am_halftone_screen(
                grid, am_screen_k(dot_spacing_mm, pitch))
            sgrid = [[int(power) if v else 0 for v in row] for row in binaire]
            _emit_raster_rows(lines, sgrid, pitch, Z_WORK_MM, z_safe, feed,
                              y0=y_off)
        else:                              # enfle
            if niveaux_enfle is None:
                if not quiet:
                    FreeCAD.Console.PrintWarning(
                        "Mire : bande Lignes gravées sautée -- {}\n".format(
                            swell_refus_message(material, feed)
                            if material else
                            "aucun matériau, donc aucune largeur brûlée mesurée."))
                continue
            puiss, _w_min, _w_max = niveaux_enfle
            n = len(puiss)
            sgrid = [[puiss[max(0, min(n - 1, int(round(
                min(1.0, max(0.0, d)) * (n - 1)))))] for d in row]
                for row in grid]
            # AU FOYER, et à la vitesse où le trait enfle encore.
            _emit_raster_rows(lines, sgrid, pitch, Z_WORK_MM, z_safe,
                              feed_enfle, y0=y_off)

    lines.append("G0 Z{:.4f}".format(z_safe))
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : TEST DES OFFSETS X/Y DU LASER (VALIDATION tool.tbl)
# ==========================================================================
def generate_gcode_style_sampler(power, feed, z_focus, style_params=None,
                                  line_length=40.0, band_gap=6.0,
                                  label_height=4.0, spot_width=1.5,
                                  pre_gcode="", post_gcode="", quiet=False):
    """MIRE DES STYLES du Marquage : grave le MÊME trait droit avec
    chacun des 6 styles de trait, une bande par style étiquetée de son
    chiffre (gravé net au foyer), pour comparer les rendus sur une chute
    du matériau et choisir en connaissance de cause :

        1 plein   2 tirets   3 pointillé (micro-traits)   4 vague
        5 défocus (point élargi, largeur spot_width)   6 dégradé
          (Z croissant le long du trait, largeurs deg_z_min/max de
          style_params)

    Toutes les bandes partagent power/feed ; la bande défocus N'EST PAS
    compensée en puissance (c'est le rendu brut au réglage courant que la
    mire doit montrer). style_params : mêmes clés que le Marquage
    (dash_len, gap_len, dot_spacing, dot_dwell_s, wave_period,
    wave_amplitude, deg_z_min, deg_z_max) ; deg_angle est forcé à 0 pour
    que le dégradé coure le long de sa bande. Assemblé via
    generate_gcode_combined : un seul armement pour toute la mire."""
    if line_length <= 0:
        return None
    sp = dict(style_params or {})
    sp["deg_angle"] = 0.0

    defocus = defocus_for_spot_diameter(
        spot_width, SPOT_FOCUS_MM, calibrated_half_angle()) or 0.0

    bands = [
        ("1", "plein", z_focus, sp),
        ("2", "tirets", z_focus, sp),
        ("3", "pointille", z_focus, sp),
        ("4", "vague", z_focus, sp),
        ("5", "plein", z_focus + defocus, sp),   # défocus : trait plein gravé plus haut
        ("6", "degrade", z_focus, sp),
    ]

    ops = []
    label_edges = []
    label_x = -(text_char_width(label_height) + 3.0)
    for i, (digit, style, z_eff, params) in enumerate(bands):
        y = i * band_gap
        p1 = FreeCAD.Vector(0.0, y, 0.0)
        p2 = FreeCAD.Vector(line_length, y, 0.0)
        ops.append({
            "type": "curved",
            "label": "Mire style {} ({})".format(digit, style),
            "params": dict(edges=[Part.LineSegment(p1, p2).toShape()],
                           power=power, feed=feed, z_focus=z_eff,
                           marge_survol=TRANSIT_MARGIN_MM,
                           style=style, style_params=dict(params)),
        })
        label_edges.extend(text_to_edges(digit, label_x, y - label_height / 2.0,
                                         label_height))
    if label_edges:
        ops.append({
            "type": "curved",
            "label": "Mire styles : etiquettes",
            "params": dict(edges=label_edges, power=power, feed=feed,
                           z_focus=z_focus, marge_survol=TRANSIT_MARGIN_MM),
        })

    return generate_gcode_combined(ops, pre_gcode=pre_gcode,
                                   post_gcode=post_gcode, quiet=quiet)


def _style_showcase_ops(power, feed, z_focus, sample, sp, spot_widths,
                        text_height, caption_height, row_gap, y_top):
    """Ops de marquage d'un bloc « styles » : un MOT exemple gravé dans chaque
    style, numéroté et légendé. Renvoie (ops, caption_edges, y_bas)."""
    half = calibrated_half_angle()
    # Sans amplitude, les cellules « vague » et « dégradé » seraient plates
    # (identiques au plein) : on injecte des valeurs parlantes si l'appelant
    # n'en fournit pas (ex. le catalogue).
    sp = dict(sp)
    sp.setdefault("wave_period", 5.0)
    if not sp.get("wave_amplitude"):
        sp["wave_amplitude"] = defocus_for_spot_diameter(2.0, SPOT_FOCUS_MM, half) or 0.0
    if not sp.get("deg_z_max"):
        sp.setdefault("deg_z_min", 0.0)
        sp["deg_z_max"] = defocus_for_spot_diameter(3.0, SPOT_FOCUS_MM, half) or 0.0
    cells = [
        ("plein (foyer)", "plein", 0.0),
        ("tirets", "tirets", 0.0),
        ("pointille", "pointille", 0.0),
        ("vague defocus", "vague", 0.0),
    ]
    for w in spot_widths:
        dz = defocus_for_spot_diameter(w, SPOT_FOCUS_MM, half) or 0.0
        cells.append(("point elargi {:g} mm".format(w), "plein", dz))
    cells.append(("degrade Z", "degrade", 0.0))

    ops, caps = [], []
    gap_cap, descender, y = 2.0, text_height * 0.35, y_top
    for i, (label, style, dz) in enumerate(cells):
        caps.extend(single_line_text_to_edges(
            "{}. {}".format(i + 1, label), height=caption_height, x0=0.0, y0=y))
        samp_y = y - caption_height - gap_cap - text_height
        ex = single_line_text_to_edges(sample, height=text_height, x0=0.0, y0=samp_y)
        if ex:
            ops.append({
                "type": "curved",
                "label": "Styles {} ({})".format(i + 1, style),
                "params": dict(edges=ex, power=power, feed=feed,
                               z_focus=z_focus + dz,
                               marge_survol=TRANSIT_MARGIN_MM,
                               style=style, style_params=dict(sp)),
            })
        y = samp_y - descender - row_gap
    return ops, caps, y


def generate_gcode_style_showcase(power, feed, z_focus, sample_text="Laser",
                                  text_height=8.0, spot_widths=(1.0, 2.0, 3.0),
                                  style_params=None, row_gap=7.0,
                                  caption_height=3.0, pre_gcode="",
                                  post_gcode="", quiet=False):
    """PLANCHE DES STYLES : grave un même MOT exemple dans chaque style de
    trait du Marquage, chaque exemple numéroté et légendé au foyer -- planche
    de référence à garder après calibration. Un seul job (un seul armement)."""
    sample = (sample_text or "Laser").strip() or "Laser"
    sp = dict(style_params or {})
    sp["deg_angle"] = 0.0
    ops, caps, _ = _style_showcase_ops(power, feed, z_focus, sample, sp,
                                       spot_widths, text_height, caption_height,
                                       row_gap, 0.0)
    if caps:
        ops.append({"type": "curved", "label": "Planche styles : legendes",
                    "params": dict(edges=caps, power=power, feed=feed,
                                   z_focus=z_focus, marge_survol=TRANSIT_MARGIN_MM)})
    if not ops:
        return None
    return generate_gcode_combined(ops, pre_gcode=pre_gcode,
                                   post_gcode=post_gcode, quiet=quiet)


def _catalogue_star_ops(power, feed, z_focus, r_out, cx, cy, spacing=1.0):
    """Exemple « gravure remplie » du catalogue : une étoile hachurée au
    défocus (point élargi = noir plein) + son contour net au foyer. Renvoie []
    si la géométrie Part échoue (l'exemple est alors simplement omis)."""
    try:
        half = calibrated_half_angle()
        n = 5
        pts = []
        for i in range(2 * n + 1):
            ang = math.pi / 2 + i * math.pi / n
            r = r_out if i % 2 == 0 else r_out * 0.42
            pts.append(FreeCAD.Vector(cx + r * math.cos(ang),
                                      cy + r * math.sin(ang), 0.0))
        face = Part.Face(Part.Wire(Part.makePolygon(pts)))
        defocus = defocus_for_fill_spacing(spacing, SPOT_FOCUS_MM, half) or 0.0
        fill = generate_hatch_edges([face], spacing, 45.0)
        outline = [Part.LineSegment(pts[i], pts[i + 1]).toShape()
                   for i in range(len(pts) - 1)]
        ops = []
        if fill:
            ops.append({"type": "curved", "label": "Catalogue remplie : fond",
                        "params": dict(edges=fill, power=power, feed=feed,
                                       z_focus=z_focus + defocus,
                                       marge_survol=TRANSIT_MARGIN_MM,
                                       style="plein", style_params={})})
        if outline:
            ops.append({"type": "curved", "label": "Catalogue remplie : contour",
                        "params": dict(edges=outline, power=power, feed=feed,
                                       z_focus=z_focus,
                                       marge_survol=TRANSIT_MARGIN_MM,
                                       style="plein", style_params={})})
        return ops
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "Catalogue : exemple gravure remplie ignoré ({}).\n".format(exc))
        return []


def build_catalogue_ops(power, feed, z_focus, sample_text="Laser",
                        blocks=("marquage", "remplie"),
                        style_params=None):
    """Ops (marquage) d'une PLANCHE CATALOGUE de RÉFÉRENCE : les styles de
    trait du Marquage (sur un mot exemple) + un exemple de gravure remplie,
    titrés. Sert au G-code et à l'aperçu photo."""
    sample = (sample_text or "Laser").strip() or "Laser"
    sp = dict(style_params or {})
    sp["deg_angle"] = 0.0
    ops, caps, y = [], [], 0.0
    title_h, block_gap = 5.0, 10.0

    def add_title(txt):
        caps.extend(single_line_text_to_edges(txt, height=title_h, x0=0.0, y0=y))

    if "marquage" in blocks:
        add_title("MARQUAGE - styles")
        y -= title_h + 4.0
        b_ops, b_caps, y = _style_showcase_ops(
            power, feed, z_focus, sample, sp, (1.0, 2.0, 3.0), 8.0, 3.0, 7.0, y)
        ops += b_ops
        caps += b_caps
        y -= block_gap
    if "remplie" in blocks:
        add_title("GRAVURE REMPLIE (noir plein)")
        y -= title_h + 4.0
        cy = y - 14.0
        ops += _catalogue_star_ops(power, feed, z_focus, 14.0, 14.0, cy)
        y = cy - 14.0 - block_gap
    if caps:
        ops.append({"type": "curved", "label": "Catalogue : titres/legendes",
                    "params": dict(edges=caps, power=power, feed=feed,
                                   z_focus=z_focus, marge_survol=TRANSIT_MARGIN_MM,
                                   style="plein", style_params={})})
    return ops


def generate_gcode_catalogue(power, feed, z_focus, sample_text="Laser",
                             blocks=("marquage", "remplie"),
                             style_params=None, pre_gcode="", post_gcode="",
                             quiet=False):
    """PLANCHE CATALOGUE : assemble en UN job des exemples de plusieurs modes
    de gravure (voir build_catalogue_ops). La photo tramée reste une planche
    à part (rendu raster, cf. generate_gcode_photo_sampler)."""
    ops = build_catalogue_ops(power, feed, z_focus, sample_text, blocks, style_params)
    if not ops:
        return None
    return generate_gcode_combined(ops, pre_gcode=pre_gcode,
                                   post_gcode=post_gcode, quiet=quiet)


# ---------------------------------------------------------------------------
# PLANCHES DE CALIBRATION SÉPARÉES (refonte : on scinde la planche unique en
# trois). Chacune est un seul job (un armement) et sort recadrée au zéro pièce
# à l'écriture (_write_gcode_with_dialog). Helpers communs ci-dessous.
# ---------------------------------------------------------------------------
def _powers_capped(powers):
    """Puissances bornées à S_MAX (plafond du laser actif), dédupliquées et
    triées croissant -- le balayage de puissance ne dépasse jamais l'échelle."""
    return tuple(sorted({min(float(p), float(S_MAX)) for p in powers}))


def _emit_flat_marks(lines, bands, z_safe):
    """Émet les lignes G-code pour une série de « bandes » de traits déjà à
    plat -- (chain, power, feed, comment) avec chain = liste de (x, y) --
    groupées par hauteur Z : `bands` = [(target_z, [(chain,power,feed,
    comment), ...]), ...]. Un seul plongeon/une seule remontée PAR
    CHANGEMENT de hauteur, jamais de retrait entre deux traits À LA MÊME
    hauteur -- surface de calibration TOUJOURS plate (aucun relief à
    dégager, contrairement aux modes Courbe/Découpe qui suivent une
    surface). Même principe que generate_gcode_test_grid/
    generate_gcode_defocus_calibration ; ne fait ici QUE l'émission, pas la
    géométrie (appelant : construit `bands`, ajoute son propre en-tête/
    armement avant, désarmement après). Modifie `lines` en place ; termine
    par une remontée à z_safe si quoi que ce soit a été gravé."""
    current_z = [None]

    def _travel_to(x, y, target_z):
        if current_z[0] != target_z:
            lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(x, y, z_safe))
            lines.append("G0 Z{:.4f}".format(target_z))
            current_z[0] = target_z
        else:
            lines.append("G0 X{:.4f} Y{:.4f}".format(x, y))

    last_comment = None
    for target_z, band in bands:
        for chain, power, feed, comment in band:
            if comment != last_comment:
                lines.append(comment)
                last_comment = comment
            x0, y0 = chain[0]
            _travel_to(x0, y0, target_z)
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=power))
            for x, y in chain[1:]:
                lines.append("G1 X{:.4f} Y{:.4f} F{:.0f}".format(x, y, feed))
            lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
    if current_z[0] is not None:
        lines.append("G0 Z{:.4f}".format(z_safe))


def _label_band(label_edges, comment):
    """Convertit des arêtes d'étiquettes (text_to_edges) en bande
    (chain, power, feed, comment) aux réglages Étiquettes des Préférences,
    format attendu par _emit_flat_marks (chain = liste de (x, y), le
    z de chaque point Vector étant ignoré -- la hauteur vient de la bande)."""
    if not label_edges:
        return []
    return [([(v.x, v.y) for v in chain], LABEL_POWER, LABEL_FEED, comment)
            for chain in chain_edges(label_edges)]


def generate_gcode_planche_focus(z_focus=None,
                                 powers=(200.0, 400.0, 600.0, 800.0, 1000.0),
                                 feeds=(200.0, 400.0, 800.0, 1000.0,
                                        1200.0, 1500.0, 3000.0),
                                 trait_len=20.0, row_gap=6.0, label_height=3.0,
                                 pre_gcode="", post_gcode="", quiet=False, body_only=False):
    """PLANCHE 1 -- FOYER (Vitesse x Puissance). Grille de traits gravés AU
    FOYER : une ligne par puissance S (bornée à S_MAX), une colonne par vitesse
    F. À mesurer : la LARGEUR brûlée de chaque trait (un trait vierge est une
    donnée : seuil du matériau) -> alimente burn_width_at (foyer, feed-aware).
    Un seul armement.

    Feed max ramené à 3000 (27 juil. 2026, était 6000 avant un changement de
    lentille) : F6000 ne marque plus du tout depuis -- si un futur
    changement de lentille/tête fait remarquer au-delà, remonter la plage.

    Surface TOUJOURS PLATE (calibration) : un seul plongeon/une seule
    remontée pour tout le job (cf. _emit_flat_marks) -- jamais de retrait de
    sécurité entre deux traits (tous au même Z ici), qui ferait perdre du
    temps sans réduire aucun risque (le bec ne suit aucun relief sur une
    chute plate). Même principe que generate_gcode_test_grid."""
    if z_focus is None:
        z_focus = Z_WORK_MM
    powers = _powers_capped(powers)
    x0, col_pitch = 16.0, trait_len + 12.0
    label_edges = []

    def _lab(txt, x, y, h=None):
        label_edges.extend(text_to_edges(txt, x, y, h or label_height))

    band = []
    for i, s in enumerate(powers):
        y = 4.0 + i * row_gap
        _lab("S{:.0f}".format(s), 2.0, y - label_height / 2.0)
        for j, f in enumerate(feeds):
            x = x0 + j * col_pitch
            comment = "(-- Planche 1 : S{:.0f} F{:.0f} --)".format(s, f)
            band.append(([(x, y), (x + trait_len, y)], s, f, comment))
    y_head = 4.0 + len(powers) * row_gap + 1.0
    for j, f in enumerate(feeds):
        _lab("F{:.0f}".format(f), x0 + j * col_pitch, y_head)
    _lab("1", 0.0, y_head + 6.0, 5.0)
    labels = _label_band(label_edges, "(-- Planche 1 : etiquettes --)")

    if not band and not labels:
        return None

    z_safe = z_focus + TRAVEL_CLEARANCE_MM
    lines = []
    if not body_only:
        lines.append("(G-Code Laser - Planche 1 : foyer (vitesse x puissance))")
        lines.append("(Traits : {} S x {} F, tous au foyer Z={:.4f})".format(
            len(powers), len(feeds), z_focus))
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    if not body_only:
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))

    _emit_flat_marks(lines, [(z_focus, band), (z_focus, labels)], z_safe)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_planche_defocus(z_focus=None,
                                   powers=(200.0, 400.0, 600.0, 800.0, 1000.0),
                                   feeds=(200.0, 400.0, 600.0, 800.0),
                                   defocus_levels_mm=DEFOCUS_LEVELS_MM,
                                   trait_len=20.0, row_gap=6.0, block_gap=10.0,
                                   label_height=3.0,
                                   pre_gcode="", post_gcode="", quiet=False, body_only=False):
    """PLANCHE 2 -- DÉFOCUS (balayage du feed). Pour CHAQUE niveau de défocus
    (defocus_levels_mm, ~15 et 36 mm), une grille de traits S x F gravés à
    z_focus + dz. À mesurer : la largeur brûlée de chaque trait -> alimente le
    modèle feed-aware burn_width_defocus_scaled(S, F, défocus). Un bloc étiqueté
    « d<mm> » par niveau, empilés. Un seul armement.

    feeds par défaut resserré à 200-800 (27 juil. 2026) : au DÉFOCUS
    (contrairement au foyer), F1500/F2000 ne marquent quasiment jamais --
    sur MDF, aucune mesure n'a jamais été enregistrée à ces vitesses
    malgré plusieurs planches, alors que F800 a des largeurs mesurables
    aux 5 puissances. L'ancienne plage (400-2000) gaspillait donc la
    moitié de la grille en cases blanches ; la nouvelle reste dans la
    zone qui marque, avec plus de résolution (200/600 en plus).

    Surface TOUJOURS PLATE (calibration) : un seul plongeon/une seule
    remontée PAR NIVEAU de défocus (cf. _emit_flat_marks), jamais de
    retrait entre deux traits au même niveau -- même principe que la
    Planche 1."""
    if z_focus is None:
        z_focus = Z_WORK_MM
    powers = _powers_capped(powers)
    x0, col_pitch = 16.0, trait_len + 12.0
    label_edges = []

    def _lab(txt, x, y, h=None):
        label_edges.extend(text_to_edges(txt, x, y, h or label_height))

    bands = []  # [(z_focus + dz, band), ...], un par niveau de défocus
    y = 4.0
    for dz in defocus_levels_mm:
        band = []
        for i, s in enumerate(powers):
            yy = y + i * row_gap
            _lab("S{:.0f}".format(s), 6.0, yy - label_height / 2.0)
            for j, f in enumerate(feeds):
                x = x0 + j * col_pitch
                comment = "(-- Planche 2 : d{:.0f} S{:.0f} F{:.0f} --)".format(dz, s, f)
                band.append(([(x, yy), (x + trait_len, yy)], s, f, comment))
        bands.append((z_focus + dz, band))
        y_head = y + len(powers) * row_gap + 1.0
        for j, f in enumerate(feeds):
            _lab("F{:.0f}".format(f), x0 + j * col_pitch, y_head)
        _lab("d{:.0f}".format(dz), 0.0, y_head, 5.0)
        y = y_head + block_gap
    _lab("2", 0.0, y_head + 6.0, 5.0)
    labels = _label_band(label_edges, "(-- Planche 2 : etiquettes --)")
    bands.append((z_focus, labels))

    if not any(band for _, band in bands):
        return None

    z_safe = max([z for z, _ in bands] + [z_focus]) + TRAVEL_CLEARANCE_MM
    lines = []
    if not body_only:
        lines.append("(G-Code Laser - Planche 2 : defocus (S x F par niveau))")
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        if cmd_path_blend():
            lines.append(cmd_path_blend())
        lines.append(cmd_tool_comp())
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    if not body_only:
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))

    _emit_flat_marks(lines, bands, z_safe)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    if not body_only:
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_planche_spot(z_focus=None, pre_gcode="", post_gcode="", quiet=False,
                                body_only=False):
    """PLANCHE 3 -- LARGEUR DU POINT. Reprend le noyau « Bande de calibration
    défocus » : une série de traits à hauteurs de bec croissantes (Z, du foyer
    jusqu'à ~36 mm), pour mesurer le Ø net au foyer et le Ø à une hauteur connue
    -> le modèle d'élargissement du point (spot_diameter_at_defocus). Le mode
    autonome « Bande de calibration défocus » (Préférences > Calibration du
    point) reste pour les réglages fins ; ce raccourci grave la bande avec des
    valeurs par défaut, recadré au zéro pièce comme les autres planches.

    feed par défaut abaissé à 750 (27 juil. 2026, était 1500) : à S600,
    F1500 ne marque pas du tout au-delà des tout premiers mm de défocus
    (planche entièrement blanche constatée) -- F750 laisse le temps au
    matériau de chauffer sur toute la plage de Z testée.

    Rampe de puissance 600->1000 ajoutée (27 juil. 2026) : à S600 constant,
    le dernier trait (défocus 44mm) ne marque plus assez pour être mesuré --
    la même énergie étalée sur un point large donne une fluence trop faible.
    Monter à S1000 dès le foyer saturerait/élargirait les premiers traits et
    fausserait la mesure du point net ; la rampe garde S600 au foyer (déjà
    correct) et ne monte qu'avec le défocus. draw_power_labels (par défaut)
    grave la puissance réelle de chaque trait, donc rien d'autre à changer
    pour la lire sur la planche."""
    if z_focus is None:
        z_focus = Z_WORK_MM
    return generate_gcode_defocus_calibration(
        z_start=z_focus, z_step=3.0, n_marks=13, mark_length=15.0, row_gap=6.0,
        power=600.0, power_end=1000.0, feed=750.0, plank_label="3",
        pre_gcode=pre_gcode, post_gcode=post_gcode,
        quiet=quiet, body_only=body_only)


def generate_gcode_planches_combinees(z_focus=None, pre_gcode="", post_gcode="", quiet=False,
                                      gap_mm=15.0):
    """Grave les TROIS planches de calibration (foyer, défocus, largeur du
    point) dans UN SEUL fichier -- un seul armement (M3) au début, un seul
    désarmement (M5)/fin (M2) à la fin -- au lieu de les charger une par
    une sur la machine. Planche 1 (foyer) et Planche 2 (défocus) restent
    empilées verticalement (Y croissant, X inchangé), comme avant. Planche 3
    (largeur du point) est placée à sa DROITE (X croissant, juste après la
    plus large des deux premières + `gap_mm`, alignée sur le même départ en
    Y) plutôt que de continuer la pile verticale -- elle est déjà haute (13
    traits + étiquettes) et l'allongerait inutilement. Une planche vide
    (calibration invalide) est simplement omise. Renvoie None si les trois
    sont vides."""
    if z_focus is None:
        z_focus = Z_WORK_MM
    empilees = [
        ("Planche 1 : foyer",
         generate_gcode_planche_focus(z_focus=z_focus, quiet=quiet, body_only=True)),
        ("Planche 2 : defocus",
         generate_gcode_planche_defocus(z_focus=z_focus, quiet=quiet, body_only=True)),
    ]
    empilees = [(label, c) for label, c in empilees if c]
    spot = generate_gcode_planche_spot(z_focus=z_focus, quiet=quiet, body_only=True)
    if not empilees and not spot:
        return None

    y_offset, x_max = 0.0, 0.0
    corps_decales = []
    for label, c in empilees:
        bbox = gcode_bbox_xy(c)
        dy = 0.0
        if bbox is not None:
            xmin, xmax, ymin, ymax = bbox
            dy = y_offset - ymin
            y_offset = ymax + dy + gap_mm
            x_max = max(x_max, xmax)
        corps_decales.append((label, shift_gcode_xy(c, 0.0, dy)))

    if spot:
        bbox = gcode_bbox_xy(spot)
        dx = dy = 0.0
        if bbox is not None:
            xmin, _, ymin, _ = bbox
            dx = (x_max + gap_mm - xmin) if corps_decales else 0.0
            dy = -ymin
        corps_decales.append(("Planche 3 : point", shift_gcode_xy(spot, dx, dy)))

    lines = []
    lines.append("(G-Code Laser - Planches de calibration combinees (foyer + defocus + point))")
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    if cmd_path_blend():
        lines.append(cmd_path_blend())
    lines.append(cmd_tool_comp())
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    for label, corps_c in corps_decales:
        lines.append("(===== {} =====)".format(label))
        lines.append(corps_c)
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


def generate_gcode_offset_test(mill_tool=2, mill_rpm=18000.0, mill_feed=600.0,
                               mill_depth=0.4, half_length=10.0, surface_z=0.0,
                               z_focus=7.0, laser_power=300.0, laser_feed=1000.0,
                               pre_gcode="", post_gcode="", quiet=False):
    """Job MIXTE fraise + laser pour valider les offsets X/Y de l'outil
    laser (LASER_TOOL, T100 par défaut) dans tool.tbl : fraise une croix
    centrée sur X0 Y0, puis
    grave une croix laser au MÊME X0 Y0 programmé. Si les offsets X/Y de
    du laser sont justes, les deux croix se superposent ; sinon, l'écart entre
    les deux croix EST l'erreur d'offset (au pied à coulisse, écarts
    SIGNÉS dans le sens des axes machine) :

        dX = X croix laser - X croix fraisée
        dY = Y croix laser - Y croix fraisée
        tool.tbl (outil laser) :  X_nouveau = X_actuel - dX
                         Y_nouveau = Y_actuel - dY

    puis recharger la table d'outils (QtDragon) et relancer ce test pour
    confirmer (superposition à ~0.1 mm attendue). Un écart Y d'environ
    2x l'offset (~180 mm pour un offset a 90), ou un refus soft-limit au
    moment de la croix laser, est le symptôme classique d'un SIGNE
    d'offset inversé dans tool.tbl.

    Contrairement aux autres modes de l'atelier (laser seul, prérequis
    « T<laser> M6 fait avant » + G43 en tête), ce job fait ses PROPRES
    changements d'outil : T<fraise> M6 puis T<laser> M6, chacun avec le
    palpage auto et la pause M1 du toolchange de la machine -- monter la
    glissière laser pendant la pause du second. La croix fraisée tourne
    sur la broche VFD (M3 sans sélecteur, spindle.0), la croix laser sur
    la broche laser habituelle (SPINDLE_SELECT).

    Préparation côté machine (rappelée en commentaires dans le fichier) :
    chute de bois assez grande (prévoir LARGE en Y si le signe est faux),
    zéro X/Y à l'oeil au centre de la chute, fraise à graver montée à la
    main. surface_z : Z du dessus de la chute dans le WCS courant (= son
    épaisseur si le zéro Z est sur le martyre). z_focus : hauteur de
    focale du nez laser au-dessus de la surface (cf. bande de calibration
    défocus). Lunettes laser obligatoires, surveillance permanente."""
    mill_tool = int(mill_tool)
    if mill_tool == int(LASER_TOOL):
        if not quiet:
            FreeCAD.Console.PrintWarning(
                "Test d'offsets : l'outil fraise ne peut pas être T{} (réservé au laser).\n".format(int(LASER_TOOL)))
        return None
    if half_length <= 0:
        return None

    z_laser = surface_z + z_focus
    z_hop = surface_z + 2.0        # petit saut entre les deux branches fraisées
    z_clear = surface_z + 5.0      # dégagement avant M5 / retrait broche
    plunge_feed = max(1.0, mill_feed / 2.0)

    lines = []
    lines.append("(G-Code MIXTE fraise+laser - Test des offsets X/Y du laser T{})".format(int(LASER_TOOL)))
    lines.append("(Croix fraisee T{} puis croix laser T{} au meme X0 Y0 programme)".format(mill_tool, int(LASER_TOOL)))
    lines.append("(Prerequis : zero X/Y au centre de la chute, fraise montee a la main)")
    lines.append("(Mesure : dX = X laser - X fraise ; dY = Y laser - Y fraise [signes])")
    lines.append("(Correction tool.tbl T{} : X_nouveau = X_actuel - dX ; Y_nouveau = Y_actuel - dY)".format(int(LASER_TOOL)))
    lines.append("(Ecart Y ~2x l'offset ou refus soft-limit = signe d'offset inverse)")
    lines.append("(SECURITE : lunettes laser obligatoires, surveillance permanente)")
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    # --- Étape 1 : croix FRAISÉE centrée sur X0 Y0 -----------------------
    lines.append("(===== Etape 1 : croix fraisee T{} =====)".format(mill_tool))
    lines.append("T{} M6 (palpage auto - RESUME apres le M1 du toolchange)".format(mill_tool))
    lines.append("G43 H{}".format(mill_tool))
    lines.append("M3 S{:.0f} (broche VFD)".format(mill_rpm))
    lines.append("G0 X{:.4f} Y0".format(-half_length))
    lines.append("G0 Z{:.4f}".format(z_hop))
    lines.append("G1 Z{:.4f} F{:.0f}".format(surface_z - mill_depth, plunge_feed))
    lines.append("G1 X{:.4f} F{:.0f}".format(half_length, mill_feed))
    lines.append("G0 Z{:.4f}".format(z_hop))
    lines.append("G0 X0 Y{:.4f}".format(-half_length))
    lines.append("G1 Z{:.4f} F{:.0f}".format(surface_z - mill_depth, plunge_feed))
    lines.append("G1 Y{:.4f} F{:.0f}".format(half_length, mill_feed))
    lines.append("G0 Z{:.4f}".format(z_clear))
    lines.append("M5")
    lines.append("G53 G0 Z0")

    # --- Étape 2 : croix LASER au même X0 Y0 programmé -------------------
    lines.append("(===== Etape 2 : croix laser T{} =====)".format(int(LASER_TOOL)))
    lines.append("(MSG, Monter la glissiere laser pendant la pause du changement d'outil)")
    lines.append("T{} M6 (palpage decale auto du nez laser)".format(int(LASER_TOOL)))
    lines.append("G43 H{}".format(int(LASER_TOOL)))
    lines.append("M5 {sel} (securite avant armement)".format(sel=SPINDLE_SELECT))
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    lines.append("G0 X{:.4f} Y0".format(-half_length))
    lines.append("G0 Z{:.4f}".format(z_laser))
    lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=laser_power))
    lines.append("G1 X{:.4f} F{:.0f}".format(half_length, laser_feed))
    lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
    lines.append("G0 X0 Y{:.4f}".format(-half_length))
    lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=laser_power))
    lines.append("G1 Y{:.4f} F{:.0f}".format(half_length, laser_feed))
    lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("G53 G0 Z0")

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    lines.append("(MSG, Test termine - mesurer dX dY entre les 2 croix et corriger tool.tbl T{})".format(int(LASER_TOOL)))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# Appliquée en FIN de module : les réglages listés dans _USER_SETTINGS
# surchargent des globales définies tout au long du fichier
# (SAFE_MIN_NOZZLE_HEIGHT_MM etc.), elles doivent toutes exister avant.
_apply_settings_config()
