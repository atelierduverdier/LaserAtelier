# -*- coding: utf-8 -*-
"""commands.py -- commandes/icônes de la barre d'outils Atelier Laser.
© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Chaque commande capture la sélection courante au moment du clic (même
convention que l'ancienne macro : sélectionner AVANT de lancer), vérifie
qu'elle est plausible pour ce mode, puis ouvre le panneau de tâches
correspondant (task_panels.py). IsActive() grise l'icône tant qu'aucun
document/sélection pertinent n'est disponible -- évite un clic dans le
vide suivi d'une boîte d'erreur."""

import os
import FreeCAD
import FreeCADGui as Gui
from PySide6 import QtWidgets

import task_panels

_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources", "icons")


def _icon_path(name):
    return os.path.join(_ICON_DIR, name)


def _warn_selection(message):
    QtWidgets.QMessageBox.warning(None, "Sélection", message)


def _show(panel):
    """Ouvre un panneau de tâches en fermant d'abord une éventuelle fenêtre
    de tâches DÉJÀ active -- sinon FreeCAD refuse (« Active task dialog
    found ») quand on lance une commande alors qu'un panneau est ouvert."""
    if Gui.Control.activeDialog():
        Gui.Control.closeDialog()
    Gui.Control.showDialog(panel)


class GuideCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("guide.svg"),
            "MenuText": "Guide rapide",
            "ToolTip": "Le flux de travail de l'atelier et « quel mode pour quoi ? » -- "
                       "le point d'entrée pour découvrir l'atelier",
        }

    def IsActive(self):
        # Purement informatif : toujours disponible.
        return True

    def Activated(self):
        _show(task_panels.TaskPanelGuide())


class TextCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("text.svg"),
            "MenuText": "Texte (trait simple)",
            "ToolTip": "Crée du texte en police MONO-TRAIT (un seul trait par branche, "
                       "comme un traceur à plume) comme objet fil, à graver ensuite avec "
                       "Marquage -- idéal au gros point / défocus",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelText())


class CatalogueCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("catalogue.svg"),
            "MenuText": "Catalogue (planche d'exemples)",
            "ToolTip": "Grave en un seul job une planche d'EXEMPLES de plusieurs modes "
                       "(styles Marquage, Texte trait simple, Gravure remplie), avec aperçu "
                       "photo -- une planche de référence à garder après calibration",
        }

    def IsActive(self):
        return True

    def Activated(self):
        _show(task_panels.TaskPanelCatalogue())


class HatchCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("hatch.svg"),
            "MenuText": "Hachures 2D (géométrie)",
            "ToolTip": "Remplit une face 2D sélectionnée de hachures (parallèles / croisées / défocus) et "
                       "crée un objet Hachures -- géométrie seule, le G-code se génère ensuite avec le mode Marquage",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            _warn_selection("Sélectionne le motif (face/sketch) avant de lancer ce mode.")
            return
        _show(task_panels.TaskPanelHatch(selection))


class FilledEngravingCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("filled.svg"),
            "MenuText": "Gravure remplie (noir)",
            "ToolTip": "Grave une forme/texte 2D en noir plein : remplissage par hachures en défocus "
                       "(rentré pour ne pas déborder) puis contour repassé net au foyer",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            _warn_selection("Sélectionne le motif 2D (face/sketch/ShapeString) avant de lancer ce mode.")
            return
        _show(task_panels.TaskPanelFilledEngraving(selection))


class HalftoneCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("halftone.svg"),
            "MenuText": "Gravure photo (trame de points)",
            "ToolTip": "Grave une image en niveaux de gris sous forme de trame de points laser "
                       "(tramage par diffusion ou durée de pulse variable -- aucune sélection requise)",
        }

    def IsActive(self):
        # Aucun document ni sélection nécessaires : l'image vient d'un fichier.
        return True

    def Activated(self):
        _show(task_panels.TaskPanelHalftone())


class ProjectCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("project.svg"),
            "MenuText": "Projeter sur surface 3D",
            "ToolTip": "Projette un ou plusieurs motifs 2D (hachures, texte) sur une surface 3D de référence par raycast vertical",
        }

    def IsActive(self):
        # Plus besoin d'une sélection AVANT d'ouvrir : le panneau se
        # sélectionne pendant qu'il est ouvert (état affiché en direct).
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelProject())


class KerfCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("kerf.svg"),
            "MenuText": "Motif de calibration kerf",
            "ToolTip": "Crée un carré test pour mesurer le kerf réel du laser (aucune sélection requise)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelKerf())


class TestGridCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("testgrid.svg"),
            "MenuText": "Grille de test puissance/vitesse",
            "ToolTip": "Génère en un seul job une grille de cellules gravure/découpe à puissance et vitesse variables (aucune sélection requise)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelTestGrid())


class PowerRampCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("powerramp.svg"),
            "MenuText": "Test rampe puissance/vitesse (lignes)",
            "ToolTip": "Grave de longues lignes, une par vitesse, avec une puissance qui monte "
                       "progressivement de gauche à droite -- complément continu de la grille de test "
                       "(aucune sélection requise)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelPowerRamp())


class DefocusCalibrationCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("defocus.svg"),
            "MenuText": "Bande de calibration défocus",
            "ToolTip": "Grave une rangée de traits à hauteurs de bec croissantes (étiquetées) pour "
                       "mesurer le foyer et la divergence du point -- de quoi calibrer le défocus (aucune sélection requise)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelDefocusCalibration())


class NuancierCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("nuancier.svg"),
            "MenuText": "Nuancier matériau",
            "ToolTip": "La palette de gris MESURÉE d'un matériau : chaque ton = un réglage (S/F/défocus) + "
                       "son résultat constaté (noirceur %, largeur). Alimenté après les grilles/rampes de test, "
                       "appliqué d'un clic dans Marquage et Gravure remplie",
        }

    def IsActive(self):
        # Simple éditeur de données : toujours disponible.
        return True

    def Activated(self):
        _show(task_panels.TaskPanelNuancier())


class OffsetTestCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("offset_test.svg"),
            "MenuText": "Test des offsets X/Y du laser",
            "ToolTip": "Job mixte fraise+laser : croix fraisée puis croix laser au même X0 Y0 -- "
                       "l'écart entre les deux croix donne la correction des offsets X/Y du T100 "
                       "dans tool.tbl (aucune sélection requise)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelOffsetTest())


class CurvedCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("curved.svg"),
            "MenuText": "Marquage de motif (plat ou courbe)",
            "ToolTip": "Génère le G-code de marquage d'un motif filaire (hachures, tracés), avec styles de "
                       "trait (plein/tirets/pointillé/vague défocus). Pièce plate : sélectionne juste le motif "
                       "2D. Surface courbe : sélectionne le motif projeté ET le modèle 3D ensemble pour que la "
                       "gravure suive fidèlement ses courbes.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            _warn_selection(
                "Pièce PLATE : sélectionne juste le motif 2D (hachures,\n"
                "tracés...).\n"
                "Surface COURBE : sélectionne les Hachures_3D (motif projeté)\n"
                "ET le modèle 3D d'origine, TOUS LES DEUX EN MÊME TEMPS -- le\n"
                "modèle 3D permet une sonde exacte du relief pour que la\n"
                "gravure suive fidèlement ses courbes (sans lui, le Z n'est\n"
                "qu'interpolé entre les points déjà projetés).")
            return
        _show(task_panels.TaskPanelCurved(selection))


class CurvedCutCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("curved_cut.svg"),
            "MenuText": "Découpe multi-passes sur surface courbée",
            "ToolTip": "Génère le G-code de découpe multi-passes qui suit le relief d'une surface courbe "
                       "(objets projetés par le mode Projection). Sélectionne le motif ET le modèle 3D "
                       "ensemble pour que la découpe suive fidèlement ses courbes.",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            _warn_selection(
                "Sélectionne les Hachures_3D (motif projeté) ET le modèle 3D\n"
                "d'origine, TOUS LES DEUX EN MÊME TEMPS -- le modèle 3D permet\n"
                "une sonde exacte du relief pour que la découpe suive\n"
                "fidèlement ses courbes.")
            return
        _show(task_panels.TaskPanelCurvedCut(selection))


class FlatCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("flat.svg"),
            "MenuText": "Découpe multi-passes (matériau plat)",
            "ToolTip": "Génère le G-code de découpe multi-passes sur matériau plat",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            _warn_selection("Sélectionne le(s) contour(s) à découper.")
            return
        _show(task_panels.TaskPanelFlat(selection))


class CombinedCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("combined.svg"),
            "MenuText": "Job combiné (plusieurs opérations)",
            "ToolTip": "Empile plusieurs opérations (Marquage courbe / Découpe multi-passes / Grille de test) "
                       "dans un seul job avec un seul armement du laser (aucune sélection requise à l'ouverture -- "
                       "la géométrie est sélectionnée puis capturée à chaque ajout d'opération)",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        _show(task_panels.TaskPanelCombined())


class JobsToCombinedCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("combined_from_jobs.svg"),
            "MenuText": "Jobs sélectionnés → job combiné",
            "ToolTip": "Empile les Jobs sélectionnés dans l'arborescence comme opérations "
                       "du job combiné (chacun avec les réglages portés par sa forme), "
                       "puis ouvre le Job combiné pour les ordonner et générer le fichier unique",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None and bool(Gui.Selection.getSelection())

    def Activated(self):
        import laser_jobs
        jobs = [o for o in Gui.Selection.getSelection() if laser_jobs._est_job(o)]
        if not jobs:
            _warn_selection("Sélectionne un ou plusieurs objets Job dans l'arborescence "
                            "(dossier « Atelier Laser »).")
            return
        ajoutes, ignores = laser_jobs.ajouter_jobs_au_combine(jobs)
        if ignores:
            QtWidgets.QMessageBox.warning(
                None, "Job combiné",
                "Jobs ignorés :\n- " + "\n- ".join(ignores))
        if ajoutes:
            _show(task_panels.TaskPanelCombined())


class SettingsCommand:
    def GetResources(self):
        return {
            "Pixmap": _icon_path("settings.svg"),
            "MenuText": "Préférences",
            "ToolTip": "Réglages de l'atelier : dossier G-code par défaut, vitesse rapide d'estimation, "
                       "sélecteur broche, garde-fous de découpe, profil du bec (anti-collision)",
        }

    def IsActive(self):
        # Pas besoin de document ni de sélection pour régler l'atelier.
        return True

    def Activated(self):
        _show(task_panels.TaskPanelSettings())


def register_commands():
    Gui.addCommand("LaserAtelier_Guide", GuideCommand())
    Gui.addCommand("LaserAtelier_Settings", SettingsCommand())
    Gui.addCommand("LaserAtelier_Hatch", HatchCommand())
    Gui.addCommand("LaserAtelier_Text", TextCommand())
    Gui.addCommand("LaserAtelier_FilledEngraving", FilledEngravingCommand())
    Gui.addCommand("LaserAtelier_Halftone", HalftoneCommand())
    Gui.addCommand("LaserAtelier_Project", ProjectCommand())
    Gui.addCommand("LaserAtelier_Kerf", KerfCommand())
    Gui.addCommand("LaserAtelier_TestGrid", TestGridCommand())
    Gui.addCommand("LaserAtelier_PowerRamp", PowerRampCommand())
    Gui.addCommand("LaserAtelier_DefocusCalibration", DefocusCalibrationCommand())
    Gui.addCommand("LaserAtelier_OffsetTest", OffsetTestCommand())
    Gui.addCommand("LaserAtelier_Nuancier", NuancierCommand())
    Gui.addCommand("LaserAtelier_Catalogue", CatalogueCommand())
    Gui.addCommand("LaserAtelier_Curved", CurvedCommand())
    Gui.addCommand("LaserAtelier_CurvedCut", CurvedCutCommand())
    Gui.addCommand("LaserAtelier_Flat", FlatCommand())
    Gui.addCommand("LaserAtelier_Combined", CombinedCommand())
    Gui.addCommand("LaserAtelier_JobsToCombined", JobsToCombinedCommand())
