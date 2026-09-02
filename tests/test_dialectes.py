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


# ==========================================================================
# DEUX COMMENTAIRES SUR UNE LIGNE : LE CODE DU MILIEU DOIT SURVIVRE
# ==========================================================================
# Trouvé à la lecture ligne à ligne du 02/09/2026. L'assainisseur prenait
# du PREMIER « ( » au DERNIER « ) » et neutralisait tout l'intérieur --
# juste pour un commentaire qui contient des parenthèses (« passe(s) »,
# le cas pour lequel il a été écrit), FAUX pour une ligne qui porte DEUX
# commentaires.
#
# Or le G-code PERSONNALISÉ des Préférences passe par ici. « G0 X10
# (aller) Y20 (puis) » ressortait « G0 X10 (aller] Y20 [puis) » : le
# « Y20 » enfermé dans le commentaire, le mouvement perdu, sans un mot.
#
# On tranche sur CE QUI SÉPARE : un mot de G-code entre deux parenthèses
# fermées veut dire deux commentaires ; du texte veut dire un seul.

_CAS_ASSAIN = [
    # (entrée, sortie attendue, ce que l'essai gèle)
    ("G0 X10 (aller) Y20 (puis)", "G0 X10 (aller) Y20 (puis)",
     "du code entre deux commentaires doit rester du code"),
    ("G1 X0 Y0 (3 passe(s) par bande)", "G1 X0 Y0 (3 passe[s] par bande)",
     "un commentaire à parenthèses internes reste UN commentaire"),
    ("(-- 2 operation(s) : marquage (fin) --)",
     "(-- 2 operation[s] : marquage [fin] --)",
     "idem quand toute la ligne est un commentaire"),
    ("M3 (arme", "M3 (arme)",
     "un commentaire non refermé est fermé en fin de ligne"),
    ("G0 X1 (a) (b) Y2 (c)", "G0 X1 (a) (b) Y2 (c)",
     "trois commentaires et du code : rien ne fusionne"),
    ("G1 X1 Y1 F800", "G1 X1 Y1 F800", "une ligne sans parenthèse ne bouge pas"),
]
for _entree, _attendu, _pourquoi in _CAS_ASSAIN:
    _obtenu = core.sanitize_gcode_for_linuxcnc(_entree)
    assert _obtenu == _attendu, (_pourquoi, _entree, _obtenu, _attendu)
    # IDEMPOTENT : un job combiné réassainit des corps déjà assainis.
    assert core.sanitize_gcode_for_linuxcnc(_obtenu) == _obtenu, (
        "l'assainissement n'est pas idempotent", _obtenu)
print("assainisseur : {} cas, le code entre deux commentaires survit, "
      "idempotent OK".format(len(_CAS_ASSAIN)))


# ==========================================================================
# L'ASSAINISSEUR SUR LE VRAI G-CODE DES GÉNÉRATEURS
# ==========================================================================
# Les cas ci-dessus sont fabriqués ; celui-ci passe la règle sur ce que les
# générateurs ÉCRIVENT RÉELLEMENT -- leurs en-têtes sont pleins de
# commentaires à parenthèses internes (« 3 passe(s) », « rampe S200
# (gauche) -> S1000 (droite) », « Chaînes : 5 (à partir de 12 segments) »).
#
# Deux propriétés, et la seconde est celle qui a failli me coûter cher :
# le premier jet de la règle prenait le « S1000 » entre deux parenthèses
# fermées pour du code et découpait le commentaire en trois. C'est la
# suite qui l'a dit, pas mon raisonnement.
_generateurs = {}
_img = [[min(1.0, ((x * 7 + y * 5) % 100) / 99.0) for x in range(16)]
        for y in range(12)]
_generateurs["rampe"] = core.generate_gcode_power_ramp_lines(
    line_length=60.0, n_lines=3, feed_min=200.0, feed_max=800.0,
    power_min=200.0, power_max=1000.0, z_work=core.Z_WORK_MM,
    line_gap=10.0, z_end=core.Z_WORK_MM + 20.0, quiet=True)
_generateurs["planche1"] = core.generate_gcode_planche_focus(
    z_focus=core.Z_WORK_MM, quiet=True)
_generateurs["planche2"] = core.generate_gcode_planche_defocus(
    z_focus=core.Z_WORK_MM, quiet=True)
_generateurs["bande"] = core.generate_gcode_defocus_calibration(
    z_start=core.Z_WORK_MM, z_step=3.0, n_marks=6, mark_length=15.0,
    row_gap=6.0, power=600.0, feed=800.0, quiet=True)
_generateurs["halftone"] = core.generate_gcode_halftone(
    _img, 0.8, core.Z_WORK_MM, 500.0, 0.010, 0.060, quiet=True)
_generateurs["offsets"] = core.generate_gcode_offset_test(quiet=True)
_generateurs = {k: v for k, v in _generateurs.items() if v}
assert len(_generateurs) >= 6, sorted(_generateurs)

_MOT_MOUVEMENT = re.compile(r"(?<![A-Za-z0-9.])[XYZFS][-+]?(?:\d+\.?\d*|\.\d+)")
_n_lignes = 0
for _nom, _g in sorted(_generateurs.items()):
    # (a) IDEMPOTENT. Un job combiné réassainit des corps déjà assainis, et
    # une planche combinée les réassainit une troisième fois.
    assert core.sanitize_gcode_for_linuxcnc(_g) == _g, (
        "{} : l'assainissement n'est pas idempotent".format(_nom))
    for _l in _g.split("\n"):
        _n_lignes += 1
        # (b) AUCUN MOT DE MOUVEMENT NE PART DANS UN COMMENTAIRE. C'est le
        # défaut d'origine : « G0 X10 (aller) Y20 (puis) » ressortait
        # « G0 X10 (aller] Y20 [puis) », le Y20 avalé, le mouvement perdu.
        _hors = re.sub(r"\([^)]*\)", "", _l)
        # `\b` et non un simple préfixe : « G43 H100 » commence par
        # « G4 » sans être une temporisation, et n'a aucun mot d'axe
        # hors commentaire -- l'essai s'accusait lui-même.
        if re.match(r"(G0|G1)\b", _l.lstrip()):
            assert _MOT_MOUVEMENT.search(_hors), (
                "{} : un mot de mouvement a été avalé par un "
                "commentaire -> {!r}".format(_nom, _l))
        # (c) PARENTHÈSES ÉQUILIBRÉES ET JAMAIS IMBRIQUÉES -- ce que
        # l'interpréteur RS274 exige, et ce qui avait fait refuser un
        # fichier le 31/07/2026.
        _prof = 0
        for _c in _l:
            if _c == "(":
                _prof += 1
                assert _prof <= 1, ("{} : parenthèses imbriquées -> "
                                    "{!r}".format(_nom, _l))
            elif _c == ")":
                _prof -= 1
                assert _prof >= 0, ("{} : parenthèse fermante orpheline -> "
                                    "{!r}".format(_nom, _l))
        assert _prof == 0, ("{} : parenthèse non refermée -> "
                            "{!r}".format(_nom, _l))
print("assainisseur : {} générateurs, {} lignes de vrai G-code -- idempotent, "
      "aucun mot avalé, parenthèses saines OK".format(
          len(_generateurs), _n_lignes))
