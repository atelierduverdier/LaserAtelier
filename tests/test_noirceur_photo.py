# -*- coding: utf-8 -*-
"""Lecture de la noirceur sur photo redressee : geometrie et normalisation.

Le piege central est un RETOURNEMENT : le G-code a Y vers le HAUT, l'image
Y vers le BAS. Une erreur de sens ne casse rien -- elle lit des cases
voisines, avec des valeurs parfaitement plausibles, et le nuancier entier
part a l'envers sans qu'aucune exception ne se leve.
"""
from harness import preparer
h = preparer()
core = h.core

# --- 1. Le repere de la mire, et le sens du Y ---------------------------
INFOS = {"x0": 10.0, "y0": 20.0, "largeur": 100.0, "hauteur": 60.0,
         "power": 150.0, "feed": 300.0, "laser": "bleu"}
COTE, PAS = 6.0, 8.0
cells = [{"row": r, "col": c, "power": 200.0 + 100 * c, "feed": 400.0,
          "x0": 10.0 + c * PAS, "y0": 20.0 + r * PAS}
         for r in range(3) for c in range(4)]
f = core.fiche_grille_noirceur(cells, COTE, INFOS, marge_lecture=0.0)
assert f and len(f["cases"]) == 12, f
par = {(c["row"], c["col"]): c for c in f["cases"]}

# La case row=0 est la plus BASSE sur la machine, donc la plus HAUTE en y
# d'image : son y0 d'image doit etre le plus GRAND des trois rangees.
y0 = [par[(r, 0)]["y0"] for r in range(3)]
assert y0[0] > y0[1] > y0[2], ("le Y n'est pas retourne : la rangee 0 est en "
                               "bas sur la machine, donc en BAS de l'image", y0)
# Et la colonne 0 reste a gauche : le X, lui, ne se retourne pas.
x0 = [par[(0, c)]["x0"] for c in range(4)]
assert x0 == sorted(x0), ("le X ne doit PAS etre retourne", x0)

# Case (0,0) : coin machine (10,20)-(16,26), mire en (10,20) haute de 60.
# Image : x 0..6 ; y = 80-26=54 .. 80-20=60.
c00 = par[(0, 0)]
for cle, attendu in (("x0", 0.0), ("x1", 6.0), ("y0", 54.0), ("y1", 60.0)):
    assert abs(c00[cle] - attendu) < 1e-9, (cle, c00[cle], attendu)
# Toute case tient DANS la mire : sinon on lirait hors de la photo.
for c in f["cases"]:
    assert 0 <= c["x0"] < c["x1"] <= INFOS["largeur"], c
    assert 0 <= c["y0"] < c["y1"] <= INFOS["hauteur"], c
print("1. le repere de la mire retourne le Y et pas le X OK")

# --- 2. La marge de lecture rogne le BORD, pas le centre ----------------
f2 = core.fiche_grille_noirceur(cells, COTE, INFOS, marge_lecture=0.25)
d = par[(0, 0)]
r = [c for c in f2["cases"] if (c["row"], c["col"]) == (0, 0)][0]
assert r["x0"] > d["x0"] and r["x1"] < d["x1"], (d, r)
# Le CENTRE ne bouge pas : on lit moins large, pas ailleurs.
for a, b in (("x0", "x1"), ("y0", "y1")):
    assert abs((r[a] + r[b]) - (d[a] + d[b])) < 1e-9, (a, b, d, r)
print("2. la marge de lecture rogne le bord sans deplacer le centre OK")

# --- 3. mm -> pixels : la marge du redressement --------------------------
photo = {"largeur_mm": 110.0, "base_mm": [100.0, 60.0], "pxmm": 40.0}
assert abs(core.marge_photo(photo) - 5.0) < 1e-9, core.marge_photo(photo)
px = core.case_en_pixels(par[(0, 0)], photo["pxmm"], core.marge_photo(photo))
assert px == (200, 2360, 440, 2600), px
assert core.marge_photo({}) == 0.0
print("3. mm -> pixels passe par la marge du redressement OK")

# --- 4. La normalisation, et son refus ----------------------------------
assert abs(core.noirceur_normalisee(200.0, 200.0, 40.0) - 0.0) < 1e-9
assert abs(core.noirceur_normalisee(40.0, 200.0, 40.0) - 100.0) < 1e-9
assert abs(core.noirceur_normalisee(120.0, 200.0, 40.0) - 50.0) < 1e-9
# Insensible a l'exposition : tout decaler d'un facteur ne change rien.
for k in (0.5, 1.4):
    assert abs(core.noirceur_normalisee(120.0*k, 200.0*k, 40.0*k) - 50.0) < 1e-6, k
# Hors bornes : borne, jamais negatif ni au-dela de 100.
assert core.noirceur_normalisee(230.0, 200.0, 40.0) == 0.0
assert core.noirceur_normalisee(10.0, 200.0, 40.0) == 100.0
# Deux reperes trop proches : REFUS, pas un pourcentage sur du bruit.
assert core.noirceur_normalisee(100.0, 120.0, 100.0) is None, (
    "un ecart de %g niveaux doit etre refuse" % core.ECART_REPERES_MINI)
assert core.noirceur_normalisee(100.0, 100.0, 100.0) is None
print("4. la normalisation est insensible a l'exposition, et refuse le bruit OK")

# --- 5. Cas vides -------------------------------------------------------
assert core.fiche_grille_noirceur([], COTE, INFOS) is None
assert core.fiche_grille_noirceur(cells, COTE, None) is None
assert core.bbox_grille_test([], COTE) is None
bb = core.bbox_grille_test(cells, COTE)
assert bb == (10.0, 20.0, 10.0 + 3*PAS + COTE, 20.0 + 2*PAS + COTE), bb
print("5. entrees vides : None plutot qu'une fiche a moitie vraie OK")

print("\nTOUS LES TESTS noirceur_photo PASSENT")

# --- 6. Le panneau : case a cocher, mire gravee, fiche deposee ----------
from harness import sans_dialogues
sans_dialogues()
tp = h.tp
p = tp.TaskPanelTestGrid()
assert hasattr(p, "chk_mire"), "la case « mire » manque au panneau Grille"
assert not p.chk_mire.isChecked(), "la mire ne doit pas etre cochee par defaut"
assert "mire" in p._last_fields, "la case doit se souvenir entre deux sessions"
assert hasattr(p, "_deposer_fiche_grille"), "le depot de fiche manque"

# La mire change VRAIMENT le G-code produit, et seulement quand on coche.
COTE = 6.0
_cells = core.build_test_grid_cells("gravure", 200.0, 1000.0, 3, 400.0, 800.0, 2,
                                    COTE, 2.0, fill_type="paralleles",
                                    hatch_spacing=0.4)
_sans = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                      mire=False, quiet=True)
_avec = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                      mire=True, quiet=True)
assert "Mire de mesure" not in _sans, "mire gravee sans avoir ete demandee"
assert "Mire de mesure" in _avec, "mire demandee mais absente du G-code"
assert len(_avec) > len(_sans), (len(_avec), len(_sans))

# La mire est AU FOYER : la planche ne doit pas gagner une troisieme hauteur
# quand les cellules sont defocalisees, sinon la reference serait floue.
import re as _re2
def _hauteurs(g):
    return sorted({round(float(m.group(1)), 3)
                   for l in g.split("\n") for m in [_re2.search(r"\bZ(-?[\d.]+)", l)] if m})
_defoc = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                       mire=True, cell_z_offset=12.0, quiet=True)
_h = _hauteurs(_defoc)
assert core.Z_WORK_MM in _h, ("la mire doit rester au foyer", _h)
assert len(_h) == 3, ("foyer + defocus + retrait, pas une de plus", _h)
print("6. la case grave la mire, au foyer, et seulement si on la coche OK")
