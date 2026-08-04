# -*- coding: utf-8 -*-
"""Texte gravé : le CONTOUR des lettres, pour les polices classiques.

Christophe, 04/08/2026 : « ça fonctionne bien pour certaines fonts
calligraphie mais pour les fonts classiques ça ne fonctionne pas bien, on
peut y mettre une sorte de 2 modes de rendu ? ».

Et ce n'est pas une affaire de précision -- mesuré, un DejaVu Serif passé au
squelette couvre 97,5 % de la lettre et déborde MOINS que La Graziela. C'est
le principe : sur une calligraphie le contour est la trace d'une plume, sur
une police classique le contour EST le dessin.

Comme pour la calligraphie, aucune police n'entre dans le dépôt : on prend
ce que la machine a, et les contrôles portent sur des PROPRIÉTÉS vraies de
n'importe quelle police latine, jamais sur des chiffres d'une police donnée.
"""
import math
import sys

from harness import preparer

h = preparer()
core = h.core
tp = h.tp
import calligraphie as cal          # noqa: E402  (après le harness)

_polices = cal.polices_disponibles()
assert _polices, "aucune police .otf/.ttf sur ce système : test impossible"
_nom, _chemin = _polices[0]


# --- 1. Un contour est FERMÉ, sinon ce n'est pas un contour ------------
# Tout ce qui suit -- Marquage au trait, Gravure remplie, faces OCC -- part
# de là. Un contour ouvert donne une lettre qui fuit : le remplissage
# déborde par la brèche, et personne ne voit d'où ça vient.
_c1, _i1 = cal.contours_texte(_chemin, "Atelier", largeur_mm=80.0)
assert _c1, "aucun contour produit"
for _c in _c1:
    assert len(_c) >= 4, ("un contour de moins de 4 points n'entoure rien",
                          len(_c))
    _d = math.hypot(_c[-1][0] - _c[0][0], _c[-1][1] - _c[0][1])
    assert _d < 1e-9, ("contour NON FERMÉ : il manque {:.3f} mm".format(_d))
print("1. {} contours, tous fermés ({} points, {:.0f} mm de tracé) OK".format(
    _i1["n_contours"], _i1["n_points"], _i1["longueur_mm"]))


# --- 2. Les CONTREFORMES sont des contours à part ----------------------
# Le trou d'un « o », d'un « e », d'un « A ». C'est ce qui distingue ce mode
# du squelette : la lettre garde ses vides. On juge sur une RELATION vraie
# de toute police latine -- un « o » a un trou, un « l » n'en a pas -- et
# jamais sur un compte absolu, qui dépend de la police.
_o, _io = cal.contours_texte(_chemin, "o", largeur_mm=20.0)
_l, _il = cal.contours_texte(_chemin, "l", largeur_mm=20.0)
assert _io["n_contours"] > _il["n_contours"], (
    "le « o » n'a pas plus de contours que le « l » : la contreforme est "
    "perdue, la lettre sortira pleine", _io["n_contours"], _il["n_contours"])
# Et le trou est DEDANS : sa boîte tient dans celle du contour extérieur.
_gros = max(_o, key=lambda c: (max(p[0] for p in c) - min(p[0] for p in c)) *
                              (max(p[1] for p in c) - min(p[1] for p in c)))
_petit = min(_o, key=lambda c: (max(p[0] for p in c) - min(p[0] for p in c)) *
                               (max(p[1] for p in c) - min(p[1] for p in c)))
assert (min(p[0] for p in _petit) > min(p[0] for p in _gros) and
        max(p[0] for p in _petit) < max(p[0] for p in _gros)), (
    "la contreforme du « o » n'est pas à l'intérieur du contour extérieur")
print("2. « o » en {} contours contre {} pour « l » ; la contreforme est bien "
      "dedans OK".format(_io["n_contours"], _il["n_contours"]))


# --- 3. La TAILLE demandée est la taille obtenue -----------------------
# La largeur se donne, la hauteur suit : les proportions de la police ne
# sont pas négociables.
for _large in (30.0, 120.0, 400.0):
    _c3, _i3 = cal.contours_texte(_chemin, "Atelier", largeur_mm=_large)
    assert abs(_i3["largeur_mm"] - _large) < 0.01, (
        "largeur demandée non tenue", _large, _i3["largeur_mm"])
    _xs = [p[0] for c in _c3 for p in c]
    _ys = [p[1] for c in _c3 for p in c]
    assert min(_xs) > -1e-6 and min(_ys) > -1e-6, (
        "le texte ne part pas du coin (0, 0)", min(_xs), min(_ys))
_c3b, _i3b = cal.contours_texte(_chemin, "Atelier", hauteur_mm=25.0)
assert abs(_i3b["hauteur_mm"] - 25.0) < 0.01, (
    "hauteur demandée non tenue", _i3b["hauteur_mm"])
print("3. largeur et hauteur tenues au centième de mm, origine en (0, 0) OK")


# --- 4. LA FLÈCHE EST EN MILLIMÈTRES DE GRAVURE ------------------------
# Piège de fond : les courbes de la police sont dans SES unités (upem), pas
# en mm, et l'échelle ne se connaît qu'une fois la boîte mesurée. Aplatir
# avant de connaître l'échelle donnerait une flèche qui dépend de la police
# et de la taille -- 0,02 mm sur l'une, 2 mm sur l'autre.
#
# Ce qui se vérifie sans reconstruire les Béziers : une flèche plus GROSSE
# doit donner MOINS de points, et le dessin doit rester le même à la flèche
# près. Et à taille égale, deux tailles de gravure doivent donner des
# nombres de points différents -- sinon c'est que la flèche n'a pas suivi.
_fin, _if = cal.contours_texte(_chemin, "Atelier", largeur_mm=80.0,
                               fleche_mm=0.01)
_gros4, _ig = cal.contours_texte(_chemin, "Atelier", largeur_mm=80.0,
                                 fleche_mm=0.5)
assert _ig["n_points"] < _if["n_points"], (
    "une flèche plus grossière ne réduit pas le nombre de points : "
    "l'aplatissement ignore le réglage", _if["n_points"], _ig["n_points"])
assert _ig["n_contours"] == _if["n_contours"], (
    "le nombre de contours a changé avec la flèche : ce n'est plus la même "
    "lettre")
_petit4, _ip = cal.contours_texte(_chemin, "Atelier", largeur_mm=20.0)
_grand4, _igr = cal.contours_texte(_chemin, "Atelier", largeur_mm=400.0)
assert _igr["n_points"] > _ip["n_points"], (
    "gravé 20 fois plus grand, le contour a le même nombre de points : la "
    "flèche n'est pas en mm de gravure", _ip["n_points"], _igr["n_points"])
print("4. flèche 0,01 -> {} points, 0,5 -> {} ; à 20 mm {} points, à 400 mm "
      "{} OK".format(_if["n_points"], _ig["n_points"], _ip["n_points"],
                     _igr["n_points"]))


# --- 5. Ce que la police n'a pas, elle le DIT --------------------------
# La règle de la maison : rien ne disparaît en silence. Le mode mono-trait a
# gravé « franais » pendant des mois parce que le ç était présent mais vide.
_c5, _i5 = cal.contours_texte(_chemin, "Atelier 字宙", largeur_mm=80.0)
assert "字" in _i5["manquants"] or "宙" in _i5["manquants"], (
    "des caractères absents de la police ne sont pas signalés",
    repr(_i5["manquants"]))
_c5b, _i5b = cal.contours_texte(_chemin, "Atelier", largeur_mm=80.0)
assert not _i5b["manquants"], (
    "un texte que la police sait écrire est déclaré incomplet",
    repr(_i5b["manquants"]))
print("5. caractères absents nommés (« {} »), aucun faux positif sur du "
      "latin OK".format(_i5["manquants"]))


# --- 6. Le panneau, et ce qu'il annonce --------------------------------
_p = tp.TaskPanelTexteContour()
_p.edt_police.setText(_chemin)
_p.edt_texte.setText("Atelier du Verdier")
_p.spn_largeur.setValue(120.0)
_p._maj_verdict()
_v = _p.texte_verdict()
assert isinstance(_v, list) and len(_v) >= 2, (
    "le verdict n'est pas une liste de constats", _v)
for _lg in _v:
    assert _lg.strip(), "un constat vide"
    assert len(_lg) < 400, ("un constat trop long : le pavé est revenu",
                            _lg[:120])
# Sans police, il doit le dire plutôt que planter.
_p.edt_police.setText("")
_p._maj_verdict()
assert _p.texte_verdict(), "le panneau reste muet quand il manque la police"
# Et une police illisible ne doit pas remonter en exception.
_p.edt_police.setText(__file__)
_p._maj_verdict()
assert any("mpossible" in _l for _l in _p.texte_verdict()), (
    "une police illisible n'est pas annoncée", _p.texte_verdict())
print("6. panneau : verdict en {} constats, muet ni bavard sur police "
      "manquante ou illisible OK".format(len(_v)))


# --- 7. L'objet posé dans le document ----------------------------------
# On teste le chemin que l'utilisateur EMPRUNTE -- accept() --, pas
# creer_objet_contours_texte appelé directement : entre les deux il y a la
# lecture des champs, et c'est là que les défauts se logent.
import FreeCAD                                            # noqa: E402
_doc = FreeCAD.newDocument("EssaiTexteContour")
try:
    _p2 = tp.TaskPanelTexteContour()
    _p2.edt_police.setText(_chemin)
    _p2.edt_texte.setText("Ateo")
    _p2.spn_largeur.setValue(60.0)
    _p2._maj_verdict()
    assert _p2.accept() is True, "le bouton OK a refusé un cas valide"
    _objs = [o for o in _doc.Objects
             if core.fiche_objet_contours_texte(o)]
    assert len(_objs) == 1, ("l'objet n'a pas été posé", len(_objs))
    _obj = _objs[0]
    _fiche = core.fiche_objet_contours_texte(_obj)
    assert _fiche.get("texte") == "Ateo", ("fiche incomplète", _fiche)
    assert _obj.Shape.Edges, "l'objet posé n'a aucune arête"
    _bb = _obj.Shape.BoundBox
    assert abs(_bb.XLength - 60.0) < 0.2, (
        "l'objet posé n'a pas la largeur demandée", _bb.XLength)
    assert not _obj.Shape.Faces, (
        "l'objet porte des faces : ce mode pose des CONTOURS, c'est Gravure "
        "remplie qui en fait des faces")
    print("7. OK pose 1 objet de {} arêtes, {:.1f} x {:.1f} mm, sans face ; "
          "fiche relue OK".format(len(_obj.Shape.Edges), _bb.XLength,
                                  _bb.YLength))
finally:
    FreeCAD.closeDocument("EssaiTexteContour")
