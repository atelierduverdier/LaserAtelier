# -*- coding: utf-8 -*-
"""Ce que la lecture ligne à ligne des panneaux a trouvé (02/09/2026).

Cinq défauts d'INTERFACE, tous reproduits avant d'être décrits. Ils ont
en commun de ne rien casser bruyamment : un libellé qui reste seul, un
message posté au mauvais endroit, une section qui se referme, un réglage
qui ne revient pas, une info-bulle qui décrit un mécanisme abandonné.
Rien ne lève d'exception ; c'est ce qui les rend chers.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness import preparer

h = preparer()
core, tp = h.core, h.tp
from PySide6 import QtWidgets                                    # noqa: E402

QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.critical = staticmethod(lambda *a, **k: None)
QtWidgets.QMessageBox.information = staticmethod(lambda *a, **k: None)


# ==========================================================================
# 1. CACHER UN CHAMP, C'EST CACHER SA RANGÉE
# ==========================================================================
# `_set_row_visible` existe pour ça, et sa page le dit : « setVisible sur
# le seul champ laisse le libellé orphelin ». La Grille de test masquait
# pourtant ses champs à la main, dans une boucle. Passer en mode Découpe
# laissait donc « Type de remplissage : », « Espacement hachures : » et
# « Angle hachures : » suspendus dans le vide, sans rien à leur droite.
def _orphelins(racine):
    """Rangées où le champ et son libellé ne sont pas d'accord."""
    mauvais = []
    for lay in racine.findChildren(QtWidgets.QFormLayout):
        for r in range(lay.rowCount()):
            li = lay.itemAt(r, QtWidgets.QFormLayout.LabelRole)
            fi = lay.itemAt(r, QtWidgets.QFormLayout.FieldRole)
            if li is None or fi is None:
                continue
            lbl, champ = li.widget(), fi.widget()
            if lbl is None or champ is None:
                continue
            if lbl.isHidden() != champ.isHidden():
                mauvais.append(lbl.text()[:34])
    return mauvais


_grille = tp.TaskPanelTestGrid()
for _mode, _nom in ((0, "Gravure"), (1, "Découpe")):
    _grille.combo_mode.setCurrentIndex(_mode)
    _restes = _orphelins(_grille.form)
    assert not _restes, (
        "mode {} : {} libellé(s) sans leur champ -- {}".format(
            _nom, len(_restes), _restes))
print("1. Grille de test : en gravure comme en découpe, aucun libellé ne "
      "reste seul OK")

# ==========================================================================
# 2. LE MESSAGE VA DANS LE BLOC DE LA CASE VISÉE
# ==========================================================================
# Un bloc de mesure vit SOUS CHAQUE grille -- « le bouton doit être là où
# sont les cases », après une séance de saisie passée à faire défiler. Un
# seul site écrivait encore en dur dans le libellé du bloc du FOYER : la
# phrase qui NOMME la case visée, celle que le code appelle lui-même « le
# dernier moment où la corriger coûte un clic ». Viser une case d'une
# grille de défocus faisait donc changer le bouton sur place pendant que
# sa réponse partait trois grilles plus haut.
class _FausseVue(object):
    def addEventCallback(self, *a):
        return object()

    def removeEventCallback(self, *a):
        pass


class _FauxParent(object):
    form = None


_hote = QtWidgets.QWidget()
_hote.setLayout(QtWidgets.QFormLayout())
_ctrl = tp._MesuresPlanchesControleur(_hote.layout(), _FauxParent(),
                                      lambda: u"Hêtre")
_ctrl.reload()
_ctrl._vue3d = lambda: _FausseVue()
assert _ctrl.grilles_defocus, "il faut au moins une grille de défocus"
_dz = sorted(_ctrl.grilles_defocus)[0]
_gr = _ctrl.grilles_defocus[_dz]
_gr._chk.setChecked(False)                       # déverrouiller
_case = sorted(_gr.cells().items())[0][1]
_ctrl._on_case_focus(_case)
_bloc = _ctrl._bloc_de(_case)
assert _bloc is not _ctrl._blocs[0], (
    "le bloc du défocus doit différer de celui du foyer")
_bloc.lbl.setText("")
_ctrl.lbl_mesure.setText("")
_ctrl._on_mesurer(_bloc)
assert "Cible" in _bloc.lbl.text(), (
    "la cible n'est pas annoncée dans le bloc de la case : {!r}"
    .format(_bloc.lbl.text()))
assert "Cible" not in _ctrl.lbl_mesure.text(), (
    "la cible est annoncée dans le bloc du FOYER, trois grilles plus "
    "haut : {!r}".format(_ctrl.lbl_mesure.text()))
_ctrl._fin_mesure()
print("2. la cible d'une mesure s'annonce sous SA grille, pas sous celle "
      "du foyer OK")

# ==========================================================================
# 3. UNE SECTION D'ÉTAPE EST UNE ÉTAPE, JUSQU'À ⑨
# ==========================================================================
# `_SectionHeader` peignait la carte orange de ① à ⑨ ; `_ETAPES`
# s'arrêtait à ③. « ④ Déduire (modèle & nuancier) » -- la dernière étape
# de l'Assistant matériau -- avait donc l'APPARENCE d'une étape sans en
# avoir les règles : ouvrir ② pour saisir une mesure la refermait
# derrière soi, quand ①②③ restaient en place. C'est mot pour mot le
# défaut pour lequel l'exemption d'accordéon a été écrite.
_assistant = tp.TaskPanelAssistant()
_entetes = _assistant.form.findChildren(tp._SectionHeader)
_etapes = [e for e in _entetes if e._etape]
assert len(_etapes) >= 4, "l'Assistant devrait porter au moins ④ étapes"
for _e in _etapes:
    assert tp._est_etape(_e.text()), (
        "« {} » est peinte en carte d'étape mais n'en suit pas les règles"
        .format(_e.text()))
for _e in _entetes:                              # tout replier
    if _e.isChecked():
        _e.set_open(False)
_quatre = next(e for e in _etapes if e.text().lstrip().startswith("④"))
_quatre.set_open(True)
_deux = next(e for e in _etapes if e.text().lstrip().startswith("②"))
_deux.set_open(True)                             # on ouvre ② pour mesurer
assert _quatre.isChecked(), (
    "ouvrir ② a refermé « {} » : l'accordéon ne doit pas toucher aux "
    "étapes".format(_quatre.text()))
print("3. les sections d'étape ①…⑨ échappent toutes à l'accordéon OK")

# ==========================================================================
# 4. LE DÉFOCUS DES CELLULES SURVIT À LA FERMETURE
# ==========================================================================
# Il ne figurait dans AUCUNE des deux listes de la Grille de test. Après
# l'objectif « bande de tons », rouvrir le panneau rendait le pas de
# 1,01 mm -- calculé pour un trait de 0,68 à 0,96 mm en défocus 15 --
# avec un défocus retombé à 0. Au foyer le trait fait 0,11 à 0,20 mm :
# couverture 11 à 25 % au lieu de 52 à 95 %. C'est très exactement la
# planche rayée que raconte `_recalculer_pas` ; ce correctif-là fermait
# UNE des deux façons d'y arriver, celle-ci restait ouverte.
_g = tp.TaskPanelTestGrid()
_i = _g.combo_recipe.findData("noirceur_balayage")
assert _i > 0, "l'objectif « bande de tons » a disparu"
_g.combo_recipe.setCurrentIndex(_i)
_dz_objectif = _g.spn_cell_defocus.value()
_pas_objectif = _g.spn_hatch_spacing.value()
assert _dz_objectif > 1.0, "cet objectif devrait graver en défocus"
tp._save_last_values("testgrid", _g._last_fields)
_g2 = tp.TaskPanelTestGrid()
assert abs(_g2.spn_cell_defocus.value() - _dz_objectif) < 1e-6, (
    "le défocus des cellules n'est pas revenu : {:.2f} au lieu de {:.2f}, "
    "alors que le pas ({:.2f} mm) l'est".format(
        _g2.spn_cell_defocus.value(), _dz_objectif,
        _g2.spn_hatch_spacing.value()))
print("4. le défocus des cellules revient avec le pas qui lui correspond "
      "({:.0f} mm / {:.2f} mm) OK".format(_dz_objectif, _pas_objectif))

# ==========================================================================
# 5. AUCUNE INFO-BULLE NE PROMET UN PULSE À L'ARRÊT
# ==========================================================================
# La règle de la maison est nette : jamais de `G4` faisceau allumé, parce
# que la puissance est asservie à la vitesse réelle et tombe à zéro à
# l'arrêt -- un point tiré ainsi ne grave RIEN. Les trois call sites sont
# passés au micro-trait le 02/08/2026, mais SIX textes d'interface
# décrivaient encore « arrêt + pulse à chaque point » et « la machine
# s'arrête à chaque point ». Un utilisateur qui les lit croit que sa
# machine s'arrête pour tirer.
_INTERDITS = ("arrêt + pulse", "s'arrête à chaque point",
              "machine s'arrête", "pulses (G4)")
_source = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "task_panels.py"), encoding="utf-8").read()
for _mot in _INTERDITS:
    assert _mot not in _source, (
        "un texte d'interface promet encore un pulse à l'arrêt : {!r}"
        .format(_mot))
# ET LE GÉNÉRATEUR LE CONFIRME : zéro G4 dans un pointillé.
import FreeCAD                                                   # noqa: E402
_g4 = core.generate_flat_styled_body(
    [[FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(20, 0, 0)]], 500.0, 800.0, 8.0,
    style="pointille", dot_spacing=1.5, dot_dwell_s=0.05)
assert not [l for l in _g4.split("\n") if l.startswith("G4")], (
    "le style pointillé émet un G4")
print("5. aucune info-bulle ne décrit un pulse à l'arrêt, et le pointillé "
      "n'émet aucun G4 OK")

# ==========================================================================
# 6. LA TOLÉRANCE ANNONCÉE EST CELLE DU CODE
# ==========================================================================
# La table des largeurs libres annonçait « à moins de 5 mm » -- la valeur
# d'avant l'arrivée des niveaux profonds (40/55/60), passée à 2 mm
# précisément pour que 40 NE devienne PAS 36. Le message a continué
# d'annoncer l'ancienne règle, et c'est celui qui avait été réécrit après
# que Christophe a dit ne pas le comprendre.
_hote2 = QtWidgets.QWidget()
_hote2.setLayout(QtWidgets.QFormLayout())
_libres = tp._make_largeurs_libres(_hote2.layout(), lambda: u"EssaiTolerance")
_table = _hote2.findChild(QtWidgets.QTableWidget)
for _c, _v in enumerate(("800", "400", "17", "1.20")):
    _table.setItem(0, _c, QtWidgets.QTableWidgetItem(_v))
_hote2.findChildren(QtWidgets.QPushButton)[-1].click()
_dits = [l.text() for l in _hote2.findChildren(tp._WrapLabel)
         if "Attention" in l.text()]
assert _dits, "aucun avertissement sur un défocus de 17 mm"
assert "{:g} mm".format(core.SNAP_DEFOCUS_TOLERANCE_MM) in _dits[0], (
    "le message n'annonce pas la tolérance réelle ({:g} mm) : {!r}".format(
        core.SNAP_DEFOCUS_TOLERANCE_MM, _dits[0][-160:]))
print("6. la tolérance de rangement annoncée est celle du code "
      "({:g} mm) OK".format(core.SNAP_DEFOCUS_TOLERANCE_MM))

print()
print("TOUT EST VERT")
