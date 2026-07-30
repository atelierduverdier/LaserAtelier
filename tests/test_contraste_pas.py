# -*- coding: utf-8 -*-
"""Lignes gravées : le contraste annoncé doit BOUGER avec le pas.

Le défaut : le verdict affichait `1 - fin/épais`, un RAPPORT, donc
insensible au pas. Christophe, 29/07/2026 : « malgré que je change le pas
il est toujours à 56 %, pourtant je vois la photo noircir si je diminue
le pas ». Il avait raison -- ce qui se voit, c'est l'ÉCART DE COUVERTURE,
de fin/pas à épais/pas (ce dernier plafonné à 100 %).

Et cet écart passe par un MAXIMUM au pas qui vaut exactement le trait le
plus épais : au-dessus les noirs n'atteignent jamais 100 %, en dessous ils
y sont déjà et seuls les clairs s'assombrissent (d'où « la photo noircit »
sans gagner en contraste).
"""
import re

from harness import preparer, texte

h = preparer()
core, tp = h.core, h.tp

MAT = u"Hêtre"
p = tp.TaskPanelHalftone()
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
p.combo_photo_mat.setCurrentIndex(mats.index(MAT))
p.combo_mode.setCurrentIndex(6)
p.spn_line_min.setValue(0.10)


def verdict(pas, feed):
    p.spn_line_feed.setValue(feed)
    p.spn_pitch.setValue(pas)
    p._maj_regime()
    t = texte(p.lbl_regime)
    m = re.search(r"contraste (\d+) points", t)
    assert m, t
    return int(m.group(1)), t


# --- 1. Le verdict n'est jamais vide -----------------------------------
c, t = verdict(0.30, 800.0)
assert len(t) > 10, ("verdict vide : coche sans texte", repr(t))
assert "0.10 → 0.30 mm" in t, t
print("1. verdict renseigne : « {} » OK".format(t))

# --- 2. Il BOUGE avec le pas -------------------------------------------
pas_essais = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.60, 0.80)
c800 = {pas: verdict(pas, 800.0)[0] for pas in pas_essais}
assert len(set(c800.values())) > 1, ("contraste insensible au pas", c800)
print("2. contraste par pas a F800 : " + ", ".join(
    "{:.2f}->{}".format(k, v) for k, v in sorted(c800.items())) + " OK")

# --- 3. Le maximum est au pas = trait le plus epais --------------------
plage = core.burn_width_range(MAT, 800.0)
opti = plage[1]
assert opti == 0.30, plage
assert c800[opti] == max(c800.values()), ("l'optimum n'est pas au pas = trait "
                                          "maxi", opti, c800)
# et il redescend DES DEUX COTES
assert c800[0.20] < c800[opti] and c800[0.40] < c800[opti], c800
attendu = round(100.0 * (1.0 - 0.10 / opti))
assert c800[opti] == attendu, (c800[opti], attendu)
print("3. maximum {} points au pas {:.2f} mm = trait le plus epais, et il "
      "redescend des deux cotes OK".format(c800[opti], opti))

# --- 4. Le calcul suit la formule, pas une constante -------------------
for pas in pas_essais:
    bas = 0.10 / pas
    haut = min(1.0, opti / pas)
    assert c800[pas] == round(100.0 * (haut - bas)), (pas, c800[pas], bas, haut)
print("4. chaque valeur vaut bien min(1, epais/pas) - fin/pas OK")

# --- 5. L'optimum est NOMME, et le pourquoi expliqué -------------------
_, t40 = verdict(0.40, 800.0)
assert "0.30 mm" in t40, ("le pas optimal n'est pas nomme", t40)
_, t20 = verdict(0.20, 800.0)
assert "saturent déjà" in t20, ("rien ne dit pourquoi plus fin ne gagne "
                                "rien", t20)
_, t30 = verdict(0.30, 800.0)
assert "Contraste maximal" not in t30, ("conseil inutile quand on y est", t30)
print("5. au pas 0.40 l'optimum est nomme ; au pas 0.20 le « pourquoi » est "
      "donne ; au pas optimal le conseil se tait OK")

# --- 6. L'optimum SUIT la vitesse --------------------------------------
# A F1000 le trait ne monte qu'a 0,23 mm : l'optimum se deplace avec lui.
plage_1000 = core.burn_width_range(MAT, 1000.0)
c1000 = {pas: verdict(pas, 1000.0)[0] for pas in
         (0.15, 0.20, 0.23, 0.30, 0.40)}
assert plage_1000[1] < opti, plage_1000
assert c1000[0.23] == max(c1000.values()), (plage_1000, c1000)
assert max(c1000.values()) < max(c800.values()), (c1000, c800)
print("6. a F1000 le trait plafonne a {:.2f} mm : optimum au pas 0.23 et "
      "contraste maximal {} au lieu de {} OK".format(
          plage_1000[1], max(c1000.values()), max(c800.values())))

# --- 7. Le doublon sous la grille a bien disparu -----------------------
p.edt_image.setText("/home/christophe/Images/Moi-laser/moi_gravure_contraste.png")
p.spn_width.setValue(80.0)
verdict(0.30, 800.0)
p._update_grid_info()
assert "Trait" not in p.lbl_grid.text(), ("dit deux fois", p.lbl_grid.text())
assert "contraste" in re.sub(r"<[^>]+>", "", p.lbl_regime.text()), \
    p.lbl_regime.text()
print("7. l'information sur le trait n'est dite QUE sous « Trait & matière » OK")

print("\nTOUS LES TESTS contraste_pas PASSENT")
