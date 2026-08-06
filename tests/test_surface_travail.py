# -*- coding: utf-8 -*-
"""Un job plus grand que la machine doit le dire AVANT la gravure.

Christophe, 06/08/2026, en regardant la fiche de son Creality Falcon2 :
« elle a une petite surface de gravure, ce n'est pas ma table de
120 x 120 cm ». Sa PrintNC fait 1200 x 1200, le Falcon2 **400 x 415**.

Un motif dessiné pour l'une part droit dans les butées de l'autre : le
contrôleur lève une alarme de limite logicielle EN PLEIN JOB, ou tape dans
le cadre. Et ça se découvre la pièce en place et le bois entamé.

L'ATELIER NE SAVAIT PAS CE QUE LA MACHINE PEUT ATTEINDRE. Il calculait
bien l'emprise du parcours (`gcode_bbox_xy`) -- pour recadrer au zéro pièce
et assembler les jobs combinés, jamais pour la comparer à une course. La
notion n'existait pas.

ON JUGE SUR LE G-CODE TEL QU'IL SERA ÉCRIT, jamais sur le dessin : le
recadrage a déjà eu lieu, le cadrage et les marges de survol sont dedans.
Et on AVERTIT sans refuser -- la course déclarée est un réglage, pas une
mesure, et un refus sec jetterait un G-code qui n'existe nulle part
ailleurs.
"""
import os
import sys

_os_chemin = os.path.join

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer, sans_dialogues                  # noqa: E402

h = preparer()
core = h.core

FALCON = (400.0, 415.0)      # la fiche Creality
PRINTNC = (1200.0, 1200.0)   # la table de Christophe


def job(x0, y0, x1, y1):
    """Un G-code minimal dont l'emprise est exactement ce rectangle."""
    return ("G21\nG90\n"
            "G0 X{:.4f} Y{:.4f}\nG1 X{:.4f} Y{:.4f}\n"
            "G1 X{:.4f} Y{:.4f}\nM2\n"
            .format(x0, y0, x1, y0, x1, y1))


print("=" * 62)
print("§1  Surface inconnue (0) : AUCUN contrôle")
print("=" * 62)

enorme = job(0, 0, 5000, 5000)
print("   job de 5000 x 5000 mm, surface non renseignée -> %r"
      % core.job_hors_surface(enorme, 0.0, 0.0))
assert core.job_hors_surface(enorme, 0.0, 0.0) is None, (
    "un contrôle se déclenche alors que la course n'est pas renseignée : "
    "personne ne doit hériter d'un refus pour un réglage jamais vu")

print()
print("=" * 62)
print("§2  Ce qui TIENT passe, ce qui NE TIENT PAS parle")
print("=" * 62)

cas = [
    ("300 x 300 sur le Falcon",     job(0, 0, 300, 300),   FALCON,  False),
    ("399 x 414 sur le Falcon",     job(0, 0, 399, 414),   FALCON,  False),
    ("500 x 300 sur le Falcon",     job(0, 0, 500, 300),   FALCON,  True),
    ("300 x 500 sur le Falcon",     job(0, 0, 300, 500),   FALCON,  True),
    ("500 x 300 sur la PrintNC",    job(0, 0, 500, 300),   PRINTNC, False),
    ("le poussoir (324 x 350)",     job(0, 0, 324, 350),   FALCON,  False),
]
for libelle, g, (sx, sy), attendu in cas:
    souci = core.job_hors_surface(g, sx, sy)
    print("   %-28s -> %s" % (libelle, "REFUS" if souci else "passe"))
    assert bool(souci) == attendu, (
        "« %s » : attendu %s, obtenu %s"
        % (libelle, "un refus" if attendu else "un passage",
           repr(souci)[:80]))

print()
print("=" * 62)
print("§3  La POSITION compte, pas seulement la taille")
print("=" * 62)

# 100 x 100 tient largement dans 400 x 415 -- mais posé à X350 il déborde.
# Une vérification qui ne regarderait que la taille laisserait passer
# exactement le cas qu'on veut attraper : un job recadré ailleurs.
tient = job(0, 0, 100, 100)
decale = job(350, 0, 450, 100)
print("   100 x 100 à l'origine -> %s"
      % ("REFUS" if core.job_hors_surface(tient, *FALCON) else "passe"))
print("   le même posé en X350  -> %s"
      % ("REFUS" if core.job_hors_surface(decale, *FALCON) else "passe"))
assert core.job_hors_surface(tient, *FALCON) is None
souci = core.job_hors_surface(decale, *FALCON)
assert souci, (
    "un job qui TIENT mais est posé hors course passe : le contrôle ne "
    "regarde que la taille")
assert "450" in souci, "le message ne dit pas jusqu'où le job va : %r" % souci

# Et le négatif, qui est hors course sur toute machine à origine coin.
negatif = job(-20, 0, 100, 100)
souci_neg = core.job_hors_surface(negatif, *FALCON)
print("   le même posé en X-20  -> %s"
      % ("REFUS" if souci_neg else "passe"))
assert souci_neg, "un job en coordonnées négatives passe"

print()
print("=" * 62)
print("§4  Le message DIT les chiffres")
print("=" * 62)

souci = core.job_hors_surface(job(0, 0, 500, 300), *FALCON)
print("   %s" % souci.replace("\n", "\n   "))

# ON VISE LA PREMIÈRE PHRASE, celle qui dit la RAISON. Première version :
# on cherchait « 500 » et « 400 » n'importe où dans le message -- or le
# bloc « Emprise du parcours » les contient tous les deux de toute façon,
# si bien qu'un message dont la raison était vidée passait quand même.
premiere = souci.split("\n")[0]
print("   (phrase de raison : %r)" % premiere)
assert "500" in premiere and "400" in premiere, (
    "la RAISON ne nomme pas la cote fautive et la course : %r" % premiere)
assert "X" in premiere, "la raison ne dit pas quel axe : %r" % premiere
for attendu in ("500.0", "400", "300.0"):
    assert attendu in souci, (
        "le message ne porte pas %s : sans les chiffres, on ne sait ni de "
        "combien ça dépasse ni quoi corriger" % attendu)

print()
print("=" * 62)
print("§5  L'ÉCRITURE s'arrête, et le G-code n'est pas perdu")
print("=" * 62)

# ON PILOTE LE CHEMIN QUE L'UTILISATEUR DÉCLENCHE, pas le helper : c'est la
# leçon du bouton de la Grille de test, livré cassé parce que la
# vérification appelait la fonction d'en dessous.
sans_dialogues()
from PySide6 import QtWidgets                                 # noqa: E402
tp = h.tp
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

cfg = core.load_config()
cfg.setdefault("settings", {})["surface_travail_x_mm"] = FALCON[0]
cfg["settings"]["surface_travail_y_mm"] = FALCON[1]
core.save_config(cfg)
core._apply_settings_config()
assert core.SURFACE_TRAVAIL_X_MM == FALCON[0], "le réglage n'a pas pris"

# `sans_dialogues` répond la première option, donc « Yes » : on force le
# refus en remplaçant la question par un « No ».
_vrai_warning = QtWidgets.QMessageBox.warning
QtWidgets.QMessageBox.warning = staticmethod(
    lambda *a, **k: QtWidgets.QMessageBox.No)
# LE FAUX DIALOGUE REND UN VRAI CHEMIN, et c'est indispensable. Première
# version : il rendait une chaîne vide, ce que `_write_gcode_with_dialog`
# lit comme « Annuler » -- il repropose alors le dialogue, `sans_dialogues`
# répond « oui », et ça tourne SANS FIN. Le sabotage ne faisait donc pas
# rougir le test, il le FIGEAIT : aucune sortie, exactement le tableau d'une
# boucle infinie dans le code testé.
import tempfile as _tf                                        # noqa: E402
_dossier = _tf.mkdtemp(prefix="surface-")
_appels = []
_vrai_dialogue = QtWidgets.QFileDialog.getSaveFileName
QtWidgets.QFileDialog.getSaveFileName = staticmethod(
    lambda *a, **k: (_appels.append(a) or
                     (_os_chemin(_dossier, "ecrit.ngc"), "")))
try:
    resultat = tp._write_gcode_with_dialog(
        None, job(0, 0, 500, 300), "/tmp/jamais-ecrit.ngc")
finally:
    QtWidgets.QMessageBox.warning = _vrai_warning
    QtWidgets.QFileDialog.getSaveFileName = _vrai_dialogue

print("   écriture d'un job de 500 mm sur une machine de 400 : %r" % resultat)
print("   dialogue de fichier ouvert : %s" % ("oui" if _appels else "non"))
assert resultat is False, (
    "l'écriture a continué malgré le refus de l'utilisateur")
assert not _appels, (
    "le dialogue de fichier s'est ouvert AVANT l'avertissement : on nomme "
    "un fichier pour rien")

print()
print("=" * 62)
print("§6  Le réglage est PAR LASER, et les champs existent")
print("=" * 62)

for cle in ("surface_travail_x_mm", "surface_travail_y_mm"):
    assert cle in core.PER_LASER_KEYS, (
        "%s n'est pas par profil laser : la PrintNC et le Falcon n'ont pas "
        "la même course, et c'est tout le sujet" % cle)
import io as _io                                              # noqa: E402
_src = _io.open("/home/christophe/.local/share/FreeCAD/v1-1/Mod/"
                "LaserAtelier/task_panels.py", encoding="utf-8").read()
assert "spn_surface_x" in _src and '"surface_travail_x_mm": self.spn_surface_x' in _src, (
    "les Préférences n'offrent pas les champs, ou ne les enregistrent pas")
assert "job_hors_surface" in _src, (
    "le contrôle n'est branché nulle part dans l'écriture")
print("   par laser : ✓   champs dans les Préférences : ✓   branché : ✓")

cfg = core.load_config()
cfg["settings"]["surface_travail_x_mm"] = 0.0
cfg["settings"]["surface_travail_y_mm"] = 0.0
core.save_config(cfg)
core._apply_settings_config()

print()
print("TOUT EST VERT")

sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
