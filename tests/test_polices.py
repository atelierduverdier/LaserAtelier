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

from harness import preparer

h = preparer()
core = h.core
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
            os.path.join(RACINE, "hershey_font_{}.py".format(_cle))):
        _manquants.append(_cle)
assert not _manquants, ("clés du registre sans module", _manquants)
print("1. {} polices au registre, toutes chargeables OK".format(
    len(core.HERSHEY_FONTS)))

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
