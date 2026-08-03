# -*- coding: utf-8 -*-
"""La planche qu'on mesure est celle qu'on croit, à l'échelle qu'il faut.

Christophe, 03/08/2026, après avoir redressé sa planche 1 en sapin : « il
m'ouvre la mauvaise image […] j'ai l'impression qu'il ne lit pas le json,
car je dois les mettre à la main ». Trois défauts, une seule racine : la
liste des planches est bâtie à l'ouverture du panneau et ne bouge plus,
et la fiche .json était cherchée à côté du fichier DÉSIGNÉ plutôt qu'à
côté de la planche.
"""
import glob
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
        json.dump({"fichier": base + ".png", "pxmm": pxmm, "nom": nom,
                   "largeur_mm": 156.0, "hauteur_mm": 76.0,
                   "base_mm": [140.0, 60.0]}, fh)
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


# --- 6. Un nom saisi ne doit pas rendre la planche méconnaissable -------
# Christophe, 03/08/2026 : « le calcul automatique non, il faut que
# j'encadre chaque trait un à un ». Depuis qu'on peut NOMMER sa planche au
# redressement, « planche1 » s'écrit « planche1-Sapin-au-foyer » dans le nom
# de fichier -- et le cadreur testait `"_planche1_" in nom`. Il ne
# reconnaissait donc plus rien et se taisait, ce qui est aussi son
# comportement légitime quand il ne sait pas cadrer : la panne était
# indiscernable du fonctionnement normal.
_CAS = [
    ("LT_planche1_20260801-0909_redresse.png", "planche1"),
    ("LT_planche1-Sapin-au-foyer_20260803-2005_redresse.png", "planche1"),
    ("LT_planche2_20260801-0958_redresse.png", "planche2"),
    ("LT_planche2b_20260801-1114_redresse.png", "planche2b"),
    ("LT_planche2b-hetre-profond_20260801-1114_redresse.png", "planche2b"),
    ("LT_planche_autre_20260802-0735_redresse.png", "planche_autre"),
    ("LT_planche_autre-tons-defocus_20260802-2011_redresse.png", "planche_autre"),
    # Un nom de laser à soulignés ne doit pas non plus tromper le repérage.
    ("Mon_Laser_Bleu_planche1-essai_20260803-2005_redresse.png", "planche1"),
    # C'est le DÉLIMITEUR qui sépare « planche2 » de « planche2b », pas
    # l'ordre d'essai des clés : une clé inconnue collée à une connue ne
    # doit pas se faire lire comme elle.
    ("LT_planche2bis_20260803-2005_redresse.png", None),
    ("LT_planche12_20260803-2005_redresse.png", None),
]
for _nom, _attendu in _CAS:
    _obtenu = core.type_planche(os.path.join(DOSSIER, _nom))
    assert _obtenu == _attendu, ("type de planche mal lu", _nom, _obtenu, _attendu)
assert core.type_planche("/tmp/photo_quelconque.png") is None
print("6. type de planche reconnu sur {} écritures, nom saisi compris OK"
      .format(len(_CAS)))

# --- 7. Le cadreur PROPOSE vraiment sur une planche 1 nommée ------------
# §6 vérifie la lecture du nom ; celui-ci vérifie que le cadreur s'en sert.
# Sans lui, corriger `type_planche` sans le brancher passerait inaperçu.
_NOMMEE = _poser_planche("LT_planche1-Sapin_20260803-2100", 50.0, 3000.0)
_ANONYME = _poser_planche("LT_planche1_20260803-2101", 50.0, 3001.0)
_gr = _m.grille_focus
_cases = _m._cases_ordonnees(_gr)
assert _cases, "aucune case dans la grille du foyer"
_avec = _m._cadreur_auto(_ANONYME + ".png", 50.0, _gr, _cases)
assert _avec is not None, "le cadreur refuse déjà une planche 1 sans nom"
_nomme = _m._cadreur_auto(_NOMMEE + ".png", 50.0, _gr, _cases)
assert _nomme is not None, (
    "le cadreur se tait sur une planche 1 NOMMÉE : le nom saisi la rend "
    "méconnaissable")
_r1, _r2 = _avec(0), _nomme(0)
assert _r1 is not None and _r2 is not None, "aucun cadre pour la 1re case"
assert (_r1.x(), _r1.y(), _r1.width(), _r1.height()) == \
       (_r2.x(), _r2.y(), _r2.width(), _r2.height()), (
    "le nom saisi change le cadre calculé")
_n_cadres = sum(1 for i in range(len(_cases)) if _nomme(i))
assert _n_cadres == len(_cases), (
    "toutes les cases ne sont pas cadrées", _n_cadres, len(_cases))
print("7. planche 1 nommée : {} cases sur {} cadrées, au pixel près comme "
      "sans nom OK".format(_n_cadres, len(_cases)))


# --- 8. LES DEUX boutons qui avancent recadrent l'aperçu ---------------
# Christophe, 03/08/2026 : « les données passent bien à la cellule suivante,
# mais l'aperçu du trait non, il reste bloqué ». « Retenir → case suivante »
# vidait la vue et relançait le cadrage ; « — Pas de valeur → suivante » se
# contentait de bouger la liste déroulante. Un correctif écrit pour un
# bouton et pas pour son jumeau.
#
# Le contrôle porte donc sur LA FAMILLE : tout bouton qui fait avancer la
# case doit laisser l'aperçu sur le trait de la NOUVELLE case. Un test
# écrit pour le seul bouton signalé serait resté vert pendant que l'autre
# gardait le défaut.
import hashlib                                       # noqa: E402


def _empreinte_vue(dlg):
    """Ce que l'oeil voit : le contenu de l'image affichée."""
    if dlg._vue is None:
        return None
    bits = dlg._vue._img.constBits()
    b = bits.tobytes() if hasattr(bits, "tobytes") else bytes(bits)
    return hashlib.md5(b).hexdigest()


def _ouvrir(m, chemin, gr):
    cases = m._cases_ordonnees(gr)
    m._derniere_case = m._mesure_cible = cases[0]
    d = tp._DialogueMesureTrait(
        chemin, 50.0, [m._nom_case(w) or "?" for w in cases], 0,
        m._retenir_depuis_image, m._viser_index,
        cadre_auto=m._cadreur_auto(chemin, 50.0, gr, cases),
        on_vider=m._vider_case)
    assert d._cadrer_auto(), "le cadrage automatique refuse dès la 1re case"
    return d, cases


_VRAIES = sorted(glob.glob("/home/christophe/Planches-LaserAtelier/"
                           "*planche1*_redresse.png"))
assert _VRAIES, "aucune planche 1 redressée sur ce poste"
_IMG = _VRAIES[-1]
_gr = _m.grille_focus
_gr._chk.setChecked(False)

for _libelle, _avancer in (("Retenir → case suivante",
                            lambda d: d._retenir_et_suivant()),
                           ("— Pas de valeur → suivante",
                            lambda d: d._pas_de_valeur())):
    _d, _cases = _ouvrir(_m, _IMG, _gr)
    _vues, _index = [_empreinte_vue(_d)], [_d.combo_cible.currentIndex()]
    for _ in range(3):
        _avancer(_d)
        _vues.append(_empreinte_vue(_d))
        _index.append(_d.combo_cible.currentIndex())
    assert _index == [0, 1, 2, 3], (_libelle, "la case n'avance pas", _index)
    assert None not in _vues, (
        _libelle, "l'aperçu a disparu au lieu de suivre la case", _vues)
    assert len(set(_vues)) == len(_vues), (
        _libelle, "l'aperçu du trait reste bloqué sur la case précédente")
    _d.close()
print("8. les 2 boutons qui avancent recadrent l'aperçu sur la nouvelle case OK")


# --- 9. Ne PAS renseigner une case : les deux gestes du clavier --------
# Christophe, 03/08/2026 : « dans la case, si je ne veux pas de mesure, avec
# le clavier j'écris quoi ? ». Taper 0 marchait ; EFFACER le texte non — un
# QDoubleSpinBox vidé garde sa valeur, et Qt remet l'ancienne en quittant la
# case. Le champ paraissait vide et la mesure précédente partait quand même
# à l'enregistrement, comme si elle avait été relevée. Sur une planche où
# l'on saute les cases illisibles, c'est la façon la plus discrète
# d'inventer une mesure.
from PySide6 import QtCore                             # noqa: E402

_gr9 = _m.grille_focus
_gr9._chk.setChecked(False)
_sp = _m._cases_ordonnees(_gr9)[0]
_cle = next(k for k, w in _gr9.cells().items() if w is _sp)

# a) taper 0
_sp.setValue(0.30)
_sp.setValue(0.0)
assert _sp.text() == "—", ("0 devrait afficher « — »", _sp.text())
assert _cle not in _gr9.values(), "une case à « — » part quand même à l'enregistrement"

# b) effacer le texte, puis quitter la case
_sp.setValue(0.30)
assert _cle in _gr9.values(), "la mesure de départ n'est pas prise en compte"
_sp.lineEdit().selectAll()
_sp.lineEdit().del_()
QtWidgets.QApplication.sendEvent(_sp, QtCore.QEvent(QtCore.QEvent.FocusOut))
assert _sp.value() == 0.0, (
    "effacer le texte laisse l'ancienne mesure : elle sera enregistrée "
    "comme si elle avait été relevée", _sp.value())
assert _cle not in _gr9.values(), "la case effacée part quand même"

# c) et une VRAIE mesure ne doit pas se faire effacer au passage
_sp.setValue(0.42)
QtWidgets.QApplication.sendEvent(_sp, QtCore.QEvent(QtCore.QEvent.FocusOut))
assert abs(_gr9.values().get(_cle, 0.0) - 0.42) < 1e-9, (
    "une mesure saisie a été perdue en quittant la case", _sp.value())
print("9. « — » par 0 ou par effacement ; une vraie mesure survit au focus OK")


# --- 10. La fin de grille se termine, elle ne se grise pas -------------
# Christophe, 03/08/2026, arrivé sur la dernière case : « quand j'ai fini,
# j'ai pas de bouton terminé, juste annulé qui fonctionne mais c'est pas
# intuitif ». « Retenir → case suivante » annonçait la fin et fermait ;
# « — Pas de valeur → suivante » GRISAIT les trois boutons d'action et
# laissait « Annuler » comme seule sortie apparente — après une heure de
# mesures, et alors que rien n'était à annuler.
#
# Encore un contrôle sur LA FAMILLE : les deux boutons qui avancent doivent
# terminer de la même façon.
_annonces = sans_dialogues()

for _libelle, _avancer in (("Retenir → case suivante",
                            lambda d: d._retenir_et_suivant()),
                           ("— Pas de valeur → suivante",
                            lambda d: d._pas_de_valeur())):
    _d, _cases = _ouvrir(_m, _IMG, _gr)
    del _annonces[:]
    # Se placer sur la DERNIÈRE case et avancer une fois de plus.
    _m._derniere_case = _m._mesure_cible = _cases[-1]
    _d.combo_cible.blockSignals(True)
    _d.combo_cible.setCurrentIndex(len(_cases) - 1)
    _d.combo_cible.blockSignals(False)
    _avancer(_d)
    assert _d.result() == QtWidgets.QDialog.Accepted, (
        _libelle, "la fenêtre ne se ferme pas en fin de grille ; il ne reste "
                  "que « Fermer » pour sortir")
    assert _annonces, (_libelle, "la fin de grille n'est pas annoncée")
    _dit = " ".join(a[2] for a in _annonces)
    assert "dernière case" in _dit, (_libelle, "l'annonce ne dit pas pourquoi", _dit)
    assert "Enregistrer les mesures" in _dit, (
        _libelle, "l'annonce ne dit pas où sont passées les largeurs", _dit)
print("10. les 2 boutons terminent la grille en l'annonçant OK")

# --- 11. Le bouton de sortie ne promet pas d'annuler -------------------
# Il ne défait rien : chaque largeur est écrite dans sa case au moment où on
# la retient. L'étiquette « Annuler » faisait hésiter au pire moment.
_d, _ = _ouvrir(_m, _IMG, _gr)
_libelles = [b.text() for b in _d.findChildren(QtWidgets.QPushButton)]
assert "Fermer" in _libelles, ("pas de bouton « Fermer »", _libelles)
assert "Annuler" not in _libelles, (
    "un bouton « Annuler » qui n'annule rien", _libelles)
_d.close()
print("11. la sortie s'appelle « Fermer », pas « Annuler » OK")

shutil.rmtree(DOSSIER, ignore_errors=True)
