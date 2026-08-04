# -*- coding: utf-8 -*-
"""Le bloc « Nuancier matériau », rangé par usage réel.

Christophe, 04/08/2026, sur Marquage de motif : « on choisit le matériau, ça
c'est OK, classer par, c'est OK aussi, mais après réglage : cela me donne une
liste interminable que je ne regarde jamais. Ce dont je me sers le plus
souvent c'est sur mesure -- largeur et sur mesure noirceur [...] j'utilise le
plus souvent cliquer le ton sur la photo. Voir la photo du nuancier, je
trouve que cela fait doublon ».

Trois changements, et le troisième n'est PAS celui qu'il demandait :

  * la photo cliquable passe en tête, la liste des tons mesurés et les
    pastilles descendent dans une section repliée ;
  * « Ton sur mesure » prend sa propre section, ouverte ;
  * les deux boutons photo FUSIONNENT au lieu que l'un disparaisse. Ils
    n'étaient pas tout à fait doublons : cliquer un ton exige en plus la
    FICHE de disposition de la planche, et sans elle seul « Voir » marchait.
    Supprimer « Voir » aurait rendu la photo inatteignable pour ces
    matériaux-là.
"""
import sys

from harness import preparer
from PySide6 import QtWidgets                             # noqa: E402

h = preparer()
core = h.core
tp = h.tp


def _formulaire(panneau, contient):
    """Le QFormLayout qui porte la rangée `contient`.

    Pas « le plus garni » : le panneau Marquage a un sous-formulaire de
    paramètres de style plus long que le formulaire principal, et c'est lui
    qu'on décrochait -- avec des libellés qui n'ont rien à voir."""
    for form in panneau.form.findChildren(QtWidgets.QFormLayout):
        for i in range(form.rowCount()):
            it = form.itemAt(i, QtWidgets.QFormLayout.LabelRole)
            if (it is not None and it.widget() is not None
                    and (it.widget().text() or "").strip() == contient):
                return form
    raise AssertionError("aucun formulaire ne porte « {} »".format(contient))


def _rangs(form):
    """Rang de chaque libellé de rangée, pour juger d'un ORDRE."""
    out = {}
    for i in range(form.rowCount()):
        it = form.itemAt(i, QtWidgets.QFormLayout.LabelRole)
        if it is not None and it.widget() is not None:
            t = (it.widget().text() or "").strip()
            if t:
                out.setdefault(t, i)
    return out


# --- 1. Un seul bouton photo, et il dit les deux usages ----------------
_p = tp.TaskPanelCurved([])
_sp = _p._shade_picker
assert "clic" in _sp, "le bouton photo a disparu du picker"
_txt = _sp["clic"].text()
assert "Voir" in _txt and "cliquer" in _txt.lower(), (
    "le libellé du bouton ne dit pas ses deux usages", _txt)
_boutons = [b.text() for b in _p.form.findChildren(QtWidgets.QPushButton)]
assert "Voir la photo du nuancier" not in _boutons, (
    "les deux boutons photo coexistent encore : c'est le doublon signalé",
    _boutons)
print("1. un seul bouton photo : « {} » OK".format(_txt))


# --- 2. IL S'ACTIVE DÈS QU'UNE PHOTO EXISTE ----------------------------
# C'est tout l'intérêt de la fusion : sans fiche de planche on ne peut pas
# cliquer un ton, mais on peut encore VOIR la photo. Le bouton restait
# grisé dans ce cas -- donc la photo était inatteignable.
_vraies_photos = core.result_photos
_vraies_fiches = core.load_fiches_nuancier_planche
try:
    core.result_photos = lambda cle: [{"path": "/tmp/x.png", "description": ""}]
    core.load_fiches_nuancier_planche = lambda m: []          # AUCUNE fiche
    _p2 = tp.TaskPanelCurved([])
    _p2._shade_picker["reload"]()
    assert _p2._shade_picker["clic"].isEnabled(), (
        "photo présente mais pas de fiche : le bouton est grisé, donc la "
        "photo est inatteignable — c'est ce que « Voir la photo » servait "
        "à faire")
    _tip = _p2._shade_picker["clic"].toolTip()
    assert "MONTRE" in _tip, ("l'infobulle ne dit pas qu'il se contente de "
                              "montrer", _tip[:120])
    # Et sans AUCUNE photo, il doit être grisé : rien à montrer.
    core.result_photos = lambda cle: []
    _p3 = tp.TaskPanelCurved([])
    _p3._shade_picker["reload"]()
    assert not _p3._shade_picker["clic"].isEnabled(), (
        "le bouton est actif sans aucune photo")
finally:
    core.result_photos = _vraies_photos
    core.load_fiches_nuancier_planche = _vraies_fiches
print("2. actif dès qu'une photo existe (même sans fiche), grisé sans photo OK")


# --- 3. LA LISTE EST DERRIÈRE UN REPLI, LA PHOTO NON -------------------
# `_section` ouvre un NOUVEAU formulaire pour ce qu'elle contient : c'est
# la structure elle-même qui dit ce qui est replié, et non un rang de
# rangée. Le contrôle porte donc là-dessus.
def _forme_du(panneau, widget):
    """Le QFormLayout qui contient ce widget."""
    for form in panneau.form.findChildren(QtWidgets.QFormLayout):
        for i in range(form.count()):
            it = form.itemAt(i)
            if it is not None and it.widget() is widget:
                return form
        # un bouton posé seul sur sa rangée passe par un sous-layout
        for i in range(form.rowCount()):
            for role in (QtWidgets.QFormLayout.FieldRole,
                         QtWidgets.QFormLayout.SpanningRole):
                it = form.itemAt(i, role)
                if it is not None and it.widget() is widget:
                    return form
    return None

_f_mat = _forme_du(_p, _sp["mat"])
_f_clic = _forme_du(_p, _sp["clic"])
_f_liste = _forme_du(_p, _sp["shade"])
assert _f_mat is not None and _f_clic is not None and _f_liste is not None, (
    "un des trois contrôles n'a pas été retrouvé dans le panneau")
assert _f_clic is _f_mat, (
    "la photo cliquable n'est pas avec le matériau, en haut : c'est ce dont "
    "Christophe se sert le plus")
assert _f_liste is not _f_mat, (
    "la liste des tons est restée dans la section du haut : elle devait "
    "descendre dans un repli -- « une liste interminable que je ne regarde "
    "jamais »")

_titres = [w.text() for w in _p.form.findChildren(QtWidgets.QLabel)
           if (w.text() or "").strip()]
assert any("piocher dans la liste" in t for t in _titres), (
    "la section repliée n'a pas de titre : une liste sans titre repliée est "
    "une liste perdue")
print("3. photo cliquable avec le matériau ; liste des tons dans une section "
      "à part, titrée OK")


# --- 4. « Ton sur mesure » N'EST PAS dans le repli ---------------------
# Le piège de la maison, payé trois fois : des rangées ajoutées après une
# section repliée lui appartiennent. Ce sont justement les deux champs dont
# Christophe se sert le plus.
_f_mesure = _forme_du(_p, _p.spn_custom_width)
assert _f_mesure is not None, "le champ « sur mesure -- largeur » a disparu"
assert _f_mesure is not _f_liste, (
    "les champs « sur mesure » sont tombés DANS le repli de la liste des "
    "tons : ils deviendraient invisibles alors que ce sont les plus utilisés")
assert any("Ton sur mesure" in t for t in _titres), (
    "« Ton sur mesure » n'a pas de titre de section", _titres[:12])
print("4. « Ton sur mesure » dans sa propre section, hors du repli OK")
