# -*- coding: utf-8 -*-
"""La planche qu'on mesure est celle qu'on croit, à l'échelle qu'il faut.

Christophe, 03/08/2026, après avoir redressé sa planche 1 en sapin : « il
m'ouvre la mauvaise image […] j'ai l'impression qu'il ne lit pas le json,
car je dois les mettre à la main ». Trois défauts, une seule racine : la
liste des planches est bâtie à l'ouverture du panneau et ne bouge plus,
et la fiche .json était cherchée à côté du fichier DÉSIGNÉ plutôt qu'à
côté de la planche.
"""
import json
import os
import shutil
import tempfile

from harness import preparer, sans_dialogues

h = preparer()
core, tp = h.core, h.tp
from PySide6 import QtWidgets                      # noqa: E402

DOSSIER = tempfile.mkdtemp(prefix="planches_")


def _poser_planche(nom, pxmm, quand):
    """Une planche redressée complète : image de mesure, fiche, aperçu,
    contrôle des repères -- exactement ce que le redressement écrit."""
    base = os.path.join(DOSSIER, nom + "_redresse")
    for suffixe, ext in (("", ".png"), ("_apercu", ".jpg"), ("_reperes", ".jpg")):
        with open(base + suffixe + ext, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" if not suffixe else b"\xff\xd8\xff")
    with open(base + ".json", "w") as fh:
        json.dump({"fichier": base + ".png", "pxmm": pxmm,
                   "nom": nom, "base_mm": [140.0, 60.0]}, fh)
    os.utime(base + ".png", (quand, quand))
    return base


_ANCIENNE = _poser_planche("LT_planche2_20260801-0958", 50.0, 1000.0)
core.dossier_planches = lambda creer=False: DOSSIER

# --- 1. Une planche se retrouve depuis N'IMPORTE LEQUEL de ses fichiers -
# Le calcul d'avant était `splitext(chemin)[0] + ".json"`. Il tombe juste
# sur l'image de mesure et RATE tout le reste -- or le dialogue de fichiers
# propose l'aperçu et le contrôle des repères, qui sont des .jpg comme les
# autres. La fiche existait, à dix centimètres de là, et le panneau
# demandait l'échelle à la main.
for _suf, _ext in (("", ".png"), ("_apercu", ".jpg"),
                   ("_reperes", ".jpg"), ("", ".json")):
    _f = _ANCIENNE + _suf + _ext
    assert core.base_planche(_f) == _ANCIENNE, ("base non retrouvée", _f)
    assert core.fiche_planche(_f).get("pxmm") == 50.0, ("fiche non lue", _f)
    assert core.image_de_mesure(_f) == _ANCIENNE + ".png", (
        "mauvaise image de mesure", _f)
assert core.base_planche("/tmp/une_photo.jpg") is None, (
    "un fichier quelconque passe pour une planche")
assert core.fiche_planche("/tmp/une_photo.jpg") == {}, "fiche inventée"
print("1. planche retrouvée depuis ses 4 fichiers ; un fichier étranger est "
      "refusé OK")

# --- 2. L'aperçu N'EST PAS l'image de mesure ---------------------------
# C'est le défaut dangereux : les deux montrent la même planche, mais
# l'aperçu de la planche Sapin fait 15,38 px/mm contre 50. Mesurer dessus
# en appliquant l'échelle de la fiche donne des largeurs 3,25 fois trop
# petites, en silence -- et ces largeurs partent dans la table du matériau.
assert core.image_de_mesure(_ANCIENNE + "_apercu.jpg") != _ANCIENNE + "_apercu.jpg"
assert core.image_de_mesure(_ANCIENNE + "_reperes.jpg") != _ANCIENNE + "_reperes.jpg"
print("2. aperçu et contrôle des repères renvoient vers l'image de mesure OK")

# --- 3. Le panneau part sur la planche la plus récente ------------------
_msgs = sans_dialogues()
_p = tp.TaskPanelAssistant()
_m = _p._mesures
assert _m._image_mesure == _ANCIENNE + ".png", (
    "la planche par défaut n'est pas la seule présente", _m._image_mesure)
print("3. à l'ouverture, la planche par défaut est la plus récente OK")

# --- 4. Redresser PENDANT la séance rafraîchit la liste -----------------
# LE défaut signalé. La liste était bâtie une fois, à la construction du
# bloc ; la planche qu'on venait de redresser n'y était pas, et « Mesurer
# sur l'image redressée » rouvrait l'ancienne sans le dire.
#
# On pilote LE BOUTON, pas la méthode : c'est le câblage qui manquait, et
# un contrôle appelant `rafraichir_planches` en direct passerait au-dessus
# de ce qui était cassé.
_NOUVELLE = _poser_planche("LT_planche1-Sapin_20260803-2005", 50.0, 2000.0)

_bouton = None
for _b in _p.form.findChildren(QtWidgets.QPushButton):
    if "Redresser une photo" in _b.text():
        _bouton = _b
        break
assert _bouton is not None, "bouton « Redresser une photo » introuvable"

_capture = {}
_vrai = tp._redresser_photo_planche
try:
    def _faux(parent, on_range=None):
        _capture["on_range"] = on_range
    tp._redresser_photo_planche = _faux
    _bouton.click()
finally:
    tp._redresser_photo_planche = _vrai
assert _capture.get("on_range"), "le bouton ne passe aucun rappel de fin"

# Le redressement vient de produire la planche Sapin : le rappel doit
# l'annoncer au bloc de mesure.
_capture["on_range"]("planche1", _NOUVELLE + ".png")
assert _m._image_mesure == _NOUVELLE + ".png", (
    "la planche fraîchement redressée n'est pas devenue la planche mesurée",
    _m._image_mesure)
_libelles = [_m._blocs[0].combo_planche.itemText(i)
             for i in range(_m._blocs[0].combo_planche.count())]
assert any("Sapin" in x for x in _libelles), (
    "la nouvelle planche n'apparaît pas dans la liste", _libelles)
assert len(_libelles) == 2, ("la liste a doublé au lieu d'être refaite",
                             _libelles)
print("4. après un redressement, la liste est refaite et pointe sur « {} » OK"
      .format([x for x in _libelles if "Sapin" in x][0]))

# --- 5. Le rappel accepte de ne rien recevoir --------------------------
# Un redressement peut échouer, ou l'appelant être un panneau sans bloc de
# mesure : le rappel ne doit alors ni tomber ni vider la sélection sans
# raison.
_capture["on_range"]("planche1", None)
assert _m._blocs[0].combo_planche.count() == 2, "la liste a été perdue"
print("5. un redressement sans image ne casse ni la liste ni le panneau OK")

shutil.rmtree(DOSSIER, ignore_errors=True)
