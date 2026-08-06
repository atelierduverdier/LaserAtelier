# -*- coding: utf-8 -*-
"""L'assistance d'air : allumée avant le premier trait, coupée UNE fois.

Christophe, 06/08/2026, après avoir envoyé un fichier LightBurn qui a
vraiment tourné sur son Creality Falcon 2 : « fais une case dédiée ».

LE TITRE DE CE FICHIER A DÛ ÊTRE CORRIGÉ, et ça vaut d'être dit : il
promettait « une paire M8/M9, jamais plus », ce qui était mon hypothèse.
§2 explique pourquoi c'est faux, et quelle est la vraie propriété.

CE FICHIER EST LA RÉFÉRENCE, pas un raisonnement. LightBurn 1.3.01, profil
GRBL, pose `M8` juste après `M4` et `M9` AVANT le `S0`/`M5` final. On
reproduit cet ordre tel quel : un fichier qui a gravé vaut mieux que ce
qu'on croit savoir de l'ordre des commandes.

GREFFÉ SUR CMD_ARM / CMD_DISARM, ET NON DANS CHAQUE GÉNÉRATEUR. Ces deux
modèles sont émis par les dix familles -- 35 et 50 points d'appel -- et une
seule fois par fichier, y compris en job combiné où `body_only` supprime
l'armement des corps. Un M8 par opération aurait rallumé l'air à chaque
sous-job.

ET ÇA CHANGE CE QUI BRÛLE. L'atelier documente depuis juillet que l'air
fait un halo brun autour du trait, propre sans lui : c'est la variable
cachée qu'aucune planche de mesure n'enregistre. D'où le réglage PAR LASER
-- un profil, une machine, un régime.
"""
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core
MAT = u"Hêtre"


def poser(air, dialecte="grbl", m67=False):
    """Par la config JETABLE et le vrai `_apply_settings_config`."""
    cfg = core.load_config()
    s = cfg.setdefault("settings", {})
    s["assistance_air"] = air
    s["gcode_dialect"] = dialecte
    s["puissance_par_m67"] = m67
    s["machine_sans_axe_z"] = False
    core.save_config(cfg)
    core._apply_settings_config()


def familles():
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
    return {k: v for k, v in out.items() if v}


def mots(texte, mot):
    """Compte un mot de commande hors commentaire."""
    n = 0
    for ligne in texte.splitlines():
        code = ligne.split("(")[0]
        n += len(re.findall(r'(?<![A-Za-z0-9]){}(?![0-9])'.format(mot), code))
    return n


print("=" * 62)
print("§1  Décochée, AUCUN M8 ni M9 -- les fichiers d'avant sont intacts")
print("=" * 62)

poser(False)
sans = familles()
for nom, g in sorted(sans.items()):
    print("   %-20s M8=%d  M9=%d" % (nom, mots(g, "M8"), mots(g, "M9")))
    assert mots(g, "M8") == 0 and mots(g, "M9") == 0, (
        "« %s » émet de l'air alors que le réglage est éteint" % nom)

print()
print("=" * 62)
print("§2  Cochée : de l'air au début, coupé UNE SEULE FOIS à la fin")
print("=" * 62)

# LA PREMIÈRE VERSION DEMANDAIT « EXACTEMENT UN M8 », ET C'ÉTAIT MON
# HYPOTHÈSE, PAS UNE EXIGENCE. La planche défocus l'a fait tomber : elle
# grave le cadrage, DÉSARME, s'arrête sur un M0 pour qu'on vérifie le
# placement sur la planche, puis réarme --
#     M4 -> M8 -> [cadrage] -> M5 -> M0 -> M4 -> M8 -> [planche] -> M9 -> M5
# donc deux M8, et ils sont justes : un M8 sur une pompe déjà en marche ne
# fait rien. Ce qui doit être unique, c'est la COUPURE : un M9 de trop, et
# la fin du job grave sans air, sans qu'un mot le dise.
poser(True)
avec = familles()
assert set(avec) == set(sans), "des familles ont disparu"
for nom, g in sorted(avec.items()):
    n8, n9 = mots(g, "M8"), mots(g, "M9")
    print("   %-20s M8=%d  M9=%d" % (nom, n8, n9))
    assert n8 >= 1, "« %s » n'allume jamais l'air" % nom
    assert n9 == 1, (
        "« %s » coupe l'air %d fois : la seule coupure doit être la finale, "
        "sans quoi une partie du job grave sans air" % (nom, n9))

print()
print("=" * 62)
print("§3  L'ORDRE du fichier qui a tourné : M8 après l'armement,")
print("    M9 avant le désarmement")
print("=" * 62)

# Vérifié sur DEUX fichiers, dont celui qui arme deux fois : une propriété
# testée sur le cas le plus simple ne dit rien du cas tordu.
for nom in ("marquage", "planche défocus"):
    lignes = [l.split("(")[0].strip() for l in avec[nom].splitlines()]
    i8 = next(i for i, l in enumerate(lignes) if re.match(r'^M8\b', l))
    i9 = next(i for i, l in enumerate(lignes) if re.match(r'^M9\b', l))
    i_arme = next(i for i, l in enumerate(lignes) if re.match(r'^M[34]\b', l))
    i_desarme = max(i for i, l in enumerate(lignes) if re.match(r'^M5\b', l))
    # LE DERNIER TRAIT EST LE DERNIER G1, pas le dernier mot S : un
    # marquage pose sa puissance UNE fois puis enchaîne des G1 nus, si bien
    # qu'un repère cherché sur « S » tombait à la ligne 16 d'un fichier qui
    # en compte 557 -- le contrôle passait sans rien contrôler.
    faisceaux = [i for i, l in enumerate(lignes)
                 if i > i_arme and re.match(r'^G1\b', l)]
    print("   %-16s armement %d | M8 %d | 1er trait %d | dernier %d | "
          "M9 %d | M5 %d"
          % (nom, i_arme, i8, faisceaux[0], faisceaux[-1], i9, i_desarme))
    assert i_arme < i8 < faisceaux[0], (
        "« %s » : M8 n'est pas entre l'armement et le premier trait gravé -- "
        "l'air arriverait après le début de la coupe" % nom)
    assert i9 < i_desarme, (
        "« %s » : M9 doit précéder le M5 final -- c'est l'ordre du fichier "
        "LightBurn qui a tourné sur le Falcon" % nom)
    assert i9 > faisceaux[-1], (
        "« %s » : l'air est coupé AVANT le dernier trait gravé" % nom)

print()
print("=" * 62)
print("§4  UN SEUL couple sur un job COMBINÉ")
print("=" * 62)

# C'est le cas qui justifie la greffe sur CMD_ARM plutôt qu'un M8 par
# générateur : `body_only` retire l'armement des corps, le wrapper arme une
# fois. Un M8 posé dans chaque générateur en aurait mis autant que
# d'opérations, et rallumé une pompe déjà en marche.
ops = []
for nom in ("planche défocus", "rampe de puissance"):
    ops.append(avec[nom])
combine = core.generate_gcode_combined([
    {"type": "brut", "label": nom, "body": avec[nom]}
    for nom in ("planche défocus", "rampe de puissance")
]) if hasattr(core, "generate_gcode_combined") else None

if combine:
    print("   job combiné : M8=%d  M9=%d" % (mots(combine, "M8"),
                                             mots(combine, "M9")))
    assert mots(combine, "M8") <= 1 and mots(combine, "M9") <= 1, (
        "le job combiné rallume l'air à chaque opération")
else:
    # À défaut du wrapper, on vérifie la propriété qui le garantit : l'air
    # voyage sur l'armement, et un corps `body_only` n'en porte pas.
    import FreeCAD                                            # noqa: E402
    import Part                                               # noqa: E402

    def seg(a, b):
        return Part.LineSegment(FreeCAD.Vector(*a),
                                FreeCAD.Vector(*b)).toShape()

    corps = core.generate_gcode_curved(
        [seg((0, 0, 0), (30, 0, 0))], power=600, feed=1200,
        z_focus=core.Z_WORK_MM, marge_survol=0.5, body_only=True, quiet=True)
    print("   corps body_only : M8=%d  M9=%d" % (mots(corps, "M8"),
                                                 mots(corps, "M9")))
    assert mots(corps, "M8") == 0 and mots(corps, "M9") == 0, (
        "un corps sans armement porte quand même l'air : en job combiné il "
        "y en aurait un par opération")

print()
print("=" * 62)
print("§5  Vrai pour TOUS les dialectes, et avec M67")
print("=" * 62)

for dialecte, m67 in (("linuxcnc", False), ("linuxcnc", True),
                      ("grbl", True), ("grblhal", False)):
    poser(True, dialecte, m67)
    g2 = core.generate_gcode_planche_defocus(z_focus=core.Z_WORK_MM,
                                             quiet=True)
    n8, n9 = mots(g2, "M8"), mots(g2, "M9")
    print("   %-9s m67=%-5s -> M8=%d M9=%d" % (dialecte, m67, n8, n9))
    # Cette planche arme deux fois (cadrage, pause, planche) : c'est le M9
    # qui doit être unique, cf. §2.
    assert n8 >= 1 and n9 == 1, (
        "dialecte %s : %d M8 / %d M9. Le dialecte réécrit CMD_ARM APRÈS "
        "coup -- l'air doit être greffé en dernier" % (dialecte, n8, n9))

print()
print("=" * 62)
print("§6  Le réglage est PAR LASER, et la case existe")
print("=" * 62)

assert "assistance_air" in core.PER_LASER_KEYS, (
    "l'air n'est pas par profil laser : la PrintNC et le graveur de table "
    "ne le pilotent pas pareil")
import io as _io                                              # noqa: E402
_src = _io.open("/home/christophe/.local/share/FreeCAD/v1-1/Mod/"
                "LaserAtelier/task_panels.py", encoding="utf-8").read()
assert "chk_air" in _src and '"assistance_air": self.chk_air' in _src, (
    "les Préférences n'offrent pas la case, ou ne l'enregistrent pas")
print("   par laser : ✓   case dans les Préférences : ✓")

poser(False)
print()
print("TOUT EST VERT")
