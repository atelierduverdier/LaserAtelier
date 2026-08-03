# -*- coding: utf-8 -*-
"""Le tramage SPIRALE : un trait unique du centre au bord.

Né d'un rendu que Christophe a essayé sur muffinman.io/vertigo le
03/08/2026. Son SVG n'était pas gravable : c'est le CONTOUR d'un ruban
(deux traits par tour une fois importé, qui fondent en aplat), et il
module l'épaisseur de 0,02 à 0,80 mm quand ce laser sait faire 0,10 à
0,30 au foyer. Ici la modulation sort de la table de largeurs MESURÉE,
comme le reste de l'atelier.

Ce que ce fichier fige, et que rien d'autre ne peut voir :
  - le PAS de la spirale est bien l'écart entre deux tours (c'est lui
    qu'on compare à la largeur brûlée -- se tromper là rendrait le
    verdict de couverture faux sans que rien ne le dise) ;
  - la spirale COUVRE le rectangle, coins compris ;
  - le trait est UNIQUE : aucun G0 au milieu de la gravure ;
  - la puissance sort des paliers MESURÉS, jamais d'une échelle inventée.
"""
from harness import preparer, figer_largeurs
h = preparer()
core = h.core
import math, re

MAT = u"HetreSpirale"
figer_largeurs(core, MAT)          # table connue : la propriete, pas les mesures du jour


def _pts_gcode(g):
    out = []
    for l in g.split("\n"):
        m = re.match(r"G[01] X(-?[\d.]+) Y(-?[\d.]+)", l)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
    return out


# --- 1. Le PAS est l'ecart entre deux tours -----------------------------
# Mesure par CROISEMENTS INTERPOLES d'un rayon, jamais par les points qui
# tombent dessus : l'echantillonnage suit la longueur d'arc, donc presque
# aucun point ne tombe pile sur le rayon -- une premiere sonde ecrite
# comme ca annoncait 0,818 mm pour un pas de 0,300.
def _ecart_tours(pts, cx, cy):
    r = []
    for a, b in zip(pts, pts[1:]):
        if (a[1] - cy) * (b[1] - cy) < 0:
            t = (cy - a[1]) / (b[1] - a[1])
            x = a[0] + t * (b[0] - a[0])
            if x > cx:
                r.append(x - cx)
    r.sort()
    e = [b - a for a, b in zip(r, r[1:])]
    return (sum(e) / len(e)) if e else None


for _pas in (0.15, 0.30, 0.50):
    _p = core.points_spirale(80.0, 80.0, _pas)
    _m = _ecart_tours(_p, 40.0, 40.0)
    assert _m is not None and abs(_m - _pas) < 0.005, (
        "le pas demandé n'est pas l'écart entre deux tours", _pas, _m)
print("1. le pas commande l'écart entre tours (0.15/0.30/0.50 mm) OK")

# --- 2. La spirale COUVRE le rectangle, coins compris --------------------
# S'arrêter à la demi-largeur découperait l'image en disque -- joli, mais
# ce serait rogner le sujet sans le dire.
_L, _H = 100.0, 60.0
_p = core.points_spirale(_L, _H, 0.4)
_xs = [q[0] for q in _p]; _ys = [q[1] for q in _p]
assert min(_xs) <= 0.0 and max(_xs) >= _L, ("la spirale n'atteint pas les bords X",
                                            min(_xs), max(_xs))
assert min(_ys) <= 0.0 and max(_ys) >= _H, ("la spirale n'atteint pas les bords Y",
                                            min(_ys), max(_ys))
# ... et sa longueur suit l'aire du disque circonscrit / le pas.
_long = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(_p, _p[1:]))
_theorique = math.pi * (math.hypot(_L, _H) / 2.0) ** 2 / 0.4
assert abs(_long - _theorique) / _theorique < 0.02, (_long, _theorique)
print("2. la spirale couvre le rectangle coins compris, longueur à 2 %% de "
      "la théorie (%.0f mm) OK" % _long)

# --- 3. UN SEUL TRAIT : aucun G0 au milieu de la gravure ----------------
# C'est l'interet propre de ce tramage face aux rangees, qui font un
# demi-tour par ligne.
_W, _Hp = 40, 30
_rows = [[c / (_W - 1.0) for c in range(_W)] for _ in range(_Hp)]
_g = core.generate_gcode_photo_spirale(_rows, 0.30, 8.0, 800.0, MAT,
                                       white_threshold=0.05)
assert _g, "aucun G-code"
_l = _g.split("\n")
_i0 = next(i for i, x in enumerate(_l) if x.startswith("G1 "))
_i1 = len(_l) - 1 - next(i for i, x in enumerate(reversed(_l)) if x.startswith("G1 "))
_g0 = [x for x in _l[_i0:_i1] if x.startswith("G0 ")]
assert not _g0, ("un G0 coupe le trait : ce n'est plus une spirale continue",
                 _g0[:3])
print("3. aucun G0 entre le premier et le dernier G1 : trait unique OK")

# --- 4. Les puissances viennent des paliers MESURES ---------------------
_niv, _wmin, _wmax = core.swell_power_levels(MAT, 800.0, 0.10)
_vues = {int(m.group(1)) for m in re.finditer(r"\bS(\d+)", _g)}
_vues |= {int(m.group(1)) for m in re.finditer(r"\bQ(\d+)", _g)}
_vues.discard(0)                                   # bois nu
_permises = {int(round(p)) for p in _niv}
_hors = sorted(_vues - _permises)
assert not _hors, (
    "des puissances ne sortent pas de la table mesurée -- une échelle "
    "inventée quelque part", _hors[:5], sorted(_permises)[:5])
assert min(_vues) >= min(_permises), (
    "une puissance SOUS le plus bas palier mesuré : le trait y serait "
    "inconnu", min(_vues), min(_permises))
print("4. les %d puissances émises sortent toutes des paliers mesurés OK"
      % len(_vues))

# --- 5. Le seuil de blanc laisse du bois NU -----------------------------
_clair = [[0.02] * _W for _ in range(_Hp)]
_g2 = core.generate_gcode_photo_spirale(_clair, 0.30, 8.0, 800.0, MAT,
                                        white_threshold=0.10)
assert _g2, "pas de G-code sur une image claire"
_non_nuls = {int(m.group(1) or m.group(2))
             for m in re.finditer(r"\bQ(\d+)|\bS(\d+)", _g2)} - {0}
assert not _non_nuls, (
    "une image entièrement sous le seuil grave quand même", sorted(_non_nuls)[:5])
# ... et sans seuil, elle grave (sinon le controle ci-dessus ne prouve rien).
_g3 = core.generate_gcode_photo_spirale(_clair, 0.30, 8.0, 800.0, MAT,
                                        white_threshold=0.0)
_nn3 = {int(m.group(1) or m.group(2))
        for m in re.finditer(r"\bQ(\d+)|\bS(\d+)", _g3)} - {0}
assert _nn3, "sans seuil, l'image claire devrait quand même être gravée"
print("5. sous le seuil : bois nu ; sans seuil : gravé (le contrôle "
      "discrimine) OK")

# --- 6. Refus PARLANT quand le trait n'enfle plus -----------------------
assert core.generate_gcode_photo_spirale(_rows, 0.30, 8.0, 6000.0, MAT,
                                         quiet=True) is None, (
    "à une vitesse où le trait n'enfle plus, la spirale doit refuser")
assert core.generate_gcode_photo_spirale([], 0.30, 8.0, 800.0, MAT) is None
print("6. refuse une vitesse où le trait n'enfle plus, et une image vide OK")

core.save_burn_widths(MAT, {})
print("\nTOUS LES TESTS spirale PASSENT")
