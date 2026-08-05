# -*- coding: utf-8 -*-
"""La bande de tons du nuancier, calée sur le matériau et non sur le hêtre.

Christophe, 04/08/2026, photo d'une planche de sapin à l'appui : « je suis
en train de faire le sapin et je vois que c'est plus dur à graver. Les
réglages qui fonctionnaient sur le hêtre ne gravent quasiment pas sur le
sapin, peut-être que pour graver une grille il faut se baser sur les
résultats des traits faits dans les planches 1 2 2b ? »

Oui. L'objectif gravait les MÊMES nombres pour tous les matériaux -- S200 →
S1000 à F2000, défocus 15 -- et ces nombres sont du hêtre. Sur hêtre ils
gaspillaient déjà trois cases sur dix (le nuancier de l'atelier en garde la
trace : S195 → 0, S235 → 0, S275 → 2). Sur sapin, rien n'est exploitable en
dessous de ~S700 -- six ou sept cases sur dix, donc une planche entière
gravée pour trois ou quatre tons, dont le plus fort est un pâté.

LES CONTRÔLES PORTENT SUR DES MATÉRIAUX FABRIQUÉS ICI, pas sur le hêtre et
le sapin de l'atelier. La règle de la maison : un contrôle ne doit pas
rougir parce que Christophe a MESURÉ. Ses vraies données sont lues à la fin,
et seulement AFFICHÉES -- une divergence y est une information sur les
mesures, pas un défaut du code.
"""
import inspect
import sys

from harness import preparer, sans_dialogues, texte
from PySide6 import QtWidgets                              # noqa: E402

h = preparer()
core = h.core
tp = h.tp

DUR = "ZZ-Bois-dur-de-test"
TENDRE = "ZZ-Bois-tendre-de-test"
PUISSANCES = (200.0, 400.0, 600.0, 800.0, 1000.0)


def _semer():
    """Deux matériaux fictifs, dont les cases VIDES sont le sujet.

    Le dur marque partout jusqu'à F2000. Le tendre n'a rien laissé au-delà
    de F800, et à F800 rien en dessous de S400 -- exactement la forme des
    planches du sapin, où les cases manquantes sont toutes dans le coin le
    moins énergique."""
    dur = [{"power": s, "feed": f, "z_offset": 15.0, "width": 0.5}
           for s in PUISSANCES for f in (200.0, 400.0, 800.0, 2000.0)]
    tendre = [{"power": s, "feed": f, "z_offset": 15.0, "width": 0.5}
              for s in PUISSANCES for f in (200.0, 400.0, 800.0)
              # le coin sans trace : S200 s'arrête après F400
              if not (s <= 200.0 and f >= 600.0)
              and not (s <= 300.0 and f >= 800.0)]
    core.save_burn_widths(DUR, {"focus": [], "defocus": dur})
    core.save_burn_widths(TENDRE, {"focus": [], "defocus": tendre})


_semer()


# --- 1. LA RÈGLE DU MÉLANGE, ET ELLE DOIT REDONNER LA LISTE LIVRÉE -----
# Les dix puissances étaient une liste écrite à la main. Elle est maintenant
# calculée, parce que la bande n'a plus toujours dix cases ni le même
# plancher -- mais le désordre était un CHOIX (rangées par ordre croissant,
# les cases se jugent les unes par rapport aux autres et l'oeil fabrique une
# progression qui n'existe pas). Le remplacer par une règle qui ne le
# reproduit pas, ce serait le perdre sans s'en apercevoir.
_LIVREE = [200.0, 644.0, 378.0, 822.0, 556.0, 1000.0, 289.0, 733.0, 467.0, 911.0]
_calc = core.puissances_bande_tons(200.0, 1000.0, 10)
assert _calc == _LIVREE, ("la règle ne reproduit plus la série livrée", _calc)
for _n in (2, 3, 5, 7, 10, 12, 16):
    _o = core.ordre_melange(_n)
    assert sorted(_o) == list(range(_n)), ("ordre_melange n'est pas une "
                                           "permutation", _n, _o)
    # Aucune case voisine dans la RAMPE ne doit être voisine sur la
    # PLANCHE : c'est tout ce que le mélange achète. La règle ne le garantit
    # qu'à partir de n=8 (cf. sa docstring) ; la bande en grave dix, donc le
    # contrôle porte là où la garantie est revendiquée -- ni plus, pour ne
    # pas exiger ce que le code annonce ne pas tenir, ni moins, pour que la
    # série livrée soit couverte.
    if _n >= 8:
        _cotes = [abs(_o[i + 1] - _o[i]) for i in range(_n - 1)]
        assert min(_cotes) > 1, ("deux cases consécutives de la rampe sont "
                                 "gravées côte à côte", _n, _o)
    elif _n >= 4:
        # En dessous de 8 on n'exige que « ce n'est pas la rampe telle
        # quelle ». n ≤ 3 est exclu parce qu'aucune permutation de trois
        # rangs n'évite deux voisins : ce n'est pas une tolérance, c'est
        # l'arithmétique.
        assert _o != list(range(_n)), ("série courte laissée dans l'ordre "
                                       "croissant", _n, _o)
print("1. règle du mélange : série livrée reproduite, permutation valide "
      "jusqu'à n=16, jamais deux rangs voisins côte à côte OK")


# --- 2. LE PLANCHER VIENT DES CASES VIDES ------------------------------
_f, _p, _dire = core.regime_bande_tons(TENDRE, 2000.0, 15.0, n=10)
assert core.puissance_mini_qui_marque(TENDRE, 800.0, 15.0) == 400.0, (
    "le plancher du bois tendre à F800 n'est pas S400",
    core.puissance_mini_qui_marque(TENDRE, 800.0, 15.0))
assert min(_p) == 400.0, ("la bande descend sous le plancher : ces cases "
                          "sortiront vierges", sorted(_p))
assert max(_p) == 1000.0, ("la bande n'atteint plus le noir", sorted(_p))
assert len(_p) == 10, ("la bande a perdu des cases", len(_p))
print("2. bois tendre : plancher S400 tiré des cases vides, bande "
      "S400→S1000 sur 10 cases OK")


# --- 3. LA VITESSE NE SORT PAS DE CE QU'ON A OBSERVÉ --------------------
# Graver à une vitesse jamais vue, c'est parier -- et le sapin a perdu le
# pari sur sept cases. Le modèle de largeur, lui, ne prévient pas : il BORNE
# en vitesse et rend celle de F800 pour F2000, au centième près.
assert _f == 800.0, ("la vitesse n'a pas été ramenée dans la plage observée",
                     _f)
assert core.vitesse_maxi_mesuree(TENDRE, 15.0) == 800.0
assert "F2000" in (_dire or "") and "F800" in (_dire or ""), (
    "l'explication ne nomme pas les deux vitesses", _dire)
_f_dur, _p_dur, _dire_dur = core.regime_bande_tons(DUR, 2000.0, 15.0, n=10)
assert _f_dur == 2000.0, ("le bois dur est mesuré à F2000 : rien à ramener",
                          _f_dur)
assert _dire_dur is None, ("rien n'a changé, il ne faut donc rien dire",
                           _dire_dur)
print("3. tendre F2000→F800 avec l'explication ; dur laissé à F2000, muet OK")


# --- 4. UN TON JUGÉ ROUVRE LA VITESSE ----------------------------------
# Sinon la boucle ne se referme jamais : une largeur en défocus ne se mesure
# qu'aux vitesses lentes des planches (F800 au plus), donc une bande de
# repérage rapportée en ② n'aurait rien changé et l'objectif aurait rabattu
# à F800 pour l'éternité. Un ton NUL ne rouvre rien -- c'est la preuve du
# contraire.
core.save_shades(TENDRE, [
    {"power": 300.0, "feed": 2000.0, "z_offset": 15.0, "width": 0.8,
     "darkness": 0.0},
    {"power": 900.0, "feed": 2000.0, "z_offset": 15.0, "width": 0.8,
     "darkness": 55.0}])
_f2, _p2, _dire2 = core.regime_bande_tons(TENDRE, 2000.0, 15.0, n=10)
assert _f2 == 2000.0, ("un ton jugé à F2000 prouve que le régime marque : "
                       "la vitesse ne devait plus être rabattue", _f2)
assert min(_p2) == 900.0, ("le plancher devait venir du ton jugé, pas des "
                           "largeurs", sorted(_p2))
core.save_shades(TENDRE, [
    {"power": 300.0, "feed": 2000.0, "z_offset": 15.0, "width": 0.8,
     "darkness": 0.0}])
_f3, _p3, _dire3 = core.regime_bande_tons(TENDRE, 2000.0, 15.0, n=10)
assert _f3 == 800.0, ("un ton jugé à 0 est la preuve que le bois est resté "
                      "intact : il ne doit RIEN rouvrir", _f3)
core.save_shades(TENDRE, [])
print("4. un ton jugé > 0 rouvre la vitesse et donne le plancher ; un ton "
      "à 0 ne rouvre rien OK")


# --- 5. MATÉRIAU JAMAIS MESURÉ : ON NE TOUCHE À RIEN, ET ON LE DIT -----
_f4, _p4, _dire4 = core.regime_bande_tons("ZZ-jamais-vu", 2000.0, 15.0, n=10)
assert _f4 == 2000.0 and _p4 == _LIVREE, (
    "sans mesure, il n'y a rien à recaler", _f4, sorted(_p4))
assert _dire4 and "REPÉRAGE" in _dire4, (
    "il faut dire que cette planche-là est un repérage, sinon l'atelier "
    "promet une bande de tons et rend des cases vierges", _dire4)
print("5. matériau jamais mesuré : bande inchangée, annoncée comme un "
      "repérage OK")


# --- 6. LE PANNEAU L'APPLIQUE VRAIMENT ---------------------------------
# La règle de la maison : on éprouve le chemin que Christophe CLIQUE, pas
# les fonctions autour. Le bouton Générer de ce même panneau a été livré
# cassé le 01/08/2026 alors que ses helpers marchaient.
sans_dialogues()
_pan = tp.TaskPanelTestGrid()
_idx = next(i for i in range(_pan.combo_recipe.count())
            if _pan.combo_recipe.itemData(i) == "noirceur_balayage")


def _choisir_materiau(nom):
    """Prendre le matériau DANS LA LISTE, comme Christophe le fait.

    `setCurrentText` sur une combo éditable se contente d'écrire dans la
    ligne de saisie : aucun signal, donc aucun recalage. Un contrôle bâti
    dessus aurait montré une bande figée sur le matériau précédent et
    conclu au défaut -- ou, le correctif venu, aurait continué de passer
    sans jamais rien éprouver."""
    i = _pan.edt_measure_mat.findText(nom)
    assert i >= 0, ("le matériau de test n'est pas dans la liste du "
                    "panneau", nom)
    _pan.edt_measure_mat.setCurrentIndex(i)


_choisir_materiau(TENDRE)
_pan.combo_recipe.setCurrentIndex(_idx)
assert _pan.spn_feed_min.value() == 800.0, (
    "le panneau grave encore à la vitesse du hêtre", _pan.spn_feed_min.value())
assert _pan.spn_power_min.value() == 400.0, (
    "le panneau grave encore sous le plancher du matériau",
    _pan.spn_power_min.value())
_note = texte(_pan.lbl_recipe_note)
assert "TES planches" in _note, ("la note ne dit pas que la bande a été "
                                 "recalée", _note[:160])

# Et il SUIT le matériau : le changer doit tout recaler.
_choisir_materiau(DUR)
assert _pan.spn_feed_min.value() == 2000.0, (
    "changer de matériau n'a pas recalé la bande : elle reste sur le "
    "précédent en affichant le nom du nouveau", _pan.spn_feed_min.value())
assert _pan.spn_power_min.value() == 200.0, _pan.spn_power_min.value()
print("6. le panneau applique le recalage et SUIT le matériau choisi OK")


# --- 7. LE MATÉRIAU SE CHOISIT EN ①, LÀ OÙ IL SERT --------------------
# Christophe, 04/08/2026, après la livraison : « je ne vois pas ta bande
# 800, dis moi exactement où il se trouve ». Elle était bien là -- calée sur
# le HÊTRE, parce que le panneau s'ouvre sur le premier matériau de la liste
# et que le seul endroit où en changer était « Matériau mesuré », dans ②,
# plusieurs écrans plus bas. Un réglage qui gouverne ① ne peut pas vivre
# uniquement dans ②.
#
# Une seule valeur, deux vues : elles doivent se suivre DANS LES DEUX SENS,
# sans quoi la bande se calerait sur un matériau que le panneau n'affiche
# plus.
assert hasattr(_pan, "combo_mat_objectif"), (
    "il n'y a pas de champ matériau en ① : il faut descendre en ② pour "
    "changer ce qui gouverne la bande")
assert _pan.combo_mat_objectif.currentText() == DUR, (
    "le champ de ① n'a pas suivi le choix fait en ②",
    _pan.combo_mat_objectif.currentText())

_i = _pan.combo_mat_objectif.findText(TENDRE)
assert _i >= 0, "le matériau de test manque à la liste de ①"
_pan.combo_mat_objectif.setCurrentIndex(_i)
assert _pan.edt_measure_mat.currentText() == TENDRE, (
    "le champ de ② n'a pas suivi le choix fait en ① : les mesures se "
    "rangeraient sous un autre matériau que celui qu'on grave",
    _pan.edt_measure_mat.currentText())
assert _pan.spn_feed_min.value() == 800.0, (
    "changer le matériau en ① n'a pas recalé la bande",
    _pan.spn_feed_min.value())
assert "materiau" in _pan._last_fields, (
    "le matériau n'est pas retenu d'une session à l'autre : le panneau "
    "rouvrira sur le premier de la liste")
print("7. matériau choisi en ①, les deux champs se suivent dans les deux "
      "sens, retenu d'une session à l'autre OK")


# --- 8. LES VRAIES DONNÉES DE L'ATELIER : on AFFICHE, on n'exige pas ---
# Elles bougent à chaque planche gravée. Un contrôle qui rougit parce que
# Christophe a mesuré est pire que pas de contrôle du tout.
print("8. sur les mesures réelles de l'atelier (informatif) :")
for _mat in core.burn_width_materials():
    if _mat.startswith("ZZ-"):
        continue
    _fr, _pr, _dr = core.regime_bande_tons(_mat, 2000.0, 15.0, n=10)
    print("   {:<10} F{:.0f}  S{:.0f}→S{:.0f}   {}".format(
        _mat, _fr, min(_pr), max(_pr),
        "(inchangé)" if not _dr else _dr[:100] + "…"))


# --- 9. LE PAS S'ÉLARGIT QUAND LA BANDE SATURE ---------------------------
# Christophe, planche de sapin en main, 05/08/2026 : « pour le sapin, tout
# est à peu près au même ton ». Dix cases, dix fois le même brun.
#
# On ne mesure PAS sur les données de l'atelier ici : elles bougent à chaque
# planche gravée, et un contrôle qui rougit parce qu'il a mesuré est pire
# que pas de contrôle. On pose des largeurs choisies et on vérifie la
# PROPRIÉTÉ, ce qui laisse le sabotage possible.
_vrai_largeur = core.burn_width_defocus_scaled


def _largeurs_fixes(valeurs):
    """Remplace le modèle de largeur par une liste, une par puissance."""
    _table = {}

    def _faux(power, feed, defocus, material=None):
        return _table.get(round(float(power), 3))

    return _faux, _table


core.burn_width_defocus_scaled, _table = _largeurs_fixes(None)
try:
    # a) SATURÉE : au pas de 0,80 la plus foncée couvre 120 %.
    _puis = [200.0, 400.0, 600.0, 800.0]
    for _s, _w in zip(_puis, (0.64, 0.78, 0.90, 0.96)):
        _table[_s] = _w
    _pas, _dire = core.pas_bande_tons("Bois", 800.0, 15.0, _puis, 0.80)
    assert _pas > 0.80, (
        "la bande sature (couverture 80 à 120 %) et le pas n'a pas bougé : "
        "les dix cases se recouvrent toutes et rendront le même ton", _pas)
    assert abs(0.96 / _pas - core.COUVERTURE_CIBLE) < 1e-6, (
        "la case la plus foncée ne tombe pas sur la couverture visée",
        0.96 / _pas)
    assert 0.64 / _pas < 0.75, (
        "la case la plus claire reste trop couverte : ce n'est toujours pas "
        "une échelle de tons", 0.64 / _pas)
    assert _dire and "0.80" in _dire, (
        "l'élargissement est silencieux : le panneau ne pourra pas dire "
        "pourquoi le pas n'est plus celui qu'on a demandé", _dire)

    # b) SAINE : le hêtre à F2000 va de 50 à 62 %, on n'y touche pas.
    for _s, _w in zip(_puis, (0.40, 0.45, 0.48, 0.50)):
        _table[_s] = _w
    _pas2, _dire2 = core.pas_bande_tons("Bois", 2000.0, 15.0, _puis, 0.80)
    assert _pas2 == 0.80 and _dire2 is None, (
        "une bande qui FONCTIONNE a été élargie : son ton vient de la "
        "noirceur du trait, pas du recouvrement", _pas2, _dire2)

    # c) SABOTAGE : le critère porté sur la case la plus CLAIRE -- la
    # première version, celle que la planche de sapin a condamnée.
    for _s, _w in zip(_puis, (0.64, 0.78, 0.90, 0.96)):
        _table[_s] = _w
    _src = inspect.getsource(core.pas_bande_tons)
    assert "max(ws) / max(pas_actuel" in _src, (
        "le critère de saturation ne porte plus sur la case la plus foncée "
        "-- c'est exactement la version que le sapin a réfutée")
    _faux_src = _src.replace("max(ws) / max(pas_actuel",
                             "min(ws) / max(pas_actuel")
    _ns = dict(core.__dict__)
    exec(compile(_faux_src, "<sabotage>", "exec"), _ns)
    _pas3, _ = _ns["pas_bande_tons"]("Bois", 800.0, 15.0, _puis, 0.80)
    assert _pas3 == 0.80, (
        "le sabotage ne change rien : le contrôle ci-dessus ne prouve pas "
        "que c'est bien la case la plus foncée qui décide", _pas3)
finally:
    core.burn_width_defocus_scaled = _vrai_largeur
print("9. le pas s'élargit quand la bande sature, pas quand elle marche, "
      "et c'est la case la plus FONCÉE qui décide OK")
