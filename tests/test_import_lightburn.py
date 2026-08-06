# -*- coding: utf-8 -*-
"""Un projet LightBurn s'importe par la même icône qu'un SVG.

Christophe, 06/08/2026 : « on m'a envoyé un fichier LightBurn au lieu d'un
SVG », puis « sur la même icône on peut choisir un fichier soit SVG soit
LightBurn, le programme faisant la distinction suivant l'extension ».

La conversion vit dans `svg_import.py` -- pas dans `outils/` : l'atelier
doit pouvoir l'appeler, et une copie dans un script à part aurait divergé
au premier correctif.

TROIS PIÈGES DU FORMAT, payés sur son fichier de 267 formes et gelés ici :
un point de contrôle absent s'écrit `c0x1` SANS `c0y` (le 1 est un
marqueur) ; `<PrimList>` est facultatif -- 110 chemins sur 267 n'en ont
pas et leur contour est implicite, les ignorer perdait 41 % du dessin ;
`Rx`/`Ry` des ellipses sont en capitale.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import os                                                     # noqa: E402
import tempfile                                               # noqa: E402
import svg_import                                             # noqa: E402

DOSSIER = tempfile.mkdtemp(prefix="lightburn-")

MINIMAL = """<?xml version="1.0" encoding="UTF-8"?>
<LightBurnProject AppVersion="2.1" FormatVersion="1">
  <Shape Type="Group" CutIndex="0">
    <XForm>1 0 0 1 0 0</XForm>
    <Children>
      <Shape Type="Path" CutIndex="1">
        <XForm>1 0 0 1 10 20</XForm>
        <VertList>V0 0c0x1c1x1V10 0c0x1c1x1V10 5c0x1c1x1V0 5c0x1c1x1</VertList>
        <PrimList>L0 1L1 2L2 3L3 0</PrimList>
      </Shape>
      <Shape Type="Path" CutIndex="2">
        <XForm>1 0 0 1 0 0</XForm>
        <VertList>V0 0c0x1c1x1V4 0c0x1c1x1V4 4c0x1c1x1V0 4c0x1c1x1</VertList>
      </Shape>
      <Shape Type="Ellipse" CutIndex="3" Rx="3" Ry="2">
        <XForm>1 0 0 1 50 50</XForm>
      </Shape>
    </Children>
  </Shape>
</LightBurnProject>
"""

SOURCE = os.path.join(DOSSIER, "essai.lbrn2")
with open(SOURCE, "w", encoding="utf-8") as fh:
    fh.write(MINIMAL)

print("=" * 62)
print("§1  L'extension décide, et elle seule")
print("=" * 62)

for nom, attendu in (("dessin.svg", False), ("dessin.lbrn", True),
                     ("dessin.lbrn2", True), ("dessin.LBRN2", True),
                     ("dessin.txt", False)):
    vu = svg_import.est_lightburn(nom)
    print("   %-14s -> LightBurn : %s" % (nom, vu))
    assert vu is attendu, "%s mal classé" % nom

print()
print("=" * 62)
print("§2  Les trois pièges du format sont franchis")
print("=" * 62)

chemins, bornes = svg_import.convertir_lightburn(SOURCE)
calques = sorted(set(c for c, _d in chemins), key=lambda c: (len(c), c))
print("   %d forme(s), calques %s" % (len(chemins), calques))
# Un chemin AVEC PrimList, un SANS (contour implicite), une ellipse Rx/Ry.
assert len(chemins) == 3, (
    "%d formes au lieu de 3 : un chemin sans PrimList ou l'ellipse a été "
    "perdu -- c'est ainsi qu'on perdait 41 %% du dessin" % len(chemins))
assert calques == ["1", "2", "3"], "les calques ne suivent pas : %s" % calques

# Le `c0x1` sans `c0y` ne doit PAS devenir un point de contrôle. TOUS les
# sommets de la pièce d'essai portent ce marqueur, donc AUCUN segment ne
# doit être une cubique -- le chemin à contour implicite est celui qui
# bascule si le marqueur est pris pour une coordonnée. Première version de
# ce contrôle : elle examinait le chemin à PrimList explicite, dont les
# primitives sont des `L` quoi qu'il arrive -- elle ne pouvait pas voir la
# différence, et le sabotage passait.
cubiques = [d[:70] for _c, d in chemins if "C" in d]
print("   chemins devenus cubiques : %d" % len(cubiques))
assert not cubiques, (
    "un marqueur `c0x1` a été pris pour un point de contrôle : %s" % cubiques)
print("   le marqueur `c0x1` n'a pas été pris pour une coordonnée : ✓")

print()
print("=" * 62)
print("§3  Le SVG produit est relisible par l'atelier")
print("=" * 62)

dest = svg_import.lightburn_vers_svg(SOURCE)
print("   écrit : %s" % os.path.basename(dest))
assert os.path.exists(dest), "aucun SVG écrit"
enregistrements, avertissements = svg_import.parse_svg_file(dest)
print("   relu par le parseur de l'atelier : %d tracé(s), %d avertissement(s)"
      % (len(enregistrements), len(avertissements)))
assert len(enregistrements) == 3, (
    "l'atelier ne relit pas ce qu'il vient d'écrire : %d tracés"
    % len(enregistrements))

# Les couleurs de calque doivent arriver jusqu'aux objets (repli sur
# `stroke` de resolve_fill_color) et rester DISTINCTES.
couleurs = set(tuple(round(c, 3) for c in r["fill_rgb"]) for r in enregistrements)
print("   couleurs distinctes : %d" % len(couleurs))
assert len(couleurs) == 3, (
    "les calques arrivent avec %d couleur(s) : ils ne sont plus séparables"
    % len(couleurs))

print()
print("TOUT EST VERT")
