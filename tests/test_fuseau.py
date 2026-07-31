# -*- coding: utf-8 -*-
"""Style « Dégradé le long du tracé » (Marquage) : le trait qui s'affine.

Ce que ce style promet : la largeur suit l'ABSCISSE CURVILIGNE, du premier
au dernier point de CHAQUE trait. À ne pas confondre avec le « Dégradé
(dans une direction) » qui existait déjà et rampe selon une direction de
l'espace : sur une droite orientée comme cette direction les deux
coïncident, mais sur une spirale ou une courbe qui revient sur elle-même,
l'ancien suit la POSITION et non le parcours.

Deux décisions de Christophe que ces tests figent (31/07/2026) :
  - chaque trait sélectionné porte sa rampe ENTIÈRE, donc le résultat ne
    dépend pas de l'ordre de parcours (choisi pour le trajet, pas pour le
    dessin) ;
  - sur une boucle fermée, le comportement est au CHOIX : marche visible
    à la fermeture, ou aller-retour qui referme sans raccord.
"""
import re

from harness import preparer

# `preparer()` D'ABORD, et SEULEMENT ENSUITE Part/FreeCAD : c'est lui qui
# initialise l'interpréteur FreeCAD. Importer `Part` avant fait un
# SEGFAULT sec, sans la moindre trace -- le lanceur n'affiche alors qu'un
# « ÉCHEC » vide, ce qui ressemble à tout sauf à un problème d'import.
# Aucun autre test du dépôt n'importe Part au niveau module ; celui-ci est
# le premier, d'où ce commentaire.
h = preparer()

import Part            # noqa: E402  (cf. ci-dessus)
import FreeCAD         # noqa: E402

core, tp = h.core, h.tp
V = FreeCAD.Vector


def seg(a, b):
    return Part.LineSegment(a, b).toShape()


# --- 1. Chaîne ouverte : rampe monotone d'un bout à l'autre -------------
droite = [V(i * 2.0, 0, 0) for i in range(51)]
dz = core.rampe_trace_dz(droite, 0.0, 64.8)
assert abs(dz[0]) < 1e-9 and abs(dz[-1] - 64.8) < 1e-9, (dz[0], dz[-1])
assert all(b >= a - 1e-9 for a, b in zip(dz, dz[1:])), "rampe non monotone"
assert abs(dz[len(dz) // 2] - 32.4) < 0.5, dz[len(dz) // 2]
print("1. trait ouvert : rampe monotone {:.1f} -> {:.1f} mm, moitié à {:.1f} "
      "OK".format(dz[0], dz[-1], dz[len(dz) // 2]))

# --- 2. Un VRAI cercle FreeCAD est bien vu comme fermé ------------------
# La question de départ portait sur le cercle : encore faut-il que le
# discrétiseur rende une chaîne dont les deux bouts coïncident.
cercle_shape = Part.Wire([Part.Circle(V(0, 0, 0), V(0, 0, 1), 20.0).toShape()])
chaines = core.chain_edges(cercle_shape.Edges)
assert len(chaines) == 1, len(chaines)
cercle = chaines[0]
assert core.chaine_fermee(cercle), (
    "un cercle discrétisé doit être reconnu fermé", cercle[0], cercle[-1])
assert not core.chaine_fermee(droite), "une droite n'est pas fermée"
print("2. cercle Ø40 discrétisé en {} points : reconnu FERMÉ ; droite : "
      "ouverte OK".format(len(cercle)))

# --- 3. Boucle fermée : les deux comportements, au choix ---------------
marche = core.rampe_trace_dz(cercle, 0.0, 64.8, aller_retour=False)
assert abs(marche[-1] - 64.8) < 1e-6, marche[-1]
ressaut = abs(marche[-1] - marche[0])
assert ressaut > 60.0, ("la marche doit être franche", ressaut)

va_et_vient = core.rampe_trace_dz(cercle, 0.0, 64.8, aller_retour=True)
assert abs(va_et_vient[-1] - va_et_vient[0]) < 1e-6, (
    "l'aller-retour doit refermer la boucle sans raccord",
    va_et_vient[0], va_et_vient[-1])
milieu = va_et_vient[len(va_et_vient) // 2]
assert abs(milieu - 64.8) < 0.5, (
    "en aller-retour, la largeur de FIN est atteinte à mi-parcours", milieu)
print("3. boucle fermée : marche = ressaut de {:.1f} mm ; aller-retour = "
      "ressaut de {:.3f} mm, sommet à mi-parcours ({:.1f}) OK".format(
          ressaut, abs(va_et_vient[-1] - va_et_vient[0]), milieu))

# --- 4. Sur un trait OUVERT, l'aller-retour est ignoré ------------------
# Sinon « largeur à la fin » ne voudrait plus rien dire.
assert core.rampe_trace_dz(droite, 0.0, 64.8) == \
    core.rampe_trace_dz(droite, 0.0, 64.8, aller_retour=True)
print("4. trait ouvert : l'option aller-retour est ignorée, la fin reste la "
      "fin OK")

# --- 5. Le bec ne DESCEND jamais sous le suivi de relief ---------------
# Le contrôle anti-collision est fait sur le Z natif du point : il n'est
# conservateur que si le style ne fait que MONTER. Vrai dans les deux sens
# de rampe (large->fin comme fin->large).
for a, b in ((0.0, 64.8), (64.8, 0.0), (12.0, 30.0)):
    for ch, ar in ((droite, False), (cercle, False), (cercle, True)):
        assert min(core.rampe_trace_dz(ch, a, b, ar)) >= -1e-9, (a, b, ar)
print("5. dz jamais négatif : le bec ne descend jamais sous le relief, le "
      "contrôle de collision reste conservateur OK")

# --- 6. Chaque trait porte sa rampe ENTIÈRE ----------------------------
# Deux traits de longueurs DIFFÉRENTES : même course Z, donc un résultat
# indépendant de l'ordre de parcours et du nombre d'objets sélectionnés.
g = core.generate_gcode_curved(
    [seg(V(0, 0, 0), V(100, 0, 0)), seg(V(0, 20, 0), V(60, 20, 0))],
    power=800, feed=400, z_focus=core.Z_WORK_MM, marge_survol=0.0,
    style="degrade_trace",
    style_params={"deg_z_min": 64.8, "deg_z_max": 0.0}, quiet=True)
assert g, "aucun G-code"
assert "degrade le long du TRACE" in g, [l for l in g.split("\n") if "Style" in l]

blocs, cur = [], []
for l in g.split("\n"):
    if l.startswith("G0 X") and cur:
        blocs.append(cur)
        cur = []
    m = re.match(r"G1 X([-\d.]+) Y([-\d.]+) Z([-\d.]+)", l)
    if m:
        cur.append(tuple(float(m.group(i)) for i in (1, 2, 3)))
if cur:
    blocs.append(cur)
assert len(blocs) == 2, len(blocs)
courses = [abs(b[0][2] - b[-1][2]) for b in blocs]
assert all(c > 60.0 for c in courses), courses
assert abs(courses[0] - courses[1]) < 0.5, (
    "les deux traits doivent faire la même course Z", courses)
print("6. deux traits de 100 et 60 mm : courses Z {:.1f} et {:.1f} mm -- "
      "chacun porte sa rampe entière OK".format(*courses))

# --- 7. L'approche porte déjà le décalage du premier point -------------
# Sans ça, le premier G1 sauterait de 64,8 mm sur une fraction de mm de
# déplacement XY -- le même défaut que celui corrigé jadis sur "degrade".
lignes = g.split("\n")
i = next(k for k, l in enumerate(lignes) if l.startswith("G1 X"))
z_appro = [float(m.group(1)) for l in lignes[:i]
           for m in [re.match(r"G0 Z([-\d.]+)", l)] if m]
z_premier = float(re.match(r"G1 X[-\d.]+ Y[-\d.]+ Z([-\d.]+)",
                           lignes[i]).group(1))
saut = abs(z_appro[-1] - z_premier)
assert saut < 1.0, ("l'approche ne porte pas le décalage de la rampe",
                    z_appro[-1], z_premier, saut)
print("7. approche à Z={:.2f}, premier G1 à Z={:.2f} : saut de {:.2f} mm au "
      "lieu de 64,8 OK".format(z_appro[-1], z_premier, saut))

# --- 8. Le panneau : style câblé, champs visibles, réglages mémorisés --
p = tp.TaskPanelCurved([])
assert p.combo_style.count() == 7, p.combo_style.count()
p.combo_style.setCurrentIndex(6)
assert p._style_kwargs()["style"] == "degrade_trace"
for w in (p.spn_deg_w0, p.spn_deg_w1, p.combo_deg_boucle):
    assert not w.isHidden(), "un champ du fuseau est caché sur son style"
assert p.spn_deg_angle.isHidden(), (
    "l'angle appartient au dégradé SPATIAL, pas à celui du tracé")
p.combo_style.setCurrentIndex(5)
assert not p.spn_deg_angle.isHidden() and p.combo_deg_boucle.isHidden()

# Les 4 champs du dégradé n'étaient NI mémorisés NI enregistrés en
# préréglage depuis leur création : un fuseau réglé se perdait à la
# fermeture du panneau.
for cle in ("deg_angle", "deg_w0", "deg_w1", "deg_boucle"):
    assert cle in p._last_fields, (cle, sorted(p._last_fields))
print("8. panneau : 7 styles, champs du fuseau visibles sur le bon, angle "
      "réservé au dégradé spatial, 4 réglages mémorisés OK")


# --- 9. L'APERÇU doit montrer le fuseau, pas une largeur moyenne -------
# Signalé le 31/07/2026 sur un 0,3 -> 3 mm rendu en trait fin uniforme :
# l'aperçu calculait UNE largeur pour tout le dessin. Le style « le long
# du tracé » tombait même dans le repli « plein » (largeur au foyer), et
# le dégradé directionnel peignait la MOYENNE des deux valeurs. Un aperçu
# qui ne montre pas ce qu'on va obtenir est pire qu'aucun aperçu.
p._edges = [seg(V(0, 0, 0), V(120, 0, 0))]
p.spn_power.setValue(800)
p.spn_feed.setValue(400)
p.spn_deg_w0.setValue(0.3)
p.spn_deg_w1.setValue(3.0)
for idx in (5, 6):
    p.combo_style.setCurrentIndex(idx)
    st = p._strokes_degrade(idx, 800.0, 400.0, 0.85)
    assert len(st) > 50, ("l'aperçu doit découper le tracé pour varier la "
                          "largeur", idx, len(st))
    larg = [w for _pts, w, _t in st]
    assert abs(larg[0] - 0.30) < 0.05, (idx, larg[0])
    assert abs(larg[-1] - 3.00) < 0.05, (idx, larg[-1])
    assert all(b >= a - 1e-9 for a, b in zip(larg, larg[1:])), (
        "la largeur peinte doit croître comme la rampe", idx)
    # Le défaut d'origine : une seule largeur constante partout.
    assert max(larg) - min(larg) > 2.0, (
        "l'aperçu peint une largeur quasi constante", idx, min(larg), max(larg))
print("9. aperçu des deux dégradés : {} morceaux, largeur peinte 0.30 -> 3.00 "
      "mm et croissante -- plus de trait uniforme OK".format(len(st)))

# --- 10. Aperçu et G-code sortent des MÊMES rampes ---------------------
# `rampe_direction_dz` était une fermeture interne au générateur : l'aperçu
# ne pouvait que la ré-inventer. Elle est désormais partagée, comme
# `rampe_trace_dz`. On vérifie que l'aperçu passe bien par les deux.
vraies = (core.rampe_direction_dz, core.rampe_trace_dz)
appels = {"dir": 0, "trace": 0}
core.rampe_direction_dz = lambda *a, **k: (
    appels.__setitem__("dir", appels["dir"] + 1) or vraies[0](*a, **k))
core.rampe_trace_dz = lambda *a, **k: (
    appels.__setitem__("trace", appels["trace"] + 1) or vraies[1](*a, **k))
try:
    p.combo_style.setCurrentIndex(5)
    p._strokes_degrade(5, 800.0, 400.0, 0.85)
    p.combo_style.setCurrentIndex(6)
    p._strokes_degrade(6, 800.0, 400.0, 0.85)
finally:
    core.rampe_direction_dz, core.rampe_trace_dz = vraies
assert appels["dir"] >= 1 and appels["trace"] >= 1, appels
print("10. l'aperçu appelle rampe_direction_dz ({}) et rampe_trace_dz ({}) : "
      "il ne peut pas dessiner une autre rampe que le G-code OK".format(
          appels["dir"], appels["trace"]))

print("\nTOUS LES TESTS fuseau PASSENT")
