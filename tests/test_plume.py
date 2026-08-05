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
import inspect
import re
import textwrap
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


# --- 7. LE SCHÉMA MONTRE LE RÉGLAGE COURANT -----------------------------
# Christophe : « je ne comprends pas comment fonctionne le bec et le
# contraste, un petit schéma graphique sera le bienvenu non ? ». Un schéma
# FIGÉ aurait montré un cas ; celui-ci montre le sien. Le contrôle porte
# donc sur ce qui compte : il doit CHANGER quand les réglages changent, et
# tenir dans son image -- la première légende débordait des deux côtés et
# se lisait « rait EN TRAVERS… ».
_s0 = tp._schema_plume(0.0, 16.0, 16.0)
_s25 = tp._schema_plume(25.0, 16.0, 16.0)
_smince = tp._schema_plume(0.0, 6.0, 5.0)
assert _s0.size() == _s25.size() == _smince.size()


def _empreinte(im):
    """L'encre de la BANDE DES TRAITS seule, hors titre et légende.

    Premier jet : toute l'image. Il ne pouvait pas échouer -- le titre dit
    « bec à 0° » puis « bec à 25° », deux textes de largeurs différentes,
    donc deux comptes de pixels différents même avec un schéma figé. Le
    sabotage (angle ignoré) est passé, et c'est exactement le genre de
    contrôle qui rassure sans rien vérifier."""
    return sum(1 for _x in range(0, im.width(), 2) for _y in range(32, 88, 2)
               if im.pixel(_x, _y) != QtGui.QColor(250, 246, 238).rgb())


_e0, _e25, _em = _empreinte(_s0), _empreinte(_s25), _empreinte(_smince)
assert _e0 != _e25, ("le schéma ne bouge pas quand l'angle du bec change : "
                     "il montre une règle, pas le réglage", _e0, _e25)
assert _em < _e0, ("un plein de 6 % ne dessine pas moins d'encre qu'un plein "
                   "de 16 % : le schéma ignore l'épaisseur", _em, _e0)

# La légende ne doit pas déborder : aucun pixel de texte sur les colonnes
# extrêmes.
_fond = QtGui.QColor(250, 246, 238).rgb()
_deborde = sum(1 for _y in range(_s25.height())
               for _x in (0, 1, _s25.width() - 2, _s25.width() - 1)
               if _s25.pixel(_x, _y) != _fond)
assert _deborde == 0, ("le schéma déborde de son image sur {} pixels : la "
                       "légende est coupée".format(_deborde))
print("7. le schéma suit l'angle ET l'épaisseur, et tient dans son cadre OK")


# --- 8. LE CHAPEAU S'INSÈRE D'UN BOUTON ---------------------------------
# Christophe : « c'est quelle touche le chapeau, CTRL + ? ». Aucune -- c'est
# AltGr + $. Mais si la question se pose, la réponse est mauvaise : un
# caractère qu'il faut chercher n'est pas disponible, il l'est en théorie.
assert core.HERSHEY_FONTS.get("verdier")
assert tp.CHAPEAU_GLYPHE == "¤"
_verd = core._hershey_module("verdier")
assert _verd.GLYPHES.get(tp.CHAPEAU_GLYPHE), "le bouton insérerait un glyphe vide"

# Les DEUX panneaux qui écrivent du texte l'ont, et il pose vraiment le
# caractère -- sur un QLineEdit comme sur un QTextEdit, dont les méthodes
# d'insertion ne portent pas le même nom.
_pt = tp.TaskPanelText()
_pt.txt.setPlainText("Atelier ")
_pt.btn_chapeau.click()
assert tp.CHAPEAU_GLYPHE in _pt.txt.toPlainText(), (
    "le bouton du mode Texte n'insère rien", _pt.txt.toPlainText())

_pc = tp.TaskPanelCalligraphie()
_pc.edt_texte.setText("Atelier ")
_pc.edt_texte.setCursorPosition(len(_pc.edt_texte.text()))
_pc.btn_chapeau.click()
assert tp.CHAPEAU_GLYPHE in _pc.edt_texte.text(), (
    "le bouton du mode Calligraphie n'insère rien", _pc.edt_texte.text())

# Et le chapeau se GRAVE : le glyphe traverse deplier_texte, qui remplace
# tout ce que la police ne sait pas tracer. Sur une police qui ne l'a pas,
# il doit disparaître plutôt que sortir en carré.
assert core.deplier_texte(tp.CHAPEAU_GLYPHE, _verd, quiet=True) == tp.CHAPEAU_GLYPHE
_sans = core._hershey_module("sans")
assert tp.CHAPEAU_GLYPHE not in core.deplier_texte(
    tp.CHAPEAU_GLYPHE, _sans, quiet=True), (
    "le chapeau passe sur une police qui ne le dessine pas")
print("8. chapeau inséré au bouton dans les deux panneaux, gravé en Verdier, "
      "écarté ailleurs OK")


# --- 9. DEUX INSTRUMENTS, ET ILS NE FONT PAS LA MÊME CHOSE --------------
# Christophe, la plume appliquée à une CURSIVE : « c'est une bonne idée
# mais c'est à améliorer le résultat je trouve ». Le modèle était juste --
# pour une italique. Un bec plat met des pleins dans les REMONTÉES, là où
# aucune main n'en met : on n'appuie pas en poussant une pointe vers le
# haut, elle accroche.
_MI, _MA = 0.20, 1.00
_desc = ((0, 0), (0, -1))          # trait qui DESCEND (y vers le haut)
_mont = ((0, 0), (0, 1))           # le même, qui REMONTE

# Bec plat : les deux sont identiques, la direction seule compte.
assert abs(core.largeur_plume(_desc[0], _desc[1], 0.0, _MI, _MA, core.PLUME_BEC)
           - core.largeur_plume(_mont[0], _mont[1], 0.0, _MI, _MA,
                                core.PLUME_BEC)) < 1e-9, (
    "avec un bec plat, monter et descendre doivent donner la MÊME largeur")

# Plume pointue : la descente est pleine, la remontée reste filiforme.
_p_desc = core.largeur_plume(_desc[0], _desc[1], 0.0, _MI, _MA, core.PLUME_POINTUE)
_p_mont = core.largeur_plume(_mont[0], _mont[1], 0.0, _MI, _MA, core.PLUME_POINTUE)
assert _p_desc > 0.9 * _MA, ("la descente n'est pas un plein", _p_desc)
assert abs(_p_mont - _MI) < 1e-9, (
    "la remontée n'est pas un délié : c'est exactement le défaut signalé "
    "sur la cursive", _p_mont)
print("9. bec plat : monter = descendre ; pointue : descente {:.2f}, "
      "remontée {:.2f} mm OK".format(_p_desc, _p_mont))


# --- 10. LE LISSAGE PORTE SUR UNE DISTANCE, PAS SUR DES POINTS ----------
# Le lissage portait sur TROIS POINTS. Or une polyligne de police n'a pas
# de pas régulier : un fût droit fait deux points sur 10 mm, une ronde en
# fait vingt. Trois points ne lissaient donc rien sur les droites et
# beaucoup dans les courbes -- d'où les bosses, très visibles sur une
# cursive qui n'est que courbes.
#
# Le contrôle : deux échantillonnages du MÊME arc doivent donner le même
# profil de largeur. Avec un lissage en points, le plus fin sortait plus
# lisse que l'autre.
import math as _m                                            # noqa: E402


def _arc(n):
    return [(30.0 * _m.cos(_m.radians(180.0 * i / n)),
             30.0 * _m.sin(_m.radians(180.0 * i / n))) for i in range(n + 1)]


_gros = core._largeurs_du_trait(_arc(12), 25.0, 0.2, 1.6)
_fin = core._largeurs_du_trait(_arc(48), 25.0, 0.2, 1.6)
# on compare aux mêmes abscisses (un point sur quatre du fin)
_ecart = max(abs(_gros[i] - _fin[4 * i]) for i in range(len(_gros)))
assert _ecart < 0.10, (
    "le profil de largeur dépend de la FINESSE d'échantillonnage : le "
    "lissage compte des points au lieu de mesurer une distance", _ecart)
print("10. même arc échantillonné 12 ou 48 fois : profils à {:.3f} mm près OK"
      .format(_ecart))


# --- 11. UN FÛT NE SE TRACE PAS EN DEUX MORCEAUX ------------------------
# Christophe, la plume pointue à l'écran : « un U est réalisé en 1 seul
# trait ». Le « u » de Verdier avait son fût droit coupé en deux -- la
# cuvette remontait jusqu'à la hauteur d'x, puis un SECOND trait
# redescendait du milieu à la ligne de base.
#
# Sans plume, invisible. Avec une pointe, la moitié remontante sort en
# délié et la descendante en plein : le même fût, fin en haut et gras en
# bas, avec une cassure au milieu. Le contrôle porte sur la LARGEUR le
# long du fût, pas sur le nombre de traits -- c'est le défaut visible qui
# compte, et il attraperait aussi une autre façon de le produire.
# Le contrôle porte sur CHAQUE TRAIT pris à part, et seulement sur les
# traits qui SONT des fûts : longs et quasi verticaux. Premier jet : la
# largeur de tous les points d'une colonne x -- il tombait sur le « u »
# CORRIGÉ, parce que la cuvette vient légitimement se raccorder au fût par
# le haut, en délié. Un contrôle qui accuse la bonne version n'apprend
# rien.
def _futs(car):
    """Les traits longs et quasi verticaux du glyphe, avec leurs largeurs."""
    ch, inf = core.chaines_plume("verdier", car, largeur_mm=30.0,
                                 angle_deg=55.0, modele=core.PLUME_POINTUE)
    out = []
    for c in ch:
        dy = abs(c[-1][1] - c[0][1])
        dx = abs(c[-1][0] - c[0][0])
        long_ = dy > 0.55 * inf["hauteur_mm"]
        droit = dx < 0.12 * max(dy, 1e-9)
        # et il ne serpente pas : la corde vaut presque le développé
        dev = sum(_m.hypot(c[i + 1][0] - c[i][0], c[i + 1][1] - c[i][1])
                  for i in range(len(c) - 1))
        if long_ and droit and dev < 1.08 * _m.hypot(dx, dy):
            out.append([p[2] for p in c])
    return out


_f_u = _futs("u")
assert _f_u, "aucun fût droit trouvé dans le « u » : il est encore en morceaux"
for _w in _f_u:
    assert max(_w) / max(min(_w), 1e-9) < 1.25, (
        "le fût du « u » change d'épaisseur sur sa hauteur : il est tracé "
        "en deux morceaux, un montant et un descendant", min(_w), max(_w))

# La propriété vaut pour TOUTE la famille -- règle de la maison : on
# éprouve la propriété sur la famille, pas sur le cas signalé.
_sans_fut = []
for _c in "bdhklmnpqu":
    _fs = _futs(_c)
    if not _fs:
        _sans_fut.append(_c)
        continue
    for _w in _fs:
        assert max(_w) / max(min(_w), 1e-9) < 1.25, (
            "le fût de « {} » change d'épaisseur sur sa hauteur".format(_c),
            min(_w), max(_w))
assert not _sans_fut, ("ces lettres n'ont plus de fût droit reconnaissable, "
                       "le contrôle ne vérifie donc rien sur elles", _sans_fut)
print("11. les fûts de b d h k l m n p q u sont d'un seul tenant OK")


# --- 12. ON NE LISSE PAS LES POLICES EXTRAITES --------------------------
# Christophe : « si le lissage fonctionne pourquoi pas le mettre sur les
# autres caractères réalisés à partir des fonts ». Branché, puis MESURÉ :
# chaque fenêtre coûte plus de contraste qu'elle ne gagne en régularité
# (voir le tableau dans TaskPanelCalligraphie._chaines). Ce n'est pas du
# bruit, c'est le dessin de la lettre.
#
# Le contrôle fige la mesure : si un jour le lissage y revient, il faudra
# rouvrir ce chiffre-là. `lisser_largeurs` reste éprouvée pour elle-même --
# c'est son EMPLOI sur les polices extraites qui est écarté.
_ch12 = [[(float(i), 0.0, 1.0 if i % 2 else 0.4) for i in range(40)]]
_lisse = core.lisser_largeurs(_ch12, 4.0, passes=2)
_w12 = [p[2] for c in _lisse for p in c]
assert max(_w12) - min(_w12) < 0.25, (
    "lisser_largeurs ne lisse plus : une dent de scie doit s'aplatir",
    min(_w12), max(_w12))
_intact = core.lisser_largeurs(_ch12, 0.0)
assert _intact is _ch12, "une fenêtre nulle doit rendre les gestes tels quels"
# et elle ne touche JAMAIS au tracé
assert all(a[0] == b[0] and a[1] == b[1]
           for ca, cb in zip(_ch12, _lisse) for a, b in zip(ca, cb)), (
    "le lissage a déplacé des points : il ne doit toucher que la largeur")
print("12. lisser_largeurs aplatit la dent de scie sans bouger le tracé ; "
      "écartée des polices extraites sur mesure OK")


# --- 13. LE LISSAGE NE DOIT PAS MANGER LE CONTRASTE ----------------------
# Christophe, la gravure « Atelier du Verdier du munu » en main le
# 05/08/2026. Le champ affichait 16:1 et le bois recevait 4,1:1 -- et ce
# n'était ni la police, ni le limiteur de pente Z : c'était le lissage
# livré la veille (fenêtre = le plein entier, PLUS une seconde passe).
_TXT = u"Atelier du Verdier du munu"
_ch, _inf = core.chaines_plume("verdier", _TXT, largeur_mm=80.0,
                               contraste=16.0)
_ws = [w for g in _ch for (_x, _y, w) in g]
_rapport = max(_ws) / min(_ws)
assert _rapport > 6.0, (
    "le contraste obtenu est retombé sous 6:1 : le lissage remange ce que "
    "le champ promet (16:1 demandé, 4,1:1 gravé avant correction)", _rapport)

# La fenêtre est BIEN la moitié du plein, et il n'y a PLUS de seconde passe.
assert abs(core.PLUME_LISSAGE_FENETRE - 0.5) < 1e-9, (
    "la fenêtre de lissage a changé sans que la mesure soit refaite",
    core.PLUME_LISSAGE_FENETRE)
_src = inspect.getsource(core.chaines_plume)
assert "lisser_largeurs" not in _src, (
    "la seconde passe de lissage est revenue : elle coûtait à elle seule "
    "4,9:1 -> 4,1:1 de contraste pour 8 % d'ondulation")

# SABOTAGE : on remet le réglage de la v2.80.2 et le contrôle doit échouer.
_faux = _src.replace("lissage_mm=maxi * PLUME_LISSAGE_FENETRE",
                     "lissage_mm=maxi")
assert _faux != _src, "le sabotage n'a rien remplacé -- il ne prouve rien"
_ns = dict(core.__dict__)
exec(compile(_faux, "<sabotage>", "exec"), _ns)
_ch2, _ = _ns["chaines_plume"]("verdier", _TXT, largeur_mm=80.0,
                               contraste=16.0)
_ws2 = [w for g in _ch2 for (_x, _y, w) in g]
assert max(_ws2) / min(_ws2) < _rapport - 0.5, (
    "revenir à la fenêtre pleine ne change rien : le contrôle ci-dessus ne "
    "prouve pas que c'est le lissage qui gouvernait le contraste",
    max(_ws2) / min(_ws2), _rapport)
print("13. le lissage ne mange plus le contraste : {:.1f}:1 obtenu contre "
      "{:.1f}:1 avec le réglage de la v2.80.2 OK".format(
          _rapport, max(_ws2) / min(_ws2)))


# --- 14. LE VERDICT NOMME LA VITESSE QUI DÉBLOQUE LES DÉLIÉS ------------
# Un verdict qui dit « ces déliés sortiront gras » sans dire quoi faire
# renvoie chercher. Le plancher du trait dépend fortement de l'avance.
for _mat in core.burn_width_materials():
    if _mat.startswith("ZZ-"):
        continue
    _v = core.vitesse_pour_delie(_mat, 0.125, 900.0)
    if _v is None:
        continue
    _ech = core.echelle_fuseau_z(_mat, _v, power_max=900.0, line_min_mm=0.0)
    assert _ech and _ech[1] <= 0.125 + 1e-9, (
        "la vitesse proposée ne sait pas faire le trait demandé -- c'est "
        "exactement le défaut « descendre à F3000 alors que F3000 refuse »",
        _mat, _v, _ech[1] if _ech else None)
assert core.vitesse_pour_delie(u"Hêtre", 1e-4, 900.0) is None, (
    "un délié impossible se voit proposer une vitesse quand même : le "
    "message enverrait vers un réglage qui ne marchera pas")
print("14. la vitesse proposée pour les déliés sait vraiment les faire, et "
      "l'impossible ne reçoit aucune proposition OK")


# --- 15. LE PANNEAU NE DOIT PAS RELIRE LA CONFIG EN BOUCLE --------------
# Christophe l'a ENTENDU avant de le voir : « le panneau met beaucoup de
# temps à s'afficher et j'entends le PC souffler ». Cause : la première
# version de `vitesse_pour_delie` appelait `echelle_fuseau_z` par vitesse
# candidate, et cette fonction bâtit toute l'échelle du fuseau par
# dichotomie. 26 échelles construites, 138 762 largeurs interpolées, 15 s.
#
# On compte les LECTURES, pas les secondes : un seuil en secondes est du
# bruit sur une machine partagée, un compteur non.
_n = [0]
_vraie_config = core.load_config


def _compter(*a, **k):
    _n[0] += 1
    return _vraie_config(*a, **k)


core.load_config = _compter
try:
    core.vitesse_pour_delie(u"Hêtre", 0.125, 900.0)
finally:
    core.load_config = _vraie_config
assert _n[0] <= 2, (
    "vitesse_pour_delie relit la config plusieurs fois : chaque lecture "
    "analyse tout le fichier JSON, et c'est une boucle d'analyse de "
    "fichier déguisée en boucle de calcul", _n[0])

# Et elle ne doit PAS APPELER l'échelle du fuseau -- vérifié sur l'ARBRE
# SYNTAXIQUE, pas par une recherche de texte : le commentaire de la
# fonction cite le nom pour raconter le défaut, et une recherche naïve
# accusait donc l'explication du correctif.
import ast as _ast
_arbre = _ast.parse(textwrap.dedent(
    inspect.getsource(core.vitesse_pour_delie)))
_appels = {n.func.id for n in _ast.walk(_arbre)
           if isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)}
assert "echelle_fuseau_z" not in _appels, (
    "vitesse_pour_delie reconstruit l'échelle du fuseau : c'est le défaut "
    "qui a fait passer le panneau Calligraphie à 15 s à l'ouverture",
    sorted(_appels))

# SABOTAGE : la version d'origine, et le compteur doit exploser.
_faux = '''def sabote(material, largeur_voulue, power_max=None):
    mat = _burn_width_material(material)
    tables = load_burn_widths(mat)
    mesures = (tables.get("focus") or []) + (tables.get("defocus") or [])
    for f in sorted({float(e.get("feed", 0) or 0) for e in mesures}):
        if f <= 0:
            continue
        ech = echelle_fuseau_z(mat, f, power_max=power_max, line_min_mm=0.0)
        if ech and ech[1] <= largeur_voulue + 1e-9:
            return f
    return None
'''
_ns = dict(core.__dict__)
exec(compile(_faux, "<sabotage>", "exec"), _ns)
_n[0] = 0
_ns["load_config"] = _compter
core.load_config = _compter
try:
    _ns["sabote"](u"Hêtre", 0.125, 900.0)
finally:
    core.load_config = _vraie_config
assert _n[0] > 2, (
    "le sabotage ne relit pas la config plus souvent : le contrôle "
    "ci-dessus ne prouve rien", _n[0])
print("15. vitesse_pour_delie : {} lecture(s) de config contre {} pour la "
      "version qui a fait souffler le PC OK".format(1, _n[0]))


# --- 16. LA PUISSANCE NE DOIT PAS ÊTRE COLLÉE À SON PLANCHER ------------
# Christophe, sa calligraphie gravée à F800 : « c'est vraiment moins bon
# qu'avant ». Son G-code annonçait « Trait 0.12 a 3.43 mm » alors qu'aucune
# lettre ne dépasse 0,52 : le haut de l'échelle était la plus large brûlure
# du MATÉRIAU, pas le plus gros trait du DESSIN. Comme S suit la largeur,
# tout le texte réclamait S136 et sortait rabattu au plancher S200 -- donc
# la puissance ne pouvait plus compenser la vitesse.
# UN CAS DISCRIMINANT D'ABORD. À 80 mm le plein de la plume fait 0,84 mm et
# échappe de justesse au plancher : le contrôle passerait sans rien prouver.
# On prend la taille où l'écart est franc -- et c'est la taille ordinaire
# d'une signature.
_ch16, _i16 = core.chaines_plume("verdier", u"Atelier du Verdier",
                                 largeur_mm=30.0)
_wmax16 = max(p[2] for c in _ch16 for p in c)
_g16, _d16 = core.preparer_calligraphie(_ch16, 800.0, u"Hêtre",
                                        power_max=900.0)
_ss16 = [p.s for c in _g16 for p in c]
assert _d16["w_max"] <= _wmax16 + 1e-6, (
    "le haut de l'échelle dépasse le plus gros trait du dessin : la "
    "puissance sera écrasée vers le bas pour tout le texte",
    _d16["w_max"], _wmax16)
_au_plancher = 100.0 * sum(1 for s in _ss16 if s <= 201) / len(_ss16)
assert _au_plancher < 50.0, (
    "plus de la moitié du tracé est collée au plancher de puissance : à "
    "cette vitesse le trait ne marquera pas, et accélérer ne pourra plus "
    "être compensé", _au_plancher)
assert max(_ss16) > 2 * min(_ss16), (
    "la puissance ne varie presque pas d'un délié à un plein : le fuseau "
    "ne module plus rien", min(_ss16), max(_ss16))

# SABOTAGE : on retire le plafond, comme avant le correctif.
_g16b, _d16b = core.preparer_calligraphie(_ch16, 800.0, u"Hêtre",
                                          power_max=900.0,
                                          largeur_max=99.0)
_ss16b = [p.s for c in _g16b for p in c]
_plancher_b = 100.0 * sum(1 for s in _ss16b if s <= 201) / len(_ss16b)
assert _plancher_b > 90.0, (
    "sans plafond la puissance n'est PAS écrasée : le contrôle ci-dessus "
    "ne prouve pas que c'est le plafond qui fait le travail", _plancher_b)
print("16. échelle plafonnée au plus gros trait du dessin : S{:.0f}-S{:.0f}, "
      "{:.0f} % au plancher contre {:.0f} % sans plafond OK".format(
          min(_ss16), max(_ss16), _au_plancher, _plancher_b))


# --- 17. AUCUN BLOC GRAVÉ NE DOIT DÉPASSER LE PAS D'ÉCHANTILLONNAGE -----
# Christophe, 05/08/2026, la calligraphie « Atelier du Verdier du munu » en
# Aston Script 160 mm sous les yeux : « sur le d, la barre verticale ne va
# pas, elle est fine en haut et épaisse en bas, je pense qu'elle est gravée
# en 2 passes pour 2 hauteurs différentes et non en une seule passe avec un
# z progressif ».
#
# La hampe était UN SEUL bloc G1 de 8,63 mm. Tout l'aval interpole entre
# deux points -- la machine fait varier Z linéairement sur tout le bloc --
# donc un fût droit, dont la plume donne une largeur CONSTANTE par
# construction, recevait la montée du Z destinée au plein situé quatre
# points plus loin, étalée sur ses 8,63 mm.
#
# LE CONTRÔLE PORTE SUR LE G-CODE ÉMIS, jamais sur la fonction qui le
# produit : le défaut vivait exactement entre les deux (`chaines_plume`
# rendait fidèlement les sommets qu'on lui demandait, et le générateur
# écrivait fidèlement un G1 par point -- personne ne mentait, il manquait
# simplement une étape).
_TXT17 = u"Atelier du Verdier du munu"


def _blocs_graves(txt):
    """Longueur XY de chaque G1 du fichier, dans l'ordre. Un G0 déplace le
    point courant sans rien graver."""
    x = y = None
    out = []
    for ligne in txt.splitlines():
        m = re.match(r"G([01]) X([-\d.]+) Y([-\d.]+)", ligne)
        if not m:
            continue
        nx, ny = float(m.group(2)), float(m.group(3))
        if m.group(1) == "1" and x is not None:
            out.append(math.hypot(nx - x, ny - y))
        x, y = nx, ny
    return out


_ch17, _i17 = core.chaines_plume("hersheyscript1", _TXT17, largeur_mm=160.0,
                                 angle_deg=50.0, epaisseur=0.16,
                                 contraste=16.0, modele="pointue")
_g17 = core.generate_gcode_calligraphie(_ch17, 8.0, 600.0, u"Hêtre",
                                        power_max=900.0)
_blocs17 = _blocs_graves(_g17)
_pire17 = max(_blocs17)
# LA PROPRIÉTÉ S'ÉNONCE EN LARGEURS DE BEC, pas en millimètres : une plume
# ne peut pas changer d'épaisseur plus vite que sa propre taille, donc la
# tête ne doit jamais parcourir plus d'une demi-largeur de plein entre deux
# consignes de hauteur. Dit en mm absolus, le contrôle serait faux à une
# autre taille de texte -- et le pas l'était (cf. §2, qui a refusé la
# première version de ce correctif).
assert _pire17 <= 0.5 * _i17["largeur_trait_max"], (
    "un bloc gravé de {:.2f} mm pour un plein de {:.2f} : la hauteur Z, "
    "donc la largeur du trait, est interpolée en aveugle sur toute sa "
    "longueur".format(_pire17, _i17["largeur_trait_max"]), _pire17)

# ET ELLE NE DOIT PAS DÉPENDRE DE LA TAILLE. C'est ce qui interdit un pas
# en millimètres absolus : le lissage, lui, vaut une fraction du plein.
_ch17b, _i17b = core.chaines_plume("hersheyscript1", _TXT17, largeur_mm=40.0,
                                   angle_deg=50.0, epaisseur=0.16,
                                   contraste=16.0, modele="pointue")
_g17b = core.generate_gcode_calligraphie(_ch17b, 8.0, 600.0, u"Hêtre",
                                         power_max=900.0)
_r17 = _pire17 / _i17["largeur_trait_max"]
_r17b = max(_blocs_graves(_g17b)) / _i17b["largeur_trait_max"]
assert abs(_r17 - _r17b) < 0.02, (
    "l'échantillonnage n'est pas le même à 40 et à 160 mm : le contraste "
    "obtenu suivra la taille du texte", _r17, _r17b)

# LA MÊME PROPRIÉTÉ SUR L'AUTRE PRODUCTEUR. Les deux voies -- plume et
# extraction -- se rejoignent dans `generate_gcode_calligraphie`, et c'est
# la famille entière qu'il faut tenir : la voie extraction ré-échantillonne
# depuis toujours (`calligraphie.PAS_ARC_MM`), la plume ne le faisait pas.
import calligraphie as cal17

_polices17 = cal17.polices_disponibles()
assert _polices17, "aucune police .otf/.ttf sur ce système : test impossible"
_che17 = cal17.chaines_calligraphie(_polices17[0][1], u"du", largeur_mm=40.0)[0]
_ge17 = core.generate_gcode_calligraphie(_che17, 8.0, 600.0, u"Hêtre",
                                         power_max=900.0)
_pire_ext17 = max(_blocs_graves(_ge17))
assert _pire_ext17 <= 1.5 * cal17.PAS_ARC_MM, (
    "la voie extraction émet elle aussi des blocs plus longs que son pas",
    _pire_ext17, cal17.PAS_ARC_MM)

# LE FÛT DU « d » LUI-MÊME : il doit garder une hauteur CONSTANTE sur
# l'essentiel de sa longueur. C'est la lecture de Christophe, pas une
# statistique -- un trait droit de plume ne change pas d'épaisseur.
_zs17 = []
_lg17 = _g17.splitlines()
_i = next(k for k, l in enumerate(_lg17) if l.startswith("G0 X46.82"))
for _l in _lg17[_i + 1:]:
    _m = re.match(r"G1 X([-\d.]+) Y([-\d.]+) Z([-\d.]+)", _l)
    if _m:
        _zs17.append((math.hypot(float(_m.group(1)) - 46.8203,
                                 float(_m.group(2)) - 9.5531),
                      float(_m.group(3))))
        if math.hypot(float(_m.group(1)) - 44.1073,
                      float(_m.group(2)) - 1.3637) < 1e-3:
            break
    elif _l.startswith("G0 X"):
        break
# La propriété est « la hauteur TIENT », pas « la hauteur vaut 8 » : ce
# fût est devenu un plein en v2.87.0, donc il se grave haut. Ce qu'un trait
# droit interdit, c'est que la hauteur BOUGE sur sa longueur.
_plat17 = max([d for d, z in _zs17 if abs(z - _zs17[0][1]) < 0.05] or [0.0])
assert _plat17 > 4.0, (
    "la hauteur bouge dès le haut de la hampe : le fût sortira fin en haut "
    "et épais en bas, exactement le défaut vu sur bois", _plat17)

# SABOTAGE : on retire la densification, comme avant le correctif.
_src17 = inspect.getsource(core.chaines_plume)
_faux17 = _src17.replace("pts = _densifier(pts, maxi * PAS_PLUME_EN_PLEINS)",
                         "pass  # densification retiree")
assert _faux17 != _src17, "le sabotage n'a rien remplacé -- il ne prouve rien"
_ns17 = dict(core.__dict__)
exec(compile(textwrap.dedent(_faux17), "<sabotage>", "exec"), _ns17)
_chs17 = _ns17["chaines_plume"]("hersheyscript1", _TXT17, largeur_mm=160.0,
                                angle_deg=50.0, epaisseur=0.16,
                                contraste=16.0, modele="pointue")[0]
_pires17 = max(_blocs_graves(
    core.generate_gcode_calligraphie(_chs17, 8.0, 600.0, u"Hêtre",
                                     power_max=900.0)))
assert _pires17 > 5.0, (
    "sans densification les blocs restent courts : le contrôle ci-dessus ne "
    "prouve pas que c'est elle qui les borne", _pires17)
print("17. plus aucun bloc gravé au-delà du pas : {:.2f} mm au pire (contre "
      "{:.2f} sans densification), fût du « d » à hauteur constante sur "
      "{:.1f} mm, voie extraction {:.2f} mm OK".format(
          _pire17, _pires17, _plat17, _pire_ext17))


# --- 18. LA LARGEUR DOIT SUIVRE LE SENS RÉELLEMENT GRAVÉ ----------------
# Christophe, 05/08/2026 : « en écriture un d commence par le cercle puis
# la barre verticale, et la barre verticale commence en haut ».
#
# La police enchaîne bien cercle puis hampe, mais elle trace la hampe VERS
# LE HAUT -- la remontée dans le jambage, celle qu'une main fait en filet
# avant de redescendre en plein. `sens_de_la_main` retournait ensuite le
# geste pour le graver de haut en bas, mais APRÈS que `_largeurs_du_trait`
# ait figé les largeurs : on gravait une descente en portant la largeur
# d'une montée, et la plume pointue n'appuyant qu'en descendant, les trois
# « d » recevaient 0,096 mm -- le trait le plus fin du texte là où la
# lettre demande son plein le plus visible.
#
# L'INVARIANT, et il est plus fort qu'une valeur : sur la plume,
# `sens_de_la_main` ne doit RIEN avoir à retourner. S'il retourne quoi que
# ce soit, c'est qu'un geste porte des largeurs mesurées à l'envers.
_ch18, _i18 = core.chaines_plume("hersheyscript1", _TXT17, largeur_mm=160.0,
                                 angle_deg=50.0, epaisseur=0.16,
                                 contraste=16.0, modele="pointue")
_g18, _d18 = core.preparer_calligraphie(_ch18, 600.0, u"Hêtre", power_max=900.0)
_retournes = sum(1 for g in _g18
                 if len(g) > 1 and core.sens_de_la_main(g)[0] is not g[0])
assert _retournes == 0, (
    "{} gestes sont encore retournés APRÈS coup : ceux-là portent la "
    "largeur du sens inverse de celui qu'on grave".format(_retournes))


def _futs_descendants(gestes):
    """Les longs runs droits et verticaux, avec la largeur qu'ils portent."""
    out = []
    for g in gestes:
        i = 0
        while i < len(g) - 1:
            j = i + 1
            a0 = math.atan2(g[i + 1].y - g[i].y, g[i + 1].x - g[i].x)
            while j < len(g) - 1:
                a1 = math.atan2(g[j + 1].y - g[j].y, g[j + 1].x - g[j].x)
                if abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi) > 0.035:
                    break
                j += 1
            dx, dy = g[j].x - g[i].x, g[j].y - g[i].y
            if math.hypot(dx, dy) > 5.0 and abs(dy) > abs(dx):
                # LA MÉDIANE, PAS LE MAXI : un fût est uniforme sur sa
                # longueur, et le maxi ne rapporte que la transition de ses
                # bouts -- assez pour que le sabotage rende 0,34 mm au lieu
                # du plancher et se fasse déclarer inoffensif.
                _w = sorted(p.w for p in g[i:j + 1])
                out.append((math.hypot(dx, dy), dy < 0.0, _w[len(_w) // 2]))
            i = j
    return out


_futs = _futs_descendants(_g18)
assert _futs, "aucun fût vertical de plus de 5 mm : le contrôle vise à côté"
assert all(desc for _L, desc, _w in _futs), (
    "un fût vertical est encore gravé en REMONTANT", _futs)
_wfut = min(w for _L, _d, w in _futs)
assert _wfut > 3.0 * _d18["w_min"], (
    "les hampes sortent au plancher matière ({:.3f} mm) alors qu'une "
    "descente demande un plein : c'est le « d » que Christophe a vu"
    .format(_wfut), _wfut, _d18["w_min"])

# SABOTAGE : on retire l'orientation faite à la construction, comme avant.
_src18 = inspect.getsource(core.chaines_plume)
_faux18 = _src18.replace("if not _sens_main_ok(", "if False and _sens_main_ok(")
assert _faux18 != _src18, "le sabotage n'a rien remplacé -- il ne prouve rien"
_ns18 = dict(core.__dict__)
exec(compile(textwrap.dedent(_faux18), "<sabotage>", "exec"), _ns18)
_chs18 = _ns18["chaines_plume"]("hersheyscript1", _TXT17, largeur_mm=160.0,
                                angle_deg=50.0, epaisseur=0.16,
                                contraste=16.0, modele="pointue")[0]
_gs18, _ds18 = core.preparer_calligraphie(_chs18, 600.0, u"Hêtre",
                                          power_max=900.0)
_gs18 = [core.sens_de_la_main(g) for g in _gs18]
_wsab = min(w for _L, _d, w in _futs_descendants(_gs18))
assert _wsab < 1.5 * _ds18["w_min"], (
    "sans l'orientation à la construction les hampes ne retombent PAS au "
    "plancher : le contrôle ci-dessus ne prouve pas que c'est elle qui les "
    "épaissit", _wsab, _ds18["w_min"])
print("18. la largeur suit le sens gravé : 0 geste à retourner, hampes à "
      "{:.3f} mm contre {:.3f} au plancher sans le correctif OK".format(
          _wfut, _wsab))


# --- 19. LE PLEIN DE LA PANSE TOMBE À GAUCHE ----------------------------
# Christophe, 05/08/2026, la hampe enfin bonne : « j'aurais commencé le
# cercle du d en haut à droite à environ 30 degrés et parti dans le sens
# anti-horaire [...] là c'est bien mais du coup le cercle du d est très fin
# du début à la fin ».
#
# C'est exactement ce que la police fait -- et c'est nous qui le défaisions.
# Le « d » est DEUX mouvements de plume dans UNE polyligne : panse en
# anti-horaire, puis hampe vers le haut. `_sens_main_ok` ne lit que les deux
# bouts, donc la hampe -- de loin le plus long segment -- décidait pour tout
# le monde et retournait la panse avec elle. Le plein de la panse basculait
# alors à DROITE, écrasé contre la hampe, et la grande courbe de gauche,
# celle qu'on voit le plus, tombait au minimum absolu du texte.
_ch19, _i19 = core.chaines_plume("hersheyscript1", _TXT17, largeur_mm=160.0,
                                 angle_deg=50.0, epaisseur=0.16,
                                 contraste=16.0, modele="pointue")


def _panse_du_d(chaines):
    """(médiane à gauche, médiane à droite) de la panse du 1er « d »."""
    pts = [p for c in chaines for p in c if p[1] < 5.0 and 39.0 < p[0] < 45.6]
    assert pts, "la panse du « d » est introuvable : le contrôle vise à côté"
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    g, d = [], []
    for p in pts:
        a = math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360
        if 135.0 <= a < 225.0:
            g.append(p[2])
        elif a >= 315.0 or a < 45.0:
            d.append(p[2])
    g.sort(), d.sort()
    return (g[len(g) // 2] if g else 0.0), (d[len(d) // 2] if d else 0.0)


_gau19, _dro19 = _panse_du_d(_ch19)
assert _gau19 > _dro19, (
    "le plein de la panse est à DROITE : la panse est parcourue à l'envers, "
    "son plein s'écrase contre la hampe et la courbe de gauche sort en "
    "filet", _gau19, _dro19)
assert _gau19 > 5.0 * _i19["largeur_trait_min"], (
    "la courbe de gauche du « d » est au filet ({:.3f} mm pour un délié de "
    "{:.3f}) : c'est « le cercle est très fin du début à la fin »"
    .format(_gau19, _i19["largeur_trait_min"]), _gau19)

# SABOTAGE : on désarme la coupure, comme en v2.87.0.
_src19 = inspect.getsource(core.chaines_plume)
_faux19 = _src19.replace("_couper_queue_contrariante(", "(lambda p, m: [p])(")
assert _faux19 != _src19, "le sabotage n'a rien remplacé -- il ne prouve rien"
_ns19 = dict(core.__dict__)
exec(compile(textwrap.dedent(_faux19), "<sabotage>", "exec"), _ns19)
_chs19 = _ns19["chaines_plume"]("hersheyscript1", _TXT17, largeur_mm=160.0,
                                angle_deg=50.0, epaisseur=0.16,
                                contraste=16.0, modele="pointue")[0]
_gs19, _ds19 = _panse_du_d(_chs19)
assert _gs19 < 2.0 * _i19["largeur_trait_min"], (
    "sans la coupure la panse garde son plein à gauche : le contrôle "
    "ci-dessus ne prouve pas que c'est elle qui le remet là", _gs19)
print("19. le plein de la panse est à gauche : {:.3f} mm contre {:.3f} à "
      "droite, et {:.3f} au filet sans la coupure OK".format(
          _gau19, _dro19, _gs19))


# --- 20. ARRONDIR LES COURBES, JAMAIS LES COINS -------------------------
# Christophe, 05/08/2026, photo d'une vraie calligraphie à l'appui : « c'est
# presque bon, voici un exemple concret que j'aurais dû te donner ». Son
# exemple a des courbes ; le nôtre avait des facettes -- `hersheyscript1` ne
# donne que 22 sommets pour tout le « d », et la densification n'y change
# rien (subdiviser une droite ne donne que des droites).
_ch20, _i20 = core.chaines_plume("hersheyscript1", "d", largeur_mm=40.0,
                                 angle_deg=50.0, epaisseur=0.12,
                                 contraste=5.0, modele="pointue")


def _pire_virage(chaines, ymax):
    """Le plus grand changement de direction, en degrés, sous `ymax` --
    c'est-à-dire dans la PANSE, hors raccord de la hampe qui est un vrai
    coin et doit le rester."""
    pire = 0.0
    for c in chaines:
        bas = [p for p in c if p[1] < ymax]
        for a, b, d in zip(bas, bas[1:], bas[2:]):
            a0 = math.atan2(b[1] - a[1], b[0] - a[0])
            a1 = math.atan2(d[1] - b[1], d[0] - b[0])
            pire = max(pire, abs(math.degrees(
                (a1 - a0 + math.pi) % (2 * math.pi) - math.pi)))
    return pire


_ymax20 = 0.45 * max(p[1] for c in _ch20 for p in c)
_virage20 = _pire_virage(_ch20, _ymax20)
assert _virage20 < 12.0, (
    "la panse tourne par à-coups de {:.0f}° : elle sortira en polygone, pas "
    "en courbe".format(_virage20), _virage20)


def _ecart_a_la_police(lettre, seuil_deg=None):
    """De combien le tracé produit s'éloigne-t-il de la polyligne de la
    police, en % de capitale ? Le lissage passe PAR les sommets ; ce qu'on
    mesure ici, c'est le ventre qu'il fait ENTRE eux."""
    hf = core._hershey_module("hersheyscript1")
    brut = [t for t in hf.GLYPHES[lettre][1] if len(t) >= 2]
    pire = 0.0
    for t in brut:
        p = [(q[0], q[1]) for q in t]
        lisse = (core._lisser_polyligne(p) if seuil_deg is None
                 else core._lisser_polyligne(p, seuil_deg))
        for q in lisse:
            d = min(_dist_seg(q, a, b) for a, b in zip(p, p[1:]))
            pire = max(pire, d)
    return 100.0 * pire / float(hf.CAP_HEIGHT)


def _dist_seg(p, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    l2 = vx * vx + vy * vy
    if l2 < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    u = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2))
    return math.hypot(p[0] - a[0] - u * vx, p[1] - a[1] - u * vy)


# UN VRAI COIN NE DOIT PAS SE CINTRER. Le « 4 » et le « A » sont les deux
# glyphes les plus anguleux du jeu courant : sans garde-fou ils se
# bombaient de 4,86 et 3,14 % de capitale, soit 0,49 et 0,31 mm sur un
# texte de 160 mm -- parfaitement visibles.
for _lettre in ("4", "A"):
    _e = _ecart_a_la_police(_lettre)
    assert _e < 1.5, (
        "le « {} » s'écarte de {:.2f} % de capitale du dessin de la police : "
        "la spline lui arrondit un angle qui EST le dessin".format(_lettre, _e),
        _e)

# SABOTAGE : on désarme le garde-angle, la spline lisse tout.
_e4 = _ecart_a_la_police("4", 999.0)
assert _e4 > 3.0, (
    "sans garde-angle le « 4 » ne se cintre pas davantage : le contrôle "
    "ci-dessus ne prouve pas que c'est le garde qui protège les coins", _e4)
print("20. panse lissée (virage maxi {:.1f}°) et coins préservés : le « 4 » "
      "s'écarte de {:.2f} % de capitale contre {:.2f} sans garde-angle OK"
      .format(_virage20, _ecart_a_la_police("4"), _e4))


# --- 21. LA PLUME SE PENCHE DANS LES DEUX SENS --------------------------
# Christophe, 05/08/2026, une police calligraphique en référence : « regarde
# le d de cette fonte, le tien le trait épais est en bas, là il est sur la
# gauche ».
#
# Le modèle savait le faire depuis toujours -- `largeur_plume` calcule
# abs(sin(theta - angle)), de période 180°, donc -40° est un réglage à part
# entière et NON le symétrique de +40°. C'est le CHAMP qui était borné à
# 0-90 : la moitié des inclinaisons était inatteignable.
sans_dialogues()
_p21 = tp.TaskPanelCalligraphie()
_lo21, _hi21 = _p21.spn_plume_angle.minimum(), _p21.spn_plume_angle.maximum()
assert _lo21 <= -40.0, (
    "le champ d'angle n'atteint pas les inclinaisons négatives : la moitié "
    "des plumes reste hors de portée", _lo21, _hi21)
_p21.spn_plume_angle.setValue(-40.0)
assert abs(_p21.spn_plume_angle.value() + 40.0) < 1e-9, (
    "le champ refuse -40° alors que sa plage l'annonce",
    _p21.spn_plume_angle.value())


def _bas_sur_gauche(angle):
    """Rapport épaisseur du BAS-GAUCHE / épaisseur de la GAUCHE sur la panse
    du « d ». Une vraie calligraphie place son plein à gauche et allège le
    bas, donc ce rapport doit être PETIT.

    LE SECTEUR EST CHOISI PARCE QU'IL SÉPARE. Mesuré à -40° contre +50° :
    bas-gauche 0,36 contre 0,78, bas-droite 0,33 contre 0,55, mais le BAS
    franc 0,24 contre 0,28 -- quatre centièmes, de quoi faire passer le
    contrôle sous n'importe quel code. La police de référence de Christophe
    est à 0,22 sur ce même secteur."""
    ch, _i = core.chaines_plume("hersheyscript1", "d", largeur_mm=40.0,
                                angle_deg=float(angle), epaisseur=0.12,
                                contraste=5.0, modele="pointue")
    ys = [p[1] for c in ch for p in c]
    pts = [p for c in ch for p in c if p[1] < min(ys) + 0.55 * (max(ys) - min(ys))]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    bas, gau = [], []
    for p in pts:
        a = math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360
        if 202.5 <= a < 247.5:
            bas.append(p[2])
        elif 157.5 <= a < 202.5:
            gau.append(p[2])
    bas.sort(), gau.sort()
    return (bas[len(bas) // 2] / gau[len(gau) // 2]) if bas and gau else 0.0


_neg21, _pos21 = _bas_sur_gauche(-40.0), _bas_sur_gauche(50.0)
assert _neg21 < _pos21, (
    "pencher la plume dans l'autre sens ne déplace pas le plein : le champ "
    "élargi n'apporterait rien", _neg21, _pos21)
assert _neg21 < 0.5 and _pos21 > 0.6, (
    "le bas-gauche de la panse ne s'allège pas comme sur une vraie "
    "calligraphie (référence mesurée : 0,22)", _neg21, _pos21)
print("21. la plume se penche des deux côtés ({:.0f}° à {:.0f}°) : "
      "bas-gauche/gauche de la panse {:.2f} à -40° contre {:.2f} à +50° OK".format(
          _lo21, _hi21, _neg21, _pos21))
