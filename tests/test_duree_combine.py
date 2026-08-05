# -*- coding: utf-8 -*-
"""Le job combiné ne doit pas tout recalculer à chaque ouverture.

Christophe, 05/08/2026 : « à chaque fois que je vais dans les job
combiné, l'ordinateur souffle, il recalcule tout ? ». Oui : pour afficher
une ligne « Durée estimée », `_update_duration_preview` générait le job
ENTIER. Mesuré sur un remplissage de 150 x 200 mm au pas 0,2 : 507 877
lignes de G-code en 2,13 s, relues en 0,51 s pour en tirer un nombre --
à chaque ouverture du panneau, plus une fois par clic dans la liste.

Deux propriétés, et la seconde prime : le mémo doit ÉCONOMISER, et il ne
doit JAMAIS mentir. Un aperçu qui ne montre pas ce qu'on va obtenir est
pire que pas d'aperçu (leçon de la v2.99.10).

On compte les GÉNÉRATIONS, pas les secondes : un seuil en secondes est du
bruit sur une machine partagée, un compteur ne l'est pas.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
core = h.core
tp = h.tp
sans_dialogues()

import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402

doc = FreeCAD.newDocument("duree_combine")
face = Part.Face(Part.makePolygon(
    [FreeCAD.Vector(x, y, 0) for x, y in
     [(0, 0), (60, 0), (60, 80), (0, 80), (0, 0)]]))
hachures = core.generate_hatch_edges([face], 0.5, 45.0)
assert hachures, "pas de hachures : la pièce d'essai ne pèserait rien"

OP = {"type": "filled", "label": "remplissage", "materiau": "Hetre",
      "params": {"fill_edges": hachures,
                 "contour_edges": list(face.Wires[0].Edges),
                 "z_focus": core.Z_WORK_MM, "defocus": 0.1,
                 "fill_power": 800, "fill_feed": 2000}}

compte = {"n": 0}
_vrai = core.generate_gcode_combined


def _espion(*a, **k):
    compte["n"] += 1
    return _vrai(*a, **k)


core.generate_gcode_combined = _espion
tp.core.generate_gcode_combined = _espion


def ouvrir():
    compte["n"] = 0
    panneau = tp.TaskPanelCombined()
    return panneau, compte["n"], panneau.lbl_duration.text()


print("=" * 62)
print("§1  Rouvrir sans rien changer ne régénère RIEN")
print("=" * 62)

tp._COMBINED_OPS[:] = [OP]
tp._MEMO_DUREE_COMBINE.clear()

_p, n1, texte1 = ouvrir()
print("   1re ouverture : %d génération(s) -- %s" % (n1, texte1))
assert n1 == 1, "la première ouverture doit calculer une fois (%d)" % n1
assert "--" not in texte1, "durée non calculée : %r" % texte1

for i in (2, 3):
    _p, n, texte = ouvrir()
    print("   ouverture %d   : %d génération(s) -- %s" % (i, n, texte))
    assert n == 0, "le job a été régénéré alors que rien n'a changé (%d)" % n
    assert texte == texte1, "durée affichée différente : %r vs %r" % (texte, texte1)

print()
print("=" * 62)
print("§2  Un réglage modifié DOIT régénérer, et changer la durée")
print("=" * 62)

OP["params"]["fill_feed"] = 500          # 4x plus lent
_p, n, texte2 = ouvrir()
print("   après avance 2000 -> 500 : %d génération(s) -- %s" % (n, texte2))
assert n == 1, "un réglage a changé et le mémo a resservi une durée périmée"
assert texte2 != texte1, (
    "la durée n'a pas bougé alors que l'avance est 4x plus lente : %r" % texte2)

_p, n, _t = ouvrir()
assert n == 0, "le mémo n'a pas repris la main après le recalcul (%d)" % n
print("   puis réouverture : %d génération(s)" % n)

print()
print("=" * 62)
print("§3  Une géométrie remplacée DOIT régénérer")
print("=" * 62)

autres = core.generate_hatch_edges([face], 1.5, 45.0)
assert len(autres) != len(hachures)
OP["params"]["fill_edges"] = autres
_p, n, texte3 = ouvrir()
print("   %d arêtes -> %d arêtes : %d génération(s) -- %s"
      % (len(hachures), len(autres), n, texte3))
assert n == 1, "la géométrie a changé et le mémo a resservi l'ancienne durée"
assert texte3 != texte2, "durée inchangée malgré 3x moins de hachures"

print()
print("=" * 62)
print("§4  Ajouter une opération DOIT régénérer")
print("=" * 62)

tp._COMBINED_OPS.append(dict(OP, label="seconde"))
_p, n, texte4 = ouvrir()
print("   2 opérations : %d génération(s) -- %s" % (n, texte4))
assert n == 1, "une opération ajoutée et rien n'a été recalculé"
assert texte4 != texte3, "durée inchangée avec deux fois le travail"

print()
print("=" * 62)
print("§5  La signature voit le CONTENU, pas seulement l'identité")
print("=" * 62)

# Deux listes distinctes portant la même géométrie : même signature.
tp._COMBINED_OPS[:] = [OP]
sig_a = tp._signature_combine(tp._COMBINED_OPS)
OP["params"]["fill_edges"] = list(OP["params"]["fill_edges"])
sig_b = tp._signature_combine(tp._COMBINED_OPS)
print("   même géométrie, autre liste : signatures %s"
      % ("égales" if sig_a == sig_b else "DIFFÉRENTES"))
assert sig_a == sig_b, ("la signature ne regarde que l'identité : recopier la "
                        "liste suffit à invalider le mémo pour rien")

OP["params"]["fill_edges"] = autres[:-1]
assert tp._signature_combine(tp._COMBINED_OPS) != sig_a, (
    "retirer une arête ne change pas la signature")
print("   une arête en moins  : signature DIFFÉRENTE")

print()
print("=" * 62)
print("§6  LE VRAI CHEMIN : une opération adossée à un Job")
print("=" * 62)

# Les §1-5 posent les opérations à la main. Le panneau, lui, appelle
# `rafraichir_operations`, qui RECONSTRUIT chaque opération depuis son Job
# -- tout y est neuf à chaque ouverture. Une première version du mémo
# passait les §1-5 et ratait ses trois ouvertures sur trois ici, parce que
# deux dictionnaires de style sur dix-huit paramètres retombaient sur
# `id()`. C'est le seul §  qui aurait attrapé le défaut.
import laser_jobs as lj                                       # noqa: E402
import FreeCADGui as Gui                                      # noqa: E402

_selection = []


class _SelEx:
    """Ce que `getSelectionEx` rend, réduit à ce que les panneaux lisent."""

    def __init__(self, obj, sous):
        self.Object = obj
        self.SubElementNames = tuple(sous)
        self.ObjectName = obj.Name
        self.HasSubObjects = bool(sous)
        self.Document = obj.Document
        self.SubObjects = tuple()
        self.FullName = obj.Name


def _ajouter(obj, sous=None):
    if not any(s.Object is obj for s in _selection):
        _selection.append(_SelEx(obj, [sous] if sous else []))


Gui.Selection.clearSelection = lambda *a, **k: _selection.clear()
Gui.Selection.addSelection = _ajouter
Gui.Selection.getSelectionEx = lambda *a, **k: list(_selection)
Gui.Selection.getSelection = lambda *a, **k: [s.Object for s in _selection]

motif = doc.addObject("Part::Feature", "MotifJob")
motif.Shape = Part.Face(Part.makePolygon(
    [FreeCAD.Vector(x, y, 0) for x, y in
     [(0, 0), (60, 0), (60, 80), (0, 80), (0, 0)]]))
doc.recompute()
job = lj.creer_ou_maj_job("filled", [motif])
doc.recompute()
tp._COMBINED_OPS[:] = []
ajoutes, ignores = lj.ajouter_jobs_au_combine([job])
assert ajoutes, "le Job n'a pas produit d'opération : %s" % (ignores,)
tp._MEMO_DUREE_COMBINE.clear()

_p, n, texte_job = ouvrir()
print("   1re ouverture : %d génération(s) -- %s" % (n, texte_job))
assert n == 1
for i in (2, 3):
    _p, n, texte = ouvrir()
    print("   ouverture %d   : %d génération(s) -- %s" % (i, n, texte))
    assert n == 0, (
        "le job adossé à un Job est régénéré à chaque ouverture : la "
        "reconstruction fabrique des objets neufs, donc la signature ne "
        "doit comparer que des CONTENUS")
    assert texte == texte_job

# Et la reprise des réglages doit toujours passer : on change l'avance
# portée par la forme, comme le fait le panneau du mode.
import json                                                   # noqa: E402
reglages = json.loads(motif.LaserAtelierReglages)
avances = [c for c in reglages["filled"] if "feed" in c]
assert avances, "aucune avance dans les réglages portés par la forme"
for cle in avances:
    reglages["filled"][cle] = 300.0
motif.LaserAtelierReglages = json.dumps(reglages)
doc.recompute()

_p, n, texte_lent = ouvrir()
print("   avance -> 300 : %d génération(s) -- %s" % (n, texte_lent))
assert n == 1, ("le réglage a changé dans le Job et le mémo a resservi une "
                "durée périmée -- exactement le défaut de la v2.99.10")
assert texte_lent != texte_job, (
    "durée inchangée alors que l'avance a été divisée : %r" % texte_lent)

core.generate_gcode_combined = _vrai
FreeCAD.closeDocument("duree_combine")

print()
print("TOUT EST VERT")
