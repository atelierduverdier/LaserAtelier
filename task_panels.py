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


def _icon_pixmap(name, size):
    """Pixmap d'une icône SVG à la taille voulue, ou None si le rendu
    échoue (Qt sans support SVG...) -- l'appelant se rabat alors sur le
    texte seul, jamais de plantage."""
    try:
        pm = _icon(name).pixmap(size, size)
        return pm if not pm.isNull() else None
    except Exception:
        return None


class _WrapLabel(QtWidgets.QLabel):
    """QLabel de paragraphe : word-wrap activé, et retours à la ligne
    manuels (\\n) transformés en espaces à chaque setText. Le panneau des
    tâches est étroit et non redimensionnable de façon fiable ; avec des
    \\n manuels ET le word-wrap, Qt conserve les \\n PUIS recoupe
    par-dessus quand un segment dépasse la largeur -- d'où du texte en
    escalier, coupé au mauvais endroit. En laissant Qt seul gérer le
    retour à la ligne (texte replié en un seul flux d'espaces), le texte
    s'adapte proprement à la largeur réelle. Les info-bulles (setToolTip)
    ne sont pas concernées : elles ne sont pas repliées et gardent leurs
    \\n tels quels."""

    def __init__(self, text=""):
        super().__init__()
        self.setWordWrap(True)
        self.setText(text)

    def setText(self, text):
        super().setText(" ".join(str(text).split()))


def _panel_header(form, icon_name, title):
    """Bandeau en tête de panneau : icône du mode + nom en gras/agrandi,
    suivi d'un trait. Repère visuel immédiat du mode ouvert."""
    row = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(row)
    lay.setContentsMargins(0, 2, 0, 2)
    pm = _icon_pixmap(icon_name, 28)
    if pm is not None:
        ico = QtWidgets.QLabel()
        ico.setPixmap(pm)
        lay.addWidget(ico, 0)
    lbl = QtWidgets.QLabel(title)
    lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
    lay.addWidget(lbl, 1)
    form.addRow(row)
    _hline(form)


def _section(form, title, icon_name=None):
    """Titre de section : petit picto (optionnel) + libellé gras, suivi
    d'un trait fin -- pour regrouper visuellement les champs d'un panneau
    dense."""
    row = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(row)
    lay.setContentsMargins(0, 6, 0, 0)
    pm = _icon_pixmap(icon_name, 16) if icon_name else None
    if pm is not None:
        ico = QtWidgets.QLabel()
        ico.setPixmap(pm)
        lay.addWidget(ico, 0)
    lbl = QtWidgets.QLabel(title)
    lbl.setStyleSheet("font-weight: bold; color: #ff8a00;")
    lay.addWidget(lbl, 1)
    form.addRow(row)
    _hline(form)


def _intro(form, resume, details=None):
    """En-tête d'explication d'un panneau : un RÉSUMÉ court toujours
    visible (1-2 phrases, l'essentiel pour quelqu'un qui découvre le
    mode), et des DÉTAILS optionnels repliés derrière un bouton « En
    savoir plus » -- le pavé complet reste à un clic sans encombrer le
    panneau. Renvoie le label de détails (pour d'éventuels ajustements)."""
    lbl = _WrapLabel(resume)
    form.addRow(lbl)
    if not details:
        return None
    btn = QtWidgets.QToolButton()
    btn.setText("En savoir plus")
    btn.setCheckable(True)
    btn.setArrowType(QtCore.Qt.RightArrow)
    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    btn.setAutoRaise(True)
    det = _WrapLabel(details)
    det.setVisible(False)

    def _toggle(on):
        det.setVisible(on)
        btn.setArrowType(QtCore.Qt.DownArrow if on else QtCore.Qt.RightArrow)
    btn.toggled.connect(_toggle)
    form.addRow(btn)
    form.addRow(det)
    return det


def _bullet_list(form, items, indent=10):
    """Liste à puces/étapes : UN label par élément (chacun sur sa propre
    ligne, replié individuellement par Qt) -- à utiliser pour toute
    énumération, car _WrapLabel aplatit les \\n : une liste entière dans
    un seul label redevient un pavé d'une seule coulée."""
    for item in items:
        lbl = _WrapLabel(item)
        lbl.setContentsMargins(indent, 0, 0, 2)
        form.addRow(lbl)


def _diagram(form, name, width=260, height=100):
    """Petit schéma explicatif (SVG de resources/icons) inséré comme une
    rangée du formulaire, centré -- un dessin vaut un paragraphe. Ne fait
    rien si le rendu échoue (le texte reste seul, jamais de plantage)."""
    try:
        pm = _icon(name).pixmap(width, height)
        if pm.isNull():
            return
    except Exception:
        return
    lbl = QtWidgets.QLabel()
    lbl.setPixmap(pm)
    lbl.setAlignment(QtCore.Qt.AlignHCenter)
    form.addRow(lbl)


def _hline(form):
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    form.addRow(line)


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
    lbl = _WrapLabel("Durée estimée : --")
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


# --- Mémorisation des derniers réglages par panneau ----------------------
# Chaque panneau enregistre self._last_fields = {clé: widget} puis appelle
# _restore_last_values à la fin de son __init__ et _save_last_values dans
# accept() : rouvrir un panneau retrouve les valeurs de la dernière fois au
# lieu de repartir des défauts (les préréglages matériau nommés restent le
# mécanisme explicite ; ceci est un "dernier état" implicite, clé
# "last_<panneau>" du même laser_atelier_config.json).
def _widget_get(w):
    if isinstance(w, QtWidgets.QComboBox):
        return w.currentIndex()
    if isinstance(w, QtWidgets.QCheckBox):
        return w.isChecked()
    if isinstance(w, (QtWidgets.QDoubleSpinBox, QtWidgets.QSpinBox)):
        return w.value()
    if isinstance(w, QtWidgets.QLineEdit):
        return w.text()
    return None


def _widget_set(w, v):
    try:
        if isinstance(w, QtWidgets.QComboBox):
            idx = int(v)
            if 0 <= idx < w.count():
                w.setCurrentIndex(idx)
        elif isinstance(w, QtWidgets.QCheckBox):
            w.setChecked(bool(v))
        elif isinstance(w, QtWidgets.QSpinBox):
            w.setValue(int(v))
        elif isinstance(w, QtWidgets.QDoubleSpinBox):
            w.setValue(float(v))
        elif isinstance(w, QtWidgets.QLineEdit):
            w.setText(str(v))
    except Exception:
        pass  # valeur stockée invalide : le défaut du widget reste


def _set_row_visible(form, widget, visible):
    """Masque une LIGNE ENTIÈRE (libellé + champ) d'un QFormLayout.
    setVisible sur le seul champ laisse le libellé orphelin (lignes vides
    « Longueur tiret : » etc. quand un autre style est choisi).
    setRowVisible (Qt 6.4+) replie proprement la ligne ; repli manuel
    sur le libellé sinon."""
    try:
        form.setRowVisible(widget, visible)
    except (AttributeError, TypeError, RuntimeError):
        widget.setVisible(visible)
        lbl = form.labelForField(widget)
        if lbl is not None:
            lbl.setVisible(visible)


def _restore_last_values(panel_key, fields):
    values = core.load_config().get("last_" + panel_key)
    if not isinstance(values, dict):
        return
    for name, widget in fields.items():
        if name in values:
            _widget_set(widget, values[name])


def _save_last_values(panel_key, fields):
    cfg = core.load_config()
    cfg["last_" + panel_key] = {name: _widget_get(w) for name, w in fields.items()}
    core.save_config(cfg)


# --- Job combiné : opérations empilées depuis les vrais modes ---------------
# En MÉMOIRE pour la session FreeCAD (les params portent des edges/probe =
# objets Part, non sérialisables en config). Chaque mode y ajoute son réglage
# COMPLET via « Ajouter au job combiné » ; le mode Job combiné lit cette liste.
_COMBINED_OPS = []


def _add_to_combined_job(operation):
    """Ajoute une opération {type,label,params} au job combiné et informe."""
    _COMBINED_OPS.append(operation)
    # Ferme le panneau courant : l'ajout EST l'action voulue. Sans ça, il
    # fallait cliquer Annuler -- OK aurait relancé la génération d'un fichier
    # séparé, ce qui n'était pas intuitif.
    Gui.Control.closeDialog()
    QtWidgets.QMessageBox.information(
        None, "Job combiné",
        "\u00ab {} \u00bb ajouté au job combiné ({} opération(s) en attente).\n\n"
        "Ouvre le mode \u00ab Job combiné \u00bb pour les ordonner et générer "
        "le fichier unique.".format(operation.get("label", "Opération"), len(_COMBINED_OPS)))


def _combined_add_button(form, handler):
    """Bouton « Ajouter au job combiné » partagé par les modes combinables."""
    btn = QtWidgets.QPushButton("\u2795 Ajouter au job combiné")
    btn.setToolTip(
        "Empile CE réglage (avec toutes ses options) comme une opération du\n"
        "Job combiné, au lieu de générer un fichier tout de suite. Ouvre\n"
        "ensuite \u00ab Job combiné \u00bb pour les ordonner et générer un\n"
        "seul fichier (armement unique).")
    btn.clicked.connect(handler)
    form.addRow(btn)
    return btn


class _PresetController:
    """Bloc de préréglages (sélecteur + Sauvegarder + Supprimer) réutilisable,
    adossé aux préréglages d'USINE + UTILISATEUR d'une catégorie. Un
    préréglage = un instantané de `fields_getter()` (dict nom -> widget),
    via _widget_get/_widget_set (même mécanique que la mémorisation de la
    dernière session). Les préréglages d'usine (★) ne sont pas supprimables.
    `on_loaded` est appelé après chargement (pour rafraîchir les aperçus).

    Le sélecteur/les boutons sont ajoutés à `form` tout de suite ; les
    champs (fields_getter) et on_loaded ne sont lus qu'à l'interaction,
    donc l'appelant peut placer ce bloc EN HAUT du panneau et définir
    self._last_fields plus loin dans son __init__."""

    def __init__(self, form, parent_widget, category, fields_getter, on_loaded=None):
        self.category = category
        self.fields_getter = fields_getter
        self.parent = parent_widget
        self.on_loaded = on_loaded

        _section(form, "Préréglages", "sect_preset.svg")
        self.combo = QtWidgets.QComboBox()
        self.combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(18)
        self.combo.setToolTip(
            "Charge un jeu complet de réglages. Les ★ sont fournis d'usine\n"
            "(points de départ utiles, non supprimables) ; les autres sont\n"
            "les tiens. Choisis-en un pour remplir tous les champs d'un coup,\n"
            "ajuste, puis « Sauvegarder » sous un nom pour créer le tien.")
        form.addRow("Préréglage :", self.combo)

        btn_save = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        btn_save.setToolTip("Enregistre toutes les valeurs du panneau sous un nom.")
        btn_save.clicked.connect(self._on_save)
        form.addRow(btn_save)

        btn_del = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        btn_del.clicked.connect(self._on_delete)
        form.addRow(btn_del)

        self.combo.currentIndexChanged.connect(self._on_selected)
        self._populate()

    def _populate(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("-- Choisir --", None)
        factory = core.factory_presets(self.category)
        user = core.load_presets(self.category)
        for name in factory:
            self.combo.addItem("★ " + name, name)
        for name in sorted(user):
            if name not in factory:
                self.combo.addItem(name, name)
        self.combo.blockSignals(False)

    def _on_selected(self, index):
        if index <= 0:
            return
        name = self.combo.currentData()
        values = core.all_presets(self.category).get(name)
        fields = self.fields_getter() or {}
        if not values:
            return
        for key, widget in fields.items():
            if key in values:
                _widget_set(widget, values[key])
        if self.on_loaded:
            self.on_loaded()

    def _on_save(self):
        current = self.combo.currentData() or ""
        name, ok = QtWidgets.QInputDialog.getText(
            self.parent, "Sauvegarder le préréglage",
            "Nom du préréglage :", text=current)
        name = name.strip()
        if not ok or not name:
            return
        fields = self.fields_getter() or {}
        core.save_preset(self.category, name, {k: _widget_get(w) for k, w in fields.items()})
        self._populate()
        i = self.combo.findData(name)
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def _on_delete(self):
        name = self.combo.currentData()
        if not name:
            return
        if name not in core.load_presets(self.category):
            QtWidgets.QMessageBox.information(
                self.parent, "Préréglage d'usine",
                "« {} » est un préréglage d'usine : il ne peut pas être\n"
                "supprimé. Tu peux le charger, l'ajuster, puis le sauvegarder\n"
                "sous un autre nom.".format(name))
            return
        reply = QtWidgets.QMessageBox.question(
            self.parent, "Supprimer", "Supprimer le préréglage « {} » ?".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply != QtWidgets.QMessageBox.Yes:
            return
        core.delete_preset(self.category, name)
        self._populate()


def _make_fluence_widgets(form, ref_power=500.0, ref_feed=800.0, ref_spot=1.0):
    """Ajoute une section « Puissance vs défocus » à `form` (compensation
    de la puissance selon le défocus, cf. line_fluence dans laser_core) et
    renvoie ses widgets, dont "container" (un QGroupBox regroupant tout,
    à masquer d'un bloc quand la section n'a pas lieu d'être). L'appelant
    câble l'aperçu (self.<...>.valueChanged) et lit chk pour compenser la
    puissance à la génération. La référence (matériau) est sauvegardée
    dans le préréglage matériau et la dernière session."""
    box = QtWidgets.QGroupBox("Puissance vs défocus")
    inner = QtWidgets.QFormLayout(box)
    inner.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

    lbl = _WrapLabel(
        "Défocaliser étale la puissance sur un point plus large : le trait\n"
        "pâlit, voire ne marque plus. Renseigne un réglage de RÉFÉRENCE\n"
        "connu bon sur ce matériau (une gravure réussie) ; l'atelier compare\n"
        "la fluence (énergie déposée) du réglage actuel à cette référence.")
    inner.addRow(lbl)

    chk = QtWidgets.QCheckBox("Compenser la puissance automatiquement")
    chk.setToolTip(
        "Coché : la puissance est CALCULÉE pour déposer la même énergie\n"
        "qu'à la référence, au défocus et à la vitesse actuels (la\n"
        "puissance saisie plus haut est alors ignorée). Décoché : la\n"
        "puissance saisie est utilisée telle quelle, et l'atelier indique\n"
        "seulement la fluence obtenue par rapport à la référence (à toi\n"
        "d'ajuster). Utile pour comparer les deux approches sur une chute.")
    inner.addRow(chk)

    ref_power_w = QtWidgets.QDoubleSpinBox()
    ref_power_w.setRange(0, core.S_MAX)
    ref_power_w.setValue(ref_power)
    ref_power_w.setToolTip("Puissance (S) du réglage de référence connu bon.")
    inner.addRow("Réf. puissance (S) :", ref_power_w)

    ref_feed_w = QtWidgets.QDoubleSpinBox()
    ref_feed_w.setRange(1, 20000)
    ref_feed_w.setValue(ref_feed)
    ref_feed_w.setSuffix(" mm/min")
    ref_feed_w.setToolTip("Vitesse d'avance du réglage de référence.")
    inner.addRow("Réf. vitesse :", ref_feed_w)

    ref_spot_w = QtWidgets.QDoubleSpinBox()
    ref_spot_w.setRange(0.02, 30.0)
    ref_spot_w.setDecimals(2)
    ref_spot_w.setValue(ref_spot)
    ref_spot_w.setSuffix(" mm")
    ref_spot_w.setToolTip(
        "LARGEUR du point AVEC laquelle la référence a été gravée (au\n"
        "foyer, c'est le « point au foyer » des Préférences ; défocalisée,\n"
        "c'est la largeur du trait de la gravure de référence, mesurable\n"
        "au pied à coulisse ou lue sur la bande de calibration défocus).")
    inner.addRow("Réf. largeur du point :", ref_spot_w)

    info = _WrapLabel("")
    inner.addRow(info)

    form.addRow(box)
    return {"container": box, "chk": chk, "ref_power": ref_power_w,
            "ref_feed": ref_feed_w, "ref_spot": ref_spot_w, "info": info}


def _fluence_advice(spot, power, feed, w):
    """Texte d'aperçu + puissance effective pour la section fluence.
    `spot` = diamètre de point ACTUEL (mm), `power`/`feed` = réglage
    actuel, `w` = widgets renvoyés par _make_fluence_widgets. Renvoie
    (texte, couleur, puissance_effective) : puissance_effective = valeur
    compensée si la case est cochée, sinon None (l'appelant garde sa
    puissance saisie)."""
    ref_spot = w["ref_spot"].value()
    ref_power = w["ref_power"].value()
    ref_feed = w["ref_feed"].value()
    if w["chk"].isChecked():
        p_eff = core.power_for_line_fluence(feed, spot, ref_power, ref_feed, ref_spot)
        if p_eff is None:
            return ("Référence invalide : renseigne puissance/vitesse/largeur.",
                    "#b0740a", None)
        clipped = min(p_eff, core.S_MAX)
        txt = "Puissance compensée : S{:.0f}".format(clipped)
        if p_eff > core.S_MAX:
            txt += " (plafonnée à {:g} -- la référence demande S{:.0f}, hors échelle : ralentir ou point plus fin)".format(core.S_MAX, p_eff)
        txt += " -- pour un point de {:.2f} mm.".format(spot)
        return (txt, "#2e7d32", clipped)
    ratio = core.relative_line_fluence(power, feed, spot, ref_power, ref_feed, ref_spot)
    if ratio is None:
        return ("Référence invalide : renseigne puissance/vitesse/largeur.",
                "#b0740a", None)
    suggested = core.power_for_line_fluence(feed, spot, ref_power, ref_feed, ref_spot)
    txt = "Fluence actuelle : {:.0f}% de la référence".format(ratio * 100.0)
    if ratio < 0.85:
        txt += " -- TROP FAIBLE, risque de trait pâle/absent."
        color = "#c0392b"
    elif ratio > 1.2:
        txt += " -- élevée, risque de sur-brûlage."
        color = "#b0740a"
    else:
        txt += " -- proche de la référence."
        color = "#2e7d32"
    if suggested is not None:
        txt += " Pour l'égaler : S{:.0f}.".format(min(suggested, core.S_MAX))
    return (txt, color, None)


# ==========================================================================
# GUIDE RAPIDE (point d'entrée pour découvrir l'atelier)
# ==========================================================================
class TaskPanelGuide:
    """Panneau purement informatif : le flux de travail de l'atelier et
    « quel mode pour quoi ? » -- le point d'entrée de quelqu'un qui
    connaît FreeCAD mais découvre cet atelier. Aucune logique, que du
    texte et des schémas."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "guide.svg", "Guide rapide de l'atelier")
        _diagram(form, "diag_pipeline.svg", width=280, height=110)

        _section(form, "Le flux de travail", "sect_options.svg")
        _bullet_list(form, [
            "1. CALIBRER (une fois) : Préférences (engrenage) -- focale, "
            "calibration du point via la Bande de calibration défocus, "
            "offsets de l'outil laser via le Test des offsets.",
            "2. TESTER sur une chute : Grille de test ou Rampe "
            "puissance/vitesse pour trouver les bons réglages du matériau.",
            "3. MOTIF : Hachures 2D (remplissage), texte/forme (Gravure "
            "remplie), image (Gravure photo) -- et Projection si la pièce "
            "est courbe.",
            "4. G-CODE : Marquage, Gravure remplie ou Découpe génèrent le "
            "fichier .ngc.",
            "5. CADRAGE : chaque mode propose un fichier d'aperçu séparé "
            "(rectangle englobant, laser éteint) à lancer d'abord pour "
            "vérifier le positionnement.",
            "6. GRAVER : sur LinuxCNC, faire T{} M6 AVANT de lancer le "
            "fichier (rappelé dans chaque G-code généré).".format(int(core.LASER_TOOL)),
        ])

        _section(form, "Quel mode pour quoi ?", "sect_gcode.svg")
        _bullet_list(form, [
            "• Graver un TEXTE ou une FORME en noir : Gravure remplie.",
            "• Graver une PHOTO : Gravure photo (trame de points).",
            "• Remplir une face de hachures (géométrie) : Hachures 2D, puis "
            "Marquage pour le G-code.",
            "• Graver sur une pièce BOMBÉE : Hachures 2D → Projection → "
            "Marquage (motif + modèle 3D sélectionnés ensemble).",
            "• DÉCOUPER du plat : Découpe multi-passes (attaches, amorce, "
            "copies en matrice).",
            "• Découper une pièce courbe : Découpe multi-passes (courbe).",
            "• Enchaîner plusieurs opérations en un fichier : Job combiné.",
            "• Trouver les réglages d'un matériau : Grille de test (cellules) "
            "ou Rampe (lignes continues).",
        ])

        _section(form, "Les 3 règles de la maison", "sect_safety.svg")
        _bullet_list(form, [
            "• Zéro Z toujours sur la SURFACE de la pièce (le Z de travail "
            "des Préférences est alors la focale du nez, une constante).",
            "• On MESURE, on ne devine pas : calibration du point, kerf, "
            "offsets -- tout vient d'un test réel sur chute.",
            "• Toujours lancer l'aperçu CADRAGE avant le vrai job, lunettes "
            "laser sur le nez.",
        ])

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Guide rapide de l'atelier")
        self.form.setWindowIcon(_icon("guide.svg"))

    def accept(self):
        return True

    def reject(self):
        return True


# ==========================================================================
# NUANCIER MATÉRIAU (tons de gris mesurés)
# ==========================================================================
class TaskPanelNuancier:
    """Éditeur du nuancier : la palette de gris MESURÉE d'un matériau
    (cf. load_shades dans laser_core). On y consigne, après une grille ou
    une rampe de test, chaque ton jugé utile : réglage (S/F/défocus) +
    résultat mesuré (noirceur %, largeur). Les modes Marquage et Gravure
    remplie proposent ensuite « Appliquer ce ton » d'un clic."""

    _COLS = ("Noirceur %", "Puissance S", "Vitesse F", "Défocus mm",
             "Largeur mm", "Libellé")
    _KEYS = ("darkness", "power", "feed", "z_offset", "width", "label")

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "nuancier.svg", "Nuancier matériau")
        _intro(form,
               "Ta palette de gris MESURÉE, par matériau : chaque ton = un "
               "réglage (S, F, défocus) + ce qu'il produit réellement "
               "(noirceur 0-100 % à l'oeil, largeur du trait).",
               "Alimente-le après une Grille ou une Rampe de test : garde "
               "les cases/zones qui te plaisent, note leur noirceur en les "
               "comparant entre elles (0 = matériau intact, 100 = le noir "
               "max de ce matériau) et leur largeur au pied à coulisse. "
               "La noirceur n'étant pas linéaire avec la puissance, le "
               "logiciel s'appuiera sur CES mesures (ton le plus proche) "
               "pour les dégradés, photos et choix rapides -- « on mesure, "
               "on ne devine pas ». OK enregistre le tableau.")

        self.combo_mat = QtWidgets.QComboBox()
        self.combo_mat.setEditable(True)
        self.combo_mat.setToolTip(
            "Choisis un matériau existant, ou TAPE un nouveau nom (ex.\n"
            "« MDF 6mm ») : OK créera son nuancier avec le tableau saisi.")
        form.addRow("Matériau :", self.combo_mat)

        self.table = QtWidgets.QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(list(self._COLS))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(220)
        self.table.setToolTip(
            "Un ton par ligne. Noirceur : 0-100 % à l'oeil. Défocus : mm\n"
            "au-dessus du foyer (0 = trait net). Largeur : trait mesuré.\n"
            "Libellé libre (ex. « gris moyen », « brun chaud »).")
        form.addRow(self.table)

        btn_add = QtWidgets.QPushButton("+ Ajouter un ton")
        btn_add.clicked.connect(self._on_add_row)
        form.addRow(btn_add)
        btn_del = QtWidgets.QPushButton("Supprimer le ton sélectionné")
        btn_del.clicked.connect(self._on_del_row)
        form.addRow(btn_del)

        self._reload_materials()
        self.combo_mat.activated.connect(lambda _i: self._load_material())

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Nuancier matériau")
        self.form.setWindowIcon(_icon("nuancier.svg"))

    def _reload_materials(self):
        current = self.combo_mat.currentText()
        self.combo_mat.blockSignals(True)
        self.combo_mat.clear()
        self.combo_mat.addItems(core.shade_materials())
        if current:
            self.combo_mat.setCurrentText(current)
        self.combo_mat.blockSignals(False)
        self._load_material()

    def _load_material(self):
        shades = core.load_shades(self.combo_mat.currentText().strip())
        self.table.setRowCount(0)
        for s in shades:
            self._append_row(s)

    def _append_row(self, shade=None):
        shade = shade or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        defaults = {"darkness": 50, "power": 500, "feed": 800,
                    "z_offset": 0.0, "width": 0.0, "label": ""}
        for c, key in enumerate(self._KEYS):
            val = shade.get(key, defaults[key])
            text = val if key == "label" else "{:g}".format(val)
            self.table.setItem(r, c, QtWidgets.QTableWidgetItem(str(text)))

    def _on_add_row(self):
        self._append_row()

    def _on_del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def _table_shades(self):
        """Relit le tableau -> liste de tons ; les lignes dont un nombre
        est illisible sont ignorées avec un avertissement."""
        shades = []
        for r in range(self.table.rowCount()):
            shade = {}
            ok = True
            for c, key in enumerate(self._KEYS):
                item = self.table.item(r, c)
                text = item.text().strip() if item else ""
                if key == "label":
                    shade[key] = text
                    continue
                try:
                    shade[key] = float(text.replace(",", "."))
                except ValueError:
                    ok = False
                    break
            if ok:
                shade["darkness"] = min(100.0, max(0.0, shade["darkness"]))
                shades.append(shade)
            else:
                FreeCAD.Console.PrintWarning(
                    "Nuancier : ligne {} illisible, ignorée.\n".format(r + 1))
        return shades

    def accept(self):
        material = self.combo_mat.currentText().strip()
        if not material:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Donne un nom de matériau (ex. « MDF 6mm »).")
            return False
        core.save_shades(material, self._table_shades())
        FreeCAD.Console.PrintMessage(
            "Nuancier « {} » enregistré ({} ton(s)).\n".format(
                material, self.table.rowCount()))
        return True

    def reject(self):
        return True


def _make_shade_picker(form, on_apply):
    """Bloc « Nuancier matériau » réutilisable dans un panneau de mode :
    sélecteur matériau + ton mesuré + bouton « Appliquer ce ton »
    (on_apply(shade) est appelé avec le dict du ton). Renvoie ses widgets ;
    l'appelant appelle ["reload"]() en fin d'__init__."""
    _section(form, "Nuancier matériau", "sect_preset.svg")
    combo_mat = QtWidgets.QComboBox()
    combo_mat.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo_mat.setMinimumContentsLength(14)
    combo_mat.setToolTip(
        "Matériau du nuancier (tons de gris MESURÉS, cf. le mode Nuancier\n"
        "dans Tests & calibration).")
    form.addRow("Matériau :", combo_mat)

    combo_shade = QtWidgets.QComboBox()
    combo_shade.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo_shade.setMinimumContentsLength(18)
    combo_shade.setToolTip("Ton mesuré : noirceur % -- réglage (largeur).")
    form.addRow("Ton :", combo_shade)

    btn = QtWidgets.QPushButton("Appliquer ce ton")
    btn.setToolTip(
        "Remplit puissance/vitesse (et défocus si le ton en a un) avec ce\n"
        "réglage MESURÉ -- le rendu sur la pièce sera celui constaté lors\n"
        "du test.")
    form.addRow(btn)

    def _reload_shades():
        combo_shade.clear()
        m = combo_mat.currentData()
        if not m:
            combo_shade.addItem("-- (aucun ton) --", None)
            return
        for s in core.load_shades(m):
            combo_shade.addItem(core.shade_summary(s), s)

    def _reload():
        combo_mat.blockSignals(True)
        combo_mat.clear()
        mats = core.shade_materials()
        if not mats:
            combo_mat.addItem("-- (nuancier vide) --", None)
        for m in mats:
            combo_mat.addItem(m, m)
        combo_mat.blockSignals(False)
        _reload_shades()

    combo_mat.currentIndexChanged.connect(lambda _i: _reload_shades())

    def _apply():
        s = combo_shade.currentData()
        if s:
            on_apply(s)
    btn.clicked.connect(_apply)

    return {"mat": combo_mat, "shade": combo_shade, "reload": _reload}


# ==========================================================================
# MODE : HACHURES 2D
# ==========================================================================
class TaskPanelHatch:
    def __init__(self, selection):
        self.selection = selection
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        _panel_header(form, "hatch.svg", "Hachures 2D (géométrie)")
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _intro(form,
               "Remplit la face 2D sélectionnée de hachures et crée un objet "
               "« Hachures » dans le document. GÉOMÉTRIE SEULE : aucun G-code "
               "ici -- grave ensuite cet objet avec le mode Marquage (ou "
               "projette-le d'abord sur une surface 3D).",
               "Trois types : Parallèles (zigzag, défaut), Croisées (2 passes à "
               "angle+90, plus dense) et Défocus (destiné à être gravé avec le "
               "point laser élargi pour noircir en un seul passage -- le défocus "
               "à utiliser est calculé plus bas depuis la calibration des "
               "Préférences). Le Retrait du bord rentre les hachures pour que "
               "la brûlure ne déborde pas de la forme.")

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

        self.spn_inset = QtWidgets.QDoubleSpinBox()
        self.spn_inset.setRange(0.0, 20.0)
        self.spn_inset.setDecimals(2)
        self.spn_inset.setValue(0.0)
        self.spn_inset.setSuffix(" mm")
        self.spn_inset.setToolTip(
            "RETRAIT DU BORD : rentre les hachures de cette marge vers\n"
            "l'intérieur de la forme (0 = bord à bord). Le trait laser a\n"
            "une largeur -- surtout en défocus, pointillé ou vague (mode\n"
            "Marquage), où le point est élargi : bord à bord, la brûlure\n"
            "DÉBORDE de la forme d'environ un rayon de point. Mettre ici\n"
            "le rayon du point élargi garde la brûlure à l'intérieur (la\n"
            "valeur recommandée s'affiche plus bas en mode Défocus).\n"
            "La Gravure remplie fait ce retrait automatiquement.")
        form.addRow("Retrait du bord :", self.spn_inset)

        self.lbl_defocus_result = _WrapLabel("Défocus calculé : --")
        form.addRow(self.lbl_defocus_result)

        def _update_defocus_preview():
            # Calibration du point : centralisée dans les Préférences
            # (icône engrenage), plus de champs resaisis ici.
            half_angle = core.calibrated_half_angle()
            defocus = core.defocus_for_fill_spacing(
                self.spn_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration du point invalide dans\n"
                    "les Préférences : le point au défocus de test doit être\n"
                    "plus large qu'au foyer -- à mesurer avec la Bande de\n"
                    "calibration défocus puis à saisir dans les Préférences).")
            else:
                spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.3f} mm -- à AJOUTER au Z de travail\n"
                    "(mode Marquage/Découpe) pour cette passe de remplissage.\n"
                    "Point élargi : {:.2f} mm -- Retrait du bord recommandé :\n"
                    "{:.2f} mm (rayon du point) pour que la brûlure ne déborde\n"
                    "pas de la forme.\n"
                    "(Calibration du point : Préférences, icône engrenage.)".format(
                        defocus, spot, spot / 2.0))

        def _on_filltype_changed(idx):
            self.lbl_defocus_result.setVisible(idx == 2)
            _update_defocus_preview()

        self.combo_filltype.currentIndexChanged.connect(_on_filltype_changed)
        self.spn_spacing.valueChanged.connect(lambda _v: _update_defocus_preview())
        _on_filltype_changed(self.combo_filltype.currentIndex())

        self._last_fields = {
            "filltype": self.combo_filltype, "spacing": self.spn_spacing,
            "angle": self.spn_angle, "inset": self.spn_inset,
        }
        _restore_last_values("hatch", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Hachures 2D")
        self.form.setWindowIcon(_icon("hatch.svg"))

    def accept(self):
        _save_last_values("hatch", self._last_fields)
        fill_type_map = {0: "paralleles", 1: "croisees", 2: "defocus"}
        fill_type = fill_type_map.get(self.combo_filltype.currentIndex(), "paralleles")
        obj, err = core.run_hatch_generation(
            self.selection, self.spn_spacing.value(), self.spn_angle.value(),
            fill_type=fill_type, inset=self.spn_inset.value())
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

        _panel_header(form, "filled.svg", "Gravure remplie (noir)")
        _intro(form,
               "Grave la forme/le texte 2D sélectionné (face, sketch, "
               "ShapeString) en NOIR PLEIN, en deux temps :",
               "Le remplissage utilise le point laser volontairement ÉLARGI "
               "(défocus, calculé depuis la calibration des Préférences pour "
               "l'espacement choisi) et il est rentré du rayon de point pour ne "
               "pas déborder ; le contour est ensuite repassé net au foyer pour "
               "une arête propre. Un seul armement laser pour les deux. Chaque "
               "partie a ses propres styles de trait (plein/tirets/pointillé/"
               "vague) et la section « Puissance vs défocus » aide à garder un "
               "noir constant quel que soit le défocus.")
        _diagram(form, "diag_filled.svg")

        _section(form, "Préréglage matériau", "sect_preset.svg")
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Recharge un jeu complet de réglages sauvegardé sous un nom\n"
            "(typiquement un matériau). Survole un nom pour voir son résumé.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.lbl_preset_summary = _WrapLabel("")
        self.lbl_preset_summary.setVisible(False)
        form.addRow(self.lbl_preset_summary)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder comme préréglage...")
        self.btn_save_preset.setToolTip("Sauvegarde toutes les valeurs du panneau sous un nom.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        form.addRow(self.btn_save_preset)

        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer le préréglage sélectionné")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        form.addRow(self.btn_delete_preset)

        def _apply_shade(s):
            # Ton mesuré du nuancier -> puissance/vitesse du REMPLISSAGE
            # (le défocus du remplissage reste calculé depuis l'espacement).
            self.spn_fill_power.setValue(s.get("power", self.spn_fill_power.value()))
            self.spn_fill_feed.setValue(s.get("feed", self.spn_fill_feed.value()))
            self._update_defocus_preview()
        self._shade_picker = _make_shade_picker(form, _apply_shade)

        _section(form, "Remplissage", "sect_fill.svg")
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
        self.spn_fill_power.setRange(0, core.S_MAX)
        self.spn_fill_power.setValue(500)
        self.spn_fill_power.setToolTip("Puissance (S) du remplissage.")
        form.addRow("Puissance remplissage :", self.spn_fill_power)

        self.spn_fill_feed = QtWidgets.QDoubleSpinBox()
        self.spn_fill_feed.setRange(1, 20000)
        self.spn_fill_feed.setValue(800)
        self.spn_fill_feed.setSuffix(" mm/min")
        self.spn_fill_feed.setToolTip("Vitesse d'avance du remplissage.")
        form.addRow("Vitesse remplissage :", self.spn_fill_feed)

        self.chk_perimeter = QtWidgets.QCheckBox("Cerner le remplissage (fermer les blancs au bord)")
        self.chk_perimeter.setChecked(True)
        self.chk_perimeter.setToolTip(
            "Trace le bord de la zone remplie avec le faisceau de remplissage,\n"
            "en plus des hachures. Sans ça, les hachures parallèles laissent\n"
            "une fine bande non brûlée le long du bord (surtout sur les bords\n"
            "obliques) : ce liseré la comble pour un noir plein jusqu'au contour.")
        form.addRow(self.chk_perimeter)

        self._fluence = _make_fluence_widgets(form)

        self.lbl_defocus_result = _WrapLabel("Défocus calculé : --")
        self.lbl_defocus_result.setToolTip(
            "Calculé depuis la calibration du point des Préférences (icône\n"
            "engrenage) -- mesurée avec la Bande de calibration défocus.")
        form.addRow(self.lbl_defocus_result)

        _section(form, "Contour", "sect_contour.svg")
        self.chk_contour = QtWidgets.QCheckBox("Graver le contour (repassé après le remplissage)")
        self.chk_contour.setChecked(True)
        self.chk_contour.setToolTip(
            "Repasse le bord de la forme APRÈS le remplissage, pour une\n"
            "arête nette. Décoche pour ne faire que le remplissage.")
        form.addRow(self.chk_contour)

        self.spn_contour_power = QtWidgets.QDoubleSpinBox()
        self.spn_contour_power.setRange(0, core.S_MAX)
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

        self.lbl_contour_result = _WrapLabel("")
        form.addRow(self.lbl_contour_result)

        self.chk_contour.toggled.connect(self.spn_contour_power.setEnabled)
        self.chk_contour.toggled.connect(self.spn_contour_feed.setEnabled)
        self.chk_contour.toggled.connect(self.spn_contour_width.setEnabled)

        _section(form, "Styles de trait", "sect_options.svg")
        style_items = ["Trait plein", "Tirets", "Pointillé", "Vague défocus"]
        style_tooltip = (
            "Trait plein : trait continu (comportement historique).\n"
            "Tirets : faisceau pulsé le long du tracé (mouvement continu).\n"
            "Pointillé : vrais points ronds -- arrêt + pulse à chaque point\n"
            "(plus lent ; en défocus, gros points doux).\n"
            "Vague défocus : le Z oscille entre le foyer et un défocus max,\n"
            "le trait varie continûment en largeur et en intensité (effet\n"
            "calligraphique). Nécessite la calibration du point ci-dessus.")

        self.combo_fill_style = QtWidgets.QComboBox()
        self.combo_fill_style.addItems(style_items)
        self.combo_fill_style.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_fill_style.setMinimumContentsLength(14)
        self.combo_fill_style.setToolTip("Style des traits du REMPLISSAGE.\n" + style_tooltip)
        form.addRow("Style remplissage :", self.combo_fill_style)

        self.combo_contour_style = QtWidgets.QComboBox()
        self.combo_contour_style.addItems(style_items)
        self.combo_contour_style.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_contour_style.setMinimumContentsLength(14)
        self.combo_contour_style.setToolTip(
            "Style du trait de CONTOUR.\n" + style_tooltip +
            "\nEn Vague, « Épaisseur trait contour » (ci-dessus) devient la\n"
            "largeur MAX de la vague (au foyer le trait reste le plus fin).")
        form.addRow("Style contour :", self.combo_contour_style)

        self.spn_dash_len = QtWidgets.QDoubleSpinBox()
        self.spn_dash_len.setRange(0.2, 50.0)
        self.spn_dash_len.setValue(3.0)
        self.spn_dash_len.setSuffix(" mm")
        self.spn_dash_len.setToolTip("Longueur de chaque tiret (style Tirets).")
        form.addRow("Longueur tiret :", self.spn_dash_len)

        self.spn_gap_len = QtWidgets.QDoubleSpinBox()
        self.spn_gap_len.setRange(0.2, 50.0)
        self.spn_gap_len.setValue(2.0)
        self.spn_gap_len.setSuffix(" mm")
        self.spn_gap_len.setToolTip("Espace entre deux tirets (style Tirets).")
        form.addRow("Espace entre tirets :", self.spn_gap_len)

        self.spn_dot_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_dot_spacing.setRange(0.2, 50.0)
        self.spn_dot_spacing.setValue(1.5)
        self.spn_dot_spacing.setSuffix(" mm")
        self.spn_dot_spacing.setToolTip("Espacement des points le long du tracé (style Pointillé).")
        form.addRow("Espacement points :", self.spn_dot_spacing)

        self.spn_dot_dwell = QtWidgets.QDoubleSpinBox()
        self.spn_dot_dwell.setRange(5.0, 2000.0)
        self.spn_dot_dwell.setDecimals(0)
        self.spn_dot_dwell.setValue(50.0)
        self.spn_dot_dwell.setSuffix(" ms")
        self.spn_dot_dwell.setToolTip(
            "Durée du pulse laser sur chaque point (style Pointillé). Plus\n"
            "long = point plus marqué/profond. La machine s'arrête à chaque\n"
            "point : le job est nettement plus lent qu'un trait continu.")
        form.addRow("Durée du pulse :", self.spn_dot_dwell)

        self.spn_wave_period = QtWidgets.QDoubleSpinBox()
        self.spn_wave_period.setRange(0.5, 100.0)
        self.spn_wave_period.setValue(5.0)
        self.spn_wave_period.setSuffix(" mm")
        self.spn_wave_period.setToolTip(
            "Période de l'oscillation Z (style Vague) : distance le long du\n"
            "tracé entre deux points fins (au foyer). Une période courte à\n"
            "grande vitesse peut dépasser la vitesse de l'axe Z (voir\n"
            "l'avertissement calculé plus bas).")
        form.addRow("Période de la vague :", self.spn_wave_period)

        self.spn_fill_wave_width = QtWidgets.QDoubleSpinBox()
        self.spn_fill_wave_width.setRange(0.1, 10.0)
        self.spn_fill_wave_width.setDecimals(2)
        self.spn_fill_wave_width.setValue(1.5)
        self.spn_fill_wave_width.setSuffix(" mm")
        self.spn_fill_wave_width.setToolTip(
            "Largeur MAX du trait de remplissage en Vague (au sommet de\n"
            "l'oscillation) -- l'amplitude Z est calculée via la calibration\n"
            "du point. Le trait oscille entre le point au foyer et cette\n"
            "largeur.")
        form.addRow("Largeur max vague (rempl.) :", self.spn_fill_wave_width)

        self.lbl_style_info = _WrapLabel("")
        form.addRow(self.lbl_style_info)

        self._style_param_widgets = {
            "tirets": [self.spn_dash_len, self.spn_gap_len],
            "pointille": [self.spn_dot_spacing, self.spn_dot_dwell],
            "vague": [self.spn_wave_period],
        }

        def _update_defocus_preview():
            # Calibration du point : centralisée dans les Préférences.
            half_angle = core.calibrated_half_angle()
            defocus = core.defocus_for_fill_spacing(
                self.spn_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration du point invalide dans\n"
                    "les Préférences : le point au défocus de test doit être\n"
                    "plus large qu'au foyer).")
            else:
                spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.2f} mm (bec remonté d'autant) -- point\n"
                    "{:.3f} mm, remplissage rentré de {:.3f} mm du bord.\n"
                    "(Calibration du point : Préférences, icône engrenage.)".format(
                        defocus, spot, spot / 2.0))
            # Retour visuel du contour : épaisseur voulue -> défocus.
            off = self._contour_offset(half_angle)
            if off <= 0:
                self.lbl_contour_result.setText("Contour : net au foyer (trait le plus fin).")
            else:
                self.lbl_contour_result.setText(
                    "Contour : trait {:.2f} mm -> bec remonté de {:.2f} mm.".format(
                        self.spn_contour_width.value(), off))
            # Fluence du remplissage (compensation puissance/défocus).
            if defocus is not None:
                spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
                txt, color, _ = _fluence_advice(
                    spot, self.spn_fill_power.value(), self.spn_fill_feed.value(),
                    self._fluence)
                self._fluence["info"].setText("Remplissage -- " + txt)
                self._fluence["info"].setStyleSheet("color: {};".format(color))
                self.spn_fill_power.setEnabled(not self._fluence["chk"].isChecked())

        self._update_defocus_preview = _update_defocus_preview
        self.spn_spacing.valueChanged.connect(lambda _v: _update_defocus_preview())
        self.spn_contour_width.valueChanged.connect(lambda _v: _update_defocus_preview())
        for _w in (self.spn_fill_power, self.spn_fill_feed, self._fluence["chk"],
                   self._fluence["ref_power"], self._fluence["ref_feed"],
                   self._fluence["ref_spot"]):
            _sig = _w.toggled if isinstance(_w, QtWidgets.QCheckBox) else _w.valueChanged
            _sig.connect(lambda _v: _update_defocus_preview())

        def _update_style_preview():
            # Visibilité : n'affiche que les paramètres des styles choisis.
            style_map = {0: "plein", 1: "tirets", 2: "pointille", 3: "vague"}
            fill_s = style_map[self.combo_fill_style.currentIndex()]
            contour_s = style_map[self.combo_contour_style.currentIndex()]
            active = {fill_s, contour_s}
            for style, widgets in self._style_param_widgets.items():
                for w in widgets:
                    _set_row_visible(form, w, style in active)
            _set_row_visible(form, self.spn_fill_wave_width, fill_s == "vague")

            # Avertissement vitesse Z crête pour les vagues.
            infos = []
            half_angle = core.calibrated_half_angle()
            period = self.spn_wave_period.value()
            checks = []
            if fill_s == "vague":
                amp = core.defocus_for_fill_spacing(
                    self.spn_fill_wave_width.value(), core.SPOT_FOCUS_MM,
                    half_angle, overlap=1.0)
                checks.append(("remplissage", amp, self.spn_fill_feed.value()))
            if contour_s == "vague":
                checks.append(("contour", self._contour_offset(half_angle),
                               self.spn_contour_feed.value()))
            for what, amp, feed in checks:
                if amp is None:
                    infos.append("Vague {} : calibration du point invalide.".format(what))
                    continue
                peak = core.wave_peak_z_feed(amp, feed, period)
                txt = "Vague {} : amplitude {:.2f} mm, vitesse Z crête ~{:.0f} mm/min".format(
                    what, amp, peak)
                if peak > core.Z_MAX_FEED_MM_MIN:
                    txt += " -- AU-DELÀ de la limite Z supposée ({:.0f}, cf. Préférences) : le trajet sera ralenti".format(
                        core.Z_MAX_FEED_MM_MIN)
                infos.append(txt + ".")
            self.lbl_style_info.setText("\n".join(infos))
            self.lbl_style_info.setVisible(bool(infos))

        self._update_style_preview = _update_style_preview
        self.combo_fill_style.currentIndexChanged.connect(lambda _i: _update_style_preview())
        self.combo_contour_style.currentIndexChanged.connect(lambda _i: _update_style_preview())
        for w in (self.spn_wave_period, self.spn_fill_wave_width, self.spn_fill_feed,
                  self.spn_contour_feed, self.spn_contour_width):
            w.valueChanged.connect(lambda _v: _update_style_preview())

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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

        self._last_fields = {
            "spacing": self.spn_spacing, "angle": self.spn_angle,
            "fill_power": self.spn_fill_power, "fill_feed": self.spn_fill_feed,
            "perimeter": self.chk_perimeter,
            "contour": self.chk_contour, "contour_power": self.spn_contour_power,
            "contour_feed": self.spn_contour_feed, "contour_width": self.spn_contour_width,
            "fill_style": self.combo_fill_style, "contour_style": self.combo_contour_style,
            "dash_len": self.spn_dash_len, "gap_len": self.spn_gap_len,
            "dot_spacing": self.spn_dot_spacing, "dot_dwell_ms": self.spn_dot_dwell,
            "wave_period": self.spn_wave_period, "fill_wave_width": self.spn_fill_wave_width,
            "fluence_on": self._fluence["chk"], "ref_power": self._fluence["ref_power"],
            "ref_feed": self._fluence["ref_feed"], "ref_spot": self._fluence["ref_spot"],
        }
        _restore_last_values("filled", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Gravure remplie (noir)")
        self.form.setWindowIcon(_icon("filled.svg"))

        self._populate_preset_combo()
        self._shade_picker["reload"]()
        _update_defocus_preview()
        _update_style_preview()

    # --- Préréglages nommés (catégorie "filled") ---
    @staticmethod
    def _preset_summary(values):
        lines = ["Remplissage : espace {:g} mm @ {:g} deg, S{:g} F{:g}".format(
            values.get("spacing", 0), values.get("angle", 0),
            values.get("fill_power", 0), values.get("fill_feed", 0))]
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
            "perimeter": self.chk_perimeter.isChecked(),
            "contour": self.chk_contour.isChecked(),
            "contour_power": self.spn_contour_power.value(),
            "contour_feed": self.spn_contour_feed.value(),
            "contour_width": self.spn_contour_width.value(),
            "fill_style": self.combo_fill_style.currentIndex(),
            "contour_style": self.combo_contour_style.currentIndex(),
            "dash_len": self.spn_dash_len.value(),
            "gap_len": self.spn_gap_len.value(),
            "dot_spacing": self.spn_dot_spacing.value(),
            "dot_dwell_ms": self.spn_dot_dwell.value(),
            "wave_period": self.spn_wave_period.value(),
            "fill_wave_width": self.spn_fill_wave_width.value(),
            "fluence_on": self._fluence["chk"].isChecked(),
            "ref_power": self._fluence["ref_power"].value(),
            "ref_feed": self._fluence["ref_feed"].value(),
            "ref_spot": self._fluence["ref_spot"].value(),
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
        self.chk_perimeter.setChecked(v.get("perimeter", self.chk_perimeter.isChecked()))
        self.chk_contour.setChecked(v.get("contour", self.chk_contour.isChecked()))
        self.spn_contour_power.setValue(v.get("contour_power", self.spn_contour_power.value()))
        self.spn_contour_feed.setValue(v.get("contour_feed", self.spn_contour_feed.value()))
        self.spn_contour_width.setValue(v.get("contour_width", self.spn_contour_width.value()))
        self.combo_fill_style.setCurrentIndex(v.get("fill_style", self.combo_fill_style.currentIndex()))
        self.combo_contour_style.setCurrentIndex(v.get("contour_style", self.combo_contour_style.currentIndex()))
        self.spn_dash_len.setValue(v.get("dash_len", self.spn_dash_len.value()))
        self.spn_gap_len.setValue(v.get("gap_len", self.spn_gap_len.value()))
        self.spn_dot_spacing.setValue(v.get("dot_spacing", self.spn_dot_spacing.value()))
        self.spn_dot_dwell.setValue(v.get("dot_dwell_ms", self.spn_dot_dwell.value()))
        self.spn_wave_period.setValue(v.get("wave_period", self.spn_wave_period.value()))
        self.spn_fill_wave_width.setValue(v.get("fill_wave_width", self.spn_fill_wave_width.value()))
        self._fluence["chk"].setChecked(v.get("fluence_on", self._fluence["chk"].isChecked()))
        self._fluence["ref_power"].setValue(v.get("ref_power", self._fluence["ref_power"].value()))
        self._fluence["ref_feed"].setValue(v.get("ref_feed", self._fluence["ref_feed"].value()))
        self._fluence["ref_spot"].setValue(v.get("ref_spot", self._fluence["ref_spot"].value()))
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
        (cible = largeur exacte, pas de recouvrement). Point au foyer :
        calibration des Préférences."""
        off = core.defocus_for_fill_spacing(
            self.spn_contour_width.value(), core.SPOT_FOCUS_MM, half_angle, overlap=1.0)
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
        half_angle = core.calibrated_half_angle()
        defocus = core.defocus_for_fill_spacing(
            self.spn_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
        if defocus is None:
            if not silent:
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur",
                    "Calibration du point invalide dans les Préférences : le\n"
                    "point mesuré au défocus de test doit être strictement\n"
                    "plus large que celui mesuré au foyer (à mesurer avec la\n"
                    "Bande de calibration défocus, puis à saisir dans les\n"
                    "Préférences, icône engrenage).")
            return None, None, None, None
        spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
        fill_edges, contour_edges = core.build_filled_engraving_edges(
            faces, self.spn_spacing.value(), self.spn_angle.value(), fill_inset=spot / 2.0,
            add_perimeter=self.chk_perimeter.isChecked())
        return fill_edges, contour_edges, defocus, self._contour_offset(half_angle)

    def _gen_kwargs(self, defocus, contour_z_offset):
        style_map = {0: "plein", 1: "tirets", 2: "pointille", 3: "vague"}
        fill_style = style_map.get(self.combo_fill_style.currentIndex(), "plein")
        contour_style = style_map.get(self.combo_contour_style.currentIndex(), "plein")
        common = {
            "dash_len": self.spn_dash_len.value(),
            "gap_len": self.spn_gap_len.value(),
            "dot_spacing": self.spn_dot_spacing.value(),
            "dot_dwell_s": self.spn_dot_dwell.value() / 1000.0,
            "wave_period": self.spn_wave_period.value(),
        }
        fill_params = dict(common)
        contour_params = dict(common)
        half_angle = core.calibrated_half_angle()
        if fill_style == "vague":
            amp = core.defocus_for_fill_spacing(
                self.spn_fill_wave_width.value(), core.SPOT_FOCUS_MM,
                half_angle, overlap=1.0)
            fill_params["wave_amplitude"] = amp or 0.0
        if contour_style == "vague":
            # « Épaisseur trait contour » = largeur max de la vague.
            contour_params["wave_amplitude"] = self._contour_offset(half_angle)
        # Compensation puissance/défocus (option 2) : si cochée, la
        # puissance de remplissage est calculée pour égaler la fluence de
        # référence au point élargi réel du remplissage.
        fill_power = self.spn_fill_power.value()
        fill_spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
        _, _, p_eff = _fluence_advice(
            fill_spot, fill_power, self.spn_fill_feed.value(), self._fluence)
        if p_eff is not None:
            fill_power = p_eff
        return {
            "z_focus": core.Z_WORK_MM,
            "defocus": defocus,
            "fill_power": fill_power,
            "fill_feed": self.spn_fill_feed.value(),
            "draw_contour": self.chk_contour.isChecked(),
            "contour_power": self.spn_contour_power.value(),
            "contour_feed": self.spn_contour_feed.value(),
            "contour_z_offset": contour_z_offset,
            "marge_survol": core.TRANSIT_MARGIN_MM,
            "fill_style": fill_style,
            "contour_style": contour_style,
            "fill_style_params": fill_params,
            "contour_style_params": contour_params,
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
        _save_last_values("filled", self._last_fields)
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
    """Le panneau s'ouvre SANS sélection préalable : on sélectionne les
    objets dans la vue 3D pendant qu'il est ouvert (un panneau de tâches
    FreeCAD est non-bloquant), un état affiché en direct dit ce qui est
    reconnu, puis OK projette. Plus besoin de tout sélectionner AVANT de
    cliquer sur l'icône (ce qui était contre-intuitif : l'icône était
    grisée tant que rien n'était sélectionné, puis se plaignait qu'il
    fallait sélectionner)."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        _panel_header(form, "project.svg", "Projection sur surface 3D")
        lbl = _WrapLabel(
            "Sélectionne maintenant, dans la vue 3D (le panneau reste\n"
            "ouvert) : un ou plusieurs motifs 2D (ShapeString, hachures...)\n"
            "ET la surface 3D de référence (sphère, vague...). Ils seront\n"
            "tous projetés ensemble sur cette surface en un seul objet.\n"
            "L'état ci-dessous se met à jour au fil de ta sélection ; clique\n"
            "sur OK quand il est vert.")
        form.addRow(lbl)
        _diagram(form, "diag_projection.svg")

        self.lbl_status = _WrapLabel()
        form.addRow(self.lbl_status)

        # Un panneau de tâches FreeCAD ne reçoit pas d'événement de
        # sélection : on interroge la sélection courante à intervalle
        # régulier pour rafraîchir l'état (léger, juste une classification).
        self._timer = QtCore.QTimer()
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Projection sur surface 3D")
        self.form.setWindowIcon(_icon("project.svg"))
        self._refresh_status()

    def _classify(self):
        """(motifs 2D, surface 3D, message) de la sélection courante."""
        selection = Gui.Selection.getSelectionEx()
        if not selection:
            return [], None, "Aucun objet sélectionné."
        motifs, reference = core.split_projection_selection(selection)
        if not motifs or reference is None:
            return None, None, (
                "Sélection ambiguë : il faut EXACTEMENT une surface 3D\n"
                "(un seul objet d'épaisseur significative) et au moins un\n"
                "motif 2D plat.")
        return motifs, reference, None

    def _refresh_status(self):
        motifs, reference, err = self._classify()
        if err:
            self.lbl_status.setText("⏳ " + err)
            self.lbl_status.setStyleSheet("color: #b0740a;")
            return
        self.lbl_status.setText(
            "✅ {} motif(s) 2D + surface « {} » -- prêt à projeter.".format(
                len(motifs), reference.Label))
        self.lbl_status.setStyleSheet("color: #2e7d32; font-weight: bold;")

    def accept(self):
        selection = Gui.Selection.getSelectionEx()
        obj, err = core.run_projection(selection)
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))
        self._timer.stop()
        return True

    def reject(self):
        self._timer.stop()
        return True


# ==========================================================================
# MODE : CALIBRATION KERF
# ==========================================================================
class TaskPanelKerf:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self._formlayout = form

        _panel_header(form, "kerf.svg", "Calibration kerf")
        _intro(form,
               "Deux tests, à découper ensuite en mode Découpe multi-passes : "
               "le CARRÉ pour MESURER le kerf, le TENON + MORTAISE pour VALIDER "
               "l'ajustement réel une fois le kerf connu.",
               "Ordre conseillé : 1) découpe le CARRÉ avec Compensation de kerf "
               "= 0, mesure la pièce, kerf = taille dessinée - taille mesurée ; "
               "2) reporte ce kerf en Compensation, puis découpe le TENON + "
               "MORTAISE : insère le tenon dans chaque mortaise et retiens le "
               "JEU (gravé sous chacune) qui donne l'ajustement voulu -- serré "
               "pour un collage, glissant pour du démontable.")

        self.combo_test = QtWidgets.QComboBox()
        self.combo_test.addItems(["Carré (mesure du kerf)",
                                  "Tenon + mortaise (ajustement)"])
        self.combo_test.setToolTip(
            "Carré : pour MESURER le kerf.\n"
            "Tenon + mortaise : pour VALIDER l'ajustement une fois le kerf connu.")
        form.addRow("Test :", self.combo_test)

        self.lbl_fit_diag = QtWidgets.QLabel()
        self.lbl_fit_diag.setAlignment(QtCore.Qt.AlignHCenter)
        try:
            _pm = _icon("diag_fit.svg").pixmap(260, 120)
            if not _pm.isNull():
                self.lbl_fit_diag.setPixmap(_pm)
        except Exception:
            pass
        form.addRow(self.lbl_fit_diag)

        # --- Carré (mesure du kerf) ---
        self.spn_size = QtWidgets.QDoubleSpinBox()
        self.spn_size.setRange(1.0, 200.0)
        self.spn_size.setValue(20.0)
        self.spn_size.setSuffix(" mm")
        self.spn_size.setToolTip(
            "Côté du carré généré (mm). Plus grand = mesure au pied à\n"
            "coulisse plus précise, mais consomme davantage de matière.")
        form.addRow("Taille du carré test :", self.spn_size)

        self.lbl_square = _WrapLabel(
            "Découpe-le en Découpe multi-passes avec Compensation de kerf = 0, "
            "puis mesure la pièce : kerf = taille dessinée - taille mesurée.")
        form.addRow(self.lbl_square)

        # --- Tenon + mortaise (ajustement) ---
        self.spn_tenon_w = QtWidgets.QDoubleSpinBox()
        self.spn_tenon_w.setRange(3.0, 200.0)
        self.spn_tenon_w.setValue(20.0)
        self.spn_tenon_w.setSuffix(" mm")
        self.spn_tenon_w.setToolTip("Largeur du tenon (la pièce mâle isolée).")
        form.addRow("Largeur du tenon :", self.spn_tenon_w)

        self.spn_tenon_h = QtWidgets.QDoubleSpinBox()
        self.spn_tenon_h.setRange(3.0, 200.0)
        self.spn_tenon_h.setValue(10.0)
        self.spn_tenon_h.setSuffix(" mm")
        self.spn_tenon_h.setToolTip("Hauteur du tenon (la pièce mâle isolée).")
        form.addRow("Hauteur du tenon :", self.spn_tenon_h)

        self.spn_nslots = QtWidgets.QSpinBox()
        self.spn_nslots.setRange(1, 12)
        self.spn_nslots.setValue(5)
        self.spn_nslots.setToolTip(
            "Nombre de mortaises (trous), chacune avec un jeu croissant.")
        form.addRow("Nombre de mortaises :", self.spn_nslots)

        self.spn_clr_start = QtWidgets.QDoubleSpinBox()
        self.spn_clr_start.setRange(0.0, 2.0)
        self.spn_clr_start.setDecimals(2)
        self.spn_clr_start.setSingleStep(0.05)
        self.spn_clr_start.setValue(0.0)
        self.spn_clr_start.setSuffix(" mm")
        self.spn_clr_start.setToolTip(
            "Jeu de la 1re mortaise = écart mortaise - tenon (réparti moitié\n"
            "de chaque côté). 0 = mortaise au même nominal que le tenon.")
        form.addRow("Jeu de départ :", self.spn_clr_start)

        self.spn_clr_step = QtWidgets.QDoubleSpinBox()
        self.spn_clr_step.setRange(0.01, 1.0)
        self.spn_clr_step.setDecimals(2)
        self.spn_clr_step.setSingleStep(0.05)
        self.spn_clr_step.setValue(0.1)
        self.spn_clr_step.setSuffix(" mm")
        self.spn_clr_step.setToolTip("Incrément de jeu entre deux mortaises.")
        form.addRow("Pas de jeu :", self.spn_clr_step)

        self.lbl_fit = _WrapLabel(
            "Deux objets : « decoupe » = les contours (tenon isolé + mortaises "
            "rangées par jeu croissant), à découper avec ta Compensation de "
            "kerf ; « gravure » = le jeu sous chaque mortaise et la cote sur le "
            "tenon, à MARQUER à faible puissance. Grave puis découpe (ou "
            "enchaîne les deux via Job combiné), insère le tenon dans chaque "
            "mortaise et retiens le jeu qui donne l'ajustement voulu -- serré "
            "pour un collage, glissant pour du démontable.")
        form.addRow(self.lbl_fit)

        self._square_rows = [self.spn_size, self.lbl_square]
        self._fit_rows = [self.lbl_fit_diag, self.spn_tenon_w, self.spn_tenon_h,
                          self.spn_nslots, self.spn_clr_start, self.spn_clr_step,
                          self.lbl_fit]
        self.combo_test.currentIndexChanged.connect(lambda _i: self._sync_mode())
        self._sync_mode()

        self._last_fields = {"test": self.combo_test, "size": self.spn_size,
                             "tenon_w": self.spn_tenon_w, "tenon_h": self.spn_tenon_h,
                             "nslots": self.spn_nslots, "clr_start": self.spn_clr_start,
                             "clr_step": self.spn_clr_step}
        self._presets = _PresetController(form, inner, "kerf", lambda: self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Calibration kerf")
        self.form.setWindowIcon(_icon("kerf.svg"))

    def _sync_mode(self):
        fit = self.combo_test.currentIndex() == 1
        for w in self._square_rows:
            _set_row_visible(self._formlayout, w, not fit)
        for w in self._fit_rows:
            _set_row_visible(self._formlayout, w, fit)

    def accept(self):
        if self.combo_test.currentIndex() == 1:
            objs, err = core.create_fit_test_pattern(
                self.spn_tenon_w.value(), self.spn_tenon_h.value(),
                self.spn_nslots.value(), self.spn_clr_start.value(),
                self.spn_clr_step.value())
            if err:
                QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
                return False
            noms = ", ".join(o.Name for o in objs)
            FreeCAD.Console.PrintMessage(
                "Succès : {} créé(s). Graver « ...gravure » (jeux + cote du "
                "tenon, faible puissance) et découper « ...decoupe » avec ta "
                "Compensation de kerf.\n".format(noms))
            return True
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

        _panel_header(form, "defocus.svg", "Bande de calibration défocus")
        _intro(form,
               "Grave une rangée de traits, chacun à une hauteur de bec "
               "croissante (étiquetée) : le trait LE PLUS FIN te donne le "
               "foyer, les traits larges la divergence du faisceau. Zéro Z "
               "sur la surface, aucune sélection requise.",
               "À mesurer au pied à coulisse : (1) la hauteur du trait le plus "
               "fin = ton Z de foyer et sa largeur = « point au foyer » ; "
               "(2) un trait bien plus large : sa hauteur moins celle du foyer "
               "= « défocus de test », sa largeur = « point au défocus de "
               "test ». REPORTE ces trois mesures dans les Préférences (icône "
               "engrenage, section Calibration du point) : elles servent à "
               "tous les modes (remplissage noir, styles vague/défocus...). "
               "La rampe de puissance optionnelle garde les traits très "
               "défocalisés visibles. Astuce : mets « Nombre de bandes » > 1 "
               "pour graver plusieurs bandes côte à côte, une par vitesse "
               "(de la 1re à la dernière) -- tous tes niveaux de gris/noir en "
               "un seul job, chaque bande étiquetée de sa vitesse.")
        _diagram(form, "diag_defocus.svg")

        self._presets = _PresetController(form, inner, "defocus_calib", lambda: self._last_fields)

        _section(form, "Balayage en hauteur (Z)", "sect_zheight.svg")
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

        _section(form, "Traits (puissance / vitesse)", "sect_power.svg")
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
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(300)
        self.spn_power.setToolTip(
            "Puissance (S) du 1er trait (le plus bas, près du foyer).\n"
            "Modérée : assez pour marquer, pas trop pour que la brûlure ne\n"
            "s'élargisse pas au-delà du point (ce qui fausserait la mesure).")
        form.addRow("Puissance 1er trait (bas) :", self.spn_power)

        self.spn_power_end = QtWidgets.QDoubleSpinBox()
        self.spn_power_end.setRange(0, core.S_MAX)
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
        self.spn_feed.setToolTip(
            "Vitesse d'avance des traits. Si plusieurs bandes (ci-dessous),\n"
            "c'est la vitesse de la PREMIÈRE bande.")
        form.addRow("Vitesse des traits :", self.spn_feed)

        _section(form, "Plusieurs vitesses (bandes)", "sect_options.svg")
        self.spn_nbands = QtWidgets.QSpinBox()
        self.spn_nbands.setRange(1, 20)
        self.spn_nbands.setValue(1)
        self.spn_nbands.setToolTip(
            "Nombre de bandes gravées CÔTE À CÔTE, une par vitesse. 1 = une\n"
            "seule bande (la vitesse ci-dessus). Plus = balaie de la 1re\n"
            "vitesse (ci-dessus) à la dernière (ci-dessous) : on obtient tous\n"
            "les niveaux de gris/noir en un seul job, sans tout refaire.")
        form.addRow("Nombre de bandes :", self.spn_nbands)

        self.spn_feed_end = QtWidgets.QDoubleSpinBox()
        self.spn_feed_end.setRange(1, 20000)
        self.spn_feed_end.setValue(400)
        self.spn_feed_end.setSuffix(" mm/min")
        self.spn_feed_end.setToolTip(
            "Vitesse de la DERNIÈRE bande. Les bandes intermédiaires ont une\n"
            "vitesse interpolée entre la 1re (ci-dessus) et celle-ci.")
        form.addRow("Vitesse dernière bande :", self.spn_feed_end)

        self.spn_band_gap = QtWidgets.QDoubleSpinBox()
        self.spn_band_gap.setRange(0.0, 50.0)
        self.spn_band_gap.setValue(5.0)
        self.spn_band_gap.setSuffix(" mm")
        self.spn_band_gap.setToolTip(
            "Espace horizontal libre entre deux bandes (étiquettes comprises).")
        form.addRow("Espace entre bandes :", self.spn_band_gap)

        def _sync_bands():
            multi = self.spn_nbands.value() > 1
            _set_row_visible(form, self.spn_feed_end, multi)
            _set_row_visible(form, self.spn_band_gap, multi)
            # Rend explicite que « Vitesse des traits » = vitesse de la 1re
            # bande quand il y en a plusieurs (à régler avec la dernière).
            lbl = form.labelForField(self.spn_feed)
            if lbl is not None:
                lbl.setText("Vitesse 1re bande :" if multi else "Vitesse des traits :")
        self.spn_nbands.valueChanged.connect(
            lambda _v: (_sync_bands(), self._update_duration_preview()))
        _sync_bands()

        _section(form, "Étiquettes", "sect_labels.svg")
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
        self.spn_label_power.setRange(0, core.S_MAX)
        self.spn_label_power.setValue(300)
        self.spn_label_power.setToolTip("Puissance (S) des étiquettes.")
        form.addRow("Puissance étiquettes :", self.spn_label_power)

        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setValue(1500)
        self.spn_label_feed.setSuffix(" mm/min")
        self.spn_label_feed.setToolTip("Vitesse d'avance des étiquettes.")
        form.addRow("Vitesse étiquettes :", self.spn_label_feed)

        self.spn_label_z = QtWidgets.QDoubleSpinBox()
        self.spn_label_z.setRange(-50, 200)
        self.spn_label_z.setDecimals(2)
        self.spn_label_z.setValue(core.Z_WORK_MM)
        self.spn_label_z.setSuffix(" mm")
        self.spn_label_z.setToolTip(
            "Hauteur (Z) de gravure des étiquettes -- FIXE, indépendante du\n"
            "défocus des traits, pour qu'elles restent nettes et lisibles.\n"
            "Défaut : la focale (Z de travail des Préférences).")
        form.addRow("Hauteur (Z) étiquettes :", self.spn_label_z)

        def _sync_label_fields():
            on = self.chk_labels.isChecked() or self.chk_power_labels.isChecked()
            self.spn_label_power.setEnabled(on)
            self.spn_label_feed.setEnabled(on)
            self.spn_label_z.setEnabled(on)
        self.chk_labels.toggled.connect(lambda _v: _sync_label_fields())
        self.chk_power_labels.toggled.connect(lambda _v: _sync_label_fields())

        self.lbl_range = _WrapLabel("")
        form.addRow(self.lbl_range)

        def _update_range():
            zmax = self.spn_zstart.value() + (self.spn_nmarks.value() - 1) * self.spn_zstep.value()
            self.lbl_range.setText("Plage balayée : Z {:.1f} à {:.1f} mm.".format(
                self.spn_zstart.value(), zmax))
        self.spn_zstart.valueChanged.connect(lambda _v: _update_range())
        self.spn_zstep.valueChanged.connect(lambda _v: _update_range())
        self.spn_nmarks.valueChanged.connect(lambda _v: _update_range())

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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

        self._last_fields = {
            "zstart": self.spn_zstart, "zstep": self.spn_zstep,
            "nmarks": self.spn_nmarks, "length": self.spn_length,
            "rowgap": self.spn_rowgap, "power": self.spn_power,
            "power_end": self.spn_power_end, "feed": self.spn_feed,
            "nbands": self.spn_nbands, "feed_end": self.spn_feed_end,
            "band_gap": self.spn_band_gap,
            "labels": self.chk_labels, "power_labels": self.chk_power_labels,
            "label_power": self.spn_label_power, "label_feed": self.spn_label_feed,
            "label_z": self.spn_label_z,
        }
        _restore_last_values("defocus_calib", self._last_fields)
        # Un préréglage chargé rafraîchit la plage affichée et la durée.
        self._presets.on_loaded = lambda: (_update_range(), self._update_duration_preview())

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
            "n_bands": self.spn_nbands.value(),
            "feed_end": self.spn_feed_end.value(),
            "band_gap": self.spn_band_gap.value(),
            "draw_labels": self.chk_labels.isChecked(),
            "draw_power_labels": self.chk_power_labels.isChecked(),
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
            "label_z": self.spn_label_z.value(),
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
        _save_last_values("defocus_calib", self._last_fields)
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
# MODE : TEST RAMPE PUISSANCE / VITESSE (LIGNES)
# ==========================================================================
class TaskPanelPowerRamp:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "powerramp.svg", "Test rampe puissance / vitesse (lignes)")
        _intro(form,
               "Grave de longues lignes, UNE PAR VITESSE, avec la puissance "
               "qui MONTE le long de chaque ligne : on repère d'un coup où le "
               "trait apparaît et où il sature, à chaque vitesse. Zéro Z sur "
               "la surface, aucune sélection requise.",
               "Complément continu de la Grille de test (cellules discrètes). "
               "La règle graduée sous la première ligne donne la puissance "
               "sous chaque point du trait. Option rampe Z : la hauteur du "
               "bec monte aussi le long de la ligne (défocus progressif). "
               "Astuce laser S/PWM : si le trait se pointille à haute "
               "vitesse, baisse le nombre de paliers (chaque changement de "
               "puissance fait micro-branler la machine).")
        _diagram(form, "diag_ramp.svg")

        self._presets = _PresetController(form, inner, "powerramp", lambda: self._last_fields)

        _section(form, "Lignes (vitesses)", "sect_power.svg")
        self.spn_length = QtWidgets.QDoubleSpinBox()
        self.spn_length.setRange(10.0, 500.0)
        self.spn_length.setValue(80.0)
        self.spn_length.setSuffix(" mm")
        self.spn_length.setToolTip(
            "Longueur de chaque ligne : toute la plage de puissance est\n"
            "étalée dessus, donc plus long = transition plus lisible et plus\n"
            "facile à repérer où le trait apparaît.")
        form.addRow("Longueur des lignes :", self.spn_length)

        self.spn_nlines = QtWidgets.QSpinBox()
        self.spn_nlines.setRange(1, 40)
        self.spn_nlines.setValue(6)
        self.spn_nlines.setToolTip("Nombre de lignes = nombre de vitesses testées.")
        form.addRow("Nombre de vitesses :", self.spn_nlines)

        self.spn_gap = QtWidgets.QDoubleSpinBox()
        self.spn_gap.setRange(1.0, 50.0)
        self.spn_gap.setValue(8.0)
        self.spn_gap.setSuffix(" mm")
        self.spn_gap.setToolTip("Espacement vertical entre deux lignes.")
        form.addRow("Espacement des lignes :", self.spn_gap)

        self.spn_feed_min = QtWidgets.QDoubleSpinBox()
        self.spn_feed_min.setRange(1, 20000)
        self.spn_feed_min.setValue(500)
        self.spn_feed_min.setSuffix(" mm/min")
        self.spn_feed_min.setToolTip("Vitesse de la 1re ligne (en bas) -- la plus lente.")
        form.addRow("Vitesse min :", self.spn_feed_min)

        self.spn_feed_max = QtWidgets.QDoubleSpinBox()
        self.spn_feed_max.setRange(1, 20000)
        self.spn_feed_max.setValue(3000)
        self.spn_feed_max.setSuffix(" mm/min")
        self.spn_feed_max.setToolTip("Vitesse de la dernière ligne (en haut) -- la plus rapide.")
        form.addRow("Vitesse max :", self.spn_feed_max)

        _section(form, "Rampe de puissance", "sect_power.svg")
        self.spn_power_min = QtWidgets.QDoubleSpinBox()
        self.spn_power_min.setRange(0, core.S_MAX)
        self.spn_power_min.setValue(0)
        self.spn_power_min.setToolTip(
            "Puissance (S) au DÉBUT de chaque ligne (gauche). 0 = la ligne\n"
            "commence éteinte et monte -- pratique pour voir exactement où\n"
            "le trait apparaît.")
        form.addRow("Puissance min (gauche) :", self.spn_power_min)

        self.spn_power_max = QtWidgets.QDoubleSpinBox()
        self.spn_power_max.setRange(0, core.S_MAX)
        self.spn_power_max.setValue(800)
        self.spn_power_max.setToolTip("Puissance (S) à la FIN de chaque ligne (droite).")
        form.addRow("Puissance max (droite) :", self.spn_power_max)

        self.spn_steps = QtWidgets.QSpinBox()
        self.spn_steps.setRange(4, 400)
        self.spn_steps.setValue(20)
        self.spn_steps.setToolTip(
            "Nombre de paliers approximant la rampe (un changement de S par\n"
            "palier). Beaucoup de paliers = rampe plus douce, MAIS sur un\n"
            "laser piloté par la vitesse de broche (S/PWM), chaque\n"
            "changement de S est une frontière où la machine fait un\n"
            "micro-arrêt : à haute vitesse, ces frontières hachent le trait\n"
            "en pointillés. À l'intérieur d'un palier (S constant), le trait\n"
            "reste continu. Donc si le trait se pointille trop vite, BAISSE\n"
            "le nombre de paliers (ex. 8-15) : chaque palier devient un\n"
            "segment plus long tracé en continu (rampe plus « en marches »\n"
            "mais trait franc), et tu lis quand même à quelle puissance/\n"
            "vitesse ça marque le mieux.")
        form.addRow("Paliers de la rampe :", self.spn_steps)

        _section(form, "Rampe de hauteur (Z)", "sect_zheight.svg")
        self.chk_zramp = QtWidgets.QCheckBox("Monter en Z le long de la ligne (défocus progressif)")
        self.chk_zramp.setToolTip(
            "Coché : la hauteur du bec monte AUSSI le long de chaque ligne,\n"
            "de la focale (gauche) à la hauteur de fin (droite), en même\n"
            "temps que la puissance -- pour tester à chaque vitesse l'effet\n"
            "combiné puissance croissante + défocus croissant. Décoché :\n"
            "hauteur constante au foyer (rampe de puissance seule).")
        form.addRow(self.chk_zramp)

        self.lbl_zstart = _WrapLabel(
            "Z de début (gauche) = focale des Préférences : {:.2f} mm.".format(core.Z_WORK_MM))
        form.addRow(self.lbl_zstart)

        self.spn_z_end = QtWidgets.QDoubleSpinBox()
        self.spn_z_end.setRange(-50.0, 200.0)
        self.spn_z_end.setDecimals(2)
        self.spn_z_end.setValue(core.Z_WORK_MM + 6.0)
        self.spn_z_end.setSuffix(" mm")
        self.spn_z_end.setToolTip(
            "Hauteur du bec à la FIN de chaque ligne (droite). Le Z monte\n"
            "linéairement de la focale (gauche) à cette valeur (droite).\n"
            "Plus haut que la focale = défocus croissant (point élargi).")
        form.addRow("Z de fin (droite) :", self.spn_z_end)

        self.chk_zramp.toggled.connect(self.spn_z_end.setEnabled)
        self.spn_z_end.setEnabled(False)

        _section(form, "Étiquettes", "sect_labels.svg")
        self.chk_labels = QtWidgets.QCheckBox("Graver les étiquettes (vitesse + bornes de puissance)")
        self.chk_labels.setChecked(True)
        self.chk_labels.setToolTip(
            "Grave la vitesse (F) à gauche de chaque ligne, et les bornes\n"
            "de puissance (Smin à gauche, Smax à droite) sous la 1re ligne.")
        form.addRow(self.chk_labels)

        self.spn_label_power = QtWidgets.QDoubleSpinBox()
        self.spn_label_power.setRange(0, core.S_MAX)
        self.spn_label_power.setValue(300)
        self.spn_label_power.setToolTip(
            "Puissance (S) qui GRAVE les étiquettes elles-mêmes (les F à\n"
            "gauche et les chiffres de puissance). FIXE, séparée de la rampe\n"
            "testée, pour que les étiquettes restent lisibles même quand tu\n"
            "testes des puissances très faibles (une étiquette à S0 serait\n"
            "invisible). Effet visible sur la PIÈCE gravée, pas dans\n"
            "l'aperçu de trajet 3D (qui dessine tout en rouge, sans tenir\n"
            "compte de la puissance).")
        form.addRow("Puissance étiquettes :", self.spn_label_power)

        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setValue(1500)
        self.spn_label_feed.setSuffix(" mm/min")
        self.spn_label_feed.setToolTip(
            "Vitesse d'avance qui GRAVE les étiquettes. FIXE, séparée de la\n"
            "rampe testée. N'apparaît pas dans l'aperçu de trajet 3D, mais\n"
            "change le rendu sur la pièce ET la durée estimée (plus lent =\n"
            "étiquettes plus marquées mais job plus long).")
        form.addRow("Vitesse étiquettes :", self.spn_label_feed)

        self.chk_labels.toggled.connect(self.spn_label_power.setEnabled)
        self.chk_labels.toggled.connect(self.spn_label_feed.setEnabled)

        _section(form, "G-code & aperçus", "sect_gcode.svg")
        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_pr", ""))
        self.txt_post.setPlainText(cfg.get("post_pr", ""))

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

        self._last_fields = {
            "length": self.spn_length, "nlines": self.spn_nlines, "gap": self.spn_gap,
            "feed_min": self.spn_feed_min, "feed_max": self.spn_feed_max,
            "power_min": self.spn_power_min, "power_max": self.spn_power_max,
            "steps": self.spn_steps, "zramp": self.chk_zramp, "z_end": self.spn_z_end,
            "labels": self.chk_labels,
            "label_power": self.spn_label_power, "label_feed": self.spn_label_feed,
        }
        _restore_last_values("powerramp", self._last_fields)
        self._presets.on_loaded = self._update_duration_preview

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Test rampe puissance / vitesse (lignes)")
        self.form.setWindowIcon(_icon("powerramp.svg"))

        self._update_duration_preview()

    def _gen_kwargs(self):
        return {
            "line_length": self.spn_length.value(),
            "n_lines": self.spn_nlines.value(),
            "feed_min": self.spn_feed_min.value(),
            "feed_max": self.spn_feed_max.value(),
            "power_min": self.spn_power_min.value(),
            "power_max": self.spn_power_max.value(),
            "z_work": core.Z_WORK_MM,
            "z_end": self.spn_z_end.value() if self.chk_zramp.isChecked() else None,
            "line_gap": self.spn_gap.value(),
            "n_steps": self.spn_steps.value(),
            "draw_labels": self.chk_labels.isChecked(),
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
        }

    def _valid_ranges(self, warn=False):
        if self.spn_power_max.value() < self.spn_power_min.value() or self.spn_feed_max.value() < self.spn_feed_min.value():
            if warn:
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur", "Vérifie les plages (max >= min) puissance et vitesse.")
            return False
        return True

    def _update_duration_preview(self):
        if not self._valid_ranges():
            self.lbl_duration.setText("Durée estimée : -- (vérifie les plages min/max)")
            return
        gcode = core.generate_gcode_power_ramp_lines(quiet=True, **self._gen_kwargs())
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        if not self._valid_ranges(warn=True):
            return
        gcode = core.generate_gcode_power_ramp_lines(frame_only=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_rampe.ngc")

    def _on_toolpath_preview(self):
        if not self._valid_ranges(warn=True):
            return
        gcode = core.generate_gcode_power_ramp_lines(quiet=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        if not self._valid_ranges(warn=True):
            return False
        _save_last_values("powerramp", self._last_fields)
        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_power_ramp_lines(
            pre_gcode=pre_text, post_gcode=post_text, **self._gen_kwargs())

        cfg = core.load_config()
        cfg["pre_pr"] = pre_text
        cfg["post_pr"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/test_rampe_puissance.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : TEST DES OFFSETS X/Y DU LASER
# ==========================================================================
class TaskPanelOffsetTest:
    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "offset_test.svg", "Test des offsets X/Y du laser")
        _intro(form,
               "Job MIXTE fraise + laser : fraise une croix sur X0 Y0, puis "
               "grave une croix laser au même X0 Y0 programmé. L'écart mesuré "
               "entre les deux croix = l'erreur d'offsets X/Y du T{} dans "
               "tool.tbl. Lunettes laser obligatoires.".format(int(core.LASER_TOOL)),
               "Correction : X_nouveau = X_actuel - dX (idem Y), avec dX = X "
               "laser - X fraisé (écarts signés, sens machine). AVANT de "
               "lancer : chute de bois sur le martyre (prévoir LARGE si un "
               "signe d'offset est faux), fraise à graver montée à la main, "
               "zéro X/Y à l'oeil au centre de la chute. Monter la glissière "
               "laser pendant la pause du 2e changement d'outil. Aucune "
               "sélection requise.")
        _diagram(form, "diag_offset.svg")

        self._presets = _PresetController(form, inner, "offset_test", lambda: self._last_fields)

        _section(form, "Croix (géométrie)", "sect_options.svg")
        self.spn_half = QtWidgets.QDoubleSpinBox()
        self.spn_half.setRange(2.0, 100.0)
        self.spn_half.setValue(10.0)
        self.spn_half.setSuffix(" mm")
        self.spn_half.setToolTip(
            "Demi-longueur des branches de chaque croix (10 mm = croix de\n"
            "20 x 20 mm). Assez grand pour poser le pied à coulisse.")
        form.addRow("Demi-longueur des branches :", self.spn_half)

        self.spn_surface_z = QtWidgets.QDoubleSpinBox()
        self.spn_surface_z.setRange(-100.0, 200.0)
        self.spn_surface_z.setDecimals(2)
        self.spn_surface_z.setValue(0.0)
        self.spn_surface_z.setSuffix(" mm")
        self.spn_surface_z.setToolTip(
            "Z du dessus de la chute dans le WCS courant : l'épaisseur de\n"
            "la chute (pied à coulisse) si le zéro Z est fait sur le\n"
            "martyre, 0 si le zéro Z est fait sur la chute elle-même.")
        form.addRow("Z du dessus de la chute :", self.spn_surface_z)

        _section(form, "Croix fraisée", "sect_contour.svg")
        self.spn_mill_tool = QtWidgets.QSpinBox()
        self.spn_mill_tool.setRange(1, 99)
        self.spn_mill_tool.setValue(2)
        self.spn_mill_tool.setToolTip(
            "Numéro (tool.tbl) de la fraise à graver/fraise fine montée.\n"
            "Le job fait T<n> M6 (palpage auto) -- pas T{}, réservé au laser.".format(int(core.LASER_TOOL)))
        form.addRow("Numéro d'outil fraise :", self.spn_mill_tool)

        self.spn_rpm = QtWidgets.QDoubleSpinBox()
        self.spn_rpm.setRange(1000, 30000)
        self.spn_rpm.setDecimals(0)
        self.spn_rpm.setValue(18000)
        self.spn_rpm.setSuffix(" tr/min")
        self.spn_rpm.setToolTip("Vitesse de la broche VFD pour la croix fraisée.")
        form.addRow("Vitesse broche :", self.spn_rpm)

        self.spn_mill_feed = QtWidgets.QDoubleSpinBox()
        self.spn_mill_feed.setRange(10, 5000)
        self.spn_mill_feed.setValue(600)
        self.spn_mill_feed.setSuffix(" mm/min")
        self.spn_mill_feed.setToolTip(
            "Avance de fraisage des branches (la plongée se fait à la\n"
            "moitié de cette avance).")
        form.addRow("Avance de fraisage :", self.spn_mill_feed)

        self.spn_depth = QtWidgets.QDoubleSpinBox()
        self.spn_depth.setRange(0.05, 5.0)
        self.spn_depth.setDecimals(2)
        self.spn_depth.setSingleStep(0.1)
        self.spn_depth.setValue(0.4)
        self.spn_depth.setSuffix(" mm")
        self.spn_depth.setToolTip(
            "Profondeur de la croix sous la surface de la chute. Juste\n"
            "assez pour un trait net et mesurable.")
        form.addRow("Profondeur de gravure :", self.spn_depth)

        _section(form, "Croix laser", "sect_focus.svg")
        self.spn_zfocus = QtWidgets.QDoubleSpinBox()
        self.spn_zfocus.setRange(0.0, 100.0)
        self.spn_zfocus.setDecimals(2)
        self.spn_zfocus.setValue(core.Z_WORK_MM)
        self.spn_zfocus.setSuffix(" mm")
        self.spn_zfocus.setToolTip(
            "Hauteur de focale du nez laser au-dessus de la surface\n"
            "(mesurée avec la bande de calibration défocus) : un trait au\n"
            "foyer est fin, donc facile à pointer au pied à coulisse.")
        form.addRow("Focale laser :", self.spn_zfocus)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(300)
        self.spn_power.setToolTip(
            "Puissance (S, 0-{:g}) de la croix laser. Juste de quoi marquer\n".format(core.S_MAX) +
            "net : une brûlure trop large fausserait le pointage.")
        form.addRow("Puissance laser :", self.spn_power)

        self.spn_laser_feed = QtWidgets.QDoubleSpinBox()
        self.spn_laser_feed.setRange(1, 20000)
        self.spn_laser_feed.setValue(1000)
        self.spn_laser_feed.setSuffix(" mm/min")
        self.spn_laser_feed.setToolTip("Vitesse de gravure de la croix laser.")
        form.addRow("Vitesse laser :", self.spn_laser_feed)

        _section(form, "G-code & aperçus", "sect_gcode.svg")
        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_ot", ""))
        self.txt_post.setPlainText(cfg.get("post_ot", ""))

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Hors changements d'outil et palpages (durée machine réelle\n"
            "nettement plus longue).")

        self.btn_toolpath_preview = QtWidgets.QPushButton("Aperçu du trajet (vue 3D)")
        self.btn_toolpath_preview.setToolTip(
            "Trace les deux croix dans la vue 3D (superposées par\n"
            "construction : c'est la machine qui révèle l'écart réel).")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        form.addRow(self.btn_toolpath_preview)

        self._last_fields = {
            "half": self.spn_half, "surface_z": self.spn_surface_z,
            "mill_tool": self.spn_mill_tool, "rpm": self.spn_rpm,
            "mill_feed": self.spn_mill_feed, "depth": self.spn_depth,
            "zfocus": self.spn_zfocus, "power": self.spn_power,
            "laser_feed": self.spn_laser_feed,
        }
        _restore_last_values("offset_test", self._last_fields)
        self._presets.on_loaded = self._update_duration_preview

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Test des offsets X/Y du laser")
        self.form.setWindowIcon(_icon("offset_test.svg"))

        self._update_duration_preview()

    def _gen_kwargs(self):
        return {
            "mill_tool": self.spn_mill_tool.value(),
            "mill_rpm": self.spn_rpm.value(),
            "mill_feed": self.spn_mill_feed.value(),
            "mill_depth": self.spn_depth.value(),
            "half_length": self.spn_half.value(),
            "surface_z": self.spn_surface_z.value(),
            "z_focus": self.spn_zfocus.value(),
            "laser_power": self.spn_power.value(),
            "laser_feed": self.spn_laser_feed.value(),
        }

    def _update_duration_preview(self):
        gcode = core.generate_gcode_offset_test(quiet=True, **self._gen_kwargs())
        if not gcode:
            self.lbl_duration.setText("Durée estimée : --")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText(
            "Durée estimée : {} (hors changements d'outil)".format(core.format_duration(seconds)))

    def _on_toolpath_preview(self):
        gcode = core.generate_gcode_offset_test(quiet=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        rapid, mark = core.parse_gcode_toolpath(gcode)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def accept(self):
        _save_last_values("offset_test", self._last_fields)
        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_offset_test(
            pre_gcode=pre_text, post_gcode=post_text, **self._gen_kwargs())

        cfg = core.load_config()
        cfg["pre_ot"] = pre_text
        cfg["post_ot"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/test_offsets_laser.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : GRAVURE PHOTO (TRAME DE POINTS)
# ==========================================================================
class TaskPanelHalftone:
    """Convertit une image en trame de points laser (cf.
    generate_gcode_halftone). La conversion image -> grille de noirceur se
    fait ici (QImage, couche UI) pour garder laser_core sans Qt."""

    def __init__(self):
        self._img_cache = (None, None)  # ((chemin, angle), QImage) -- évite de recharger à chaque aperçu
        self._img_error = None          # raison du dernier échec de chargement (affichée)
        # Les photos d'appareil moderne peuvent dépasser la limite
        # d'allocation par défaut de Qt (128-256 Mo) : on la relève, sinon
        # l'image est refusée SANS message. (API Qt 6 ; ignoré si absente.)
        try:
            QtGui.QImageReader.setAllocationLimit(1024)
        except AttributeError:
            pass
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "halftone.svg", "Gravure photo (trame de points)")
        _intro(form,
               "Grave une image (PNG/JPG...) en TRAME DE POINTS laser, comme "
               "une photo de journal. Choisis l'image, la largeur et le pas "
               "de trame -- aucune sélection requise.",
               "Chaque point encode la noirceur locale : soit par sa densité "
               "(tramage par diffusion Floyd-Steinberg, recommandé), soit par "
               "la durée de son pulse. Image posée coin bas-gauche en X0 Y0 ; "
               "zéro X/Y sur la pièce, zéro Z sur sa surface. La machine "
               "s'arrête à chaque point : compter ~2-4 points/seconde -- le "
               "pas de trame pilote directement la durée du job.")

        _section(form, "Image", "sect_preview.svg")
        self.edt_image = QtWidgets.QLineEdit()
        self.edt_image.setToolTip("Chemin de l'image (PNG/JPG/BMP...). Convertie en niveaux de gris.")
        btn_browse = QtWidgets.QPushButton("Parcourir...")
        btn_browse.clicked.connect(self._on_browse)
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.edt_image, 1)
        row_layout.addWidget(btn_browse, 0)
        form.addRow("Image :", row)

        self.spn_width = QtWidgets.QDoubleSpinBox()
        self.spn_width.setRange(5.0, 500.0)
        self.spn_width.setValue(60.0)
        self.spn_width.setSuffix(" mm")
        self.spn_width.setToolTip(
            "Largeur gravée. La hauteur suit les proportions de l'image.")
        form.addRow("Largeur cible :", self.spn_width)

        self.spn_pitch = QtWidgets.QDoubleSpinBox()
        self.spn_pitch.setRange(0.1, 3.0)
        self.spn_pitch.setDecimals(2)
        self.spn_pitch.setValue(0.4)
        self.spn_pitch.setSuffix(" mm")
        self.spn_pitch.setToolTip(
            "Pas de la trame (distance entre deux points). Repère : le\n"
            "diamètre du point au foyer (~0.15-0.3mm) ; plus fin = plus de\n"
            "détail mais beaucoup plus de points (durée en carré inverse\n"
            "du pas).")
        form.addRow("Pas de trame :", self.spn_pitch)

        self.combo_rotation = QtWidgets.QComboBox()
        self.combo_rotation.addItems(["0°", "90°", "180°", "270°"])
        self.combo_rotation.setToolTip(
            "Rotation de l'image avant gravure (sens horaire). L'orientation\n"
            "EXIF des photos de téléphone est déjà appliquée automatiquement ;\n"
            "ce réglage sert à orienter la gravure sur la pièce.")
        form.addRow("Rotation :", self.combo_rotation)

        self.chk_invert = QtWidgets.QCheckBox("Inverser (négatif)")
        self.chk_invert.setToolTip(
            "Par défaut, les zones SOMBRES de l'image sont gravées (la\n"
            "brûlure fonce le matériau clair). Inverser pour graver les\n"
            "zones claires (matériau foncé, ardoise...).")
        form.addRow(self.chk_invert)

        self.lbl_grid = _WrapLabel("Grille : --")
        form.addRow(self.lbl_grid)

        # Aperçu du rendu tramé (l'image telle qu'elle sera piquetée) --
        # LE retour visuel qui compte pour une photo, mis à jour avec les
        # réglages. Pixellisé volontairement : chaque pixel = un point.
        self.lbl_halftone_preview = QtWidgets.QLabel()
        self.lbl_halftone_preview.setAlignment(QtCore.Qt.AlignHCenter)
        self.lbl_halftone_preview.setToolTip(
            "Aperçu du TRAMAGE : ce que les points graveront (noir = point,\n"
            "blanc = rien). Se met à jour avec l'image, la largeur, le pas,\n"
            "le tramage, le négatif et le seuil blanc.")
        form.addRow(self.lbl_halftone_preview)

        _section(form, "Tramage & puissance", "sect_power.svg")
        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItems(["Diffusion (Floyd-Steinberg)", "Durée variable"])
        self.combo_mode.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mode.setMinimumContentsLength(17)
        self.combo_mode.setToolTip(
            "Diffusion : points TOUS identiques (durée max), leur densité\n"
            "locale rend le gris -- robuste, pas de demi-teinte à calibrer.\n"
            "Durée variable : un point par case non blanche, durée du pulse\n"
            "proportionnelle à la noirceur -- rendu plus doux, mais dépend\n"
            "de la réponse du matériau (à valider sur une chute).")
        form.addRow("Tramage :", self.combo_mode)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(500)
        self.spn_power.setToolTip("Puissance (S) des pulses.")
        form.addRow("Puissance :", self.spn_power)

        self.spn_dwell_min = QtWidgets.QDoubleSpinBox()
        self.spn_dwell_min.setRange(1.0, 2000.0)
        self.spn_dwell_min.setDecimals(0)
        self.spn_dwell_min.setValue(10.0)
        self.spn_dwell_min.setSuffix(" ms")
        self.spn_dwell_min.setToolTip(
            "Durée du pulse des points les plus PÂLES (tramage Durée\n"
            "variable uniquement).")
        form.addRow("Pulse min :", self.spn_dwell_min)

        self.spn_dwell_max = QtWidgets.QDoubleSpinBox()
        self.spn_dwell_max.setRange(1.0, 2000.0)
        self.spn_dwell_max.setDecimals(0)
        self.spn_dwell_max.setValue(60.0)
        self.spn_dwell_max.setSuffix(" ms")
        self.spn_dwell_max.setToolTip(
            "Durée du pulse des points les plus NOIRS (et de TOUS les\n"
            "points en tramage Diffusion).")
        form.addRow("Pulse max :", self.spn_dwell_max)

        self.spn_white = QtWidgets.QDoubleSpinBox()
        self.spn_white.setRange(0.0, 50.0)
        self.spn_white.setDecimals(0)
        self.spn_white.setValue(8.0)
        self.spn_white.setSuffix(" %")
        self.spn_white.setToolTip(
            "Seuil blanc (tramage Durée variable) : aucune case dont la\n"
            "noirceur est sous ce seuil n'est gravée -- évite de piqueter\n"
            "les blancs.")
        form.addRow("Seuil blanc :", self.spn_white)

        def _sync_mode():
            is_duree = self.combo_mode.currentIndex() == 1
            self.spn_dwell_min.setEnabled(is_duree)
            self.spn_white.setEnabled(is_duree)
        self.combo_mode.currentIndexChanged.connect(lambda _i: _sync_mode())
        _sync_mode()

        _section(form, "Taille des points", "sect_zheight.svg")
        self.spn_spot_width = QtWidgets.QDoubleSpinBox()
        self.spn_spot_width.setRange(0.0, 30.0)
        self.spn_spot_width.setDecimals(2)
        self.spn_spot_width.setValue(0.0)
        self.spn_spot_width.setSuffix(" mm")
        self.spn_spot_width.setToolTip(
            "LARGEUR de point voulue -- l'atelier calcule la hauteur de\n"
            "défocus correspondante via la calibration des Préférences.\n"
            "0 (ou <= point au foyer) = points fins/nets au foyer ; plus\n"
            "large = gros points doux (grain visible, permet un pas de\n"
            "trame plus grand). Repère : la largeur du point devrait être\n"
            "proche du pas de trame pour des points qui se touchent presque.")
        form.addRow("Largeur du point :", self.spn_spot_width)

        _section(form, "G-code & aperçus", "sect_gcode.svg")
        self.txt_pre = QtWidgets.QPlainTextEdit()
        self.txt_pre.setMaximumHeight(50)
        self.txt_pre.setPlaceholderText("G-code personnalisé inséré avant le job (optionnel)")
        form.addRow("G-code avant :", self.txt_pre)

        self.txt_post = QtWidgets.QPlainTextEdit()
        self.txt_post.setMaximumHeight(50)
        self.txt_post.setPlaceholderText("G-code personnalisé inséré après le job (optionnel)")
        form.addRow("G-code après :", self.txt_post)

        cfg = core.load_config()
        self.txt_pre.setPlainText(cfg.get("pre_ht", ""))
        self.txt_post.setPlainText(cfg.get("post_ht", ""))

        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Dominée par les pulses (G4) et les arrêts à chaque point.")

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Fichier à part traçant le rectangle englobant de l'image, à\n"
            "lancer seul pour vérifier le positionnement avant le vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_dots_preview = QtWidgets.QPushButton("Aperçu des points (vue 3D)")
        self.btn_dots_preview.setToolTip(
            "Dessine chaque point de la trame (petite croix) dans la vue 3D,\n"
            "à sa position réelle -- pour vérifier l'emprise et la densité\n"
            "sur le modèle. Purement visuel.")
        self.btn_dots_preview.clicked.connect(self._on_dots_preview)
        form.addRow(self.btn_dots_preview)

        self._last_fields = {
            "image": self.edt_image, "width": self.spn_width,
            "pitch": self.spn_pitch, "invert": self.chk_invert,
            "rotation": self.combo_rotation,
            "mode": self.combo_mode, "power": self.spn_power,
            "dwell_min": self.spn_dwell_min, "dwell_max": self.spn_dwell_max,
            "white": self.spn_white, "spot_width": self.spn_spot_width,
        }
        _restore_last_values("halftone", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Gravure photo (trame de points)")
        self.form.setWindowIcon(_icon("halftone.svg"))

        for _sig in (self.edt_image.textChanged, self.spn_width.valueChanged,
                     self.spn_pitch.valueChanged, self.spn_white.valueChanged):
            _sig.connect(lambda *_a: self._update_grid_info())
        self.combo_mode.currentIndexChanged.connect(lambda _i: self._update_grid_info())
        self.combo_rotation.currentIndexChanged.connect(lambda _i: self._update_grid_info())
        self.chk_invert.toggled.connect(lambda _v: self._update_grid_info())
        self._update_grid_info()

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.form, "Choisir une image", self.edt_image.text() or os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;Tous les fichiers (*)")
        if path:
            self.edt_image.setText(path)

    def _load_image(self):
        """QImage de l'image choisie (avec cache), ou None. L'orientation
        EXIF est appliquée (une photo de téléphone « portrait » est
        souvent stockée couchée + une étiquette de rotation que les
        visionneuses appliquent mais pas QImage seul -- d'où une photo
        verticale qui apparaissait horizontale ici), puis la rotation
        manuelle du panneau."""
        path = self.edt_image.text().strip()
        if not path:
            self._img_error = None
            return None
        if not os.path.isfile(path):
            self._img_error = "fichier introuvable"
            return None
        angle = self.combo_rotation.currentIndex() * 90
        if self._img_cache[0] == (path, angle) and self._img_cache[1] is not None:
            return self._img_cache[1]
        reader = QtGui.QImageReader(path)
        reader.setAutoTransform(True)  # applique l'orientation EXIF
        img = reader.read()
        if img.isNull() or img.width() < 2 or img.height() < 2:
            # Raison précise plutôt qu'un échec muet (format non géré,
            # limite d'allocation, fichier corrompu...).
            self._img_error = reader.errorString() or "format non lisible"
            return None
        self._img_error = None
        if angle:
            img = img.transformed(QtGui.QTransform().rotate(angle))
        self._img_cache = ((path, angle), img)
        return img

    def _grid_size(self, img):
        cols = max(2, int(round(self.spn_width.value() / self.spn_pitch.value())) + 1)
        rows = max(2, int(round(cols * img.height() / float(img.width()))))
        return cols, rows

    def _build_rows(self, silent=False, max_cells=None):
        """Grille de noirceur 0..1 (lignes haut -> bas) depuis l'image, ou
        None (message d'erreur sauf si silent). max_cells : plafonne la
        grille en réduisant cols/rows proportionnellement -- utilisé par
        l'APERÇU seulement (rendu représentatif à coût borné) ; la
        génération réelle utilise toujours la grille exacte."""
        img = self._load_image()
        if img is None:
            if not silent:
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur", "Choisis d'abord une image valide.")
            return None
        cols, rows = self._grid_size(img)
        if max_cells and cols * rows > max_cells:
            factor = (max_cells / float(cols * rows)) ** 0.5
            cols = max(2, int(cols * factor))
            rows = max(2, int(rows * factor))
        scaled = img.scaled(cols, rows, QtCore.Qt.IgnoreAspectRatio,
                            QtCore.Qt.SmoothTransformation)
        scaled = scaled.convertToFormat(QtGui.QImage.Format_Grayscale8)
        invert = self.chk_invert.isChecked()
        darkness = []
        for y in range(scaled.height()):
            drow = []
            for x in range(scaled.width()):
                g = QtGui.qGray(scaled.pixel(x, y)) / 255.0
                drow.append(g if invert else 1.0 - g)
            darkness.append(drow)
        return darkness

    def _update_grid_info(self):
        img = self._load_image()
        if img is None:
            if self._img_error:
                self.lbl_grid.setText(
                    "Grille : -- image NON CHARGÉE : {}.".format(self._img_error))
            else:
                self.lbl_grid.setText("Grille : -- (choisis une image)")
            self.lbl_halftone_preview.setVisible(False)
            return
        cols, rows = self._grid_size(img)
        pitch = self.spn_pitch.value()
        # Dimensions et orientation affichées : permet de vérifier d'un
        # coup d'oeil que l'image est chargée dans le bon sens (EXIF).
        self.lbl_grid.setText(
            "Image {} x {} px ({}) -- grille {} x {} cases = {:.0f} x {:.0f} mm "
            "({} points max).".format(
                img.width(), img.height(),
                "portrait" if img.height() > img.width() else "paysage",
                cols, rows, (cols - 1) * pitch, (rows - 1) * pitch, cols * rows))
        self._update_halftone_preview()

    _PREVIEW_MAX_CELLS = 250000  # plafond du tramage d'APERÇU (coût borné)

    def _update_halftone_preview(self):
        """Rendu du tramage dans le panneau : une image pixel-par-point
        (noir = point gravé), agrandie SANS lissage pour que la trame
        reste visible. Sur une trame très fine, l'aperçu est calculé sur
        une grille RÉDUITE (représentatif, coût borné) -- il reste
        toujours affiché ; la génération réelle, elle, utilise la grille
        exacte."""
        darkness = self._build_rows(silent=True, max_cells=self._PREVIEW_MAX_CELLS)
        if darkness is None:
            self.lbl_halftone_preview.setVisible(False)
            return
        h = len(darkness)
        w = len(darkness[0])
        mode = "duree" if self.combo_mode.currentIndex() == 1 else "diffusion"
        white = self.spn_white.value() / 100.0
        buf = bytearray(w * h)
        if mode == "diffusion":
            binary = core.floyd_steinberg_dither(darkness)
            for y in range(h):
                base = y * w
                rowb = binary[y]
                for x in range(w):
                    buf[base + x] = 0 if rowb[x] else 255
        else:
            for y in range(h):
                base = y * w
                rowd = darkness[y]
                for x in range(w):
                    d = rowd[x]
                    buf[base + x] = 255 if d < white else 255 - int(d * 255)
        img = QtGui.QImage(bytes(buf), w, h, w, QtGui.QImage.Format_Grayscale8).copy()
        pm = QtGui.QPixmap.fromImage(img)
        target_w = 240
        pm = pm.scaledToWidth(target_w, QtCore.Qt.FastTransformation)
        self.lbl_halftone_preview.setPixmap(pm)
        self.lbl_halftone_preview.setVisible(True)

    def _on_dots_preview(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Ouvre (ou crée) un document d'abord.")
            return
        rows = self._build_rows()
        if rows is None:
            return
        kw = self._gen_kwargs()
        dots = core.halftone_dots(rows, kw["pitch"], kw["dwell_min_s"], kw["dwell_max_s"],
                                  mode=kw["mode"], white_threshold=kw["white_threshold"])
        if not dots:
            QtWidgets.QMessageBox.critical(self.form, "Erreur",
                                           "Aucun point (image toute blanche ?).")
            return
        if len(dots) > 20000:
            reply = QtWidgets.QMessageBox.question(
                self.form, "Beaucoup de points",
                "{} points à dessiner : la vue 3D peut ramer. Continuer ?".format(len(dots)),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
                return
        # Une petite croix par point, à sa position réelle.
        r = kw["pitch"] * 0.3
        segs = []
        for x, y, _dw in dots:
            segs.append((FreeCAD.Vector(x - r, y, 0), FreeCAD.Vector(x + r, y, 0)))
            segs.append((FreeCAD.Vector(x, y - r, 0), FreeCAD.Vector(x, y + r, 0)))
        core.create_toolpath_preview_objects(doc, [], segs, name_prefix="Apercu_Photo")

    def _gen_kwargs(self):
        return {
            "pitch": self.spn_pitch.value(),
            "z_work": core.Z_WORK_MM + (core.defocus_for_spot_diameter(
                self.spn_spot_width.value(), core.SPOT_FOCUS_MM,
                core.calibrated_half_angle()) or 0.0),
            "power": self.spn_power.value(),
            "dwell_min_s": self.spn_dwell_min.value() / 1000.0,
            "dwell_max_s": self.spn_dwell_max.value() / 1000.0,
            "mode": "duree" if self.combo_mode.currentIndex() == 1 else "diffusion",
            "white_threshold": self.spn_white.value() / 100.0,
        }

    def _update_duration_preview(self):
        rows = self._build_rows(silent=True)
        if rows is None:
            self.lbl_duration.setText("Durée estimée : -- (aucune image valide)")
            return
        gcode = core.generate_gcode_halftone(rows, quiet=True, **self._gen_kwargs())
        if not gcode:
            self.lbl_duration.setText("Durée estimée : -- (image toute blanche ?)")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        rows = self._build_rows()
        if rows is None:
            return
        gcode = core.generate_gcode_halftone(rows, frame_only=True, **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_photo.ngc")

    def accept(self):
        _save_last_values("halftone", self._last_fields)
        rows = self._build_rows()
        if rows is None:
            return False

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_halftone(
            rows, pre_gcode=pre_text, post_gcode=post_text, **self._gen_kwargs())

        cfg = core.load_config()
        cfg["pre_ht"] = pre_text
        cfg["post_ht"] = post_text
        core.save_config(cfg)

        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Aucun G-code généré (image toute blanche au seuil actuel ?).")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/gravure_photo.ngc")

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

        _panel_header(form, "testgrid.svg", "Grille de test puissance / vitesse")
        _intro(form,
               "Grave (ou découpe) une grille de cellules sur une chute : "
               "chaque cellule teste UN couple puissance/vitesse. Tu choisis "
               "ensuite la meilleure à l'oeil. Aucune sélection requise.",
               "Puissance croissante en colonnes (X), vitesse croissante en "
               "lignes (Y) ; chaque colonne/ligne est étiquetée directement "
               "sur la pièce (S..., F...), et la grille complète est aussi "
               "imprimée dans la vue Rapport. Le champ « Hauteur (Z) de "
               "test » permet de rejouer la même grille à une autre hauteur "
               "(bec défocalisé) pour caractériser un matériau proprement, "
               "une hauteur à la fois.")
        _diagram(form, "diag_grid.svg")

        # Préréglages nommés (par matériau), catégorie "testgrid" : TOUS les
        # réglages de la grille sont couverts (pas seulement puissance/vitesse).
        _section(form, "Préréglage matériau", "sect_preset.svg")
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Recharge un jeu complet de réglages de grille sauvegardé sous\n"
            "un nom (typiquement : un matériau). Survole un nom dans la\n"
            "liste pour voir le résumé de ses réglages avant de choisir.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.lbl_preset_summary = _WrapLabel("")
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

        _section(form, "Mode & plages puissance/vitesse", "sect_power.svg")
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
        self.spn_power_min.setRange(0, core.S_MAX)
        self.spn_power_min.setValue(200)
        self.spn_power_min.setToolTip(
            "Puissance (valeur S) de la 1ère colonne (X minimal) de la\n"
            "grille -- la plus faible testée.")
        form.addRow("Puissance min (S) :", self.spn_power_min)

        self.spn_power_max = QtWidgets.QDoubleSpinBox()
        self.spn_power_max.setRange(0, core.S_MAX)
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

        _section(form, "Cellules", "sect_contour.svg")
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

        self.spn_zwork = QtWidgets.QDoubleSpinBox()
        self.spn_zwork.setRange(-50.0, 200.0)
        self.spn_zwork.setDecimals(2)
        self.spn_zwork.setValue(core.Z_WORK_MM)
        self.spn_zwork.setSuffix(" mm")
        self.spn_zwork.setToolTip(
            "Hauteur du bec (Z) à laquelle TOUTE la grille est gravée --\n"
            "par défaut la focale des Préférences ({:.2f} mm). Change-la\n"
            "pour tester la même matrice puissance/vitesse à une AUTRE\n"
            "hauteur (bec écarté du foyer = point élargi/défocalisé) : tu\n"
            "balaies ainsi plusieurs hauteurs proprement, une grille par\n"
            "hauteur, sans toucher aux Préférences. En remplissage Défocus,\n"
            "cette valeur reste la base et le défocus calculé s'ajoute\n"
            "par-dessus pour les cellules.".format(core.Z_WORK_MM))
        form.addRow("Hauteur (Z) de test :", self.spn_zwork)

        _section(form, "Remplissage", "sect_fill.svg")
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

        self.lbl_defocus_result = _WrapLabel("Défocus calculé : --")
        self.lbl_defocus_result.setToolTip(
            "Calculé depuis la calibration du point des Préférences (icône\n"
            "engrenage) -- mesurée avec la Bande de calibration défocus.")
        form.addRow(self.lbl_defocus_result)

        self._defocus_widgets = [self.lbl_defocus_result]


        self.lbl_total = _WrapLabel("Total : -- cellules")
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
            # Calibration du point : centralisée dans les Préférences.
            half_angle = core.calibrated_half_angle()
            defocus = core.defocus_for_fill_spacing(
                self.spn_hatch_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration du point invalide dans\n"
                    "les Préférences : le point au défocus de test doit être\n"
                    "plus large qu'au foyer).")
            else:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.3f} mm -- Z cellules = Z de travail\n"
                    "+ cette valeur (étiquettes toujours au foyer).\n"
                    "(Calibration du point : Préférences, icône engrenage.)".format(defocus))

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
        self.spn_power_steps.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_feed_steps.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_cell_size.valueChanged.connect(lambda _v: _update_total_preview())
        self.spn_gap.valueChanged.connect(lambda _v: _update_total_preview())
        _update_visibility()
        _update_total_preview()

        _section(form, "Options", "sect_options.svg")
        self.chk_proximity = QtWidgets.QCheckBox("Optimiser l'ordre par proximité")
        self.chk_proximity.setChecked(True)
        self.chk_proximity.setToolTip(
            "Réordonne les chaînes (cellules et étiquettes) par plus\n"
            "proche voisin (heuristique, comme le mode Découpe\n"
            "multi-passes) pour réduire les déplacements à vide -- calculé\n"
            "SÉPARÉMENT pour les cellules et les étiquettes (jamais\n"
            "mélangées) afin de garder un minimum de changements de Z.")
        form.addRow(self.chk_proximity)

        _section(form, "Étiquettes S/F", "sect_labels.svg")
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
        self.spn_label_power.setRange(0, core.S_MAX)
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

        _section(form, "Cadre net (contour des carrés)", "sect_contour.svg")
        self.chk_border = QtWidgets.QCheckBox("Cadre net autour de chaque carré (au foyer)")
        self.chk_border.setChecked(True)
        self.chk_border.setToolTip(
            "Grave le contour carré de chaque cellule, NET AU FOYER, à un Z\n"
            "propre (ci-dessous). Utile surtout en remplissage Défocus, où\n"
            "les cellules sont volontairement floues : le cadre au foyer\n"
            "délimite clairement chaque carré. Indépendant du Z des\n"
            "cellules (qui peut être décalé par le défocus).")
        form.addRow(self.chk_border)


        self.spn_border_power = QtWidgets.QDoubleSpinBox()
        self.spn_border_power.setRange(0, core.S_MAX)
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

        self.chk_border.toggled.connect(self.spn_border_power.setEnabled)
        self.chk_border.toggled.connect(self.spn_border_feed.setEnabled)

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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
        _combined_add_button(form, self._on_add_to_combined)

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

        self._last_fields = {
            "mode": self.combo_mode, "power_min": self.spn_power_min,
            "power_max": self.spn_power_max, "power_steps": self.spn_power_steps,
            "feed_min": self.spn_feed_min, "feed_max": self.spn_feed_max,
            "feed_steps": self.spn_feed_steps, "cell_size": self.spn_cell_size,
            "gap": self.spn_gap, "zwork": self.spn_zwork, "filltype": self.combo_filltype,
            "hatch_spacing": self.spn_hatch_spacing, "hatch_angle": self.spn_hatch_angle,
            "proximity": self.chk_proximity,
            "labels": self.chk_labels, "label_power": self.spn_label_power,
            "label_feed": self.spn_label_feed, "border": self.chk_border,
            "border_power": self.spn_border_power,
            "border_feed": self.spn_border_feed,
        }
        _restore_last_values("testgrid", self._last_fields)

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
            lines.append("Cadre au foyer S{:g} F{:g}".format(
                values.get("border_power", 0), values.get("border_feed", 0)))
        return "\n".join(lines)

    def _border_kwargs(self):
        """Paramètres du cadre net passés au générateur (partagés par
        accept, aperçu trajet et estimation de durée)."""
        return {
            "draw_border": self.chk_border.isChecked(),
            "z_border": self.spn_zwork.value(),
            "border_power": self.spn_border_power.value(),
            "border_feed": self.spn_border_feed.value(),
        }

    def _populate_preset_combo(self):
        self.combo_preset.blockSignals(True)
        self.combo_preset.clear()
        self.combo_preset.addItem("-- Choisir --", None)
        factory = core.factory_presets("testgrid")
        user = core.load_presets("testgrid")
        # ★ = préréglages d'usine (non supprimables) ; nom réel en itemData.
        for name in factory:
            self.combo_preset.addItem("★ " + name, name)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1,
                self._preset_summary(factory[name]), QtCore.Qt.ToolTipRole)
        for name in sorted(user):
            if name in factory:
                continue
            self.combo_preset.addItem(name, name)
            self.combo_preset.setItemData(
                self.combo_preset.count() - 1,
                self._preset_summary(user[name]), QtCore.Qt.ToolTipRole)
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
            "zwork": self.spn_zwork.value(),
            "filltype": self.combo_filltype.currentIndex(),
            "hatch_spacing": self.spn_hatch_spacing.value(),
            "hatch_angle": self.spn_hatch_angle.value(),
            "proximity": self.chk_proximity.isChecked(),
            "labels": self.chk_labels.isChecked(),
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
            "border_enabled": self.chk_border.isChecked(),
            "border_power": self.spn_border_power.value(),
            "border_feed": self.spn_border_feed.value(),
        }

    def _on_preset_selected(self, index):
        if index <= 0:
            self.lbl_preset_summary.setVisible(False)
            return
        values = core.all_presets("testgrid").get(self.combo_preset.currentData())
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
        self.spn_zwork.setValue(values.get("zwork", self.spn_zwork.value()))
        self.combo_filltype.setCurrentIndex(values.get("filltype", self.combo_filltype.currentIndex()))
        self.spn_hatch_spacing.setValue(values.get("hatch_spacing", self.spn_hatch_spacing.value()))
        self.spn_hatch_angle.setValue(values.get("hatch_angle", self.spn_hatch_angle.value()))
        self.chk_proximity.setChecked(values.get("proximity", self.chk_proximity.isChecked()))
        self.chk_labels.setChecked(values.get("labels", self.chk_labels.isChecked()))
        self.spn_label_power.setValue(values.get("label_power", self.spn_label_power.value()))
        self.spn_label_feed.setValue(values.get("label_feed", self.spn_label_feed.value()))
        self.chk_border.setChecked(values.get("border_enabled", self.chk_border.isChecked()))
        self.spn_border_power.setValue(values.get("border_power", self.spn_border_power.value()))
        self.spn_border_feed.setValue(values.get("border_feed", self.spn_border_feed.value()))
        self.lbl_preset_summary.setText(self._preset_summary(values))
        self.lbl_preset_summary.setVisible(True)

    def _on_save_preset(self):
        current = self.combo_preset.currentData() or ""
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Sauvegarder le préréglage",
            "Nom du préréglage (matériau) :", text=current)
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("testgrid", name, self._preset_values())
        self._populate_preset_combo()
        idx = self.combo_preset.findData(name)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)

    def _on_delete_preset(self):
        name = self.combo_preset.currentData()
        if not name:
            return
        if name not in core.load_presets("testgrid"):
            QtWidgets.QMessageBox.information(
                self.form, "Préréglage d'usine",
                "« {} » est un préréglage d'usine : il ne peut pas être\n"
                "supprimé. Tu peux le charger, l'ajuster, puis le sauvegarder\n"
                "sous un autre nom.".format(name))
            return
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
        # use_proximity transmis comme dans accept() : sans lui, la durée
        # affichée est celle du trajet NON optimisé, pas du job réel.
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(), label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(),
            quiet=True, **self._border_kwargs()
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
            half_angle = core.calibrated_half_angle()
            defocus = core.defocus_for_fill_spacing(
                self.spn_hatch_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
            if defocus is None:
                if not silent:
                    QtWidgets.QMessageBox.critical(
                        self.form, "Erreur",
                        "Calibration du point invalide dans les Préférences :\n"
                        "le point mesuré au défocus de test doit être plus\n"
                        "large que celui mesuré au foyer (à mesurer avec la\n"
                        "Bande de calibration défocus, puis à saisir dans les\n"
                        "Préférences, icône engrenage).")
                return None, None, None, None
            cell_z_offset = defocus
            # Rayon du point élargi à ce défocus : on rentre la zone
            # hachurée d'autant pour que la brûlure ne déborde pas du carré.
            spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
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
        # Les paramètres du cadre sont transmis aussi en cadrage : le Z de
        # sécurité du fichier d'aperçu doit être LE MÊME que celui du job
        # réel (z_border compte dans son calcul) -- c'est la garantie
        # documentée de l'aperçu cadrage.
        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            label_power=self.spn_label_power.value(), label_feed=self.spn_label_feed.value(),
            cell_z_offset=cell_z_offset, frame_only=True, **self._border_kwargs()
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

    def _build_combined_operation(self):
        _mode, _fill, cells, cell_z_offset = self._build_cells()
        if cells is None:
            return None
        _pw, _fd, label_edges = self._build_label_edges(cells)
        return {"type": "testgrid", "label": "Grille de test",
                "params": dict(cells=cells, z_work=self.spn_zwork.value(),
                               label_edges=label_edges if self.chk_labels.isChecked() else None,
                               label_power=self.spn_label_power.value(),
                               label_feed=self.spn_label_feed.value(),
                               cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(),
                               **self._border_kwargs())}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def accept(self):
        if self.spn_power_max.value() < self.spn_power_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Puissance max doit être >= puissance min.")
            return False
        if self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Vitesse max doit être >= vitesse min.")
            return False
        _save_last_values("testgrid", self._last_fields)

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
        _panel_header(form, "curved.svg", "Marquage de motif (plat ou courbe)")
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _intro(form,
               "Grave un motif filaire (hachures, tracés...). Pièce PLATE : "
               "sélectionne juste le motif 2D. Surface COURBE : sélectionne "
               "le motif projeté (Hachures_3D) ET le modèle 3D d'origine, "
               "les deux en même temps.",
               "Le modèle 3D permet une sonde exacte du relief pendant le "
               "marquage (sans lui, le Z n'est qu'interpolé entre les points "
               "déjà projetés). Cinq styles de trait : plein, tirets, "
               "pointillé, vague défocus (le Z ondule, trait qui varie en "
               "largeur), et défocus point élargi (noircir un remplissage en "
               "un passage) -- tous suivent le relief. Le Z de travail et la "
               "marge de transit viennent des Préférences.")

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

        def _apply_shade(s):
            # Applique un ton MESURÉ du nuancier : puissance, vitesse, et
            # si le ton était défocalisé, style « Défocus (point élargi) »
            # à la largeur constatée -- le rendu sera celui du test.
            self.spn_power.setValue(s.get("power", self.spn_power.value()))
            self.spn_feed.setValue(s.get("feed", self.spn_feed.value()))
            if s.get("z_offset", 0) > 0:
                self.combo_style.setCurrentIndex(4)
                width = s.get("width", 0) or core.spot_diameter_at_defocus(
                    s["z_offset"], core.SPOT_FOCUS_MM, core.calibrated_half_angle())
                self.spn_spot_width.setValue(width)
            else:
                self.combo_style.setCurrentIndex(0)
            self._update_style_ui()
            self._update_duration_preview()
        self._shade_picker = _make_shade_picker(form, _apply_shade)

        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la gravure (valeur S, selon\n"
            "l'échelle de la machine). 0 = laser éteint -- utile pour\n"
            "vérifier le trajet (avec l'aperçu cadrage) sans marquer.")
        form.addRow("Puissance (S 0-{:g}) :".format(core.S_MAX), self.spn_power)

        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(1000)
        self.spn_feed.setSuffix(" mm/min")
        self.spn_feed.setToolTip(
            "Vitesse d'avance pendant la gravure (mm/min). Plus lent =\n"
            "marquage plus prononcé mais job plus long ; plus rapide =\n"
            "marquage plus léger.")
        form.addRow("Avance (Feed) :", self.spn_feed)


        _section(form, "Style de trait", "sect_options.svg")
        self.combo_style = QtWidgets.QComboBox()
        self.combo_style.addItems(
            ["Trait plein", "Tirets", "Pointillé", "Vague défocus", "Défocus (point élargi)"])
        self.combo_style.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_style.setMinimumContentsLength(14)
        self.combo_style.setToolTip(
            "Trait plein : trait continu net, au foyer.\n"
            "Tirets : faisceau pulsé le long du tracé (mouvement continu).\n"
            "Pointillé : vrais points ronds -- arrêt + pulse à chaque point\n"
            "(plus lent). Vague défocus : le Z oscille entre le foyer et\n"
            "l'amplitude ci-dessous AU-DESSUS du suivi de relief -- trait\n"
            "qui varie continûment en largeur et en intensité.\n"
            "Défocus (point élargi) : trait continu gravé plus HAUT que le\n"
            "foyer (point laser élargi) -- pour NOIRCIR un remplissage en un\n"
            "passage (l'équivalent du remplissage Défocus des Hachures 2D,\n"
            "mais appliqué au motif projeté). Tous les styles suivent le\n"
            "relief comme le trait plein.")
        form.addRow("Style de trait :", self.combo_style)

        self.spn_dash_len = QtWidgets.QDoubleSpinBox()
        self.spn_dash_len.setRange(0.2, 50.0)
        self.spn_dash_len.setValue(3.0)
        self.spn_dash_len.setSuffix(" mm")
        self.spn_dash_len.setToolTip("Longueur de chaque tiret (style Tirets).")
        form.addRow("Longueur tiret :", self.spn_dash_len)

        self.spn_gap_len = QtWidgets.QDoubleSpinBox()
        self.spn_gap_len.setRange(0.2, 50.0)
        self.spn_gap_len.setValue(2.0)
        self.spn_gap_len.setSuffix(" mm")
        self.spn_gap_len.setToolTip("Espace entre deux tirets (style Tirets).")
        form.addRow("Espace entre tirets :", self.spn_gap_len)

        self.spn_dot_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_dot_spacing.setRange(0.2, 50.0)
        self.spn_dot_spacing.setValue(1.5)
        self.spn_dot_spacing.setSuffix(" mm")
        self.spn_dot_spacing.setToolTip("Espacement des points le long du tracé (style Pointillé).")
        form.addRow("Espacement points :", self.spn_dot_spacing)

        self.spn_dot_dwell = QtWidgets.QDoubleSpinBox()
        self.spn_dot_dwell.setRange(5.0, 2000.0)
        self.spn_dot_dwell.setDecimals(0)
        self.spn_dot_dwell.setValue(50.0)
        self.spn_dot_dwell.setSuffix(" ms")
        self.spn_dot_dwell.setToolTip(
            "Durée du pulse laser sur chaque point (style Pointillé). La\n"
            "machine s'arrête à chaque point : job nettement plus lent.")
        form.addRow("Durée du pulse :", self.spn_dot_dwell)

        self.spn_wave_period = QtWidgets.QDoubleSpinBox()
        self.spn_wave_period.setRange(0.5, 100.0)
        self.spn_wave_period.setValue(5.0)
        self.spn_wave_period.setSuffix(" mm")
        self.spn_wave_period.setToolTip(
            "Période de l'oscillation Z (style Vague) : distance le long\n"
            "du tracé entre deux points fins (au foyer).")
        form.addRow("Période de la vague :", self.spn_wave_period)

        self.spn_wave_width = QtWidgets.QDoubleSpinBox()
        self.spn_wave_width.setRange(0.1, 30.0)
        self.spn_wave_width.setDecimals(2)
        self.spn_wave_width.setValue(1.0)
        self.spn_wave_width.setSuffix(" mm")
        self.spn_wave_width.setToolTip(
            "Largeur MAX du trait au sommet de la vague (style Vague) : la\n"
            "hauteur de défocus correspondante est calculée via la\n"
            "calibration du point (Préférences). Au creux, le trait revient\n"
            "au point fin du foyer.")
        form.addRow("Largeur max de la vague :", self.spn_wave_width)

        self.spn_spot_width = QtWidgets.QDoubleSpinBox()
        self.spn_spot_width.setRange(0.1, 30.0)
        self.spn_spot_width.setDecimals(2)
        self.spn_spot_width.setValue(1.0)
        self.spn_spot_width.setSuffix(" mm")
        self.spn_spot_width.setToolTip(
            "LARGEUR du point voulue (style Défocus point élargi) -- tu\n"
            "choisis directement l'épaisseur du trait, l'atelier calcule de\n"
            "combien remonter le bec (défocus) via la calibration du point\n"
            "(Préférences). Plus le point est large, plus il faut de\n"
            "puissance (voir « Puissance vs défocus » ci-dessous). La\n"
            "hauteur de défocus obtenue s'affiche ci-dessous.")
        form.addRow("Largeur du point :", self.spn_spot_width)

        self.lbl_style_info = _WrapLabel("")
        form.addRow(self.lbl_style_info)

        self._fluence = _make_fluence_widgets(form)

        def _update_style_ui():
            idx = self.combo_style.currentIndex()
            # _set_row_visible masque libellé + champ (sinon des lignes
            # vides « Longueur tiret : » restent sur les styles inactifs).
            for w in (self.spn_dash_len, self.spn_gap_len):
                _set_row_visible(form, w, idx == 1)
            for w in (self.spn_dot_spacing, self.spn_dot_dwell):
                _set_row_visible(form, w, idx == 2)
            for w in (self.spn_wave_period, self.spn_wave_width):
                _set_row_visible(form, w, idx == 3)
            _set_row_visible(form, self.spn_spot_width, idx == 4)
            # Compensation puissance/défocus : seulement pour le style
            # Défocus (point élargi), le seul à point élargi constant.
            self._fluence["container"].setVisible(idx == 4)
            half = core.calibrated_half_angle()
            if idx == 3:
                # Largeur voulue -> défocus (amplitude Z) via la calibration.
                amp = core.defocus_for_spot_diameter(
                    self.spn_wave_width.value(), core.SPOT_FOCUS_MM, half) or 0.0
                peak = core.wave_peak_z_feed(
                    amp, self.spn_feed.value(), self.spn_wave_period.value())
                txt = ("Vague : largeur max {:.2f} mm -> bec remonté de {:.2f} mm,\n"
                       "vitesse Z crête ~{:.0f} mm/min").format(
                    self.spn_wave_width.value(), amp, peak)
                if peak > core.Z_MAX_FEED_MM_MIN:
                    txt += (" -- AU-DELÀ de la limite Z supposée ({:.0f}, cf. Préférences) :"
                            " le trajet sera ralenti").format(core.Z_MAX_FEED_MM_MIN)
                self.lbl_style_info.setText(txt + ".")
                self.lbl_style_info.setVisible(True)
            elif idx == 4:
                defocus = core.defocus_for_spot_diameter(
                    self.spn_spot_width.value(), core.SPOT_FOCUS_MM, half) or 0.0
                self.lbl_style_info.setText(
                    "Point élargi à {:.2f} mm -> bec remonté de {:.2f} mm au-dessus\n"
                    "du foyer. Pour un noir plein, espacer les hachures d'un peu\n"
                    "moins que cette largeur (mode Hachures 2D).".format(
                        self.spn_spot_width.value(), defocus))
                self.lbl_style_info.setVisible(True)
                # Aperçu fluence + puissance compensée pour ce point élargi.
                txt2, color, _ = _fluence_advice(
                    self.spn_spot_width.value(), self.spn_power.value(),
                    self.spn_feed.value(), self._fluence)
                self._fluence["info"].setText(txt2)
                self._fluence["info"].setStyleSheet("color: {};".format(color))
                self.spn_power.setEnabled(not self._fluence["chk"].isChecked())
            else:
                self.lbl_style_info.setVisible(False)
                self.spn_power.setEnabled(True)

        self._update_style_ui = _update_style_ui
        self.combo_style.currentIndexChanged.connect(lambda _i: _update_style_ui())
        for w in (self.spn_wave_width, self.spn_wave_period, self.spn_feed, self.spn_spot_width,
                  self.spn_power, self._fluence["ref_power"], self._fluence["ref_feed"],
                  self._fluence["ref_spot"]):
            w.valueChanged.connect(lambda _v: _update_style_ui())
        self._fluence["chk"].toggled.connect(lambda _v: _update_style_ui())

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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
        _combined_add_button(form, self._on_add_to_combined)

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

        self._last_fields = {
            "power": self.spn_power, "feed": self.spn_feed,
            "style": self.combo_style, "dash_len": self.spn_dash_len,
            "gap_len": self.spn_gap_len, "dot_spacing": self.spn_dot_spacing,
            "dot_dwell_ms": self.spn_dot_dwell, "wave_period": self.spn_wave_period,
            "wave_width": self.spn_wave_width, "spot_width": self.spn_spot_width,
            "fluence_on": self._fluence["chk"], "ref_power": self._fluence["ref_power"],
            "ref_feed": self._fluence["ref_feed"], "ref_spot": self._fluence["ref_spot"],
        }
        _restore_last_values("curved", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Marquage de motif (plat ou courbe)")
        self.form.setWindowIcon(_icon("curved.svg"))

        self._populate_preset_combo()
        self._shade_picker["reload"]()
        _update_style_ui()
        self._update_duration_preview()

    def _get_edges(self):
        edge_sel, reference_shape = core.split_selection(self.selection)
        edges = core.get_all_edges_from_selection(edge_sel)
        return edges, reference_shape

    def _z_focus(self):
        """Z de travail effectif : foyer des Préférences, remonté du
        défocus si le style « Défocus (point élargi) » est choisi. Le
        défocus est calculé depuis la LARGEUR DE POINT voulue via la
        calibration (le point élargi noircit en un passage)."""
        base = core.Z_WORK_MM
        if self.combo_style.currentIndex() == 4:  # Défocus (point élargi)
            defocus = core.defocus_for_spot_diameter(
                self.spn_spot_width.value(), core.SPOT_FOCUS_MM, core.calibrated_half_angle())
            base += defocus or 0.0
        return base

    def _effective_power(self):
        """Puissance effective : compensée selon la largeur du point
        (fluence de référence) si le style Défocus est choisi ET la
        compensation cochée, sinon la puissance saisie."""
        if self.combo_style.currentIndex() == 4:
            _, _, p_eff = _fluence_advice(
                self.spn_spot_width.value(), self.spn_power.value(),
                self.spn_feed.value(), self._fluence)
            if p_eff is not None:
                return p_eff
        return self.spn_power.value()

    def _style_kwargs(self):
        # Le style « Défocus » (index 4) est un trait PLEIN gravé plus haut
        # (cf. _z_focus) : le point élargi fait le noir, le tracé reste
        # continu. D'où style="plein" ici, la différence est portée par le Z.
        style_map = {0: "plein", 1: "tirets", 2: "pointille", 3: "vague", 4: "plein"}
        # Vague : la largeur max voulue -> amplitude de défocus (Z) via la
        # calibration du point.
        wave_amp = core.defocus_for_spot_diameter(
            self.spn_wave_width.value(), core.SPOT_FOCUS_MM, core.calibrated_half_angle())
        return {
            "style": style_map.get(self.combo_style.currentIndex(), "plein"),
            "style_params": {
                "dash_len": self.spn_dash_len.value(),
                "gap_len": self.spn_gap_len.value(),
                "dot_spacing": self.spn_dot_spacing.value(),
                "dot_dwell_s": self.spn_dot_dwell.value() / 1000.0,
                "wave_period": self.spn_wave_period.value(),
                "wave_amplitude": wave_amp or 0.0,
            },
        }

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
        self.combo_style.setCurrentIndex(values.get("style", self.combo_style.currentIndex()))
        self.spn_dash_len.setValue(values.get("dash_len", self.spn_dash_len.value()))
        self.spn_gap_len.setValue(values.get("gap_len", self.spn_gap_len.value()))
        self.spn_dot_spacing.setValue(values.get("dot_spacing", self.spn_dot_spacing.value()))
        self.spn_dot_dwell.setValue(values.get("dot_dwell_ms", self.spn_dot_dwell.value()))
        self.spn_wave_period.setValue(values.get("wave_period", self.spn_wave_period.value()))
        self.spn_wave_width.setValue(values.get("wave_width", self.spn_wave_width.value()))
        self.spn_spot_width.setValue(values.get("spot_width", self.spn_spot_width.value()))
        self._fluence["chk"].setChecked(values.get("fluence_on", self._fluence["chk"].isChecked()))
        self._fluence["ref_power"].setValue(values.get("ref_power", self._fluence["ref_power"].value()))
        self._fluence["ref_feed"].setValue(values.get("ref_feed", self._fluence["ref_feed"].value()))
        self._fluence["ref_spot"].setValue(values.get("ref_spot", self._fluence["ref_spot"].value()))

    def _on_save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self.form, "Sauvegarder le préréglage", "Nom du préréglage :")
        name = name.strip()
        if not ok or not name:
            return
        core.save_preset("curved", name, {
            "power": self.spn_power.value(),
            "feed": self.spn_feed.value(),
            "style": self.combo_style.currentIndex(),
            "dash_len": self.spn_dash_len.value(),
            "gap_len": self.spn_gap_len.value(),
            "dot_spacing": self.spn_dot_spacing.value(),
            "dot_dwell_ms": self.spn_dot_dwell.value(),
            "wave_period": self.spn_wave_period.value(),
            "wave_width": self.spn_wave_width.value(),
            "spot_width": self.spn_spot_width.value(),
            "fluence_on": self._fluence["chk"].isChecked(),
            "ref_power": self._fluence["ref_power"].value(),
            "ref_feed": self._fluence["ref_feed"].value(),
            "ref_spot": self._fluence["ref_spot"].value(),
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
            self._edges, self._effective_power(), self.spn_feed.value(),
            self._z_focus(), core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
            **self._style_kwargs()
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
        z_offset = core.curved_native_z_offset(self._edges, self._z_focus())
        rapid = core.shift_segments_z(rapid, -z_offset)
        mark = core.shift_segments_z(mark, -z_offset)
        core.create_toolpath_preview_objects(FreeCAD.ActiveDocument, rapid, mark)

    def _update_duration_preview(self):
        if not self._edges:
            self.lbl_duration.setText("Durée estimée : -- (aucun segment dans la sélection)")
            return
        gcode = core.generate_gcode_curved(
            self._edges, self._effective_power(), self.spn_feed.value(),
            self._z_focus(), core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
            **self._style_kwargs()
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
            self._edges, self._effective_power(), self.spn_feed.value(),
            self._z_focus(), core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape, frame_only=True, probe=self._probe,
            **self._style_kwargs()
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_courbe.ngc")

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        return {"type": "curved",
                "label": "Marquage (S{:.0f})".format(self._effective_power()),
                "params": dict(edges=self._edges, power=self._effective_power(),
                               feed=self.spn_feed.value(), z_focus=self._z_focus(),
                               marge_survol=core.TRANSIT_MARGIN_MM, reference_shape=self._reference_shape,
                               probe=self._probe, **self._style_kwargs())}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        _save_last_values("curved", self._last_fields)
        FreeCAD.Console.PrintMessage(
            "Chaînage des segments connectés... ({})\n".format(
                "objet 3D de référence détecté" if self._reference_shape is not None else "pas d'objet 3D, interpolation"))

        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()
        gcode = core.generate_gcode_curved(
            self._edges,
            self._effective_power(),
            self.spn_feed.value(),
            self._z_focus(),
            core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape,
            pre_gcode=pre_text,
            post_gcode=post_text,
            probe=self._probe,
            **self._style_kwargs()
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
        _panel_header(form, "flat.svg", "Découpe multi-passes (plat)")
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
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la découpe (valeur S, selon\n"
            "l'échelle de la machine). Fixe pour toutes les passes, sauf si\n"
            "la rampe de puissance ci-dessous est activée.")
        form.addRow("Puissance (S 0-{:g}) :".format(core.S_MAX), self.spn_power)

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

        self.lbl_zauto = _WrapLabel("Hauteur bec 1ère passe (calculée) : 0.000 mm")
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
        self.spn_power_end.setRange(0, core.S_MAX)
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

        _section(form, "Attaches & amorce", "sect_safety.svg")
        self.spn_tab_count = QtWidgets.QSpinBox()
        self.spn_tab_count.setRange(0, 12)
        self.spn_tab_count.setValue(0)
        self.spn_tab_count.setToolTip(
            "Nombre d'ATTACHES par contour fermé (0 = désactivé) : des ponts\n"
            "de matière non coupés, régulièrement répartis, qui retiennent\n"
            "la pièce dans la planche jusqu'à la fin du job (à couper au\n"
            "cutter ensuite). S'applique aussi aux trous : la chute d'un\n"
            "trou reste attachée au lieu de tomber dans la machine.")
        form.addRow("Nombre d'attaches :", self.spn_tab_count)

        self.spn_tab_length = QtWidgets.QDoubleSpinBox()
        self.spn_tab_length.setRange(0.5, 20.0)
        self.spn_tab_length.setValue(4.0)
        self.spn_tab_length.setSuffix(" mm")
        self.spn_tab_length.setToolTip("Longueur de chaque attache le long du contour.")
        form.addRow("Longueur d'attache :", self.spn_tab_length)

        self.spn_tab_height = QtWidgets.QDoubleSpinBox()
        self.spn_tab_height.setRange(0.1, 10.0)
        self.spn_tab_height.setDecimals(1)
        self.spn_tab_height.setValue(1.0)
        self.spn_tab_height.setSuffix(" mm")
        self.spn_tab_height.setToolTip(
            "Épaisseur de matière laissée sous chaque attache : seules les\n"
            "passes qui attaqueraient ces derniers mm sautent les zones\n"
            "d'attache (faisceau éteint), les passes hautes coupent normalement.")
        form.addRow("Hauteur d'attache :", self.spn_tab_height)

        self.spn_tab_count.valueChanged.connect(
            lambda v: (self.spn_tab_length.setEnabled(v > 0), self.spn_tab_height.setEnabled(v > 0)))
        self.spn_tab_length.setEnabled(False)
        self.spn_tab_height.setEnabled(False)

        self.spn_lead_in = QtWidgets.QDoubleSpinBox()
        self.spn_lead_in.setRange(0.0, 10.0)
        self.spn_lead_in.setDecimals(1)
        self.spn_lead_in.setValue(0.0)
        self.spn_lead_in.setSuffix(" mm")
        self.spn_lead_in.setToolTip(
            "AMORCE de découpe (0 = désactivé) : le faisceau s'allume à\n"
            "cette distance du contour, DANS LA CHUTE (extérieur d'une\n"
            "pièce, intérieur d'un trou), puis rejoint le contour en\n"
            "coupant -- la verrue du point d'allumage reste hors du bord\n"
            "fini. Contours fermés uniquement.")
        form.addRow("Amorce (lead-in) :", self.spn_lead_in)

        _section(form, "Copies en matrice", "sect_options.svg")
        self.spn_copies_x = QtWidgets.QSpinBox()
        self.spn_copies_x.setRange(1, 50)
        self.spn_copies_x.setValue(1)
        self.spn_copies_x.setToolTip(
            "Nombre de copies en X (1 = pas de copie). La sélection est\n"
            "répliquée en matrice au pas ci-dessous : n pièces identiques\n"
            "découpées en un seul job.")
        form.addRow("Copies en X :", self.spn_copies_x)

        self.spn_copies_y = QtWidgets.QSpinBox()
        self.spn_copies_y.setRange(1, 50)
        self.spn_copies_y.setValue(1)
        self.spn_copies_y.setToolTip("Nombre de copies en Y (1 = pas de copie).")
        form.addRow("Copies en Y :", self.spn_copies_y)

        self.spn_copy_dx = QtWidgets.QDoubleSpinBox()
        self.spn_copy_dx.setRange(1.0, 1000.0)
        self.spn_copy_dx.setValue(30.0)
        self.spn_copy_dx.setSuffix(" mm")
        self.spn_copy_dx.setToolTip(
            "Pas entre deux copies en X (d'origine à origine : prévoir la\n"
            "largeur de la pièce + un espace + le kerf).")
        form.addRow("Pas X :", self.spn_copy_dx)

        self.spn_copy_dy = QtWidgets.QDoubleSpinBox()
        self.spn_copy_dy.setRange(1.0, 1000.0)
        self.spn_copy_dy.setValue(30.0)
        self.spn_copy_dy.setSuffix(" mm")
        self.spn_copy_dy.setToolTip("Pas entre deux copies en Y.")
        form.addRow("Pas Y :", self.spn_copy_dy)

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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
        _combined_add_button(form, self._on_add_to_combined)

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

        self._last_fields = {
            "power": self.spn_power, "feed": self.spn_feed,
            "thickness": self.spn_thickness, "n_passes": self.spn_passes,
            "zoverride": self.chk_zoverride, "zstart": self.spn_zstart,
            "use_finish": self.chk_finish, "finish_feed": self.spn_finish_feed,
            "use_power_ramp": self.chk_power_ramp, "power_end": self.spn_power_end,
            "kerf": self.spn_kerf, "hole_first": self.chk_hole_first,
            "proximity": self.chk_proximity,
            "tab_count": self.spn_tab_count, "tab_length": self.spn_tab_length,
            "tab_height": self.spn_tab_height, "lead_in": self.spn_lead_in,
            "copies_x": self.spn_copies_x, "copies_y": self.spn_copies_y,
            "copy_dx": self.spn_copy_dx, "copy_dy": self.spn_copy_dy,
        }
        _restore_last_values("flat", self._last_fields)

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
        self.spn_tab_count.setValue(values.get("tab_count", self.spn_tab_count.value()))
        self.spn_tab_length.setValue(values.get("tab_length", self.spn_tab_length.value()))
        self.spn_tab_height.setValue(values.get("tab_height", self.spn_tab_height.value()))
        self.spn_lead_in.setValue(values.get("lead_in", self.spn_lead_in.value()))

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
            "tab_count": self.spn_tab_count.value(),
            "tab_length": self.spn_tab_length.value(),
            "tab_height": self.spn_tab_height.value(),
            "lead_in": self.spn_lead_in.value(),
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
            self._edges_for_job(), self.spn_power.value(), self.spn_feed.value(),
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
            tab_count=self.spn_tab_count.value(),
            tab_length=self.spn_tab_length.value(),
            tab_height=self.spn_tab_height.value(),
            lead_in_mm=self.spn_lead_in.value(),
        )

    def _edges_for_job(self):
        """Edges de la sélection, répliquées en matrice si des copies sont
        demandées -- partagé par accept, aperçus et estimation de durée."""
        return core.replicate_edges(
            self._edges, self.spn_copies_x.value(), self.spn_copies_y.value(),
            self.spn_copy_dx.value(), self.spn_copy_dy.value())

    def _update_duration_preview(self):
        if not self._edges:
            self.lbl_duration.setText("Durée estimée : -- (aucun segment dans la sélection)")
            return
        gcode = core.generate_gcode_flat_multipass(
            self._edges_for_job(), self.spn_power.value(), self.spn_feed.value(),
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
            self._edges_for_job(), self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            frame_only=True, **self._build_gcode_kwargs(),
        )
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_decoupe.ngc")

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        return {"type": "flat",
                "label": "Découpe multi-passes ({:.0f} passes, S{:.0f})".format(
                    self.spn_passes.value(), self.spn_power.value()),
                "params": dict(edges=self._edges_for_job(), power=self.spn_power.value(),
                               feed=self.spn_feed.value(), thickness=self.spn_thickness.value(),
                               n_passes=self.spn_passes.value(), **self._build_gcode_kwargs())}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        _save_last_values("flat", self._last_fields)
        pre_text = self.txt_pre.toPlainText()
        post_text = self.txt_post.toPlainText()

        FreeCAD.Console.PrintMessage("Chaînage des segments connectés...\n")
        gcode = core.generate_gcode_flat_multipass(
            self._edges_for_job(),
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

        _panel_header(form, "curved_cut.svg", "Découpe multi-passes (courbe)")
        _intro(form,
               "Découpe en plusieurs passes EN SUIVANT LE RELIEF d'une "
               "surface courbe. Sélectionne le motif projeté (Hachures_3D) "
               "ET le modèle 3D d'origine, les deux en même temps.",
               "Le modèle 3D permet une sonde exacte du relief. Chaque passe "
               "recule le foyer un peu plus DANS la matière (comme la découpe "
               "à plat : épaisseur / nombre de passes), tout en suivant le "
               "relief natif à chaque point du tracé. Compensation de kerf, "
               "ordre trous-avant-contour et optimisation par proximité "
               "disponibles comme à plat.")

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
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(0)
        self.spn_power.setToolTip(
            "Puissance du laser pendant la découpe (valeur S, selon\n"
            "l'échelle de la machine). Fixe pour toutes les passes, sauf si\n"
            "la rampe de puissance ci-dessous est activée.")
        form.addRow("Puissance (S 0-{:g}) :".format(core.S_MAX), self.spn_power)

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
        self.spn_zfocus.setValue(core.Z_WORK_MM)
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
        self.spn_marge.setValue(core.TRANSIT_MARGIN_MM)
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
        self.spn_power_end.setRange(0, core.S_MAX)
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

        _section(form, "G-code & aperçus", "sect_gcode.svg")
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
        _combined_add_button(form, self._on_add_to_combined)

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

        self._last_fields = {
            "power": self.spn_power, "feed": self.spn_feed,
            "z_focus": self.spn_zfocus, "marge": self.spn_marge,
            "thickness": self.spn_thickness, "n_passes": self.spn_passes,
            "use_finish": self.chk_finish, "finish_feed": self.spn_finish_feed,
            "use_power_ramp": self.chk_power_ramp, "power_end": self.spn_power_end,
            "kerf": self.spn_kerf, "hole_first": self.chk_hole_first,
            "proximity": self.chk_proximity,
        }
        _restore_last_values("curved_cut", self._last_fields)

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

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        return {"type": "curved_cut",
                "label": "Découpe courbe ({:.0f} passes, S{:.0f})".format(
                    self.spn_passes.value(), self.spn_power.value()),
                "params": dict(edges=self._edges, power=self.spn_power.value(),
                               feed=self.spn_feed.value(), thickness=self.spn_thickness.value(),
                               n_passes=self.spn_passes.value(), z_focus=self.spn_zfocus.value(),
                               marge_survol=self.spn_marge.value(), reference_shape=self._reference_shape,
                               probe=self._probe, **self._build_gcode_kwargs())}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def accept(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        _save_last_values("curved_cut", self._last_fields)
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
class TaskPanelCombined:
    def __init__(self):
        self.operations = _COMBINED_OPS

        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "combined.svg", "Job combiné")
        info = _WrapLabel(
            "Assemble plusieurs opérations en UN SEUL fichier -- un seul "
            "armement (M3) au début, un seul désarmement (M5)/M2 à la fin, "
            "exécutées dans l'ordre de la liste.")
        form.addRow(info)
        howto = _WrapLabel(
            "Pour AJOUTER une opération : ouvre son mode normal (Découpe, "
            "Marquage, Grille de test...), règle tout comme d'habitude, puis "
            "clique \u00ab \u2795 Ajouter au job combiné \u00bb dans ce mode. "
            "Reviens ici pour ordonner la liste et générer le fichier.")
        form.addRow(howto)

        self.list_ops = QtWidgets.QListWidget()
        self.list_ops.setToolTip("Opérations empilées, exécutées dans cet ordre.")
        form.addRow(self.list_ops)


        self.btn_move_up = QtWidgets.QPushButton("Monter l'opération sélectionnée")
        self.btn_move_up.clicked.connect(self._on_move_up)
        form.addRow(self.btn_move_up)

        self.btn_move_down = QtWidgets.QPushButton("Descendre l'opération sélectionnée")
        self.btn_move_down.clicked.connect(self._on_move_down)
        form.addRow(self.btn_move_down)

        self.btn_remove = QtWidgets.QPushButton("Supprimer l'opération sélectionnée")
        self.btn_remove.clicked.connect(self._on_remove)
        form.addRow(self.btn_remove)

        self.btn_clear = QtWidgets.QPushButton("Vider la liste")
        self.btn_clear.clicked.connect(self._on_clear)
        form.addRow(self.btn_clear)

        self.lbl_duration = _WrapLabel("Durée estimée : -- (aucune opération)")
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

    def _refresh_list(self):
        self.list_ops.clear()
        for i, op in enumerate(self.operations):
            self.list_ops.addItem("{}. {}".format(i + 1, op["label"]))
        self._update_duration_preview()

    def _on_clear(self):
        if not self.operations:
            return
        reply = QtWidgets.QMessageBox.question(
            self.form, "Vider",
            "Retirer toutes les opérations du job combiné ?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            del self.operations[:]
            self._refresh_list()

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

        core.ensure_laser_profiles()
        settings = core.current_settings()
        nozzle = core.current_nozzle()

        _panel_header(form, "settings.svg", "Préférences Atelier Laser")

        _section(form, "Laser actif", "sect_options.svg")
        _intro(form,
               "Chaque laser a son propre profil : numéro d'outil, calibration "
               "du point, Z de travail, échelle de puissance et profil du bec. "
               "Change de laser pour retrouver ses réglages.",
               "Les réglages MACHINE (dossier, broche, cinématique, sécurité) "
               "restent communs à tous les lasers. Pour ajouter un module (ex. "
               "un IR 1064 nm en T101 à côté du bleu en T100) : « Nouveau "
               "(cloner) » copie le laser courant, tu ajustes puis tu valides. "
               "Changer de laser dans la liste applique aussitôt son profil "
               "(valide d'abord si tu avais des modifications en cours). Le "
               "nuancier et les préréglages matériau restent pour l'instant "
               "communs à tous les lasers.")
        self.combo_laser = QtWidgets.QComboBox()
        self.combo_laser.setToolTip(
            "Laser dont les réglages sont affichés et édités ci-dessous.")
        self._refresh_laser_combo()
        self.combo_laser.currentIndexChanged.connect(self._on_laser_changed)
        form.addRow("Laser :", self.combo_laser)

        laser_btns = QtWidgets.QWidget()
        laser_btns_l = QtWidgets.QHBoxLayout(laser_btns)
        laser_btns_l.setContentsMargins(0, 0, 0, 0)
        btn_new_laser = QtWidgets.QPushButton("Nouveau (cloner)")
        btn_new_laser.setToolTip(
            "Crée un laser en copiant les réglages du laser courant\n"
            "(point de départ pour un 2e module à ajuster).")
        btn_new_laser.clicked.connect(self._new_laser)
        btn_rename_laser = QtWidgets.QPushButton("Renommer")
        btn_rename_laser.clicked.connect(self._rename_laser)
        btn_del_laser = QtWidgets.QPushButton("Supprimer")
        btn_del_laser.clicked.connect(self._delete_laser)
        laser_btns_l.addWidget(btn_new_laser)
        laser_btns_l.addWidget(btn_rename_laser)
        laser_btns_l.addWidget(btn_del_laser)
        form.addRow("", laser_btns)

        _section(form, "Sauvegarde & estimation", "sect_gcode.svg")
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

        _section(form, "Machine / G-code", "sect_options.svg")
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

        self.spn_laser_tool = QtWidgets.QSpinBox()
        self.spn_laser_tool.setRange(1, 999)
        self.spn_laser_tool.setValue(int(settings["laser_tool"]))
        self.spn_laser_tool.setToolTip(
            "Numéro (tool.tbl) de l'OUTIL LASER sur ta machine. Utilisé\n"
            "par la compensation G43 H<n> en tête de chaque job (prérequis\n"
            "T<n> M6) et par le Test des offsets X/Y. 100 par défaut --\n"
            "à adapter si ton laser est un autre outil de la table.")
        form.addRow("Numéro d'outil laser :", self.spn_laser_tool)

        self.spn_s_max = QtWidgets.QDoubleSpinBox()
        self.spn_s_max.setRange(1.0, 100000.0)
        self.spn_s_max.setDecimals(0)
        self.spn_s_max.setValue(settings["s_max"])
        self.spn_s_max.setToolTip(
            "Échelle de puissance de la broche laser : la valeur S qui\n"
            "correspond à la PLEINE puissance sur ta machine (dépend de la\n"
            "config broche LinuxCNC ; 1000 par défaut). Fixe le maximum de\n"
            "tous les champs de puissance de l'atelier et le plafond de la\n"
            "compensation de fluence. Les panneaux ouverts doivent être\n"
            "rouverts pour voir la nouvelle plage.")
        form.addRow("Échelle de puissance max (S) :", self.spn_s_max)

        self.spn_z_max_feed = QtWidgets.QDoubleSpinBox()
        self.spn_z_max_feed.setRange(10.0, 20000.0)
        self.spn_z_max_feed.setDecimals(0)
        self.spn_z_max_feed.setValue(settings["z_max_feed_mm_min"])
        self.spn_z_max_feed.setSuffix(" mm/min")
        self.spn_z_max_feed.setToolTip(
            "Vitesse max supposée de l'axe Z (MAX_VELOCITY de l'axe dans\n"
            "LinuxCNC). Sert uniquement à AVERTIR quand un trait en Vague\n"
            "défocus demanderait plus vite (le trajet serait alors ralenti\n"
            "par la machine). N'affecte jamais le G-code.")
        form.addRow("Vitesse Z max (avertissement) :", self.spn_z_max_feed)

        self.spn_accel = QtWidgets.QDoubleSpinBox()
        self.spn_accel.setRange(10.0, 20000.0)
        self.spn_accel.setDecimals(0)
        self.spn_accel.setValue(settings["accel_mm_s2"])
        self.spn_accel.setSuffix(" mm/s2")
        self.spn_accel.setToolTip(
            "Accélération machine supposée, pour l'estimation de durée\n"
            "(profil trapézoïdal par course : chaque départ/arrêt paie son\n"
            "accélération -- décisif sur les remplissages faits de milliers\n"
            "de traits courts). Mettre la MAX_ACCELERATION des axes X/Y de\n"
            "ton LinuxCNC. N'affecte jamais le G-code.")
        form.addRow("Accélération (estimation) :", self.spn_accel)

        _section(form, "Calibration du point (défocus)", "sect_focus.svg")
        lbl_calib = _WrapLabel(
            "Propriété machine, mesurée UNE FOIS avec la Bande de\n"
            "calibration défocus : brûle deux points test (au foyer, puis à\n"
            "un défocus connu) et mesure leur diamètre. Utilisée par\n"
            "Hachures 2D, Gravure remplie, Grille de test et le style\n"
            "Vague -- plus rien à resaisir dans les panneaux.")
        form.addRow(lbl_calib)
        _diagram(form, "diag_defocus.svg")

        self.spn_spot_focus = QtWidgets.QDoubleSpinBox()
        self.spn_spot_focus.setRange(0.01, 20.0)
        self.spn_spot_focus.setDecimals(3)
        self.spn_spot_focus.setValue(settings["spot_focus_mm"])
        self.spn_spot_focus.setSuffix(" mm")
        self.spn_spot_focus.setToolTip(
            "Diamètre du point laser AU FOYER (trait le plus fin de la\n"
            "bande de calibration). À MESURER réellement.")
        form.addRow("Point au foyer (mesuré) :", self.spn_spot_focus)

        self.spn_spot_zdefocus = QtWidgets.QDoubleSpinBox()
        self.spn_spot_zdefocus.setRange(0.1, 60.0)
        self.spn_spot_zdefocus.setDecimals(2)
        self.spn_spot_zdefocus.setValue(settings["spot_test_defocus_mm"])
        self.spn_spot_zdefocus.setSuffix(" mm")
        self.spn_spot_zdefocus.setToolTip(
            "Défocus de test de la 2e mesure : hauteur AU-DESSUS du foyer\n"
            "d'un trait nettement plus large de la bande de calibration.")
        form.addRow("Défocus de test :", self.spn_spot_zdefocus)

        self.spn_spot_dtest = QtWidgets.QDoubleSpinBox()
        self.spn_spot_dtest.setRange(0.01, 30.0)
        self.spn_spot_dtest.setDecimals(3)
        self.spn_spot_dtest.setValue(settings["spot_test_diameter_mm"])
        self.spn_spot_dtest.setSuffix(" mm")
        self.spn_spot_dtest.setToolTip("Diamètre du point mesuré à ce défocus de test.")
        form.addRow("Point au défocus de test :", self.spn_spot_dtest)

        _section(form, "Z de travail par défaut", "sect_zheight.svg")
        self.spn_zwork_default = QtWidgets.QDoubleSpinBox()
        self.spn_zwork_default.setRange(-50.0, 200.0)
        self.spn_zwork_default.setDecimals(2)
        self.spn_zwork_default.setValue(settings["z_work_mm"])
        self.spn_zwork_default.setSuffix(" mm")
        self.spn_zwork_default.setToolTip(
            "Z de travail (foyer) PROPOSÉ PAR DÉFAUT dans tous les\n"
            "panneaux -- avec le zéro Z sur la surface de la pièce, c'est\n"
            "la focale du nez laser, une propriété machine. Chaque panneau\n"
            "reste modifiable au cas par cas (et retient sa dernière\n"
            "valeur).")
        form.addRow("Z de travail (foyer) :", self.spn_zwork_default)

        self.spn_transit_default = QtWidgets.QDoubleSpinBox()
        self.spn_transit_default.setRange(0.0, 100.0)
        self.spn_transit_default.setDecimals(1)
        self.spn_transit_default.setValue(settings["transit_margin_mm"])
        self.spn_transit_default.setSuffix(" mm")
        self.spn_transit_default.setToolTip(
            "Marge de survol PROPOSÉE PAR DÉFAUT dans les modes de\n"
            "marquage (au-dessus du Z de travail / du relief pour les\n"
            "transits). 0 = transits à plat, recommandé sur pièce plate.")
        form.addRow("Marge de survol (marquage) :", self.spn_transit_default)

        _section(form, "Sécurité découpe", "sect_safety.svg")
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

        _section(form, "Profil du bec (anti-collision)", "sect_focus.svg")
        lbl_nozzle = _WrapLabel(
            "Profil du bec (contrôle anti-collision des modes sur surface\n"
            "courbe). Tube droit : bas = haut = diamètre du tube. Section\n"
            "rectangulaire : entrer la diagonale.")
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

        lbl = _WrapLabel(
            "Enregistré dans laser_atelier_config.json et appliqué\n"
            "immédiatement (les panneaux déjà ouverts gardent leurs\n"
            "infobulles d'origine).")
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

    def _refresh_laser_combo(self):
        self.combo_laser.blockSignals(True)
        self.combo_laser.clear()
        for lid, name in core.laser_profiles():
            self.combo_laser.addItem(name, lid)
        idx = self.combo_laser.findData(core.active_laser_id())
        if idx >= 0:
            self.combo_laser.setCurrentIndex(idx)
        self.combo_laser.blockSignals(False)

    def _reload_active_laser_fields(self):
        """Recharge les champs PAR laser après une bascule de profil."""
        s = core.current_settings()
        n = core.current_nozzle()
        self.spn_laser_tool.setValue(int(s["laser_tool"]))
        self.spn_s_max.setValue(s["s_max"])
        self.spn_frame_power.setValue(s["frame_power"])
        self.spn_spot_focus.setValue(s["spot_focus_mm"])
        self.spn_spot_zdefocus.setValue(s["spot_test_defocus_mm"])
        self.spn_spot_dtest.setValue(s["spot_test_diameter_mm"])
        self.spn_zwork_default.setValue(s["z_work_mm"])
        self.spn_nozzle_bottom.setValue(n["bottom_diameter_mm"])
        self.spn_nozzle_top.setValue(n["top_diameter_mm"])
        self.spn_nozzle_height.setValue(n["height_mm"])

    def _on_laser_changed(self, idx):
        lid = self.combo_laser.itemData(idx)
        if lid and core.set_active_laser(lid):
            self._reload_active_laser_fields()

    def _new_laser(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Nouveau laser",
            "Nom du nouveau laser (copie du laser courant) :", text="IR 1064 nm")
        if not ok or not name.strip():
            return
        lid = core.add_laser(name.strip(), clone_from=core.active_laser_id())
        core.set_active_laser(lid)
        self._refresh_laser_combo()
        self._reload_active_laser_fields()

    def _rename_laser(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Renommer le laser", "Nouveau nom :",
            text=core.active_laser_name())
        if ok and name.strip():
            core.rename_laser(core.active_laser_id(), name.strip())
            self._refresh_laser_combo()

    def _delete_laser(self):
        if len(core.laser_profiles()) <= 1:
            QtWidgets.QMessageBox.information(
                self.form, "Suppression impossible",
                "Il faut garder au moins un laser.")
            return
        name = core.active_laser_name()
        if QtWidgets.QMessageBox.question(
                self.form, "Supprimer le laser",
                "Supprimer le profil du laser « {} » ?\n(les réglages machine "
                "communs ne sont pas touchés)".format(name),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return
        core.delete_laser(core.active_laser_id())
        self._refresh_laser_combo()
        self._reload_active_laser_fields()

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
            "laser_tool": self.spn_laser_tool.value(),
            "s_max": self.spn_s_max.value(),
            "rapid_feed_mm_min": self.spn_rapid.value(),
            "z_max_feed_mm_min": self.spn_z_max_feed.value(),
            "accel_mm_s2": self.spn_accel.value(),
            "spot_focus_mm": self.spn_spot_focus.value(),
            "spot_test_defocus_mm": self.spn_spot_zdefocus.value(),
            "spot_test_diameter_mm": self.spn_spot_dtest.value(),
            "z_work_mm": self.spn_zwork_default.value(),
            "transit_margin_mm": self.spn_transit_default.value(),
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
