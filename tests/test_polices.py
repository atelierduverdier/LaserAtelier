# -*- coding: utf-8 -*-
"""Polices mono-trait : le catalogue, le repli, et la hauteur MESURÉE.

Christophe a apporté quatre dépôts de polices CNC le 03/08/2026 et demandé
« de les avoir afin de diversifier ». L'enquête a livré autant de défauts
que de polices :

 - la police par DÉFAUT gravait « ç », « æ », « Ç », « Æ » comme des BLANCS
   (glyphes présents, liste de traits vide) : « français » sortait
   « franais », sans un mot d'avertissement ;
 - le script qui génère ces modules n'existait pas, alors qu'ils portent
   « ne pas éditer à la main » -- une donnée qu'on ne sait plus produire est
   une donnée qu'on n'ose plus corriger ;
 - les polices d'oskay DÉCLARENT une hauteur de capitale de 500 quand leurs
   capitales montent à 662 : tout texte serait sorti 32 % trop haut.
"""
import importlib
import math
import os
import sys

from harness import preparer

h = preparer()
core, tp = h.core, h.tp
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- 1. Le catalogue, et le chargement PARESSEUX ------------------------
# 42 modules sur le disque ne doivent rien coûter tant qu'on n'en choisit
# pas un : `_hershey_module` importe à la demande. Si un jour quelqu'un
# précharge tout « pour aller plus vite », l'ouverture du panneau paiera
# 2,6 Mo de Python pour une police utilisée.
assert len(core.HERSHEY_FONTS) >= 40, len(core.HERSHEY_FONTS)
for _cle in ("sans", "script", "relief"):
    assert _cle in core.HERSHEY_FONTS, _cle
_manquants = []
for _cle in core.HERSHEY_FONTS:
    _m = core._hershey_module(_cle)
    if _cle not in ("sans", "script") and not os.path.isfile(
            os.path.join(RACINE, core.POLICES_PAQUET,
                         "hershey_font_{}.py".format(_cle))):
        _manquants.append(_cle)
assert not _manquants, ("clés du registre sans module", _manquants)
print("1. {} polices au registre, toutes chargeables OK".format(
    len(core.HERSHEY_FONTS)))


# --- 1 bis. LES POLICES SONT DANS LEUR DOSSIER, ET LES DEUX CHEMINS
#            D'IMPORT MARCHENT ------------------------------------------
# Christophe, 04/08/2026 : « j'ai vu que dans le dépôt toutes les
# hershey_font étaient à la racine, il n'y a pas moyen de les mettre dans un
# dossier ? ». Elles sont désormais dans `polices_monotrait/`. Ce n'est pas
# que du rangement : FreeCAD met CHAQUE dossier de `Mod/` sur `sys.path`,
# donc un fichier à la racine d'un workbench occupe un nom GLOBAL, partagé
# avec tous les ateliers installés. Quarante-quatre noms exposés sont
# devenus un seul.
_m = core._hershey_module("relief")
assert _m.__name__.startswith(core.POLICES_PAQUET + "."), _m.__name__
assert os.path.basename(os.path.dirname(_m.__file__)) == core.POLICES_PAQUET
# ET C'EST LE CHEMIN NORMAL QUI A SERVI, pas le repli. Le nom du module ne
# les distingue pas -- le repli donne exactement le même -- alors qu'un
# `sys.modules` les sépare nettement : `import_module` y inscrit le paquet
# ET le sous-module, `exec_module` sur un spec de fichier n'y inscrit rien.
# Sans ce contrôle-ci, casser l'import par paquet passait inaperçu : le
# repli rattrapait tout et la suite restait verte (vérifié en le cassant).
assert core.POLICES_PAQUET in sys.modules, (
    "le paquet des polices n'a jamais été importé : c'est le repli par "
    "chemin qui sert, et le chemin normal est cassé sans le dire")
assert sys.modules.get(_m.__name__) is _m, (
    "la police ne vient pas de sys.modules : elle a été chargée par le "
    "repli", _m.__name__)

# Le repli par chemin, éprouvé POUR LUI-MÊME : il n'entre en jeu que si
# `sys.path` ne porte pas le dossier du workbench, donc jamais ici. Livré
# sans contrôle, il resterait faux jusqu'au jour où il faudrait qu'il
# marche -- et ce jour-là, TOUTES les polices tomberaient d'un coup, au
# redémarrage, loin du changement qui l'aurait causé. Il l'était : écrit
# avec `_WORKBENCH_DIR`, que le harnais détourne vers une copie jetable, il
# cherchait les polices dans /tmp.
_repli = core._charger_police_par_chemin("hershey_font_relief")
assert len(_repli.GLYPHES) == len(_m.GLYPHES) > 0, (
    "le repli par chemin ne rend pas la même police", len(_repli.GLYPHES))
assert _repli.CAP_HEIGHT == _m.CAP_HEIGHT

# Et la clé inconnue retombe toujours sur la police par défaut.
assert core._hershey_module("police-qui-n-existe-pas").GLYPHES, (
    "une clé inconnue ne retombe plus sur la police par défaut")
print("1 bis. importées depuis {}/, repli par chemin éprouvé, clé inconnue "
      "repliée OK".format(core.POLICES_PAQUET))

# --- 2. La hauteur de capitale est MESURÉE, pas crue ---------------------
# Le piège : les SVG d'oskay annoncent cap-height="500" et dessinent leurs
# capitales jusqu'à 662. Le mode Texte divise par CAP_HEIGHT, donc croire
# la déclaration gravait 32 % trop haut -- sur toutes les étiquettes des
# planches de calibration. Attrapé par test_mire_planches, pas par l'oeil.
_ecarts = []
for _cle in core.HERSHEY_FONTS:
    _m = core._hershey_module(_cle)
    _refs = [c for c in "HXEIT" if _m.GLYPHES.get(c) and _m.GLYPHES[c][1]]
    if not _refs:
        continue
    # L'ÉCART du 'H', pas son sommet : dans les polices EMS le trait est
    # l'AXE du fût, donc rentré (leur 'H' court de 22 à 652). C'est
    # l'écart que Christophe mesure au pied à coulisse sur le bois.
    _ys = [y for t in _m.GLYPHES[_refs[0]][1] for _x, y in t]
    _haut = max(_ys) - min(_ys)
    _rel = abs(_haut - _m.CAP_HEIGHT) / float(_m.CAP_HEIGHT)
    if _rel > 0.02:
        _ecarts.append((_cle, _m.CAP_HEIGHT, _haut))
assert not _ecarts, (
    "CAP_HEIGHT ne vaut pas la hauteur réelle des capitales : un texte "
    "demandé à 2,5 mm ne sortira pas à 2,5", _ecarts[:4])
# ... et vérifié de bout en bout : une capitale demandée à 10 mm en fait 10.
for _cle in ("sans", "relief", "emsreadability", "emsswiss"):
    _e = core.single_line_text_to_edges("HHH", height=10.0, font=_cle)
    _ys = [v.Point.y for a in _e for v in a.Vertexes]
    assert abs((max(_ys) - min(_ys)) - 10.0) < 0.2, (
        _cle, "capitale gravée", max(_ys) - min(_ys))
print("2. hauteur de capitale mesurée : 'H' demandé à 10 mm en fait 10 sur "
      "{} polices OK".format(len(core.HERSHEY_FONTS)))

# --- 3. Aucun caractère français ne se perd EN SILENCE -------------------
# Le défaut d'origine, formulé comme une propriété : ce qui n'est pas
# gravable est REMPLACÉ (repli typographique) ou NOMMÉ, jamais escamoté.
_FR = "àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»°"
for _cle in ("sans", "script", "relief", "emsreadability", "emstech"):
    _m = core._hershey_module(_cle)
    _sortie = core.deplier_texte(_FR, _m, quiet=True)
    _perdus = [c for c in _sortie
               if c not in _m.GLYPHES or (not _m.GLYPHES[c][1] and c != " ")]
    assert not _perdus, (_cle, "caractères encore muets après repli",
                         " ".join(_perdus))
# Le repli est bien celui du français, pas un caractère au hasard.
_sans = core._hershey_module("sans")
assert core.deplier_texte("cœur", _sans, quiet=True) == "coeur"
assert core.deplier_texte("ŒUVRE", _sans, quiet=True) == "OEUVRE"
# « ç » ne doit PLUS être un repli : la police régénérée le trace vraiment.
assert core.deplier_texte("français", _sans, quiet=True) == "français"
assert _sans.GLYPHES["ç"][1], "« ç » est de nouveau muet dans la police par défaut"
print("3. les {} caractères français passent sur 5 polices ; cœur -> coeur, "
      "et « ç » est tracé OK".format(len(_FR)))

# --- 4. Le texte gravé grandit avec le nombre de lettres ----------------
# Contrôle grossier mais qui a du mordant : si le repli oubliait d'être
# appliqué à la MESURE (single_line_text_extent) sans l'oublier au TRACÉ,
# le cadre annoncé serait plus étroit que la gravure -- et la pièce sortirait
# du champ. Les deux passent par `deplier_texte`.
for _cle in ("sans", "emsreadability"):
    _l1, _ = core.single_line_text_extent("cœur", height=10.0, font=_cle)
    _l2, _ = core.single_line_text_extent("coeur", height=10.0, font=_cle)
    assert abs(_l1 - _l2) < 0.01, (
        "la mesure ignore le repli : le cadre annoncé mentira", _cle, _l1, _l2)
    _e = core.single_line_text_to_edges("cœur", height=10.0, font=_cle)
    _xs = [v.Point.x for a in _e for v in a.Vertexes]
    _encre = max(_xs) - min(_xs)
    # L'ENCRE tient dans la MESURE, et pas de beaucoup : l'écart est
    # l'approche droite de la dernière lettre (une chasse comprend son
    # blanc), donc au plus une lettre. Exiger l'égalité stricte reviendrait
    # à interdire les approches, ce qu'aucune police ne fait.
    assert _encre <= _l1 + 0.01, (_cle, "l'encre déborde du cadre annoncé",
                                  _encre, _l1)
    assert _l1 - _encre < 0.6 * 10.0, (
        _cle, "le cadre annoncé est bien plus large que l'encre", _encre, _l1)
print("4. mesure et tracé appliquent le MÊME repli OK")

# --- 5. Les polices à fût contourné sont ÉTIQUETÉES ---------------------
# Elles gravent chaque branche deux fois : deux fois le temps, et un trait
# plus large que voulu. Christophe les a demandées quand même -- elles sont
# donc là, mais le libellé le dit. Un piège annoncé n'est plus un piège.
_lourdes = [c for c, lib in core.HERSHEY_FONTS.items()
            if "contourné" in lib]
assert _lourdes, "aucune police n'est signalée « fût contourné »"
for _cle in _lourdes:
    _m = core._hershey_module(_cle)
    _n = [len(_m.GLYPHES[c][1]) for c in "AEHOBMSnmoe" if _m.GLYPHES.get(c)]
    assert sum(_n) / float(len(_n)) >= 3.5, (
        "étiquetée « fût contourné » mais légère", _cle, sum(_n) / len(_n))
_sans_n = [len(_sans.GLYPHES[c][1]) for c in "AEHOBMSnmoe"]
assert sum(_sans_n) / float(len(_sans_n)) < 3.5, "la police par défaut est lourde"
print("5. {} polices à fût contourné, toutes étiquetées et vérifiées lourdes "
      "OK".format(len(_lourdes)))


# --- 6. Le spécimen dessine les VRAIS traits, à la bonne taille ---------
# Le piège de ce genre d'aperçu est d'afficher une police d'ÉCRAN qui
# ressemble à la police machine : on choisit alors d'après une image qui
# n'est pas ce qui sera gravé. La vérification tient en une mesure : la
# hauteur d'encre d'un « H » doit valoir la hauteur de capitale demandée,
# ce qui n'est vrai que si le tracé vient bien de GLYPHES, à l'échelle du
# CAP_HEIGHT de CETTE police-là.
from PySide6 import QtGui, QtCore

def _boite_encre(img):
    """Rectangle occupé par les pixels non transparents (l, h, y_haut)."""
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            if QtGui.qAlpha(img.pixel(x, y)) > 40:
                xs.append(x); ys.append(y)
    if not xs:
        return (0, 0, 0)
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, min(ys))

_CAPS = 40
_essais = ["sans"] + [c for c in list(core.HERSHEY_FONTS)[1:12]]
_vus = {}
for _cle in _essais:
    _hf = core._hershey_module(_cle)
    if not _hf.GLYPHES.get("H"):
        continue
    _img, _x = tp._dessiner_police(_hf, "H", 400, hauteur_cap_px=_CAPS)
    _l, _h, _y = _boite_encre(_img)
    assert _h > 0, (_cle, "le spécimen est vide")
    # Tolérance : l'épaisseur de plume (1,4 px) déborde d'un demi-trait de
    # chaque côté, et l'anticrénelage étale un peu. Au-delà de 4 px c'est
    # que l'échelle vient d'ailleurs que du CAP_HEIGHT de cette police.
    assert abs(_h - _CAPS) <= 4, (
        _cle, "hauteur d'encre du H ≠ hauteur de capitale demandée",
        _h, _CAPS, _hf.CAP_HEIGHT)
    _vus[_cle] = _img.copy()
assert len(_vus) >= 8, ("trop peu de polices testées", len(_vus))

# Et deux polices différentes ne donnent pas la même image : sans cela, la
# mesure ci-dessus passerait aussi avec un seul dessin recopié 44 fois.
_texte_demo = "Atelier"
_rendus = {}
for _cle in _vus:
    _img, _ = tp._dessiner_police(core._hershey_module(_cle), _texte_demo, 400)
    _rendus[_cle] = bytes(_img.constBits())
assert len(set(_rendus.values())) >= len(_rendus) - 1, (
    "plusieurs polices rendent une image identique",
    len(set(_rendus.values())), len(_rendus))
print("6. spécimen : {} polices tracées avec leurs propres traits, "
      "à leur propre hauteur de capitale OK".format(len(_vus)))

# --- 7. Cliquer une police l'APPLIQUE vraiment --------------------------
# Le choix visuel des tons a appris la règle à ses dépens : PySide
# reconstruit les données d'item à chaque lecture, donc seul un INDEX
# désigne une entrée de façon fiable. Ici on vérifie le bout utile de la
# chaîne : ce que la boîte renvoie finit dans le combo, donc dans le
# G-code -- pas seulement dans un aperçu.
_panneau = tp.TaskPanelText()
_cible = None
for _i in range(_panneau.combo_font.count()):
    if _panneau.combo_font.itemData(_i) != _panneau.combo_font.currentData():
        _cible = _i
        break
assert _cible is not None, "un seul choix de police dans le combo ?"
_attendu = _panneau.combo_font.itemData(_cible)
_originel = tp._choisir_police_visuel
try:
    tp._choisir_police_visuel = lambda *_a, **_k: _cible
    _panneau._on_voir_polices()
finally:
    tp._choisir_police_visuel = _originel
assert _panneau.combo_font.currentData() == _attendu, (
    "la police cliquée n'est pas celle appliquée",
    _panneau.combo_font.currentData(), _attendu)

# Annuler (None) ne doit RIEN changer -- un aperçu qu'on ferme ne décide pas.
# On se place volontairement sur un index NON NUL : sur l'index 0, un
# « annuler » qui retomberait bêtement au début passerait inaperçu (c'est
# exactement ce qu'un sabotage de ce contrôle a montré).
_panneau.combo_font.setCurrentIndex(_panneau.combo_font.count() - 1)
_avant = _panneau.combo_font.currentIndex()
assert _avant > 0, "index de départ nul : le contrôle ne prouverait rien"
try:
    tp._choisir_police_visuel = lambda *_a, **_k: None
    _panneau._on_voir_polices()
finally:
    tp._choisir_police_visuel = _originel
assert _panneau.combo_font.currentIndex() == _avant, (
    "annuler le spécimen a quand même changé la police")
print("7. le clic applique la police, l'annulation ne touche à rien OK")
