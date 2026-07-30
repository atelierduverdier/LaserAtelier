# -*- coding: utf-8 -*-
"""Rampe puissance/vitesse : les graduations Z chiffrent le DÉFOCUS.

Ces graduations ne sont pas décoratives : c'est en face d'elles que
Christophe mesure au pied à coulisse, et le chiffre qu'il lit part droit
dans « + Ajouter ce ton » comme `z_offset`. Or `z_offset` est un DÉFOCUS
partout dans l'atelier (tons, largeurs brûlées, `DEFOCUS_LEVELS_MM`,
« Défocus des cellules ») ; la cote machine n'est saisie nulle part.

Graduer tous les 5 mm de HAUTEUR Z faisait tomber les traits sur les
défocus 2, 7, 12 et 17 avec un foyer à 8 mm, en gravant « 10 15 20 25 ».
Le « 15 » désignait donc un défocus de 7 -- et `_snap_defocus_level`
l'aurait rangé au niveau 15, celui où vivent déjà ses mesures. Des
largeurs prises à 7 mm de défocus mélangées à celles de 15, sans un mot.
Corrigé en v1.97.1.
"""
import re

from harness import preparer

h = preparer()
core = h.core

Z_FOYER = 8.0
Z_FIN = 28.0                 # 20 mm de défocus -> défocus ronds 5/10/15/20
LONGUEUR = 120.0

# --- 1. Les chiffres gravés sont les défocus, pas les hauteurs -----------
# Discriminant net : en défocus la série est 5/10/15/20, en hauteur elle
# serait 10/15/20/25. Donc « 5 » présent et « 25 » absent tranche.
vrai = core.text_to_edges_vertical
vus = []
core.text_to_edges_vertical = lambda txt, *a, **k: (vus.append(txt)
                                                    or vrai(txt, *a, **k))
try:
    g = core.generate_gcode_power_ramp_lines(
        line_length=LONGUEUR, n_lines=4, feed_min=200.0, feed_max=800.0,
        power_min=200.0, power_max=1000.0, z_work=Z_FOYER,
        line_gap=10.0, z_end=Z_FIN, n_steps=40, quiet=True)
finally:
    core.text_to_edges_vertical = vrai
assert g, "aucun G-code"
assert "5" in vus, ("le défocus 5 n'est pas gravé", vus)
assert "25" not in vus, ("« 25 » gravé : c'est une hauteur machine, pas un "
                         "défocus", vus)
for d in ("5", "10", "15", "20"):
    assert d in vus, (d, vus)
print("1. chiffres gravés : {} -- les 4 défocus ronds y sont, aucune cote "
      "machine OK".format([v for v in vus if float(v) <= 20]))

# --- 2. Un trait par défocus rond, traversant toutes les lignes ---------
# Un trait de graduation Z coupe les 4 lignes de rampe : c'est un G1 à X
# constant dont Y varie de plus que l'écart entre lignes.
x = y = None
verticaux = []
for l in g.split("\n"):
    mx = re.search(r"\bX(-?\d+\.?\d*)", l)
    my = re.search(r"\bY(-?\d+\.?\d*)", l)
    nx = float(mx.group(1)) if mx else x
    ny = float(my.group(1)) if my else y
    if l.startswith("G1 ") and None not in (x, y, nx, ny):
        if abs(nx - x) < 1e-6 and abs(ny - y) > 3 * 10.0:
            verticaux.append(nx)
    x, y = nx, ny
assert len(verticaux) == 4, (len(verticaux), verticaux)
print("2. {} traits verticaux traversant les 4 lignes, aux X {} OK".format(
    len(verticaux), [round(v, 2) for v in sorted(verticaux)]))

# --- 3. LE test : le Z RÉEL en face de chaque trait ---------------------
# Pas la formule de placement -- la trajectoire que le G-code parcourt
# vraiment. C'est le piège maison : une graduation cohérente avec sa
# propre règle de trois et fausse par rapport aux paliers gravés.
traj = []
x = z = None
dans = False
for l in g.split("\n"):
    if l.startswith("(====="):
        dans = "Lignes a rampe" in l or "rampe de puissance" in l
    mx = re.search(r"\bX(-?\d+\.?\d*)", l)
    mz = re.search(r"\bZ(-?\d+\.?\d*)", l)
    if mx:
        x = float(mx.group(1))
    if mz:
        z = float(mz.group(1))
    if dans and l.startswith("G1 ") and None not in (x, z) and z <= Z_FIN + 1e-6:
        traj.append((x, z))
assert traj, "aucune trajectoire de rampe relevée"

for attendu, xt in zip((5.0, 10.0, 15.0, 20.0), sorted(verticaux)):
    z_reel = min(traj, key=lambda p: abs(p[0] - xt))[1]
    obtenu = z_reel - Z_FOYER
    # Tolérance = un palier de rampe : 20 mm de Z sur 40 paliers = 0,5 mm.
    assert abs(obtenu - attendu) < 0.55, (attendu, obtenu, xt)
    print("   graduation « {:.0f} » en X={:.2f} : Z réel {:.3f} -> défocus "
          "{:.2f} mm OK".format(attendu, xt, z_reel, obtenu))
print("3. chaque graduation tombe sur le défocus qu'elle annonce, mesuré sur "
      "la vraie trajectoire OK")

# --- 4. Sans rampe Z, aucune graduation de hauteur ----------------------
vus2 = []
core.text_to_edges_vertical = lambda txt, *a, **k: (vus2.append(txt)
                                                    or vrai(txt, *a, **k))
try:
    plat = core.generate_gcode_power_ramp_lines(
        line_length=LONGUEUR, n_lines=4, feed_min=200.0, feed_max=800.0,
        power_min=200.0, power_max=1000.0, z_work=Z_FOYER,
        line_gap=10.0, z_end=None, n_steps=40, quiet=True)
finally:
    core.text_to_edges_vertical = vrai
assert plat and "Hauteur Z" not in plat, "annonce une rampe Z sans rampe Z"
assert "5" not in vus2 and "20" not in vus2, ("graduations de défocus sans "
                                             "rampe Z", vus2)
print("4. z_end=None : ni annonce ni graduation de défocus OK")

print("\nTOUS LES TESTS rampe_z PASSENT")
