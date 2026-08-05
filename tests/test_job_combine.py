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


# --- LES CALQUES : une couleur par mode, une case pour graver ou non ----
# Christophe, 05/08/2026, après avoir vu LightBurn : « il y a une sorte de
# calque pour chaque type de trait ou travail afin de les sélectionner ou
# pas pour la gravure, et aussi grâce à la couleur de voir sur l'écran quel
# job pour quel trait ».
#
# Les Jobs de l'arbre TENAIENT DÉJÀ ce rôle -- un par couple (mode, forme),
# et `ajouter_jobs_au_combine` en faisait déjà un fichier unique. Il
# manquait la couleur et la case.
import laser_jobs as lj                                       # noqa: E402
import Part                                                   # noqa: E402

# TOUT MODE DOIT AVOIR SA COULEUR, sinon sa forme reste de la couleur du
# document et le calque est muet précisément là où on le regarde.
_sans = sorted(set(lj.MODES) - set(lj.COULEURS_MODE))
assert not _sans, ("des modes n'ont aucune couleur de calque : leurs formes "
                   "ne diront rien", _sans)
# Et elles doivent SE DISTINGUER : deux calques de même couleur ne sont
# qu'un calque.
_couleurs = list(lj.COULEURS_MODE.values())
for _i, _a in enumerate(_couleurs):
    for _b in _couleurs[_i + 1:]:
        _ecart = sum(abs(x - y) for x, y in zip(_a, _b))
        assert _ecart > 0.30, (
            "deux modes portent des couleurs trop proches pour être "
            "séparées à l'œil", _a, _b, _ecart)

_doc = FreeCAD.newDocument("EssaiCalques")


def _trait(nom):
    o = _doc.addObject("Part::Feature", nom)
    o.Shape = Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                               FreeCAD.Vector(10, 0, 0)).toShape()
    return o


try:
    _a, _b = _trait("Contour"), _trait("Motif")
    _doc.recompute()
    _j1 = lj.creer_ou_maj_job("flat", [_a])
    _j2 = lj.creer_ou_maj_job("curved", [_b])
    assert _j1.Grave is True and _j2.Grave is True, (
        "un job neuf doit être gravé par défaut : sinon une planche préparée "
        "comme avant sortirait vide")

    # DÉCOCHÉ = PAS GRAVÉ, et la raison est NOMMÉE. Un job qui disparaît du
    # fichier sans un mot, c'est une planche ratée qu'on ne s'explique pas.
    tp._COMBINED_OPS[:] = []
    _j1.Grave = False
    _doc.recompute()
    _aj, _ig = lj.ajouter_jobs_au_combine([_j1])
    assert _aj == [] and len(tp._COMBINED_OPS) == 0, (
        "un job décoché est quand même parti dans le job combiné", _aj)
    assert _ig and "décoché" in _ig[0], (
        "le job décoché est ignoré SANS le dire", _ig)

    # SABOTAGE : la case doit être ce qui bloque, et non un refus général.
    # Recoché, le même job doit repasser la porte -- il échouera plus loin,
    # sur la sélection 3D que le harnais ne sait pas bouchonner, et c'est
    # justement la preuve qu'il a dépassé la case.
    _j1.Grave = True
    _doc.recompute()
    try:
        _aj2, _ig2 = lj.ajouter_jobs_au_combine([_j1])
        _passe = not (_ig2 and "décoché" in _ig2[0])
    except AttributeError:
        _passe = True          # tombé APRÈS la case, sur Gui.Selection
    assert _passe, (
        "recoché, le job est toujours refusé pour « décoché » : ce n'est pas "
        "la case qui gouverne, et le contrôle ci-dessus ne prouve rien")

    # UNE PILE DE CALQUES : décocher celui du dessus doit RÉVÉLER celui du
    # dessous. La v2.93 peignait job par job, dernier arrivé gagnant, si
    # bien que décocher un job GRISAIT une forme que deux autres gravaient
    # encore -- Christophe, trois jobs sur un même texte : « quand je décoche
    # gravure oui / non la couleur du dessous ou dessus ne s'affiche pas ».
    _t = _trait("Texte")
    _doc.recompute()
    _jm = lj.creer_ou_maj_job("curved", [_t])
    _jf = lj.creer_ou_maj_job("filled", [_t])
    _jh = lj.creer_ou_maj_job("hatch", [_t])

    def _qui_gagne():
        _actifs = lj.rafraichir_calques(_doc).get(_t.Label, [])
        return next((_m for _m in lj.PRIORITE_CALQUE if _m in _actifs), None)

    assert _qui_gagne() == "filled", (
        "avec les trois cochés, ce n'est pas le plus conséquent qui montre "
        "sa couleur", _qui_gagne())
    _jf.Grave = False
    assert _qui_gagne() == "hatch", (
        "décocher la gravure remplie ne révèle pas le calque du dessous",
        _qui_gagne())
    _jh.Grave = False
    assert _qui_gagne() == "curved", (
        "décocher deux calques ne révèle pas le troisième", _qui_gagne())
    _jm.Grave = False
    assert _qui_gagne() is None, (
        "tout décoché, la forme devrait passer au gris et non garder une "
        "couleur de mode", _qui_gagne())
    _jf.Grave = True
    assert _qui_gagne() == "filled", (
        "recocher un calque ne le fait pas revenir")

    # ET LA PILE DOIT ÊTRE COMPLÈTE : un mode absent de la priorité ne
    # gagnerait jamais, donc sa couleur ne s'afficherait jamais.
    assert set(lj.PRIORITE_CALQUE) == set(lj.COULEURS_MODE), (
        "des modes colorés ne figurent pas dans la pile des calques",
        set(lj.COULEURS_MODE) - set(lj.PRIORITE_CALQUE))

    # Une forme d'UN SEUL job n'est pas signalée comme partagée.
    assert lj.colorer_sources(_j2) == [], (
        "une forme d'un seul job est signalée comme partagée")
    assert lj.colorer_sources(_jm) == ["Texte"], (
        "une forme servant à trois jobs n'est pas signalée",
        lj.colorer_sources(_jm))
    # LA COULEUR DIT QUEL TRAVAIL, pas seulement quel mode. Ce qui noircit
    # une aire se montre REMPLI (la face prend la couleur) ; ce qui marque
    # ou coupe se montre au TRAIT seul -- forcer un solide 3D en fil de fer
    # pour la beauté du calque rendrait le modèle inutilisable.
    assert lj.MODES_REMPLIS <= set(lj.MODES), (
        "un mode remplissant n'existe pas dans la table des modes",
        lj.MODES_REMPLIS - set(lj.MODES))
    assert "filled" in lj.MODES_REMPLIS and "hatch" in lj.MODES_REMPLIS, (
        "la gravure remplie et les hachures noircissent une aire : elles "
        "doivent se montrer remplies", lj.MODES_REMPLIS)
    for _m in ("flat", "curved_cut", "curved"):
        assert _m not in lj.MODES_REMPLIS, (
            "« {} » suit un trait : peindre sa face masquerait le modèle "
            "sous une couleur pleine".format(_m))
    # Le gris d'extinction doit être TRÈS clair -- demandé tel quel -- sans
    # quoi une planche à moitié décochée reste illisible.
    assert min(lj.GRIS_ETEINT) > 0.75, (
        "le gris des jobs décochés n'est pas assez clair : les formes "
        "éteintes continuent de réclamer l'attention", lj.GRIS_ETEINT)
    # ET IL DOIT SE DISTINGUER DE TOUTES LES COULEURS DE MODE, sinon un job
    # éteint se lirait comme un job allumé.
    for _m, _c in lj.COULEURS_MODE.items():
        _e = sum(abs(x - y) for x, y in zip(_c, lj.GRIS_ETEINT))
        assert _e > 0.40, (
            "la couleur du mode « {} » se confond avec le gris éteint"
            .format(_m), _c, _e)

    print("calques : {} modes colorés et distincts, job décoché ignoré "
          "(« {} »), forme partagée nommée OK".format(
              len(lj.COULEURS_MODE), _ig[0]))
finally:
    FreeCAD.closeDocument("EssaiCalques")
