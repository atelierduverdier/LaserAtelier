# -*- coding: utf-8 -*-
"""À quelle PROFONDEUR est ce contour, et de quel côté part le trait ?

`compute_nesting_depths` compte, pour chaque contour, combien d'autres
l'entourent. Ce nombre décide deux choses sur la vraie pièce :

* **de quel côté compenser la saignée** -- profondeur paire (un
  extérieur) : on décale vers le DEHORS ; impaire (un trou) : vers le
  DEDANS. Se tromper de sens ne rate pas de peu, il rate du DOUBLE de la
  saignée, soit ~0,4 mm sur du 6 mm ;
* **l'ordre de coupe** -- les trous d'abord, sinon la pièce se détache et
  bascule avant que son trou ne soit percé.

Le test du dedans se faisait sur le CENTRE DE MASSE du contour. Un centre
de masse ne se trouve pas forcément dans sa propre forme : une pièce en U,
un croissant, un L le mettent DEHORS. Trouvé à la lecture ligne à ligne du
02/09/2026 -- le trou d'une pièce en U était compté comme un extérieur.

On teste donc avec un SOMMET du contour, qui lui appartient toujours.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import preparer

h = preparer()
core = h.core

# La fonction prend des chaînes de points à `.x` / `.y` (des Vector).
from collections import namedtuple
P = namedtuple("P", "x y")


def _ch(paires):
    """Une chaîne fermée à partir de paires (x, y)."""
    return [P(float(x), float(y)) for x, y in paires]


def _rect(x0, y0, x1, y1):
    """Rectangle fermé, sens direct."""
    return _ch([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])


# --- 1. LE CAS QUI A PAYÉ : UN TROU EN U DANS UNE PIÈCE EN U -----------
# Il faut les DEUX concavités pour que le défaut se voie. La profondeur ne
# compare un contour qu'à ceux de plus GRANDE aire : si la pièce concave
# est la plus grande de la planche, son propre centre de masse n'est
# jamais testé, et l'erreur dort. Elle se réveille dès qu'un contour
# concave est CONTENU dans un autre contour concave.
#
# La pièce : un U de 30x30, encoche x 10..20 ouverte par le haut.
# Le trou  : un U mince tracé dans la matière du U, ses deux branches
#            dans les bras gauche et droit, sa barre en bas.
# Le centre de masse du trou tombe à (15 ; 14,25) -- en plein dans
# l'encoche, donc HORS de la pièce. Le trou passait pour un extérieur :
# saignée compensée vers le dehors (trou 2x saignée trop petit) et coupé
# APRÈS le contour englobant, quand la pièce n'est déjà plus tenue.
_piece_u = _ch([(0, 0), (30, 0), (30, 30), (20, 30), (20, 10), (10, 10),
                (10, 30), (0, 30), (0, 0)])
_trou_u = _ch([(3, 2), (27, 2), (27, 25), (23, 25), (23, 5), (7, 5),
               (7, 25), (3, 25), (3, 2)])
_cx = sum(p.x for p in _trou_u) / len(_trou_u)
_cy = sum(p.y for p in _trou_u) / len(_trou_u)
assert not core._point_in_polygon(_cx, _cy, [(p.x, p.y) for p in _piece_u]), (
    "le gabarit ne mord plus : le centre de masse du trou ({:.2f} ; "
    "{:.2f}) est retombé DANS la pièce, l'essai ne prouverait "
    "rien".format(_cx, _cy))
_p = core.compute_nesting_depths([_piece_u, _trou_u])
assert _p == [0, 1], (
    "trou en U dans une pièce en U : profondeurs 0 puis 1 attendues, "
    "obtenu {} -- le trou est pris pour un contour extérieur".format(_p))
print("1. trou en U dans une pièce en U : le trou reste un trou, bien que "
      "son centre de masse tombe hors de la pièce OK")

# --- 2. NE PAS CASSER LE CAS ORDINAIRE ----------------------------------
_carre = _rect(0, 0, 100, 100)
_creux = _rect(20, 20, 80, 80)
_ilot = _rect(40, 40, 60, 60)
_p = core.compute_nesting_depths([_carre, _creux, _ilot])
assert _p == [0, 1, 2], (
    "carré + trou + îlot : profondeurs 0/1/2 attendues, obtenu "
    "{}".format(_p))
print("2. carré, trou, îlot : 0 / 1 / 2, l'emboîtement ordinaire tient OK")

# --- 3. L'ORDRE DE LA LISTE NE DOIT RIEN CHANGER ------------------------
_p = core.compute_nesting_depths([_ilot, _carre, _creux])
assert _p == [2, 0, 1], (
    "les mêmes contours donnés dans un autre ordre changent de "
    "profondeur : {}".format(_p))
print("3. les profondeurs ne dépendent pas de l'ordre de la liste OK")

# --- 4. UN CROISSANT, MÊME PIÈGE QUE LE U -------------------------------
# Deux demi-disques : le centre de masse d'un croissant assez creusé sort
# de la matière. Construit en polygone pour rester sans OCC.
import math
_ext = [(20 * math.cos(math.radians(a)), 20 * math.sin(math.radians(a)))
        for a in range(0, 181, 10)]
_int = [(16 * math.cos(math.radians(a)), 16 * math.sin(math.radians(a)))
        for a in range(180, -1, -10)]
_croissant = _ch(_ext + _int + [_ext[0]])
_pastille = _rect(-19, 1, -17, 3)   # dans l'épaisseur, à gauche
_p = core.compute_nesting_depths([_croissant, _pastille])
assert _p == [0, 1], (
    "croissant : extérieur (0) puis pastille (1) attendus, obtenu "
    "{}".format(_p))
print("4. croissant mince : le contour reste un extérieur OK")

# --- 5. DEUX PIÈCES CÔTE À CÔTE NE S'ENTOURENT PAS ----------------------
_p = core.compute_nesting_depths([_rect(0, 0, 10, 10), _rect(20, 0, 30, 10)])
assert _p == [0, 0], "deux pièces disjointes : 0 et 0, obtenu {}".format(_p)
print("5. deux pièces disjointes restent deux extérieurs OK")

print()
print("TOUT EST VERT")
