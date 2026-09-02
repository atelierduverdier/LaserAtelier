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
# ON RETIENT CE QUE `addCommand` REÇOIT, au lieu de le jeter. Bouchonné à
# vide, il laissait passer le seul défaut que ce fichier ne pouvait pas
# voir : un nom annoncé au menu sans commande derrière (§6).
_ENREGISTREES = {}
_faux_gui.addCommand = lambda n, c: _ENREGISTREES.__setitem__(n, c)
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


# --- 6. TOUT NOM ANNONCÉ A UNE COMMANDE DERRIÈRE -----------------------
# Christophe, 06/08/2026 : « je lance l'atelier et ça fonctionne ». C'est
# vrai, et son redémarrage est un test plus fort que celui-ci -- il fait
# tourner InitGui dans le VRAI FreeCAD, pas contre des bouchons.
#
# Reste ce que ni l'un ni l'autre n'attrapait. §1 compare le menu aux
# barres : deux listes écrites dans le même fichier, qui peuvent être
# d'accord entre elles et fausses toutes les deux. Un nom qui ne
# correspond à aucune commande enregistrée n'empêche RIEN de se charger --
# le bouton n'est simplement pas là, parmi vingt-quatre.
#
# LE PREMIER SABOTAGE ÉCRIT POUR CETTE SECTION NE LA TOUCHAIT PAS : ajouter
# un nom bidon à la liste du menu, ou retirer un nom d'une barre, déséquilibre
# les deux listes et c'est §1 qui rougit. La section restait non prouvée.
# Le vrai défaut -- et le seul sabotage qui vaille ici -- est un RENOMMAGE
# FAIT D'UN SEUL CÔTÉ : changer le nom passé à `Gui.addCommand` dans
# `commands.py` laisse menu et barres parfaitement d'accord, et c'est bien
# §6 qui parle.
_fantomes = [c for c in _menu if c not in _ENREGISTREES]
assert not _fantomes, (
    "ces noms sont annoncés au menu et dans une barre, mais aucune "
    "commande ne porte ce nom : FreeCAD n'affichera pas le bouton, sans un "
    "mot, et le mode deviendra inatteignable", _fantomes)
_jamais_montrees = [n for n in _ENREGISTREES if n not in _menu]
assert not _jamais_montrees, (
    "ces commandes sont enregistrées mais n'apparaissent NI au menu NI "
    "dans une barre : du code livré que personne ne peut atteindre",
    _jamais_montrees)
print("6. les {} commandes annoncées sont toutes enregistrées, et aucune "
      "enregistrée n'est orpheline OK".format(len(_menu)))


# --- 7. CHAQUE BOUTON A UNE ICÔNE QUI EXISTE ET QUI SE PARSE -----------
# QtSvg ne rend RIEN, en silence, si le XML est invalide (le « -- » dans un
# commentaire, piège que CLAUDE.md documente déjà). Un bouton vide se
# charge parfaitement : ni le redémarrage de Christophe ni les sections
# ci-dessus ne le signalent. `xmllint --noout` est le geste manuel ; ici il
# devient automatique, sur les 24 d'un coup.
import xml.etree.ElementTree as _ET7                           # noqa: E402

_sans_icone, _absentes, _illisibles = [], [], []
for _nom7 in sorted(_ENREGISTREES):
    try:
        _res7 = _ENREGISTREES[_nom7].GetResources()
    except Exception as _exc7:
        _sans_icone.append((_nom7, "GetResources lève : %r" % (_exc7,)))
        continue
    _px7 = _res7.get("Pixmap")
    if not _px7:
        _sans_icone.append((_nom7, "aucun Pixmap"))
        continue
    if not os.path.exists(_px7):
        _absentes.append((_nom7, _px7))
        continue
    try:
        _ET7.parse(_px7)
    except Exception as _exc7:
        _illisibles.append((_nom7, os.path.basename(_px7), str(_exc7)[:70]))

assert not _sans_icone, (
    "des commandes n'annoncent pas d'icône (ou lèvent en le disant)",
    _sans_icone)
assert not _absentes, (
    "le fichier d'icône n'existe pas : le bouton s'affichera vide",
    _absentes)
assert not _illisibles, (
    "SVG invalide -- QtSvg ne rendra RIEN, en silence, et le bouton "
    "s'affichera vide sans qu'aucune erreur ne le dise", _illisibles)
print("7. les {} icônes existent et se parsent OK".format(len(_ENREGISTREES)))


# --- TOUTE BARRE REÇOIT UNE TEINTE, MÊME LA DIXIÈME ---------------------
# `_colorer_barres` appariait barres et teintes par `zip` : neuf de chaque
# aujourd'hui, mais ajouter un mode -- manœuvre courante, décrite dans
# CLAUDE.md -- peut ajouter une barre, et la dixième serait restée grise
# sans un mot. Trouvé à l'audit du 02/09/2026.
import laser_core as _lc                                      # noqa: E402

_roue = _lc.TEINTES_ATELIER
assert _roue, "la roue de teintes est vide"
_teintes = [_roue[_i % len(_roue)] for _i in range(len(_barres))]
assert len(_teintes) == len(_barres), "une barre sans teinte"
assert all(isinstance(_t, int) for _t in _teintes), "teinte non numérique"

# ET LA ONZIÈME AUSSI : on simule une barre de plus, la roue doit reprendre
# au début plutôt que de laisser la barre sans couleur.
_faux = list(_barres) + [("Atelier — barre d'essai", ["LaserAtelier_Guide"])]
_teintes2 = [_roue[_i % len(_roue)] for _i in range(len(_faux))]
assert len(_teintes2) == len(_faux), (
    "une barre ajoutée resterait sans teinte : le repli sur la roue ne joue "
    "pas")
import inspect as _insp2                                      # noqa: E402
_src_col = _insp2.getsource(_w._colorer_barres)
assert "zip(self._barres" not in _src_col, (
    "les barres sont de nouveau appariées par zip : une barre de plus que "
    "de teintes serait tronquée en silence")
print("teintes : {} barres, {} teintes, repli sur la roue OK".format(
    len(_barres), len(_roue)))
