# -*- coding: utf-8 -*-
"""AUCUN TRANSIT NE SE FAIT FAISCEAU ALLUMÉ.

Un `G0` est un déplacement à vide : la tête vole d'un trait au suivant,
et rien ne doit brûler entre les deux. Mais la puissance est MODALE en
RS274 -- un `S` posé sur un bloc reste en vigueur jusqu'au suivant --,
donc « ne rien écrire » ne veut pas dire « faisceau coupé » : ça veut
dire « la puissance d'avant est toujours commandée ».

CE QUE ÇA A COÛTÉ, trouvé à la lecture ligne à ligne du 02/09/2026. La
calligraphie coupait son faisceau entre deux gestes par
`cmd_power_prefix(0.0)`. Or ce préfixe ne rend RIEN en canal S direct
(là, la puissance voyage sur le G1 lui-même, il n'y a pas de préfixe à
poser) : la ligne n'écrivait aucune commande. Mesuré sur deux gestes
distants de 50 mm -- quatre G0 parcourus à S1000, dont la traversée
complète entre les deux lettres, à pleine puissance. En M67 le même
appel écrivait « M67 E0 Q0 » et coupait bien : le défaut ne se voyait
que dans l'AUTRE canal, celui du réglage par défaut, et celui que GRBL
impose sans qu'on ait le choix.

Ce test ne vérifie donc pas un site mais une PROPRIÉTÉ, sur toute la
famille et DANS LES DEUX CANAUX -- la moitié du travail, ici, c'est de
tester les deux, puisque le défaut se cachait dans celui qu'on ne
regardait pas.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import preparer, canal_puissance

h = preparer()
core = h.core
MAT = u"Hêtre"

# Un matériau au fuseau complet pour la calligraphie : deux puissances au
# foyer et deux à défocus 15, ce qu'exige `echelle_fuseau_z`.
core.save_burn_widths(u"EssaiTransit", {
    "focus":   [{"power": 200.0, "feed": 800.0, "width": 0.12},
                {"power": 900.0, "feed": 800.0, "width": 0.30}],
    "defocus": [{"power": 200.0, "feed": 800.0, "z_offset": 15.0, "width": 0.70},
                {"power": 900.0, "feed": 800.0, "z_offset": 15.0, "width": 1.30}],
})


def tous_les_gcodes():
    """Un G-code par famille qui allume le faisceau et transite entre."""
    img = [[min(1.0, ((x * 7 + y * 5) % 100) / 99.0) for x in range(24)]
           for y in range(18)]
    out = {}
    out["halftone"] = core.generate_gcode_halftone(
        img, 0.8, core.Z_WORK_MM, 500.0, 0.010, 0.060, quiet=True)
    out["dither"] = core.generate_gcode_photo_dither_lines(
        img, 0.8, core.Z_WORK_MM, 500.0, 2000.0, quiet=True)
    out["am"] = core.generate_gcode_photo_am(
        img, 0.30, core.Z_WORK_MM, 1000.0, 800.0, quiet=True)
    out["enfle"] = core.generate_gcode_photo_swell_lines(
        img, 0.30, core.Z_WORK_MM, 800.0, MAT, quiet=True)
    out["zdots"] = core.generate_gcode_photo_zdots(
        img, 0.75, core.Z_WORK_MM, 300.0, core.SPOT_FOCUS_MM, 0.60,
        0.010, 0.060, quiet=True)
    out["lignes"] = core.generate_gcode_photo_lines(
        img, 0.80, core.Z_WORK_MM + 15.0, 2000.0, 0.80, MAT, quiet=True)
    out["rampe"] = core.generate_gcode_power_ramp_lines(
        line_length=60.0, n_lines=3, feed_min=200.0, feed_max=800.0,
        power_min=200.0, power_max=1000.0, z_work=core.Z_WORK_MM,
        line_gap=10.0, z_end=core.Z_WORK_MM + 20.0, quiet=True)
    out["planche1"] = core.generate_gcode_planche_focus(
        z_focus=core.Z_WORK_MM, quiet=True)
    out["planche2"] = core.generate_gcode_planche_defocus(
        z_focus=core.Z_WORK_MM, quiet=True)
    out["bande_defocus"] = core.generate_gcode_defocus_calibration(
        z_start=core.Z_WORK_MM, z_step=3.0, n_marks=6, mark_length=15.0,
        row_gap=6.0, power=600.0, feed=800.0, quiet=True)
    # LA CALLIGRAPHIE, celle qui a payé : deux gestes bien séparés, pour
    # que la traversée entre eux existe vraiment.
    out["calligraphie"] = core.generate_gcode_calligraphie(
        [[(0.0, 10.0, 0.15), (0.0, 0.0, 0.45)],
         [(50.0, 10.0, 0.15), (50.0, 0.0, 0.45)]],
        z_work=core.Z_WORK_MM, feed=800.0, material=u"EssaiTransit",
        quiet=True)
    # Fuseau Z : le Z porte la largeur, le faisceau se coupe quand même.
    out["spirale_fuseau"] = core.generate_gcode_photo_spirale(
        [[1.0] * 12 for _ in range(12)], 1.0, core.Z_WORK_MM, 800.0,
        u"EssaiTransit", fuseau_z=True, quiet=True)
    out["rangees_fuseau"] = core.generate_gcode_photo_swell_lines(
        [[1.0] * 12 for _ in range(12)], 1.0, core.Z_WORK_MM, 800.0,
        u"EssaiTransit", fuseau_z=True, quiet=True)
    return {k: v for k, v in out.items() if v}


def transits_allumes(gcode):
    """Les `G0` parcourus avec une puissance non nulle encore commandée.

    On REJOUE la modalité, on ne cherche pas un mot sur la ligne : c'est
    justement l'absence de mot qui laissait le faisceau allumé."""
    s = 0.0
    fautes = []
    for brut in gcode.split("\n"):
        ligne = brut.strip()
        if not ligne or ligne.startswith("("):
            continue
        if ligne.startswith("M67"):
            try:
                s = float(ligne.split("Q")[1].split()[0])
            except (IndexError, ValueError):
                pass
        else:
            for mot in ligne.split():
                if mot[:1] == "S" and mot[1:].replace(".", "", 1).isdigit():
                    s = float(mot[1:])
        if ligne.startswith("G0") and s > 0:
            fautes.append((ligne, s))
    return fautes


for m67 in (False, True):
    canal_puissance(core, m67=m67)
    nom_canal = "M67 synchronisé" if m67 else "S direct"
    gcodes = tous_les_gcodes()
    assert len(gcodes) >= 12, (nom_canal, sorted(gcodes))
    for nom, g in sorted(gcodes.items()):
        fautes = transits_allumes(g)
        assert not fautes, (
            "{} / {} : {} transit(s) G0 faisceau ALLUMÉ, p.ex. {!r} à "
            "S{:.0f}".format(nom_canal, nom, len(fautes), fautes[0][0],
                             fautes[0][1]))
    print("   {:<16} {:2d} générateurs, aucun G0 allumé".format(
        nom_canal, len(gcodes)))
canal_puissance(core, m67=False)

print()
print("TOUT EST VERT")
