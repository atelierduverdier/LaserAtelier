# -*- coding: utf-8 -*-
"""La PLUME : des pleins et déliés sur une police mono-trait.

Christophe, 04/08/2026, capture de l'aperçu à l'appui : « les pleins et les
déliés, je vois pas où ils sont ». Ils n'y étaient pas -- et je lui avais
dit le contraire. Une police mono-trait EST un squelette : elle ne porte
aucune épaisseur, et le mode Calligraphie ne fait qu'EXTRAIRE celle d'une
police à contour rempli.

Il restait pourtant une information, et elle est EXACTE : la DIRECTION de
chaque trait, lue dans le dessin de la police. Un bec de plume large et
incliné en tire des pleins et des déliés -- et sans les déviations aux
croisements que coûte un squelette tramé, puisque rien n'est estimé.
"""
import math

from harness import preparer, sans_dialogues

h = preparer()
core = h.core
tp = h.tp


# --- 1. LE MODÈLE DE LA PLUME, sur des cas qu'on peut vérifier de tête ---
# Un bec plat (0°) : le fût vertical est au MAXIMUM, la barre horizontale au
# MINIMUM. C'est la définition ; si ces deux-là s'inversent, tout le reste
# est faux et joli quand même.
_MINI, _MAXI = 0.20, 1.00
_fut = core.largeur_plume((0, 0), (0, -1), 0.0, _MINI, _MAXI)
_barre = core.largeur_plume((0, 0), (1, 0), 0.0, _MINI, _MAXI)
assert abs(_fut - _MAXI) < 1e-9, ("bec plat : le fût n'est pas au maximum", _fut)
assert abs(_barre - _MINI) < 1e-9, ("bec plat : la barre n'est pas au minimum",
                                    _barre)
# Le trait PARALLÈLE au bec est toujours le plus fin, quel que soit l'angle.
for _a in (0.0, 25.0, 40.0, 70.0):
    _para = core.largeur_plume(
        (0, 0), (math.cos(math.radians(_a)), math.sin(math.radians(_a))),
        _a, _MINI, _MAXI)
    _perp = core.largeur_plume(
        (0, 0), (-math.sin(math.radians(_a)), math.cos(math.radians(_a))),
        _a, _MINI, _MAXI)
    assert abs(_para - _MINI) < 1e-9 and abs(_perp - _MAXI) < 1e-9, (
        "à {:.0f}°, parallèle et perpendiculaire ne donnent pas les deux "
        "extrêmes".format(_a), _para, _perp)
# Un point immobile ne doit pas donner une largeur nulle (division par rien).
assert core.largeur_plume((5, 5), (5, 5), 25.0, _MINI, _MAXI) == _MAXI
print("1. bec plat : fût au maxi, barre au mini ; parallèle/perpendiculaire "
      "aux quatre angles OK")


# --- 2. LA LARGEUR SUIT LA TAILLE DU TEXTE ------------------------------
# Une plume ne grossit pas avec la lettre ; une POLICE si -- et tout l'aval
# en dépend : le verdict juge si le matériau sait rendre les pleins
# demandés, ce qu'il ne peut faire que si la demande varie avec la taille.
_tailles = {}
for _l in (60.0, 120.0, 240.0):
    _ch, _inf = core.chaines_plume("verdier", "Atelier", largeur_mm=_l)
    _tailles[_l] = _inf
    assert abs(_inf["largeur_mm"] - _l) < 0.5, (
        "le texte ne fait pas la largeur demandée", _l, _inf["largeur_mm"])
_a, _b = _tailles[60.0], _tailles[240.0]
assert abs(_b["largeur_trait_max"] / _a["largeur_trait_max"] - 4.0) < 0.05, (
    "les pleins ne suivent pas la taille du texte",
    _a["largeur_trait_max"], _b["largeur_trait_max"])
assert abs(_a["rapport"] - _b["rapport"]) < 0.05, (
    "le contraste plein/délié change avec la taille, il ne devrait pas")
print("2. texte ×4 → pleins ×{:.1f}, contraste inchangé ({:.1f}:1) OK".format(
    _b["largeur_trait_max"] / _a["largeur_trait_max"], _a["rapport"]))


# --- 3. IL Y A VRAIMENT DES PLEINS ET DES DÉLIÉS ------------------------
# Le défaut qu'on répare est précisément « tout est de la même épaisseur ».
# Un contrôle qui ne regarderait que la présence de largeurs passerait sur
# une police plate.
_ch, _inf = core.chaines_plume("verdier", "Atelier du Verdier", largeur_mm=120.0)
# LE SEUIL VIENT DU DÉFAUT QU'ON RÉPARE. Livrée à 6 % / 5:1, la plume
# rendait 3,1:1 -- et Christophe, l'aperçu sous les yeux : « c'est une
# police un peu plus épaisse quoi ». Il avait raison. Ses propres polices
# calligraphiques demandent 26:1 et 31:1 ; en dessous de 4 on n'est pas
# dans le même métier, et un contrôle à 2 aurait laissé passer exactement
# ce qu'il a rejeté.
assert _inf["rapport"] > 4.0, (
    "le trait ne module pas assez pour qu'on parle de pleins et déliés : "
    "c'est une police un peu plus épaisse, pas une plume", _inf["rapport"])
assert _inf["largeur_trait_max"] / (_inf["hauteur_mm"] or 1) > 0.10, (
    "le plein fait moins de 10 % de la hauteur : une plume est GRASSE, "
    "c'est ce qui la distingue d'un trait épaissi",
    _inf["largeur_trait_max"], _inf["hauteur_mm"])
# ET LA MODULATION EST DANS LA LETTRE, pas seulement entre les lettres.
# Le contrôle porte sur la STRUCTURE plutôt que sur un rapport global : le
# « A » de Verdier est fait de deux gestes -- le chevron, puis la barre --
# et la barre, horizontale, doit sortir plus fine que les jambages, qui
# sont raides. Un rapport global se contenterait d'un chiffre ; celui-ci
# ne peut pas passer par accident, et il dit ce que « pleins et déliés »
# veut dire.
_ch_a, _ = core.chaines_plume("verdier", "A", largeur_mm=40.0)
assert len(_ch_a) == 2, ("le « A » n'a plus deux gestes, le contrôle vise "
                         "peut-être le mauvais", len(_ch_a))
_moy = [sum(p[2] for p in c) / len(c) for c in _ch_a]
assert _moy[1] < _moy[0] * 0.75, (
    "la barre du « A » n'est pas plus fine que ses jambages : la plume ne "
    "module pas dans la lettre", _moy)
print("3. contraste {:.1f}:1 sur le texte ; dans le « A », barre {:.2f} mm "
      "contre {:.2f} aux jambages OK".format(_inf["rapport"], _moy[1], _moy[0]))


# --- 4. LA FORME RENDUE EST CELLE QUE LA SUITE ATTEND -------------------
# C'est tout le pari de l'ajout : verdict, aperçu, pose du tracé et
# générateur du fuseau ne savent pas d'où viennent les gestes. S'ils
# divergeaient d'une clé, ça tomberait à la génération, pas ici.
import calligraphie as cal                                   # noqa: E402
_ref = cal.chaines_calligraphie.__doc__ or ""
_attendu = ("largeur_mm", "hauteur_mm", "mm_px", "largeur_trait_min",
            "largeur_trait_max", "rapport", "n_chaines", "longueur_mm")
for _k in _attendu:
    assert _k in _inf, ("la plume ne rend pas la clé « {} » que le panneau "
                        "lit sur l'autre source".format(_k))
assert all(len(p) == 3 for c in _ch for p in c), (
    "les gestes ne sont pas des triplets (x, y, largeur)")
print("4. mêmes clés d'infos et mêmes triplets que chaines_calligraphie OK")


# --- 5. LE PANNEAU LE PROPOSE, ET S'EN SERT -----------------------------
# On éprouve le chemin que Christophe coche, pas la fonction derrière.
sans_dialogues()
_p = tp.TaskPanelCalligraphie()
assert hasattr(_p, "chk_plume"), "la case « plume » n'est pas dans le panneau"
_p.chk_plume.setChecked(True)
_i = _p.combo_plume_police.findData("verdier")
assert _i >= 0, "les polices mono-trait ne sont pas proposées"
_p.combo_plume_police.setCurrentIndex(_i)
_p.edt_texte.setText("Atelier du Verdier")
_p.spn_largeur.setValue(120.0)
_res = _p._chaines()
assert _res and _res[1].get("plume"), (
    "le panneau n'est pas passé par la plume alors que la case est cochée")
assert _res[1]["rapport"] > 4.0
# Décochée, il revient au fichier .otf -- et sans fichier, il ne rend rien
# plutôt que de rendre la plume en douce.
_p.chk_plume.setChecked(False)
_p.edt_police.setText("")
assert _p._chaines() is None, (
    "case décochée et aucun fichier : le panneau doit se taire, pas "
    "retomber sur la plume")
print("5. le panneau propose la plume, s'en sert cochée, et revient au "
      "fichier décochée OK")


# --- 6. L'APERÇU CONTIENT L'ENCRE ---------------------------------------
# Christophe : « le rendu dépasse du cadre » -- le « r » de Verdier coupé
# net. Ce n'était pas la plume : l'aperçu se dimensionnait sur `infos`,
# c'est-à-dire sur la LIGNE MOYENNE, alors qu'un trait posé au bord
# déborde de sa demi-largeur. Le défaut était là depuis toujours et ne se
# voyait pas tant que les pleins faisaient 0,7 mm ; à 2 mm il saute aux
# yeux. Une plume plus grasse n'a rien cassé, elle a RÉVÉLÉ.
from PySide6 import QtGui                                    # noqa: E402

_ch6, _inf6 = core.chaines_plume("verdier", "Atelier du Verdier",
                                 largeur_mm=120.0)
_prep6 = core.preparer_calligraphie(_ch6, 200.0,
                                    (core.burn_width_materials() or ["MDF"])[0],
                                    power_max=900)
_img = tp._rendre_calligraphie(_ch6, _prep6, _inf6)
_fond = QtGui.QColor(250, 246, 238).rgb()
_bord = 0
for _x in range(_img.width()):
    for _y in (0, _img.height() - 1):
        if _img.pixel(_x, _y) != _fond:
            _bord += 1
for _y in range(_img.height()):
    for _x in (0, _img.width() - 1):
        if _img.pixel(_x, _y) != _fond:
            _bord += 1
assert _bord == 0, (
    "{} pixels d'encre touchent le bord de l'aperçu : le tracé est coupé, "
    "et c'est le cadre qui est trop petit, pas le tracé trop gros".format(_bord))
print("6. l'aperçu contient l'encre : {}×{} px, aucun pixel sur le bord OK"
      .format(_img.width(), _img.height()))
