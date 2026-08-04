#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Capture d'écran d'un panneau de l'atelier, EN DEHORS de FreeCAD.

    outils/capturer_panneau.py <sortie.png> <TaskPanelXxx> [largeur]

La procédure d'avant passait par la session FreeCAD ouverte : on y
instanciait le panneau, on le posait avec `WA_DontShowOnScreen`, on
capturait. Ça marchait, mais ça touchait à la session de travail -- et cet
atelier a déjà perdu un document non enregistré comme ça (02/08/2026).
Ici tout se passe dans un interpréteur à part, en mode offscreen : rien
n'est ouvert, fermé ni enregistré chez l'utilisateur.

    PYTHONPATH=/tmp/.mount_FreeCAxxxx/usr/lib:tests:. \
    FONTCONFIG_PATH=/etc/fonts FONTCONFIG_FILE=/etc/fonts/fonts.conf \
    /tmp/.mount_FreeCAxxxx/usr/bin/python outils/capturer_panneau.py \
        docs/manuel_img/calligraphie.png TaskPanelCalligraphie 430

LES DEUX VARIABLES FONTCONFIG SONT INDISPENSABLES, et `FONTCONFIG_PATH`
est celle qu'on oublie. Sans elle, Qt ne trouve aucune fonte système et
retombe sur une chasse fixe : la capture reste lisible, elle ne ressemble
simplement plus du tout aux vingt et une autres de la galerie -- et les
①②③ des sections sortent en « 0 ». Constaté en livrant trois captures
d'affilée dans ce faux rendu, le 04/08/2026.

Largeurs de la maison : **453** px pour `docs/screenshots/panneaux/`,
**430** px pour `docs/manuel_img/`.
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "tests"))
sys.path.insert(0, RACINE)

from harness import preparer, sans_dialogues          # noqa: E402


def capturer(sortie, classe, largeur=453):
    h = preparer()
    # Le panneau doit s'afficher dans les réglages RÉELS de l'atelier
    # (dialecte, M67, hauteurs) : une capture est une documentation, pas
    # un test.
    h.core._apply_settings_config()
    sans_dialogues()
    from PySide6 import QtWidgets, QtCore

    app = QtWidgets.QApplication.instance()
    panneau = getattr(h.tp, classe)()
    w = panneau.form.widget() if hasattr(panneau.form, "widget") else panneau.form
    w.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    w.setFixedWidth(int(largeur))
    w.adjustSize()
    w.resize(int(largeur), max(w.sizeHint().height(), 400))
    w.show()
    for _ in range(8):
        app.processEvents()
    w.grab().save(sortie)

    # Rogner le vide du bas : le widget est toujours plus haut que son
    # contenu, et une capture qui traîne 400 px de gris dilue la page.
    from PIL import Image
    im = Image.open(sortie).convert("RGB")
    px, (larg, haut) = im.load(), im.size
    fond = px[larg - 2, haut - 2]
    bas = haut
    while bas > 10 and all(px[x, bas - 1] == fond for x in range(0, larg, 3)):
        bas -= 1
    im.crop((0, 0, larg, min(haut, bas + 8))).save(sortie)
    return Image.open(sortie).size


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    taille = capturer(sys.argv[1], sys.argv[2],
                      sys.argv[3] if len(sys.argv) > 3 else 453)
    print("écrit : {} {}".format(sys.argv[1], taille))
