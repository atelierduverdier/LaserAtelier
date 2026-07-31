# -*- coding: utf-8 -*-
"""Chaque dialecte n'émet QUE ce que son contrôleur comprend.

Les trois dialectes existent depuis longtemps, et personne n'avait jamais relu
ce que GRBL produisait vraiment. Le 30/07/2026, une relecture a trouvé du
premier coup un `M67 E0 Q0` dans TOUS les jobs GRBL : la ligne venait d'être
ajoutée une heure plus tôt au désarmement PARTAGÉ entre dialectes, pour
neutraliser le canal de puissance sous LinuxCNC. GRBL ne connaît pas M67 —
chaque job aurait fini sur une erreur de commande inconnue. Rien ne l'aurait
signalé : aucune machine GRBL n'avait jamais lancé une ligne de cet atelier.

D'où ce test. Il ne vérifie pas que GRBL « marche » — ça, seule une machine le
dira. Il vérifie la seule chose vérifiable ici : que l'atelier n'émet aucune
commande que le contrôleur visé ignore, et qu'il émet bien celles qui le
distinguent.
"""
import re

from harness import preparer

h = preparer()
core = h.core
MAT = u"Hêtre"


def jobs():
    """Un job par famille, dans le dialecte courant."""
    img = [[min(1.0, ((x * 7 + y * 5) % 100) / 99.0) for x in range(40)]
           for y in range(30)]
    out = {
        "enfle": core.generate_gcode_photo_swell_lines(
            img, 0.30, core.Z_WORK_MM, 800.0, MAT, line_min_mm=0.10,
            quiet=True),
        "points": core.generate_gcode_halftone(
            img, 0.8, core.Z_WORK_MM, 500.0, 0.010, 0.060, quiet=True),
        "planche2": core.generate_gcode_planche_defocus(
            z_focus=core.Z_WORK_MM, quiet=True),
        "rampe": core.generate_gcode_power_ramp_lines(
            line_length=60.0, n_lines=3, feed_min=200.0, feed_max=800.0,
            power_min=200.0, power_max=1000.0, z_work=core.Z_WORK_MM,
            line_gap=10.0, z_end=core.Z_WORK_MM + 20.0, quiet=True),
    }
    return {k: v for k, v in out.items() if v}


def poser(dialecte, m67=True):
    """Écrit le dialecte dans la config JETABLE et le fait appliquer, par le
    vrai chemin -- pas en forçant les constantes à la main, sans quoi le test
    ne prouverait rien sur `_apply_settings_config`."""
    cfg = core.load_config()
    cfg.setdefault("settings", {})["gcode_dialect"] = dialecte
    # Volontairement DEMANDÉ partout : un dialecte qui ignore M67 doit
    # l'ignorer, pas compter sur l'utilisateur pour décocher la case.
    cfg["settings"]["puissance_par_m67"] = m67
    core.save_config(cfg)
    core._apply_settings_config()


# Commandes que GRBL 1.1 (et ses dérivés ESP32) ne connaissent pas.
INCONNUES_DE_GRBL = (
    (r"\bM6[78]\b", "M67/M68 (sortie analogique LinuxCNC)"),
    (r"\bG64\b", "G64 (lissage : natif en GRBL, réglage $11)"),
    (r"\bG10\b", "G10 (table d'outils)"),
    (r"\$\d", "sélecteur de broche $n (multi-broche LinuxCNC)"),
)
# Vraies pour tout dialecte : le contrôleur lit des octets ASCII, et GRBL a un
# tampon de réception de 128 octets par ligne.
UNIVERSELLES = (
    (r"[^\x00-\x7F]", "caractère non ASCII"),
)
LIMITE_LIGNE = 128

essais = 0
for dialecte in ("grbl", "grblhal"):
    poser(dialecte)
    assert core.GCODE_DIALECT == dialecte, core.GCODE_DIALECT
    assert core.SPINDLE_SELECT == "", ("pas de sélecteur de broche en GRBL",
                                       repr(core.SPINDLE_SELECT))
    assert core.POWER_M67 is False, (
        "M67 activé en {} : le dialecte doit l'ignorer, pas s'en remettre à "
        "une case décochée".format(dialecte))
    assert core.cmd_path_blend() is None, "G64 émis en GRBL"
    for nom, g in sorted(jobs().items()):
        lignes = g.split("\n")
        for rx, quoi in INCONNUES_DE_GRBL + UNIVERSELLES:
            fautifs = [l for l in lignes if re.search(rx, l)]
            assert not fautifs, (dialecte, nom, quoi, fautifs[:2])
        trop = [l for l in lignes if len(l.encode("ascii", "ignore")) > LIMITE_LIGNE]
        assert not trop, (dialecte, nom,
                          "ligne plus longue que le tampon GRBL", trop[:1])
        # Ce qui DOIT y être : l'armement en mode laser, et la fin.
        assert re.search(r"^M4\b", g, re.M), (dialecte, nom, "pas de M4")
        assert re.search(r"^M5\b", g, re.M), (dialecte, nom, "pas de M5")
        assert "M2" in g, (dialecte, nom, "pas de fin de programme")
        # La puissance voyage forcément par S, seul canal que GRBL connaisse.
        assert re.search(r"\bS\d", g), (dialecte, nom, "aucune puissance")
        essais += 1
    # Le changement d'outil sépare les deux : grblHAL le garde, GRBL non.
    outil = core.cmd_tool_comp()
    if dialecte == "grbl":
        assert outil.lstrip().startswith("("), ("GRBL : T/M6 doit devenir un "
                                                "commentaire", outil)
    else:
        assert re.search(r"\bT\d", outil) and "G43" in outil, (
            "grblHAL garde la table d'outils", outil)
    print("   {:<9} sélecteur vide, pas de G64/M67/$n, M4+M5+M2, outil {} OK"
          .format(dialecte, "commenté" if dialecte == "grbl" else "T/M6+G43"))
print("1. {} jobs relus sur les 2 dialectes GRBL : aucune commande inconnue, "
      "tout ASCII, aucune ligne > {} octets OK".format(essais, LIMITE_LIGNE))

# --- LinuxCNC : l'inverse doit être vrai --------------------------------
poser("linuxcnc", m67=False)
assert core.SPINDLE_SELECT == "$1", core.SPINDLE_SELECT
assert core.cmd_path_blend(), "G64 absent en LinuxCNC"
g = jobs()["enfle"]
assert "$1" in g and "G64" in g and re.search(r"\bT\d+ M6\b", g), \
    "LinuxCNC a perdu ce qui le distingue"
print("2. LinuxCNC garde son sélecteur $1, son G64 et son T/M6 OK")

# --- Et le désarmement, la faute exacte du 30/07/2026 ------------------
poser("linuxcnc", m67=True)
assert "M67" in core.CMD_DISARM, ("sous LinuxCNC le désarmement doit "
                                  "neutraliser le canal M67", core.CMD_DISARM)
poser("grbl", m67=True)
assert "M67" not in core.CMD_DISARM, (
    "le désarmement GRBL porte un M67 : c'est le bug du 30/07/2026, revenu",
    core.CMD_DISARM)
print("3. le désarmement porte le M67 sous LinuxCNC et JAMAIS sous GRBL OK")

poser("linuxcnc", m67=False)
print("\nTOUS LES TESTS dialectes PASSENT")


# --- Commentaire non refermé : LinuxCNC refuse de CHARGER le fichier ---
# Trouvé le 31/07/2026 : une planche dont l'en-tête portait un commentaire
# coupé en deux lignes a fait échouer le chargement (« Unclosed comment
# found », le job ne démarre même pas). L'assainisseur recopiait la ligne
# telle quelle -- alors que garantir un fichier chargeable EST son rôle.
# RS274 n'a pas de commentaire multi-ligne : fermer en fin de ligne est
# donc toujours la bonne réparation.
brut = "\n".join([
    "(en-tete coupe en deux",
    "( suite du commentaire)",
    "G1 X10 Y10 F800",
    "G1 X20 (commentaire normal)",
])
propre = core.sanitize_gcode_for_linuxcnc(brut)
for i, l in enumerate(propre.split("\n"), 1):
    ouvertes = l.count("(")
    fermees = l.count(")")
    assert ouvertes == fermees, (
        "ligne {} : {} '(' pour {} ')'".format(i, ouvertes, fermees), l)
assert propre.split("\n")[0] == "(en-tete coupe en deux)", propre.split("\n")[0]
# Les lignes déjà correctes ne bougent pas.
assert propre.split("\n")[2] == "G1 X10 Y10 F800"
assert propre.split("\n")[3] == "G1 X20 (commentaire normal)"
# Idempotence : ré-assainir ne rajoute pas une deuxième parenthèse.
assert core.sanitize_gcode_for_linuxcnc(propre) == propre, "non idempotent"
# Et le contrôle se démontre : sans le correctif, la 1re ligne resterait
# telle quelle et le compte de parenthèses serait déséquilibré.
assert "(en-tete coupe en deux" in brut and not brut.split("\n")[0].endswith(")")
print("commentaire non referme : ferme en fin de ligne, idempotent, "
      "lignes valides intactes OK")
