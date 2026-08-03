# -*- coding: utf-8 -*-
"""Aucun tramage photo ne doit faire demi-tour au milieu d'une ligne.

Un tramage à points pose un micro-trait par case (jamais un G4 : le HAL
asservit la puissance à la vitesse, à l'arrêt rien ne grave). Ces points
sont rangés en serpentin pour économiser du trajet -- mais si le trait est
toujours gravé vers la droite, le gain est perdu sur une ligne sur deux :
la machine recule avant chaque point.

Ça s'est produit DEUX FOIS. Corrigé le 29/07/2026 (v1.93.0) pour la trame
de points et pour la mire, `generate_gcode_photo_zdots` avait été oublié --
et c'est Christophe qui l'a entendu à la machine, un mois plus tard, sur les
gros points Z. Le G-code était valide, l'image gravée juste : seul le bruit
trahissait le défaut. D'où ce test, qui interroge les SEPT tramages au lieu
de celui qu'on vient de réparer.
"""
from harness import (preparer, demi_tours_x, mouvements, image_demo)

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"

# --- 1. TOUS les tramages, un par un ------------------------------------
# Le compte n'est PAS ecrit en dur : il vient de _TRAMAGES. Un tramage
# ajoute entre dans ce controle tout seul -- c'est ce qui a fait entrer
# la spirale (8e) le 03/08/2026 sans toucher a ce fichier.
p = tp.TaskPanelHalftone()
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
p.combo_photo_mat.setCurrentIndex(mats.index(MAT))
p.edt_image.setText(image_demo())
p.spn_width.setValue(40.0)
p.spn_gamma.setValue(1.0)

# Chaque tramage a son régime ; imposer celui des lignes calibrées aux
# lignes gravées les ferait refuser (cf. test_panneaux).
# F200 pas 0,34 : le SEUL régime qui enfle vraiment sous le plafond
# S900 de l'atelier (1,94x). L'ancien -- F800 pas 0,30 -- venait des
# trois colonnes fabriquées du 31/07, et refuse depuis le vrai relevé.
REGIMES = {6: (0.34, 200.0)}
DEFAUT = (0.80, 2000.0)

for idx in range(p.combo_mode.count()):
    p.combo_mode.setCurrentIndex(idx)
    nom = p.combo_mode.currentText()
    pas, feed = REGIMES.get(idx, DEFAUT)
    p.spn_pitch.setValue(pas)
    p.spn_line_feed.setValue(feed)
    rows = p._build_rows(silent=True, max_cells=30000)
    g = p._generate(rows, quiet=True)
    assert g, (idx, nom)
    n = demi_tours_x(g)
    assert n == 0, (idx, nom, "{} demi-tours en X".format(n))
    print("   [{}] {:<44} 0 demi-tour OK".format(idx, nom[:44]))
print("1. les {} tramages balaient chaque ligne d'un seul tenant OK"
      .format(len(tp._TRAMAGES)))

# --- 2. Gros points Z : le trait suit VRAIMENT le sens de la ligne ------
# Le compte de demi-tours ne suffit pas : un générateur qui n'émettrait
# qu'un point par ligne le passerait aussi. On vérifie le sens du trait.
img = [[0.5] * 6 for _ in range(4)]
g = core.generate_gcode_photo_zdots(img, 0.75, core.Z_WORK_MM, 300.0,
                                    core.SPOT_FOCUS_MM, 0.60, 0.02, 0.08,
                                    quiet=True)
assert g, "aucun G-code gros points Z"
graves = [(x, y) for _d, x, y, grave in mouvements(g) if grave]
assert len(graves) == 24, len(graves)          # 4 lignes x 6 cases pleines
# Ligne du haut parcourue vers la droite, la suivante vers la gauche :
# les traits gravés doivent suivre, sinon on a le défaut d'origine.
par_ligne = {}
for x, y in graves:
    par_ligne.setdefault(round(y, 4), []).append(x)
ys = sorted(par_ligne, reverse=True)           # de haut en bas
assert len(ys) == 4, ys
for rang, y in enumerate(ys):
    xs = par_ligne[y]
    croissant = xs == sorted(xs)
    assert croissant == (rang % 2 == 0), (rang, y, xs)
print("2. gros points Z : ligne {} vers la droite, {} vers la gauche, en "
      "alternance OK".format(ys[0], ys[1]))

# --- 3. Le trait garde sa LONGUEUR, donc son temps de pose --------------
# Orienter le trait ne doit pas changer la dose : c'est la longueur divisée
# par l'avance qui fait l'exposition.
seg = max(0.05, min(0.3 * 0.75, 0.2))
x_prec = None
longueurs = []
for l in g.split("\n"):
    import re
    mx = re.search(r"\bX(-?\d+\.?\d*)", l)
    if not mx:
        continue
    xv = float(mx.group(1))
    if l.startswith("G1 ") and x_prec is not None:
        longueurs.append(abs(xv - x_prec))
    x_prec = xv
assert longueurs and all(abs(v - seg) < 1e-6 for v in longueurs), \
    (seg, sorted(set(round(v, 6) for v in longueurs))[:5])
print("3. les {} micro-traits mesurent tous {:.2f} mm : dose inchangée OK"
      .format(len(longueurs), seg))

# --- 4. Le trajet à vide diminue pour de vrai ---------------------------
# Sans orientation, chaque point d'une ligne vers la gauche coûtait un recul
# de (pas + trait) au lieu de (pas - trait). Le gain se mesure.
pas = 0.75
a_vide = sum(d for d, _x, _y, grave in mouvements(g) if not grave)
# Borne haute généreuse : 24 points, transits <= pas + trait chacun, plus
# les changements de ligne et le retour final.
plafond = 24 * (pas + seg) + 4 * 6 * pas
naif = 24 * (pas + seg)
assert a_vide < naif, ("le trajet à vide n'a pas diminué", a_vide, naif)
print("4. trajet à vide {:.1f} mm, contre {:.1f} mm minimum en gravant "
      "toujours vers la droite OK".format(a_vide, naif))

print("\nTOUS LES TESTS micro_traits PASSENT")

# --- Le BLANC se traverse en transit, pas a l'avance de gravure ---------
# Le portrait du 02/08/2026 passait 55 % de son temps -- une heure -- a
# traverser le fond blanc a F1000 faisceau eteint. Le blanc est ENTRE les
# traits, aucun recadrage ne le recupere.
import re as _re
_g5 = [[0]*40 for _ in range(3)]
for _r in range(3):
    _g5[_r][0] = 500; _g5[_r][1] = 500          # 2 cellules marquees
    _g5[_r][30] = 700                            # ... 28 cellules blanches ...
    _g5[_r][32] = 700                            # et un blanc COURT (1 cellule)
_li5 = []
core._emit_raster_rows(_li5, _g5, 0.5, 8.0, 18.0, 1000.0)
_fs = []
_s5 = 0.0
for _l in _li5:
    _m = _re.search(r"\b[SQ]([\d.]+)", _l)
    if _m: _s5 = float(_m.group(1))
    _m = _re.match(r"G1 .*F(\d+)", _l)
    if _m:
        _fs.append((int(_m.group(1)), _s5))
_rapides = [(f, s) for f, s in _fs if f > 1000]
_lents = [(f, s) for f, s in _fs if f == 1000]
assert _rapides, "aucun transit rapide sur 14 mm de blanc"
# JAMAIS de faisceau allume a la vitesse de transit : c'est la condition
# qui rend l'optimisation sure.
assert all(s == 0 for _f, s in _rapides), (
    "faisceau ALLUME pendant un transit rapide", _rapides)
assert all(f == 1000 for f, _s in _fs if _s > 0), (
    "un segment grave ne doit jamais heriter de l'avance de transit", _fs)
# Le blanc COURT (0,5 mm entre les cellules 30 et 32) reste a l'avance de
# gravure : accelerer pour un demi-millimetre hacherait le mouvement.
_courts = [f for f, s in _fs if s == 0 and f == 1000]
assert _courts, "le blanc court aurait du rester a l'avance de gravure"
print("   transit blanc : %d plage(s) rapide(s), faisceau eteint, blancs "
      "courts inchanges OK" % len(_rapides))
