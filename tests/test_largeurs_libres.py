# -*- coding: utf-8 -*-
"""Saisie LIBRE des largeurs brûlées : (S, F, défocus, largeur) hors grille.

La saisie des largeurs passait uniquement par la grille miroir de la Planche 2 :
puissances 1000..200, vitesses 200..800, défocus 15 et 36. Juste pour une
planche, qui grave une grille discrète. Mais la RAMPE mesure un CONTINUUM — la
puissance et la hauteur montent ensemble le long de chaque ligne. La première
rampe Z gravée (30/07/2026) a donné cinq points du genre S980/F200 à défocus
60 : aucun n'entrait dans la grille, et il n'existait nulle part où les mettre.

Ce que ce test protège, et c'est le plus important : `save_burn_widths` ÉCRASE
la table du matériau. Une saisie qui oublierait de fusionner ferait disparaître
des heures d'établi en un clic. C'est la donnée la plus irremplaçable du
projet.
"""
from harness import preparer

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"

# Les cinq vrais points relevés sur la rampe du 30/07/2026, avec la puissance
# RÉELLEMENT gravée à cet endroit (la rampe monte S et Z ensemble).
RELEVES = [
    (980.0, 200.0, 60.0, 4.00),
    (909.0, 400.0, 55.0, 3.00),
    (716.0, 600.0, 40.0, 2.00),
    (585.0, 800.0, 30.0, 1.50),
    (392.0, 1000.0, 15.0, 1.00),
]

# --- 1. Aucun de ces points n'entre dans la grille figée ----------------
# C'est la raison d'être de la table libre : le prouver plutôt que l'affirmer.
G = tp._MesuresPlanchesControleur
hors = [(s, f, dz) for s, f, dz, _w in RELEVES
        if s not in G.POWERS or f not in G.FEEDS_DEFOCUS
        or dz not in core.DEFOCUS_LEVELS_MM]
assert len(hors) == len(RELEVES), ("un relevé entrait dans la grille", hors)
print("1. les {} relevés sont TOUS hors de la grille figée (S {}, F {}, "
      "défocus {}) OK".format(len(RELEVES), G.POWERS, G.FEEDS_DEFOCUS,
                              core.DEFOCUS_LEVELS_MM))

# --- 2. La fusion n'efface RIEN ----------------------------------------
avant = core.load_config().get("burn_widths", {}).get(MAT, {})
n_focus_avant = len(avant.get("focus", []) or [])
n_defoc_avant = len(avant.get("defocus", []) or [])
assert n_focus_avant and n_defoc_avant, "la copie de config n'a pas de mesures"

p = tp.TaskPanelPowerRamp()
p.combo_mat.setCurrentText(MAT)
table = p._largeurs["table"]
from PySide6 import QtWidgets
for r, (s, f, dz, w) in enumerate(RELEVES):
    for c, v in enumerate((s, f, dz, w)):
        table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))
p._largeurs["table"].parentWidget()      # (le widget est bien monté)
# Déclencher l'enregistrement comme le ferait le bouton.
for b in p.form.findChildren(QtWidgets.QPushButton):
    if b.text() == "Enregistrer ces largeurs":
        b.click()
        break
else:
    raise AssertionError("bouton « Enregistrer ces largeurs » introuvable")

apres = core.load_config().get("burn_widths", {}).get(MAT, {})
assert len(apres.get("focus", [])) == n_focus_avant, (
    "des mesures AU FOYER ont disparu", n_focus_avant,
    len(apres.get("focus", [])))
assert len(apres.get("defocus", [])) == n_defoc_avant + len(RELEVES), (
    "les 5 points n'ont pas tous été ajoutés, ou d'anciens ont disparu",
    n_defoc_avant, len(apres.get("defocus", [])))
print("2. fusion : {} -> {} points en défocus, et les {} du foyer intacts OK"
      .format(n_defoc_avant, len(apres.get("defocus", [])), n_focus_avant))

# --- 3. Les valeurs stockées sont EXACTEMENT celles saisies -------------
# Lecture brute : `load_burn_widths` arrondirait les défocus.
brut = {(float(pt["power"]), float(pt["feed"]), float(pt.get("z_offset", 0)))
        : float(pt["width"]) for pt in apres.get("defocus", [])}
for s, f, dz, w in RELEVES:
    assert (s, f, dz) in brut, ("point absent", s, f, dz, sorted(brut)[:3])
    assert abs(brut[(s, f, dz)] - w) < 1e-9, (s, f, dz, brut[(s, f, dz)], w)
print("3. les 5 points sont stockés à leur défocus EXACT (30, 40, 55, 60...) OK")

# --- 4. Réenregistrer ne duplique pas ----------------------------------
for b in p.form.findChildren(QtWidgets.QPushButton):
    if b.text() == "Enregistrer ces largeurs":
        b.click()
        break
encore = core.load_config().get("burn_widths", {}).get(MAT, {})
assert len(encore.get("defocus", [])) == n_defoc_avant + len(RELEVES), (
    "un second enregistrement a dupliqué les points",
    len(encore.get("defocus", [])))
print("4. deuxième enregistrement : remplacement, pas duplication OK")

# --- 5. Le défocus 40 est bien RELU à 36, et c'était le piège ----------
# `_snap_defocus_level` ramène au niveau standard à moins de 5 mm. On ne le
# corrige pas -- il protège les mesures héritées (15,34 -> 15) -- mais la
# table doit le DIRE, sinon un 40 saisi devient un 36 sans un mot.
assert abs(core._snap_defocus_level(40.0) - 36.0) < 1e-9, "le 40 ne snappe plus"
assert abs(core._snap_defocus_level(30.0) - 30.0) < 1e-9, "le 30 ne doit PAS snapper"
assert abs(core._snap_defocus_level(60.0) - 60.0) < 1e-9, "le 60 ne doit PAS snapper"
lus = core.load_burn_widths(MAT).get("defocus", [])
niveaux = sorted({round(float(pt.get("z_offset", 0) or 0), 1) for pt in lus})
assert 40.0 not in niveaux and 36.0 in niveaux, (
    "le 40 devrait être relu comme 36", niveaux)
assert 30.0 in niveaux and 55.0 in niveaux and 60.0 in niveaux, niveaux
print("5. relecture : 30/55/60 conservés, 40 rangé en 36 comme annoncé — "
      "niveaux présents {} OK".format(niveaux))

# --- 6. Une ligne incomplète est ignorée, pas devinée ------------------
table.setItem(6, 0, QtWidgets.QTableWidgetItem("500"))   # S seul, sans F ni largeur
avant6 = len(core.load_config().get("burn_widths", {}).get(MAT, {})
             .get("defocus", []))
for b in p.form.findChildren(QtWidgets.QPushButton):
    if b.text() == "Enregistrer ces largeurs":
        b.click()
        break
apres6 = len(core.load_config().get("burn_widths", {}).get(MAT, {})
             .get("defocus", []))
assert apres6 == avant6, ("une ligne incomplète a été enregistrée", avant6, apres6)
print("6. ligne incomplète ignorée, aucune valeur devinée OK")

print("\nTOUS LES TESTS largeurs_libres PASSENT")
