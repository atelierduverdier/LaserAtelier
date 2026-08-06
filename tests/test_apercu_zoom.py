# -*- coding: utf-8 -*-
"""L'aperçu photo doit être assez fin pour juger, et zoomable.

Christophe, 06/08/2026 : « dans la visualisation photo, il est possible
d'avoir plus de résolution et zoomer ? ». Deux plafonds se cumulaient, et
le second annulait le premier :

  - le RENDU s'arrêtait à 2200 px de côté, ce qui ramenait une pièce de
    120 x 160 mm de son échelle naturelle (24 px/mm) à 13,2 ;
  - la BOÎTE d'affichage réduisait ensuite tout à 900 px, soit ~7 px/mm.

Un trait brûlé de 0,30 mm tenait donc sur deux pixels : il n'y avait rien
à juger. Le rendu monte à 4000 px (mesuré : au-delà, l'image ne bouge
plus, c'est `scale` qui décide) et la boîte zoome jusqu'à 8x.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
core = h.core
tp = h.tp
sans_dialogues()

from PySide6 import QtWidgets, QtCore, QtGui                  # noqa: E402
import FreeCAD                                                # noqa: E402
import Part                                                   # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

print("=" * 62)
print("§1  Le rendu atteint son échelle NATURELLE")
print("=" * 62)

doc = FreeCAD.newDocument("apercu_zoom")
face = Part.Face(Part.makePolygon(
    [FreeCAD.Vector(x, y, 0) for x, y in
     [(0, 0), (120, 0), (120, 160), (0, 160), (0, 0)]]))
aretes = core.generate_hatch_edges([face], 0.3, 45.0)
traits = [([(v.Point.x, v.Point.y) for v in e.Vertexes], 0.30, 0.85)
          for e in aretes]
assert traits, "pas de traits à peindre"

LARGEUR_MM = 120.0 + 2 * 3.0          # la pièce plus ses marges
img = tp._render_engraving_photo(traits)
px_par_mm = img.width() / LARGEUR_MM
print("   %d traits -> image %d x %d px, soit %.1f px/mm"
      % (len(traits), img.width(), img.height(), px_par_mm))
# 24 px/mm est l'échelle `scale` du rendu : l'atteindre veut dire que le
# plafond ne mord plus. Avant le correctif on tombait à 13,2.
assert px_par_mm > 20.0, (
    "seulement %.1f px/mm : le plafond de côté rabote encore le rendu "
    "(l'échelle naturelle est 24)" % px_par_mm)

# Et à cette échelle, un trait brûlé fait plusieurs pixels -- c'est CELA
# qui rend l'aperçu jugeable, pas le nombre de pixels en soi.
largeur_trait_px = 0.30 * px_par_mm
print("   un trait brûlé de 0,30 mm y pèse %.1f px" % largeur_trait_px)
assert largeur_trait_px >= 4.0, (
    "un trait de 0,30 mm ne fait que %.1f px : rien à juger"
    % largeur_trait_px)

print()
print("=" * 62)
print("§2  La vue zoome, et se borne")
print("=" * 62)

vue = tp._VueImage(img)
vue.resize(800, 600)
vue.show()
app.processEvents()

vue.ajuster()
zoom_ajuste = vue.zoom()
print("   « Ajuster » : zoom %.3f -> image montrée %d x %d px"
      % (zoom_ajuste, img.width() * zoom_ajuste, img.height() * zoom_ajuste))
assert 0 < zoom_ajuste < 1.0, "l'ajustement devrait réduire cette image"
assert img.height() * zoom_ajuste <= vue.viewport().height() + 1, (
    "l'image ajustée dépasse encore la vue")

vue.poser_zoom(1.0)
assert abs(vue.zoom() - 1.0) < 1e-6
print("   « 100 %% » : un pixel d'image = un pixel d'écran")

vue.poser_zoom(500.0)
print("   demande de 500x -> %.1fx (borné)" % vue.zoom())
assert vue.zoom() <= 8.0, "zoom non borné : %.1f" % vue.zoom()
vue.poser_zoom(0.0001)
print("   demande de 0.0001x -> %.3fx (borné)" % vue.zoom())
assert vue.zoom() >= 0.05, "dézoom non borné : %.4f" % vue.zoom()

print()
print("=" * 62)
print("§3  La molette zoome AUTOUR DU CURSEUR, pas du centre")
print("=" * 62)

# La propriété qui compte à l'usage : on zoome pour regarder un détail
# précis. Centré, le détail fuit hors de l'écran à chaque cran.
vue.poser_zoom(1.0)
app.processEvents()
ancre = QtCore.QPoint(120, 90)
# Le point de l'IMAGE qui se trouve sous le curseur avant le zoom.
avant = (vue.horizontalScrollBar().value() + ancre.x(),
         vue.verticalScrollBar().value() + ancre.y())
vue.poser_zoom(2.0, ancre)
apres = ((vue.horizontalScrollBar().value() + ancre.x()) / 2.0,
         (vue.verticalScrollBar().value() + ancre.y()) / 2.0)
print("   point visé avant : (%d, %d) | après un zoom 2x : (%.0f, %.0f)"
      % (avant[0], avant[1], apres[0], apres[1]))
ecart = max(abs(avant[0] - apres[0]), abs(avant[1] - apres[1]))
assert ecart <= 2.0, (
    "le point visé a bougé de %.0f px : le zoom est centré sur la vue, "
    "pas sur le curseur" % ecart)
print("   il a bougé de %.0f px : le point reste sous le curseur" % ecart)

print()
print("=" * 62)
print("§4  L'aperçu du tramage photo est monté en résolution")
print("=" * 62)

panneau = tp.TaskPanelHalftone()
grille = panneau._build_rows(max_cells=panneau._PREVIEW_MAX_CELLS)
assert grille, "pas de grille de tramage"
lignes, colonnes = len(grille), len(grille[0])
img2, _note = panneau._render_photo_preview(grille, largeur_px=2400)
assert img2 is not None, "rendu du tramage impossible"
px_par_case = img2.height() / float(lignes)
print("   grille %d x %d cases -> image %d x %d px, soit %.1f px par rangée"
      % (colonnes, lignes, img2.width(), img2.height(), px_par_case))
assert px_par_case >= 3.0, (
    "%.1f px par rangée gravée : on voit une image, pas un tramage"
    % px_par_case)

FreeCAD.closeDocument("apercu_zoom")
print()
print("TOUT EST VERT")
