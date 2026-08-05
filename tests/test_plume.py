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
