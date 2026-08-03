# -*- coding: utf-8 -*-
"""Calligraphie : le squelette, la largeur, et le trait qui sort.

Les contrôles portent sur une forme SYNTHÉTIQUE dont on connaît la réponse
(un trait dont on a dessiné soi-même l'épaisseur) plutôt que sur une police
du commerce : les deux polices d'essai de Christophe sont en licence « usage
personnel » et n'ont donc rien à faire dans le dépôt. Une police du système
sert pour le bout de chaîne qui a besoin d'un vrai fichier.
"""
import math
import sys

from harness import preparer

h = preparer()
core = h.core
import calligraphie as cal          # noqa: E402  (après le harness)
import numpy as np                  # noqa: E402
from PIL import Image, ImageDraw    # noqa: E402


def _trait_fuselé(long_px=600, haut_px=200, w_min=6, w_max=60):
    """Un trait horizontal dont l'épaisseur enfle puis diminue : on connaît
    sa largeur en chaque point, donc on peut juger la mesure."""
    img = Image.new("L", (long_px, haut_px), 0)
    dr = ImageDraw.Draw(img)
    for x in range(20, long_px - 20):
        t = (x - 20) / float(long_px - 40)
        w = w_min + (w_max - w_min) * math.sin(math.pi * t)
        dr.line([x, haut_px // 2 - w / 2, x, haut_px // 2 + w / 2], fill=255)
    return np.array(img) > 127, w_min, w_max


# --- 1. La largeur mesurée est la largeur dessinée ----------------------
_b, _wmin, _wmax = _trait_fuselé()
_sq = cal.amincir(_b)
_lar = cal.largeur_locale(_b)
_mesure = _lar[_sq]
assert abs(_mesure.max() - _wmax) <= 3.0, (
    "largeur maxi mal mesurée", _mesure.max(), _wmax)
# Le squelette s'arrête avant la pointe, donc le mini mesuré est un peu
# au-dessus du mini dessiné -- mais pas au-delà du quart de l'amplitude.
assert _mesure.min() <= _wmin + 0.25 * (_wmax - _wmin), (
    "largeur mini mal mesurée", _mesure.min(), _wmin)
print("1. largeur locale : {:.1f} à {:.1f} px pour {} à {} dessinés OK".format(
    _mesure.min(), _mesure.max(), _wmin, _wmax))

# --- 2. Une chaîne ne SAUTE JAMAIS -------------------------------------
# LE défaut du 03/08/2026 : la détection de boucles refermait une chaîne sur
# son premier pixel sans vérifier qu'on y était revenu. La marche mourant
# dans une impasse à l'autre bout du mot, cela inventait un trait droit en
# travers des dix-huit lettres d'« Atelier du Verdier » -- et ce trait était
# GRAVÉ. Tout ce qui suit interpole entre points consécutifs : un seul saut
# devient un trait. L'invariant se vérifie donc ici, sur la sortie.
def _plus_grand_saut(chaines):
    pire = 0.0
    for c in chaines:
        for a, b in zip(c, c[1:]):
            pire = max(pire, math.hypot(b[0] - a[0], b[1] - a[1]))
    return pire

# Une forme à boucles ET à impasses : un anneau, plus une barre isolée.
_img = Image.new("L", (400, 400), 0)
_dr = ImageDraw.Draw(_img)
_dr.ellipse([60, 60, 300, 300], outline=255, width=16)
_dr.line([120, 350, 380, 350], fill=255, width=14)
_dr.line([330, 90, 380, 200], fill=255, width=10)
_b2 = np.array(_img) > 127
_sq2 = cal.amincir(_b2)
_brut = cal.tracer(_sq2)
_saut = _plus_grand_saut(_brut)
assert _saut <= 3.0, ("le traçage a laissé un saut de {:.0f} px".format(_saut))
_saut_c = _plus_grand_saut(cal.coudre(_brut))
assert _saut_c <= 3.0, ("la couture a laissé un saut de {:.0f} px".format(_saut_c))
print("2. aucun saut dans les chaînes : au pire {:.1f} px (traçage) et "
      "{:.1f} px (couture) OK".format(_saut, _saut_c))

# --- 3. Le trait gravé recouvre la lettre, sans déborder ----------------
# LA mesure qui juge, et celle qui ne juge pas. « Somme des largeurs x
# longueur » surestime toujours (un trait qui tourne se recouvre, un
# croisement compte une fois par branche) : elle m'a fait croire à un défaut
# de +40 % qui n'existait pas, et accepter une « correction » qui a fait
# passer le débordement de 4 % à 67 %. Ce qui tranche est le BALAYAGE : le
# disque promené le long du chemin, comparé pixel à pixel à la forme.
def _balayer(encre, chaines, mm_px, hauteur_mm):
    im = Image.new("L", (encre.shape[1], encre.shape[0]), 0)
    d = ImageDraw.Draw(im)
    for c in chaines:
        for x, y, w in c:
            X, Y = x / mm_px, (hauteur_mm - y) / mm_px
            r = 0.5 * w / mm_px
            d.ellipse([X - r, Y - r, X + r, Y + r], fill=255)
    s = np.array(im) > 127
    return (100.0 * (s & encre).sum() / encre.sum(),
            100.0 * (s & ~encre).sum() / encre.sum())

_polices = cal.polices_disponibles()
assert _polices, "aucune police .otf/.ttf sur ce système : test impossible"
_nom, _chemin = _polices[0]
_TXT = "Verdier"
_encre = cal.rendre_texte(_chemin, _TXT)
_ch, _inf = cal.chaines_calligraphie(_chemin, _TXT, largeur_mm=120.0)
_couv, _deb = _balayer(_encre, _ch, _inf["mm_px"], _inf["hauteur_mm"])
assert _couv >= 88.0, ("le tracé ne couvre pas la lettre", _couv, _nom)
assert _deb <= 8.0, ("le tracé déborde de la lettre", _deb, _nom)
print("3. « {} » en {} : couvre {:.0f} % de la lettre, déborde {:.0f} % OK"
      .format(_TXT, _nom, _couv, _deb))

# --- 4. Le G-code : la hauteur fait la largeur, jamais un dwell allumé --
_MAT = None
for _m in core.burn_width_materials():
    if core.echelle_fuseau_z(_m, 200, power_max=900, line_min_mm=0.0):
        _MAT = _m
        break
assert _MAT, "aucun matériau mesuré dans la config d'essai"
# Le G-code se juge sur un trait DONT ON CONNAÎT le fuseau, pas sur la
# première police venue : celle du système peut très bien être une monospace
# à graisse constante, qui ne demanderait jamais au Z de bouger -- le contrôle
# passerait alors sans rien prouver (constaté ici même : AdwaitaMono).
_TRAIT = [[(0.4 * i, 10.0, 0.20 + 3.0 * math.sin(math.pi * i / 100.0))
           for i in range(101)]]
_g = core.generate_gcode_calligraphie(_TRAIT, 0.0, 200, _MAT, power_max=900,
                                      police=_nom)
assert _g, "aucun G-code produit"
_lignes = _g.split("\n")

import re                                                    # noqa: E402
_puis, _fautes = 0.0, []
for _l in _lignes:
    _m2 = re.search(r"M67 E0 Q(-?\d+\.?\d*)", _l) or re.match(r"S(\d+)", _l)
    if _m2:
        _puis = float(_m2.group(1))
    if re.search(r"\bG4\b", _l) and _puis > 0:
        _fautes.append(_l)
assert not _fautes, ("G4 émis faisceau ALLUMÉ : le job sortirait blanc", _fautes)

_zs = [float(m.group(1)) for m in
       (re.search(r"^G1 .*Z(-?\d+\.\d+)", l) for l in _lignes) if m]
assert len(set(round(z, 2) for z in _zs)) > 10, (
    "le Z ne balaie pas : ce n'est plus un fuseau", len(set(_zs)))

# La puissance SUIT la largeur : sans cela le large sort pâle. On vérifie sur
# les points eux-mêmes, pas sur le texte du fichier.
_gestes, _diag = core.preparer_calligraphie(_TRAIT, 200, _MAT, power_max=900)
_pts = [p for g in _gestes for p in g]
_fins = [p.s for p in _pts if p.w <= _diag["w_min"] * 1.3]
_larges = [p.s for p in _pts if p.w >= _diag["w_max"] * 0.7]
assert _fins and _larges, "pas assez de contraste pour juger"
assert min(_larges) > max(_fins), (
    "la puissance ne suit pas la largeur", max(_fins), min(_larges))
print("4. G-code : {} lignes, Z sur {} paliers, S {:.0f} au fin -> {:.0f} au "
      "large, aucun G4 allumé OK".format(
          len(_lignes), len(set(round(z, 2) for z in _zs)),
          max(_fins), min(_larges)))

# --- 5. On ne remonte pas plus haut qu'il ne faut ----------------------
# Dans ce mode le Z du fuseau ÉLOIGNE la tête du bois : remonter à la garde
# globale depuis un plein, où la tête est déjà à 47 mm, ce sont deux
# allers-retours pour rien -- et sur soixante gestes cela s'entend.
_z_max_g1 = max(_zs)
_montees = [float(m.group(1)) for m in
            (re.match(r"^G0 Z(-?\d+\.\d+)", l) for l in _lignes) if m]
_garde = _z_max_g1 + core.TRAVEL_CLEARANCE_MM
assert max(_montees) <= _garde + 1e-6, (
    "transit plus haut que la garde", max(_montees), _garde)
_inutiles = [z for z in _montees if z > _z_max_g1 + core.TRAVEL_CLEARANCE_MM]
assert not _inutiles, ("remontées au-dessus de toute utilité", _inutiles[:3])
print("5. transits : {} remontées, la plus haute à {:.1f} mm pour un Z gravé "
      "maxi de {:.1f} OK".format(len(_montees), max(_montees), _z_max_g1))

# --- 6. Trop grand : le panneau le DIT, et dit de combien ---------------
# La taille est le seul levier : aucune puissance n'élargit un trait au-delà
# de ce que le défocus mesuré donne. Un panneau qui se tairait laisserait
# graver des pleins tronqués sans prévenir.
tp = h.tp
_p = tp.TaskPanelCalligraphie()
_p.edt_police.setText(_chemin)
_p.edt_texte.setText(_TXT)
for _i in range(_p.combo_mat.count()):
    if _p.combo_mat.itemData(_i) == _MAT:
        _p.combo_mat.setCurrentIndex(_i)
_p.spn_feed.setValue(200.0)
_p.spn_largeur.setValue(90.0)
_p._maj_verdict()
_petit = h.texte(_p.lbl_verdict) if hasattr(h, "texte") else _p.lbl_verdict.text()
_p.spn_largeur.setValue(600.0)
_p._maj_verdict()
_grand = _p.lbl_verdict.text()
assert "plus large" in _grand, ("aucune alerte à 600 mm", _grand[:200])
_conseil = re.search(r"Descends vers (\d+) mm", _grand)
assert _conseil, ("l'alerte ne propose aucune taille", _grand[:200])
assert 10 < int(_conseil.group(1)) < 600, (
    "taille conseillée absurde", _conseil.group(1))
print("6. à 600 mm le verdict alerte et conseille {} mm OK".format(
    _conseil.group(1)))
