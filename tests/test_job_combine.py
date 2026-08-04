# -*- coding: utf-8 -*-
"""Job combiné : OK ferme, un bouton génère.

Christophe, 04/08/2026 : « j'ai créé plusieurs jobs, je veux en effacer un
puis revenir travailler afin d'en mettre un autre, mais si je clique sur OK
après l'effacement du job il veut me créer le fichier ; un bouton afin de
créer le G-code serait mieux, et le bouton OK sert à valider ».

La génération était accrochée à `accept()`, donc la SEULE façon de fermer le
panneau après avoir remanié la liste était d'écrire un fichier dont on ne
voulait pas. C'est la convention déjà appliquée aux quatre panneaux de test
en v2.20 : le travail se fait par un bouton, OK ferme.

On teste le CÂBLAGE du panneau, pas le générateur : `generate_gcode_combined`
est bouchonné. Ce qui a changé est l'endroit d'où part l'écriture, et c'est
cela qu'il faut prendre.
"""
import sys

from harness import preparer, sans_dialogues

h = preparer()
core = h.core
tp = h.tp
import FreeCAD                                            # noqa: E402

_doc = FreeCAD.newDocument("EssaiJobCombine")
_ecrits = []
_vrai_write = tp._write_gcode_with_dialog
_vrai_gen = core.generate_gcode_combined
tp._write_gcode_with_dialog = (
    lambda form, gcode, defaut: (_ecrits.append(defaut), "/tmp/essai.ngc")[1])
core.generate_gcode_combined = lambda ops, **kw: "G21\nG90\nM2\n"
sans_dialogues()
try:
    _p = tp.TaskPanelCombined()
    _p.operations.clear()
    _p.operations.append({"type": "flat", "label": "essai 1", "params": {}})
    _p.operations.append({"type": "flat", "label": "essai 2", "params": {}})
    # Le widget de liste ne se peuple pas tout seul : empiler dans
    # `operations` sans le dire à la vue laisse `currentRow()` à -1, et la
    # suppression ne trouve rien à supprimer.
    _p._refresh_list()

    # (a) OK NE DOIT RIEN ÉCRIRE. C'est tout le défaut : supprimer une
    #     opération puis fermer écrivait un fichier.
    assert _p.accept() is True, "OK doit fermer le panneau"
    assert not _ecrits, (
        "OK a écrit un fichier : remanier la liste puis fermer grave un job "
        "dont on ne veut pas", _ecrits)

    # (b) ET IL NE DOIT RIEN PERDRE : la liste survit, sinon on ne peut pas
    #     revenir la compléter.
    assert len(_p.operations) == 2, (
        "OK a vidé la liste des opérations", len(_p.operations))

    # (c) LE BOUTON, LUI, ÉCRIT -- et le panneau reste ouvert.
    assert hasattr(_p, "btn_generer"), "pas de bouton de génération"
    _p.btn_generer.click()
    assert len(_ecrits) == 1, (
        "le bouton n'a pas écrit le fichier du job", _ecrits)
    assert len(_p.operations) == 2, (
        "générer a vidé la liste : on ne pourrait pas regénérer")

    # (d) On peut supprimer, regénérer, sans jamais fermer.
    _p.list_ops.setCurrentRow(0)
    _p._on_remove()
    assert len(_p.operations) == 1, ("la suppression n'a pas eu lieu",
                                     len(_p.operations))
    _p.btn_generer.click()
    assert len(_ecrits) == 2, ("regénérer après suppression n'a pas écrit",
                               _ecrits)

    # (e) Liste vide : le bouton refuse, et ne ferme rien.
    _p._on_clear()
    assert not _p.operations
    _p.btn_generer.click()
    assert len(_ecrits) == 2, (
        "un job VIDE a produit un fichier", _ecrits)
    assert _p.accept() is True, "OK doit fermer même sur une liste vide"
    print("1. OK ferme sans rien écrire (liste de {} gardée) ; le bouton "
          "écrit {} fois, supprime et regénère sans fermer ; liste vide "
          "refusée OK".format(2, len(_ecrits)))
finally:
    tp._write_gcode_with_dialog = _vrai_write
    core.generate_gcode_combined = _vrai_gen
    FreeCAD.closeDocument("EssaiJobCombine")
