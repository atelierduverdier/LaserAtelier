# -*- coding: utf-8 -*-
"""La machine se décrit elle-même : lire ses limites dans son .ini.

Christophe, 06/08/2026, sur le constat d'audit « les défauts d'usine ≠ une
vraie machine » : « ok fait le ».

TROIS RÉGLAGES DE L'ATELIER SONT DEVINÉS, et ce sont les seuls : vitesse
rapide, vitesse Z max, accélération. Ni mesurés au bois, ni choisis --
supposés, avec des valeurs prudentes d'usine que rien ne signalait comme
telles.

Sur Z ce n'est pas cosmétique : `pente_z_max` en dépend, donc le fuseau.
1500 au lieu de 3000 divise la pente par deux et DOUBLE la longueur de
trace nécessaire à un fuseau complet -- moitié moins de motifs sur la même
image. §5 le mesure plutôt que de le raconter.

Et relever le défaut à l'aveugle serait le mauvais sens : trop bas ne coûte
que du détail, trop haut fait ralentir tout le mouvement par LinuxCNC pour
que le Z suive -- le temps de pose change, donc la noirceur, en silence.
D'où la lecture du .ini : la machine le déclare, on cesse de deviner.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()
core = h.core

import os                                                     # noqa: E402
import tempfile                                               # noqa: E402

DOSSIER = tempfile.mkdtemp(prefix="limites-ini-")
INI_REEL = os.path.expanduser("~/Projets/printnc-config/remora-flexi.ini")


def ecrire(nom, contenu):
    chemin = os.path.join(DOSSIER, nom)
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(contenu)
    return chemin


print("=" * 62)
print("§1  Le .ini de la PrintNC redonne EXACTEMENT ce qu'il déclare")
print("=" * 62)

if not os.path.exists(INI_REEL):
    print("   (%s absent -- section sautée)" % INI_REEL)
else:
    reglages, lignes = core.limites_depuis_ini(INI_REEL)
    for ligne in lignes:
        print("   %s" % ligne)

    # ON RELIT LE FICHIER À LA MAIN plutôt que de figer 8000/3000/600 : ces
    # trois nombres sont ceux d'UNE machine, et un littéral copié dans un
    # test garde la fiction le jour où la config change (c'est exactement
    # ce qui est arrivé à la table des largeurs au foyer). Le test vérifie
    # la CONVERSION, pas les chiffres de Christophe.
    brut = open(INI_REEL, encoding="utf-8", errors="replace").read()
    sections, courante = {}, None
    for ligne in brut.splitlines():
        ligne = ligne.split("#")[0].split(";")[0].strip()
        if ligne.startswith("[") and ligne.endswith("]"):
            courante = ligne[1:-1].strip().upper()
        elif courante and "=" in ligne:
            cle, _s, val = ligne.partition("=")
            sections.setdefault(courante, {}).setdefault(
                cle.strip().upper(), val.strip())

    attendu_z = round(float(sections["AXIS_Z"]["MAX_VELOCITY"]) * 60.0)
    attendu_a = round(float(sections["AXIS_X"]["MAX_ACCELERATION"]))
    attendu_r = round(min(float(sections["AXIS_X"]["MAX_VELOCITY"]),
                          float(sections["AXIS_Y"]["MAX_VELOCITY"]),
                          float(sections["TRAJ"]["MAX_LINEAR_VELOCITY"])) * 60.0)
    print("   relu à la main : rapide %d, Z %d, accél %d"
          % (attendu_r, attendu_z, attendu_a))
    assert reglages["z_max_feed_mm_min"] == float(attendu_z), (
        "Z lu %s au lieu de %s : la conversion unités/s -> mm/min est fausse"
        % (reglages["z_max_feed_mm_min"], attendu_z))
    assert reglages["accel_mm_s2"] == float(attendu_a), (
        "accélération lue %s au lieu de %s"
        % (reglages["accel_mm_s2"], attendu_a))
    assert reglages["rapid_feed_mm_min"] == float(attendu_r), (
        "vitesse rapide lue %s au lieu de %s"
        % (reglages["rapid_feed_mm_min"], attendu_r))

    # ET LE VRAI CONTRÔLE : ce que la lecture propose doit tomber sur ce que
    # Christophe avait saisi À LA MAIN dans sa config, après avoir constaté
    # que les défauts ne collaient pas. Si les deux divergent, l'un des deux
    # ment -- et c'est cette coïncidence qui prouve que le lecteur sert.
    saisis = core.current_settings()
    ecarts = [(c, saisis[c], reglages[c]) for c in core.LIMITES_INI_CLES
              if c in reglages and saisis[c] != reglages[c]]
    print("   écarts avec ses réglages saisis à la main : %s"
          % (ecarts or "aucun"))
    assert not ecarts, (
        "le .ini et les réglages de l'atelier ne disent pas la même chose : "
        "%s" % ecarts)

print()
print("=" * 62)
print("§2  Un fichier en POUCES est converti")
print("=" * 62)

pouces = ecrire("pouces.ini", """
[TRAJ]
LINEAR_UNITS = inch
MAX_LINEAR_VELOCITY = 5.0
[AXIS_X]
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 20.0
[AXIS_Y]
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 20.0
[AXIS_Z]
MAX_VELOCITY = 2.0
MAX_ACCELERATION = 8.0
""")
reglages, lignes = core.limites_depuis_ini(pouces)
for ligne in lignes:
    print("   %s" % ligne)
assert reglages["rapid_feed_mm_min"] == round(5.0 * 25.4 * 60), (
    "5 in/s devrait faire %d mm/min, lu %s"
    % (round(5.0 * 25.4 * 60), reglages["rapid_feed_mm_min"]))
assert reglages["z_max_feed_mm_min"] == round(2.0 * 25.4 * 60)
assert reglages["accel_mm_s2"] == round(20.0 * 25.4)
assert any("inch" in l for l in lignes), (
    "la conversion pouces n'est pas annoncée : un facteur 25,4 silencieux "
    "est indiscernable d'une machine 25 fois plus rapide")

print()
print("=" * 62)
print("§3  La vitesse rapide retenue est la plus CONTRAIGNANTE")
print("=" * 62)

# Un G0 quelconque est borné par chacun des axes qu'il bouge ET par la
# trajectoire. L'estimation ne manie qu'un nombre : prendre le maximum
# serait flatteur et faux sur tout déplacement le long de l'axe lent.
bride = ecrire("bride.ini", """
[TRAJ]
LINEAR_UNITS = mm
MAX_LINEAR_VELOCITY = 200.0
[AXIS_X]
MAX_VELOCITY = 200.0
MAX_ACCELERATION = 900.0
[AXIS_Y]
MAX_VELOCITY = 50.0
MAX_ACCELERATION = 300.0
[AXIS_Z]
MAX_VELOCITY = 25.0
MAX_ACCELERATION = 100.0
""")
reglages, lignes = core.limites_depuis_ini(bride)
for ligne in lignes:
    print("   %s" % ligne)
assert reglages["rapid_feed_mm_min"] == 3000.0, (
    "X fait 200 mm/s et Y 50 : la rapide retenue doit être 3000 mm/min, "
    "pas %s" % reglages["rapid_feed_mm_min"])
assert reglages["accel_mm_s2"] == 300.0, (
    "l'accélération retenue doit être celle de l'axe le plus lent (300), "
    "pas %s" % reglages["accel_mm_s2"])

print()
print("=" * 62)
print("§4  Sans [AXIS_*], on retombe sur les joints -- et on le DIT")
print("=" * 62)

joints = ecrire("joints.ini", """
[TRAJ]
LINEAR_UNITS = mm
[JOINT_0]
MAX_VELOCITY = 100.0
MAX_ACCELERATION = 500.0
[JOINT_1]
MAX_VELOCITY = 100.0
MAX_ACCELERATION = 500.0
[JOINT_2]
MAX_VELOCITY = 30.0
MAX_ACCELERATION = 200.0
""")
reglages, lignes = core.limites_depuis_ini(joints)
for ligne in lignes:
    print("   %s" % ligne)
assert reglages["z_max_feed_mm_min"] == 1800.0, (
    "le repli sur [JOINT_2] ne marche pas : %s" % reglages)
assert any("JOINT" in l for l in lignes), (
    "le repli sur les joints n'est pas annoncé -- sur un portique le "
    "numéro de joint ne suit plus l'axe, le lecteur doit pouvoir vérifier")

print()
print("=" * 62)
print("§5  CE QUE Z_MAX CHANGE : la pente du fuseau, donc le détail")
print("=" * 62)

# C'est la raison d'être de tout ce fichier. Un test qui ne mesurerait que
# le parsing laisserait croire qu'il s'agit d'un confort de saisie.
avant = core.Z_MAX_FEED_MM_MIN
try:
    core.Z_MAX_FEED_MM_MIN = 1500.0
    pente_defaut = core.pente_z_max(200.0)
    mini_defaut = core.longueur_mini_fuseau(200.0, 20.0)
    core.Z_MAX_FEED_MM_MIN = 3000.0
    pente_reelle = core.pente_z_max(200.0)
    mini_reelle = core.longueur_mini_fuseau(200.0, 20.0)
finally:
    core.Z_MAX_FEED_MM_MIN = avant
print("   défaut 1500 : pente %.2f mm/mm, fuseau complet en %.1f mm"
      % (pente_defaut, mini_defaut))
print("   réel   3000 : pente %.2f mm/mm, fuseau complet en %.1f mm"
      % (pente_reelle, mini_reelle))
assert abs(pente_reelle / pente_defaut - 2.0) < 1e-9, (
    "doubler Z_MAX ne double pas la pente autorisée : le réglage ne "
    "gouverne plus le fuseau, ce fichier n'a plus de sujet")
assert mini_defaut > mini_reelle * 1.9, (
    "le défaut prudent ne coûte plus de détail (%.1f contre %.1f mm) : "
    "vérifier FUSEAU_MARGE_Z" % (mini_defaut, mini_reelle))

print()
print("=" * 62)
print("§6  Un fichier illisible ne remplace RIEN")
print("=" * 62)

for nom, contenu in (("vide.ini", ""),
                     ("prose.ini", "ceci n'est pas un ini\ndu tout\n"),
                     ("sansaxes.ini", "[TRAJ]\nLINEAR_UNITS = mm\n")):
    chemin = ecrire(nom, contenu)
    reglages, lignes = core.limites_depuis_ini(chemin)
    print("   %-14s -> %s | %s" % (nom, reglages or "{}", lignes[0]))
    assert not reglages, (
        "%s a produit des réglages (%s) : un défaut de secours écraserait "
        "en silence une valeur juste" % (nom, reglages))
    assert lignes and lignes[0].strip(), (
        "%s échoue sans dire pourquoi" % nom)

manquant = os.path.join(DOSSIER, "jamais-existe.ini")
reglages, lignes = core.limites_depuis_ini(manquant)
print("   fichier absent -> %s | %s" % (reglages or "{}", lignes[0]))
assert not reglages, "un fichier absent a produit des réglages"

print()
print("=" * 62)
print("§7  LE BOUTON DU PANNEAU remplit vraiment les trois champs")
print("=" * 62)

# ON PILOTE LE GESTIONNAIRE QUE L'UTILISATEUR CLIQUE, pas le helper : la
# Grille de test a livré un bouton cassé dont la vérification appelait la
# fonction d'en dessous, en enjambant la ligne fautive.
from harness import sans_dialogues                            # noqa: E402
sans_dialogues()
from PySide6 import QtWidgets                                 # noqa: E402
tp = h.tp
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

panneau = tp.TaskPanelSettings()
panneau.spn_rapid.setValue(1234.0)
panneau.spn_z_max_feed.setValue(1234.0)
panneau.spn_accel.setValue(123.0)
panneau._on_lire_ini(bride)
print("   après lecture : rapide %.0f, Z %.0f, accél %.0f"
      % (panneau.spn_rapid.value(), panneau.spn_z_max_feed.value(),
         panneau.spn_accel.value()))
assert panneau.spn_rapid.value() == 3000.0, "le champ rapide n'est pas rempli"
assert panneau.spn_z_max_feed.value() == 1500.0, "le champ Z n'est pas rempli"
assert panneau.spn_accel.value() == 300.0, "le champ accél n'est pas rempli"
assert panneau.lbl_ini.isVisibleTo(panneau.lbl_ini.parentWidget()), (
    "le compte rendu de lecture reste caché : l'utilisateur ne saurait pas "
    "d'où viennent les trois nombres qui viennent de changer")
texte = panneau.lbl_ini.text()
assert "bride.ini" in texte, "le compte rendu ne nomme pas le fichier lu"
assert "AXIS_Y" in texte, (
    "le compte rendu ne dit pas de QUELLE section vient chaque nombre : "
    "%r" % texte)

print()
print("   le chemin est mémorisé : %r" % panneau._chemin_ini)
assert panneau._chemin_ini == bride, (
    "le fichier lu n'est pas retenu : relire après un changement de config "
    "machine redemanderait de naviguer")
assert "chemin_ini_linuxcnc" in dict(
    (c[0], c[1]) for c in core._USER_SETTINGS), (
    "le chemin n'est pas un réglage persistant")

print()
print("=" * 62)
print("§8  Un échec de lecture ne touche AUCUN champ du panneau")
print("=" * 62)

vide = ecrire("vide2.ini", "")
panneau.spn_rapid.setValue(4321.0)
panneau.spn_z_max_feed.setValue(4321.0)
panneau.spn_accel.setValue(432.0)
panneau._on_lire_ini(vide)
print("   après un .ini vide : rapide %.0f, Z %.0f, accél %.0f"
      % (panneau.spn_rapid.value(), panneau.spn_z_max_feed.value(),
         panneau.spn_accel.value()))
assert (panneau.spn_rapid.value(), panneau.spn_z_max_feed.value(),
        panneau.spn_accel.value()) == (4321.0, 4321.0, 432.0), (
    "un fichier illisible a modifié des réglages en place")
assert panneau._chemin_ini == bride, (
    "un fichier illisible est devenu le chemin mémorisé")

print()
print("TOUT EST VERT")

# Qt/FreeCAD rendent parfois un code non nul à la destruction des widgets,
# sans traceback et toutes vérifications passées (cf. test_panneaux.py).
# TOUTES les assertions sont AU-DESSUS de cette ligne : un vrai échec lève
# et sort non nul avant d'y arriver -- vérifié en insérant `assert False`
# juste avant.
#
# ET ON VIDE LES TAMPONS AVANT : `os._exit` ne les vide pas, si bien que la
# première version de cette ligne a fait passer le test SANS AUCUNE SORTIE
# -- indiscernable d'un test qui n'aurait rien exécuté.
del panneau
app.processEvents()
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
