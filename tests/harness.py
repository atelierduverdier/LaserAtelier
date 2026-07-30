# -*- coding: utf-8 -*-
"""Harnais commun des tests headless de l'atelier.

Un test commence par `from harness import preparer` puis `h = preparer()`,
et travaille avec `h.core` / `h.tp`. Le harnais s'occupe de tout ce qui,
sinon, se recopie de test en test et finit par diverger :

- Qt en mode OFFSCREEN (aucune fenêtre ne s'ouvre).
- `FreeCADGui.Selection` bouchonné : plusieurs panneaux lisent la sélection
  3D à la construction, et elle n'existe pas sans interface graphique.
- **La config est redirigée vers une COPIE jetable.** C'est la règle la plus
  importante de ce dossier : un test ne doit JAMAIS écrire dans la config de
  l'atelier. Elle contient des mesures faites au pied à coulisse sur du bois
  -- des heures d'établi, irremplaçables par un calcul. La copie garde les
  mêmes données (donc les tests lisent le vrai nuancier, la vraie table de
  kerf), mais toute écriture part à la poubelle.

Le dossier de l'atelier est aussi redirigé, pour que les photos de résultat
écrites par un test n'atterrissent pas à côté du code.
"""
import atexit
import os
import re
import shutil
import sys
import tempfile
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def preparer(config_reelle=True):
    """Prépare l'environnement et renvoie un objet portant `core`, `tp` et
    les utilitaires. `config_reelle=False` part d'une config VIDE (utile
    pour tester les cas « aucun matériau mesuré »)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)

    import FreeCAD
    import FreeCADGui
    if not hasattr(FreeCADGui, "Selection"):
        FreeCADGui.Selection = types.SimpleNamespace(
            getSelectionEx=lambda *a, **k: [],
            getSelection=lambda *a, **k: [],
            clearSelection=lambda *a, **k: None)

    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    import laser_core as core

    bac = tempfile.mkdtemp(prefix="laseratelier-tests-")
    atexit.register(shutil.rmtree, bac, ignore_errors=True)
    copie = os.path.join(bac, "laser_atelier_config.json")
    if config_reelle and os.path.exists(core.CONFIG_FILE):
        shutil.copy(core.CONFIG_FILE, copie)
    else:
        with open(copie, "w") as f:
            f.write("{}")
    core.CONFIG_FILE = copie
    core._WORKBENCH_DIR = bac

    import task_panels as tp
    return types.SimpleNamespace(core=core, tp=tp, app=app, bac=bac,
                                 FreeCAD=FreeCAD, FreeCADGui=FreeCADGui)


# --- Utilitaires partagés --------------------------------------------------

def texte(widget_ou_html):
    """Texte visible d'un QLabel : les verdicts sont écrits en HTML (gras,
    couleur), et un test qui chercherait « 0.30 mm » dans le balisage brut
    passerait à côté dès qu'on met un mot en gras."""
    s = widget_ou_html if isinstance(widget_ou_html, str) else widget_ou_html.text()
    return re.sub(r"<[^>]+>", "", s).strip()


def mouvements(gcode):
    """[(distance_mm, x, y, est_gravure), ...] de chaque déplacement."""
    import math
    x = y = None
    out = []
    for l in gcode.split("\n"):
        mx = re.search(r"\bX(-?\d+\.?\d*)", l)
        my = re.search(r"\bY(-?\d+\.?\d*)", l)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        if l.startswith(("G0 ", "G1 ")) and None not in (x, y, nx, ny):
            d = math.hypot(nx - x, ny - y)
            if d > 1e-9:
                out.append((d, nx, ny, l.startswith("G1 ")))
        x, y = nx, ny
    return out


def trajet_a_vide(gcode):
    """Longueur des déplacements faisceau éteint (mm)."""
    return sum(d for d, _x, _y, grave in mouvements(gcode) if not grave)


def demi_tours_x(gcode):
    """Nombre de CHANGEMENTS DE SENS en X à l'intérieur d'une même ligne
    (Y constant).

    Un tramage à points pose un micro-trait par case. S'il le grave
    toujours vers la droite, la machine doit RECULER avant chaque point des
    lignes parcourues vers la gauche : un aller-retour par point, des
    dizaines de milliers de fois. Rien dans le G-code ne le signale -- ni
    erreur, ni avertissement, et le résultat gravé est le même. Ce qui
    change, c'est ce qu'on entend à l'atelier. Il faut donc compter les
    inversions : sur une image balayée, la réponse attendue est ZÉRO.
    """
    n = 0
    x = y = sens = None
    for l in gcode.split("\n"):
        mx = re.search(r"\bX(-?\d+\.?\d*)", l)
        my = re.search(r"\bY(-?\d+\.?\d*)", l)
        nx = float(mx.group(1)) if mx else x
        ny = float(my.group(1)) if my else y
        if l.startswith(("G0 ", "G1 ")) and None not in (x, y, nx, ny):
            if abs(ny - y) > 1e-9:
                sens = None            # changement de ligne : on repart à zéro
            elif abs(nx - x) > 1e-9:
                s = 1 if nx > x else -1
                if sens is not None and s != sens:
                    n += 1
                sens = s
        x, y = nx, ny
    return n


def hauteurs_z(gcode):
    """Ensemble des Z rencontrés."""
    return {float(v) for v in re.findall(r"Z(-?\d+\.?\d*)", gcode)}


def puissances(gcode, gravure_seule=False):
    """Valeurs de S. `gravure_seule` : uniquement celles portées par un G1
    (les S0 de fin de ligne coupent le faisceau, ce n'est pas une gravure)."""
    if gravure_seule:
        return {int(m.group(1)) for m in
                (re.search(r"\bS(\d+)", l) for l in gcode.split("\n")
                 if l.startswith("G1 ")) if m}
    return {int(m) for m in re.findall(r"\bS(\d+)\b", gcode)}


def image_demo():
    """Une image réelle pour les tests photo, ou None si absente."""
    for p in ("/home/christophe/Images/Moi-laser/moi_gravure_contraste.png",
              os.path.join(RACINE, "resources", "demo", "photo_demo.jpg")):
        if os.path.exists(p):
            return p
    return None
