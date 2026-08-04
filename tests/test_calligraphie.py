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

from harness import preparer, sans_dialogues

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
_petit = _p.texte_verdict()
_p.spn_largeur.setValue(600.0)
_p._maj_verdict()
_grand = _p.texte_verdict()
assert "plus large" in _grand, ("aucune alerte à 600 mm", _grand[:200])
_conseil = re.search(r"Descends vers (\d+) mm", _grand)
assert _conseil, ("l'alerte ne propose aucune taille", _grand[:200])
assert 10 < int(_conseil.group(1)) < 600, (
    "taille conseillée absurde", _conseil.group(1))
print("6. à 600 mm le verdict alerte et conseille {} mm OK".format(
    _conseil.group(1)))

# --- 7. Le verdict tient en LIGNES, pas en pavé ------------------------
# La règle de la maison : jamais une énumération dans un seul _WrapLabel.
# Ce verdict en aligne jusqu'à huit constats ; en un seul paragraphe, la
# hauteur de rangée et le repli se disputent -- « je vois déjà un
# chevauchement des cellules » (03/08/2026, capture à l'appui) -- et l'oeil
# ne trouve plus rien. Chaque constat a donc son étiquette.
_visibles = [lg for lg in _p._lignes_verdict if not lg.isHidden()]
assert len(_visibles) >= 4, (
    "le verdict tient en une ou deux étiquettes : il est resté un pavé",
    len(_visibles))
for _lg in _visibles:
    assert _lg.text().strip(), "une étiquette visible est vide"
    # Un constat, c'est une phrase -- pas huit collées.
    assert len(_lg.text()) < 400, ("un constat trop long : le pavé est "
                                   "revenu", _lg.text()[:120])
# Et un verdict COURT ne doit pas laisser traîner les lignes du précédent.
_p.edt_texte.setText("")
_p._maj_verdict()
_restes = [lg.text() for lg in _p._lignes_verdict if not lg.isHidden()]
assert len(_restes) == 1, ("les lignes de l'ancien verdict sont restées "
                           "affichées", _restes)
print("7. verdict en {} lignes, et un verdict court n'en laisse qu'une OK"
      .format(len(_visibles)))


# --- 8. Rien d'encre ne se perd, rien d'immobile ne se grave ------------
# Christophe, 04/08/2026, comparant le rendu de « La Graziela Script Demo »
# au mien : « il y a des coupures dans la tienne ». Deux causes.
#
# a) Le filtre d'élagage jetait sur la LONGUEUR ABSOLUE (0,8 mm) : sur cette
#    police, 89 chaînes sur 158, dont des liaisons entières. Une barbe
#    d'amincissement se reconnaît à ce qu'elle tient dans l'ÉPAISSEUR du
#    trait qui la porte, pas à ce qu'elle est courte.
# b) Un point d'i, un accent, une ponctuation sont des taches dont le
#    squelette fait un ou deux pixels : sous le minimum du traçage, ils ne
#    produisaient AUCUNE chaîne et disparaissaient sans un mot.
#
# Le contrôle porte donc sur l'ENCRE : chaque tache d'encre séparée doit
# recevoir au moins un geste.
from scipy import ndimage as _ndi                    # noqa: E402

def _taches_servies(encre, chaines, mm_px, hauteur_mm):
    im = Image.new("L", (encre.shape[1], encre.shape[0]), 0)
    d = ImageDraw.Draw(im)
    for c in chaines:
        for x, y, w in c:
            X, Y = x / mm_px, (hauteur_mm - y) / mm_px
            r = 0.5 * w / mm_px
            d.ellipse([X - r, Y - r, X + r, Y + r], fill=255)
    s = np.array(im) > 127
    lab, n = _ndi.label(encre)
    return len(set(np.unique(lab[s])) - {0}), n


# Un « i » et un « é » : deux taches détachées que rien ne relie au reste.
_TXT8 = "il a été"
_encre8 = cal.rendre_texte(_chemin, _TXT8)
_ch8, _inf8 = cal.chaines_calligraphie(_chemin, _TXT8, largeur_mm=120.0)
_servies, _total = _taches_servies(_encre8, _ch8, _inf8["mm_px"],
                                   _inf8["hauteur_mm"])
assert _total >= 3, ("le texte d'essai n'a pas de tache détachée : il ne "
                     "peut rien prouver", _total)
assert _servies == _total, (
    "des taches d'encre ne reçoivent aucun geste : un point d'i, un accent "
    "ou une ponctuation serait gravé manquant", _servies, _total)

# Et aucun geste immobile : à l'arrêt le HAL ramène la puissance à zéro,
# donc un G1 de longueur nulle ne marque rien et coûte deux mouvements.
for _c in _ch8:
    _lg = sum(math.hypot(_c[i+1][0]-_c[i][0], _c[i+1][1]-_c[i][1])
              for i in range(len(_c)-1))
    assert _lg > 1e-9, "un geste de longueur nulle : il ne gravera rien"
    assert _lg >= 0.5 * max(p[2] for p in _c) - 1e-9, (
        "un geste plus court que la moitié de sa largeur : son encre est "
        "déjà déposée par le trait qui le porte", _lg)
# LA MÊME CHOSE EN PLUS PETIT ne doit pas perdre d'encre. C'est la signature
# d'un seuil ABSOLU : réduire le texte réduit toutes les longueurs, donc un
# critère en millimètres finit par manger des traits entiers. Le critère
# proportionnel (une barbe tient dans l'épaisseur de son porteur) est
# insensible à l'échelle -- c'est tout l'intérêt.
for _lmm in (200.0, 120.0, 60.0, 35.0):
    _c2, _i2 = cal.chaines_calligraphie(_chemin, _TXT8, largeur_mm=_lmm)
    _s2, _t2 = _taches_servies(_encre8, _c2, _i2["mm_px"], _i2["hauteur_mm"])
    assert _s2 == _t2, (
        "à {:.0f} mm de large, {} taches d'encre sur {} ne sont plus gravées : "
        "le critère d'élagage dépend de la taille".format(_lmm, _t2 - _s2, _t2))
# LA GRAVURE NE DOIT PAS ÊTRE PLUS MORCELÉE QUE LA LETTRE. C'est la mesure
# de la « coupure » telle qu'on la voit : si le tracé se casse au milieu d'un
# geste, le résultat compte plus de morceaux que la police. Sur « La Graziela
# Script Demo », c'était 11 contre 7 -- l'axe médian s'arrête à une
# demi-largeur des pointes, et une liaison fine s'y perdait entièrement.
_couv8 = cal.couverture(_encre8, _ch8, _inf8["mm_px"],
                        (_encre8.shape[0] - 1) * _inf8["mm_px"], echelle=1)
_, _n_police = _ndi.label(_encre8)
_, _n_grave = _ndi.label(_couv8)
assert _n_grave <= _n_police + 1, (
    "la gravure est plus morcelée que la lettre : le tracé se coupe",
    _n_grave, _n_police)
print("8. « {} » : {} taches d'encre servies de 35 à 200 mm ; gravure en {} "
      "morceaux pour {} dans la police ; aucun geste immobile ni redondant OK"
      .format(_TXT8, _total, _n_grave, _n_police))


# --- 9. On place le texte parce qu'on le VOIT -------------------------
# Christophe, 04/08/2026 : « imagine, je crée une pièce sous FreeCAD, je veux
# positionner mon texte à un endroit précis ; si je ne le vois pas, je ne
# peux pas le placer ». Le mode écrivait le G-code directement, au prétexte
# qu'une largeur variable ne se range pas dans un fil. Vrai, et hors sujet :
# ce qu'on place est un TRAJET, et un trajet est un fil. La largeur suit à la
# gravure.
#
# Le contrôle porte sur la chaîne ENTIÈRE : poser l'objet, le déplacer comme
# le ferait la souris, et vérifier que le G-code atterrit là où l'objet est
# — pas là où il a été créé.
import FreeCAD                                        # noqa: E402

# `sans_dialogues()` AVANT tout clic : `_on_creer_objet` annonce le tracé
# posé par une boîte de message, et hors écran une boîte attend un clic qui
# ne viendra jamais -- le test gèle SANS AUCUNE SORTIE, ce qui ressemble à
# une boucle infinie dans le code testé. C'est écrit noir sur blanc dans les
# règles du dépôt, je suis tombé dedans, et la « correction » que j'ai crue
# faite n'avait rien remplacé : le script l'annonçait sans l'avoir vérifié.
# D'où l'assertion sur chaque ancre, désormais.
_dits = sans_dialogues()
_doc = FreeCAD.newDocument("EssaiCalligraphie")
try:
    _p9 = tp.TaskPanelCalligraphie()
    _p9.edt_police.setText(_chemin)
    _p9.edt_texte.setText(_TXT)
    for _i in range(_p9.combo_mat.count()):
        if _p9.combo_mat.itemData(_i) == _MAT:
            _p9.combo_mat.setCurrentIndex(_i)
    _p9.spn_largeur.setValue(80.0)
    _p9._on_creer_objet()
    _obj = _p9._objet
    assert _obj is not None, "aucun objet posé dans le document"
    assert _obj.Shape.Edges, "l'objet posé n'a aucune arête : rien à voir"
    _fiche = core.fiche_objet_calligraphie(_obj)
    assert _fiche.get("texte") == _TXT, (
        "l'objet ne dit pas de quel texte il vient", _fiche)

    # On le déplace ET on le tourne, comme à la souris.
    _obj.Placement = FreeCAD.Placement(
        FreeCAD.Vector(120.0, 45.0, 0.0),
        FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 15.0))
    _doc.recompute()

    _ecrit = {}
    _vrai_w = tp._write_gcode_with_dialog
    try:
        tp._write_gcode_with_dialog = (
            lambda w, g, d, **k: _ecrit.setdefault("g", g) or "/tmp/x.ngc")
        _p9._generer(cadre=False)
    finally:
        tp._write_gcode_with_dialog = _vrai_w
    assert _ecrit.get("g"), "aucun G-code produit"
    _xs = [float(m.group(1))
           for m in re.finditer(r"^G1 X(-?\d+\.\d+)", _ecrit["g"], re.M)]
    _ys = [float(m.group(1)) for m in
           re.finditer(r"^G1 X-?\d+\.\d+ Y(-?\d+\.\d+)", _ecrit["g"], re.M)]
    assert _xs and _ys, "le G-code ne contient aucun mouvement gravé"
    _bb = _obj.Shape.BoundBox
    assert abs(min(_xs) - _bb.XMin) < 2.0 and abs(min(_ys) - _bb.YMin) < 2.0, (
        "le G-code ne suit pas le placement de l'objet : le texte serait "
        "gravé ailleurs que là où on l'a posé",
        (min(_xs), min(_ys)), (_bb.XMin, _bb.YMin))
    assert min(_xs) > 100.0, (
        "le G-code est resté à l'origine : le placement est ignoré", min(_xs))
    print("9. tracé posé ({} arêtes), déplacé de (120, 45) et tourné de 15° : "
          "le G-code atterrit en ({:.0f}, {:.0f}) comme l'objet OK".format(
              len(_obj.Shape.Edges), min(_xs), min(_ys)))
finally:
    FreeCAD.closeDocument("EssaiCalligraphie")


# --- 10. Le graphe du squelette : couverture ET continuité -------------
# Quatre approches ont échoué avant celle-ci, TOUTES pour la même raison :
# on optimisait un parcours sur une structure qu'on n'avait pas comptée.
# Les deux invariants ci-dessous sont la porte d'entrée -- ils se vérifient
# AVANT tout usage, jamais après.
#
#   1. COUVERTURE : chaque pixel du squelette est dans exactement une arête.
#      L'approche « retirer les nœuds et laisser les composantes connexes
#      séparer les arêtes » échoue ici : un squelette est 8-connexe, donc
#      les deux pixels de part et d'autre d'un nœud restent voisins EN
#      DIAGONALE et rien n'est séparé.
#   2. CONTINUITÉ : deux points consécutifs se touchent. Un seul saut
#      devient un trait gravé en travers du dessin.
_formes = []
_img10 = Image.new("L", (500, 400), 0)
_d10 = ImageDraw.Draw(_img10)
_d10.ellipse([40, 40, 300, 300], outline=255, width=14)      # une boucle
_d10.line([170, 40, 170, 380], fill=255, width=12)           # qui la traverse
_d10.line([60, 210, 460, 210], fill=255, width=10)           # et une barre
_d10.arc([250, 150, 470, 370], 0, 300, fill=255, width=11)
_formes.append(("croisements", np.array(_img10) > 127))
_formes.append(("lettre réelle", cal.rendre_texte(_chemin, "Atelier")))

for _nom10, _forme in _formes:
    _sq10 = cal.amincir(_forme)
    _ar10, _cy10, _rap = cal.construire(_sq10)
    assert _rap["manquants"] == 0, (
        _nom10, "des pixels du squelette n'appartiennent à aucune arête",
        _rap["manquants"], _rap["squelette"])
    assert _rap["saut_max"] <= 1.5, (
        _nom10, "une arête saute : ce serait un trait gravé en travers",
        _rap["saut_max"])
    _g10 = cal.parcourir(_ar10, _cy10)
    _vus10 = {p for c in _g10 for p in c}
    _tous10 = {(int(y), int(x)) for y, x in zip(*np.nonzero(_sq10))}
    assert not (_tous10 - _vus10), (
        _nom10, "le parcours perd des pixels que le graphe avait",
        len(_tous10 - _vus10))
    for _c in _g10:
        for _p, _q in zip(_c, _c[1:]):
            assert math.hypot(_q[0]-_p[0], _q[1]-_p[1]) <= 1.5, (
                _nom10, "le parcours a introduit un saut")
    # Le parcours doit ENCHAÎNER : sinon il ne sert à rien d'avoir un graphe.
    assert len(_g10) < len(_ar10), (
        _nom10, "autant de gestes que d'arêtes : rien n'a été enchaîné",
        len(_g10), len(_ar10))
    print("10. {:14s} : {} arêtes -> {} gestes ; couverture entière, aucun "
          "saut OK".format(_nom10, len(_ar10), len(_g10)))


# --- 11. On grave le squelette, pas les miettes -------------------------
# Christophe, 04/08/2026, capture surlignée en jaune à l'appui : « ton rendu
# est fidèle et c'est vraiment vraiment mieux, ce qui me gêne c'est que ça
# essaye encore de suivre certains petits tracés, afin de rester fidèle, mais
# ces petits tracés ne vont pas [...] il faut juste le squelette de la lettre
# et bien sûr les points sur les i et accents ».
#
# Mesuré sur « Atelier du Verdier » à 120 mm : 27 des 55 gestes étaient des
# COMBLEMENTS d'encre non couverte, et 24 d'entre eux tombaient dans une
# lettre déjà tracée. Ils réparaient les « coupures » d'avant le parcours de
# graphe ; celui-ci les a supprimées à leur source, et il ne restait que le
# coût -- des traits épars le long des jonctions.
#
# Deux règles, chacune jugée sur l'ENCRE et non sur une longueur :
#   a) `taches_sans_geste` : on ne comble QUE ce qu'aucun geste ne touche.
#   b) `gestes_utiles` : un geste dont l'empreinte est déjà brûlée par un
#      autre ne dépose rien.

# Une barre franche et, loin d'elle, une tache détachée : le point d'un i.
_img11 = Image.new("L", (400, 200), 0)
_d11 = ImageDraw.Draw(_img11)
_d11.line([40, 150, 360, 150], fill=255, width=16)
_d11.ellipse([190, 30, 214, 54], fill=255)
_encre11 = np.array(_img11) > 127
_mm_px11 = 0.2
_haut11 = (_encre11.shape[0] - 1) * _mm_px11

def _en_mm(y_px, x_px, w_px):
    return (x_px * _mm_px11, _haut11 - y_px * _mm_px11, w_px * _mm_px11)

_barre = [_en_mm(150, x, 16) for x in range(45, 356, 5)]

# (a) La tache est vue comme non servie ; la barre, non.
_couv11 = cal.couverture(_encre11, [_barre], _mm_px11, _haut11)
_sans11 = cal.taches_sans_geste(_encre11, _couv11)
assert _sans11[42, 202], (
    "la tache détachée n'est pas reconnue : un point d'i serait gravé "
    "manquant")
assert not _sans11[150, 200], (
    "la barre est déclarée sans geste alors qu'un geste la parcourt : on "
    "recomblerait l'intérieur des lettres, ce que Christophe a surligné")
assert int(_sans11.sum()) < int(_encre11.sum()) * 0.2, (
    "presque toute l'encre est déclarée sans geste", int(_sans11.sum()))

# (b) Un doublon de la barre, décalé d'un pixel, ne dépose rien de neuf.
_doublon = [(x, y - _mm_px11, w) for x, y, w in _barre]
_point = [_en_mm(42, 196, 24), _en_mm(42, 208, 24)]
_gardes11 = cal.gestes_utiles(_encre11, [_barre, _doublon, _point],
                              _mm_px11, _haut11)
assert len(_gardes11) == 2, (
    "le doublon n'a pas été jeté (ou un vrai geste l'a été)", len(_gardes11))
assert _point in _gardes11, (
    "le geste de la tache détachée a été jeté : il dépose pourtant toute "
    "son encre")
assert _barre in _gardes11 or _doublon in _gardes11, (
    "la barre entière a été jetée")

# (c) Sur une vraie lettre, l'élagage doit AVOIR LIEU et ne rien coûter.
_TXT11 = "il a été"
_encre_r = cal.rendre_texte(_chemin, _TXT11)
_sq_r = cal.amincir(_encre_r)
_ar_r, _cy_r, _ = cal.construire(_sq_r)
_haut_r = (_encre_r.shape[0] - 1) * (120.0 / _encre_r.shape[1])
_ch11, _inf11 = cal.chaines_calligraphie(_chemin, _TXT11, largeur_mm=120.0)
# Plus aucun geste ne doit être redondant : c'est la propriété, pas le compte.
_mm_r = _inf11["mm_px"]
_vide_r = cal.couverture(_encre_r, [], _mm_r, _haut_r)
_petit_r = np.array(Image.fromarray((_encre_r > 0).astype(np.uint8) * 255)
                    .resize((_vide_r.shape[1], _vide_r.shape[0]))) > 127
for _i11, _c11 in enumerate(_ch11):
    _autres = cal.couverture(_encre_r, _ch11[:_i11] + _ch11[_i11+1:],
                             _mm_r, _haut_r)
    _propre = cal.couverture(_encre_r, [_c11], _mm_r, _haut_r) & _petit_r
    _neuf = float((_propre & ~_autres).sum()) / max(1, int(_propre.sum()))
    assert _neuf > 0.0, (
        "un geste ne dépose aucune encre que les autres ne déposent déjà : "
        "il coûte un relevage, un transit et deux terminaisons franches",
        _i11, _neuf)

# (d) Les chiffres annoncés décrivent CE QUI SERA GRAVÉ. Les cumuler avant
#     l'élagage laissait un moignon jeté fixer à lui seul la largeur mini,
#     celle sur laquelle le panneau juge si le matériau sait faire le trait.
_somme11 = sum(math.hypot(_q[0]-_p[0], _q[1]-_p[1])
               for _c in _ch11 for _p, _q in zip(_c, _c[1:]))
assert abs(_inf11["longueur_mm"] - _somme11) < 1e-6, (
    "la longueur annoncée compte des gestes qui ne seront pas gravés",
    _inf11["longueur_mm"], _somme11)
assert abs(_inf11["largeur_trait_min"]
           - min(w for _c in _ch11 for _x, _y, w in _c)) < 1e-9, (
    "la largeur mini annoncée vient d'un geste jeté")
assert _inf11["n_chaines"] == len(_ch11)
print("11. « {} » : {} arêtes -> {} gestes, aucun redondant ; tache détachée "
      "servie, intérieur des lettres non recomblé ; chiffres du verdict "
      "conformes au tracé OK".format(_TXT11, len(_ar_r), len(_ch11)))
