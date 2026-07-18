# -*- coding: utf-8 -*-
"""
laser_core.py -- Atelier Laser (FreeCAD Workbench)

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
     -> corde droite sous la courbure réelle). Crée "Hachures_3D" (rouge).
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

import math
import json
import os
import unicodedata
import FreeCAD
import Part
from collections import defaultdict

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
    return "\n".join(out)

# Persistance des champs G-code avant/après entre deux exécutions de la
# macro (un run de macro FreeCAD repart de zéro à chaque fois, rien ne
# reste en mémoire Python d'une exécution à l'autre -- il faut un vrai
# fichier sur disque).
CONFIG_FILE = os.path.join(FreeCAD.getUserAppDataDir(), "laser_atelier_config.json")


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as exc:
        FreeCAD.Console.PrintWarning("Impossible de sauvegarder la config : {}\n".format(exc))

# ==========================================================================
# CONFIGURATION COMMUNE (les deux modes)
# ==========================================================================
SPINDLE_SELECT = "$1"
ARM_DWELL_S = 2.0
# Compensation d'outil laser : applique les offsets X/Y (tool.tbl) et
# le Z palpé au dernier T100 M6. Sans elle, le Z de foyer et les XY
# seraient interprétés en coordonnées broche, pas nez laser.
# PRÉREQUIS MACHINE : avoir fait T100 M6 dans la session LinuxCNC.
CMD_TOOL_COMP = "G43 H100 (compensation T100 - prerequis: T100 M6 fait dans la session)"
CMD_ARM = "S0 {sel}\nM3 {sel}\nG4 P{dwell:.1f}"
CMD_DISARM = "S0 {sel}\nM5 {sel}"
CMD_BEAM_ON = "S{power:.0f} {sel}"
CMD_BEAM_OFF = "S0 {sel}"

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
RAPID_FEED_MM_MIN = 6000.0            # vitesse rapide supposée (G0) pour l'estimation de durée
TRAVEL_CLEARANCE_MM = 10.0            # marge de survol ajoutée au Z de travail pour les
                                      # transits/début/fin de job (modes grille et découpe à
                                      # plat -- les modes courbes ont leur champ Marge de
                                      # sécurité par panneau). 0 = transits au Z de travail.
FRAME_POWER = 0.0                     # puissance (S) du faisceau pendant l'aperçu cadrage :
                                      # 0 = laser éteint (défaut), sinon TRÈS FAIBLE (S5-S20)
                                      # juste pour visualiser la zone de travail sans marquer
FRAME_FEED_MM_MIN = 1500.0            # vitesse du tracé de cadrage quand le faisceau est allumé

# (clé JSON, nom de la globale à surcharger, conversion, validation)
_USER_SETTINGS = (
    ("gcode_dir", "GCODE_DIR", str, lambda v: bool(v.strip())),
    ("spindle_select", "SPINDLE_SELECT", str, lambda v: bool(v.strip())),
    ("arm_dwell_s", "ARM_DWELL_S", float, lambda v: v >= 0),
    ("rapid_feed_mm_min", "RAPID_FEED_MM_MIN", float, lambda v: v > 0),
    ("travel_clearance_mm", "TRAVEL_CLEARANCE_MM", float, lambda v: v >= 0),
    ("frame_power", "FRAME_POWER", float, lambda v: 0 <= v <= 1000),
    ("frame_feed_mm_min", "FRAME_FEED_MM_MIN", float, lambda v: v > 0),
    ("safe_min_nozzle_height_mm", "SAFE_MIN_NOZZLE_HEIGHT_MM", float, lambda v: v >= 0),
    ("max_thickness_warning_mm", "MAX_THICKNESS_WARNING_MM", float, lambda v: v > 0),
    ("recommended_max_step_mm", "RECOMMENDED_MAX_STEP_MM", float, lambda v: v > 0),
)


def _apply_settings_config():
    """Surcharge les réglages utilisateur depuis la config JSON (clé
    "settings"). Valeur invalide : avertissement et valeur par défaut
    conservée -- même politique que le profil de bec."""
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


def current_settings():
    """Valeurs effectives des réglages utilisateur ({clé JSON: valeur}) --
    pour préremplir le panneau Préférences."""
    return {key: globals()[global_name] for key, global_name, _, _ in _USER_SETTINGS}


def save_settings(new_settings):
    """Écrit les réglages (clés JSON de _USER_SETTINGS) dans la config et
    les applique immédiatement -- pas besoin de redémarrer FreeCAD."""
    cfg = load_config()
    stored = cfg.get("settings")
    if not isinstance(stored, dict):
        stored = {}
    stored.update(new_settings)
    cfg["settings"] = stored
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
    que la surcharge manuelle documentée plus bas) et le réapplique."""
    cfg = load_config()
    cfg["nozzle"] = {"bottom_diameter_mm": bottom_diameter_mm,
                     "top_diameter_mm": top_diameter_mm,
                     "height_mm": height_mm}
    save_config(cfg)
    _apply_nozzle_config()

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
    comptage garanti sinon)."""
    all_edges = []
    for sel_obj in selection:
        obj = sel_obj.Object
        subnames = sel_obj.SubElementNames if sel_obj.HasSubObjects else []
        if subnames:
            for sub in subnames:
                shape = obj.getSubObject(sub)
                if isinstance(shape, Part.Edge):
                    all_edges.append(shape)
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
        pts = e.discretize(Distance=distance)
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


# ==========================================================================
# MODE 0a : GÉNÉRATION DE HACHURES 2D (adapté de hachure.fcmacro)
# ==========================================================================
def _plane_basis(face):
    """Repère local (U, V) d'une face plane."""
    surf = face.Surface
    normal = FreeCAD.Vector(surf.Axis).normalize()
    origin = FreeCAD.Vector(surf.Position)
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


def get_faces_from_selection_for_hatch(selection):
    """Extrait les faces planes fermées depuis la sélection (Face directe,
    Draft Shape, ou Sketch avec fils fermés -> Bullseye)."""
    faces = []
    for sel_obj in selection:
        obj = sel_obj.Object
        subnames = sel_obj.SubElementNames if sel_obj.HasSubObjects else []
        if subnames:
            for sub in subnames:
                shape = obj.getSubObject(sub)
                if isinstance(shape, Part.Face):
                    faces.append(shape)
        elif hasattr(obj, 'Shape'):
            if obj.Shape.Faces:
                faces.extend(obj.Shape.Faces)
            else:
                wires = [w for w in obj.Shape.Wires if w.isClosed()]
                if wires:
                    try:
                        made_face = Part.makeFace(wires, "Part::FaceMakerBullseye")
                        faces.extend(made_face.Faces)
                    except Exception:
                        FreeCAD.Console.PrintWarning(
                            "Impossible de créer une face à partir de : {}\n".format(obj.Label))
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


def run_hatch_generation(selection, spacing, angle, fill_type="paralleles"):
    """Crée l'objet 'Hachures_...' dans le document (vert), comme
    hachure.fcmacro, avec 3 types de remplissage possibles :
    parallèles (défaut), croisées (2 passes à angle+90), défocus
    (remplissage noir plein -- même tracé que parallèles, seul le Z de
    travail change au moment de la gravure, cf. defocus_for_fill_spacing).
    Renvoie l'objet créé, ou None en cas d'échec."""
    faces = get_faces_from_selection_for_hatch(selection)
    if not faces:
        return None, "Aucune face 2D fermée trouvée dans la sélection."

    if fill_type == "croisees":
        edges = generate_hatch_edges(faces, spacing, angle) + generate_hatch_edges(faces, spacing, angle + 90.0)
    else:
        # "paralleles" et "defocus" partagent le même tracé (hachures
        # parallèles) -- cf. commentaire ci-dessus.
        edges = generate_hatch_edges(faces, spacing, angle)

    if not edges:
        return None, "Aucune hachure générée (vérifie l'espacement ou la taille de la forme)."

    doc = FreeCAD.ActiveDocument
    hatch_compound = Part.Compound(edges)
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
    (<0.1mm, même heuristique qu'avant), "3D" sinon -- permet de
    sélectionner PLUSIEURS motifs 2D en une seule fois (ex: un ShapeString
    + des hachures, chacun avec le même corps de référence sélectionné une
    seule fois puisque la sélection FreeCAD ne garde pas les doublons) et
    de les projeter tous ensemble sur la MÊME surface, au lieu de répéter
    l'opération motif par motif. Renvoie (liste d'objets 2D, objet 3D), ou
    (None, None) si la classification est ambiguë (pas exactement une
    surface 3D dans la sélection)."""
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
        else:
            if reference is not None:
                return None, None
            reference = obj
    if reference is None or not motifs:
        return None, None
    return motifs, reference


def drop_edges_to_surface(edges_2d, shape_3d):
    """Projette chaque point des lignes 2D sur la surface 3D via la sonde
    par maillage (_MeshZProbe : tessellation une fois, puis interpolation
    barycentrique par point -- remplace l'ancien raycast booléen
    OpenCascade par point, ~5ms chacun, qui coûtait plus d'une minute sur
    un remplissage dense). L'interpolation linéaire donne un Z continu :
    pas de tracé en dents de scie, l'écart à la vraie surface est borné
    par MESH_PROBE_DEVIATION_MM."""
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
    """Crée l'objet 'Hachures_3D' dans le document (rouge), comme
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
    for obj in motif_objs:
        if hasattr(obj.Shape, 'Edges'):
            edges_2d.extend(obj.Shape.Edges)
    if not edges_2d:
        return None, "Aucune ligne trouvée dans le(s) motif(s) 2D."

    FreeCAD.Console.PrintMessage("Calcul de la projection sur le 3D (raycast Z)...\n")
    edges_3d = drop_edges_to_surface(edges_2d, obj_3d.Shape)
    if not edges_3d:
        return None, ("La projection a échoué. Vérifie que le(s) motif(s) 2D sont bien positionnés "
                       "au-dessus de l'objet 3D (dans l'axe Z).")

    doc = FreeCAD.ActiveDocument
    compound_3d = Part.Compound(edges_3d)
    new_obj = doc.addObject("Part::Feature", "Hachures_3D")
    new_obj.Shape = compound_3d
    if hasattr(new_obj, 'ViewObject'):
        new_obj.ViewObject.LineColor = (1.0, 0.0, 0.0)
        new_obj.ViewObject.LineWidth = 2.0
    doc.recompute()
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
                           fill_inset=0.0):
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

    Renvoie une liste de dicts :
    {row, col, power, feed, x0, y0, edges, border_edges}."""
    n_power = max(1, int(n_power))
    n_feed = max(1, int(n_feed))
    step = cell_size + gap

    cells = []
    for row in range(n_feed):
        feed = feed_min if n_feed == 1 else feed_min + (feed_max - feed_min) * row / float(n_feed - 1)
        for col in range(n_power):
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


def generate_gcode_test_grid(cells, z_work, label_edges=None, label_power=300.0, label_feed=1500.0,
                              cell_z_offset=0.0, use_proximity=False,
                              draw_border=False, z_border=8.5, border_power=300.0, border_feed=1000.0,
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
    for cell in sorted(cells, key=lambda c: (c["row"], c["col"])):
        comment = "(-- Cellule L{} C{} : S={:.0f} F={:.0f} --)".format(
            cell["row"], cell["col"], cell["power"], cell["feed"])
        cell_chains = [(chain, cell["power"], cell["feed"], comment)
                       for chain in chain_edges(cell["edges"])]
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
    border_band = []  # [(chain, power, feed, comment), ...] à z_border
    if draw_border:
        border_comment = "(-- Cadre net au foyer autour de chaque carré : S={:.0f} F={:.0f} Z={:.4f} --)".format(
            border_power, border_feed, z_border)
        for cell in sorted(cells, key=lambda c: (c["row"], c["col"])):
            for chain in chain_edges(cell["border_edges"]):
                border_band.append((chain, border_power, border_feed, border_comment))

    if not cell_band and not label_band and not border_band:
        return None

    all_pts = [p for item in cell_band + label_band + border_band for p in item[0]]
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
        lines.append(CMD_TOOL_COMP)
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        if all_pts:
            fx_min = min(p.x for p in all_pts)
            fx_max = max(p.x for p in all_pts)
            fy_min = min(p.y for p in all_pts)
            fy_max = max(p.y for p in all_pts)
            lines.extend(build_frame_trace(fx_min, fx_max, fy_min, fy_max, z_safe))
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

    def z_at(self, x, y):
        if not self.points:
            return None
        dists = [((px - x) ** 2 + (py - y) ** 2, pz) for px, py, pz in self.points]
        dists.sort(key=lambda t: t[0])
        nearest = dists[:self.k]
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


def split_selection(selection):
    """Sépare la sélection entre objets-sources d'edges (à graver) et
    objet de référence 3D (à sonder pour le Z). Un objet est reconnu
    comme référence s'il a de vraies Faces (ex: la sphère elle-même)."""
    edge_sel = []
    reference_shape = None
    for sel_obj in selection:
        obj = sel_obj.Object
        shape = getattr(obj, 'Shape', None)
        if shape is not None and shape.Faces:
            if reference_shape is None:
                reference_shape = shape
            else:
                FreeCAD.Console.PrintWarning(
                    "Plusieurs objets avec des faces sélectionnés -- '{}' ignoré.\n".format(obj.Label))
            continue
        edge_sel.append(sel_obj)
    return edge_sel, reference_shape


def generate_gcode_curved(edges, power, feed, z_focus, marge_survol, reference_shape=None,
                           pre_gcode="", post_gcode="", frame_only=False, quiet=False, body_only=False,
                           min_safe_z=None, probe=None):
    """frame_only : ne génère QUE le rectangle englobant (laser éteint),
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
    if not chains:
        return None

    all_pts = [p for chain in chains for p in chain]
    z_min = min(p.z for p in all_pts)
    z_max = max(p.z for p in all_pts)
    z_offset = z_focus - z_min
    z_safe_start_end = z_max + z_offset + marge_survol + 5.0
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
    lines.append("(G-Code Laser - Marquage courbe : chaînes + transit continu)")
    lines.append("(Chaînes : {} (à partir de {} segments d'origine))".format(len(chains), len(edges)))
    lines.append("(Transit : hauteur de travail + {:.2f}mm, {})".format(marge_survol, probe_kind))
    lines.append("(Contrôle bec (cône {:.0f}mm) : {})".format(
        NOZZLE_CONE_TOP_RADIUS * 2, "actif" if nozzle_check_active else "inactif (pas de sonde exacte)"))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        lines.append(CMD_TOOL_COMP)
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe_start_end))

    fx_min = min(p.x for p in all_pts)
    fx_max = max(p.x for p in all_pts)
    fy_min = min(p.y for p in all_pts)
    fy_max = max(p.y for p in all_pts)

    if frame_only:
        lines.extend(build_frame_trace(fx_min, fx_max, fy_min, fy_max, z_safe_start_end))
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

    for chain in chains:
        p0 = chain[0]

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

        lines.append("G0 Z{:.4f}".format(to_machine_z(p0.z)))

        if not state_armed:
            lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
            state_armed = True
        lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=power))

        last_check_pos = p0
        for p in chain[1:]:
            # Pendant la gravure, le Z est imposé par le focus correct :
            # un désaccord avec le bec est seulement signalé, jamais
            # corrigé (le corriger changerait le focus). Contrôlé tous les
            # NOZZLE_CHECK_INTERVAL_MM (pas à chaque point discrétisé --
            # inutile pour un cône de 16mm, et ruineux en performance sur
            # un remplissage dense).
            if nozzle_check_active and math.hypot(p.x - last_check_pos.x, p.y - last_check_pos.y) >= NOZZLE_CHECK_INTERVAL_MM:
                required = nozzle_clearance_z(p.x, p.y, p.z, height_probe.z_at, 0.0)
                if required > p.z + 0.05:
                    nozzle_marking_warnings += 1
                last_check_pos = p
            lines.append("G1 X{:.4f} Y{:.4f} Z{:.4f} F{:.0f}".format(p.x, p.y, to_machine_z(p.z), feed))

        lines.append(CMD_BEAM_OFF.format(sel=SPINDLE_SELECT))
        current_pos = chain[-1]

    lines.append("G0 Z{:.4f}".format(z_safe_start_end))

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
    key = "presets_" + category
    presets = cfg.get(key, {})
    presets[name] = values
    cfg[key] = presets
    save_config(cfg)


def delete_preset(category, name):
    """Supprime un préréglage nommé, sans erreur s'il n'existe déjà
    plus."""
    cfg = load_config()
    key = "presets_" + category
    presets = cfg.get(key, {})
    if name in presets:
        del presets[name]
        cfg[key] = presets
        save_config(cfg)


def estimate_job_time_seconds(gcode_text, rapid_feed=None):
    """Estime le temps total du job en secondes, en reparcourant le
    G-code déjà généré : G1 selon la distance/avance programmée, G0 à
    une vitesse rapide SUPPOSÉE (RAPID_FEED_MM_MIN par défaut --
    approximation, la vraie vitesse rapide machine n'est pas connue
    ici), G4 pris en compte. Approximatif : ignore
    accélérations/décélérations réelles."""
    if rapid_feed is None:
        rapid_feed = RAPID_FEED_MM_MIN
    total_seconds = 0.0
    last_x = last_y = last_z = 0.0
    current_feed = 1000.0
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
        dist = math.sqrt((x - last_x) ** 2 + (y - last_y) ** 2 + (z - last_z) ** 2)
        feed = rapid_feed if is_g0 else current_feed
        if feed > 0:
            total_seconds += (dist / feed) * 60.0
        last_x, last_y, last_z = x, y, z
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
    if clamped_passes:
        lines.append("(ATTENTION : butée de sécurité {:.1f}mm appliquée sur {} passe(s), voir Rapport)".format(
            SAFE_MIN_NOZZLE_HEIGHT_MM, len(clamped_passes)))
    if not body_only:
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        lines.append(CMD_TOOL_COMP)
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    all_pts_flat = [p for c in chains for p in c]
    fx_min = min(p.x for p in all_pts_flat)
    fx_max = max(p.x for p in all_pts_flat)
    fy_min = min(p.y for p in all_pts_flat)
    fy_max = max(p.y for p in all_pts_flat)

    if frame_only:
        lines.extend(build_frame_trace(fx_min, fx_max, fy_min, fy_max, z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only

    for chain in chains:
        p0 = chain[0]

        for pass_idx in range(n_passes):
            z_pass = pass_heights[pass_idx]
            is_last_pass = (pass_idx == n_passes - 1)
            pass_feed = finish_feed if (is_last_pass and finish_feed) else feed
            if power_end is not None and n_passes > 1:
                t = pass_idx / float(n_passes - 1)
                pass_power = power + (power_end - power) * t
            else:
                pass_power = power

            lines.append("(-- Passe {}/{} : Z={:.4f} F={:.0f} S={:.0f} --)".format(
                pass_idx + 1, n_passes, z_pass, pass_feed, pass_power))

            if pass_idx == 0:
                # Arrivée sur cette chaîne : retrait complet nécessaire
                # (on vient d'une autre chaîne, ou d'une position inconnue)
                lines.append("G0 X{:.4f} Y{:.4f} Z{:.4f}".format(p0.x, p0.y, z_safe))
                lines.append("G0 Z{:.4f}".format(z_pass))
            else:
                # Passe suivante de la MÊME chaîne, même X,Y : le kerf est
                # déjà ouvert ici (coupé par la passe précédente) -- pas
                # besoin de remonter, juste ajuster le Z directement.
                lines.append("G0 Z{:.4f}".format(z_pass))

            if not state_armed:
                lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
                state_armed = True
            lines.append(CMD_BEAM_ON.format(sel=SPINDLE_SELECT, power=pass_power))

            for p in chain[1:]:
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
                               min_safe_z=None, probe=None):
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
        lines.append(CMD_TOOL_COMP)
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    fx_min = min(p.x for p in all_pts)
    fx_max = max(p.x for p in all_pts)
    fy_min = min(p.y for p in all_pts)
    fy_max = max(p.y for p in all_pts)

    if frame_only:
        lines.extend(build_frame_trace(fx_min, fx_max, fy_min, fy_max, z_safe))
        if not body_only:
            lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
            lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    state_armed = body_only
    nozzle_cut_warnings = 0

    for chain in chains:
        p0 = chain[0]

        for pass_idx in range(n_passes):
            is_last_pass = (pass_idx == n_passes - 1)
            pass_feed = finish_feed if (is_last_pass and finish_feed) else feed
            if power_end is not None and n_passes > 1:
                t = pass_idx / float(n_passes - 1)
                pass_power = power + (power_end - power) * t
            else:
                pass_power = power

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
            for p in chain[1:]:
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

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : BANDE DE CALIBRATION DÉFOCUS
# ==========================================================================
def generate_gcode_defocus_calibration(z_start, z_step, n_marks, mark_length, row_gap,
                                       power, feed, power_end=None, draw_labels=True,
                                       draw_power_labels=True,
                                       label_power=300.0, label_feed=1500.0, label_z=None,
                                       pre_gcode="", post_gcode="", frame_only=False, quiet=False):
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
    lisibles quel que soit le défocus du trait qu'elles désignent.

    power / power_end : puissance du 1er trait, et du dernier. Plus le trait
    est défocalisé, plus la MÊME puissance est étalée sur un gros point,
    donc plus le trait est pâle -- jusqu'à disparaître. Une RAMPE
    (power_end > power) monte progressivement la puissance avec la hauteur
    pour que même les traits très défocalisés marquent, et restent
    mesurables. power_end=None -> puissance constante.

    Le transit entre traits se fait DIRECTEMENT à la hauteur du trait
    suivant (laser éteint, pièce plate) -- pas de remontée au Z de sécurité
    entre chaque trait (inutile à plat, et lente).

    frame_only : ne trace que le rectangle englobant (cadrage séparé)."""
    n_marks = max(1, int(n_marks))
    def _mark_power(k):
        if power_end is None or n_marks < 2:
            return power
        return power + (power_end - power) * (k / float(n_marks - 1))
    if label_z is None:
        label_z = z_start
    label_height = max(2.0, min(row_gap * 0.45, 5.0))

    marks = []  # (chain, z)
    for k in range(n_marks):
        z = z_start + k * z_step
        y = k * row_gap
        marks.append(([FreeCAD.Vector(0.0, y, 0.0), FreeCAD.Vector(mark_length, y, 0.0)], z))

    label_chains = []
    for k, (_, z) in enumerate(marks):
        y = k * row_gap
        if draw_labels:
            # Hauteur à GAUCHE. Décimale seulement si nécessaire : pas
            # entiers -> "2","4" ; pas fractionnaires -> "0.5","1.5" (point
            # décimal géré par la police).
            text = "{:g}".format(round(z, 1))
            w = text_width(text, label_height)
            edges = text_to_edges(text, -(w + row_gap * 0.4), y - label_height / 2.0, label_height)
            label_chains.extend(chain_edges(edges))
        if draw_power_labels:
            # Puissance à DROITE du trait (utile avec la rampe : sinon on ne
            # sait pas quelle puissance a donné quel trait).
            ptext = "S{:.0f}".format(_mark_power(k))
            edges = text_to_edges(ptext, mark_length + row_gap * 0.4, y - label_height / 2.0, label_height)
            label_chains.extend(chain_edges(edges))

    all_pts = [p for chain, _ in marks for p in chain] + [p for chain in label_chains for p in chain]
    z_safe = max([z for _, z in marks] + [label_z]) + TRAVEL_CLEARANCE_MM

    lines = []
    lines.append("(G-Code Laser - Bande de calibration defocus)")
    if power_end is None:
        p_desc = "S{:.0f}".format(power)
    else:
        p_desc = "S{:.0f}->{:.0f} (rampe)".format(power, power_end)
    lines.append("(Traits : {} de Z={:.2f} a Z={:.2f} par pas de {:.2f}, {} F{:.0f})".format(
        n_marks, z_start, z_start + (n_marks - 1) * z_step, z_step, p_desc, feed))
    lines.append("(Mesurer l'epaisseur de chaque trait : le plus fin = foyer)")
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    lines.append(CMD_TOOL_COMP)
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    lines.append("G0 Z{:.4f}".format(z_safe))

    if frame_only:
        lines.extend(build_frame_trace(
            min(p.x for p in all_pts), max(p.x for p in all_pts),
            min(p.y for p in all_pts), max(p.y for p in all_pts), z_safe))
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

    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    lines.append("(===== Traits de calibration =====)")
    for k, (chain, z) in enumerate(marks):
        _emit(chain, _mark_power(k), feed, z)
    if label_chains:
        lines.append("(===== Etiquettes (hauteur en mm) =====)")
        for chain in label_chains:
            _emit(chain, label_power, label_feed, label_z)

    if started[0]:
        lines.append("G0 Z{:.4f}".format(z_safe))
    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())
    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")
    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# ==========================================================================
# MODE : GRAVURE REMPLIE (NOIR) -- remplissage défocus + contour au foyer
# ==========================================================================
def build_filled_engraving_edges(faces, spacing, angle_deg, fill_inset=0.0):
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

    L'appelant calcule fill_inset = rayon du point au défocus retenu
    (spot_diameter_at_defocus / 2)."""
    contour_edges = []
    fill_faces = []
    for f in faces:
        contour_edges.extend(f.Edges)
        if fill_inset > 0:
            try:
                inset = f.makeOffset2D(-fill_inset)
                sub = list(inset.Faces)
            except Exception:
                sub = []
            fill_faces.extend(sub)  # vide si trop fin -> pas de remplissage ici
        else:
            fill_faces.append(f)
    fill_edges = generate_hatch_edges(fill_faces, spacing, angle_deg) if fill_faces else []
    return fill_edges, contour_edges


def generate_gcode_filled_engraving(fill_edges, contour_edges, z_focus, defocus,
                                     fill_power, fill_feed,
                                     draw_contour=True, contour_power=300.0, contour_feed=1000.0,
                                     contour_z_offset=0.0, marge_survol=5.0,
                                     pre_gcode="", post_gcode="", frame_only=False, quiet=False):
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

    frame_only : ne trace que le rectangle englobant (cadrage séparé)."""
    z_fill = z_focus + defocus
    z_contour = z_focus + contour_z_offset

    has_contour = bool(draw_contour and contour_edges)
    # Hauteur de sécurité commune (marquage à plat : Z natif = 0, donc
    # z_safe = niveau de travail + marge + 5, cf. generate_gcode_curved).
    safe_levels = [z_fill] + ([z_contour] if has_contour else [])
    global_min_safe_z = max(safe_levels) + marge_survol + 5.0

    if frame_only:
        all_edges = list(fill_edges or []) + (list(contour_edges) if has_contour else [])
        chains = chain_edges(all_edges)
        if not chains:
            return None
        pts = [p for c in chains for p in c]
        lines = ["(G-Code Laser - Gravure remplie : cadrage)"]
        lines.append("G21")
        lines.append("G90")
        lines.append("G94")
        lines.append(CMD_TOOL_COMP)
        lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
        lines.append("G0 Z{:.4f}".format(global_min_safe_z))
        lines.extend(build_frame_trace(
            min(p.x for p in pts), max(p.x for p in pts),
            min(p.y for p in pts), max(p.y for p in pts), global_min_safe_z))
        lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
        lines.append("M2")
        return sanitize_gcode_for_linuxcnc("\n".join(lines))

    # Corps : remplissage d'abord, contour ensuite (repassé propre).
    bodies = []
    fill_body = generate_gcode_curved(
        fill_edges, fill_power, fill_feed, z_fill, marge_survol,
        reference_shape=None, body_only=True, quiet=quiet, min_safe_z=global_min_safe_z)
    if fill_body:
        bodies.append(("Remplissage defocus", fill_body))
    if has_contour:
        contour_body = generate_gcode_curved(
            contour_edges, contour_power, contour_feed, z_contour, marge_survol,
            reference_shape=None, body_only=True, quiet=quiet, min_safe_z=global_min_safe_z)
        if contour_body:
            bodies.append(("Contour", contour_body))
    if not bodies:
        return None

    lines = []
    lines.append("(G-Code Laser - Gravure remplie noir)")
    lines.append("(Remplissage Z={:.4f} defocus={:.4f} S{:.0f} F{:.0f})".format(
        z_fill, defocus, fill_power, fill_feed))
    if any(label == "Contour" for label, _ in bodies):
        lines.append("(Contour Z={:.4f} S{:.0f} F{:.0f})".format(z_contour, contour_power, contour_feed))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    lines.append(CMD_TOOL_COMP)
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))
    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())
    lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))
    for label, body in bodies:
        lines.append("(===== {} =====)".format(label))
        lines.append(body)
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
        return z_max + z_offset + params.get("marge_survol", 0.0) + 5.0
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
        z_cells = z_work + params.get("cell_z_offset", 0.0)
        return max(z_work, z_cells) + TRAVEL_CLEARANCE_MM
    return None


def generate_gcode_combined(operations, pre_gcode="", post_gcode="", frame_only=False, quiet=False):
    """Assemble plusieurs opérations (Marquage courbe / Découpe
    multi-passes / Grille de test, chacune avec ses propres paramètres)
    en UN SEUL job avec UN SEUL armement (M3) au tout début et UN SEUL
    désarmement (M5)/fin de programme (M2) à la toute fin -- au lieu
    d'un cycle armement/désarmement par opération, pour des transitions
    plus rapides entre opérations (le laser reste réputé prêt à tirer
    tout du long, cf. CMD_BEAM_ON/CMD_BEAM_OFF qui continuent de gérer
    la puissance réelle indépendamment de cet armement).

    frame_only : ne génère QUE les rectangles englobants de chaque
    opération (laser jamais armé), pour un fichier de vérification de
    cadrage séparé -- mêmes garanties que sur les modes simples.

    Une opération dont le générateur renvoie None (aucune géométrie,
    ex: sélection vide) est ignorée avec un avertissement (sauf si
    quiet)."""
    if not operations:
        return None

    dispatch = {
        "curved": generate_gcode_curved,
        "curved_cut": generate_gcode_curved_cut,
        "flat": generate_gcode_flat_multipass,
        "testgrid": generate_gcode_test_grid,
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
        gcode = generator(**params)
        if not gcode:
            if not quiet:
                FreeCAD.Console.PrintWarning(
                    "Opération '{}' ignorée dans le job combiné (aucune géométrie générée).\n".format(label))
            continue
        bodies.append((label, gcode))

    if not bodies:
        return None

    lines = []
    lines.append("(G-Code Laser - Job combiné : {} operation(s))".format(len(bodies)))
    for label, _ in bodies:
        lines.append("(  - {})".format(label))
    lines.append("G21")
    lines.append("G90")
    lines.append("G94")
    lines.append("M5 {sel}".format(sel=SPINDLE_SELECT))

    if pre_gcode.strip():
        lines.append("(-- G-code personnalisé (avant) --)")
        lines.append(pre_gcode.strip())

    if not frame_only:
        lines.append(CMD_ARM.format(sel=SPINDLE_SELECT, dwell=ARM_DWELL_S))

    for label, gcode in bodies:
        lines.append("(===== Operation : {} =====)".format(label))
        lines.append(gcode)

    if post_gcode.strip():
        lines.append("(-- G-code personnalisé (après) --)")
        lines.append(post_gcode.strip())

    lines.append(CMD_DISARM.format(sel=SPINDLE_SELECT))
    lines.append("M2")

    return sanitize_gcode_for_linuxcnc("\n".join(lines))


# Appliquée en FIN de module : les réglages listés dans _USER_SETTINGS
# surchargent des globales définies tout au long du fichier
# (SAFE_MIN_NOZZLE_HEIGHT_MM etc.), elles doivent toutes exister avant.
_apply_settings_config()
