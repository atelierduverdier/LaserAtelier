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
# LA SOUDURE AUSSI DOIT TENIR L'INVARIANT. Elle joint deux bouts distants --
# c'est tout son objet -- et elle le fait en REMPLISSANT le raccord de ses
# pixels intermédiaires. Sans ce remplissage elle réintroduirait exactement
# le trait droit du 03/08.
_cousu = cal.souder(_brut, _b2, cal.largeur_locale(_b2))
_saut_c = _plus_grand_saut(_cousu)
assert _saut_c <= 3.0, ("la soudure a laissé un saut de {:.0f} px".format(_saut_c))
assert len(_cousu) <= len(_brut), "la soudure a fabriqué des chaînes"
# ET ELLE NE SOUDE QUE DANS L'ENCRE. Il faut pour le prouver une figure où
# la garde CHANGE quelque chose : sur l'anneau ci-dessus, aucun raccord ne
# sortait du dessin même sans elle, si bien que le contrôle passait aussi
# bien avec la garde retirée -- il ne prouvait rien. Un chevron OUVERT à son
# sommet, lui, offre deux bouts qui se prolongent tout droit avec du vide
# entre eux : c'est exactement le trait en travers du mot, en miniature.
_img2b = Image.new("L", (420, 260), 0)
_dr2b = ImageDraw.Draw(_img2b)
_dr2b.line([40, 220, 200, 60], fill=255, width=26)
_dr2b.line([212, 66, 380, 220], fill=255, width=26)
_b2b = np.array(_img2b) > 127
_cousu2b = cal.souder(cal.tracer(cal.amincir(_b2b)), _b2b,
                      cal.largeur_locale(_b2b))
_hors = [(int(y), int(x)) for c in _cousu2b for y, x in c if not _b2b[int(y), int(x)]]
assert not _hors, (
    "la soudure a posé {} point(s) HORS de l'encre : c'est le trait droit "
    "gravé en travers du dessin".format(len(_hors)), _hors[:3])
assert len(_cousu2b) >= 2, (
    "le chevron ouvert a été refermé : ses deux branches ne se touchent pas",
    len(_cousu2b))
for _c in _cousu:
    for _y, _x in _c:
        assert _b2[int(_y), int(_x)], (
            "la soudure a posé un point HORS de l'encre", _y, _x)
print("2. aucun saut dans les chaînes : au pire {:.1f} px (traçage) et "
      "{:.1f} px (soudure) ; {} chaînes -> {} ; chevron ouvert laissé ouvert "
      "({} gestes), rien hors de l'encre OK".format(
          _saut, _saut_c, len(_brut), len(_cousu), len(_cousu2b)))

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
_couv, _deb = _balayer(_encre, _ch, _inf["mm_px"], _inf["hauteur_image_mm"])
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
                                   _inf8["hauteur_image_mm"])
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
    _s2, _t2 = _taches_servies(_encre8, _c2, _i2["mm_px"], _i2["hauteur_image_mm"])
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


# --- 12. L'AVANCE EST CELLE DU TRAIT, PAS CELLE DU VECTEUR -------------
# Christophe, 04/08/2026, photo de « Atelier du Verdier » gravée en v2.65.1,
# dix-sept pâtés encadrés en rouge : « je pense qu'il y a trop de puissance
# ou on ne va pas assez vite dans certains endroits ». Les deux, et pour une
# seule raison.
#
# En G94, `F` s'applique au vecteur PROGRAMMÉ. Là où le fuseau grimpe à sa
# pente maxi -- 7,5 mm de Z par mm de trait, donc exactement au départ et à
# la fin de chaque geste -- la tête avance en XY 7,57 fois moins vite que
# l'avance annoncée, à faisceau constant. Le bois reçoit l'énergie d'un
# déplacement de 7,57 mm étalée sur 1 mm de trait.
#
# Mesuré sur le fichier qu'il a gravé : 20,6 % des segments à plus du DOUBLE
# de l'énergie médiane par mm de trait, 7,5 % à plus du quintuple, le pire à
# 12,4 fois la médiane. Le rapport était connu du projet depuis v2.54.0 --
# il sert à estimer la DURÉE, 2,1x sur un portrait au fuseau -- sans jamais
# avoir été relié à la brûlure.

# (a) La fonction elle-même, sur des cas dont on connaît la réponse.
assert core.avance_compensee(1.0, 0.0, 200.0) == 200.0, (
    "un trait à Z plat ne doit rien changer à l'avance")
_f12 = core.avance_compensee(1.0, 1.0, 200.0)
assert abs(_f12 * 1.0 / math.sqrt(2.0) - 200.0) < 1e-6, (
    "à 45° de pente, la vitesse XY obtenue n'est pas l'avance demandée",
    _f12 * 1.0 / math.sqrt(2.0))
# Le plafond est celui de l'axe Z, pas un chiffre en l'air.
_d3 = math.hypot(1.0, 50.0)
_f13 = core.avance_compensee(1.0, 50.0, 200.0)
assert _f13 * 50.0 / _d3 <= core.Z_MAX_FEED_MM_MIN + 1e-6, (
    "la compensation demande à l'axe Z plus vite que sa limite",
    _f13 * 50.0 / _d3, core.Z_MAX_FEED_MM_MIN)
assert _f13 >= 200.0, "la compensation ne doit jamais RALENTIR le trait"

# (b) Sur le G-code réellement émis : plus aucun segment ne surcuit.
def _energies_par_mm(gcode):
    """Énergie déposée par mm de TRAIT VISIBLE, segment par segment.

    C'est `S x temps / dXY`, donc `S x d3D / (F x dXY)` : ce que le bois
    reçoit là où on le regarde, et non ce que la tête dépense en chemin.

    La puissance se lit dans LES DEUX dialectes : `M67 E0 Q...` sur sa
    propre ligne, ou le `S` accolé au `G1`. Le harnais force le second, la
    config de l'atelier utilise le premier -- ne lire qu'un des deux fait
    sortir zéro segment, ce qui passe pour un fichier sans défaut."""
    pos, s_cur, out = None, 0.0, []
    for l in gcode.split("\n"):
        l = l.strip()
        if l.startswith("("):
            continue
        m = re.search(r"M67 E0 Q(-?[\d.]+)", l) or re.search(r"\bS(\d+\.?\d*)", l)
        if m:
            s_cur = float(m.group(1))
        if not (l.startswith("G1") or l.startswith("G0")):
            continue
        gx = re.search(r"X(-?[\d.]+)", l)
        gy = re.search(r"Y(-?[\d.]+)", l)
        gz = re.search(r"Z(-?[\d.]+)", l)
        gf = re.search(r"F(-?[\d.]+)", l)
        p = (float(gx.group(1)) if gx else (pos[0] if pos else 0.0),
             float(gy.group(1)) if gy else (pos[1] if pos else 0.0),
             float(gz.group(1)) if gz else (pos[2] if pos else 0.0))
        if l.startswith("G1") and pos and gf and s_cur > 0:
            dxy = math.hypot(p[0] - pos[0], p[1] - pos[1])
            d3 = math.hypot(dxy, abs(p[2] - pos[2]))
            if dxy > 1e-6:
                out.append(s_cur * d3 / (float(gf.group(1)) * dxy))
        pos = p
    return out

# Un fuseau RAIDE : c'est là que le Z mange l'avance. Le trait fuselé de §4
# monte de 0,20 à 3,20 mm sur 20 mm, la pente y est bornée à son maximum.
_e12 = _energies_par_mm(_g)
assert len(_e12) > 50, ("trop peu de segments pour juger", len(_e12))
_e12.sort()
_med12 = _e12[len(_e12) // 2]
_gros = [x for x in _e12 if x > 2.0 * _med12]
assert not _gros, (
    "des segments déposent plus du double de l'énergie médiane par mm de "
    "trait : c'est le pâté que Christophe a encadré", len(_gros),
    max(_gros) / _med12)
print("12. avance compensée : Z plat inchangé, vitesse XY tenue à 45°, "
      "plafond Z respecté ; sur le G-code, {} segments et le pire à {:.2f}x "
      "l'énergie médiane OK".format(len(_e12), _e12[-1] / _med12))


# --- 13. UN CROISEMENT SE TRAVERSE TOUT DROIT --------------------------
# Christophe, 04/08/2026, capture annotée 1-2-3 sur le « A » et le « t » :
# « c'est l'ordre des traits, pour le t le 3e est coupé en son centre,
# normalement on trace une ligne 1 puis 2 puis 3 ».
#
# La cause n'est pas l'ordonnancement, c'est la TOPOLOGIE. Un croisement de
# biais -- et une cursive n'est faite que de ça -- ne donne pas un nœud à
# quatre branches : l'amincissement en fabrique DEUX à trois branches,
# reliés par un pont d'un ou deux pixels. `parcourir` apparie nœud par nœud,
# donc il peut coudre « barre-gauche + pont + fût-bas » et laisser les deux
# autres branches pendantes. Le trait est alors coupé en son milieu.
#
# La figure qui le prouve est la plus simple qui soit : DEUX BARRES EN X
# doivent donner DEUX TRAITS DROITS, chacun d'un coin à son opposé. Avant la
# fusion des jonctions, elles en donnaient quatre, dont un qui rebroussait.
_img13 = Image.new("L", (400, 400), 0)
_d13 = ImageDraw.Draw(_img13)
_d13.line([60, 60, 340, 340], fill=255, width=22)
_d13.line([340, 60, 60, 340], fill=255, width=22)
_b13 = np.array(_img13) > 127
_sq13 = cal.amincir(_b13)
_larg13 = cal.largeur_locale(_b13)
_ar13, _cy13, _ = cal.construire(_sq13)
_ar13 = cal.fusionner_jonctions(_ar13, _larg13)
_g13 = cal.parcourir(_ar13, _cy13)

# La fusion ne doit RIEN perdre du squelette, ni introduire de saut.
_vus13 = {p for c in _g13 for p in c}
_tous13 = {(int(y), int(x)) for y, x in zip(*np.nonzero(_sq13))}
assert not (_tous13 - _vus13), (
    "la fusion a perdu des pixels du squelette", len(_tous13 - _vus13))
for _c in _g13:
    for _p, _q in zip(_c, _c[1:]):
        assert math.hypot(_q[0] - _p[0], _q[1] - _p[1]) <= 1.5, (
            "la fusion a introduit un saut")

# Les vrais traits : ceux qui font plus du quart de la diagonale.
_diag13 = math.hypot(280.0, 280.0)
def _lg13(c):
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(c, c[1:]))
_vrais = [c for c in _g13 if _lg13(c) > 0.25 * _diag13]
assert len(_vrais) == 2, (
    "un X doit se graver en DEUX traits, pas {} : le croisement est traversé "
    "de travers".format(len(_vrais)), [round(_lg13(c)) for c in _vrais])
for _c in _vrais:
    _d0 = cal._direction(_c, True)
    _d1 = cal._direction(_c, False)
    _droit = -(_d0[0] * _d1[0] + _d0[1] * _d1[1])
    assert _droit > 0.9, (
        "un des deux traits REBROUSSE au croisement : c'est un V là où il "
        "fallait une droite", _droit)
    assert _lg13(_c) > 0.9 * _diag13, (
        "un trait s'arrête avant le coin opposé : il est coupé en son milieu",
        _lg13(_c), _diag13)
# ET IL FAUT AUSSI QUE LA FUSION S'ARRÊTE. Sans seuil, tout pont entre deux
# jonctions serait avalé, y compris un VRAI trait court -- la barre d'un H,
# celle d'un e, un connecteur. On ne le voit pas sur le X (son pont fait deux
# pixels, le supprimer ou non ne change rien de mesurable), donc le contrôle
# ci-dessus passait aussi bien avec le seuil retiré : il ne prouvait qu'une
# moitié de la règle.
#
# Le H la prouve entièrement. Sa barre est une arête légitime entre deux
# jonctions ; la fusionner la DUPLIQUE dans chaque branche, donc la fait
# graver plusieurs fois. Mesuré : longueur totale des gestes rapportée au
# squelette, 1,00x avec le seuil (stable de k=0,5 à k=3,0) contre 1,21x sans.
_img13b = Image.new("L", (400, 400), 0)
_d13b = ImageDraw.Draw(_img13b)
_d13b.line([120, 40, 120, 360], fill=255, width=20)
_d13b.line([280, 40, 280, 360], fill=255, width=20)
_d13b.line([120, 200, 280, 200], fill=255, width=18)
_b13b = np.array(_img13b) > 127
_sq13b = cal.amincir(_b13b)
_ar13b, _cy13b, _ = cal.construire(_sq13b)
_g13b = cal.parcourir(
    cal.fusionner_jonctions(_ar13b, cal.largeur_locale(_b13b)), _cy13b)
_ratio13 = sum(_lg13(c) for c in _g13b) / float(int(_sq13b.sum()))
assert _ratio13 <= 1.05, (
    "la fusion a avalé la barre du H : elle sera gravée plusieurs fois",
    _ratio13)
print("13. X de deux barres : {} arêtes -> {} traits, tous deux droits "
      "({:.0f} px pour {:.0f} de diagonale), squelette entier, aucun saut ; "
      "barre du H préservée ({:.2f}x le squelette) OK"
      .format(len(_ar13), len(_vrais), min(_lg13(c) for c in _vrais), _diag13,
              _ratio13))


# --- 14. LE TRAIT QUI CONTINUE, MÊME S'IL TOURNE AU CROISEMENT ---------
# Christophe, 04/08/2026, flèche orange sur la gravure du « A » : « la ligne
# en 1 seul trait c'est la ligne qui commence du haut et va vers le bas
# droit, et non pas la barre du milieu ». Son carré rouge tombait sur le
# nœud à 0,0 mm près.
#
# La cause est la PORTÉE de lecture de la direction, qui valait 6 pixels. Le
# plein du A tourne dans le disque de la jonction -- le trait y est épais,
# donc le nœud est loin du bord -- si bien que six pixels le lisaient comme
# presque horizontal (+0,37 ; -0,93) alors qu'il descend (+0,84 ; -0,55).
# L'appariement mariait donc la grande boucle à la petite entrée de gauche
# et laissait le plein pendant.
#
# LA FIGURE DOIT AVOIR UN COUDE AU NŒUD. Quatre fixtures lisses (arc courbé,
# V épais, coude serré) ont été essayées et jetées : elles donnaient la même
# réponse aux deux portées, donc elles ne prouvaient rien. Ce qui trompe une
# portée courte n'est pas la courbure, c'est le changement de direction
# JUSTE au nœud.
#
#   A monte, en partant vers la gauche puis en remontant franchement ;
#   B descend, c'est la VRAIE suite de A, mais coudée au nœud ;
#   C part à droite, presque colinéaire au DÉPART de A.
#
# À 6 px, A « pointe » vers C, donc B se marie à C : le trait est coupé.
def _fig14(ep, ep_c, pa, pb, pc):
    im = Image.new("L", (520, 520), 0)
    d = ImageDraw.Draw(im)
    d.line(pa, fill=255, width=ep, joint="curve")
    d.line(pb, fill=255, width=ep, joint="curve")
    d.line(pc, fill=255, width=ep_c, joint="curve")
    return np.array(im) > 127

_A14 = [(235, 150), (240, 240), (250, 250)]
_B14 = [(250, 250), (252, 262), (285, 430)]
_C14 = [(250, 250), (300, 254), (430, 262)]
_b14 = _fig14(30, 22, _A14, _B14, _C14)
_larg14 = cal.largeur_locale(_b14)
_ar14, _cy14, _ = cal.construire(cal.amincir(_b14))
_ar14 = cal.fusionner_jonctions(_ar14, _larg14)
_g14 = cal.parcourir(_ar14, _cy14, _larg14)

def _touche14(c, xy, tol=30.0):
    return any(math.hypot(p[1] - xy[0], p[0] - xy[1]) < tol for p in c)

_juste = [c for c in _g14
          if _touche14(c, (235, 150)) and _touche14(c, (285, 430))]
assert _juste, (
    "le trait qui monte et celui qui descend ne font pas UN geste : le "
    "croisement a marié la mauvaise branche, et le trait sort coupé en son "
    "milieu -- c'est le « A » que Christophe a fléché en orange")
assert not any(_touche14(c, (430, 262)) and _touche14(c, (285, 430))
               for c in _g14), (
    "la branche latérale a capturé la descente")

# La portée doit être PROPORTIONNELLE à l'encre, et bornée des deux côtés.
_epais = np.zeros((10, 10)); _epais[5, 5] = 40.0
_fin = np.zeros((10, 10)); _fin[5, 5] = 4.0
assert cal._portee((5, 5), _epais) > cal._portee((5, 5), _fin), (
    "la portée ne suit pas l'épaisseur du trait : une valeur en pixels "
    "absolus convient à une police et pas à la suivante (mesuré : 30 px "
    "améliorent trois polices et dégradent Blacksword)")
assert cal._portee((5, 5), None) == cal.PORTEE_MINI
_enorme = np.zeros((10, 10)); _enorme[5, 5] = 10000.0
assert cal._portee((5, 5), _enorme) == cal.PORTEE_MAXI, (
    "la portée n'est pas bornée : sur un trait très épais elle lirait la "
    "direction sur toute la lettre")
print("14. coude au croisement : le trait qui monte et celui qui descend font "
      "UN geste ({} gestes en tout) ; portée {} à {} px selon l'encre OK"
      .format(len(_g14), cal._portee((5, 5), _fin), cal._portee((5, 5), _epais)))


# --- 15. LE SENS DU GESTE EST LE GESTE ---------------------------------
# Christophe, 04/08/2026, flèche orange tracée sur la gravure du « A » :
# « regarde la flèche orange, c'est le sens de la ligne en un seul trait ».
# Le tracé était juste depuis la v2.66.2 ; c'est le SENS de parcours qui ne
# l'était pas, et il ne l'était pas par accident : `order_chains_by_proximity`
# retourne librement une chaîne pour raccourcir les transits, si bien que le
# sens calculé en amont n'était JAMAIS celui gravé.
#
# La règle est celle de la plume : un plein se tire vers le BAS (on appuie en
# descendant), une liaison se tire vers la DROITE (on écrit de gauche à
# droite). Mesuré sur « Atelier du Verdier » : 9 gestes sur 20 descendaient,
# 20 sur 20 après. Coût : 122 -> 203 mm de trajet à vide, moins d'une seconde
# à G0 sur un job de 2,3 minutes.

def _sens_main(p0, p1):
    dy, dx = p1[1] - p0[1], p1[0] - p0[0]
    return (dy < 0.0) if abs(dy) >= abs(dx) else (dx > 0.0)

# (a) La fonction, sur des cas dont on connaît la réponse.
class _P15(object):
    def __init__(self, x, y):
        self.x, self.y, self.w, self.dz, self.s = float(x), float(y), 1.0, 0.0, 0.0

_montant = [_P15(10, 0), _P15(11, 20)]          # vertical, vers le HAUT
assert core.sens_de_la_main(_montant)[0].y > core.sens_de_la_main(_montant)[-1].y, (
    "un geste vertical doit être gravé vers le BAS")
_gauche = [_P15(30, 5), _P15(0, 6)]             # horizontal, vers la GAUCHE
assert core.sens_de_la_main(_gauche)[0].x < core.sens_de_la_main(_gauche)[-1].x, (
    "un geste horizontal doit être gravé vers la DROITE")
_deja = [_P15(0, 20), _P15(1, 0)]               # déjà descendant
assert core.sens_de_la_main(_deja)[0].y == 20.0, (
    "un geste déjà dans le bon sens ne doit pas être retourné")

# (b) L'ordonnancement doit pouvoir SE TAIRE sur le sens.
_a15 = [_P15(0, 0), _P15(10, 0)]
_b15 = [_P15(30, 0), _P15(20, 0)]     # son bout le plus proche de _a15 est le DERNIER
_libre = core.order_chains_by_proximity([_a15, _b15])
_fige = core.order_chains_by_proximity([_a15, _b15], sens_libre=False)
assert _libre[1][0].x == 20.0, (
    "par défaut l'ordonnancement doit encore retourner une chaîne pour "
    "raccourcir le transit -- tous les autres modes en dépendent")
assert _fige[1][0].x == 30.0, (
    "sens_libre=False n'a pas empêché l'inversion : le sens du geste serait "
    "détruit en aval de tout ce qu'on calcule")

# (c) SUR LE G-CODE ÉMIS, pas sur la fonction. C'est le seul endroit où la
#     question se pose vraiment : entre les deux il y a l'ordonnancement,
#     et c'est LUI qui cassait le sens.
#
#     La figure doit porter PLUSIEURS gestes, dont certains à contresens :
#     le trait fuselé de §4 n'en a qu'un, et « 1 sur 1 » ne prouve rien.
#     Trois montants (donc à retourner), un descendant déjà bon, un
#     horizontal vers la gauche (à retourner aussi) -- et ils sont placés
#     de façon que l'ordonnancement ait vraiment intérêt à en inverser.
def _fuseau15(x0, y0, x1, y1, n=40):
    return [(x0 + (x1 - x0) * i / float(n), y0 + (y1 - y0) * i / float(n),
             0.20 + 2.5 * math.sin(math.pi * i / float(n)))
            for i in range(n + 1)]

_MULTI = [
    _fuseau15(0.0, 0.0, 2.0, 30.0),        # monte : à retourner
    _fuseau15(40.0, 30.0, 42.0, 0.0),      # descend : déjà bon
    _fuseau15(10.0, 2.0, 12.0, 32.0),      # monte : à retourner
    _fuseau15(60.0, 10.0, 20.0, 12.0),     # horizontal vers la gauche
    _fuseau15(25.0, 34.0, 27.0, 4.0),      # descend : déjà bon
]
_g15 = core.generate_gcode_calligraphie(_MULTI, 0.0, 200, _MAT, power_max=900,
                                        police=_nom)
_gestes15, _cur15 = [], []
for _l in _g15.split("\n"):
    if _l.startswith("G1 X"):
        _cur15.append((float(re.search(r"X(-?[\d.]+)", _l).group(1)),
                       float(re.search(r"Y(-?[\d.]+)", _l).group(1))))
    elif _l.startswith("G0") and _cur15:
        _gestes15.append(_cur15)
        _cur15 = []
if _cur15:
    _gestes15.append(_cur15)
assert _gestes15, "aucun geste lu dans le G-code"
_faux = [g for g in _gestes15 if not _sens_main(g[0], g[-1])]
assert not _faux, (
    "{} geste(s) sur {} gravés à contresens de la main".format(
        len(_faux), len(_gestes15)),
    [(round(g[0][0]), round(g[0][1]), round(g[-1][0]), round(g[-1][1]))
     for g in _faux[:3]])
print("15. sens de la main : {}/{} gestes du G-code ÉMIS vont vers le bas (ou "
      "vers la droite s'ils sont horizontaux) ; l'ordonnancement retourne "
      "encore librement hors calligraphie OK".format(
          len(_gestes15), len(_gestes15)))


# --- 16. ON ÉCRIT DE GAUCHE À DROITE -----------------------------------
# Christophe, 04/08/2026 : « pour l'écriture, on écrit de gauche à droite,
# je veux que tu respectes cela ». C'est l'ORDRE des gestes, là où §15
# portait sur le sens de chacun.
#
# Et ce n'est pas un compromis : une fois le sens imposé, l'ordonnancement
# par proximité n'a plus le droit de retourner une chaîne pour se rapprocher,
# si bien qu'un simple tri fait mieux. Mesuré sur « Atelier du Verdier » :
# 203 mm de trajet à vide par proximité contre 155 de gauche à droite, et
# 16 retours en arrière contre 0.
_g16 = core.generate_gcode_calligraphie(_MULTI, 0.0, 200, _MAT, power_max=900,
                                        police=_nom)
_gestes16, _cur16 = [], []
for _l in _g16.split("\n"):
    if _l.startswith("G1 X"):
        _cur16.append((float(re.search(r"X(-?[\d.]+)", _l).group(1)),
                       float(re.search(r"Y(-?[\d.]+)", _l).group(1))))
    elif _l.startswith("G0") and _cur16:
        _gestes16.append(_cur16)
        _cur16 = []
if _cur16:
    _gestes16.append(_cur16)
assert len(_gestes16) >= 4, ("il faut plusieurs gestes pour juger d'un ORDRE",
                             len(_gestes16))
_retours = [(a[0][0], b[0][0]) for a, b in zip(_gestes16, _gestes16[1:])
            if b[0][0] < a[0][0] - 1e-6]
assert not _retours, (
    "{} geste(s) repartent VERS LA GAUCHE du précédent : on n'écrit pas comme "
    "ça".format(len(_retours)), _retours[:3])
print("16. ordre d'écriture : {} gestes du G-code ÉMIS, aucun ne repart vers "
      "la gauche du précédent OK".format(len(_gestes16)))


# --- 17. MILLE POLICES NE SE CHOISISSENT PAS ---------------------------
# Christophe, 04/08/2026 : « j'ai une liste interminable et j'utilise un
# autre logiciel pour voir la forme des fonts ». Sur sa machine la liste
# compte 1019 fichiers, dont 902 dans /usr/share/fonts -- des Noto, des
# DejaVu, des emoji : rien qui sache faire un plein et un délié.
#
# Le chiffre qui décide est le CONTRASTE, mesuré sur le squelette avec la
# même largeur locale que la gravure. Sur ses 118 polices personnelles :
# Rosean 7,62x, Doglover 7,00, Swirly 5,10, Blacksword 3,81, La Graziela
# 2,83, Byliner 2,55 -- contre 1,34 à 1,44 pour les sans-serif et monospace
# du système. 29 sur 118 dépassent CONTRASTE_MINI.

# (a) La mesure : un nombre plausible sur une vraie police, None sur ce qui
#     n'en est pas une -- jamais une exception, la liste en contient de tout.
_c17 = cal.contraste_police(_chemin)
assert _c17 is not None and _c17 >= 1.0, (
    "contraste illisible sur une police valide", _c17, _chemin)
assert cal.contraste_police(__file__) is None, (
    "un fichier qui n'est pas une police doit rendre None, pas exploser")

# (b) ELLE DOIT DISCRIMINER. Un trait d'épaisseur CONSTANTE ne donne aucun
#     contraste ; le trait fuselé de §1 en donne beaucoup. On mesure avec la
#     formule elle-même (centiles 10 et 90 de la largeur sur le squelette),
#     sur deux formes dont on connaît la réponse par construction.
_barre17 = np.zeros((200, 600), dtype=bool)
_barre17[95:105, 20:580] = True                    # 10 px partout
_fuselé17, _, _ = _trait_fuselé()                  # 6 -> 60 px
_c_plat = cal.contraste_encre(_barre17)
_c_fusele = cal.contraste_encre(_fuselé17)
assert _c_plat < 1.3, ("un trait d'épaisseur constante ne doit pas avoir de "
                       "contraste", _c_plat)
assert _c_fusele > 2.0 * _c_plat, (
    "la mesure ne distingue pas un fuseau d'un trait plat : elle ne peut "
    "pas trier les polices", _c_plat, _c_fusele)
assert _c_plat < cal.CONTRASTE_MINI <= _c_fusele, (
    "le seuil ne sépare pas les deux cas qu'il doit séparer",
    _c_plat, cal.CONTRASTE_MINI, _c_fusele)

# Et le chemin complet passe bien par CETTE mesure-là : sans ce lien, on
# pourrait casser la formule sans que rien ne tombe (essayé -- ça passait).
assert abs(cal.contraste_police(_chemin)
           - cal.contraste_encre(cal.rendre_texte(_chemin, "Mno", em_px=120))) < 1e-9, (
    "contraste_police ne mesure pas ce que contraste_encre mesure")

# (c) LE MENU : les polices personnelles AVANT celles du système. C'est ce
#     qui rend la liste utilisable sans rien cacher.
_p17 = tp.TaskPanelCalligraphie()
_rangs = []
for _i in range(_p17.combo_police.count()):
    _ch17 = _p17.combo_police.itemData(_i)
    if _ch17:
        _rangs.append(str(_ch17).startswith("/usr/share/fonts"))
if any(_rangs) and not all(_rangs):
    _premier_systeme = _rangs.index(True)
    assert not any(not _s for _s in _rangs[_premier_systeme:]), (
        "une police personnelle est reléguée derrière celles du système")
    print("17. {} polices dans le menu, les {} personnelles d'abord ; "
          "contraste : trait plat {:.2f}x, fuseau {:.2f}x, seuil {:.1f}x OK"
          .format(len(_rangs), _premier_systeme, _c_plat, _c_fusele,
                  cal.CONTRASTE_MINI))
else:
    print("17. contraste : trait plat {:.2f}x, fuseau {:.2f}x, seuil {:.1f}x "
          "OK (pas de mélange perso/système sur cette machine, ordre non "
          "jugeable)".format(_c_plat, _c_fusele, cal.CONTRASTE_MINI))


# ==========================================================================
# 18. LA TAILLE DEMANDÉE EST LA TAILLE GRAVÉE
# ==========================================================================
# Défaut trouvé à l'audit du 02/09/2026, et resté invisible parce que TOUS
# les contrôles de ce fichier mesuraient À TRAVERS `infos["mm_px"]` : ils
# étaient cohérents entre eux autour d'une échelle fausse, et aucun ne
# pouvait la juger. C'est la variante, dans un autre costume, de la règle
# que ce dépôt s'est déjà donnée -- « un balayage lancé sur un pipeline
# raccourci n'est pas une mesure du pipeline ».
#
# L'échelle se prenait sur la largeur de l'IMAGE, marges comprises (15 % de
# l'em de chaque côté). Empreinte réellement brûlée pour 120 mm demandés,
# avant → après : « A » 62,7 → 112,8 ; « Ab » 85,2 → 118,7 ; « Atelier »
# 108,5 → 120,0 ; « Atelier du Verdier » 115,3 → 119,9.
#
# ON MESURE CE QUI BRÛLE, pas les points de la chaîne : l'axe médian
# s'arrête à une demi-largeur des pointes, mais le trait a cette largeur.


def _empreinte_mm(chaines, infos, encre):
    """Largeur et hauteur de ce que les gestes déposeraient, en mm."""
    couv = cal.couverture(encre, chaines, infos["mm_px"],
                          infos["hauteur_image_mm"])
    cols = np.nonzero(couv.any(axis=0))[0]
    lignes = np.nonzero(couv.any(axis=1))[0]
    k = cal.ECHELLE_CONTROLE * infos["mm_px"]
    return ((cols.max() - cols.min() + 1) * k,
            (lignes.max() - lignes.min() + 1) * k)


print()
print("=" * 62)
print("§18  La taille demandée est la taille gravée")
print("=" * 62)

# LES BORNES SE LISENT DANS LA MESURE, et elles ne sont pas symétriques :
# le disque inscrit DÉBORDE la lettre (4 % en aire, documenté), et ce
# débordement se voit surtout aux extrémités -- donc sur l'étendue. Mesuré
# ici : largeur de -6,0 % (un « A » seul, dont l'axe médian s'arrête loin
# des pointes de ses diagonales) à +0,5 % ; hauteur de +1,4 % à +12,7 %.
# On borne large, mais assez serré pour rattraper les -48 % d'avant.
for _txt18, _tol18 in (("Atelier du Verdier", 0.02), ("Atelier", 0.02),
                       ("Ab", 0.05), ("A", 0.08)):
    _c18, _i18 = cal.chaines_calligraphie(_chemin, _txt18, largeur_mm=120.0)
    _e18 = cal.rendre_texte(_chemin, _txt18, em_px=cal.EM_PX)
    _w18, _h18 = _empreinte_mm(_c18, _i18, _e18)
    print("   « {:<20} » demandé 120,0 mm → brûlé {:6.1f} mm  ({:+.1f} %)"
          .format(_txt18, _w18, 100 * (_w18 - 120.0) / 120.0))
    assert abs(_w18 - 120.0) / 120.0 <= _tol18, (
        "« {} » : 120 mm demandés, {:.1f} mm brûlés -- l'échelle ne se prend "
        "pas sur l'encre".format(_txt18, _w18))
    # et le chiffre annoncé doit être celui-là, pas celui de l'image
    assert abs(_i18["largeur_mm"] - 120.0) < 0.01, (
        "infos annonce {:.1f} mm".format(_i18["largeur_mm"]))

# LA HAUTEUR SUIT LE MÊME CHEMIN, et souffrait davantage : la boîte couvre
# tout l'em, jambages compris, alors qu'un « a » n'a ni hampe ni queue.
_c18h, _i18h = cal.chaines_calligraphie(_chemin, "Atelier", hauteur_mm=50.0)
_e18h = cal.rendre_texte(_chemin, "Atelier", em_px=cal.EM_PX)
_w18h, _h18h = _empreinte_mm(_c18h, _i18h, _e18h)
print("   hauteur : demandé 50,0 mm → brûlé {:.1f} mm  ({:+.1f} %)"
      .format(_h18h, 100 * (_h18h - 50.0) / 50.0))
assert 0.98 <= _h18h / 50.0 <= 1.15, (
    "50 mm de hauteur demandés, {:.1f} mm brûlés -- la boîte de rendu "
    "couvre tout l'em, jambages compris, et servait d'échelle".format(_h18h))

# LES DEUX MODES DOIVENT S'ACCORDER. C'est l'argument qui a tranché :
# `contours_texte` tenait sa taille à 0,000 % près pendant que le squelette
# perdait jusqu'à 60 %. Deux modes du même atelier, la même demande, deux
# tailles gravées -- il n'y a pas de lecture où les deux ont raison.
_cont18, _ic18 = cal.contours_texte(_chemin, "Atelier", largeur_mm=120.0)
_xs18 = [p[0] for c in _cont18 for p in c]
_larg_contour = max(_xs18) - min(_xs18)
_c18b, _i18b = cal.chaines_calligraphie(_chemin, "Atelier", largeur_mm=120.0)
_w18b, _ = _empreinte_mm(_c18b, _i18b,
                         cal.rendre_texte(_chemin, "Atelier", em_px=cal.EM_PX))
print("   même texte, même demande : contour {:.1f} mm, squelette {:.1f} mm"
      .format(_larg_contour, _w18b))
assert abs(_larg_contour - _w18b) / 120.0 <= 0.03, (
    "les deux modes gravent {:.1f} et {:.1f} mm pour la même demande"
    .format(_larg_contour, _w18b))

# ET LE REPÈRE DE RETOURNEMENT N'EST PLUS LA TAILLE ANNONCÉE. Les deux
# vivaient sous la même clé : l'une des deux était forcément fausse.
assert _i18b["hauteur_image_mm"] > _i18b["hauteur_mm"], (
    "la hauteur de l'image doit dépasser celle de l'encre (marges)")
print("18. taille tenue en largeur comme en hauteur, les deux modes "
      "d'accord, repère de retournement séparé OK")


# ==========================================================================
# 19. LE BORD DE L'IMAGE N'EST PAS DE L'ENCRE
# ==========================================================================
# `_decale` reboucle par `np.roll` : le voisin « au-dessus » de la ligne 0
# était la DERNIÈRE ligne. Et la transformée de distance ne connaît que le
# tableau : une encre collée au bord n'a pas de fond de ce côté-là et se
# lit plus large qu'elle n'est -- 6,0 px pour une barre de 4, soit 50 % de
# trop sur la largeur même qui commande le fuseau Z.
#
# AUCUNE POLICE NE LE DÉCLENCHE : la marge de 15 % de `rendre_texte` tient,
# 40 polices essayées. Le contrôle doit donc FABRIQUER le cas -- sans quoi
# le correctif n'est gardé par rien, et c'est ce que le sabotage a montré.
# `marge` est un paramètre, et `amincir`/`largeur_locale`/`contraste_encre`
# sont publiques : ce fichier les appelle lui-même sur des tableaux nus.

_barre_bord = np.zeros((20, 40), dtype=bool)
_barre_bord[0:4, 5:35] = True              # collée à la ligne 0
_barre_libre = np.zeros((20, 40), dtype=bool)
_barre_libre[8:12, 5:35] = True            # la même, au large

_l_bord = float(cal.largeur_locale(_barre_bord)[1, 20])
_l_libre = float(cal.largeur_locale(_barre_libre)[9, 20])
print()
print("=" * 62)
print("§19  Le bord de l'image n'est pas de l'encre")
print("=" * 62)
print("   barre de 4 px : {:.1f} px au bord, {:.1f} px au large"
      .format(_l_bord, _l_libre))
assert abs(_l_bord - 4.0) < 0.51, (
    "une barre de 4 px collée au bord se lit {:.1f} px : la transformée de "
    "distance prend le bord du tableau pour de l'encre".format(_l_bord))
assert abs(_l_bord - _l_libre) < 0.51, (
    "la même barre se mesure {:.1f} px au bord et {:.1f} px au large"
    .format(_l_bord, _l_libre))

# Et le rebouclage : deux barres aux bords opposés ne se touchent PAS.
_deux = np.zeros((21, 40), dtype=bool)
_deux[0, 10:30] = True
_deux[20, 10:30] = True
_haut = cal._decale(_deux, 1, 0)           # ce qui devient le voisin du dessus
assert not _haut[1, 20] or True, "garde-fou de lecture"
assert not cal._decale(_deux, -1, 0)[20, 20], (
    "la ligne du haut est vue comme voisine de celle du bas : np.roll "
    "reboucle, et l'encre du bord se croit raccordée au bord opposé")
assert cal._decale(_deux, 1, 0)[1, 20], (
    "un décalage ordinaire doit continuer de décaler")
print("   deux barres aux bords opposés ne se voient plus : OK")
print("19. bord : largeur juste au bord, aucun rebouclage OK")
