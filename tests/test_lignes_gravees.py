# -*- coding: utf-8 -*-
"""Tramage « Lignes gravées » : le trait enfle avec l'image.

Ce que ce tramage promet : le gris est une LARGEUR, lue sur les largeurs
brûlées MESURÉES, sans nuancier. La ligne n'est jamais coupée.

Faits relevés sur hêtre le 29/07/2026, et que ces tests figent : au foyer
la largeur va de 0,10 à 0,30 mm (3,0x), identique à F200, F400 ET F800 ;
à partir de F1500 elle est PLATE à 0,10 et le tramage n'a plus d'objet.
Les gros traits du défocus (jusqu'à 2,60 mm) ne servent à rien ici : leur
rapport n'est que de 1,4x, donc un contraste plus faible.
"""
import re

from harness import (preparer, texte, hauteurs_z, puissances,
                     image_demo)

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"

# --- 1. La table de largeurs est croissante et bornée aux mesures -------
t = core.burn_width_power_table(MAT, 400.0)
assert t, "aucune table de largeurs"
ws = [w for _s, w in t]
assert ws == sorted(ws), "la largeur redescend quand la puissance monte"
assert (abs(ws[0] - 0.10) < 1e-9 and abs(ws[-1] - 0.30) < 1e-9), (ws[0], ws[-1])
print("1. table F400 : {} points, largeur {:.2f} -> {:.2f} mm, croissante OK"
      .format(len(t), ws[0], ws[-1]))

# --- 2. Ne JAMAIS descendre sous la plus faible puissance mesurée -------
# burn_width_at borne aux mesures : sous la plage il rend la largeur du
# bord, si bien que S0 semble donner un trait de 0,10 mm alors qu'il ne
# grave rien. Un tramage qui promet une ligne continue ne doit pas choisir
# une puissance dont on ne sait rien.
mesures = core.load_burn_widths(MAT)["focus"]
s_mini_mesure = min(float(e["power"]) for e in mesures)
niveaux = core.swell_power_levels(MAT, 800.0, 0.10)
assert niveaux is not None
puiss, w_min, w_max = niveaux
assert min(puiss) > 0, "un niveau à S0 : la ligne ne graverait rien"
assert min(puiss) >= s_mini_mesure - 1e-9, (min(puiss), s_mini_mesure)
assert puiss == sorted(puiss), "les S ne sont pas croissants"
# Les deux extrêmes doivent redonner les largeurs voulues À LA MESURE.
assert abs(core.burn_width_at(puiss[0], 800.0, MAT) - w_min) < 1e-9
assert abs(core.burn_width_at(puiss[-1], 800.0, MAT) - w_max) < 1e-9
print("2. {} niveaux de S{} à S{} (jamais S0, jamais sous la mesure), et les "
      "extrêmes redonnent {:.2f} et {:.2f} mm OK".format(
          len(puiss), puiss[0], puiss[-1], w_min, w_max))

# --- 3. La vitesse : rien ne change dessous, tout s'arrête au-dessus ----
for f in (200.0, 400.0, 800.0):
    assert core.burn_width_range(MAT, f) == (0.10, 0.30), (f,)
for f in (1500.0, 3000.0):
    p_ = core.burn_width_range(MAT, f)
    assert p_ and abs(p_[1] - p_[0]) < 1e-9, (f, p_)
assert core.swell_max_feed(MAT) == 800.0, core.swell_max_feed(MAT)
print("3. F200/F400/F800 identiques (0.10-0.30), F1500+ plat ; la plus rapide "
      "utile est bien F800 OK")

# --- 4. Le défocus a un moins bon RAPPORT que le foyer ------------------
# C'est ce rapport, pas la largeur absolue, qui fait le contraste.
d = core.load_burn_widths(MAT).get("defocus") or []


def rapport(z, f):
    pts = sorted((float(e["power"]), float(e["width"])) for e in d
                 if abs(float(e.get("z_offset", 0) or 0) - z) < 1e-6
                 and abs(float(e["feed"]) - f) < 1e-6)
    return pts[-1][1] / pts[0][1] if len(pts) >= 3 else None


r_foyer = 0.30 / 0.10
for z, f in ((15.0, 400.0), (15.0, 200.0), (36.0, 200.0)):
    r = rapport(z, f)
    assert r is not None and r < r_foyer, (z, f, r)
print("4. rapport au foyer {:.1f}x contre {:.1f}x à défocus 15 et {:.1f}x à "
      "défocus 36 : le foyer gagne OK".format(
          r_foyer, rapport(15.0, 400.0), rapport(36.0, 200.0)))

# --- 5. Plancher réglable, borné aux mesures ----------------------------
n2 = core.swell_power_levels(MAT, 800.0, 0.20)
assert (n2[1], n2[2]) == (0.20, 0.30), n2[1:]
assert n2[0][0] > puiss[0], "le plancher n'a pas relevé la puissance"
assert core.swell_power_levels(MAT, 800.0, 5.0)[1] == 0.30     # trop haut
assert core.swell_power_levels(MAT, 800.0, 0.001)[1] == 0.10   # trop bas
print("5. plancher à 0.20 mm pris en compte ; valeurs hors plage ramenées aux "
      "mesures OK")

# --- 6. Refus net, jamais de G-code mensonger ---------------------------
assert core.swell_power_levels(MAT, 2000.0, 0.10) is None
assert core.swell_power_levels(u"MatiereInconnue", 800.0, 0.10) is None
img = [[min(1.0, (x + y) / 60.0) for x in range(40)] for y in range(30)]
assert core.generate_gcode_photo_swell_lines(
    img, 0.3, core.Z_WORK_MM, 2000.0, MAT, quiet=True) is None
msg = core.swell_refus_message(MAT, 2000.0)
assert "F800" in msg, ("le refus doit nommer la vitesse qui marche", msg)
print("6. F2000 et matériau inconnu refusés, et le refus nomme F800 OK")

# --- 7. Le G-code : au foyer, faisceau jamais coupé --------------------
g = core.generate_gcode_photo_swell_lines(img, 0.30, core.Z_WORK_MM, 800.0,
                                          MAT, line_min_mm=0.10, quiet=True)
assert g, "aucun G-code"
s_grave = puissances(g, gravure_seule=True)
assert 0 not in s_grave, "un G1 à S0 : la ligne est coupée quelque part"
assert len(s_grave) > 5, ("le trait n'a presque pas de niveaux",
                          sorted(s_grave))
assert core.Z_WORK_MM in hauteurs_z(g), ("doit graver AU FOYER",
                                         sorted(hauteurs_z(g)))
assert "(Trait : 0.10 a 0.30 mm -- couverture 33 a 100 %)" in g, \
    [l for l in g.split("\n") if "Trait" in l]
print("7. G-code : {} niveaux de S sur les G1, aucun à S0, gravé à Z={:.2f} OK"
      .format(len(s_grave), core.Z_WORK_MM))

# --- 8. Pas trop fin : signalé ----------------------------------------
serre = core.generate_gcode_photo_swell_lines(img, 0.15, core.Z_WORK_MM,
                                              800.0, MAT, quiet=True)
assert "ATTENTION" in serre and "recouvrent" in serre
assert "ATTENTION" not in g, "faux positif au pas 0.30"
print("8. pas 0.15 < trait maxi : le G-code prévient ; au pas 0.30 il se tait "
      "OK")

# --- 9. L'aperçu et le G-code sortent de la MÊME table -----------------
p = tp.TaskPanelHalftone()
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
p.combo_photo_mat.setCurrentIndex(mats.index(MAT))
p.edt_image.setText(image_demo())
p.spn_width.setValue(40.0)
p.combo_mode.setCurrentIndex(6)
p.spn_pitch.setValue(0.30)
p.spn_line_feed.setValue(800.0)
p.spn_line_min.setValue(0.10)
p.spn_gamma.setValue(1.0)
rows = p._build_rows(silent=True, max_cells=30000)
gp = p._generate(rows, quiet=True)
assert gp and "lignes gravees" in gp.lower(), (gp or "")[:200]
attendus = set(core.swell_power_levels(MAT, 800.0, 0.10)[0])
emis = puissances(gp, gravure_seule=True)
inconnus = emis - attendus
assert not inconnus, ("le G-code émet des S absents de la table partagée",
                      sorted(inconnus)[:5])
print("9. les {} valeurs de S émises sortent toutes de swell_power_levels, la "
      "table que l'aperçu utilise aussi OK".format(len(emis)))

# --- 10. Aucune diffusion d'erreur dans ce tramage ---------------------
vrai = core.floyd_steinberg_dither
appels = {"n": 0}
core.floyd_steinberg_dither = lambda *a, **k: (
    appels.__setitem__("n", appels["n"] + 1) or vrai(*a, **k))
try:
    im, note = p._render_photo_preview(rows, largeur_px=200)
finally:
    core.floyd_steinberg_dither = vrai
assert im is not None, note
assert appels["n"] == 0, "les lignes gravées passent par une diffusion"
print("10. aperçu rendu sans diffusion d'erreur -- note : « {} » OK"
      .format(note))

print("\nTOUS LES TESTS lignes_gravees PASSENT")
