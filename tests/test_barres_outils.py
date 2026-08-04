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
