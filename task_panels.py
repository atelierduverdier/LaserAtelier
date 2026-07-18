# -*- coding: utf-8 -*-
"""task_panels.py -- panneaux de tâches (Tasks) de l'Atelier Laser.

Un panneau par mode, affiché dans le panneau des tâches (dock à gauche,
non-bloquant -- on peut tourner la vue 3D pendant qu'il reste ouvert) via
FreeCADGui.Control.showDialog, à la place des pages de l'ancienne boîte de
dialogue modale (QDialog) de la macro. Toute la logique de calcul reste
dans laser_core.py ; ces classes se contentent de lire les widgets et
d'appeler les fonctions correspondantes.

Contrat des panneaux FreeCAD (Gui::TaskView) : accept()/reject() qui
renvoient False laissent le panneau ouvert (utilisé ici pour les erreurs
de validation, afin de ne pas perdre la saisie de l'utilisateur)."""

import os
import FreeCAD
import FreeCADGui as Gui
from PySide6 import QtWidgets, QtGui, QtCore

import laser_core as core

_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources", "icons")


def _icon(name):
    return QtGui.QIcon(os.path.join(_ICON_DIR, name))


def _scrollable(inner):
    # setWidgetResizable(True) + une hauteur minimale forcée sur le
    # QScrollArea (voir plus bas) étirent "inner" pour remplir tout
    # l'espace vertical disponible, y compris quand le contenu réel est
    # plus compact. Sans absorbeur d'espace dédié, QFormLayout répartit
    # cet espace en trop de façon imprévisible entre les lignes à
    # widget unique (ex: le label de durée estimée) plutôt que de le
    # laisser en bas -- d'où les grands vides constatés au-dessus et
    # en-dessous de ce label. Un widget factice Expanding ajouté en
    # toute dernière ligne absorbe cet espace à lui seul, ce qui laisse
    # le reste du contenu compact et ancré en haut.
    layout = inner.layout()
    if layout is not None:
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout.addRow(spacer)

    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    scroll.setWidget(inner)
    # Sans politique de taille explicite, le QScrollArea peut se contenter
    # d'une hauteur "naturelle" plus petite que le panneau de tâches de
    # FreeCAD -- laissant de l'espace vide en bas et une barre de
    # défilement comprimée dans une zone plus petite que la fenêtre
    # entière. Expanding force le widget à occuper tout l'espace vertical
    # (et horizontal) disponible dans le panneau qui l'accueille.
    scroll.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
    # Hauteur minimale généreuse : comme le panneau des tâches ne peut pas
    # être redimensionné à la main sans risquer un plantage (contrainte
    # connue de cette installation FreeCAD), on demande d'emblée une boîte
    # plus haute plutôt que de compter sur un redimensionnement manuel.
    scroll.setMinimumHeight(900)
    return scroll


def _duration_row(form, callback, tooltip_extra=""):
    """Ajoute à `form` (QFormLayout) une ligne label de durée estimée +
    bouton "Actualiser", connecté à `callback`. Volontairement PAS
    recalculé automatiquement au changement des champs (valueChanged) :
    avec un recalcul en direct, taper une valeur au clavier (ex. "3"
    puis "0" puis "0" puis "0" pour arriver à 3000) déclenche un calcul
    intermédiaire sur une valeur transitoire non voulue. Un bouton
    explicite laisse l'utilisateur finir sa saisie avant de
    recalculer."""
    row = QtWidgets.QWidget()
    row_layout = QtWidgets.QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    lbl = QtWidgets.QLabel("Durée estimée : --")
    lbl.setWordWrap(True)
    lbl.setToolTip(
        "Cliquer sur Actualiser pour recalculer avec les valeurs\n"
        "actuelles des champs ci-dessus. " + tooltip_extra)
    btn = QtWidgets.QPushButton("Actualiser")
    btn.setToolTip("Recalcule la durée estimée.")
    btn.clicked.connect(callback)
    row_layout.addWidget(lbl, 1)
    row_layout.addWidget(btn, 0)
    form.addRow(row)
    return lbl


def _write_gcode_with_dialog(parent_widget, gcode, default_path):
    """Estime la durée, propose un fichier de sauvegarde, écrit le G-code
    si un chemin est choisi. Retourne True si le fichier a été écrit,
    False si l'utilisateur a renoncé. Un clic sur Annuler dans le dialogue
    de fichier propose une relance au lieu d'abandonner en silence : le
    G-code généré n'existe nulle part ailleurs, le perdre sur un simple
    Annuler (peut-être accidentel) forçait à refaire tous les réglages du
    panneau. La durée est affichée à la fois dans la vue Rapport ET dans
    une boîte de dialogue -- la vue Rapport n'est pas toujours
    ouverte/visible (panneau optionnel de FreeCAD), donc s'y fier seule
    rendait l'info invisible en pratique pour qui ne l'a pas ouverte."""
    # Dossier par défaut : GCODE_DIR (Préférences) ; repli sur le chemin
    # d'origine si le dossier (partage réseau...) n'est pas accessible.
    if os.path.isdir(core.GCODE_DIR):
        default_path = os.path.join(core.GCODE_DIR, os.path.basename(default_path))
    estimated_seconds = core.estimate_job_time_seconds(gcode)
    duration_text = core.format_duration(estimated_seconds)
    FreeCAD.Console.PrintMessage(
        "Durée estimée (approximative, rapide supposé à {:.0f}mm/min) : {}\n".format(
            core.RAPID_FEED_MM_MIN, duration_text))
    while True:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent_widget, "Sauvegarder G-code", default_path, "G-code (*.ngc)")
        if path:
            break
        retry = QtWidgets.QMessageBox.question(
            parent_widget, "Sauvegarde annulée",
            "Le G-code généré n'a pas été enregistré.\n\n"
            "Rouvrir le dialogue de sauvegarde ?\n"
            "(Non = abandonner ce fichier ; le panneau et ses réglages\n"
            "restent ouverts pour re-générer.)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if retry != QtWidgets.QMessageBox.Yes:
            FreeCAD.Console.PrintMessage("Sauvegarde G-code abandonnée.\n")
            return False
    with open(path, "w") as f:
        f.write(gcode)
    FreeCAD.Console.PrintMessage(
        "Fichier écrit : {} (durée estimée {})\n".format(path, duration_text))
    QtWidgets.QMessageBox.information(
        parent_widget, "G-code généré",
        "Fichier écrit :\n{}\n\nDurée estimée (approximative, rapide supposé à "
        "{:.0f}mm/min) :\n{}".format(path, core.RAPID_FEED_MM_MIN, duration_text))
    return True


# ==========================================================================
# MODE : HACHURES 2D
# ==========================================================================
class TaskPanelHatch:
    def __init__(self, selection):
        self.selection = selection
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.combo_filltype = QtWidgets.QComboBox()
        self.combo_filltype.addItems(["Parallèles", "Croisées (grille)", "Défocus (noir)"])
        # Par défaut, un QComboBox se dimensionne sur son item le PLUS
        # LONG de la liste (ici "Défocus (remplissage noir)"), même si
        # l'item affiché est court -- d'où une boîte bien plus large que
        # nécessaire et un panneau qui déborde. AdjustToMinimumContentsLength
        # ignore la longueur des items et se base uniquement sur
        # minimumContentsLength : largeur fixe et compacte, la liste
        # déroulante elle-même reste toujours lisible en entier.
        self.combo_filltype.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filltype.setMinimumContentsLength(17)
        self.combo_filltype.setToolTip(
            "Parallèles : lignes droites toutes dans le même sens\n"
            "(boustrophédon/zigzag) -- le mode par défaut.\n"
            "Croisées : les mêmes lignes doublées à angle+90 (grille),\n"
            "remplissage plus dense/plus uniforme, deux fois plus de trait.\n"
            "Défocus : même tracé que Parallèles, mais destiné à être gravé\n"
            "avec le point laser élargi (voir calibration ci-dessous) pour\n"
            "noircir toute la surface en un seul passage.")
        form.addRow("Type de remplissage :", self.combo_filltype)

        self.spn_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_spacing.setRange(0.05, 100.0)
        self.spn_spacing.setValue(1.0)
        self.spn_spacing.setDecimals(2)
        self.spn_spacing.setSuffix(" mm")
        self.spn_spacing.setToolTip(
            "En remplissage Défocus : espacement des traits visé -- le\n"
            "défocus calculé plus bas est celui qui élargit le point\n"
            "laser à peu près à cette taille, pour noircir sans laisser\n"
            "de bandes non brûlées entre les traits.")
        form.addRow("Espacement :", self.spn_spacing)

        self.spn_angle = QtWidgets.QDoubleSpinBox()
        self.spn_angle.setRange(-360, 360)
        self.spn_angle.setValue(45)
        self.spn_angle.setSuffix(" deg")
        self.spn_angle.setToolTip(
            "Orientation des hachures dans le repère local de la face\n"
            "(0 deg = lignes horizontales). En mode Croisées, la 2e passe\n"
            "est automatiquement à cet angle + 90 deg.")
        form.addRow("Angle :", self.spn_angle)

        self.lbl_defocus_calib = QtWidgets.QLabel(
            "<b>Calibration du point laser</b> -- brûle 2 points test (au\n"
            "foyer, puis à un défocus connu) et mesure leur diamètre :")
        self.lbl_defocus_calib.setWordWrap(True)
        form.addRow(self.lbl_defocus_calib)

        self.spn_dfocus = QtWidgets.QDoubleSpinBox()
        self.spn_dfocus.setRange(0.01, 20.0)
        self.spn_dfocus.setValue(0.15)
        self.spn_dfocus.setDecimals(3)
        self.spn_dfocus.setSuffix(" mm")
        self.spn_dfocus.setToolTip(
            "Diamètre du point laser AU FOYER (Z de travail normal, celui\n"
            "utilisé pour un trait fin/une découpe). À MESURER réellement --\n"
            "0.15mm n'est qu'une valeur de départ, pas une donnée\n"
            "constructeur.")
        form.addRow("Point au foyer (mesuré) :", self.spn_dfocus)

        self.spn_ztest = QtWidgets.QDoubleSpinBox()
        self.spn_ztest.setRange(0.1, 50.0)
        self.spn_ztest.setValue(3.0)
        self.spn_ztest.setDecimals(2)
        self.spn_ztest.setSuffix(" mm")
        self.spn_ztest.setToolTip(
            "Défocus de test (bec écarté de cette distance du foyer)\n"
            "utilisé pour la 2e mesure -- la valeur exacte importe peu,\n"
            "seule compte la précision de la mesure du point obtenu.")
        form.addRow("Défocus de test :", self.spn_ztest)

        self.spn_dtest = QtWidgets.QDoubleSpinBox()
        self.spn_dtest.setRange(0.01, 30.0)
        self.spn_dtest.setValue(1.0)
        self.spn_dtest.setDecimals(3)
        self.spn_dtest.setSuffix(" mm")
        self.spn_dtest.setToolTip("Diamètre du point laser mesuré à ce défocus de test.")
        form.addRow("Point au défocus de test (mesuré) :", self.spn_dtest)

        self.lbl_defocus_result = QtWidgets.QLabel("Défocus calculé : --")
        self.lbl_defocus_result.setWordWrap(True)
        form.addRow(self.lbl_defocus_result)

        self._defocus_widgets = [
            self.lbl_defocus_calib, self.spn_dfocus, self.spn_ztest,
            self.spn_dtest, self.lbl_defocus_result,
        ]

        def _update_defocus_preview():
            half_angle = core.defocus_divergence_half_angle(
                self.spn_dfocus.value(), self.spn_dtest.value(), self.spn_ztest.value())
            defocus = core.defocus_for_fill_spacing(
                self.spn_spacing.value(), self.spn_dfocus.value(), half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration invalide : le point\n"
                    "mesuré au défocus de test doit être strictement plus\n"
                    "large que celui mesuré au foyer)")
            else:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.3f} mm -- à AJOUTER au Z de travail\n"
                    "(mode Marquage/Découpe) pour cette passe de remplissage.".format(defocus))

        def _on_filltype_changed(idx):
            is_defocus = (idx == 2)
            for w in self._defocus_widgets:
                w.setVisible(is_defocus)
            _update_defocus_preview()

        self.combo_filltype.currentIndexChanged.connect(_on_filltype_changed)
        self.spn_spacing.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dfocus.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_ztest.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dtest.valueChanged.connect(lambda _v: _update_defocus_preview())
        _on_filltype_changed(self.combo_filltype.currentIndex())

        info = QtWidgets.QLabel("Sélectionne le motif 2D (face/sketch) avant de générer.")
        info.setWordWrap(True)
        form.addRow(info)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Hachures 2D")
        self.form.setWindowIcon(_icon("hatch.svg"))

    def accept(self):
        fill_type_map = {0: "paralleles", 1: "croisees", 2: "defocus"}
        fill_type = fill_type_map.get(self.combo_filltype.currentIndex(), "paralleles")
        obj, err = core.run_hatch_generation(
            self.selection, self.spn_spacing.value(), self.spn_angle.value(), fill_type=fill_type)
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : GRAVURE REMPLIE (NOIR) -- remplissage défocus + contour au foyer
# ==========================================================================
class TaskPanelFilledEngraving:
    def __init__(self, selection):
        self.selection = selection
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Grave une forme/texte 2D en NOIR PLEIN : remplissage par\n"
            "hachures en défocus (point élargi, rentré pour ne pas déborder\n"
            "du bord) puis contour repassé net au foyer. Sélectionne le\n"
            "motif 2D (face/sketch/ShapeString) avant de lancer.")
        info.setWordWrap(True)
        form.addRow(info)

        # --- Préréglages nommés (par matériau), catégorie "filled" ---
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Recharge un jeu complet de réglages sauvegardé sous un nom\n"
            "(typiquement un matériau). Survole un nom pour voir son résumé.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.lbl_preset_summary = QtWidgets.QLabel("")
        self.lbl_preset_summary.setWordWrap(True)
        self.lbl_preset_summary.setVisible(False)
        form.addRow(self.lbl_preset_summary)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip("Sauvegarde toutes les valeurs du panneau sous un nom.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        # --- Remplissage ---
        self.spn_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_spacing.setRange(0.05, 100.0)
        self.spn_spacing.setDecimals(2)
        self.spn_spacing.setValue(1.0)
        self.spn_spacing.setSuffix(" mm")
        self.spn_spacing.setToolTip(
            "Espacement des hachures de remplissage. Le défocus calculé\n"
            "plus bas élargit le point à peu près à cette taille pour\n"
            "noircir sans laisser de bandes claires.")
        form.addRow("Espacement remplissage :", self.spn_spacing)

        self.spn_angle = QtWidgets.QDoubleSpinBox()
        self.spn_angle.setRange(-360, 360)
        self.spn_angle.setValue(45)
        self.spn_angle.setSuffix(" deg")
        self.spn_angle.setToolTip("Orientation des hachures de remplissage.")
        form.addRow("Angle hachures :", self.spn_angle)

        self.spn_fill_power = QtWidgets.QDoubleSpinBox()
        self.spn_fill_power.setRange(0, 1000)
        self.spn_fill_power.setValue(500)
        self.spn_fill_power.setToolTip("Puissance (S) du remplissage.")
        form.addRow("Puissance remplissage :", self.spn_fill_power)

        self.spn_fill_feed = QtWidgets.QDoubleSpinBox()
        self.spn_fill_feed.setRange(1, 20000)
        self.spn_fill_feed.setValue(800)
        self.spn_fill_feed.setSuffix(" mm/min")
        self.spn_fill_feed.setToolTip("Vitesse d'avance du remplissage.")
        form.addRow("Vitesse remplissage :", self.spn_fill_feed)

        # --- Calibration du point (défocus) : mêmes champs que Hachures 2D ---
        self.lbl_defocus_calib = QtWidgets.QLabel(
            "<b>Calibration du point laser</b> -- brûle 2 points test (au\n"
            "foyer, puis à un défocus connu) et mesure leur diamètre :")
        self.lbl_defocus_calib.setWordWrap(True)
        form.addRow(self.lbl_defocus_calib)

        self.spn_dfocus = QtWidgets.QDoubleSpinBox()
        self.spn_dfocus.setRange(0.01, 20.0)
        self.spn_dfocus.setDecimals(3)
        self.spn_dfocus.setValue(0.15)
        self.spn_dfocus.setSuffix(" mm")
        self.spn_dfocus.setToolTip(
            "Diamètre du point AU FOYER. À MESURER réellement -- 0.15mm\n"
            "n'est qu'une valeur de départ.")
        form.addRow("Point au foyer (mesuré) :", self.spn_dfocus)

        self.spn_ztest = QtWidgets.QDoubleSpinBox()
        self.spn_ztest.setRange(0.1, 60.0)
        self.spn_ztest.setDecimals(2)
        self.spn_ztest.setValue(3.0)
        self.spn_ztest.setSuffix(" mm")
        self.spn_ztest.setToolTip(
            "Défocus de test (bec écarté de cette distance du foyer)\n"
            "utilisé pour la 2e mesure.")
        form.addRow("Défocus de test :", self.spn_ztest)

        self.spn_dtest = QtWidgets.QDoubleSpinBox()
        self.spn_dtest.setRange(0.01, 30.0)
        self.spn_dtest.setDecimals(3)
        self.spn_dtest.setValue(1.0)
        self.spn_dtest.setSuffix(" mm")
        self.spn_dtest.setToolTip("Diamètre du point mesuré à ce défocus de test.")
        form.addRow("Point au défocus de test (mesuré) :", self.spn_dtest)

        self.lbl_defocus_result = QtWidgets.QLabel("Défocus calculé : --")
        self.lbl_defocus_result.setWordWrap(True)
        form.addRow(self.lbl_defocus_result)

        # --- Z de travail ---
        self.spn_zwork = QtWidgets.QDoubleSpinBox()
        self.spn_zwork.setRange(-50, 200)
        self.spn_zwork.setDecimals(2)
        self.spn_zwork.setValue(8.5)
        self.spn_zwork.setSuffix(" mm")
        self.spn_zwork.setToolTip(
            "Z de foyer (bec au point sur la surface). Le remplissage est\n"
            "gravé à ce Z + le défocus calculé ; le contour à ce Z + son\n"
            "propre défocus (ci-dessous).")
        form.addRow("Z de travail (foyer) :", self.spn_zwork)

        self.spn_marge = QtWidgets.QDoubleSpinBox()
        self.spn_marge.setRange(0.0, 100.0)
        self.spn_marge.setDecimals(1)
        self.spn_marge.setValue(0.0)
        self.spn_marge.setSuffix(" mm")
        self.spn_marge.setToolTip(
            "Hauteur de survol des déplacements à vide (laser éteint) entre\n"
            "les traits. 0 = transit à plat, sans lever le bec (recommandé\n"
            "sur du plat : évite un aller-retour vertical à chaque hachure).\n"
            "N'augmenter que pour survoler des obstacles (brides, serre-flans).")
        form.addRow("Marge de survol (transit) :", self.spn_marge)

        # --- Contour ---
        self.chk_contour = QtWidgets.QCheckBox("Graver le contour (repassé après le remplissage)")
        self.chk_contour.setChecked(True)
        self.chk_contour.setToolTip(
            "Repasse le bord de la forme APRÈS le remplissage, pour une\n"
            "arête nette. Décoche pour ne faire que le remplissage.")
        form.addRow(self.chk_contour)

        self.spn_contour_power = QtWidgets.QDoubleSpinBox()
        self.spn_contour_power.setRange(0, 1000)
        self.spn_contour_power.setValue(300)
        self.spn_contour_power.setToolTip("Puissance (S) du contour.")
        form.addRow("Puissance contour :", self.spn_contour_power)

        self.spn_contour_feed = QtWidgets.QDoubleSpinBox()
        self.spn_contour_feed.setRange(1, 20000)
        self.spn_contour_feed.setValue(1000)
        self.spn_contour_feed.setSuffix(" mm/min")
        self.spn_contour_feed.setToolTip("Vitesse d'avance du contour.")
        form.addRow("Vitesse contour :", self.spn_contour_feed)

        self.spn_contour_width = QtWidgets.QDoubleSpinBox()
        self.spn_contour_width.setRange(0.0, 10.0)
        self.spn_contour_width.setDecimals(2)
        self.spn_contour_width.setValue(0.0)
        self.spn_contour_width.setSuffix(" mm")
        self.spn_contour_width.setToolTip(
            "Largeur VOULUE du trait de contour. 0 (ou une valeur ≤ point au\n"
            "foyer) = trait le plus fin, net au foyer. Sinon l'atelier\n"
            "défocalise le bec juste ce qu'il faut pour élargir le point à\n"
            "cette largeur -- entrer 1 mm donne un trait d'environ 1 mm.\n"
            "Le défocus correspondant est indiqué juste en dessous.")
        form.addRow("Épaisseur trait contour :", self.spn_contour_width)

        self.lbl_contour_result = QtWidgets.QLabel("")
        self.lbl_contour_result.setWordWrap(True)
        form.addRow(self.lbl_contour_result)

        self.chk_contour.toggled.connect(self.spn_contour_power.setEnabled)
        self.chk_contour.toggled.connect(self.spn_contour_feed.setEnabled)
        self.chk_contour.toggled.connect(self.spn_contour_width.setEnabled)

        def _update_defocus_preview():
            half_angle = core.defocus_divergence_half_angle(
                self.spn_dfocus.value(), self.spn_dtest.value(), self.spn_ztest.value())
            defocus = core.defocus_for_fill_spacing(
                self.spn_spacing.value(), self.spn_dfocus.value(), half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration invalide : le point au\n"
                    "défocus de test doit être plus large qu'au foyer)")
            else:
                spot = core.spot_diameter_at_defocus(defocus, self.spn_dfocus.value(), half_angle)
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.2f} mm (bec remonté d'autant) -- point\n"
                    "{:.3f} mm, remplissage rentré de {:.3f} mm du bord.".format(
                        defocus, spot, spot / 2.0))
            # Retour visuel du contour : épaisseur voulue -> défocus.
            off = self._contour_offset(half_angle)
            if off <= 0:
                self.lbl_contour_result.setText("Contour : net au foyer (trait le plus fin).")
            else:
                self.lbl_contour_result.setText(
                    "Contour : trait {:.2f} mm -> bec remonté de {:.2f} mm.".format(
                        self.spn_contour_width.value(), off))

        self._update_defocus_preview = _update_defocus_preview
        self.spn_spacing.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dfocus.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_ztest.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dtest.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_contour_width.valueChanged.connect(lambda _v: _update_defocus_preview())

        # --- G-code avant/après ---
        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_fe", ""))
        self.txt_post.setPlainText(cfg.get("post_fe", ""))

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à la vitesse rapide des Préférences.")

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART traçant le rectangle englobant, laser\n"
            "éteint (ou faisceau de visée : voir Préférences) -- à lancer\n"
            "seul pour vérifier le positionnement avant le vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet dans la vue 3D : gris fin = transit éteint,\n"
            "rouge = gravure. Vérifie que le remplissage tient dans le\n"
            "contour. Purement visuel.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Gravure remplie (noir)")
        self.form.setWindowIcon(_icon("filled.svg"))

        self._populate_preset_combo()
        _update_defocus_preview()

    # --- Préréglages nommés (catégorie "filled") ---
    @staticmethod
    def _preset_summary(values):
        lines = ["Remplissage : espace {:g} mm @ {:g} deg, S{:g} F{:g}".format(
            values.get("spacing", 0), values.get("angle", 0),
            values.get("fill_power", 0), values.get("fill_feed", 0))]
        lines.append("Foyer {:g} mm, calib point {:g} / défocus {:g}->{:g} mm".format(
            values.get("zwork", 0), values.get("dfocus", 0),
            values.get("ztest", 0), values.get("dtest", 0)))
        if values.get("contour", True):
            lines.append("Contour S{:g} F{:g}, trait {:g} mm".format(
                values.get("contour_power", 0), values.get("contour_feed", 0),
                values.get("contour_width", 0)))
        return "\n".join(lines)

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --")
        presets = core.load_presets("filled")
        for name in sorted(presets):
            self.combo_preset.addItem(name)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1, self._preset_summary(presets[name]),
                QtCore.Qt.ToolTipRole)
        self.combo_preset.blockSignals(False)
        self.lbl_preset_summary.setVisible(False)

    def _preset_values(self):
        return {
            "spacing": self.spn_spacing.value(),
            "angle": self.spn_angle.value(),
            "fill_power": self.spn_fill_power.value(),
            "fill_feed": self.spn_fill_feed.value(),
            "dfocus": self.spn_dfocus.value(),
            "ztest": self.spn_ztest.value(),
            "dtest": self.spn_dtest.value(),
            "zwork": self.spn_zwork.value(),
            "marge": self.spn_marge.value(),
            "contour": self.chk_contour.isChecked(),
            "contour_power": self.spn_contour_power.value(),
            "contour_feed": self.spn_contour_feed.value(),
            "contour_width": self.spn_contour_width.value(),
        }

    def _on_preset_selected(self, index):
        if index <= 0:
            self.lbl_preset_summary.setVisible(False)
            return
        v = core.load_presets("filled").get(self.combo_preset.currentText())
        if not v:
            return
        self.spn_spacing.setValue(v.get("spacing", self.spn_spacing.value()))
        self.spn_angle.setValue(v.get("angle", self.spn_angle.value()))
        self.spn_fill_power.setValue(v.get("fill_power", self.spn_fill_power.value()))
        self.spn_fill_feed.setValue(v.get("fill_feed", self.spn_fill_feed.value()))
        self.spn_dfocus.setValue(v.get("dfocus", self.spn_dfocus.value()))
        self.spn_ztest.setValue(v.get("ztest", self.spn_ztest.value()))
        self.spn_dtest.setValue(v.get("dtest", self.spn_dtest.value()))
        self.spn_zwork.setValue(v.get("zwork", self.spn_zwork.value()))
        self.spn_marge.setValue(v.get("marge", self.spn_marge.value()))
        self.chk_contour.setChecked(v.get("contour", self.chk_contour.isChecked()))
        self.spn_contour_power.setValue(v.get("contour_power", self.spn_contour_power.value()))
        self.spn_contour_feed.setValue(v.get("contour_feed", self.spn_contour_feed.value()))
        self.spn_contour_width.setValue(v.get("contour_width", self.spn_contour_width.value()))
        self.lbl_preset_summary.setText(self._preset_summary(v))
        self.lbl_preset_summary.setVisible(True)

    def _on_save_preset(self):
        current = self.combo_preset.currentText() if self.combo_preset.currentIndex() > 0 else ""
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Sauvegarder le préréglage",
            "Nom du préréglage (matériau) :", text=current)
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("filled", name, self._preset_values())
        self._populate_preset_combo()
        idx = self.combo_preset.findText(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        if self.combo_preset.currentIndex() <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QtWidgets.QMessageBox.question(
            self.form, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset("filled", name)
        self._populate_preset_combo()

    def _contour_offset(self, half_angle):
        """Défocus (mm) du contour pour que son trait fasse l'épaisseur
        demandée -- 0 si la largeur voulue est <= au point au foyer (déjà
        le plus fin). Réutilise defocus_for_fill_spacing avec overlap=1
        (cible = largeur exacte, pas de recouvrement)."""
        off = core.defocus_for_fill_spacing(
            self.spn_contour_width.value(), self.spn_dfocus.value(), half_angle, overlap=1.0)
        return off if off is not None else 0.0

    def _build_edges(self, silent=False):
        """Renvoie (fill_edges, contour_edges, defocus, contour_z_offset) ou
        (None, None, None, None) si la sélection est vide ou la calibration
        défocus invalide."""
        faces = core.get_faces_from_selection_for_hatch(self.selection)
        if not faces:
            if not silent:
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur",
                    "Aucune face 2D fermée trouvée dans la sélection\n"
                    "(face, Draft, ou sketch à fils fermés).")
            return None, None, None, None
        half_angle = core.defocus_divergence_half_angle(
            self.spn_dfocus.value(), self.spn_dtest.value(), self.spn_ztest.value())
        defocus = core.defocus_for_fill_spacing(
            self.spn_spacing.value(), self.spn_dfocus.value(), half_angle)
        if defocus is None:
            if not silent:
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur",
                    "Calibration de défocus invalide : le point mesuré au\n"
                    "défocus de test doit être strictement plus large que\n"
                    "celui mesuré au foyer.")
            return None, None, None, None
        spot = core.spot_diameter_at_defocus(defocus, self.spn_dfocus.value(), half_angle)
        fill_edges, contour_edges = core.build_filled_engraving_edges(
            faces, self.spn_spacing.value(), self.spn_angle.value(), fill_inset=spot / 2.0)
        return fill_edges, contour_edges, defocus, self._contour_offset(half_angle)

    def _gen_kwargs(self, defocus, contour_z_offset):
        return {
            "z_focus": self.spn_zwork.value(),
            "defocus": defocus,
            "fill_power": self.spn_fill_power.value(),
            "fill_feed": self.spn_fill_feed.value(),
            "draw_contour": self.chk_contour.isChecked(),
            "contour_power": self.spn_contour_power.value(),
            "contour_feed": self.spn_contour_feed.value(),
            "contour_z_offset": contour_z_offset,
            "marge_survol": self.spn_marge.value(),
        }

    def _update_duration_preview(self):
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges(silent=True)
        if fill_edges is None:
            self.lbl_duration.setText("Durée estimée : -- (sélection/calibration invalide)")
            return
        gcode = core.generate_gcode_filled_engraving(
            fill_edges, contour_edges, quiet=True, **self._gen_kwargs(defocus, contour_z_offset))
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return
        gcode = core.generate_gcode_filled_engraving(
            fill_edges, contour_edges, frame_only=True, **self._gen_kwargs(defocus, contour_z_offset))
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_gravure_remplie.ngc")

    def _on_toolpath_preview(self):
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return
        gcode = core.generate_gcode_filled_engraving(
            fill_edges, contour_edges, quiet=True, **self._gen_kwargs(defocus, contour_z_offset))
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return False
        if not fill_edges and not self.chk_contour.isChecked():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Rien à graver : le remplissage est vide (motif plus fin que\n"
                "le point défocalisé) et le contour est décoché.")
            return False

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_filled_engraving(
            fill_edges, contour_edges,
            pre_gcode=pre_text, post_gcode=post_text, **self._gen_kwargs(defocus, contour_z_offset))

        cfg = core.load_config()
        cfg["pre_fe"] = pre_text
        cfg["post_fe"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/gravure_remplie.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : PROJECTION SUR SURFACE 3D
# ==========================================================================
class TaskPanelProject:
    def __init__(self, selection):
        self.selection = selection
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        lbl = QtWidgets.QLabel(
            "Sélectionne un ou plusieurs motifs 2D (ShapeString, hachures...)\n"
            "PUIS la surface 3D de référence (sphère, vague...), tous en\n"
            "même temps -- ils seront tous projetés ensemble sur cette\n"
            "surface, en un seul objet résultat. Aucun autre paramètre --\n"
            "clique juste sur OK.")
        lbl.setWordWrap(True)
        form.addRow(lbl)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Projection sur surface 3D")
        self.form.setWindowIcon(_icon("project.svg"))

    def accept(self):
        obj, err = core.run_projection(self.selection)
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : CALIBRATION KERF
# ==========================================================================
class TaskPanelKerf:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)

        self.spn_size = QtWidgets.QDoubleSpinBox()
        self.spn_size.setRange(1.0, 200.0)
        self.spn_size.setValue(20.0)
        self.spn_size.setSuffix(" mm")
        self.spn_size.setToolTip(
            "Côté du carré généré (mm). Plus grand = mesure au pied à\n"
            "coulisse plus précise (l'erreur de mesure pèse moins sur le\n"
            "résultat), mais consomme davantage de matière pour le test.")
        form.addRow("Taille du carré test :", self.spn_size)

        lbl = QtWidgets.QLabel(
            "Crée un carré test. Découpe-le en mode Découpe multi-passes\n"
            "avec Compensation de kerf = 0, puis mesure la pièce obtenue :\n"
            "kerf = taille dessinée - taille mesurée.")
        lbl.setWordWrap(True)
        form.addRow(lbl)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Calibration kerf")
        self.form.setWindowIcon(_icon("kerf.svg"))

    def accept(self):
        obj, err = core.create_kerf_test_pattern(self.spn_size.value())
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : BANDE DE CALIBRATION DÉFOCUS
# ==========================================================================
class TaskPanelDefocusCalibration:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Grave une rangée de courts traits, chacun à une hauteur de bec\n"
            "croissante (étiquetée en mm). MESURE l'épaisseur de chaque\n"
            "trait : le plus fin = le foyer (sa hauteur = ton Z de foyer, sa\n"
            "largeur = « point au foyer ») ; choisis un trait bien plus\n"
            "large pour « défocus de test » (sa hauteur - celle du foyer) et\n"
            "« point au défocus de test » (sa largeur). Zéro Z sur la\n"
            "surface. Aucune sélection requise.")
        info.setWordWrap(True)
        form.addRow(info)

        self.spn_zstart = QtWidgets.QDoubleSpinBox()
        self.spn_zstart.setRange(-50, 200)
        self.spn_zstart.setDecimals(2)
        self.spn_zstart.setSingleStep(0.25)
        self.spn_zstart.setValue(0.0)
        self.spn_zstart.setSuffix(" mm")
        self.spn_zstart.setToolTip(
            "Hauteur du bec du 1er trait (Z=0 = bec touche la surface).\n"
            "Commence un peu en dessous du foyer présumé.")
        form.addRow("Z de départ :", self.spn_zstart)

        self.spn_zstep = QtWidgets.QDoubleSpinBox()
        self.spn_zstep.setRange(0.05, 50.0)
        self.spn_zstep.setDecimals(2)
        self.spn_zstep.setSingleStep(0.25)
        self.spn_zstep.setValue(2.0)
        self.spn_zstep.setSuffix(" mm")
        self.spn_zstep.setToolTip(
            "Pas de hauteur entre deux traits. Petit pas près du foyer\n"
            "(pour bien le cerner) ; ton faisceau divergeant lentement, un\n"
            "grand nombre de traits couvre une large plage.")
        form.addRow("Pas de hauteur :", self.spn_zstep)

        self.spn_nmarks = QtWidgets.QSpinBox()
        self.spn_nmarks.setRange(2, 100)
        self.spn_nmarks.setValue(20)
        self.spn_nmarks.setToolTip("Nombre de traits (donc de hauteurs testées).")
        form.addRow("Nombre de traits :", self.spn_nmarks)

        self.spn_length = QtWidgets.QDoubleSpinBox()
        self.spn_length.setRange(2.0, 200.0)
        self.spn_length.setValue(15.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.setToolTip("Longueur de chaque trait (plus long = plus facile à mesurer).")
        form.addRow("Longueur des traits :", self.spn_length)

        self.spn_rowgap = QtWidgets.QDoubleSpinBox()
        self.spn_rowgap.setRange(1.0, 50.0)
        self.spn_rowgap.setValue(8.0)
        self.spn_rowgap.setSuffix(" mm")
        self.spn_rowgap.setToolTip(
            "Espace vertical entre deux traits -- assez grand pour que les\n"
            "traits les plus larges (fort défocus) ne se touchent pas.")
        form.addRow("Espacement des traits :", self.spn_rowgap)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(300)
        self.spn_power.setToolTip(
            "Puissance (S) du 1er trait (le plus bas, près du foyer).\n"
            "Modérée : assez pour marquer, pas trop pour que la brûlure ne\n"
            "s'élargisse pas au-delà du point (ce qui fausserait la mesure).")
        form.addRow("Puissance 1er trait (bas) :", self.spn_power)

        self.spn_power_end = QtWidgets.QDoubleSpinBox()
        self.spn_power_end.setRange(0, 1000)
        self.spn_power_end.setValue(800)
        self.spn_power_end.setToolTip(
            "Puissance (S) du DERNIER trait (le plus défocalisé). Plus haute\n"
            "que le 1er : à défocus élevé, le point est étalé donc le trait\n"
            "pâlit jusqu'à disparaître -- monter la puissance le maintient\n"
            "visible et mesurable. La puissance augmente progressivement du\n"
            "1er au dernier trait. Mets la même valeur que le 1er pour une\n"
            "puissance constante.")
        form.addRow("Puissance dernier trait (haut) :", self.spn_power_end)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(1000)
        self.spn_feed.setSuffix(" mm/min")
        self.spn_feed.setToolTip("Vitesse d'avance FIXE des traits.")
        form.addRow("Vitesse des traits :", self.spn_feed)

        self.chk_labels = QtWidgets.QCheckBox("Graver la hauteur (mm) à gauche")
        self.chk_labels.setChecked(True)
        self.chk_labels.setToolTip(
            "Grave à gauche de chaque trait sa hauteur en mm (décimale\n"
            "affichée au besoin, ex. 0.5).\n"
            "Gravées à hauteur fixe (le Z de départ) pour rester lisibles.")
        form.addRow(self.chk_labels)

        self.chk_power_labels = QtWidgets.QCheckBox("Graver la puissance (S) à droite")
        self.chk_power_labels.setChecked(True)
        self.chk_power_labels.setToolTip(
            "Grave à droite de chaque trait la puissance (S) qui l'a produit.\n"
            "Indispensable avec la rampe de puissance : sinon impossible de\n"
            "savoir quelle puissance a donné quel trait.")
        form.addRow(self.chk_power_labels)

        self.spn_label_power = QtWidgets.QDoubleSpinBox()
        self.spn_label_power.setRange(0, 1000)
        self.spn_label_power.setValue(300)
        self.spn_label_power.setToolTip("Puissance (S) des étiquettes.")
        form.addRow("Puissance étiquettes :", self.spn_label_power)

        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setValue(1500)
        self.spn_label_feed.setSuffix(" mm/min")
        self.spn_label_feed.setToolTip("Vitesse d'avance des étiquettes.")
        form.addRow("Vitesse étiquettes :", self.spn_label_feed)

        def _sync_label_fields():
            on = self.chk_labels.isChecked() or self.chk_power_labels.isChecked()
            self.spn_label_power.setEnabled(on)
            self.spn_label_feed.setEnabled(on)
        self.chk_labels.toggled.connect(lambda _v: _sync_label_fields())
        self.chk_power_labels.toggled.connect(lambda _v: _sync_label_fields())

        self.lbl_range = QtWidgets.QLabel("")
        self.lbl_range.setWordWrap(True)
        form.addRow(self.lbl_range)

        def _update_range():
            zmax = self.spn_zstart.value() + (self.spn_nmarks.value() - 1) * self.spn_zstep.value()
            self.lbl_range.setText("Plage balayée : Z {:.1f} à {:.1f} mm.".format(
                self.spn_zstart.value(), zmax))
        self.spn_zstart.valueChanged.connect(lambda _v: _update_range())
        self.spn_zstep.valueChanged.connect(lambda _v: _update_range())
        self.spn_nmarks.valueChanged.connect(lambda _v: _update_range())

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_dc", ""))
        self.txt_post.setPlainText(cfg.get("post_dc", ""))

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance, G0 (transit) à la\n"
            "vitesse rapide des Préférences.")

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Fichier à part traçant le rectangle englobant, à lancer seul\n"
            "pour vérifier le positionnement avant le vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Bande de calibration défocus")
        self.form.setWindowIcon(_icon("defocus.svg"))

        _update_range()
        self._update_duration_preview()

    def _gen_kwargs(self):
        return {
            "z_start": self.spn_zstart.value(),
            "z_step": self.spn_zstep.value(),
            "n_marks": self.spn_nmarks.value(),
            "mark_length": self.spn_length.value(),
            "row_gap": self.spn_rowgap.value(),
            "power": self.spn_power.value(),
            "power_end": self.spn_power_end.value(),
            "feed": self.spn_feed.value(),
            "draw_labels": self.chk_labels.isChecked(),
            "draw_power_labels": self.chk_power_labels.isChecked(),
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
        }

    def _update_duration_preview(self):
        gcode = core.generate_gcode_defocus_calibration(quiet=True, **self._gen_kwargs())
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        gcode = core.generate_gcode_defocus_calibration(frame_only=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_calibration_defocus.ngc")

    def _on_toolpath_preview(self):
        gcode = core.generate_gcode_defocus_calibration(quiet=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_defocus_calibration(
            pre_gcode=pre_text, post_gcode=post_text, **self._gen_kwargs())

        cfg = core.load_config()
        cfg["pre_dc"] = pre_text
        cfg["post_dc"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/calibration_defocus.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : GRILLE DE TEST PUISSANCE / VITESSE
# ==========================================================================
class TaskPanelTestGrid:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Génère en un seul job une grille de cellules couvrant une\n"
            "plage de puissance x vitesse, pour choisir à l'œil le\n"
            "meilleur réglage sur une chute du matériau visé, au lieu de\n"
            "tâtonner passe par passe. La position de chaque cellule est\n"
            "son étiquette (puissance croissante en X, vitesse croissante\n"
            "en Y) -- la grille complète est aussi imprimée dans la vue\n"
            "Rapport. Aucune sélection requise.")
        info.setWordWrap(True)
        form.addRow(info)

        # --- Préréglages nommés (par matériau) : même mécanique et même
        # fichier de config que les modes Marquage courbe / Découpe
        # multi-passes, catégorie "testgrid". Ici TOUS les réglages de la
        # grille sont couverts (pas seulement puissance/vitesse). ---
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Recharge un jeu complet de réglages de grille sauvegardé sous\n"
            "un nom (typiquement : un matériau). Survole un nom dans la\n"
            "liste pour voir le résumé de ses réglages avant de choisir.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.lbl_preset_summary = QtWidgets.QLabel("")
        self.lbl_preset_summary.setWordWrap(True)
        self.lbl_preset_summary.setVisible(False)
        form.addRow(self.lbl_preset_summary)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip(
            "Sauvegarde les valeurs actuelles de TOUT le panneau sous un\n"
            "nom de préréglage (un nom déjà existant est remplacé).")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Gravure (remplissage)", "Découpe (contour)"])
        # Même repli que le combo "Type de remplissage" du mode Hachures :
        # sans ça, la boîte se dimensionne sur l'item le plus long de la
        # liste et déborde du panneau étroit.
        self.combo_mode.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mode.setMinimumContentsLength(17)
        self.combo_mode.setToolTip(
            "Gravure : chaque cellule est remplie de hachures parallèles\n"
            "(comme le mode Hachures 2D) et gravée à sa puissance/vitesse.\n"
            "Découpe : chaque cellule est un simple contour carré, découpé\n"
            "(une seule passe) à sa puissance/vitesse -- pour vérifier à\n"
            "quelle combinaison le matériau se traverse proprement.")
        form.addRow("Mode de test :", self.combo_mode)

        self.spn_power_min = QtWidgets.QDoubleSpinBox()
        self.spn_power_min.setRange(0, 1000)
        self.spn_power_min.setValue(200)
        self.spn_power_min.setToolTip(
            "Puissance (valeur S) de la 1ère colonne (X minimal) de la\n"
            "grille -- la plus faible testée.")
        form.addRow("Puissance min (S) :", self.spn_power_min)

        self.spn_power_max = QtWidgets.QDoubleSpinBox()
        self.spn_power_max.setRange(0, 1000)
        self.spn_power_max.setValue(800)
        self.spn_power_max.setToolTip(
            "Puissance (valeur S) de la dernière colonne (X maximal) de\n"
            "la grille -- la plus forte testée.")
        form.addRow("Puissance max (S) :", self.spn_power_max)

        self.spn_power_steps = QtWidgets.QSpinBox()
        self.spn_power_steps.setRange(1, 20)
        self.spn_power_steps.setValue(4)
        self.spn_power_steps.setToolTip(
            "Nombre de colonnes (valeurs de puissance testées), réparties\n"
            "régulièrement entre min et max. 1 = une seule colonne, à la\n"
            "valeur min.")
        form.addRow("Nombre de puissances :", self.spn_power_steps)

        self.spn_feed_min = QtWidgets.QDoubleSpinBox()
        self.spn_feed_min.setRange(1, 20000)
        self.spn_feed_min.setValue(500)
        self.spn_feed_min.setSuffix(" mm/min")
        self.spn_feed_min.setToolTip(
            "Vitesse d'avance de la 1ère ligne (Y minimal) de la grille --\n"
            "la plus lente testée.")
        form.addRow("Vitesse min (Feed) :", self.spn_feed_min)

        self.spn_feed_max = QtWidgets.QDoubleSpinBox()
        self.spn_feed_max.setRange(1, 20000)
        self.spn_feed_max.setValue(3000)
        self.spn_feed_max.setSuffix(" mm/min")
        self.spn_feed_max.setToolTip(
            "Vitesse d'avance de la dernière ligne (Y maximal) de la\n"
            "grille -- la plus rapide testée.")
        form.addRow("Vitesse max (Feed) :", self.spn_feed_max)

        self.spn_feed_steps = QtWidgets.QSpinBox()
        self.spn_feed_steps.setRange(1, 20)
        self.spn_feed_steps.setValue(4)
        self.spn_feed_steps.setToolTip(
            "Nombre de lignes (valeurs de vitesse testées), réparties\n"
            "régulièrement entre min et max. 1 = une seule ligne, à la\n"
            "valeur min.")
        form.addRow("Nombre de vitesses :", self.spn_feed_steps)

        self.spn_cell_size = QtWidgets.QDoubleSpinBox()
        self.spn_cell_size.setRange(2.0, 100.0)
        self.spn_cell_size.setValue(10.0)
        self.spn_cell_size.setSuffix(" mm")
        self.spn_cell_size.setToolTip(
            "Côté de chaque cellule carrée de la grille. Plus grand =\n"
            "plus facile à juger à l'œil/au toucher, mais grille totale\n"
            "plus grande (consomme davantage de matière pour le test).")
        form.addRow("Taille de cellule :", self.spn_cell_size)

        self.spn_gap = QtWidgets.QDoubleSpinBox()
        self.spn_gap.setRange(0.5, 50.0)
        self.spn_gap.setValue(3.0)
        self.spn_gap.setSuffix(" mm")
        self.spn_gap.setToolTip(
            "Espace laissé entre deux cellules voisines -- évite qu'une\n"
            "cellule à forte puissance/faible vitesse (marquage plus\n"
            "prononcé) ne déborde visuellement sur sa voisine.")
        form.addRow("Espacement cellules :", self.spn_gap)

        self.combo_filltype = QtWidgets.QComboBox()
        self.combo_filltype.addItems(["Parallèles", "Croisées (grille)", "Défocus (noir)"])
        # Même repli que le combo "Type de remplissage" du mode Hachures :
        # sans ça, la boîte se dimensionne sur l'item le plus long de la
        # liste et déborde du panneau étroit.
        self.combo_filltype.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filltype.setMinimumContentsLength(17)
        self.combo_filltype.setToolTip(
            "Mode Gravure uniquement -- mêmes 3 types que le mode Hachures\n"
            "2D. Parallèles : lignes droites toutes dans le même sens.\n"
            "Croisées : les mêmes lignes doublées à angle+90 (grille),\n"
            "deux fois plus de trait. Défocus : même tracé que Parallèles,\n"
            "mais gravé avec le point laser élargi (calibration ci-dessous)\n"
            "-- les cellules sont alors gravées à un Z différent (bec\n"
            "écarté du foyer) des étiquettes, qui restent nettes au foyer\n"
            "normal.")
        form.addRow("Type de remplissage :", self.combo_filltype)

        self.spn_hatch_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_hatch_spacing.setRange(0.05, 5.0)
        self.spn_hatch_spacing.setValue(0.2)
        self.spn_hatch_spacing.setDecimals(2)
        self.spn_hatch_spacing.setSuffix(" mm")
        self.spn_hatch_spacing.setToolTip(
            "Mode Gravure uniquement : espacement des hachures de\n"
            "remplissage de chaque cellule (voir le mode Hachures 2D pour\n"
            "le même paramètre -- ici fixe, identique pour toutes les\n"
            "cellules, seules puissance/vitesse varient d'une cellule à\n"
            "l'autre). En Défocus, c'est aussi l'espacement visé par le\n"
            "calcul du défocus ci-dessous.")
        form.addRow("Espacement hachures :", self.spn_hatch_spacing)

        self.spn_hatch_angle = QtWidgets.QDoubleSpinBox()
        self.spn_hatch_angle.setRange(-360, 360)
        self.spn_hatch_angle.setValue(45)
        self.spn_hatch_angle.setSuffix(" deg")
        self.spn_hatch_angle.setToolTip(
            "Mode Gravure uniquement : orientation des hachures de\n"
            "remplissage, identique pour toutes les cellules. En mode\n"
            "Croisées, la 2e passe est automatiquement à cet angle + 90 deg.")
        form.addRow("Angle hachures :", self.spn_hatch_angle)

        self._gravure_widgets = [self.combo_filltype, self.spn_hatch_spacing, self.spn_hatch_angle]

        self.lbl_defocus_calib = QtWidgets.QLabel(
            "<b>Calibration du point laser</b> -- brûle 2 points test (au\n"
            "foyer, puis à un défocus connu) et mesure leur diamètre :")
        self.lbl_defocus_calib.setWordWrap(True)
        form.addRow(self.lbl_defocus_calib)

        self.spn_dfocus = QtWidgets.QDoubleSpinBox()
        self.spn_dfocus.setRange(0.01, 20.0)
        self.spn_dfocus.setValue(0.15)
        self.spn_dfocus.setDecimals(3)
        self.spn_dfocus.setSuffix(" mm")
        self.spn_dfocus.setToolTip(
            "Diamètre du point laser AU FOYER (Z de travail normal). À\n"
            "MESURER réellement -- 0.15mm n'est qu'une valeur de départ,\n"
            "pas une donnée constructeur.")
        form.addRow("Point au foyer (mesuré) :", self.spn_dfocus)

        self.spn_ztest = QtWidgets.QDoubleSpinBox()
        self.spn_ztest.setRange(0.1, 50.0)
        self.spn_ztest.setValue(3.0)
        self.spn_ztest.setDecimals(2)
        self.spn_ztest.setSuffix(" mm")
        self.spn_ztest.setToolTip(
            "Défocus de test (bec écarté de cette distance du foyer)\n"
            "utilisé pour la 2e mesure.")
        form.addRow("Défocus de test :", self.spn_ztest)

        self.spn_dtest = QtWidgets.QDoubleSpinBox()
        self.spn_dtest.setRange(0.01, 30.0)
        self.spn_dtest.setValue(1.0)
        self.spn_dtest.setDecimals(3)
        self.spn_dtest.setSuffix(" mm")
        self.spn_dtest.setToolTip("Diamètre du point laser mesuré à ce défocus de test.")
        form.addRow("Point au défocus de test (mesuré) :", self.spn_dtest)

        self.lbl_defocus_result = QtWidgets.QLabel("Défocus calculé : --")
        self.lbl_defocus_result.setWordWrap(True)
        form.addRow(self.lbl_defocus_result)

        self._defocus_widgets = [
            self.lbl_defocus_calib, self.spn_dfocus, self.spn_ztest,
            self.spn_dtest, self.lbl_defocus_result,
        ]

        self.spn_zwork = QtWidgets.QDoubleSpinBox()
        self.spn_zwork.setRange(-50, 200)
        self.spn_zwork.setValue(4.0)
        self.spn_zwork.setSuffix(" mm")
        self.spn_zwork.setToolTip(
            "Z de travail FIXE pour toute la grille (pas de sonde/\n"
            "courbure, la grille est destinée à une chute posée à plat) :\n"
            "en Gravure, la hauteur qui met le laser au point (foyer). En\n"
            "Découpe, la hauteur du bec au-dessus de la surface (voir le\n"
            "mode Découpe multi-passes, Z=0 = bec touche la surface). En\n"
            "remplissage Défocus, cette valeur reste le foyer utilisé pour\n"
            "les étiquettes -- les cellules sont automatiquement décalées\n"
            "du défocus calculé ci-dessus.")
        form.addRow("Z de travail :", self.spn_zwork)

        self.lbl_total = QtWidgets.QLabel("Total : -- cellules")
        self.lbl_total.setWordWrap(True)
        form.addRow(self.lbl_total)

        def _update_total_preview():
            n = self.spn_power_steps.value() * self.spn_feed_steps.value()
            size = self.spn_cell_size.value()
            gap = self.spn_gap.value()
            width = self.spn_power_steps.value() * size + (self.spn_power_steps.value() - 1) * gap
            height = self.spn_feed_steps.value() * size + (self.spn_feed_steps.value() - 1) * gap
            self.lbl_total.setText(
                "Total : {} cellules -- encombrement grille {:.0f} x {:.0f} mm".format(n, width, height))

        def _update_defocus_preview():
            half_angle = core.defocus_divergence_half_angle(
                self.spn_dfocus.value(), self.spn_dtest.value(), self.spn_ztest.value())
            defocus = core.defocus_for_fill_spacing(
                self.spn_hatch_spacing.value(), self.spn_dfocus.value(), half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration invalide : le point\n"
                    "mesuré au défocus de test doit être strictement plus\n"
                    "large que celui mesuré au foyer)")
            else:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.3f} mm -- Z cellules = Z de travail\n"
                    "+ cette valeur (étiquettes toujours au foyer).".format(defocus))

        def _update_visibility():
            is_gravure = (self.combo_mode.currentIndex() == 0)
            is_defocus = is_gravure and (self.combo_filltype.currentIndex() == 2)
            for w in self._gravure_widgets:
                w.setVisible(is_gravure)
            for w in self._defocus_widgets:
                w.setVisible(is_defocus)
            _update_defocus_preview()

        self.combo_mode.currentIndexChanged.connect(lambda _i: _update_visibility())
        self.combo_filltype.currentIndexChanged.connect(lambda _i: _update_visibility())
        self.spn_hatch_spacing.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dfocus.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_ztest.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_dtest.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_power_steps.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_feed_steps.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_cell_size.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_gap.valueChanged.connect(lambda _v: _update_total_preview())
        _update_visibility()
        _update_total_preview()

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        self.chk_proximity.setToolTip(
            "Réordonne les chaînes (cellules et étiquettes) par plus\n"
            "proche voisin (heuristique, comme le mode Découpe\n"
            "multi-passes) pour réduire les déplacements à vide -- calculé\n"
            "SÉPARÉMENT pour les cellules et les étiquettes (jamais\n"
            "mélangées) afin de garder un minimum de changements de Z.")
        form.addRow(self.chk_proximity)

        self.chk_labels = QtWidgets.QCheckBox("Graver les étiquettes S/F (colonnes/lignes)")
        self.chk_labels.setChecked(True)
        self.chk_labels.setToolTip(
            "Grave directement sur la pièce une étiquette par colonne\n"
            "(ex: \"S400\", sous la grille) et par ligne (ex: \"F1500\", à\n"
            "gauche de la grille) -- pour lire la puissance/vitesse d'une\n"
            "cellule sans avoir à recompter depuis un bord. Police\n"
            "vectorielle maison (chiffres + S/F uniquement, pas de fichier\n"
            "de police externe requis).")
        form.addRow(self.chk_labels)

        self.spn_label_power = QtWidgets.QDoubleSpinBox()
        self.spn_label_power.setRange(0, 1000)
        self.spn_label_power.setValue(300)
        self.spn_label_power.setToolTip(
            "Puissance (valeur S) FIXE pour graver les étiquettes --\n"
            "séparée des puissances en cours de test, pour rester lisible\n"
            "quelle que soit la plage testée (y compris si la puissance\n"
            "min testée est 0).")
        form.addRow("Puissance étiquettes :", self.spn_label_power)

        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setValue(1500)
        self.spn_label_feed.setSuffix(" mm/min")
        self.spn_label_feed.setToolTip(
            "Vitesse d'avance FIXE pour graver les étiquettes -- séparée\n"
            "des vitesses en cours de test.")
        form.addRow("Vitesse étiquettes :", self.spn_label_feed)

        self.chk_labels.toggled.connect(self.spn_label_power.setEnabled)
        self.chk_labels.toggled.connect(self.spn_label_feed.setEnabled)

        self.chk_border = QtWidgets.QCheckBox("Cadre net autour de chaque carré (au foyer)")
        self.chk_border.setChecked(True)
        self.chk_border.setToolTip(
            "Grave le contour carré de chaque cellule, NET AU FOYER, à un Z\n"
            "propre (ci-dessous). Utile surtout en remplissage Défocus, où\n"
            "les cellules sont volontairement floues : le cadre au foyer\n"
            "délimite clairement chaque carré. Indépendant du Z des\n"
            "cellules (qui peut être décalé par le défocus).")
        form.addRow(self.chk_border)

        self.spn_border_z = QtWidgets.QDoubleSpinBox()
        self.spn_border_z.setRange(-50, 200)
        self.spn_border_z.setDecimals(2)
        self.spn_border_z.setValue(8.5)
        self.spn_border_z.setSuffix(" mm")
        self.spn_border_z.setToolTip(
            "Z de foyer auquel le cadre est gravé (bec au point sur la\n"
            "surface = trait le plus fin). Indépendant du « Z de travail »\n"
            "des cellules : ainsi le cadre reste net même quand les\n"
            "cellules sont gravées en défocus.")
        form.addRow("Z du cadre (foyer) :", self.spn_border_z)

        self.spn_border_power = QtWidgets.QDoubleSpinBox()
        self.spn_border_power.setRange(0, 1000)
        self.spn_border_power.setValue(300)
        self.spn_border_power.setToolTip(
            "Puissance (valeur S) FIXE du cadre -- séparée des puissances\n"
            "en cours de test, pour un contour lisible quelle que soit la\n"
            "plage testée.")
        form.addRow("Puissance cadre :", self.spn_border_power)

        self.spn_border_feed = QtWidgets.QDoubleSpinBox()
        self.spn_border_feed.setRange(1, 20000)
        self.spn_border_feed.setValue(1000)
        self.spn_border_feed.setSuffix(" mm/min")
        self.spn_border_feed.setToolTip(
            "Vitesse d'avance FIXE du cadre -- séparée des vitesses en\n"
            "cours de test.")
        form.addRow("Vitesse cadre :", self.spn_border_feed)

        self.chk_border.toggled.connect(self.spn_border_z.setEnabled)
        self.chk_border.toggled.connect(self.spn_border_power.setEnabled)
        self.chk_border.toggled.connect(self.spn_border_feed.setEnabled)

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART qui trace uniquement le rectangle\n"
            "englobant de toute la grille, laser éteint (ou faisceau de\n"
            "visée très faible : voir « Puissance de cadrage » dans les\n"
            "Préférences) -- à lancer seul\n"
            "sur la machine pour vérifier le positionnement AVANT de\n"
            "lancer la grille réelle (bouton OK). Volontairement séparé\n"
            "du job réel : pas de risque de le lancer en pensant vérifier\n"
            "alors que le laser va réellement graver/découper juste après.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel dans la vue 3D de FreeCAD : gris fin =\n"
            "transit laser éteint (G0), rouge épais = gravure/découpe\n"
            "laser allumé (G1). Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        self.txt_pre.setToolTip(
            "Texte libre inséré tel quel juste avant le début du job (après\n"
            "G21/G90/G94 et la remontée de sécurité initiale, avant\n"
            "l'armement du laser). Sauvegardé d'une exécution à l'autre.")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        self.txt_post.setToolTip(
            "Texte libre inséré tel quel juste APRÈS le désarmement du\n"
            "laser (M5), avant la fin du programme (M2). Sauvegardé d'une\n"
            "exécution à l'autre.")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_t", ""))
        self.txt_post.setPlainText(cfg.get("post_t", ""))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Grille de test puissance/vitesse")
        self.form.setWindowIcon(_icon("testgrid.svg"))

        self._populate_preset_combo()
        self._update_duration_preview()

    # --- Préréglages nommés (catégorie "testgrid") ---
    @staticmethod
    def _preset_summary(values):
        """Résumé lisible d'un préréglage -- affiché en infobulle de
        chaque nom dans la liste ET sous le sélecteur une fois choisi,
        pour comparer les préréglages sans avoir à les charger."""
        mode = values.get("mode", 0)
        lines = ["{} -- S {:g} à {:g} (x{}), F {:g} à {:g} mm/min (x{})".format(
            "Découpe" if mode == 1 else "Gravure",
            values.get("power_min", 0), values.get("power_max", 0),
            values.get("power_steps", 0),
            values.get("feed_min", 0), values.get("feed_max", 0),
            values.get("feed_steps", 0))]
        line2 = "Cellules {:g} mm, espace {:g} mm, Z {:g} mm".format(
            values.get("cell_size", 0), values.get("gap", 0), values.get("zwork", 0))
        if mode == 0:
            filltypes = ("Parallèles", "Croisées", "Défocus")
            filltype = values.get("filltype", 0)
            line2 += ", {} {:g} mm @ {:g} deg".format(
                filltypes[filltype] if 0 <= filltype < len(filltypes) else "?",
                values.get("hatch_spacing", 0), values.get("hatch_angle", 0))
        lines.append(line2)
        if values.get("labels", True):
            lines.append("Étiquettes S{:g} F{:g}".format(
                values.get("label_power", 0), values.get("label_feed", 0)))
        if values.get("border_enabled", True):
            lines.append("Cadre au foyer S{:g} F{:g} Z{:g}".format(
                values.get("border_power", 0), values.get("border_feed", 0),
                values.get("border_z", 0)))
        return "\n".join(lines)

    def _border_kwargs(self):
        """Paramètres du cadre net passés au générateur (partagés par
        accept, aperçu trajet et estimation de durée)."""
        return {
            "draw_border": self.chk_border.isChecked(),
            "z_border": self.spn_border_z.value(),
            "border_power": self.spn_border_power.value(),
            "border_feed": self.spn_border_feed.value(),
        }

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --")
        presets = core.load_presets("testgrid")
        for name in sorted(presets):
            self.combo_preset.addItem(name)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1,
                self._preset_summary(presets[name]),
                QtCore.Qt.ToolTipRole)
        self.combo_preset.blockSignals(False)
        self.lbl_preset_summary.setVisible(False)

    def _preset_values(self):
        return {
            "mode": self.combo_mode.currentIndex(),
            "power_min": self.spn_power_min.value(),
            "power_max": self.spn_power_max.value(),
            "power_steps": self.spn_power_steps.value(),
            "feed_min": self.spn_feed_min.value(),
            "feed_max": self.spn_feed_max.value(),
            "feed_steps": self.spn_feed_steps.value(),
            "cell_size": self.spn_cell_size.value(),
            "gap": self.spn_gap.value(),
            "filltype": self.combo_filltype.currentIndex(),
            "hatch_spacing": self.spn_hatch_spacing.value(),
            "hatch_angle": self.spn_hatch_angle.value(),
            "dfocus": self.spn_dfocus.value(),
            "ztest": self.spn_ztest.value(),
            "dtest": self.spn_dtest.value(),
            "zwork": self.spn_zwork.value(),
            "proximity": self.chk_proximity.isChecked(),
            "labels": self.chk_labels.isChecked(),
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
            "border_enabled": self.chk_border.isChecked(),
            "border_z": self.spn_border_z.value(),
            "border_power": self.spn_border_power.value(),
            "border_feed": self.spn_border_feed.value(),
        }

    def _on_preset_selected(self, index):
        if index <= 0:
            self.lbl_preset_summary.setVisible(False)
            return
        values = core.load_presets("testgrid").get(self.combo_preset.currentText())
        if not values:
            return
        self.combo_mode.setCurrentIndex(values.get("mode", self.combo_mode.currentIndex()))
        self.spn_power_min.setValue(values.get("power_min", self.spn_power_min.value()))
        self.spn_power_max.setValue(values.get("power_max", self.spn_power_max.value()))
        self.spn_power_steps.setValue(values.get("power_steps", self.spn_power_steps.value()))
        self.spn_feed_min.setValue(values.get("feed_min", self.spn_feed_min.value()))
        self.spn_feed_max.setValue(values.get("feed_max", self.spn_feed_max.value()))
        self.spn_feed_steps.setValue(values.get("feed_steps", self.spn_feed_steps.value()))
        self.spn_cell_size.setValue(values.get("cell_size", self.spn_cell_size.value()))
        self.spn_gap.setValue(values.get("gap", self.spn_gap.value()))
        self.combo_filltype.setCurrentIndex(values.get("filltype", self.combo_filltype.currentIndex()))
        self.spn_hatch_spacing.setValue(values.get("hatch_spacing", self.spn_hatch_spacing.value()))
        self.spn_hatch_angle.setValue(values.get("hatch_angle", self.spn_hatch_angle.value()))
        self.spn_dfocus.setValue(values.get("dfocus", self.spn_dfocus.value()))
        self.spn_ztest.setValue(values.get("ztest", self.spn_ztest.value()))
        self.spn_dtest.setValue(values.get("dtest", self.spn_dtest.value()))
        self.spn_zwork.setValue(values.get("zwork", self.spn_zwork.value()))
        self.chk_proximity.setChecked(values.get("proximity", self.chk_proximity.isChecked()))
        self.chk_labels.setChecked(values.get("labels", self.chk_labels.isChecked()))
        self.spn_label_power.setValue(values.get("label_power", self.spn_label_power.value()))
        self.spn_label_feed.setValue(values.get("label_feed", self.spn_label_feed.value()))
        self.chk_border.setChecked(values.get("border_enabled", self.chk_border.isChecked()))
        self.spn_border_z.setValue(values.get("border_z", self.spn_border_z.value()))
        self.spn_border_power.setValue(values.get("border_power", self.spn_border_power.value()))
        self.spn_border_feed.setValue(values.get("border_feed", self.spn_border_feed.value()))
        self.lbl_preset_summary.setText(self._preset_summary(values))
        self.lbl_preset_summary.setVisible(True)

    def _on_save_preset(self):
        current = self.combo_preset.currentText() if self.combo_preset.currentIndex() > 0 else ""
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Sauvegarder le préréglage",
            "Nom du préréglage (matériau) :", text=current)
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("testgrid", name, self._preset_values())
        self._populate_preset_combo()
        idx = self.combo_preset.findText(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        index = self.combo_preset.currentIndex()
        if index <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QtWidgets.QMessageBox.question(
            self.form, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset("testgrid", name)
        self._populate_preset_combo()

    def _update_duration_preview(self):
        if self.spn_power_max.value() < self.spn_power_min.value() or self.spn_feed_max.value() < self.spn_feed_min.value():
            self.lbl_duration.setText("Durée estimée : -- (vérifie les plages puissance/vitesse)")
            return
        mode, fill_type, cells, cell_z_offset = self._build_cells(silent=True)
        if cells is None:
            self.lbl_duration.setText("Durée estimée : -- (calibration défocus invalide)")
            return
        _, _, label_edges = self._build_label_edges(cells)
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(), label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset, quiet=True, **self._border_kwargs()
        )
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _build_cells(self, silent=False):
        """Construit (mode, fill_type, cells, cell_z_offset) à partir des
        champs actuels, ou (None, None, None, None) si la calibration
        Défocus est invalide (message d'erreur affiché, sauf si
        silent=True -- utilisé par l'aperçu de durée EN DIRECT, qui ne
        doit pas ouvrir une boîte de dialogue à chaque frappe). Partagé
        par accept(), _on_frame_preview() et _update_duration_preview()
        pour ne jamais diverger."""
        mode = "gravure" if self.combo_mode.currentIndex() == 0 else "decoupe"
        fill_type_map = {0: "paralleles", 1: "croisees", 2: "defocus"}
        fill_type = fill_type_map.get(self.combo_filltype.currentIndex(), "paralleles") if mode == "gravure" else "paralleles"

        cell_z_offset = 0.0
        fill_inset = 0.0
        if mode == "gravure" and fill_type == "defocus":
            half_angle = core.defocus_divergence_half_angle(
                self.spn_dfocus.value(), self.spn_dtest.value(), self.spn_ztest.value())
            defocus = core.defocus_for_fill_spacing(
                self.spn_hatch_spacing.value(), self.spn_dfocus.value(), half_angle)
            if defocus is None:
                if not silent:
                    QtWidgets.QMessageBox.critical(
                        self.form, "Erreur",
                        "Calibration de défocus invalide : le point mesuré au\n"
                        "défocus de test doit être strictement plus large que\n"
                        "celui mesuré au foyer.")
                return None, None, None, None
            cell_z_offset = defocus
            # Rayon du point élargi à ce défocus : on rentre la zone
            # hachurée d'autant pour que la brûlure ne déborde pas du carré.
            spot = core.spot_diameter_at_defocus(defocus, self.spn_dfocus.value(), half_angle)
            fill_inset = spot / 2.0

        cells = core.build_test_grid_cells(
            mode,
            self.spn_power_min.value(), self.spn_power_max.value(), self.spn_power_steps.value(),
            self.spn_feed_min.value(), self.spn_feed_max.value(), self.spn_feed_steps.value(),
            self.spn_cell_size.value(), self.spn_gap.value(),
            fill_type=fill_type,
            hatch_spacing=self.spn_hatch_spacing.value(), hatch_angle=self.spn_hatch_angle.value(),
            fill_inset=fill_inset,
        )
        return mode, fill_type, cells, cell_z_offset

    def _build_label_edges(self, cells):
        power_labels, feed_labels = core.build_test_grid_axis_labels(
            cells, self.spn_power_steps.value(), self.spn_feed_steps.value(),
            self.spn_cell_size.value(), self.spn_gap.value())
        label_edges = []
        for lbl in power_labels:
            label_edges.extend(lbl["edges"])
        for lbl in feed_labels:
            label_edges.extend(lbl["edges"])
        return power_labels, feed_labels, label_edges

    def _on_frame_preview(self):
        if self.spn_power_max.value() < self.spn_power_min.value() or self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Vérifie les plages puissance/vitesse (max >= min).")
            return
        mode, fill_type, cells, cell_z_offset = self._build_cells()
        if cells is None:
            return
        _, _, label_edges = self._build_label_edges(cells)
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(), label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset, frame_only=True,
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_grille.ngc")

    def _on_toolpath_preview(self):
        if self.spn_power_max.value() < self.spn_power_min.value() or self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Vérifie les plages puissance/vitesse (max >= min).")
            return
        mode, fill_type, cells, cell_z_offset = self._build_cells()
        if cells is None:
            return
        _, _, label_edges = self._build_label_edges(cells)
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(), label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(), quiet=True,
            **self._border_kwargs()
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        if self.spn_power_max.value() < self.spn_power_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Puissance max doit être >= puissance min.")
            return False
        if self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Vitesse max doit être >= vitesse min.")
            return False

        mode, fill_type, cells, cell_z_offset = self._build_cells()
        if cells is None:
            return False

        objs, err = core.create_test_grid_object(mode, cells)
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False

        power_labels, feed_labels, label_edges = self._build_label_edges(cells)
        label_obj, lbl_err = core.create_test_grid_label_object(power_labels, feed_labels)
        if lbl_err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", lbl_err)
            return False

        core.print_test_grid_legend(mode, cells, self.spn_power_steps.value(), self.spn_feed_steps.value())

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(),
            label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset,
            use_proximity=self.chk_proximity.isChecked(),
            pre_gcode=pre_text, post_gcode=post_text,
            **self._border_kwargs()
        )

        cfg = core.load_config()
        cfg["pre_t"] = pre_text
        cfg["post_t"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False

        FreeCAD.Console.PrintMessage("Succès : {} cellules créées.\n".format(len(objs)))
        if not _write_gcode_with_dialog(self.form, gcode, "/tmp/grille_test.ngc"):
            # Sauvegarde abandonnée : accept() échoue pour que le panneau
            # reste ouvert avec tous ses réglages. Les objets tout juste
            # créés sont retirés du document -- re-cliquer OK regénère
            # tout, les garder produirait des cellules en double.
            doc = FreeCAD.ActiveDocument
            for obj in objs + ([label_obj] if label_obj is not None else []):
                doc.removeObject(obj.Name)
            doc.recompute()
            return False
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : MARQUAGE SUR SURFACE COURBE
# ==========================================================================
class TaskPanelCurved:
    def __init__(self, selection):
        self.selection = selection
        self._edges, self._reference_shape = self._get_edges()
        # Sonde Z gardée pour toute la durée de vie du panneau : la surface
        # de référence ne change pas pendant que le panneau est ouvert, donc
        # les raycasts d'un premier calcul (ouverture, aperçu durée...)
        # profitent aux suivants au lieu d'être refaits à chaque fois.
        self._probe = core.make_ray_probe(self._reference_shape) if self._reference_shape is not None else None
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Pour que la gravure SUIVE FIDÈLEMENT LES COURBES du modèle\n"
            "3D, sélectionne à la fois le motif projeté (Hachures_3D, issu\n"
            "du mode Projection) ET le modèle 3D d'origine, TOUS LES DEUX\n"
            "EN MÊME TEMPS, avant de lancer ce mode. Le modèle 3D permet\n"
            "une sonde exacte du relief pendant le marquage -- si tu ne\n"
            "sélectionnes que le motif seul, le Z est seulement interpolé\n"
            "entre les points déjà projetés (moins fidèle, surtout si la\n"
            "courbure est marquée entre deux points).")
        info.setWordWrap(True)
        form.addRow(info)

        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/Z\n"
            "travail/marge) -- en choisir un remplit automatiquement les\n"
            "champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la gravure (valeur S, 0-1000 selon\n"
            "l'échelle de la machine). 0 = laser éteint -- utile pour\n"
            "vérifier le trajet (avec l'aperçu cadrage) sans marquer.")
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(1000)
        self.spn_feed.setSuffix(" mm/min")
        self.spn_feed.setToolTip(
            "Vitesse d'avance pendant la gravure (mm/min). Plus lent =\n"
            "marquage plus prononcé mais job plus long ; plus rapide =\n"
            "marquage plus léger.")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_zfocus = QtWidgets.QDoubleSpinBox()
        self.spn_zfocus.setRange(-50, 200)
        self.spn_zfocus.setValue(4.0)
        self.spn_zfocus.setSuffix(" mm")
        self.spn_zfocus.setToolTip(
            "Hauteur de travail (cale) : position Z qui met le laser au\n"
            "point (foyer) sur la surface à graver. À régler empiriquement\n"
            "(le trait le plus net possible) -- indépendante de la butée de\n"
            "bec calculée dans le mode Découpe multi-passes.")
        form.addRow("Z Travail (Cale) :", self.spn_zfocus)

        self.spn_marge = QtWidgets.QDoubleSpinBox()
        self.spn_marge.setRange(0.0, 20)
        self.spn_marge.setValue(0.5)
        self.spn_marge.setSuffix(" mm")
        self.spn_marge.setToolTip(
            "Marge fixe au-dessus de la hauteur de travail pendant le\n"
            "transit. Sonde exacte si l'objet 3D est aussi sélectionné,\n"
            "sinon interpolation.")
        form.addRow("Marge de sécurité (transit) :", self.spn_marge)

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART qui trace uniquement le rectangle\n"
            "englobant du motif, laser éteint (ou faisceau de visée très\n"
            "faible : voir « Puissance de cadrage » dans les Préférences)\n"
            "-- à lancer seul sur la\n"
            "machine pour vérifier le positionnement AVANT de lancer le\n"
            "vrai job (bouton OK). Volontairement séparé du job réel :\n"
            "pas de risque de le lancer en pensant vérifier alors que le\n"
            "laser va réellement graver juste après.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel dans la vue 3D de FreeCAD : gris fin =\n"
            "transit laser éteint (G0), rouge épais = gravure laser allumé\n"
            "(G1). Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        self.txt_pre.setToolTip(
            "Texte libre inséré tel quel juste avant le début du job (après\n"
            "G21/G90/G94 et la remontée de sécurité initiale, avant\n"
            "l'armement du laser) -- pour une instruction particulière\n"
            "(attente, message, M-code spécifique). Sauvegardé d'une\n"
            "exécution à l'autre.")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        self.txt_post.setToolTip(
            "Texte libre inséré tel quel juste après la remontée finale,\n"
            "AVANT le désarmement du laser (M5). Sauvegardé d'une exécution\n"
            "à l'autre.")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_c", ""))
        self.txt_post.setPlainText(cfg.get("post_c", ""))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Marquage sur surface courbe")
        self.form.setWindowIcon(_icon("curved.svg"))

        self._populate_preset_combo()
        self._update_duration_preview()

    def _get_edges(self):
        edge_sel, reference_shape = core.split_selection(self.selection)
        edges = core.get_all_edges_from_selection(edge_sel)
        return edges, reference_shape

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --")
        for name in sorted(core.load_presets("curved")):
            self.combo_preset.addItem(name)
        self.combo_preset.blockSignals(False)

    def _on_preset_selected(self, index):
        if index <= 0:
            return
        values = core.load_presets("curved").get(self.combo_preset.currentText())
        if not values:
            return
        self.spn_power.setValue(values.get("power", self.spn_power.value()))
        self.spn_feed.setValue(values.get("feed", self.spn_feed.value()))
        self.spn_zfocus.setValue(values.get("z_focus", self.spn_zfocus.value()))
        self.spn_marge.setValue(values.get("marge", self.spn_marge.value()))

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self.form, "Sauvegarder le préréglage", "Nom du préréglage :")
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("curved", name, {
            "power": self.spn_power.value(),
            "feed": self.spn_feed.value(),
            "z_focus": self.spn_zfocus.value(),
            "marge": self.spn_marge.value(),
        })
        self._populate_preset_combo()
        idx = self.combo_preset.findText(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        index = self.combo_preset.currentIndex()
        if index <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QtWidgets.QMessageBox.question(
            self.form, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset("curved", name)
        self._populate_preset_combo()

    def _on_toolpath_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_curved(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        # Le Z du G-code exporté est en repère MACHINE (calé sur le foyer,
        # cf. z_offset dans generate_gcode_curved), pas dans le repère
        # natif du document -- décalage à retirer ici pour que l'aperçu se
        # superpose correctement au modèle 3D dans la vue 3D (sinon le
        # trajet apparaît décalé sous/au-dessus de la surface).
        z_offset = core.curved_native_z_offset(self._edges, self.spn_zfocus.value())
        rapid = core.shift_segments_z(rapid, -z_offset)
        mark = core.shift_segments_z(mark, -z_offset)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def _update_duration_preview(self):
        if not self._edges:
            self.lbl_duration.setText("Durée estimée : -- (aucun segment dans la sélection)")
            return
        gcode = core.generate_gcode_curved(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
        )
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_curved(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, frame_only=True, probe=self._probe,
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_courbe.ngc")

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        FreeCAD.Console.PrintMessage(
            "Chaînage des segments connectés... ({})\n".format(
                "objet 3D de référence détecté" if self._reference_shape is not None else "pas d'objet 3D, interpolation"))

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_curved(
            self._edges,
            self.spn_power.value(),
            self.spn_feed.value(),
            self.spn_zfocus.value(),
            self.spn_marge.value(),
            reference_shape=self._reference_shape,
            pre_gcode=pre_text,
            post_gcode=post_text,
            probe=self._probe,
        )

        cfg = core.load_config()
        cfg["pre_c"] = pre_text
        cfg["post_c"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False

        # Renoncement à la sauvegarde : accept() échoue pour que le panneau
        # reste ouvert avec tous ses réglages -- re-cliquer OK regénère.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/marquage_courbe.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : DÉCOUPE MULTI-PASSES SUR MATÉRIAU PLAT
# ==========================================================================
class TaskPanelFlat:
    def __init__(self, selection):
        self.selection = selection
        self._edges = core.get_all_edges_from_selection(self.selection)
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/épaisseur/\n"
            "passes/finition/rampe/kerf) -- en choisir un remplit\n"
            "automatiquement les champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la découpe (valeur S, 0-1000 selon\n"
            "l'échelle de la machine). Fixe pour toutes les passes, sauf si\n"
            "la rampe de puissance ci-dessous est activée.")
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(300)
        self.spn_feed.setSuffix(" mm/min")
        self.spn_feed.setToolTip(
            "Vitesse d'avance pendant la découpe (mm/min), pour toutes les\n"
            "passes sauf la dernière si l'option 'Ralentir la dernière\n"
            "passe' est activée. Plus lent = coupe plus franche mais job\n"
            "plus long.")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_thickness = QtWidgets.QDoubleSpinBox()
        self.spn_thickness.setRange(0.1, 30)
        self.spn_thickness.setValue(5.0)
        self.spn_thickness.setSuffix(" mm")
        self.spn_thickness.setToolTip(
            "Plage testée par le constructeur : 2-8mm. Au-delà d'environ\n"
            "12mm (retours utilisateurs pour ce laser en plusieurs passes),\n"
            "résultat incertain -- à valider sur chute.")
        form.addRow("Épaisseur matériau :", self.spn_thickness)

        self.spn_passes = QtWidgets.QSpinBox()
        self.spn_passes.setRange(1, 50)
        self.spn_passes.setValue(3)
        self.spn_passes.setToolTip(
            "Nombre de passes pour traverser toute l'épaisseur. Le pas Z\n"
            "entre deux passes = épaisseur / nombre de passes -- garder un\n"
            "pas modeste (repère ~1.5mm) plutôt que peu de passes à grand\n"
            "pas (voir avertissement si le pas calculé est trop grand).")
        form.addRow("Nombre de passes :", self.spn_passes)

        self.lbl_zauto = QtWidgets.QLabel("Hauteur bec 1ère passe (calculée) : 0.000 mm")
        self.lbl_zauto.setWordWrap(True)
        self.lbl_zauto.setToolTip(
            "Z=0 = LE BEC TOUCHE LA SURFACE (ton zéro au papier). Valeur\n"
            "POSITIVE = hauteur du bec AU-DESSUS de la surface (jamais en\n"
            "dessous). Descend progressivement vers zéro au fil des passes,\n"
            "avec une butée de sécurité qui l'empêche d'aller plus bas que\n"
            "SAFE_MIN_NOZZLE_HEIGHT_MM.")
        form.addRow(self.lbl_zauto)

        self.chk_zoverride = QtWidgets.QCheckBox("Forcer une valeur Z manuelle")
        self.chk_zoverride.setToolTip(
            "Remplace la hauteur de bec calculée automatiquement (tableau\n"
            "constructeur, ci-dessus) par la valeur saisie à la main juste\n"
            "en dessous -- utile si la pièce réelle diffère du tableau ou\n"
            "hors de la plage testée.")
        form.addRow(self.chk_zoverride)

        self.spn_zstart = QtWidgets.QDoubleSpinBox()
        self.spn_zstart.setRange(0.1, 50)
        self.spn_zstart.setValue(5.0)
        self.spn_zstart.setSuffix(" mm")
        self.spn_zstart.setToolTip(
            "Hauteur du bec au-dessus de la surface pour la 1ère passe.\n"
            "Doit rester POSITIVE (Z=0 = bec touche la surface) -- une\n"
            "valeur négative commanderait le bec sous la surface.")
        self.spn_zstart.setEnabled(False)
        self.chk_zoverride.toggled.connect(self.spn_zstart.setEnabled)
        form.addRow("Z manuel (1ère passe, hauteur bec) :", self.spn_zstart)

        def _update_zauto_preview():
            t = self.spn_thickness.value()
            z = core.nozzle_height_for_thickness(t)
            warn = " (hors plage testée)" if t > core.MAX_THICKNESS_WARNING_MM else ""
            self.lbl_zauto.setText("Hauteur bec 1ère passe (calculée) : {:.3f} mm{}".format(z, warn))

        self.spn_thickness.valueChanged.connect(lambda _v: _update_zauto_preview())
        _update_zauto_preview()

        self.chk_finish = QtWidgets.QCheckBox("Ralentir la dernière passe")
        self.chk_finish.setToolTip(
            "Utilise une avance plus lente (ci-dessous) uniquement sur la\n"
            "toute dernière passe, pour un bord de coupe plus propre --\n"
            "c'est souvent là que la calcination/les bavures sont les plus\n"
            "visibles.")
        form.addRow(self.chk_finish)

        self.spn_finish_feed = QtWidgets.QDoubleSpinBox()
        self.spn_finish_feed.setRange(1, 20000)
        self.spn_finish_feed.setValue(150)
        self.spn_finish_feed.setSuffix(" mm/min")
        self.spn_finish_feed.setEnabled(False)
        self.spn_finish_feed.setToolTip(
            "Avance (mm/min) de la dernière passe seulement, si l'option\n"
            "ci-dessus est activée -- généralement plus lente que l'avance\n"
            "normale.")
        self.chk_finish.toggled.connect(self.spn_finish_feed.setEnabled)
        form.addRow("Avance dernière passe :", self.spn_finish_feed)

        self.chk_power_ramp = QtWidgets.QCheckBox("Puissance différente en dernière passe (rampe)")
        self.chk_power_ramp.setToolTip(
            "Fait varier la puissance linéairement de la 1ère à la dernière\n"
            "passe (au lieu d'une valeur fixe) -- utile si la puissance\n"
            "nécessaire change à mesure que la coupe s'approfondit.")
        form.addRow(self.chk_power_ramp)

        self.spn_power_end = QtWidgets.QDoubleSpinBox()
        self.spn_power_end.setRange(0, 1000)
        self.spn_power_end.setValue(0)
        self.spn_power_end.setEnabled(False)
        self.spn_power_end.setToolTip(
            "La puissance varie linéairement de 'Puissance' (1ère passe)\n"
            "à cette valeur (dernière passe).")
        self.chk_power_ramp.toggled.connect(self.spn_power_end.setEnabled)
        form.addRow("Puissance dernière passe :", self.spn_power_end)

        self.spn_kerf = QtWidgets.QDoubleSpinBox()
        self.spn_kerf.setRange(0.0, 5.0)
        self.spn_kerf.setDecimals(3)
        self.spn_kerf.setValue(0.0)
        self.spn_kerf.setSuffix(" mm")
        self.spn_kerf.setToolTip(
            "Largeur de trait mesurée (0 = désactivé). Le contour extérieur\n"
            "est agrandi et les trous/îlots rétrécis de la moitié de cette\n"
            "valeur, pour que la pièce finie sorte à la bonne cote.\n"
            "À mesurer sur une chute : coupe un carré, mesure l'écart avec\n"
            "la cote dessinée.")
        form.addRow("Compensation de kerf :", self.spn_kerf)

        self.chk_hole_first = QtWidgets.QCheckBox("Découper les trous/îlots avant le contour englobant")
        self.chk_hole_first.setChecked(True)
        self.chk_hole_first.setToolTip(
            "Chaque chaîne termine TOUTES ses passes avant de passer à la\n"
            "suivante (sinon 'avant' n'aurait pas de sens physique réel).\n"
            "Évite qu'une pièce intérieure déjà détachée ne bouge avant la\n"
            "découpe du contour extérieur.")
        form.addRow(self.chk_hole_first)

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        self.chk_proximity.setToolTip(
            "Réordonne les chaînes par plus proche voisin (heuristique) pour\n"
            "réduire les déplacements à vide. Appliqué à l'intérieur de\n"
            "chaque palier trou/extérieur si les deux options sont actives.")
        form.addRow(self.chk_proximity)

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART qui trace uniquement le rectangle\n"
            "englobant du motif, laser éteint (ou faisceau de visée très\n"
            "faible : voir « Puissance de cadrage » dans les Préférences)\n"
            "-- à lancer seul sur la\n"
            "machine pour vérifier le positionnement AVANT de lancer le\n"
            "vrai job (bouton OK). Volontairement séparé du job réel :\n"
            "pas de risque de le lancer en pensant vérifier alors que le\n"
            "laser va réellement découper juste après.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel dans la vue 3D de FreeCAD : gris fin =\n"
            "transit laser éteint (G0), rouge épais = découpe laser allumé\n"
            "(G1). Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        self.txt_pre.setToolTip(
            "Texte libre inséré tel quel juste avant le début du job (après\n"
            "G21/G90/G94 et la remontée de sécurité initiale, avant\n"
            "l'armement du laser). Sauvegardé d'une exécution à l'autre.")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        self.txt_post.setToolTip(
            "Texte libre inséré tel quel juste APRÈS le désarmement du\n"
            "laser (M5), avant la fin du programme (M2). Sauvegardé d'une\n"
            "exécution à l'autre.")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_f", ""))
        self.txt_post.setPlainText(cfg.get("post_f", ""))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Découpe multi-passes (matériau plat)")
        self.form.setWindowIcon(_icon("flat.svg"))

        self._populate_preset_combo()
        self._update_duration_preview()

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --")
        for name in sorted(core.load_presets("flat")):
            self.combo_preset.addItem(name)
        self.combo_preset.blockSignals(False)

    def _on_preset_selected(self, index):
        if index <= 0:
            return
        values = core.load_presets("flat").get(self.combo_preset.currentText())
        if not values:
            return
        self.spn_power.setValue(values.get("power", self.spn_power.value()))
        self.spn_feed.setValue(values.get("feed", self.spn_feed.value()))
        self.spn_thickness.setValue(values.get("thickness", self.spn_thickness.value()))
        self.spn_passes.setValue(values.get("n_passes", self.spn_passes.value()))
        self.chk_finish.setChecked(values.get("use_finish", False))
        self.spn_finish_feed.setValue(values.get("finish_feed", self.spn_finish_feed.value()))
        self.chk_power_ramp.setChecked(values.get("use_power_ramp", False))
        self.spn_power_end.setValue(values.get("power_end", self.spn_power_end.value()))
        self.spn_kerf.setValue(values.get("kerf_width", self.spn_kerf.value()))

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self.form, "Sauvegarder le préréglage", "Nom du préréglage :")
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("flat", name, {
            "power": self.spn_power.value(),
            "feed": self.spn_feed.value(),
            "thickness": self.spn_thickness.value(),
            "n_passes": self.spn_passes.value(),
            "use_finish": self.chk_finish.isChecked(),
            "finish_feed": self.spn_finish_feed.value(),
            "use_power_ramp": self.chk_power_ramp.isChecked(),
            "power_end": self.spn_power_end.value(),
            "kerf_width": self.spn_kerf.value(),
        })
        self._populate_preset_combo()
        idx = self.combo_preset.findText(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        index = self.combo_preset.currentIndex()
        if index <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QtWidgets.QMessageBox.question(
            self.form, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset("flat", name)
        self._populate_preset_combo()

    def _on_toolpath_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_flat_multipass(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            quiet=True, **self._build_gcode_kwargs(),
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def _build_gcode_kwargs(self):
        finish_feed = self.spn_finish_feed.value() if self.chk_finish.isChecked() else None
        z_start_override = self.spn_zstart.value() if self.chk_zoverride.isChecked() else None
        power_end = self.spn_power_end.value() if self.chk_power_ramp.isChecked() else None
        return dict(
            finish_feed=finish_feed,
            z_start=z_start_override,
            power_end=power_end,
            kerf_width=self.spn_kerf.value(),
            use_hole_first=self.chk_hole_first.isChecked(),
            use_proximity=self.chk_proximity.isChecked(),
        )

    def _update_duration_preview(self):
        if not self._edges:
            self.lbl_duration.setText("Durée estimée : -- (aucun segment dans la sélection)")
            return
        gcode = core.generate_gcode_flat_multipass(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            quiet=True, **self._build_gcode_kwargs(),
        )
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_flat_multipass(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            frame_only=True, **self._build_gcode_kwargs(),
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_decoupe.ngc")

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()

        FreeCAD.Console.PrintMessage("Chaînage des segments connectés...\n")
        gcode = core.generate_gcode_flat_multipass(
            self._edges,
            self.spn_power.value(),
            self.spn_feed.value(),
            self.spn_thickness.value(),
            self.spn_passes.value(),
            pre_gcode=pre_text,
            post_gcode=post_text,
            **self._build_gcode_kwargs(),
        )

        cfg = core.load_config()
        cfg["pre_f"] = pre_text
        cfg["post_f"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False

        # Cf. marquage courbe : panneau conservé si la sauvegarde est abandonnée.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/decoupe_multipasse.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : DÉCOUPE MULTI-PASSES SUR SURFACE COURBÉE
# ==========================================================================
class TaskPanelCurvedCut:
    def __init__(self, selection):
        self.selection = selection
        self._edges, self._reference_shape = self._get_edges()
        # Sonde Z gardée pour toute la durée de vie du panneau (cf.
        # TaskPanelCurved) -- reference_shape ne change pas tant que le
        # panneau reste ouvert.
        self._probe = core.make_ray_probe(self._reference_shape) if self._reference_shape is not None else None
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Comme le marquage sur surface courbe, sélectionne à la fois\n"
            "le motif projeté (Hachures_3D, issu du mode Projection) ET le\n"
            "modèle 3D d'origine, TOUS LES DEUX EN MÊME TEMPS -- le modèle\n"
            "3D permet une sonde exacte du relief. Chaque passe recule le\n"
            "foyer un peu plus DANS la matière (comme la Découpe\n"
            "multi-passes à plat), tout en suivant le relief natif de la\n"
            "surface à chaque point du tracé.")
        info.setWordWrap(True)
        form.addRow(info)

        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/épaisseur/\n"
            "passes/Z travail/finition/rampe/kerf) -- en choisir un remplit\n"
            "automatiquement les champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la découpe (valeur S, 0-1000 selon\n"
            "l'échelle de la machine). Fixe pour toutes les passes, sauf si\n"
            "la rampe de puissance ci-dessous est activée.")
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(300)
        self.spn_feed.setSuffix(" mm/min")
        self.spn_feed.setToolTip(
            "Vitesse d'avance pendant la découpe (mm/min), pour toutes les\n"
            "passes sauf la dernière si l'option 'Ralentir la dernière\n"
            "passe' est activée.")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_zfocus = QtWidgets.QDoubleSpinBox()
        self.spn_zfocus.setRange(-50, 200)
        self.spn_zfocus.setValue(4.0)
        self.spn_zfocus.setSuffix(" mm")
        self.spn_zfocus.setToolTip(
            "Hauteur de travail (cale) : position Z qui met le laser au\n"
            "point (foyer) sur la surface, au niveau le plus bas du motif\n"
            "(1ère passe) -- même réglage que le mode Marquage sur surface\n"
            "courbe. Les passes suivantes reculent le foyer dans la matière\n"
            "à partir de cette référence.")
        form.addRow("Z Travail (Cale, 1ère passe) :", self.spn_zfocus)

        self.spn_marge = QtWidgets.QDoubleSpinBox()
        self.spn_marge.setRange(0.0, 20)
        self.spn_marge.setValue(0.5)
        self.spn_marge.setSuffix(" mm")
        self.spn_marge.setToolTip("Marge de sécurité ajoutée à la hauteur de retrait entre les chaînes.")
        form.addRow("Marge de sécurité (retrait) :", self.spn_marge)

        self.spn_thickness = QtWidgets.QDoubleSpinBox()
        self.spn_thickness.setRange(0.1, 30)
        self.spn_thickness.setValue(5.0)
        self.spn_thickness.setSuffix(" mm")
        self.spn_thickness.setToolTip(
            "Épaisseur de matière à traverser (même repère que la Découpe\n"
            "multi-passes à plat : 2-8mm testé constructeur, au-delà\n"
            "résultat incertain).")
        form.addRow("Épaisseur matériau :", self.spn_thickness)

        self.spn_passes = QtWidgets.QSpinBox()
        self.spn_passes.setRange(1, 50)
        self.spn_passes.setValue(3)
        self.spn_passes.setToolTip(
            "Nombre de passes pour traverser toute l'épaisseur. Le pas Z\n"
            "entre deux passes = épaisseur / nombre de passes, appliqué\n"
            "PARTOUT le long de la courbe (voir avertissement si le pas\n"
            "calculé est trop grand).")
        form.addRow("Nombre de passes :", self.spn_passes)

        self.chk_finish = QtWidgets.QCheckBox("Ralentir la dernière passe")
        self.chk_finish.setToolTip(
            "Utilise une avance plus lente (ci-dessous) uniquement sur la\n"
            "toute dernière passe, pour un bord de coupe plus propre.")
        form.addRow(self.chk_finish)

        self.spn_finish_feed = QtWidgets.QDoubleSpinBox()
        self.spn_finish_feed.setRange(1, 20000)
        self.spn_finish_feed.setValue(150)
        self.spn_finish_feed.setSuffix(" mm/min")
        self.spn_finish_feed.setEnabled(False)
        self.chk_finish.toggled.connect(self.spn_finish_feed.setEnabled)
        form.addRow("Avance dernière passe :", self.spn_finish_feed)

        self.chk_power_ramp = QtWidgets.QCheckBox("Puissance différente en dernière passe (rampe)")
        self.chk_power_ramp.setToolTip(
            "Fait varier la puissance linéairement de la 1ère à la dernière\n"
            "passe (au lieu d'une valeur fixe).")
        form.addRow(self.chk_power_ramp)

        self.spn_power_end = QtWidgets.QDoubleSpinBox()
        self.spn_power_end.setRange(0, 1000)
        self.spn_power_end.setValue(0)
        self.spn_power_end.setEnabled(False)
        self.spn_power_end.setToolTip(
            "La puissance varie linéairement de 'Puissance' (1ère passe)\n"
            "à cette valeur (dernière passe).")
        self.chk_power_ramp.toggled.connect(self.spn_power_end.setEnabled)
        form.addRow("Puissance dernière passe :", self.spn_power_end)

        self.spn_kerf = QtWidgets.QDoubleSpinBox()
        self.spn_kerf.setRange(0.0, 5.0)
        self.spn_kerf.setDecimals(3)
        self.spn_kerf.setValue(0.0)
        self.spn_kerf.setSuffix(" mm")
        self.spn_kerf.setToolTip(
            "Largeur de trait mesurée (0 = désactivé). Le contour extérieur\n"
            "est agrandi et les trous/îlots rétrécis de la moitié de cette\n"
            "valeur (décalage en X/Y uniquement, le suivi du relief en Z\n"
            "n'est pas affecté).")
        form.addRow("Compensation de kerf :", self.spn_kerf)

        self.chk_hole_first = QtWidgets.QCheckBox("Découper les trous/îlots avant le contour englobant")
        self.chk_hole_first.setChecked(True)
        form.addRow(self.chk_hole_first)

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        form.addRow(self.chk_proximity)

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences).".format(core.RAPID_FEED_MM_MIN))

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART qui trace uniquement le rectangle\n"
            "englobant du motif, laser éteint (ou faisceau de visée très\n"
            "faible : voir « Puissance de cadrage » dans les Préférences)\n"
            "-- à lancer seul sur la\n"
            "machine pour vérifier le positionnement AVANT de lancer le\n"
            "vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel (TOUTES les passes) dans la vue 3D :\n"
            "gris fin = transit laser éteint (G0), rouge épais = découpe\n"
            "laser allumé (G1) -- les passes profondes apparaissent sous la\n"
            "surface du modèle, comme la vraie profondeur de coupe.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_cc", ""))
        self.txt_post.setPlainText(cfg.get("post_cc", ""))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Découpe multi-passes sur surface courbée")
        self.form.setWindowIcon(_icon("curved_cut.svg"))

        self._populate_preset_combo()
        self._update_duration_preview()

    def _get_edges(self):
        edge_sel, reference_shape = core.split_selection(self.selection)
        edges = core.get_all_edges_from_selection(edge_sel)
        return edges, reference_shape

    def _build_gcode_kwargs(self):
        finish_feed = self.spn_finish_feed.value() if self.chk_finish.isChecked() else None
        power_end = self.spn_power_end.value() if self.chk_power_ramp.isChecked() else None
        return dict(
            finish_feed=finish_feed,
            power_end=power_end,
            kerf_width=self.spn_kerf.value(),
            use_hole_first=self.chk_hole_first.isChecked(),
            use_proximity=self.chk_proximity.isChecked(),
        )

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --")
        for name in sorted(core.load_presets("curved_cut")):
            self.combo_preset.addItem(name)
        self.combo_preset.blockSignals(False)

    def _on_preset_selected(self, index):
        if index <= 0:
            return
        values = core.load_presets("curved_cut").get(self.combo_preset.currentText())
        if not values:
            return
        self.spn_power.setValue(values.get("power", self.spn_power.value()))
        self.spn_feed.setValue(values.get("feed", self.spn_feed.value()))
        self.spn_zfocus.setValue(values.get("z_focus", self.spn_zfocus.value()))
        self.spn_marge.setValue(values.get("marge", self.spn_marge.value()))
        self.spn_thickness.setValue(values.get("thickness", self.spn_thickness.value()))
        self.spn_passes.setValue(values.get("n_passes", self.spn_passes.value()))
        self.chk_finish.setChecked(values.get("use_finish", False))
        self.spn_finish_feed.setValue(values.get("finish_feed", self.spn_finish_feed.value()))
        self.chk_power_ramp.setChecked(values.get("use_power_ramp", False))
        self.spn_power_end.setValue(values.get("power_end", self.spn_power_end.value()))
        self.spn_kerf.setValue(values.get("kerf_width", self.spn_kerf.value()))

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self.form, "Sauvegarder le préréglage", "Nom du préréglage :")
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("curved_cut", name, {
            "power": self.spn_power.value(),
            "feed": self.spn_feed.value(),
            "z_focus": self.spn_zfocus.value(),
            "marge": self.spn_marge.value(),
            "thickness": self.spn_thickness.value(),
            "n_passes": self.spn_passes.value(),
            "use_finish": self.chk_finish.isChecked(),
            "finish_feed": self.spn_finish_feed.value(),
            "use_power_ramp": self.chk_power_ramp.isChecked(),
            "power_end": self.spn_power_end.value(),
            "kerf_width": self.spn_kerf.value(),
        })
        self._populate_preset_combo()
        idx = self.combo_preset.findText(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        index = self.combo_preset.currentIndex()
        if index <= 0:
            return
        name = self.combo_preset.currentText()
        reply = QtWidgets.QMessageBox.question(
            self.form, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset("curved_cut", name)
        self._populate_preset_combo()

    def _update_duration_preview(self):
        if not self._edges:
            self.lbl_duration.setText("Durée estimée : -- (aucun segment dans la sélection)")
            return
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, quiet=True, probe=self._probe, **self._build_gcode_kwargs(),
        )
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, frame_only=True, probe=self._probe, **self._build_gcode_kwargs(),
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_decoupe_courbe.ngc")

    def _on_toolpath_preview(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, quiet=True, probe=self._probe, **self._build_gcode_kwargs(),
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        # Même correction que le mode Marquage sur surface courbe : le Z
        # exporté est en repère MACHINE (calé sur le foyer de la 1ère
        # passe) -- décalage retiré pour superposer l'aperçu au modèle 3D.
        # Les passes profondes restent alors visibles SOUS la surface
        # d'origine, ce qui est la profondeur de coupe réelle recherchée.
        z_offset = core.curved_native_z_offset(self._edges, self.spn_zfocus.value())
        rapid = core.shift_segments_z(rapid, -z_offset)
        mark = core.shift_segments_z(mark, -z_offset)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()

        FreeCAD.Console.PrintMessage(
            "Chaînage des segments connectés... ({})\n".format(
                "objet 3D de référence détecté" if self._reference_shape is not None else "pas d'objet 3D, interpolation"))
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape,
            pre_gcode=pre_text, post_gcode=post_text,
            probe=self._probe,
            **self._build_gcode_kwargs(),
        )

        cfg = core.load_config()
        cfg["pre_cc"] = pre_text
        cfg["post_cc"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False

        # Cf. marquage courbe : panneau conservé si la sauvegarde est abandonnée.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/decoupe_courbe.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : JOB COMBINÉ (PLUSIEURS OPÉRATIONS, UN SEUL ARMEMENT)
# ==========================================================================
# Les 3 sous-dialogues ci-dessous (un par type d'opération) sont des
# QDialog MODALES classiques -- pas des Gui::TaskView comme les panneaux
# principaux -- parce qu'elles s'ouvrent PAR-DESSUS le panneau du job
# combiné déjà ouvert (empiler deux Gui::TaskView n'est pas prévu par
# FreeCAD) et n'ont besoin d'aucune interaction avec la vue 3D pendant
# qu'elles sont affichées (contrairement aux panneaux principaux, qui
# restent ouverts pendant qu'on tourne la vue).
#
# Champs volontairement réduits à l'essentiel par rapport aux panneaux
# autonomes correspondants (pas de rampe de puissance / dernière passe
# ralentie / Z manuel pour la Découpe, pas de remplissage Défocus pour
# la Grille de test -- calibration dédiée hors de portée d'une simple
# boîte d'ajout) : un job combiné sert avant tout à enchaîner plusieurs
# opérations déjà calibrées séparément, pas à explorer tous les réglages
# fins en même temps.
class _OperationDialogCurved(QtWidgets.QDialog):
    def __init__(self, edges, reference_shape, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.reference_shape = reference_shape
        self.setWindowTitle("Ajouter une opération : Marquage sur surface courbe")
        form = QtWidgets.QFormLayout(self)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.txt_label = QtWidgets.QLineEdit("Marquage courbe")
        form.addRow("Nom de l'opération :", self.txt_label)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(1000)
        self.spn_feed.setSuffix(" mm/min")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_zfocus = QtWidgets.QDoubleSpinBox()
        self.spn_zfocus.setRange(-50, 200)
        self.spn_zfocus.setValue(4.0)
        self.spn_zfocus.setSuffix(" mm")
        form.addRow("Z Travail (Cale) :", self.spn_zfocus)

        self.spn_marge = QtWidgets.QDoubleSpinBox()
        self.spn_marge.setRange(0.0, 20)
        self.spn_marge.setValue(0.5)
        self.spn_marge.setSuffix(" mm")
        form.addRow("Marge de sécurité (transit) :", self.spn_marge)

        info = QtWidgets.QLabel("{} segment(s) sélectionné(s){}.".format(
            len(edges), " -- sonde exacte sur objet 3D" if reference_shape is not None else " -- interpolation (pas d'objet 3D de référence)"))
        info.setWordWrap(True)
        form.addRow(info)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def build_operation(self):
        return {
            "type": "curved",
            "label": self.txt_label.text().strip() or "Marquage courbe",
            "params": dict(
                edges=self.edges,
                power=self.spn_power.value(),
                feed=self.spn_feed.value(),
                z_focus=self.spn_zfocus.value(),
                marge_survol=self.spn_marge.value(),
                reference_shape=self.reference_shape,
            ),
        }


class _OperationDialogCurvedCut(QtWidgets.QDialog):
    def __init__(self, edges, reference_shape, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.reference_shape = reference_shape
        self.setWindowTitle("Ajouter une opération : Découpe multi-passes sur surface courbée")
        form = QtWidgets.QFormLayout(self)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.txt_label = QtWidgets.QLineEdit("Découpe courbe")
        form.addRow("Nom de l'opération :", self.txt_label)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(300)
        self.spn_feed.setSuffix(" mm/min")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_zfocus = QtWidgets.QDoubleSpinBox()
        self.spn_zfocus.setRange(-50, 200)
        self.spn_zfocus.setValue(4.0)
        self.spn_zfocus.setSuffix(" mm")
        form.addRow("Z Travail (Cale, 1ère passe) :", self.spn_zfocus)

        self.spn_marge = QtWidgets.QDoubleSpinBox()
        self.spn_marge.setRange(0.0, 20)
        self.spn_marge.setValue(0.5)
        self.spn_marge.setSuffix(" mm")
        form.addRow("Marge de sécurité (retrait) :", self.spn_marge)

        self.spn_thickness = QtWidgets.QDoubleSpinBox()
        self.spn_thickness.setRange(0.1, 30)
        self.spn_thickness.setValue(5.0)
        self.spn_thickness.setSuffix(" mm")
        form.addRow("Épaisseur matériau :", self.spn_thickness)

        self.spn_passes = QtWidgets.QSpinBox()
        self.spn_passes.setRange(1, 50)
        self.spn_passes.setValue(3)
        form.addRow("Nombre de passes :", self.spn_passes)

        self.spn_kerf = QtWidgets.QDoubleSpinBox()
        self.spn_kerf.setRange(0.0, 5.0)
        self.spn_kerf.setDecimals(3)
        self.spn_kerf.setValue(0.0)
        self.spn_kerf.setSuffix(" mm")
        form.addRow("Compensation de kerf :", self.spn_kerf)

        self.chk_hole_first = QtWidgets.QCheckBox("Découper les trous/îlots avant le contour englobant")
        self.chk_hole_first.setChecked(True)
        form.addRow(self.chk_hole_first)

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        form.addRow(self.chk_proximity)

        info = QtWidgets.QLabel("{} segment(s) sélectionné(s){}.".format(
            len(edges), " -- sonde exacte sur objet 3D" if reference_shape is not None else " -- interpolation (pas d'objet 3D de référence)"))
        info.setWordWrap(True)
        form.addRow(info)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def build_operation(self):
        return {
            "type": "curved_cut",
            "label": self.txt_label.text().strip() or "Decoupe courbe",
            "params": dict(
                edges=self.edges,
                power=self.spn_power.value(),
                feed=self.spn_feed.value(),
                thickness=self.spn_thickness.value(),
                n_passes=self.spn_passes.value(),
                z_focus=self.spn_zfocus.value(),
                marge_survol=self.spn_marge.value(),
                reference_shape=self.reference_shape,
                kerf_width=self.spn_kerf.value(),
                use_hole_first=self.chk_hole_first.isChecked(),
                use_proximity=self.chk_proximity.isChecked(),
            ),
        }


class _OperationDialogFlat(QtWidgets.QDialog):
    def __init__(self, edges, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.setWindowTitle("Ajouter une opération : Découpe multi-passes")
        form = QtWidgets.QFormLayout(self)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.txt_label = QtWidgets.QLineEdit("Découpe")
        form.addRow("Nom de l'opération :", self.txt_label)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, 1000)
        self.spn_power.setValue(0)
        form.addRow("Puissance (S 0-1000) :", self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(300)
        self.spn_feed.setSuffix(" mm/min")
        form.addRow("Avance (Feed) :", self.spn_feed)

        self.spn_thickness = QtWidgets.QDoubleSpinBox()
        self.spn_thickness.setRange(0.1, 30)
        self.spn_thickness.setValue(5.0)
        self.spn_thickness.setSuffix(" mm")
        form.addRow("Épaisseur matériau :", self.spn_thickness)

        self.spn_passes = QtWidgets.QSpinBox()
        self.spn_passes.setRange(1, 50)
        self.spn_passes.setValue(3)
        form.addRow("Nombre de passes :", self.spn_passes)

        self.spn_kerf = QtWidgets.QDoubleSpinBox()
        self.spn_kerf.setRange(0.0, 5.0)
        self.spn_kerf.setDecimals(3)
        self.spn_kerf.setValue(0.0)
        self.spn_kerf.setSuffix(" mm")
        form.addRow("Compensation de kerf :", self.spn_kerf)

        self.chk_hole_first = QtWidgets.QCheckBox("Découper les trous/îlots avant le contour englobant")
        self.chk_hole_first.setChecked(True)
        form.addRow(self.chk_hole_first)

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        form.addRow(self.chk_proximity)

        info = QtWidgets.QLabel("{} segment(s) sélectionné(s).".format(len(edges)))
        info.setWordWrap(True)
        form.addRow(info)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def build_operation(self):
        return {
            "type": "flat",
            "label": self.txt_label.text().strip() or "Decoupe",
            "params": dict(
                edges=self.edges,
                power=self.spn_power.value(),
                feed=self.spn_feed.value(),
                thickness=self.spn_thickness.value(),
                n_passes=self.spn_passes.value(),
                kerf_width=self.spn_kerf.value(),
                use_hole_first=self.chk_hole_first.isChecked(),
                use_proximity=self.chk_proximity.isChecked(),
            ),
        }


class _OperationDialogTestGrid(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter une opération : Grille de test puissance/vitesse")
        form = QtWidgets.QFormLayout(self)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        self.txt_label = QtWidgets.QLineEdit("Grille de test")
        form.addRow("Nom de l'opération :", self.txt_label)

        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Gravure", "Découpe"])
        form.addRow("Mode :", self.combo_mode)

        self.combo_filltype = QtWidgets.QComboBox()
        self.combo_filltype.addItems(["Parallèles", "Croisées (grille)"])
        self.combo_filltype.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_filltype.setMinimumContentsLength(17)
        form.addRow("Type de remplissage :", self.combo_filltype)
        self.combo_mode.currentIndexChanged.connect(lambda idx: self.combo_filltype.setEnabled(idx == 0))

        self.spn_power_min = QtWidgets.QDoubleSpinBox()
        self.spn_power_min.setRange(0, 1000)
        self.spn_power_min.setValue(200)
        form.addRow("Puissance min :", self.spn_power_min)

        self.spn_power_max = QtWidgets.QDoubleSpinBox()
        self.spn_power_max.setRange(0, 1000)
        self.spn_power_max.setValue(800)
        form.addRow("Puissance max :", self.spn_power_max)

        self.spn_power_steps = QtWidgets.QSpinBox()
        self.spn_power_steps.setRange(2, 20)
        self.spn_power_steps.setValue(4)
        form.addRow("Nb de paliers puissance :", self.spn_power_steps)

        self.spn_feed_min = QtWidgets.QDoubleSpinBox()
        self.spn_feed_min.setRange(1, 20000)
        self.spn_feed_min.setValue(200)
        self.spn_feed_min.setSuffix(" mm/min")
        form.addRow("Vitesse min :", self.spn_feed_min)

        self.spn_feed_max = QtWidgets.QDoubleSpinBox()
        self.spn_feed_max.setRange(1, 20000)
        self.spn_feed_max.setValue(2000)
        self.spn_feed_max.setSuffix(" mm/min")
        form.addRow("Vitesse max :", self.spn_feed_max)

        self.spn_feed_steps = QtWidgets.QSpinBox()
        self.spn_feed_steps.setRange(2, 20)
        self.spn_feed_steps.setValue(4)
        form.addRow("Nb de paliers vitesse :", self.spn_feed_steps)

        self.spn_cell_size = QtWidgets.QDoubleSpinBox()
        self.spn_cell_size.setRange(2, 100)
        self.spn_cell_size.setValue(10)
        self.spn_cell_size.setSuffix(" mm")
        form.addRow("Taille cellule :", self.spn_cell_size)

        self.spn_gap = QtWidgets.QDoubleSpinBox()
        self.spn_gap.setRange(0, 20)
        self.spn_gap.setValue(2)
        self.spn_gap.setSuffix(" mm")
        form.addRow("Espace entre cellules :", self.spn_gap)

        self.spn_hatch_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_hatch_spacing.setRange(0.05, 10)
        self.spn_hatch_spacing.setDecimals(2)
        self.spn_hatch_spacing.setValue(0.2)
        self.spn_hatch_spacing.setSuffix(" mm")
        form.addRow("Espacement hachures (Gravure) :", self.spn_hatch_spacing)

        self.spn_hatch_angle = QtWidgets.QDoubleSpinBox()
        self.spn_hatch_angle.setRange(-360, 360)
        self.spn_hatch_angle.setValue(45)
        self.spn_hatch_angle.setSuffix(" deg")
        form.addRow("Angle hachures (Gravure) :", self.spn_hatch_angle)

        self.spn_zwork = QtWidgets.QDoubleSpinBox()
        self.spn_zwork.setRange(-50, 200)
        self.spn_zwork.setValue(4.0)
        self.spn_zwork.setSuffix(" mm")
        form.addRow("Z de travail :", self.spn_zwork)

        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        form.addRow(self.chk_proximity)

        self.chk_labels = QtWidgets.QCheckBox("Graver les étiquettes puissance/vitesse")
        self.chk_labels.setChecked(True)
        form.addRow(self.chk_labels)

        self.spn_label_power = QtWidgets.QDoubleSpinBox()
        self.spn_label_power.setRange(0, 1000)
        self.spn_label_power.setValue(300)
        form.addRow("Puissance étiquettes :", self.spn_label_power)

        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setValue(1500)
        self.spn_label_feed.setSuffix(" mm/min")
        form.addRow("Vitesse étiquettes :", self.spn_label_feed)

        self.chk_labels.toggled.connect(self.spn_label_power.setEnabled)
        self.chk_labels.toggled.connect(self.spn_label_feed.setEnabled)

        info = QtWidgets.QLabel(
            "Le remplissage Défocus n'est pas disponible ici (calibration\n"
            "dédiée) -- utilise le panneau Grille de test seul pour ce cas.")
        info.setWordWrap(True)
        form.addRow(info)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        if self.spn_power_max.value() < self.spn_power_min.value():
            QtWidgets.QMessageBox.critical(self, "Erreur", "Puissance max doit être >= puissance min.")
            return
        if self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(self, "Erreur", "Vitesse max doit être >= vitesse min.")
            return
        super().accept()

    def build_operation(self):
        mode = "gravure" if self.combo_mode.currentIndex() == 0 else "decoupe"
        fill_type_map = {0: "paralleles", 1: "croisees"}
        fill_type = fill_type_map.get(self.combo_filltype.currentIndex(), "paralleles") if mode == "gravure" else "paralleles"

        cells = core.build_test_grid_cells(
            mode,
            self.spn_power_min.value(), self.spn_power_max.value(), self.spn_power_steps.value(),
            self.spn_feed_min.value(), self.spn_feed_max.value(), self.spn_feed_steps.value(),
            self.spn_cell_size.value(), self.spn_gap.value(),
            fill_type=fill_type,
            hatch_spacing=self.spn_hatch_spacing.value(), hatch_angle=self.spn_hatch_angle.value(),
        )

        label_edges = None
        if self.chk_labels.isChecked():
            power_labels, feed_labels = core.build_test_grid_axis_labels(
                cells, self.spn_power_steps.value(), self.spn_feed_steps.value(),
                self.spn_cell_size.value(), self.spn_gap.value())
            label_edges = []
            for lbl in power_labels:
                label_edges.extend(lbl["edges"])
            for lbl in feed_labels:
                label_edges.extend(lbl["edges"])

        return {
            "type": "testgrid",
            "label": self.txt_label.text().strip() or "Grille de test",
            "params": dict(
                cells=cells,
                z_work=self.spn_zwork.value(),
                label_edges=label_edges,
                label_power=self.spn_label_power.value(),
                label_feed=self.spn_label_feed.value(),
                use_proximity=self.chk_proximity.isChecked(),
            ),
        }


class TaskPanelCombined:
    def __init__(self):
        self.operations = []

        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        info = QtWidgets.QLabel(
            "Empile plusieurs opérations (Marquage courbe / Découpe\n"
            "courbe / Découpe multi-passes / Grille de test) dans UN SEUL\n"
            "job -- UN SEUL armement (M3) au début, UN SEUL désarmement\n"
            "(M5)/fin de programme (M2) à la fin, exécutées dans l'ordre\n"
            "de la liste. Sélectionne la géométrie voulue AVANT de cliquer\n"
            "sur \"+ Ajouter\" pour chaque opération -- la sélection est\n"
            "capturée à l'ajout, pas au moment de lancer le job.")
        info.setWordWrap(True)
        form.addRow(info)

        self.list_ops = QtWidgets.QListWidget()
        self.list_ops.setToolTip("Opérations empilées, exécutées dans cet ordre.")
        form.addRow(self.list_ops)

        self.btn_add_curved = QtWidgets.QPushButton("+ Ajouter : Marquage sur surface courbe")
        self.btn_add_curved.clicked.connect(self._on_add_curved)
        form.addRow(self.btn_add_curved)

        self.btn_add_curved_cut = QtWidgets.QPushButton("+ Ajouter : Découpe sur surface courbée")
        self.btn_add_curved_cut.clicked.connect(self._on_add_curved_cut)
        form.addRow(self.btn_add_curved_cut)

        self.btn_add_flat = QtWidgets.QPushButton("+ Ajouter : Découpe multi-passes")
        self.btn_add_flat.clicked.connect(self._on_add_flat)
        form.addRow(self.btn_add_flat)

        self.btn_add_testgrid = QtWidgets.QPushButton("+ Ajouter : Grille de test puissance/vitesse")
        self.btn_add_testgrid.clicked.connect(self._on_add_testgrid)
        form.addRow(self.btn_add_testgrid)

        self.btn_move_up = QtWidgets.QPushButton("Monter l'opération sélectionnée")
        self.btn_move_up.clicked.connect(self._on_move_up)
        form.addRow(self.btn_move_up)

        self.btn_move_down = QtWidgets.QPushButton("Descendre l'opération sélectionnée")
        self.btn_move_down.clicked.connect(self._on_move_down)
        form.addRow(self.btn_move_down)

        self.btn_remove = QtWidgets.QPushButton("Supprimer l'opération sélectionnée")
        self.btn_remove.clicked.connect(self._on_remove)
        form.addRow(self.btn_remove)

        self.lbl_duration = QtWidgets.QLabel("Durée estimée : -- (aucune opération)")
        self.lbl_duration.setWordWrap(True)
        self.lbl_duration.setToolTip(
            "Recalculée après chaque ajout/suppression/réorganisation.\n"
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))
        form.addRow(self.lbl_duration)

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART qui trace le rectangle englobant de\n"
            "CHAQUE opération, laser éteint (ou faisceau de visée très\n"
            "faible : voir « Puissance de cadrage » dans les Préférences)\n"
            "-- à lancer seul\n"
            "sur la machine pour vérifier le positionnement de toutes les\n"
            "opérations AVANT de lancer le job réel.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel de TOUT le job combiné dans la vue 3D :\n"
            "gris fin = transit laser éteint (G0), rouge épais =\n"
            "marquage/découpe laser allumé (G1). Purement visuel, ne\n"
            "génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        self.txt_pre.setToolTip(
            "Texte libre inséré tel quel juste avant l'armement (une seule\n"
            "fois pour tout le job combiné). Sauvegardé d'une exécution à\n"
            "l'autre.")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        self.txt_post.setToolTip(
            "Texte libre inséré tel quel juste après la dernière opération,\n"
            "avant le désarmement final (une seule fois pour tout le job\n"
            "combiné). Sauvegardé d'une exécution à l'autre.")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_j", ""))
        self.txt_post.setPlainText(cfg.get("post_j", ""))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Job combiné (plusieurs opérations)")
        self.form.setWindowIcon(_icon("combined.svg"))

        self._refresh_list()

    def _type_display(self, op_type):
        return {
            "curved": "Marquage courbe",
            "curved_cut": "Découpe courbe",
            "flat": "Découpe multi-passes",
            "testgrid": "Grille de test",
        }.get(op_type, op_type)

    def _refresh_list(self):
        self.list_ops.clear()
        for i, op in enumerate(self.operations):
            self.list_ops.addItem("{}. [{}] {}".format(i + 1, self._type_display(op["type"]), op["label"]))
        self._update_duration_preview()

    def _add_operation(self, op):
        self.operations.append(op)
        self._refresh_list()
        self.list_ops.setCurrentRow(len(self.operations) - 1)

    def _on_add_curved(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Sélectionne les Hachures_3D (motif projeté) ET le modèle 3D\n"
                "ensemble avant d'ajouter une opération de marquage courbe.")
            return
        edge_sel, reference_shape = core.split_selection(selection)
        edges = core.get_all_edges_from_selection(edge_sel)
        if not edges:
            QtWidgets.QMessageBox.warning(self.form, "Sélection", "Aucun segment trouvé dans la sélection.")
            return
        dlg = _OperationDialogCurved(edges, reference_shape, self.form)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._add_operation(dlg.build_operation())

    def _on_add_curved_cut(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Sélectionne les Hachures_3D (motif projeté) ET le modèle 3D\n"
                "ensemble avant d'ajouter une opération de découpe courbe.")
            return
        edge_sel, reference_shape = core.split_selection(selection)
        edges = core.get_all_edges_from_selection(edge_sel)
        if not edges:
            QtWidgets.QMessageBox.warning(self.form, "Sélection", "Aucun segment trouvé dans la sélection.")
            return
        dlg = _OperationDialogCurvedCut(edges, reference_shape, self.form)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._add_operation(dlg.build_operation())

    def _on_add_flat(self):
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection", "Sélectionne le(s) contour(s) à découper avant d'ajouter cette opération.")
            return
        edges = core.get_all_edges_from_selection(selection)
        if not edges:
            QtWidgets.QMessageBox.warning(self.form, "Sélection", "Aucun segment trouvé dans la sélection.")
            return
        dlg = _OperationDialogFlat(edges, self.form)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._add_operation(dlg.build_operation())

    def _on_add_testgrid(self):
        dlg = _OperationDialogTestGrid(self.form)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self._add_operation(dlg.build_operation())

    def _on_move_up(self):
        i = self.list_ops.currentRow()
        if i <= 0:
            return
        self.operations[i - 1], self.operations[i] = self.operations[i], self.operations[i - 1]
        self._refresh_list()
        self.list_ops.setCurrentRow(i - 1)

    def _on_move_down(self):
        i = self.list_ops.currentRow()
        if i < 0 or i >= len(self.operations) - 1:
            return
        self.operations[i + 1], self.operations[i] = self.operations[i], self.operations[i + 1]
        self._refresh_list()
        self.list_ops.setCurrentRow(i + 1)

    def _on_remove(self):
        i = self.list_ops.currentRow()
        if i < 0:
            return
        del self.operations[i]
        self._refresh_list()

    def _update_duration_preview(self):
        if not self.operations:
            self.lbl_duration.setText("Durée estimée : -- (aucune opération)")
            return
        gcode = core.generate_gcode_combined(self.operations, quiet=True)
        if not gcode:
            self.lbl_duration.setText("Durée estimée : -- (aucune géométrie dans les opérations)")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        if not self.operations:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Ajoute au moins une opération avant de générer un aperçu.")
            return
        gcode = core.generate_gcode_combined(self.operations, frame_only=True)
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_combine.ngc")

    def _on_toolpath_preview(self):
        if not self.operations:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Ajoute au moins une opération avant l'aperçu.")
            return
        # Prévisualisé opération par opération (au lieu du G-code combiné
        # d'un seul bloc) : une opération "curved"/"curved_cut" a son Z en
        # repère MACHINE (calé sur le foyer, cf. TaskPanelCurved/
        # TaskPanelCurvedCut) qu'il faut ramener au repère natif du
        # document pour se superposer correctement au modèle 3D dans la
        # vue -- décalage propre à CETTE opération, impossible à
        # appliquer après coup si toutes les opérations sont déjà
        # fondues dans un seul G-code.
        all_rapid, all_mark = [], []
        for op in self.operations:
            gcode = core.generate_gcode_combined([op], quiet=True)
            if not gcode:
                continue
            rapid, mark = core.parse_gcode_toolpath(gcode)
            if op["type"] in ("curved", "curved_cut"):
                z_offset = core.curved_native_z_offset(op["params"]["edges"], op["params"]["z_focus"])
                rapid = core.shift_segments_z(rapid, -z_offset)
                mark = core.shift_segments_z(mark, -z_offset)
            all_rapid.extend(rapid)
            all_mark.extend(mark)
        if not all_rapid and not all_mark:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, all_rapid, all_mark)

    def accept(self):
        if not self.operations:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Ajoute au moins une opération avant de lancer le job.")
            return False

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_combined(self.operations, pre_gcode=pre_text, post_gcode=post_text)

        cfg = core.load_config()
        cfg["pre_j"] = pre_text
        cfg["post_j"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Aucun G-code généré (vérifie que les opérations contiennent de la géométrie).")
            return False

        # Cf. marquage courbe : panneau conservé si la sauvegarde est abandonnée.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/job_combine.ngc")

    def reject(self):
        return True


# ==========================================================================
# PRÉFÉRENCES DE L'ATELIER
# ==========================================================================
class TaskPanelSettings:
    """Édite les réglages utilisateur (laser_core._USER_SETTINGS + profil
    du bec) et les enregistre dans laser_atelier_config.json. Appliqués
    immédiatement à la validation -- pas besoin de redémarrer FreeCAD."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        settings = core.current_settings()
        nozzle = core.current_nozzle()

        # --- Sauvegarde ---
        self.edt_gcode_dir = QtWidgets.QLineEdit(settings["gcode_dir"])
        self.edt_gcode_dir.setToolTip(
            "Dossier proposé par défaut dans le dialogue de sauvegarde\n"
            "G-code de tous les modes. S'il n'est pas accessible au moment\n"
            "de la sauvegarde (partage réseau non monté...), le dialogue\n"
            "retombe sur /tmp.")
        btn_browse = QtWidgets.QPushButton("Parcourir...")
        btn_browse.clicked.connect(self._browse_gcode_dir)
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.edt_gcode_dir, 1)
        row_layout.addWidget(btn_browse, 0)
        form.addRow("Dossier G-code :", row)

        self.spn_rapid = QtWidgets.QDoubleSpinBox()
        self.spn_rapid.setRange(100.0, 60000.0)
        self.spn_rapid.setDecimals(0)
        self.spn_rapid.setValue(settings["rapid_feed_mm_min"])
        self.spn_rapid.setSuffix(" mm/min")
        self.spn_rapid.setToolTip(
            "Vitesse rapide (G0) SUPPOSÉE pour l'estimation de durée des\n"
            "jobs -- la vraie vitesse machine n'est pas connue ici. Mettre\n"
            "la MAX_VELOCITY de ton LinuxCNC pour des estimations réalistes.\n"
            "N'affecte que l'estimation, jamais le G-code généré.")
        form.addRow("Vitesse rapide (estimation) :", self.spn_rapid)

        self.spn_clearance = QtWidgets.QDoubleSpinBox()
        self.spn_clearance.setRange(0.0, 100.0)
        self.spn_clearance.setDecimals(1)
        self.spn_clearance.setValue(settings["travel_clearance_mm"])
        self.spn_clearance.setSuffix(" mm")
        self.spn_clearance.setToolTip(
            "Marge AJOUTÉE au Z de travail pour les déplacements à vide et\n"
            "le début/fin de job (modes Grille de test et Découpe à plat --\n"
            "les modes sur surface courbe ont leur propre champ Marge de\n"
            "sécurité). Utile pour survoler brides/serre-flans ; 0 = les\n"
            "transits restent au Z de travail. Sans effet sur le Z de\n"
            "gravure/découpe lui-même.")
        form.addRow("Marge de survol (transits) :", self.spn_clearance)

        self.spn_frame_power = QtWidgets.QDoubleSpinBox()
        self.spn_frame_power.setRange(0.0, 1000.0)
        self.spn_frame_power.setDecimals(0)
        self.spn_frame_power.setValue(settings["frame_power"])
        self.spn_frame_power.setToolTip(
            "Puissance (valeur S) du faisceau pendant l'aperçu cadrage,\n"
            "pour VISUALISER la zone de travail sur la pièce. 0 = laser\n"
            "éteint (comportement historique). Sinon, régler TRÈS FAIBLE\n"
            "(S5-S20 typiquement) : juste de quoi voir le point sans\n"
            "marquer le matériau -- à valider sur une chute.")
        form.addRow("Puissance de cadrage (S) :", self.spn_frame_power)

        self.spn_frame_feed = QtWidgets.QDoubleSpinBox()
        self.spn_frame_feed.setRange(1.0, 20000.0)
        self.spn_frame_feed.setDecimals(0)
        self.spn_frame_feed.setValue(settings["frame_feed_mm_min"])
        self.spn_frame_feed.setSuffix(" mm/min")
        self.spn_frame_feed.setToolTip(
            "Vitesse du tracé de cadrage quand le faisceau de visée est\n"
            "allumé (sans effet si la puissance de cadrage est 0 : le\n"
            "tracé se fait alors en rapides G0). Plus lent = plus le\n"
            "rectangle est facile à suivre à l'œil.")
        form.addRow("Vitesse de cadrage :", self.spn_frame_feed)

        # --- G-code / machine ---
        self.edt_spindle = QtWidgets.QLineEdit(settings["spindle_select"])
        self.edt_spindle.setToolTip(
            "Sélecteur multi-broche ajouté aux commandes S/M3/M5 (LinuxCNC :\n"
            "\"$1\" = spindle 1 = laser). Vider n'est pas accepté ; pour un\n"
            "contrôleur mono-broche (GRBL...), utiliser \"$0\" ou adapter\n"
            "CMD_* dans laser_core.py.")
        form.addRow("Sélecteur broche :", self.edt_spindle)

        self.spn_dwell = QtWidgets.QDoubleSpinBox()
        self.spn_dwell.setRange(0.0, 30.0)
        self.spn_dwell.setDecimals(1)
        self.spn_dwell.setValue(settings["arm_dwell_s"])
        self.spn_dwell.setSuffix(" s")
        self.spn_dwell.setToolTip(
            "Pause (G4) après l'armement du laser (M3 à puissance nulle),\n"
            "le temps que l'électronique du module soit prête avant le\n"
            "premier trait.")
        form.addRow("Temporisation d'armement :", self.spn_dwell)

        # --- Sécurité découpe ---
        self.spn_safe_height = QtWidgets.QDoubleSpinBox()
        self.spn_safe_height.setRange(0.0, 20.0)
        self.spn_safe_height.setDecimals(1)
        self.spn_safe_height.setValue(settings["safe_min_nozzle_height_mm"])
        self.spn_safe_height.setSuffix(" mm")
        self.spn_safe_height.setToolTip(
            "Butée de sécurité : la hauteur du bec au-dessus de la surface\n"
            "ne descend JAMAIS en dessous de cette valeur au fil des passes\n"
            "de découpe, même si le suivi de foyer idéal voudrait plus bas.\n"
            "Garde-fou anti-collision.")
        form.addRow("Hauteur bec minimale :", self.spn_safe_height)

        self.spn_max_thickness = QtWidgets.QDoubleSpinBox()
        self.spn_max_thickness.setRange(1.0, 50.0)
        self.spn_max_thickness.setDecimals(1)
        self.spn_max_thickness.setValue(settings["max_thickness_warning_mm"])
        self.spn_max_thickness.setSuffix(" mm")
        self.spn_max_thickness.setToolTip(
            "Épaisseur au-delà de laquelle un avertissement est émis à la\n"
            "génération d'une découpe (au-delà de la plage vérifiée du\n"
            "constructeur, la qualité se dégrade). N'empêche pas de générer.")
        form.addRow("Épaisseur max sans avertir :", self.spn_max_thickness)

        self.spn_max_step = QtWidgets.QDoubleSpinBox()
        self.spn_max_step.setRange(0.1, 10.0)
        self.spn_max_step.setDecimals(1)
        self.spn_max_step.setValue(settings["recommended_max_step_mm"])
        self.spn_max_step.setSuffix(" mm")
        self.spn_max_step.setToolTip(
            "Pas Z par passe au-delà duquel un avertissement est émis\n"
            "(un pas trop grand peut faire écran au faisceau dans le trait\n"
            "déjà coupé). N'empêche pas de générer.")
        form.addRow("Pas Z max sans avertir :", self.spn_max_step)

        # --- Profil du bec (anti-collision surfaces courbes) ---
        lbl_nozzle = QtWidgets.QLabel(
            "Profil du bec (contrôle anti-collision des modes sur surface\n"
            "courbe). Tube droit : bas = haut = diamètre du tube. Section\n"
            "rectangulaire : entrer la diagonale.")
        lbl_nozzle.setWordWrap(True)
        form.addRow(lbl_nozzle)

        self.spn_nozzle_bottom = QtWidgets.QDoubleSpinBox()
        self.spn_nozzle_bottom.setRange(0.5, 100.0)
        self.spn_nozzle_bottom.setDecimals(1)
        self.spn_nozzle_bottom.setValue(nozzle["bottom_diameter_mm"])
        self.spn_nozzle_bottom.setSuffix(" mm")
        self.spn_nozzle_bottom.setToolTip(
            "Diamètre du bec à son point le plus bas (la pointe).")
        form.addRow("Bec : diamètre pointe :", self.spn_nozzle_bottom)

        self.spn_nozzle_top = QtWidgets.QDoubleSpinBox()
        self.spn_nozzle_top.setRange(0.5, 100.0)
        self.spn_nozzle_top.setDecimals(1)
        self.spn_nozzle_top.setValue(nozzle["top_diameter_mm"])
        self.spn_nozzle_top.setSuffix(" mm")
        self.spn_nozzle_top.setToolTip(
            "Diamètre du bec au sommet du cône (>= diamètre pointe).")
        form.addRow("Bec : diamètre sommet :", self.spn_nozzle_top)

        self.spn_nozzle_height = QtWidgets.QDoubleSpinBox()
        self.spn_nozzle_height.setRange(1.0, 100.0)
        self.spn_nozzle_height.setDecimals(1)
        self.spn_nozzle_height.setValue(nozzle["height_mm"])
        self.spn_nozzle_height.setSuffix(" mm")
        self.spn_nozzle_height.setToolTip(
            "Hauteur du cône (au-dessus : cylindre au diamètre du sommet).")
        form.addRow("Bec : hauteur du cône :", self.spn_nozzle_height)

        lbl = QtWidgets.QLabel(
            "Enregistré dans laser_atelier_config.json et appliqué\n"
            "immédiatement (les panneaux déjà ouverts gardent leurs\n"
            "infobulles d'origine).")
        lbl.setWordWrap(True)
        form.addRow(lbl)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Préférences Atelier Laser")
        self.form.setWindowIcon(_icon("settings.svg"))

    def _browse_gcode_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.form, "Dossier G-code par défaut",
            self.edt_gcode_dir.text() or os.path.expanduser("~"))
        if path:
            self.edt_gcode_dir.setText(path)

    def accept(self):
        if not self.edt_gcode_dir.text().strip():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Le dossier G-code ne peut pas être vide.")
            return False
        if not self.edt_spindle.text().strip():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Le sélecteur broche ne peut pas être vide.")
            return False
        if self.spn_nozzle_bottom.value() > self.spn_nozzle_top.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Profil du bec incohérent : le diamètre à la pointe doit être\n"
                "inférieur ou égal au diamètre au sommet.")
            return False
        core.save_settings({
            "gcode_dir": self.edt_gcode_dir.text().strip(),
            "spindle_select": self.edt_spindle.text().strip(),
            "arm_dwell_s": self.spn_dwell.value(),
            "rapid_feed_mm_min": self.spn_rapid.value(),
            "travel_clearance_mm": self.spn_clearance.value(),
            "frame_power": self.spn_frame_power.value(),
            "frame_feed_mm_min": self.spn_frame_feed.value(),
            "safe_min_nozzle_height_mm": self.spn_safe_height.value(),
            "max_thickness_warning_mm": self.spn_max_thickness.value(),
            "recommended_max_step_mm": self.spn_max_step.value(),
        })
        core.save_nozzle(self.spn_nozzle_bottom.value(),
                         self.spn_nozzle_top.value(),
                         self.spn_nozzle_height.value())
        FreeCAD.Console.PrintMessage("Préférences Atelier Laser enregistrées.\n")
        return True

    def reject(self):
        return True
