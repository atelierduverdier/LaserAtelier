# -*- coding: utf-8 -*-
"""La barre d'outils découpée en barres nommées, sans perdre un bouton.

Christophe, 04/08/2026 : « pour plus de visibilité je pense qu'il serait
bien de mettre un fond de couleur différent pour chaque section dans la
barre des icônes ». Les séparateurs d'une barre unique ne se voient presque
pas ; des barres distinctes portent un NOM, se déplacent et se masquent
séparément -- c'est le seul découpage que FreeCAD offre nativement.

LE RISQUE D'UN DÉCOUPAGE À LA MAIN est d'oublier un bouton en recopiant la
liste, ou d'en mettre un dans deux barres. Rien ne le signalerait : le
bouton manquerait, simplement, et son mode deviendrait inatteignable depuis
la barre.

`InitGui` a besoin des globales que FreeCAD injecte (`Workbench`, `Gui`) :
on les bouchonne, ce qui permet du même coup de vérifier que la teinte ne
lève rien quand il n'y a pas de fenêtre principale.
"""
import builtins
import os
import sys
import types

from harness import preparer

h = preparer()
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FauxWorkbench(object):
    def __init__(self):
        self.barres = []
        self.menu = None

    def appendToolbar(self, nom, cmds):
        self.barres.append((nom, list(cmds)))

    def appendMenu(self, nom, cmds):
        self.menu = (nom, list(cmds))


_faux_gui = types.ModuleType("FreeCADGui")
_faux_gui.Workbench = _FauxWorkbench
_faux_gui.addWorkbench = lambda w: None
_faux_gui.addIconPath = lambda p: None
_faux_gui.addCommand = lambda n, c: None
_faux_gui.getMainWindow = lambda: None
_vrai_gui = sys.modules.get("FreeCADGui")
sys.modules["FreeCADGui"] = _faux_gui
builtins.Workbench = _FauxWorkbench
builtins.Gui = _faux_gui
try:
    _ns = {"__name__": "InitGui",
           "__file__": os.path.join(RACINE, "InitGui.py")}
    with open(os.path.join(RACINE, "InitGui.py"), encoding="utf-8") as f:
        exec(compile(f.read(), "InitGui.py", "exec"), _ns)
    _cls = [v for v in _ns.values()
            if isinstance(v, type) and v is not _FauxWorkbench
            and issubclass(v, _FauxWorkbench)]
    assert _cls, "la classe Workbench n'a pas été trouvée dans InitGui"
    _w = _cls[0]()
    _w.Initialize()
finally:
    if _vrai_gui is not None:
        sys.modules["FreeCADGui"] = _vrai_gui


# --- 1. Aucun bouton perdu, aucun en double --------------------------
_menu = [c for c in _w.menu[1] if c != "Separator"]
_barres = [c for _n, cmds in _w.barres for c in cmds]
assert _barres, "aucune barre d'outils déclarée"
_perdus = [c for c in _menu if c not in _barres]
assert not _perdus, (
    "des commandes du menu n'apparaissent dans AUCUNE barre : leur mode "
    "devient inatteignable depuis la barre d'outils", _perdus)
_intrus = [c for c in _barres if c not in _menu]
assert not _intrus, ("une barre expose une commande absente du menu", _intrus)
_doublons = sorted({c for c in _barres if _barres.count(c) > 1})
assert not _doublons, ("une commande apparaît dans DEUX barres", _doublons)
assert len(_barres) == len(_menu), (
    "le compte ne tombe pas juste", len(_barres), len(_menu))
print("1. {} commandes, {} barres, aucune perdue ni en double OK".format(
    len(_barres), len(_w.barres)))


# --- 2. Chaque barre a un nom PROPRE et non vide ---------------------
_noms = [n for n, _c in _w.barres]
assert len(set(_noms)) == len(_noms), ("deux barres portent le même nom : "
                                       "FreeCAD les fusionnerait", _noms)
for _n, _c in _w.barres:
    assert _n.strip(), "une barre sans nom"
    assert _c, ("la barre « {} » est vide".format(_n))
print("2. {} barres nommées, toutes distinctes et non vides : {} OK".format(
    len(_noms), ", ".join(n.replace("Atelier — ", "") for n in _noms)))


# --- 3. La teinte ne doit JAMAIS empêcher l'atelier de s'ouvrir ------
# Elle est un confort ; le nom de la barre porte l'information. Sans
# fenêtre principale (ici), avec un thème qui refuse la feuille de style,
# ou sur une autre version de Qt, elle doit se taire.
assert _w._colorer_barres() is None, "la teinte a levé quelque chose"
_w._barres = [("Barre absente", ["X"])]
assert _w._colorer_barres() is None, (
    "la teinte explose quand la barre n'existe pas dans la fenêtre")
print("3. teinte silencieuse sans fenêtre principale et sur une barre "
      "introuvable OK")


# --- 4. LES NOMS SONT UN CONTRAT ---------------------------------------
# FreeCAD retient la position de chaque barre PAR SON NOM. Renommer une
# barre, c'est en créer une neuve sans position connue : elle repart à
# l'endroit par défaut, et l'utilisateur doit tout replacer à la main.
#
# C'est arrivé une fois, le 04/08/2026, en remplaçant l'unique « Atelier
# Laser » par ces neuf-là : « en relançant FreeCAD après tes changements de
# couleur, cela a cassé toute la mise en page des icônes, elles étaient
# toutes sur la même ligne, j'ai dû les replacer ». Coût unique et assumé
# du découpage -- mais une seule fois.
#
# Ces noms ne se changent donc pas à la légère. Les figer ici ne les rend
# pas immuables : cela oblige à passer par ce contrôle, donc à voir la
# phrase ci-dessus avant de décider. Si un renommage est vraiment voulu,
# il faut PRÉVENIR : il coûtera un rangement de barres.
_ATTENDUS = [
    "Atelier — Découverte",
    "Atelier — Calibrer le laser",
    "Atelier — Ajouter un matériau",
    "Atelier — Dessins",
    "Atelier — Gravure à plat",
    "Atelier — Sur surface 3D",
    "Atelier — Découpe",
    "Atelier — Assemblage",
    "Atelier — Référence et réglages",
]
assert _noms == _ATTENDUS, (
    "les noms de barres ont changé : chaque nom modifié repartira à "
    "l'endroit par défaut chez l'utilisateur, qui devra replacer ses "
    "barres à la main. Voulu ? alors préviens-le.",
    [n for n in _noms if n not in _ATTENDUS],
    [n for n in _ATTENDUS if n not in _noms])
print("4. les {} noms de barres sont ceux que FreeCAD a mémorisés OK".format(
    len(_ATTENDUS)))


# --- 5. UNE SEULE ROUE CHROMATIQUE, LUE PAR LES DEUX --------------------
# Christophe, 05/08/2026 : « je pense que pour les couleurs de remplissage,
# il faudrait rester uni par rapport à la barre d'icônes et au reste ». Les
# calques prennent donc leurs teintes dans la table qui teinte déjà les
# barres. Deux copies auraient dérivé au premier ajustement -- et « uni »
# est exactement ce qui ne survit pas à une copie.
import inspect as _insp2                                      # noqa: E402
import laser_jobs as _lj                                      # noqa: E402

_src_gui = open(os.path.join(RACINE, "InitGui.py"), encoding="utf-8").read()
assert "TEINTES_ATELIER" in _src_gui, (
    "InitGui ne lit plus la roue partagée : il a sans doute repris une "
    "table à lui, et les deux vont diverger")
import re as _re5                                             # noqa: E402
_tables = _re5.findall(r"_TEINTES\s*=\s*\(", _src_gui)
assert not _tables, (
    "InitGui redéfinit une table de teintes en propre", _tables)

# AUTANT DE TEINTES QUE DE BARRES. `zip` s'arrête au plus court : une barre
# ajoutée sans sa teinte ne serait pas colorée, en silence.
assert len(h.core.TEINTES_ATELIER) == len(_ATTENDUS), (
    "la roue n'a pas autant de teintes que l'atelier a de barres : la "
    "dernière resterait incolore sans un mot",
    len(h.core.TEINTES_ATELIER), len(_ATTENDUS))

# ET LES CALQUES EN VIENNENT VRAIMENT. Un test qui se contenterait de
# vérifier qu'ils ont une couleur passerait sur n'importe quelle palette.
_roue = {h.core.teinte_atelier(_i5) for _i5 in range(len(h.core.TEINTES_ATELIER))}
for _m5, _c5 in _lj.COULEURS_MODE.items():
    assert _c5 in _roue, (
        "la couleur du mode « {} » ne vient pas de la roue de l'atelier : "
        "elle jurera avec les barres".format(_m5), _c5)
print("5. une seule roue de {} teintes : les {} barres et les {} calques y "
      "puisent OK".format(len(h.core.TEINTES_ATELIER), len(_ATTENDUS),
                          len(_lj.COULEURS_MODE)))
