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
            "LaserAtelier_TexteContour",
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
        # LE MENU garde la liste unique, groupée par séparateurs : c'est un
        # seul déroulé qu'on lit de haut en bas.
        self.appendMenu("Atelier Laser", self.command_list)

        # LA BARRE, elle, se découpe en BARRES NOMMÉES -- une par thème.
        # Christophe, 04/08/2026 : « pour plus de visibilité il serait bien
        # de mettre un fond de couleur différent pour chaque section dans la
        # barre des icônes ». Les séparateurs d'une barre unique ne se
        # voient presque pas ; des barres distinctes, elles, portent un NOM
        # (visible dans Affichage > Barres d'outils et au survol de la
        # poignée), se déplacent et se masquent séparément. C'est le seul
        # découpage que FreeCAD offre nativement -- la teinte ci-dessous
        # n'est qu'un renfort, elle ne porte pas l'information à elle seule.
        self._barres = [
            ("Atelier — Découverte", ["LaserAtelier_Guide"]),
            ("Atelier — Calibrer le laser",
             ["LaserAtelier_DefocusCalibration", "LaserAtelier_OffsetTest"]),
            ("Atelier — Ajouter un matériau",
             ["LaserAtelier_Assistant", "LaserAtelier_TestGrid",
              "LaserAtelier_PowerRamp", "LaserAtelier_Nuancier",
              "LaserAtelier_Kerf"]),
            ("Atelier — Dessins", ["LaserAtelier_ImporterSVG"]),
            ("Atelier — Gravure à plat",
             ["LaserAtelier_Hatch", "LaserAtelier_Text",
              "LaserAtelier_Calligraphie", "LaserAtelier_TexteContour",
              "LaserAtelier_FilledEngraving", "LaserAtelier_Halftone"]),
            ("Atelier — Sur surface 3D",
             ["LaserAtelier_Project", "LaserAtelier_Curved"]),
            ("Atelier — Découpe",
             ["LaserAtelier_CurvedCut", "LaserAtelier_Flat"]),
            ("Atelier — Assemblage",
             ["LaserAtelier_Combined", "LaserAtelier_JobsToCombined"]),
            ("Atelier — Référence et réglages",
             ["LaserAtelier_Catalogue", "LaserAtelier_Settings"]),
        ]
        for nom, cmds in self._barres:
            self.appendToolbar(nom, cmds)

    # Teintes des barres, en DEGRÉS de teinte (roue chromatique). Ce ne sont
    # pas des couleurs en dur : elles sont mélangées à la couleur de fond du
    # THÈME COURANT, si bien que le clair et le sombre s'accommodent tous
    # deux, et qu'un changement de thème ne laisse pas des pavés criards.
    _TEINTES = (28, 205, 190, 265, 35, 150, 0, 300, 220)
    _MELANGE = 0.18            # part de couleur ajoutée au fond du thème

    def _colorer_barres(self):
        """Un fond légèrement teinté par barre. Jamais bloquant.

        Enveloppé de bout en bout : une barre absente, un thème qui refuse
        la feuille de style, une version de Qt différente -- rien de tout
        cela ne doit empêcher l'atelier de s'ouvrir. La couleur est un
        confort ; le NOM de la barre, lui, porte l'information."""
        try:
            import FreeCAD
            import FreeCADGui
            from PySide6 import QtGui, QtWidgets
            fen = FreeCADGui.getMainWindow()
            if fen is None:
                return
            fond = fen.palette().color(QtGui.QPalette.Window)
            for (nom, _cmds), teinte in zip(self._barres, self._TEINTES):
                barre = None
                for b in fen.findChildren(QtWidgets.QToolBar):
                    if b.windowTitle() == nom or b.objectName() == nom:
                        barre = b
                        break
                if barre is None:
                    continue
                c = QtGui.QColor.fromHsv(teinte, 200, 200)
                m = QtGui.QColor(
                    int(fond.red() * (1 - self._MELANGE) + c.red() * self._MELANGE),
                    int(fond.green() * (1 - self._MELANGE) + c.green() * self._MELANGE),
                    int(fond.blue() * (1 - self._MELANGE) + c.blue() * self._MELANGE))
                barre.setStyleSheet(
                    "QToolBar {{ background: {}; border-radius: 3px; }}"
                    .format(m.name()))
        except Exception as exc:
            try:
                import FreeCAD
                FreeCAD.Console.PrintLog(
                    "LaserAtelier : teinte des barres non appliquée ({}).\n"
                    .format(exc))
            except Exception:
                pass


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
        # Les barres n'existent qu'une fois l'atelier activé : c'est ici, et
        # pas dans Initialize(), qu'on peut les retrouver pour les teinter.
        self._colorer_barres()

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
