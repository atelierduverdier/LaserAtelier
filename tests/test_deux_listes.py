# -*- coding: utf-8 -*-
"""DEUX LISTES POUR UNE MÊME QUESTION, sur tout le fichier des panneaux.

Trouvé à la lecture ligne à ligne du 02/09/2026. Le défaut n'est jamais
« ce code est faux » : ce sont deux endroits qui répondent à la MÊME
question, d'accord le jour où on les écrit, et qui divergent au premier
ajout. `task_panels.py` en portait cinq familles, et chacune coûtait
quelque chose de mesurable :

* le préréglage nommé d'un panneau contre sa mémorisation de session ;
* le magasin de préréglages d'un panneau contre celui d'un autre ;
* les champs rechargés en changeant de laser contre `PER_LASER_KEYS` ;
* la bande de noirceur du sélecteur contre celle de la planche gravée ;
* la grille qui AFFICHE une mesure contre celle qui la POSSÈDE.

Ce fichier ne teste donc pas des valeurs mais des ACCORDS : chaque
propriété est vraie tant que les deux sources n'en font qu'une.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import preparer

h = preparer()
core, tp = h.core, h.tp
from PySide6 import QtWidgets                                    # noqa: E402

QtWidgets.QInputDialog.getText = staticmethod(lambda *a, **k: ("Essai", True))
QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.critical = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)


def _panneau(nom):
    cls = getattr(tp, nom)
    return (cls([]) if "selection" in cls.__init__.__code__.co_varnames
            else cls())


# ==========================================================================
# 1. UN PRÉRÉGLAGE NOMMÉ PORTE TOUT CE QUE LA SESSION RETIENT
# ==========================================================================
# Le bouton promet « les valeurs actuelles de TOUT le panneau ». Les cinq
# panneaux tenaient pourtant DEUX listes -- `_last_fields` et un dict
# recopié à la main -- et la seconde avait pris du retard partout :
#
#   Gravure remplie : dégradé (case, S de fin, direction) + décalage de
#                     surface -- 4 sur 25 ;
#   Grille de test  : style de trait, mire de mesure, matériau visé ;
#   Marquage        : décalage de surface + les deux champs du « ton sur
#                     mesure », deux valeurs cherchées à l'oeil ;
#   Découpe à plat  : trous d'abord, proximité, Z de départ forcé et les
#                     QUATRE champs des copies en matrice -- 8 sur 21, et
#                     les copies décident du NOMBRE de pièces débitées ;
#   Découpe courbe  : trous d'abord et proximité.
_CATEGORIES = (("TaskPanelFilledEngraving", "filled"),
               ("TaskPanelTestGrid", "testgrid"),
               ("TaskPanelCurved", "curved"),
               ("TaskPanelFlat", "flat"),
               ("TaskPanelCurvedCut", "curved_cut"))
for _nom, _cat in _CATEGORIES:
    _p = _panneau(_nom)
    core.delete_preset(_cat, "Essai")
    _p._on_save_preset()
    _enregistre = core.load_presets(_cat).get("Essai") or {}
    _manque = sorted(set(_p._last_fields) - set(_enregistre))
    assert not _manque, (
        "{} : {} réglage(s) mémorisé(s) en session mais ABSENT(S) du "
        "préréglage nommé : {}".format(_nom, len(_manque), _manque))
print("1. les {} panneaux à préréglage enregistrent TOUT ce que la session "
      "retient OK".format(len(_CATEGORIES)))

# ==========================================================================
# 2. CHAQUE PANNEAU SON MAGASIN DE PRÉRÉGLAGES
# ==========================================================================
# « Texte gravé » (3 champs) et « Calligraphie » (13, dont six pour la
# seule plume) écrivaient dans la MÊME catégorie. Mesuré : une recette de
# plume enregistrée sous « Ma plume » tombait de 13 champs à 3 dès qu'on
# enregistrait sous ce nom depuis l'autre panneau -- `save_preset`
# remplace. Dix réglages trouvés à l'œil, effacés sans un mot.
_cal = tp.TaskPanelCalligraphie()
_tc = tp.TaskPanelTexteContour()
assert _cal._presets.category != _tc._presets.category, (
    "Calligraphie et Texte gravé partagent le magasin « {} » : le second "
    "a {} champs, le premier {}".format(
        _cal._presets.category, len(_tc._last_fields), len(_cal._last_fields)))
core.save_preset(_cal._presets.category, "Ma plume",
                 {k: tp._widget_get(w) for k, w in _cal._last_fields.items()})
core.save_preset(_tc._presets.category, "Ma plume",
                 {k: tp._widget_get(w) for k, w in _tc._last_fields.items()})
assert len(core.load_presets(_cal._presets.category)["Ma plume"]) == \
    len(_cal._last_fields), (
        "la recette de plume a été rognée par l'autre panneau")
print("2. Calligraphie ({} champs) et Texte gravé ({}) ont des magasins "
      "SÉPARÉS OK".format(len(_cal._last_fields), len(_tc._last_fields)))

# ==========================================================================
# 3. CHANGER DE LASER NE DOIT PAS ÉCRASER LE PROFIL DU SUIVANT
# ==========================================================================
# `_reload_active_laser_fields` tenait sa liste à la main : neuf champs
# rechargés sur les seize de `core.PER_LASER_KEYS`. Basculer de laser
# puis valider écrasait donc le profil du second par les valeurs du
# premier -- surface de travail 400 -> 1200 mm (le garde-fou croit alors
# à une grande table sur une petite machine), « sans axe Z » décoché (des
# mots Z sur une machine qui n'en a pas), air M8 -> M7 (la sortie qui
# n'est pas câblée), étiquettes S300 -> S600.
core.ensure_laser_profiles()
_a = core.active_laser_id()
core.save_settings({"surface_travail_x_mm": 1200.0,
                    "machine_sans_axe_z": False,
                    "assistance_air": "M7", "label_power": 600.0})
_b = core.add_laser("EssaiPetiteTable", clone_from=_a)
core.set_active_laser(_b)
core.save_settings({"surface_travail_x_mm": 400.0,
                    "machine_sans_axe_z": True,
                    "assistance_air": "M8", "label_power": 300.0})


def _profil(lid):
    core.set_active_laser(lid)
    s = core.current_settings()
    return (s["surface_travail_x_mm"], s["machine_sans_axe_z"],
            s["assistance_air"], s["label_power"])


_attendu_b = _profil(_b)
core.set_active_laser(_a)
_prefs = tp.TaskPanelSettings()
_prefs.combo_laser.setCurrentIndex(_prefs.combo_laser.findData(_b))
_prefs.accept()
assert _profil(_b) == _attendu_b, (
    "basculer de laser puis valider a écrasé le profil : {} au lieu de {}"
    .format(_profil(_b), _attendu_b))
# ET LA CARTE COUVRE LA LISTE DU NOYAU : une clé ajoutée là-bas ne peut
# plus être oubliée ici sans qu'on le voie.
_sans_widget = {"mire_power", "mire_feed"}
_oubliees = sorted(set(core.PER_LASER_KEYS) - set(_prefs._champs_laser)
                   - _sans_widget)
assert not _oubliees, (
    "clé(s) de PER_LASER_KEYS sans champ dans les Préférences : {}"
    .format(_oubliees))
core.set_active_laser(_a)
print("3. changer de laser garde le profil du suivant intact ; les {} clés "
      "de PER_LASER_KEYS ont toutes leur champ OK".format(
          len(core.PER_LASER_KEYS) - len(_sans_widget)))

# ==========================================================================
# 4. LE SÉLECTEUR, LE COMPTE ANNONCÉ ET LA PLANCHE DÉCOUPENT PAREIL
# ==========================================================================
# La règle des bandes de noirceur existait en TROIS exemplaires : le
# classement du sélecteur (`valeur < borne`), le filtre de gravure et le
# compte annoncé dans la liste (tous deux `lo < valeur <= hi`). Tout ton
# posé exactement sur une borne descendait donc d'une bande sur le bois :
# annoncé « Noir (90-100 %) » dans le sélecteur, gravé sur la planche
# « Foncé (60-90 %) », et absent de la planche « Noir ». Le nuancier de
# l'atelier en compte un, le hêtre S845 à 90 %.
core.save_shades(u"EssaiBandes", [
    {"power": 300.0, "feed": 800.0, "z_offset": 15.0, "width": 0.8,
     "darkness": 20.0},
    {"power": 600.0, "feed": 800.0, "z_offset": 15.0, "width": 0.9,
     "darkness": 60.0},
    {"power": 845.0, "feed": 800.0, "z_offset": 15.0, "width": 1.0,
     "darkness": 90.0},
    {"power": 1000.0, "feed": 800.0, "z_offset": 15.0, "width": 1.1,
     "darkness": 97.0},
])
_titres = [t for _b, t in core._BANDES_NOIRCEUR]
_selecteur = {t: {int(r["darkness"]) for r in e if r["darkness"] is not None}
              for t, e in core.grouper_reglages(
                  core.reglages_disponibles(u"EssaiBandes"), "noirceur")}
_nuancier = tp.TaskPanelNuancier()
_nuancier.combo_mat.setCurrentText(u"EssaiBandes")
_nuancier._maj_bandes_nuancier()
for _i, _titre in enumerate(_titres):
    _items, _err = tp._nuancier_items("tons", u"EssaiBandes", bande=_i)
    _planche = {int(float(t["darkness"])) for _lo, _l, _r, t in (_items or [])
                if t}
    _attendu = _selecteur.get(_titre, set())
    assert _planche == _attendu, (
        "bande « {} » : le sélecteur annonce {} et la planche grave {}"
        .format(_titre, sorted(_attendu), sorted(_planche)))
    _k = _nuancier.combo_nuancier_bande.findData(_i)
    _annonce = _nuancier.combo_nuancier_bande.itemText(_k)
    assert "{} ton(s)".format(len(_attendu)) in _annonce, (
        "bande « {} » : la liste annonce {!r} pour {} ton(s)"
        .format(_titre, _annonce, len(_attendu)))
print("4. sélecteur, compte annoncé et planche gravée : un seul découpage "
      "en bandes, borne comprise OK")

# ==========================================================================
# 5. AFFICHER UNE MESURE, C'EST LA POSSÉDER
# ==========================================================================
# `reload` rangeait un point sur le niveau le plus proche À MOINS DE
# `SNAP_DEFOCUS_TOLERANCE_MM` ; `_on_save` exigeait l'ÉGALITÉ EXACTE du
# niveau. Un point à 15,34 -- le MDF de l'atelier en porte cinq, la
# valeur que cite la docstring de `load_burn_widths` -- était donc
# affiché par la grille « 15 mm » sans lui appartenir : un clic sur
# « Enregistrer les mesures » écrivait la valeur à 15,0 tout en
# « conservant » l'originale à 15,34. Six points devenaient onze.
core.save_burn_widths(u"EssaiSnap", {
    "focus": [{"power": 1000.0, "feed": 800.0, "width": 0.34}],
    "defocus": [{"power": p, "feed": 800.0, "z_offset": 15.34, "width": w}
                for p, w in ((200.0, 0.50), (400.0, 0.72), (600.0, 0.90),
                             (800.0, 1.00), (1000.0, 1.09))],
})


def _n_defocus(mat):
    d = (core.load_config().get("burn_widths") or {}).get(mat) or {}
    return len(d.get("defocus") or [])


_hote = QtWidgets.QWidget()
_hote.setLayout(QtWidgets.QFormLayout())


class _FauxParent(object):
    form = None


_ctrl = tp._MesuresPlanchesControleur(_hote.layout(), _FauxParent(),
                                      lambda: u"EssaiSnap")
_ctrl.reload()
assert len(_ctrl.grilles_defocus[15.0].values()) == 5, (
    "la grille 15 mm devrait AFFICHER les cinq points à 15,34")
_avant = _n_defocus(u"EssaiSnap")
_ctrl._on_save()
_apres = _n_defocus(u"EssaiSnap")
assert _apres == _avant, (
    "un enregistrement a DUPLIQUÉ les mesures : {} points avant, {} après"
    .format(_avant, _apres))
_ctrl._on_save()
assert _n_defocus(u"EssaiSnap") == _avant, "la duplication revient au 2e clic"
print("5. une mesure affichée par une grille lui APPARTIENT : {} points "
      "avant, {} après deux enregistrements OK".format(_avant, _apres))

print()
print("TOUT EST VERT")
