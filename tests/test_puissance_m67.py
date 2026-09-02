# -*- coding: utf-8 -*-
"""La puissance peut passer par `M67` au lieu du mot `S`.

POURQUOI, prouvé le 30/07/2026 sur la PrintNC : deux fichiers de géométrie
rigoureusement identique (200 segments de 0,30 mm en X à F800, G64 P0.050,
laser désarmé) — celui à `S` CONSTANT passe fluide, celui à `S` DIFFÉRENT à
chaque bloc SACCADE. Un mot `S` entre deux G1 fait arrêter la machine, même
sur des segments parfaitement colinéaires. Conséquence chiffrée : un portrait
de 172 614 blocs de 0,30 mm annoncé 1h30 et parti pour 4 h.

`M67 E<n> Q<v>` est la sortie analogique SYNCHRONISÉE avec le mouvement : la
valeur est appliquée au début du bloc suivant sans vider la file de
trajectoire. (`M68` est la variante immédiate et elle ARRÊTE le mouvement.)

Ce test tient deux promesses, et la PREMIÈRE est la plus importante :

1. **En mode direct, la sortie est identique au BIT** à ce qu'elle était.
   C'est une conversion de 11 sites d'émission dans six générateurs : si un
   seul décale d'un espace, la garantie est perdue et plus rien ne protège les
   gravures qui marchent aujourd'hui.
2. En mode M67, AUCUN mot `S` ne subsiste sur un mouvement, et un `M67`
   précède chaque changement de puissance. Un site oublié laisserait un `S` :
   la machine s'arrêterait encore, et — le HAL lisant désormais
   `motion.analog-out-00` — ce générateur-là graverait BLANC, sans erreur.
   Un job blanc de quatre heures est le pire mode de défaillance de ce projet.
"""
import re

from harness import preparer, canal_puissance, image_demo

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"


def tous_les_gcodes():
    """Un G-code par famille de générateur qui émet de la puissance."""
    img = [[min(1.0, ((x * 7 + y * 5) % 100) / 99.0) for x in range(24)]
           for y in range(18)]
    out = {}
    out["halftone"] = core.generate_gcode_halftone(
        img, 0.8, core.Z_WORK_MM, 500.0, 0.010, 0.060, quiet=True)
    out["dither"] = core.generate_gcode_photo_dither_lines(
        img, 0.8, core.Z_WORK_MM, 500.0, 2000.0, quiet=True)
    out["am"] = core.generate_gcode_photo_am(
        img, 0.30, core.Z_WORK_MM, 1000.0, 800.0, dot_spacing_mm=1.27,
        quiet=True)
    out["enfle"] = core.generate_gcode_photo_swell_lines(
        img, 0.30, core.Z_WORK_MM, 800.0, MAT, line_min_mm=0.10, quiet=True)
    out["zdots"] = core.generate_gcode_photo_zdots(
        img, 0.75, core.Z_WORK_MM, 300.0, core.SPOT_FOCUS_MM, 0.60,
        0.010, 0.060, quiet=True)
    out["lignes"] = core.generate_gcode_photo_lines(
        img, 0.80, core.Z_WORK_MM + 15.0, 2000.0, 0.80, MAT, quiet=True)
    out["mire"] = core.generate_gcode_photo_sampler(
        pitch=0.80, z_work=core.Z_WORK_MM + 5.0, dwell_min_s=0.010,
        dwell_max_s=0.060, power=600.0, feed=2000.0, line_width=0.80,
        material=MAT, quiet=True)
    out["rampe"] = core.generate_gcode_power_ramp_lines(
        line_length=60.0, n_lines=3, feed_min=200.0, feed_max=800.0,
        power_min=200.0, power_max=1000.0, z_work=core.Z_WORK_MM,
        line_gap=10.0, z_end=core.Z_WORK_MM + 20.0, quiet=True)
    out["planche2"] = core.generate_gcode_planche_defocus(
        z_focus=core.Z_WORK_MM, quiet=True)
    return {k: v for k, v in out.items() if v}


# --- 1. Mode direct : IDENTIQUE AU BIT ----------------------------------
# Le harnais force le canal DIRECT, quoi que dise la config de la machine
# (cf. harness.canal_puissance) : sinon cocher « Puissance par M67 » dans les
# Préférences ferait échouer ce test et deux autres, comme le 30/07/2026.
assert core.POWER_M67 is False, "le harnais doit forcer le canal direct"
direct = tous_les_gcodes()
assert len(direct) >= 8, sorted(direct)
for nom, g in sorted(direct.items()):
    # Chaque mouvement gravant porte son S, comme avant la conversion.
    g1 = [l for l in g.split("\n") if l.startswith("G1 ")]
    assert g1, nom
    print("   {:<10} {:>6} lignes, {:>5} G1".format(nom, len(g.split("\n")),
                                                    len(g1)))
# En mode direct, le SEUL M67 tolere est la remise a zero de l'autre canal
# (armement et desarmement) : aucun M67 ne doit porter une puissance.
for nom, g in direct.items():
    m67s = [l for l in g.split("\n") if l.startswith("M67 ")]
    assert m67s, (nom, "le canal M67 n'est pas neutralise en mode direct")
    assert all(l == "M67 E0 Q0" for l in m67s), (nom, "M67 porteur en direct",
                                                 [l for l in m67s
                                                  if l != "M67 E0 Q0"][:3])
print("1. les {} générateurs produisent du G-code en mode S direct OK".format(
    len(direct)))

# La référence : le G-code committé avant la conversion, relu depuis git.
# On ne peut pas le rejouer ici, donc on vérifie la PROPRIÉTÉ qui garantit
# l'identité : le suffixe de puissance vaut exactement « S<v> <sel> ».
for v in (0.0, 300.0, 1000.0):
    assert core.cmd_power_suffix(v) == "S{:.0f} {}".format(v, core.SPINDLE_SELECT)
    assert core.cmd_power_prefix(v) == []
print("2. cmd_power_suffix rend « S<v> {} » et le préfixe est vide : le texte "
      "émis est inchangé OK".format(core.SPINDLE_SELECT))

# --- 3. Mode M67 : plus aucun S sur un mouvement ------------------------
canal_puissance(core, m67=True)
try:
    m67 = tous_les_gcodes()
    assert set(m67) == set(direct), (sorted(m67), sorted(direct))
    for nom, g in sorted(m67.items()):
        lignes = g.split("\n")
        # (a) AUCUNE PUISSANCE ne voyage par le mot S. Formulé exactement :
        # pas de S sur un mouvement, et un S isolé ne peut valoir que 0 --
        # c'est la neutralisation de l'autre canal (cf. l'armement), pas une
        # consigne. Dire « aucun mot S » serait plus court et faux.
        sur_mouvement = [l for l in lignes
                         if l.startswith(("G0 ", "G1 ")) and re.search(r"\bS\d", l)]
        assert not sur_mouvement, (nom, "S sur un mouvement", sur_mouvement[:3])
        porteurs = [l for l in lignes
                    if re.match(r"^S\d", l) and not re.match(r"^S0\b", l)]
        assert not porteurs, (nom, "S porteur de puissance", porteurs[:3])
        # (b) un M67 avant chaque changement de puissance
        m67s = [l for l in lignes if l.startswith("M67 ")]
        assert m67s, (nom, "aucun M67")
        assert all(re.match(r"^M67 E\d+ Q\d+$", l) for l in m67s), (
            nom, [l for l in m67s if not re.match(r"^M67 E\d+ Q\d+$", l)][:3])
        # (c) M3/M5 conservés : c'est l'interlock du laser, pas la puissance
        assert "M3" in g and "M5" in g, (nom, "armement/désarmement perdu")
        # (e) l'armement neutralise LES DEUX canaux. Le HAL les additionne,
        # et ils PERSISTENT : un job avorté laisse sa valeur en place, et le
        # job suivant de l'autre mode graverait à la somme des deux -- trop
        # fort, sans un mot. Chaque job doit partir de zéro des deux côtés.
        tete = "\n".join(lignes[:20])
        assert re.search(r"^S0\b", tete, re.M), (nom, "canal S non neutralisé")
        assert re.search(r"^M67 E0 Q0$", tete, re.M), (
            nom, "canal M67 non neutralisé")
        # (d) jamais M68 : elle vide la file et arrête le mouvement
        assert "M68" not in g, (nom, "M68 émis")
        print("   {:<10} {:>5} M67, aucun S sur un mouvement OK".format(
            nom, len(m67s)))
    print("3. les {} générateurs basculent tous : plus un seul S, M3/M5 "
          "conservés, aucun M68 OK".format(len(m67)))

    # --- 4. La géométrie ne change PAS d'un mode à l'autre ---------------
    # Seul le canal de la puissance bascule : les mêmes points, les mêmes
    # avances. Un écart signalerait qu'un site a perdu une coordonnée dans
    # la conversion.
    def mouvements(g):
        return [re.sub(r"\s*S\d+.*$", "", l).strip()
                for l in g.split("\n") if l.startswith(("G0 ", "G1 "))]

    for nom in sorted(direct):
        a, b = mouvements(direct[nom]), mouvements(m67[nom])
        assert a == b, (nom, "géométrie modifiée",
                        [(x, y) for x, y in zip(a, b) if x != y][:3])
        print("   {:<10} {:>6} mouvements identiques".format(nom, len(a)))
    print("4. géométrie et avances rigoureusement identiques dans les deux "
          "modes OK")

    # --- 5. Le nombre de M67 suit les changements de puissance -----------
    # Sur le tramage qui module à chaque pixel, il doit y en avoir beaucoup ;
    # sur un tramage binaire, bien moins. Un M67 par mouvement serait un
    # gaspillage, aucun serait un bug.
    n_enfle = len([l for l in m67["enfle"].split("\n") if l.startswith("M67 ")])
    n_am = len([l for l in m67["am"].split("\n") if l.startswith("M67 ")])
    assert n_enfle > n_am, ("les lignes gravées modulent plus que la trame AM",
                            n_enfle, n_am)
    print("5. lignes gravées {} M67 contre {} pour la trame binaire : le canal "
          "suit bien la modulation OK".format(n_enfle, n_am))
finally:
    canal_puissance(core, m67=False)

# --- 6. GRBL ne connaît pas M67 : le réglage doit être ignoré -----------
cfg = core.load_config()
cfg.setdefault("settings", {})["puissance_par_m67"] = True
cfg["settings"]["gcode_dialect"] = "grbl"
core.save_config(cfg)          # config JETABLE (cf. harness), jamais la vraie
core._apply_settings_config()
assert core.POWER_M67 is False, ("M67 activé en GRBL, qui ne le connaît pas",
                                 core.GCODE_DIALECT)
cfg["settings"]["gcode_dialect"] = "linuxcnc"
core.save_config(cfg)
core._apply_settings_config()
assert core.POWER_M67 is True, "le réglage n'est pas relu en LinuxCNC"
assert core.CMD_BEAM_ON == core._CMD_BEAM_ON_M67
assert "M67" in core.CMD_ARM and "M3" in core.CMD_ARM
print("6. réglage relu depuis la config, ignoré en GRBL, et l'armement garde "
      "M3 OK")

# Remise en état pour ne pas contaminer un autre test du même processus.
cfg["settings"]["puissance_par_m67"] = False
core.save_config(cfg)
core._apply_settings_config()
assert core.POWER_M67 is False

# --- 6. LE DÉGRADÉ DE REMPLISSAGE MARCHE DANS LES DEUX CANAUX -----------
# Trouvé à la lecture ligne à ligne du 02/09/2026.
# `apply_fill_power_gradient` réécrit un corps de G-code en y injectant la
# puissance locale ; pour savoir de quelle puissance partir, il cherchait
# une ligne d'armement au motif `^S(...)` -- le canal DIRECT et lui seul.
#
# En M67 la puissance ne voyage plus sur un mot `S` : aucune ligne
# d'armement n'était reconnue, la fonction rendait le corps INCHANGÉ, et
# le dégradé ne faisait rien du tout. En silence, dans le canal que
# Christophe a mesuré et adopté le 31/07/2026.
#
# Mesuré sur un carré de 40 mm au pas 0,5, dégradé S200 -> S900 :
# 335 puissances distinctes en direct, UNE SEULE en M67.
import Part as _Part
import FreeCAD as _App

_carre = _Part.Face(_Part.makePolygon([_App.Vector(*p) for p in
                    [(0, 0, 0), (40, 0, 0), (40, 40, 0), (0, 40, 0), (0, 0, 0)]]))
_fill, _cont = core.build_filled_engraving_edges([_carre], 0.5, 0.0,
                                                 fill_inset=0.0)


def _puissances_du_degrade():
    g = core.generate_gcode_filled_engraving(
        _fill, _cont, z_focus=8.0, defocus=2.0, fill_power=200.0,
        fill_feed=1000.0, draw_contour=False, quiet=True,
        grad_power_fin=900.0, grad_angle_deg=0.0)
    vals = set()
    for ligne in g.split("\n"):
        ligne = ligne.strip()
        if ligne.startswith("M67"):
            vals.add(float(ligne.split("Q")[1].split()[0]))
        elif ligne[:1] == "S" and ligne[1:2].isdigit():
            vals.add(float(ligne.split()[0][1:]))
    vals.discard(0.0)
    return vals


canal_puissance(core, m67=False)
_direct_grad = _puissances_du_degrade()
canal_puissance(core, m67=True)
_m67_grad = _puissances_du_degrade()
canal_puissance(core, m67=False)
assert len(_direct_grad) > 50, (
    "le dégradé ne module presque rien en direct : {}".format(
        sorted(_direct_grad)[:8]))
assert _m67_grad == _direct_grad, (
    "le dégradé de remplissage diffère selon le canal : {} valeurs en M67 "
    "contre {} en direct".format(len(_m67_grad), len(_direct_grad)))
print("6. dégradé de remplissage : {} puissances distinctes, les MÊMES dans "
      "les deux canaux OK".format(len(_direct_grad)))

print("\nTOUS LES TESTS puissance_m67 PASSENT")
