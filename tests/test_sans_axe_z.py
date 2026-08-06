# -*- coding: utf-8 -*-
"""Une machine sans axe Z ne doit recevoir aucun mot Z.

Christophe, 06/08/2026 : « j'ai un petit laser Creality Falcon 2, mon
atelier laser est compatible ? ». Le dialecte GRBL existait et convenait ;
ce qui bloquait était ailleurs.

TOUT FICHIER PRODUIT ICI PORTE DES Z, même le plus simple. Mesuré avant
d'écrire une ligne : un marquage à plat, Z de travail 0 ET survol 0, sort
encore un `G0 Z5.0000` -- la hauteur de sécurité de début et de fin,
`+ 5.0` en dur dans le générateur. Sur un graveur à mise au point manuelle,
le contrôleur accepte ce mot, croit déplacer un axe absent, y passe du
temps, et lève une alarme de limite logicielle si elles sont actives
(course Z nulle).

Le retrait se fait à la SORTIE (`sanitize_gcode_for_linuxcnc`), passage
obligé des dix familles de générateurs : un seul point à écrire, un seul à
tester, et le prochain mode en hérite.

ET IL S'ANNONCE QUAND LE Z PORTAIT DE L'INFORMATION. Ôter une hauteur de
survol ne change rien à ce qui brûle ; ôter un Z qui VARIAIT pendant un
`G1`, c'est supprimer le défocus, le fuseau ou le suivi de relief -- le
fichier ne grave plus ce qui a été calculé, et rien à l'écran ne le dirait.
"""
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core
MAT = u"Hêtre"

# Un Z est un mot de commande : la lettre suivie d'un nombre, et jamais
# précédée d'un caractère de mot (sinon « XYZ12 » dans un commentaire
# compterait).
RX_Z = re.compile(r'(?<![A-Za-z0-9.])Z-?\d+\.?\d*')


def poser(sans_z, dialecte="grbl"):
    """Passe par la config JETABLE et le vrai `_apply_settings_config` --
    forcer la constante à la main ne prouverait rien sur le chemin réel."""
    cfg = core.load_config()
    s = cfg.setdefault("settings", {})
    s["machine_sans_axe_z"] = sans_z
    s["gcode_dialect"] = dialecte
    s["puissance_par_m67"] = False
    core.save_config(cfg)
    core._apply_settings_config()


def familles():
    """Un job par famille de générateur."""
    img = [[min(1.0, ((x * 7 + y * 5) % 100) / 99.0) for x in range(40)]
           for y in range(30)]
    out = {
        "lignes enflées": core.generate_gcode_photo_swell_lines(
            img, 0.30, core.Z_WORK_MM, 800.0, MAT, line_min_mm=0.10,
            quiet=True),
        "points": core.generate_gcode_halftone(
            img, 0.8, core.Z_WORK_MM, 500.0, 0.010, 0.060, quiet=True),
        "planche défocus": core.generate_gcode_planche_defocus(
            z_focus=core.Z_WORK_MM, quiet=True),
        "rampe de puissance": core.generate_gcode_power_ramp_lines(
            line_length=60.0, n_lines=3, feed_min=200.0, feed_max=800.0,
            power_min=200.0, power_max=1000.0, z_work=core.Z_WORK_MM,
            line_gap=10.0, z_end=core.Z_WORK_MM + 20.0, quiet=True),
    }
    import FreeCAD                                            # noqa: E402
    import Part                                               # noqa: E402

    def seg(a, b):
        return Part.LineSegment(FreeCAD.Vector(*a), FreeCAD.Vector(*b)).toShape()

    carre = [seg((0, 0, 0), (40, 0, 0)), seg((40, 0, 0), (40, 40, 0)),
             seg((40, 40, 0), (0, 40, 0)), seg((0, 40, 0), (0, 0, 0))]
    out["marquage"] = core.generate_gcode_curved(
        carre, power=600, feed=1200, z_focus=core.Z_WORK_MM,
        marge_survol=0.5, quiet=True)
    out["marquage vague"] = core.generate_gcode_curved(
        carre, power=600, feed=1200, z_focus=core.Z_WORK_MM, marge_survol=0.5,
        style="vague", style_params={"wave_amplitude": 4.0,
                                     "wave_period": 10.0}, quiet=True)
    return {k: v for k, v in out.items() if v}


print("=" * 62)
print("§1  Avec un axe Z, RIEN NE CHANGE")
print("=" * 62)

poser(False)
avec = familles()
for nom, g in sorted(avec.items()):
    print("   %-20s %d mots Z" % (nom, len(RX_Z.findall(g))))
assert any(RX_Z.findall(g) for g in avec.values()), (
    "aucune famille n'émet de Z : ce test ne peut rien prouver")
assert core.MARQUE_SANS_AXE_Z not in "".join(avec.values()), (
    "la mention « sans axe Z » apparaît alors que le réglage est éteint")

print()
print("=" * 62)
print("§2  Sans axe Z, PLUS UN SEUL mot Z sur toutes les familles")
print("=" * 62)

poser(True)
sans = familles()
assert set(sans) == set(avec), (
    "des familles ont disparu : %s" % (set(avec) ^ set(sans)))
for nom in sorted(sans):
    restants = RX_Z.findall(sans[nom])
    print("   %-20s %4d mots Z avant -> %s"
          % (nom, len(RX_Z.findall(avec[nom])), restants or "AUCUN"))
    assert not restants, (
        "« %s » porte encore %d mots Z : %s"
        % (nom, len(restants), restants[:5]))

print()
print("=" * 62)
print("§3  Aucun mouvement ORPHELIN, aucun commentaire cassé")
print("=" * 62)

# Un `G0 Z5` dont on ôte le Z laisserait un « G0 » seul -- que GRBL lit
# comme un déplacement vers la position courante : inutile, et trompeur.
# Et un commentaire doit rester SUR SA LIGNE : la première version collait
# la mention d'alerte APRÈS la parenthèse fermante, donc l'interpréteur
# l'aurait lue comme du CODE. C'est le piège que ce dépôt documente déjà.
orphelins, casses = [], []
for nom, g in sorted(sans.items()):
    for ligne in g.splitlines():
        nu = ligne.strip()
        if nu in ("G0", "G1", "G00", "G01"):
            orphelins.append((nom, ligne))
        if nu.count("(") != nu.count(")"):
            casses.append((nom, nu[:60]))
        # Rien ne doit suivre un commentaire refermé.
        fin = nu.rfind(")")
        if fin != -1 and nu[fin + 1:].strip():
            casses.append((nom, nu[:70]))
print("   mouvements réduits à « G0 » seul : %s" % (orphelins or "aucun"))
print("   commentaires mal formés          : %s" % (casses or "aucun"))
assert not orphelins, orphelins
assert not casses, casses

print()
print("=" * 62)
print("§4  Le Z qui portait de l'INFORMATION est signalé")
print("=" * 62)

# La distinction qui fait de ce réglage un outil plutôt qu'un piège :
# une hauteur de survol retirée ne change rien à ce qui brûle, un Z qui
# variait pendant un G1 change TOUT.
plat = sans["marquage"].splitlines()[0]
vague = sans["marquage vague"].splitlines()[0]
print("   marquage à plat : %s" % plat)
print("   style « vague » : %s" % vague)
assert core.MARQUE_SANS_AXE_Z in plat, "le fichier ne dit pas que des Z ont été ôtés"
assert "ATTENTION" not in plat, (
    "un marquage à plat n'a perdu que des hauteurs de survol : l'alerte "
    "crierait au loup, et on cesserait de la lire")
assert "ATTENTION" in vague, (
    "le style « vague » grave à hauteur variable ; retirer son Z sans le "
    "dire livre un fichier qui ne grave PAS ce qui a été calculé")
nb = int(re.search(r"ATTENTION : (\d+)", vague).group(1))
print("   %d mouvements gravés changeaient de hauteur" % nb)
assert nb > 10, "compte suspect : %d" % nb

print()
print("=" * 62)
print("§5  Idempotent, et réversible")
print("=" * 62)

# Un job combiné réassainit des corps DÉJÀ assainis : un second passage ne
# doit ni réempiler la mention, ni abîmer le texte.
#
# DEUX GARDE-FOUS INDÉPENDANTS le tiennent, et c'est mesuré : le retour
# anticipé quand il n'y a plus rien à retirer, et la garde qui ne réécrit
# la mention que si elle manque. En casser UN SEUL laisse la propriété
# debout -- le sabotage ne rougit pas, et cette section aurait pu passer
# pour un contrôle inutile. En casser les DEUX rougit bien. C'est noté ici
# pour qu'on ne conclue pas, la prochaine fois, que le test est décoratif.
deux = core.sanitize_gcode_for_linuxcnc(sans["marquage"])
print("   second passage identique : %s" % (deux == sans["marquage"]))
assert deux == sans["marquage"], "l'assainisseur n'est plus idempotent"
assert deux.count(core.MARQUE_SANS_AXE_Z) == 1, (
    "la mention a été empilée %d fois" % deux.count(core.MARQUE_SANS_AXE_Z))

poser(False)
retour = familles()
for nom in sorted(retour):
    assert RX_Z.findall(retour[nom]), (
        "« %s » n'a plus de Z une fois le réglage décoché : la constante "
        "est restée collée" % nom)
print("   réglage décoché : les Z sont revenus sur les %d familles"
      % len(retour))

print()
print("=" * 62)
print("§6  Le réglage est PAR LASER, et la case existe")
print("=" * 62)

assert "machine_sans_axe_z" in core.PER_LASER_KEYS, (
    "le réglage n'est pas par profil laser : un profil = une machine, et "
    "on en a deux quand on possède deux graveurs")
assert "machine_sans_axe_z" in dict((c[0], c[1]) for c in core._USER_SETTINGS)
import io as _io                                              # noqa: E402
_src = _io.open("/home/christophe/.local/share/FreeCAD/v1-1/Mod/"
                "LaserAtelier/task_panels.py", encoding="utf-8").read()
assert "chk_sans_z" in _src and '"machine_sans_axe_z": self.chk_sans_z' in _src, (
    "les Préférences n'offrent pas la case, ou ne l'enregistrent pas : un "
    "réglage inatteignable n'est pas livré")
print("   par laser : ✓   case dans les Préférences : ✓")

print()
print("TOUT EST VERT")
