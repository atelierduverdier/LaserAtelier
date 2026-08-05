# -*- coding: utf-8 -*-
"""Les pièges que ce dépôt a DÉJÀ payés, balayés sur tout le code.

Christophe, 05/08/2026 : « on arrive bientôt à la v3, j'aimerais bien
maintenant corriger des bugs pour avoir une v3 stable comme les pros ».

La meilleure piste n'est pas de chercher au hasard. Chaque règle de
`.claude/rules/` raconte un défaut qui a coûté une planche, une heure ou un
document -- et plusieurs annoncent « corrigé sur les N sites ». Or le 5 août
un neuvième site de `hasattr(ViewObject)` dormait dans les hachures, et deux
autres dans la planche d'ajustement, alors que la règle disait huit. UN
BALAYAGE FAIT UNE FOIS N'EST PAS UNE PROPRIÉTÉ : il faut le rejouer à chaque
exécution, sinon le piège revient par la porte de derrière.

Ce fichier ne teste donc pas un comportement mais une ABSENCE, sur
l'ensemble des sources. Toute nouvelle famille de défaut trouvée à
l'établi a vocation à venir ici.
"""
import os
import re

from harness import preparer

h = preparer()
core = h.core
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = ("laser_core.py", "task_panels.py", "commands.py", "InitGui.py",
           "svg_import.py", "laser_jobs.py", "calligraphie.py")


def _lire(nom):
    with open(os.path.join(RACINE, nom), encoding="utf-8") as f:
        return f.read()


# --- 1. hasattr SUR ViewObject : VRAI ET INUTILE EN HEADLESS -------------
# L'attribut EXISTE et vaut None hors interface, donc la ligne suivante meurt
# sur `None.LineColor`. La règle des panneaux annonçait « corrigé aux 8
# sites » ; il en restait trois le 05/08/2026 (hachures, découpe et gravure
# de la planche d'ajustement). C'est ce mensonge-là que ce contrôle empêche.
_coupables = []
for _nom in SOURCES:
    for _n, _l in enumerate(_lire(_nom).splitlines(), 1):
        if re.search(r"hasattr\([^,]+,\s*['\"]ViewObject['\"]\)", _l):
            _coupables.append("{}:{}".format(_nom, _n))
assert not _coupables, (
    "hasattr sur ViewObject : VRAI et INUTILE en headless -- l'attribut "
    "existe et vaut None, et la ligne suivante meurt dessus. Utiliser "
    "getattr(obj, 'ViewObject', None) is not None", _coupables)
print("1. aucun hasattr sur ViewObject dans les {} sources OK".format(
    len(SOURCES)))


# --- 2. AUCUN G4 AVEC LE FAISCEAU ALLUMÉ (non-négociable n°4) -----------
# Le HAL ramène la puissance à zéro à l'arrêt : un point fait au dwell ne
# grave RIEN et le job sort blanc, sans un mot. Tout point est un
# micro-trait. Seul l'armement -- faisceau à zéro -- a le droit au dwell.
# ON NE VISE QUE LES ÉMISSIONS. `estimate_job_time_seconds` LIT les G4 pour
# compter le temps d'attente : un balayage qui l'attrape crie au loup et
# finit par être désarmé, ce qui est pire que pas de contrôle du tout.
_LECTURE = ("startswith", "endswith", "==", "in line", "split", "strip")
_g4 = []
for _nom in SOURCES:
    for _n, _l in enumerate(_lire(_nom).splitlines(), 1):
        if not re.search(r"""["']G4\b""", _l):
            continue
        if any(_m in _l for _m in _LECTURE):
            continue                       # on lit du G-code, on n'en écrit pas
        if "ARM" in _l or "dwell=" in _l:
            continue                       # l'armement, faisceau à zéro
        _g4.append("{}:{}  {}".format(_nom, _n, _l.strip()[:60]))
assert not _g4, (
    "un G4 est émis hors de l'armement : si le faisceau est allumé, il ne "
    "grave RIEN et le job sort blanc sans un mot", _g4)
print("2. aucun G4 hors armement OK")


# --- 3. TOUT GÉNÉRATEUR ASSAINIT SA SORTIE -----------------------------
# Un commentaire NON FERMÉ fait refuser le programme entier au chargement
# (« Unclosed comment found ») : le job ne démarre jamais. Le sanitizer est
# le filet, et il doit être au bout de CHAQUE générateur -- en oublier un ne
# se voit qu'à la machine, devant une planche montée.
_src_core = _lire("laser_core.py")
_gens = re.findall(r"^def (generate_gcode_\w+)\(", _src_core, re.M)
assert len(_gens) >= 20, ("trop peu de générateurs trouvés : le balayage "
                          "vise à côté", len(_gens))
_sans_filet = []
for _g in _gens:
    _i = _src_core.index("def {}(".format(_g))
    _j = _src_core.find("\ndef ", _i + 5)
    _corps = _src_core[_i:_j if _j > 0 else len(_src_core)]
    _rendus = [_r for _r in re.findall(r"return ([^\n]+)", _corps)
               if '"\\n".join' in _r or ("lines" in _r and "join" in _r)]
    for _r in _rendus:
        if "sanitize_gcode_for_linuxcnc" not in _r:
            _sans_filet.append("{} -> {}".format(_g, _r.strip()[:60]))
assert not _sans_filet, (
    "un générateur rend son G-code SANS l'assainir : un commentaire non "
    "fermé ou un accent feront refuser le programme au chargement",
    _sans_filet)
print("3. les {} générateurs assainissent leur sortie OK".format(len(_gens)))


# --- 4. LE CONTRÔLE DES COULEURS EN DUR : ÉCRIT, MESURÉ, PUIS JETÉ -----
# Il devait interdire toute couleur posée en dur, après le vert des hachures
# qui se confondait avec celui du marquage. Deux mesures l'ont condamné :
#
#   * il attrape DIX couleurs parfaitement légitimes -- le magenta des
#     marqueurs de collision, le brun d'encre des textes posés, des gris de
#     repère -- dont aucune ne participe au langage des calques ;
#   * et il N'AURAIT PAS ATTRAPÉ LE VRAI CAS : l'ancien vert (0.0, 0.8, 0.0)
#     est à 0,85 du vert du marquage en distance RVB, plus loin que tout
#     seuil qu'on aurait osé poser. La collision était PERCEPTUELLE, pas
#     numérique.
#
# Un chiffre qui ne sépare pas ce qu'il prétend séparer rassure à tort et
# finit par être désarmé -- la leçon du détecteur de fût contourné (27 %
# contre 28 %). On préfère ne rien mettre, et le dire.
print("4. (contrôle des couleurs en dur écarté : mesuré incapable de "
      "séparer -- cf. le commentaire)")


# --- 5. UN ENREGISTREMENT NE DOIT PAS SUPPRIMER CE QU'IL NE SAIT PAS LIRE
# `save_shades` REMPLACE la liste du matériau : tout ce que le panneau ne
# rend pas est effacé. Or le Nuancier jetait une ligne dont un nombre était
# illisible -- une cellule blanchie par mégarde sur un ton MESURÉ AU PIED À
# COULISSE -- avec un simple avertissement console. Et le message de succès
# annonçait `rowCount()`, donc il pouvait se féliciter d'un enregistrement
# complet juste après en avoir perdu trois.
#
# C'est la règle de la v2.4.0 (« ② ne doit jamais effacer ce qu'il ne sait
# pas AFFICHER ») appliquée à ce qu'il ne sait pas LIRE.
from harness import sans_dialogues                             # noqa: E402
import task_panels as tp                                       # noqa: E402

sans_dialogues()
_p5 = tp.TaskPanelNuancier()
_p5.combo_mat.setEditText("EssaiPieges")
_p5.table.setRowCount(0)


def _poser(r, valeurs):
    _p5.table.insertRow(r)
    for _c, _v in enumerate(valeurs):
        _p5.table.setItem(r, _c, tp.QtWidgets.QTableWidgetItem(_v))


_poser(0, ["50", "800", "1000", "15", "0.8", "bon"])
_poser(1, ["60", "900", "1000", "15", "0.9", "bon aussi"])
_tons, _mauvaises = _p5._table_shades()
assert len(_tons) == 2 and not _mauvaises, ("table saine mal relue",
                                            len(_tons), _mauvaises)

# On blanchit UNE cellule, comme un doigt qui glisse sur un ton mesuré.
_p5.table.setItem(1, 2, tp.QtWidgets.QTableWidgetItem(""))
_tons, _mauvaises = _p5._table_shades()
assert _mauvaises == [2], ("la ligne illisible n'est pas signalée", _mauvaises)

# ET L'ENREGISTREMENT DOIT REFUSER, sans rien écrire.
_ecrits = []
_vrai_save = core.save_shades
try:
    core.save_shades = lambda m, s: _ecrits.append((m, list(s)))
    _ok = _p5.accept()
finally:
    core.save_shades = _vrai_save
assert _ok is False, ("le panneau accepte alors qu'une ligne est illisible : "
                      "le ton mesuré serait effacé")
assert not _ecrits, ("il a écrit malgré la ligne illisible", _ecrits)

# Corrigée, elle repasse -- sinon le refus serait un blocage, pas un garde.
_p5.table.setItem(1, 2, tp.QtWidgets.QTableWidgetItem("1000"))
try:
    core.save_shades = lambda m, s: _ecrits.append((m, list(s)))
    _ok = _p5.accept()
finally:
    core.save_shades = _vrai_save
assert _ok is True and len(_ecrits) == 1 and len(_ecrits[0][1]) == 2, (
    "une table saine devrait s'enregistrer", _ok, _ecrits)
print("5. le Nuancier refuse d'enregistrer une table qu'il ne sait pas "
      "relire, au lieu d'en effacer les tons OK")


# --- 6. UN RÉGLAGE TROUVÉ À L'ŒIL NE DOIT PAS SE PERDRE À LA FERMETURE ---
# La Calligraphie a perdu six réglages de plume pendant des semaines, le
# Marquage cinq champs de dégradé, puis deux du « ton sur mesure ». Chacun
# est une valeur cherchée à l'œil sur du bois, effacée par un clic sur la
# croix. Le balayage compare donc, panneau par panneau, les widgets de
# RÉGLAGE créés et ce que `_last_fields` mémorise.
#
# CHAQUE EXCLUSION EST NOMMÉE ET JUSTIFIÉE. Une liste d'exceptions muette
# finirait par tout absoudre -- et c'est exactement comme ça qu'un réglage
# se reperd.
_EXCLUS = {
    # Sélecteurs, pas des réglages : ils agissent puis se remettent au neutre.
    "combo_preset": "sélecteur de préréglages",
    "combo_police": "sélecteur qui remplit edt_police, lui mémorisé",
    "combo_recipe": "sélecteur d'objectif : le rejouer réappliquerait sa recette",
    # Persistés AILLEURS, et c'est le bon endroit.
    "chk_origin_bbox": "écrit dans save_settings au clic (réglage machine)",
    "spn_spot_dtest": "PER_LASER_KEYS, via save_settings",
    "spn_spot_focus": "PER_LASER_KEYS, via save_settings",
    "spn_spot_ztest": "PER_LASER_KEYS, via save_settings",
    "edt_measure_mat": "deuxième vue du matériau de ①, synchronisée",
    # Mesures et aides, pas des consignes.
    "spn_measured": "mesure au pied à coulisse, à refaire à chaque planche",
    "spn_dx": "résultat mesuré de la planche d'offset",
    "spn_dy": "résultat mesuré de la planche d'offset",
    "edt_mot": "loupe d'aperçu de la Calligraphie, pas un réglage gravé",
    # DÉLIBÉRÉMENT oublié : une hauteur défocalisée laissée derrière
    # empoisonne en silence tous les jobs suivants (défaut observé).
    "spn_cell_defocus": "remis au Z de travail à chaque objectif, exprès",
}
_src_tp = _lire("task_panels.py")
_classes = [(_m.start(), _m.group(1))
            for _m in re.finditer(r"^class (TaskPanel\w+)", _src_tp, re.M)]
_classes.append((len(_src_tp), "FIN"))
_perdus = []
for (_a, _nomp), (_b, _x) in zip(_classes, _classes[1:]):
    _bloc = _src_tp[_a:_b]
    _m = re.search(r"self\._last_fields\s*=\s*\{", _bloc)
    if not _m:
        continue
    _i = _m.end() - 1
    _prof, _j = 0, _i
    while _j < len(_bloc):
        if _bloc[_j] == "{":
            _prof += 1
        elif _bloc[_j] == "}":
            _prof -= 1
            if _prof == 0:
                break
        _j += 1
    _memo = set(re.findall(r"self\.(\w+)", _bloc[_i:_j]))
    _crees = set(re.findall(
        r"self\.(spn_\w+|combo_\w+|chk_\w+|edt_\w+)\s*=\s*QtWidgets\.", _bloc))
    for _w in sorted(_crees - _memo):
        if _w not in _EXCLUS:
            _perdus.append("{}.{}".format(_nomp, _w))
assert not _perdus, (
    "des réglages ne sont pas mémorisés et se perdront à la fermeture du "
    "panneau : les ajouter à _last_fields, ou les inscrire dans _EXCLUS "
    "avec la raison", _perdus)
print("6. tous les réglages des panneaux sont mémorisés ({} exclusions, "
      "chacune justifiée) OK".format(len(_EXCLUS)))


# --- 7. UN MODE PLAN DOIT REFUSER UNE FORME GALBÉE ----------------------
# Christophe, 05/08/2026 : un texte PROJETÉ sur une surface courbe, puis
# passé en Gravure remplie -- « l'aplat couleur n'a pas bien fonctionné,
# juste le point du i et l'intérieur du e sont colorés ».
#
# Ce n'était pas l'aperçu : `_faces_from_any_shape` est le MÊME constructeur
# que la Gravure remplie utilise pour savoir quoi hachurer, et il ne
# travaille qu'en 2D. Mesuré sur son document -- 1652 arêtes, 4 faces,
# 4,63 mm² -- et reproduit sur un cylindre de 60 mm : à plat 8 faces et
# 217,5 mm², projeté 2 faces et 0,0 mm². Le G-code serait sorti quasi
# blanc, sans un mot.
import FreeCAD                                                 # noqa: E402
import Part                                                    # noqa: E402

_d7 = FreeCAD.newDocument("EssaiPlan")
try:
    # Un carré bien plat, puis le même galbé de 0,3 mm -- l'ordre de grandeur
    # mesuré sur son cylindre.
    _plat = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0),
                              FreeCAD.Vector(20, 20, 0), FreeCAD.Vector(0, 20, 0),
                              FreeCAD.Vector(0, 0, 0)])
    assert core.ecart_au_plan(_plat) < 1e-6, (
        "un carré plat est vu comme galbé", core.ecart_au_plan(_plat))
    assert core.forme_est_plane(_plat)

    _galbe = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0),
                               FreeCAD.Vector(20, 20, 0.3),
                               FreeCAD.Vector(0, 20, 0), FreeCAD.Vector(0, 0, 0)])
    _e7 = core.ecart_au_plan(_galbe)
    assert 0.1 < _e7 < 0.5, ("le creux mesuré ne ressemble pas à celui d'une "
                             "projection", _e7)
    assert not core.forme_est_plane(_galbe), (
        "un creux de {:.2f} mm passe pour plan : c'est exactement le cas qui "
        "a vidé sa gravure".format(_e7))

    # LE SEUIL SE DÉDUIT DE LA FLÈCHE DE POLYGONISATION, il ne s'invente pas.
    assert abs(core.ECART_PLAN_MAXI_MM - 0.04) < 1e-9, (
        "le seuil de planéité a changé : il vaut deux fois la flèche de "
        "re-polygonisation (0,02 mm), en dessous de laquelle le constructeur "
        "de faces ne distingue plus rien", core.ECART_PLAN_MAXI_MM)

    # ET LE CAS DÉGÉNÉRÉ NE DOIT PAS CRIER AU LOUP : une forme alignée n'a
    # pas de plan à contredire.
    _ligne = Part.makePolygon([FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0),
                               FreeCAD.Vector(20, 0, 0)])
    assert core.forme_est_plane(_ligne), (
        "une forme alignée est déclarée galbée : le mode refuserait une "
        "sélection parfaitement valable")
finally:
    FreeCAD.closeDocument("EssaiPlan")
print("7. un creux de 0,3 mm est vu comme galbé, un carré plat et une ligne "
      "restent plans OK")
