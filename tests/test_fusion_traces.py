# -*- coding: utf-8 -*-
"""Réunir des dizaines de tracés en un seul objet.

Christophe, 06/08/2026, devant les 267 tracés de son dessin importé :
« j'ai plein de tracés que j'ai sélectionnés, il me faudrait un bouton
pour les regrouper tous en 1 seul ».

Un dessin au trait arrive en dizaines ou centaines d'objets — un par
tracé d'origine, ce qui est JUSTE pour un remplissage calculé tracé par
tracé, et pénible pour tout le reste : régler, projeter, marquer, autant
de gestes à répéter.

LES ORIGINAUX SONT MASQUÉS ET RANGÉS, JAMAIS SUPPRIMÉS. Le remplissage se
calcule par tracé (pair/impair par `<path>`) : qui a fusionné doit
pouvoir revenir en arrière. L'arbre se replie tout de même, les originaux
tenant désormais dans un seul dossier.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402

doc = FreeCAD.newDocument("fusion_traces")


class _Sel:
    def __init__(self, obj):
        self.Object = obj


def trace(nom, x, cote=5.0):
    obj = doc.addObject("Part::Feature", nom)
    obj.Shape = Part.Compound(list(Part.makePolygon([
        FreeCAD.Vector(a, b, 0) for a, b in
        [(x, 0), (x + cote, 0), (x + cote, cote), (x, cote), (x, 0)]]).Edges))
    return obj


traces = [trace("T%d" % i, i * 10.0) for i in range(6)]
doc.recompute()
aretes_avant = sum(len(o.Shape.Edges) for o in traces)

print("=" * 62)
print("§1  Six tracés deviennent UN objet, sans perdre une arête")
print("=" * 62)

fusion, err = core.run_fusion_traces([_Sel(o) for o in traces])
assert err is None, "erreur inattendue : %s" % err
print("   « %s » : %d arêtes (les 6 tracés en avaient %d)"
      % (fusion.Label, len(fusion.Shape.Edges), aretes_avant))
assert len(fusion.Shape.Edges) == aretes_avant, (
    "%d arêtes fusionnées pour %d d'origine : la fusion perd ou duplique"
    % (len(fusion.Shape.Edges), aretes_avant))

print()
print("=" * 62)
print("§2  Les originaux sont MASQUÉS et RANGÉS, pas supprimés")
print("=" * 62)

for o in traces:
    assert doc.getObject(o.Name) is not None, "« %s » a été SUPPRIMÉ" % o.Name
dossiers = [o for o in doc.Objects if o.TypeId == "App::DocumentObjectGroup"]
print("   dossiers créés : %s" % [(d.Label, len(d.Group)) for d in dossiers])
assert len(dossiers) == 1, "%d dossiers au lieu d'un" % len(dossiers)
assert len(dossiers[0].Group) == len(traces), (
    "%d originaux rangés sur %d" % (len(dossiers[0].Group), len(traces)))
print("   les 6 originaux existent toujours, dans un seul dossier : ✓")

print()
print("=" * 62)
print("§3  Moins de deux formes : on refuse, et on le dit")
print("=" * 62)

_f, err1 = core.run_fusion_traces([_Sel(traces[0])])
print("   une seule forme  -> %r" % err1)
assert err1, "fusionner une seule forme devrait être refusé"
_f, err0 = core.run_fusion_traces([])
print("   rien sélectionné -> %r" % err0)
assert err0, "fusionner rien devrait être refusé"

print()
print("=" * 62)
print("§4  Ce qui n'a pas d'arête est ignoré, sans faire tomber")
print("=" * 62)

vide = doc.addObject("Part::Feature", "Vide")
vide.Shape = Part.Compound([])
doc.recompute()
f2, err2 = core.run_fusion_traces([_Sel(traces[0]), _Sel(vide), _Sel(traces[1])])
assert err2 is None, "une forme vide fait échouer la fusion : %s" % err2
attendu = len(traces[0].Shape.Edges) + len(traces[1].Shape.Edges)
print("   2 tracés + 1 forme vide -> %d arêtes (attendu %d)"
      % (len(f2.Shape.Edges), attendu))
assert len(f2.Shape.Edges) == attendu, "la forme vide a perturbé le compte"

print()
print("=" * 62)
print("§4bis  Un tracé DÉJÀ rangé ne fait pas tomber la fusion")
print("=" * 62)

# FreeCAD lève une RuntimeError si un objet est mis dans DEUX dossiers, et
# l'import range désormais les tracés par calque : fusionner ce qu'on vient
# d'importer -- le cas de Christophe -- tombait dessus. Trouvé par ce test,
# pas à l'usage.
a, b = trace("R1", 200.0), trace("R2", 210.0)
deja = doc.addObject("App::DocumentObjectGroup", "CalqueExistant")
deja.Label = "Calque 7"
deja.Group = [a, b]
doc.recompute()

f3, err3 = core.run_fusion_traces([_Sel(a), _Sel(b)])
assert err3 is None, "fusionner des tracés déjà rangés échoue : %s" % err3
print("   « %s » créé sans erreur" % f3.Label)
assert len(deja.Group) == 2, (
    "les tracés ont été retirés de leur calque d'origine : le rangement du "
    "dessinateur ne doit pas être défait")
print("   ils sont restés dans « %s » : ✓" % deja.Label)
for o in (a, b):
    vue = getattr(o, "ViewObject", None)
    if vue is not None:
        assert not vue.Visibility, "« %s » est resté visible" % o.Label

print()
print("=" * 62)
print("§5  Le bouton existe, et il est nommé")
print("=" * 62)

import commands                                               # noqa: E402
assert hasattr(commands, "FusionnerTracesCommand"), "la commande a disparu"
res = commands.FusionnerTracesCommand().GetResources()
print("   « %s »" % res["MenuText"])
assert "usionner" in res["MenuText"], "libellé inattendu : %r" % res["MenuText"]
assert res["Pixmap"].endswith("fusionner.svg"), "icône manquante"

# ON LIT LE FICHIER, ON NE L'IMPORTE PAS. FreeCAD met CHAQUE dossier
# Mod/<wb>/ sur sys.path : `import InitGui` attrape celui d'un autre
# workbench (ici « fasteners », qui tombe aussitôt sur un FreeCADGui
# incomplet). C'est le piège des noms globaux que CLAUDE.md documente pour
# les polices -- il vaut aussi pour InitGui.
import os as _os
_racine = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_src = open(_os.path.join(_racine, "InitGui.py"), encoding="utf-8").read()
assert _src.count("LaserAtelier_FusionnerTraces") == 2, (
    "la commande doit être dans le MENU et dans une barre d'outils : "
    "%d occurrence(s)" % _src.count("LaserAtelier_FusionnerTraces"))
print("   présente dans le menu ET dans la barre « Dessins » : ✓")

FreeCAD.closeDocument("fusion_traces")
print()
print("TOUT EST VERT")
