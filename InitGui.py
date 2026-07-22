# -*- coding: utf-8 -*-
"""InitGui.py -- point d'entrée GUI de l'Atelier Laser (FreeCAD Workbench).
© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Exécuté au démarrage de FreeCAD (mode graphique uniquement -- Init.py
serait pour le mode sans interface, inutile ici puisque tout ce module
fait, c'est afficher des panneaux Qt). Doit rester léger : la logique
métier (laser_core.py), les panneaux de tâches (task_panels.py) et les
commandes (commands.py) ne sont importées que dans Initialize(), qui ne
s'exécute qu'au premier changement vers cet atelier -- pas à chaque
démarrage de FreeCAD."""

import os
import sys

# FreeCAD exécute InitGui.py au démarrage sans forcément définir __file__
# dans l'espace de noms (contrairement à un import Python normal) -- repli
# via inspect, même pattern que d'autres extensions FreeCAD (ex: l'addon
# MCP installé dans ce même profil).
try:
    _WB_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    import inspect
    _WB_DIR = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

if _WB_DIR not in sys.path:
    sys.path.append(_WB_DIR)


class LaserAtelierWorkbench(Workbench):
    MenuText = "Atelier Laser"
    ToolTip = "Hachures, projection 3D, calibration et génération de G-code pour marquage/découpe laser"
    # Icon assigné APRÈS la classe (pas dans le corps de classe) : FreeCAD
    # exécute InitGui.py avec des dictionnaires globals/locals distincts au
    # démarrage. Dans ce cas, le corps d'une classe (comme celui d'une
    # fonction) résout ses noms libres UNIQUEMENT via le dict "globals" de
    # l'exec, jamais via son "locals" -- même si _WB_DIR est bien assigné
    # au niveau module juste au-dessus, il finit dans "locals" et reste
    # invisible ici (NameError: name '_WB_DIR' is not defined). Une
    # instruction au niveau module (comme l'affectation faite plus bas)
    # n'a pas cette restriction.
    Icon = ""

    def Initialize(self):
        import commands
        commands.register_commands()
        self.command_list = [
            # -- Découverte --
            "LaserAtelier_Guide",
            "Separator",
            # ===== BOUTONS DE TRAVAIL (à gauche) =====
            # -- Gravure à plat --
            "LaserAtelier_Hatch",
            "LaserAtelier_FilledEngraving",
            "LaserAtelier_Halftone",
            "Separator",
            # -- Sur surface 3D --
            "LaserAtelier_Project",
            "LaserAtelier_Curved",
            "Separator",
            # -- Découpe --
            "LaserAtelier_CurvedCut",
            "LaserAtelier_Flat",
            "Separator",
            # -- Assemblage --
            "LaserAtelier_Combined",
            "LaserAtelier_JobsToCombined",
            "Separator",
            # ===== CALIBRATION (après le travail) =====
            "LaserAtelier_Kerf",
            "LaserAtelier_TestGrid",
            "LaserAtelier_PowerRamp",
            "LaserAtelier_DefocusCalibration",
            "LaserAtelier_OffsetTest",
            "LaserAtelier_Nuancier",
            "Separator",
            # ===== RÉGLAGES (tout à droite, bord écran) =====
            "LaserAtelier_Settings",
        ]
        # Barre d'outils ET menu : la même liste groupée par séparateurs.
        # (Testé aussi en sous-menus déroulants : n'apportait qu'un niveau à
        # dérouler de plus sans gain de clarté -- on garde la liste plate.)
        self.appendToolbar("Atelier Laser", self.command_list)
        self.appendMenu("Atelier Laser", self.command_list)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


LaserAtelierWorkbench.Icon = os.path.join(_WB_DIR, "resources", "icons", "workbench.svg")
Gui.addWorkbench(LaserAtelierWorkbench())
