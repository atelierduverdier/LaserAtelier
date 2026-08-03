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
        # L'ORDRE D'APPRENTISSAGE, pour la barre comme pour le menu.
        # Le Guide dit « CALIBRER (une fois) » : les sept icônes de
        # calibration arrivaient pourtant derrière DOUZE boutons de travail
        # qu'on ne peut pas utiliser tant que rien n'est mesuré. Christophe
        # a relevé la contradiction le 03/08/2026 -- l'atelier n'a qu'un
        # utilisateur, et c'est lui qui trouvait l'ordre illogique : son
        # avis passe avant l'argument ergonomique du « bouton quotidien
        # d'abord ».
        self.command_list = [
            # -- Découverte --
            "LaserAtelier_Guide",
            "Separator",
            # ===== CALIBRATION : PREMIÈRE UTILISATION DU LASER =====
            # Une fois par laser (pas par matériau) -- à refaire seulement
            # après un changement optique ou un démontage/remontage.
            "LaserAtelier_DefocusCalibration",  # ★1 foyer + point + défocus
            "LaserAtelier_OffsetTest",          # ★2 offsets X/Y
            "Separator",
            # ===== CALIBRATION : AJOUTER UN MATÉRIAU =====
            "LaserAtelier_Assistant",           # ★3 planches -> mesures
            "LaserAtelier_TestGrid",            # complément (défocus libre…)
            "LaserAtelier_PowerRamp",           # repérage rapide S/F
            "LaserAtelier_Nuancier",            # tons mesurés (gris/photo)
            "LaserAtelier_Kerf",                # ★4 kerf (si découpe)
            "Separator",
            # ===== BOUTONS DE TRAVAIL =====
            # -- Import de dessins --
            "LaserAtelier_ImporterSVG",
            "Separator",
            # -- Gravure à plat --
            "LaserAtelier_Hatch",
            "LaserAtelier_Text",
            "LaserAtelier_Calligraphie",
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
            # -- Référence --
            "LaserAtelier_Catalogue",
            "Separator",
            # ===== RÉGLAGES (tout à droite, bord écran) =====
            "LaserAtelier_Settings",
        ]
        # Barre d'outils ET menu : la même liste groupée par séparateurs.
        # (Testé aussi en sous-menus déroulants : n'apportait qu'un niveau à
        # dérouler de plus sans gain de clarté -- on garde la liste plate.
        # Testé aussi en DEUX ordres, barre par tâche et menu par
        # apprentissage : deux vérités à tenir pour un seul utilisateur,
        # abandonné le 03/08/2026 au profit d'un ordre unique.)
        self.appendToolbar("Atelier Laser", self.command_list)
        self.appendMenu("Atelier Laser", self.command_list)


    def Activated(self):
        """Un document ouvert, toujours.

        Sans document actif, quinze des vingt et un boutons sont GRISÉS
        (leur `IsActive` exige un document), et les six autres ouvrent une
        fenêtre de tâches là où FreeCAD n'a aucune vue pour l'accueillir :
        elle part derrière la fenêtre principale et devient inatteignable.
        Christophe l'a rencontré le 02/08/2026 en ouvrant FreeCAD puis
        l'atelier sans rien créer.

        Tous les modes d'ici créent ou lisent de la géométrie : il n'y a
        pas d'usage sans document. Plutôt que d'exiger un geste préalable
        que rien n'annonce, l'atelier ouvre le document lui-même -- et le
        DIT dans la vue Rapport, pour que personne ne se demande d'où sort
        cet « Atelier » dans l'arbre.

        Jamais quand un document est déjà ouvert : on n'ajoute pas un
        onglet vide à côté du travail en cours."""
        try:
            import FreeCAD
            if FreeCAD.ActiveDocument is None:
                doc = FreeCAD.newDocument("Atelier")
                FreeCAD.Console.PrintMessage(
                    "Atelier laser : aucun document ouvert, « {} » créé -- "
                    "sinon les panneaux s'ouvrent hors de portée.\n"
                    .format(doc.Name))
        except Exception as exc:      # jamais empêcher l'atelier de s'ouvrir
            try:
                FreeCAD.Console.PrintWarning(
                    "Atelier laser : document non créé ({}).\n".format(exc))
            except Exception:
                pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


LaserAtelierWorkbench.Icon = os.path.join(_WB_DIR, "resources", "icons", "workbench.svg")
Gui.addWorkbench(LaserAtelierWorkbench())
