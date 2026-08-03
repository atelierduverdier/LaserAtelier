# -*- coding: utf-8 -*-
"""Ce qu'un DÉBUTANT rencontre : l'ordre d'apprentissage et l'alerte
« rien n'est mesuré ».

Relecture de l'atelier en nouvel utilisateur, le 03/08/2026. Trois
constats, tous figés ici : le menu doit ranger la calibration AVANT les
modes de travail (le Guide dit « CALIBRER d'abord » pendant que la barre
mettait sept icônes de calibration derrière douze boutons inutilisables),
un mode de travail doit DIRE qu'aucune mesure n'existe, et l'étape ★3
doit s'afficher là où l'on grave réellement les planches.
"""
from harness import preparer, texte
h = preparer(config_reelle=False)      # atelier VIERGE : le cas du débutant
core, tp = h.core, h.tp
from PySide6 import QtWidgets as _Qt

# --- 1. La BARRE range la calibration en tete ---------------------------
# Le 03/08/2026 le menu seul avait ete reordonne, la barre gardant l'ordre
# par tache : deux verites a tenir pour UN utilisateur, et c'est lui qui
# trouvait la barre illogique. Un seul ordre depuis.
# PAR CHEMIN, jamais `import InitGui` : plusieurs ateliers de ce FreeCAD
# ont un module de ce nom, et c'est celui de « fasteners » qui repondait
# (AttributeError sur addLanguagePath, sans rien dire d'utile).
# `Workbench` et `Gui.addWorkbench` sont fournis par le FreeCAD GRAPHIQUE :
# hors interface ils n'existent pas. On les bouche le temps du chargement,
# ce qui laisse la classe -- et la fonction d'ordre -- parfaitement
# testables sans lancer d'interface.
import importlib.util as _ilu, os as _os, builtins as _bi
import FreeCADGui as _Gui
_bi.Workbench = object
_Gui.addWorkbench = lambda *a, **k: None
_bi.Gui = _Gui                 # `Gui` aussi est injecte par FreeCAD, pas importe
# `addCommand` n'existe que dans le FreeCAD graphique. On le bouche en
# ENREGISTRANT les noms : ca permet au passage de verifier que toute
# commande postee a la barre a bien ete enregistree -- une entree qui
# pointe dans le vide est grisee a l'ecran, sans explication.
_enregistrees = []
_Gui.addCommand = lambda nom, cmd: _enregistrees.append(nom)
_spec = _ilu.spec_from_file_location(
    "laseratelier_initgui",
    _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                  "InitGui.py"))
_ig = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_ig)


class _FauxWB(_ig.LaserAtelierWorkbench):
    """Le VRAI Initialize(), avec la barre et le menu interceptes.

    Lire `command_list` sans passer par Initialize() ne prouverait rien :
    c'est lui qui la construit, et c'est lui qui la donne aux deux
    surfaces. On verifie donc ce qui est REELLEMENT poste."""

    def __init__(self):
        self.pose = {}

    def appendToolbar(self, nom, liste):
        self.pose["barre"] = list(liste)

    def appendMenu(self, nom, liste):
        self.pose["menu"] = list(liste)


_wb = _FauxWB()
_wb.Initialize()
_menu = _wb.pose["barre"]
assert _wb.pose["menu"] == _menu, (
    "la barre et le menu ne postent plus la même liste")
# Aucune commande perdue en route : c'est la faute qui ne se verrait pas.
assert _menu[0] == "LaserAtelier_Guide", _menu[:2]
# Toute icone de la barre doit correspondre a une commande ENREGISTREE.
_fantomes = [c for c in _menu
             if c != "Separator" and c not in _enregistrees]
assert not _fantomes, (
    "la barre poste des commandes qui n'ont jamais ete enregistrees : "
    "elles apparaitront grisees, sans explication", _fantomes)
assert len(set(c for c in _menu if c != "Separator")) == \
       len([c for c in _menu if c != "Separator"]), (
    "une commande apparaît deux fois dans la barre", _menu)
_i_calib = _menu.index("LaserAtelier_DefocusCalibration")
_i_travail = _menu.index("LaserAtelier_Hatch")
assert _i_calib < _i_travail, (
    "le menu met un mode de travail avant la calibration, alors que le "
    "Guide dit de calibrer d'abord", _menu)
print("1. la barre range la calibration ({}e) avant les modes de travail "
      "({}e) OK".format(_i_calib + 1, _i_travail + 1))

# --- 2. Sur un atelier VIERGE, les modes de travail le DISENT ------------
# Le seul signal etait un « -- (aucune mesure) -- » au fond d'un menu
# deroulant : invisible pour qui ne sait pas qu'il doit le chercher.
assert not core.burn_width_materials() and not core.shade_materials(), (
    "le harnais devait partir d'une config VIDE")
_hote = _Qt.QWidget()
_form = _Qt.QFormLayout(_hote)
assert tp._bandeau_non_calibre(_form) is True, (
    "atelier vierge : le bandeau doit s'afficher")
_textes = [texte(_form.itemAt(i).widget().findChild(_Qt.QLabel).text())
           for i in range(_form.rowCount())
           if _form.itemAt(i) and _form.itemAt(i).widget()
           and _form.itemAt(i).widget().findChild(_Qt.QLabel)]
_tout = " ".join(_textes)
assert "Guide" in _tout, ("le bandeau doit nommer où aller", _tout)
assert "mesur" in _tout.lower(), _tout

# ... et il DISPARAÎT des qu'une seule mesure existe : un avertissement
# permanent cesse d'etre lu, et celui-ci ne vise que la premiere heure.
core.save_burn_widths(u"BoisEssai", {"focus": [
    {"power": 800.0, "feed": 800.0, "width": 0.20, "z_offset": 0.0}]})
_hote2 = _Qt.QWidget()
_form2 = _Qt.QFormLayout(_hote2)
assert tp._bandeau_non_calibre(_form2) is False, (
    "une mesure existe : le bandeau doit se taire")
assert _form2.rowCount() == 0, "le bandeau a quand meme ajoute des rangees"
core.save_burn_widths(u"BoisEssai", {})
print("2. atelier vierge -> le bandeau prévient ; une mesure -> il se tait OK")

# --- 3. Les SIX modes de travail le portent ------------------------------
# La propriete sur la FAMILLE, pas sur le mode qu'on a sous les yeux.
import inspect as _insp
for _cls in ("TaskPanelHatch", "TaskPanelFilledEngraving", "TaskPanelHalftone",
             "TaskPanelCurved", "TaskPanelFlat", "TaskPanelCurvedCut"):
    _src = _insp.getsource(getattr(tp, _cls))
    assert "_bandeau_non_calibre(form)" in _src, (
        "{} n'avertit pas un atelier vierge".format(_cls))
print("3. les 6 modes de travail portent le bandeau OK")

# --- 4. L'etape ★3 s'affiche la ou l'on grave les planches ---------------
# Elle etait accrochee a la Grille de test, qui ne grave plus les planches
# de largeurs depuis la v2.47.0 : le bandeau « ★ Étape 3/4 » vivait sur un
# panneau que le texte de l'etape n'utilise plus, et l'Assistant -- ou l'on
# va reellement -- n'en portait aucun.
_e3 = core.calibration_step_for(u"Assistant matériau")
assert _e3 is not None and _e3["n"] == 3, (
    "l'étape 3 n'est pas rattachée à l'Assistant matériau", _e3)
_gt = core.calibration_step_for(u"Grille de test puissance / vitesse")
assert _gt is not None and _gt["n"] is None, (
    "la Grille de test doit garder un bandeau, mais en COMPLÉMENT", _gt)
assert "_calibration_banner(form, \"Assistant matériau\")" in \
       _insp.getsource(tp.TaskPanelAssistant), (
    "l'Assistant n'affiche pas le bandeau de l'étape 3")
print("4. ★3 s'affiche sur l'Assistant ; la Grille de test reste un "
      "complément OK")

print("\nTOUS LES TESTS accueil_debutant PASSENT")
