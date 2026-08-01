# -*- coding: utf-8 -*-
"""task_panels.py -- panneaux de tâches (Tasks) de l'Atelier Laser.
© Atelier du Verdier -- licence LGPL-2.1-or-later (cf. LICENSE).

Un panneau par mode, affiché dans le panneau des tâches (dock à gauche,
non-bloquant -- on peut tourner la vue 3D pendant qu'il reste ouvert) via
FreeCADGui.Control.showDialog, à la place des pages de l'ancienne boîte de
dialogue modale (QDialog) de la macro. Toute la logique de calcul reste
dans laser_core.py ; ces classes se contentent de lire les widgets et
d'appeler les fonctions correspondantes.

Contrat des panneaux FreeCAD (Gui::TaskView) : accept()/reject() qui
renvoient False laissent le panneau ouvert (utilisé ici pour les erreurs
de validation, afin de ne pas perdre la saisie de l'utilisateur)."""

import json
import math
import os
import re
import subprocess
import tempfile
import time
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


def _btn_icon(btn, name, size=18):
    """Pose une icône SVG carrée sur un bouton (silencieux si le rendu
    échoue -- le bouton garde alors juste son texte). Renvoie le bouton."""
    try:
        ic = _icon(name)
        if ic is not None and not ic.isNull():
            btn.setIcon(ic)
            btn.setIconSize(QtCore.QSize(size, size))
    except Exception:
        pass
    return btn


# Correspondance libellé -> icône, testée dans l'ordre (première clé trouvée
# dans le texte du bouton = gagne). Sert à l'assigneur automatique ci-dessous :
# tous les boutons d'un panneau reçoivent une icône, sans avoir à la poser à
# la main sur chacun.
_BTN_ICON_MAP = [
    (("aperçu du trajet", "aperçu des points"), "btn_view3d.svg"),
    (("aperçu photo",), "sect_photo.svg"),
    (("aperçu cadrage", "cadrage"), "btn_frame.svg"),
    (("supprimer", "vider"), "btn_delete.svg"),
    (("générer et sauvegarder", "g-code"), "sect_gcode.svg"),
    (("reprendre la sélection",), "btn_reselect.svg"),
    (("exporter",), "btn_export.svg"),
    (("importer",), "btn_import.svg"),
    (("actualiser",), "btn_refresh.svg"),
    (("monter",), "btn_up.svg"),
    (("descendre",), "btn_down.svg"),
    (("renommer",), "btn_edit.svg"),
    (("calculer",), "btn_calc.svg"),
    (("appliquer",), "btn_apply.svg"),
    (("mesures", "calibration"), "sect_measure.svg"),
    (("mire", "planche"), "sect_labels.svg"),
    (("png",), "sect_photo.svg"),
    (("nouveau", "cloner"), "btn_add.svg"),
    (("ajouter",), "btn_add.svg"),
    (("photo",), "sect_photo.svg"),
    (("sauvegarder", "préréglage"), "sect_preset.svg"),
    (("depuis la face",), "btn_face.svg"),
    (("parcourir",), "btn_folder.svg"),
    (("auto",), "sect_options.svg"),
]


def _auto_icon_buttons(root):
    """Pose une icône adaptée sur CHAQUE bouton d'un panneau, d'après son
    libellé (table `_BTN_ICON_MAP`). Saute les boutons déjà iconés (aperçus
    icône seule, boutons réglés à la main) et ceux sans texte. Idempotent ;
    appelé à l'ouverture de chaque panneau (voir commands._show)."""
    try:
        boutons = root.findChildren(QtWidgets.QPushButton)
    except Exception:
        return
    for btn in boutons:
        try:
            if not btn.icon().isNull():
                continue
            txt = (btn.text() or "").strip().lower()
            if not txt:
                continue
            for cles, nom in _BTN_ICON_MAP:
                if any(c in txt for c in cles):
                    _btn_icon(btn, nom)
                    if nom == "btn_add.svg":
                        # le « + » / « ➕ » de tête fait doublon avec l'icône
                        t = btn.text()
                        for p in ("➕ ", "➕", "+ ", "+"):
                            if t.startswith(p):
                                btn.setText(t[len(p):].lstrip())
                                break
                    break
        except Exception:
            continue


def _preview_row(form, boutons_icones, taille=24):
    """Range des boutons d'APERÇU VISUEL en icônes seules, sur une même ligne
    pleine largeur et sans libellé de ligne. `boutons_icones` : liste de
    (bouton, nom_icone) ; chaque bouton s'étire pour occuper sa part de la
    largeur (deux aperçus -> 50/50, un seul -> pleine largeur). Le libellé
    passe en info-bulle (déjà posée par l'appelant)."""
    ligne = QtWidgets.QWidget()
    h = QtWidgets.QHBoxLayout(ligne)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    for btn, nom in boutons_icones:
        btn.setText("")
        _btn_icon(btn, nom, taille)
        btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        btn.setMinimumHeight(30)
        h.addWidget(btn)
    form.addRow(ligne)
    return ligne


def _gcode_editor(placeholder="", hauteur=76):
    """Éditeur de G-code personnalisé (avant / après le job) : police à chasse
    fixe (le code s'aligne), pas de retour à la ligne automatique (une ligne
    G-code = une ligne), et un peu plus haut qu'un simple champ pour voir
    plusieurs lignes d'un coup."""
    ed = QtWidgets.QPlainTextEdit()
    ed.setPlaceholderText(placeholder)
    ed.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    police = QtGui.QFont("monospace")
    police.setStyleHint(QtGui.QFont.Monospace)
    ed.setFont(police)
    ed.setMinimumHeight(hauteur)
    ed.setMaximumHeight(hauteur + 70)
    try:
        ed.setTabStopDistance(4 * ed.fontMetrics().horizontalAdvance(" "))
    except Exception:
        pass
    return ed


def _signature_selection(selection):
    """Empreinte comparable d'une sélection : (objet, sous-éléments). Sert
    à savoir si la vue 3D montre autre chose que ce que le panneau tient,
    SANS toucher à la géométrie -- c'est un simple relevé de noms."""
    sig = []
    for so in (selection or []):
        try:
            sig.append((getattr(so.Object, "Name", "?"),
                        tuple(getattr(so, "SubElementNames", ()) or ())))
        except Exception:
            sig.append(("?", ()))
    return tuple(sorted(sig))


def _reselect_button(form, on_reselect, selection_courante=None):
    """Bouton « Reprendre la sélection de la vue » : un panneau ne capture la
    sélection qu'à son OUVERTURE ; ce bouton relit la sélection courante.
    `on_reselect` est le rappel propre au panneau (relit + rafraîchit).

    `selection_courante` : rappel rendant la sélection que le panneau tient
    aujourd'hui. Fourni, une ligne d'état S'ANNONCE dès que la vue 3D montre
    autre chose -- le bouton existait depuis longtemps mais restait un bouton
    parmi d'autres, et l'atelier a redemandé la fonction sans l'avoir vu
    (31/07/2026). Le relevé ne lit que des NOMS d'objets, jamais la
    géométrie : le rafraîchir en continu ne coûte rien."""
    btn = QtWidgets.QPushButton("Reprendre la sélection de la vue")
    _btn_icon(btn, "btn_reselect.svg")
    btn.setToolTip(
        "Le panneau capture la sélection à son OUVERTURE. Si tu as\n"
        "sélectionné le motif APRÈS, clique ici pour reprendre la\n"
        "sélection courante de la vue / de l'arbre.\n"
        "\n"
        "Tes réglages en cours ne sont PAS remplacés : seule la géométrie\n"
        "à graver change.")
    btn.clicked.connect(on_reselect)

    if selection_courante is None:
        form.addRow(btn)
        return btn

    lbl = _WrapLabel("")
    form.addRow(lbl)
    form.addRow(btn)

    def _etat():
        try:
            vue = Gui.Selection.getSelectionEx()
        except Exception:
            return
        n = len(vue or [])
        if _signature_selection(vue) == _signature_selection(selection_courante()):
            lbl.setText("<span style=\"color:#5a626e\">Sélection 3D : "
                        "identique à celle du panneau.</span>")
            btn.setEnabled(False)
        else:
            lbl.setText(
                "<span style=\"color:#c62828\">Sélection 3D : <b>{}</b> "
                "\u2014 différente de celle du panneau.</span>".format(
                    "{} objet{}".format(n, "s" if n > 1 else "")
                    if n else "vide"))
            btn.setEnabled(True)

    minuteur = QtCore.QTimer(btn)
    minuteur.timeout.connect(_etat)
    minuteur.start(600)
    _etat()
    return btn


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
        self._ajuster_hauteur()

    def _ajuster_hauteur(self):
        # QFormLayout n'honore pas le heightForWidth des labels repliés :
        # la rangée reste à la hauteur d'UNE ligne et les paragraphes se
        # chevauchent/se rognent. On force donc la hauteur minimale à la
        # hauteur réelle du texte replié à la largeur COURANTE. Avant
        # affichage (largeur nulle), heightForWidth renverrait une hauteur
        # aberrante -> on ne fait rien tant que la largeur n'est pas connue.
        w = self.width()
        if w <= 0:
            return
        try:
            h = self.heightForWidth(w)
        except RuntimeError:
            return  # widget C++ déjà détruit (timer différé)
        if h <= 0 or h == self.minimumHeight():
            return
        self.setMinimumHeight(h)
        # updateGeometry() se contente d'INVALIDER le layout parent -- Qt ne
        # le recalcule qu'au tour de boucle suivant (LayoutRequest posté),
        # d'où le flash de chevauchement vu à l'écran : la rangée reste à
        # l'ancienne hauteur un instant avant de se corriger toute seule.
        # On force la 2e passe ICI, tout de suite (le parent connaît déjà
        # notre nouvelle hauteur minimale) : le chevauchement n'est alors
        # jamais peint du tout, quelle que soit la cause du redimensionnement
        # (dépliage de section, barre de défilement, redimensionnement de
        # la fenêtre...).
        self.updateGeometry()
        parent = self.parentWidget()
        lay = parent.layout() if parent is not None else None
        if lay is not None:
            try:
                lay.activate()
            except RuntimeError:
                pass

    def _hauteur_repliee(self, hint):
        # Hauteur du paragraphe replié à la largeur COURANTE. QFormLayout
        # dimensionne la rangée d'après sizeHint()/minimumSizeHint() (et
        # IGNORE heightForWidth) : si on laisse le sizeHint d'origine (calculé
        # pour une seule ligne), la rangée est trop basse et le widget suivant
        # se superpose. On corrige donc la hauteur annoncée.
        w = self.width()
        if w <= 0:
            return hint
        try:
            h = self.heightForWidth(w)
        except RuntimeError:
            return hint
        return QtCore.QSize(hint.width(), h) if h > 0 else hint

    def sizeHint(self):
        return self._hauteur_repliee(super().sizeHint())

    def minimumSizeHint(self):
        return self._hauteur_repliee(super().minimumSizeHint())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajuster_hauteur()

    def showEvent(self, event):
        # À la 1re apparition (section dépliée, barre de défilement qui
        # rétrécit la largeur utile), la largeur définitive n'est connue
        # qu'au tour de boucle suivant : on recalcule alors la hauteur,
        # sinon la rangée reste dimensionnée pour une largeur trop grande
        # et le widget suivant se superpose au bas du paragraphe.
        super().showEvent(event)
        self._ajuster_hauteur()
        QtCore.QTimer.singleShot(0, self._ajuster_hauteur)
        # 2e passe après stabilisation (apparition/disparition de la barre de
        # défilement quand une section se déplie) -> largeur définitive.
        QtCore.QTimer.singleShot(120, self._ajuster_hauteur)


def _calibration_banner(form, mode_titre):
    """Bandeau ★ toujours visible en tête d'un mode de calibration : il situe
    ce mode dans le PARCOURS DE PREMIÈRE CALIBRATION (numéro d'étape + le
    préréglage d'usine à charger + où reporter le résultat). Pensé pour le
    nouvel utilisateur qui a plein de préréglages sous la main mais ne sait
    pas par où commencer. Ne fait rien si le mode n'est pas dans le parcours."""
    etape = core.calibration_step_for(mode_titre)
    if etape is None:
        return
    # La portée (laser/matériau) est LE point à clarifier ici : sans elle,
    # « Étape 3/4 » donne l'impression fausse qu'un nouveau matériau oblige
    # à repasser par les étapes 1 et 2 (qui, elles, sont propres au laser).
    portee = ("une fois pour ce laser, jamais à refaire pour un nouveau matériau"
              if etape["portee"] == "laser"
              else "à refaire pour CHAQUE matériau (les étapes 1-2 ne le sont pas)")
    if etape["n"] is None:
        tete = "★ Complément -- {}".format(portee)
    else:
        total = len(core.calibration_numbered_steps())
        tete = "★ Étape {}/{} -- {}".format(etape["n"], total, portee)
    # Conteneur VBox : QFormLayout n'honore pas le heightForWidth d'un label
    # replié posé en rangée directe (rangée trop basse) -- le conteneur, lui,
    # propage la hauteur repliée. Cf. _make_fluence_widgets.
    intro = _WrapLabel(
        "<b><span style=\"color:#ff8a00\">{tete}.</span></b> Pour {but}"
        "&nbsp;:".format(tete=tete, but=etape["but"]))
    holder = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(holder)
    lay.setContentsMargins(0, 2, 0, 2)
    lay.setSpacing(0)
    lay.addWidget(intro)
    form.addRow(holder)

    actions = etape["action"]
    if len(actions) > 1:
        # Plusieurs actions distinctes -- jamais aplaties dans une seule
        # phrase (cf. _bullet_list) : une ligne numérotée par action.
        _bullet_list(form, ["<b>{}.</b> {}".format(i + 1, a)
                            for i, a in enumerate(actions)])
        suite = "Grave sur une chute, mesure, puis reporte dans"
    else:
        suite = "{}, grave sur une chute, mesure, puis reporte dans".format(actions[0])
    outro = _WrapLabel(
        "{suite} <b>{reporter}</b>. Le parcours complet est dans le "
        "<b>Guide rapide</b>.".format(suite=suite, reporter=etape["reporter"]))
    holder2 = QtWidgets.QWidget()
    lay2 = QtWidgets.QVBoxLayout(holder2)
    lay2.setContentsMargins(0, 0, 0, 6)
    lay2.setSpacing(0)
    lay2.addWidget(outro)
    form.addRow(holder2)
    _hline(form)
    # Le conteneur VBox suffit dans la plupart des cas, mais un texte plus
    # long (ex. la précision "à refaire pour CHAQUE matériau") peut encore
    # être replié à une largeur provisoire avant que le panneau ait sa
    # largeur réelle -- même symptôme et même remède que _activer_sections
    # (_toggle) : un recalage différé une fois la largeur définitive connue.
    inner = form.parentWidget()
    if inner is not None:
        QtCore.QTimer.singleShot(
            0, lambda w=inner: (w.layout().activate(), w.layout().activate(),
                                 w.adjustSize()))


def _verrou(form, champs, titre="Verrouiller les résultats"):
    """Case « 🔒 <titre> » COCHÉE PAR DÉFAUT, à placer dans une section de
    saisie de mesures : tant qu'elle est cochée, les `champs` (les valeurs
    mesurées) sont en LECTURE SEULE, pour ne pas les modifier par accident
    (la molette est déjà neutralisée globalement par _neutraliser_molette ;
    ceci bloque en plus le clic et la frappe). Décocher pour corriger.
    Accepte aussi un TABLEAU (édition UI bloquée, les déclencheurs d'origine
    sont restaurés au déverrouillage) et des BOUTONS (désactivés) -- le
    remplissage programmatique (setValue/setItem...) reste possible.
    Renvoie la case, pour la relire au besoin."""
    chk = QtWidgets.QCheckBox("🔒 " + titre)
    chk.setChecked(True)
    chk.setToolTip(
        "Coché (par défaut) : les valeurs mesurées sont protégées en\n"
        "lecture seule. Décoche pour corriger une saisie.")
    declencheurs0 = {id(w): w.editTriggers() for w in champs
                     if isinstance(w, QtWidgets.QAbstractItemView)}

    def _appliquer(verrouille):
        for w in champs:
            if isinstance(w, (QtWidgets.QAbstractSpinBox, QtWidgets.QLineEdit)):
                w.setReadOnly(verrouille)
            elif isinstance(w, QtWidgets.QComboBox):
                w.setEnabled(not verrouille)
            elif isinstance(w, QtWidgets.QAbstractItemView):
                w.setEditTriggers(
                    QtWidgets.QAbstractItemView.NoEditTriggers if verrouille
                    else declencheurs0[id(w)])
            elif isinstance(w, QtWidgets.QAbstractButton):
                w.setEnabled(not verrouille)

    chk.toggled.connect(_appliquer)
    _appliquer(True)
    form.addRow(chk)
    return chk


class _GrilleResultats(QtWidgets.QGroupBox):
    """Grille de saisie de mesures « ligne x colonne -> valeur » pour une planche
    de test (ex. largeur brûlée par S et F). Une QDoubleSpinBox par croisement,
    en-têtes de ligne/colonne, molette neutralisée (_neutraliser_molette) et
    verrou « 🔒 Verrouiller les résultats » COCHÉ PAR DÉFAUT intégrés (les valeurs
    mesurées sont protégées en lecture seule tant qu'il est coché). « — » = non
    mesuré. values() renvoie {(ligne, colonne): valeur} des cellules saisies ;
    set_values() recharge depuis un tel dict (setValue reste possible verrouillé).

    `caseFocus` est émis quand une cellule prend le focus. La grille sert donc
    aussi de FILTRE D'ÉVÉNEMENTS sur ses propres cases : c'est ce qui permet à
    « Mesurer A → B » de savoir quelle case remplir, sans brancher de filtre
    global sur l'application -- dont la durée de vie déborderait celle du
    panneau."""

    caseFocus = QtCore.Signal(object)

    def __init__(self, titre, rows, cols, row_fmt="S{:.0f}", col_fmt="F{:.0f}",
                 decimals=2, maxi=10.0, pas=0.01, parent=None):
        super().__init__("", parent)
        self._row_fmt, self._col_fmt = row_fmt, col_fmt
        # Cadre neutre : la mise en évidence vient de la barre de titre
        # ci-dessous, pas du QGroupBox natif (son ::title ne peut pas
        # s'étirer sur toute la largeur -- il restait collé au coin,
        # comme tronqué).
        self.setStyleSheet(
            "QGroupBox { border: 1px solid #ff8a00; border-radius: 6px; }")
        self._rows = [float(r) for r in rows]
        self._cols = [float(c) for c in cols]
        self._cells = {}
        g = QtWidgets.QGridLayout(self)
        # Barre de titre pleine largeur (même teinte orange que les sections
        # d'étape _SectionHeader._etape) : dans « ② Entrer les mesures »,
        # plusieurs grilles se suivent (foyer, défocus 15/36 mm) et doivent
        # se distinguer d'un coup d'œil, pas se fondre dans le reste du
        # panneau -- ni ressembler à une étiquette tronquée dans un coin.
        lbl_titre = QtWidgets.QLabel(titre)
        lbl_titre.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #ff8a00;"
            "background-color: rgba(255, 138, 0, 0.16);"
            "border: 1px solid #ff8a00; border-radius: 4px;"
            "padding: 8px 10px 6px 10px;")
        g.addWidget(lbl_titre, 0, 0, 1, len(self._cols) + 1)
        for j, c in enumerate(self._cols):
            g.addWidget(QtWidgets.QLabel(col_fmt.format(c)), 1, j + 1)
        for i, r in enumerate(self._rows):
            g.addWidget(QtWidgets.QLabel(row_fmt.format(r)), i + 2, 0)
            for j, c in enumerate(self._cols):
                sp = QtWidgets.QDoubleSpinBox()
                sp.setRange(0.0, maxi)
                sp.setDecimals(decimals)
                sp.setSingleStep(pas)
                sp.setSpecialValueText("—")
                sp.installEventFilter(self)
                g.addWidget(sp, i + 2, j + 1)
                self._cells[(r, c)] = sp
        self._chk = QtWidgets.QCheckBox("🔒 Verrouiller les résultats")
        self._chk.setChecked(True)
        self._chk.setToolTip(
            "Coché (par défaut) : les valeurs mesurées sont protégées en\n"
            "lecture seule. Décoche pour saisir ou corriger.")
        self._chk.toggled.connect(self._appliquer_verrou)
        g.addWidget(self._chk, len(self._rows) + 2, 0, 1, len(self._cols) + 1)
        self._appliquer_verrou(True)
        _neutraliser_molette(self)

    def _appliquer_verrou(self, verrouille):
        for sp in self._cells.values():
            sp.setReadOnly(verrouille)

    def eventFilter(self, obj, ev):
        if ev.type() == QtCore.QEvent.FocusIn and obj in self._cells.values():
            self.caseFocus.emit(obj)
        return False

    def nom_case(self, sp):
        """« S1000 / F800 » pour cette cellule, ou None si elle n'est pas
        d'ici. Sert à NOMMER la case visée par une mesure : voir la cible
        écrite noir sur blanc vaut mieux que de la déduire d'un cadre de
        focus qu'on ne regarde pas."""
        for (r, c), w in self._cells.items():
            if w is sp:
                return "{} / {}".format(self._row_fmt.format(r),
                                        self._col_fmt.format(c))
        return None

    def cells(self):
        """Dict {(ligne, colonne): QDoubleSpinBox}."""
        return self._cells

    def contient(self, sp):
        """Cette cellule est-elle une des miennes ?"""
        return any(w is sp for w in self._cells.values())

    def values(self):
        """{(ligne, colonne): valeur} des cellules saisies (> 0 ; « — » ignoré)."""
        return {k: sp.value() for k, sp in self._cells.items() if sp.value() > 0}

    def set_values(self, data):
        """Recharge depuis {(ligne, colonne): valeur} ; absent/0 -> « — »."""
        for sp in self._cells.values():
            sp.setValue(0.0)
        for cle, v in (data or {}).items():
            sp = self._cells.get((float(cle[0]), float(cle[1])))
            if sp is not None:
                sp.setValue(float(v))


class _BlocMesure(QtWidgets.QWidget):
    """Bouton « Mesurer A → B » + son message + le mode de mesure, placé SOUS
    CHAQUE grille.

    Un seul bloc en bas du panneau obligeait à faire défiler la fenêtre entre
    chaque valeur, la grille du haut et le bouton ne tenant pas ensemble à
    l'écran (constaté à l'établi le 01/08/2026, après une seule séance de
    saisie). Le bouton doit être là où sont les cases.

    Les cases mesurées sont hautes de quelques millimètres et larges de
    centaines : le bloc affiche donc son message juste au-dessous, là où
    l'oeil est déjà."""

    def __init__(self, on_mesurer, on_perp, parent=None):
        super().__init__(parent)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 2, 0, 8)
        v.setSpacing(2)
        self.btn = QtWidgets.QPushButton("Mesurer A → B dans la vue 3D")
        # NoFocus : le bouton ne vole pas le cadre de focus à la case, qui
        # reste ainsi visiblement désignée pendant toute la mesure.
        self.btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn.setToolTip(
            "Clique d'abord la CASE à remplir, puis ce bouton, puis les deux\n"
            "bords à mesurer dans la vue 3D. La valeur est écrite dans la case.\n"
            "\n"
            "MOYENNE : mesures successives sur la MÊME case = moyenne\n"
            "courante, avec l'étendue entre elles. Un trait gravé n'a pas des\n"
            "bords droits (le grain décide), donc trois mesures à des endroits\n"
            "différents valent mieux qu'une. Re-cliquer la case repart de zéro.\n"
            "\n"
            "ZOOME avant de pointer : à l'écran un clic vaut ~1 pixel, soit\n"
            "0,16 mm si toute la planche tient dans la fenêtre -- la moitié\n"
            "d'un trait de 0,30.\n"
            "\n"
            "Re-cliquer le bouton annule une mesure en cours.")
        self.btn.clicked.connect(lambda: on_mesurer(self))
        v.addWidget(self.btn)
        self.chk_perp = QtWidgets.QCheckBox(
            "Mesurer en travers du trait (ignorer le décalage latéral)")
        self.chk_perp.setChecked(True)
        self.chk_perp.setToolTip(
            "COCHÉ (recommandé) : seule la composante PERPENDICULAIRE au trait\n"
            "est retenue -- la plus grande de dx et dy. Un trait horizontal se\n"
            "mesure en dy, un trait vertical en dx.\n"
            "\n"
            "Pourquoi ça compte : la distance directe A→B vaut hypot(dx, dy),\n"
            "donc elle est TOUJOURS plus grande que la largeur réelle dès que\n"
            "les deux clics ne sont pas l'un au-dessus de l'autre. Sur un trait\n"
            "de 0,30 mm, 0,20 mm de décalage latéral donne 0,36 -- 20 % de trop,\n"
            "et rien ne le signale.\n"
            "\n"
            "DÉCOCHÉ : vraie distance A→B, pour mesurer autre chose qu'une\n"
            "largeur (une diagonale, un entraxe).\n"
            "\n"
            "Les deux valeurs sont toujours affichées dans le message.")
        self.chk_perp.toggled.connect(on_perp)
        v.addWidget(self.chk_perp)
        self.lbl = _WrapLabel("")
        v.addWidget(self.lbl)


def _cotes_mire_defaut(planche):
    """Cotes de la mire que le générateur ACTUEL produirait pour cette
    planche, lues dans l'en-tête du G-code qu'il sort. Proposées à
    l'utilisateur, jamais imposées : la planche qu'il a en main peut avoir
    été gravée avant une évolution de la mise en page, et ses vraies cotes
    sont GRAVÉES dessus."""
    gen = {"planche1": core.generate_gcode_planche_focus,
           "planche2": core.generate_gcode_planche_defocus}.get(planche)
    if gen is None:
        return "140-60"
    try:
        m = re.search(r"rectangle de ([\d.]+) x ([\d.]+) mm",
                      gen(quiet=True) or "")
        return "{:.0f}-{:.0f}".format(float(m.group(1)), float(m.group(2))) if m else "140-60"
    except Exception:
        return "140-60"


def _python_systeme():
    """Interpréteur SYSTÈME, pas celui de FreeCAD.

    Le redressement passe par OpenCV, qui n'existe PAS dans le python
    embarqué de l'AppImage FreeCAD. On sous-traite donc à /usr/bin/python3,
    ce qui a l'avantage de ne rien ajouter aux dépendances du workbench."""
    for c in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if os.path.exists(c):
            return c
    return None


# Variables que l'AppImage FreeCAD impose à tout son environnement et qui
# EMPOISONNENT un python système lancé depuis elle.
#
# PYTHONHOME est la plus brutale : le python du système va alors chercher
# sa bibliothèque standard dans l'AppImage et meurt sur « No module named
# 'encodings' » avant même d'exécuter une ligne (constaté le 01/08/2026 au
# premier clic sur le bouton). Les variables Qt et LD_LIBRARY_PATH sont
# tout aussi importantes ici : OpenCV 5 ouvre sa fenêtre avec Qt6, et lui
# faire charger les Qt de l'AppImage au lieu de celles du système est le
# genre de mélange qui plante sans message utile.
_VARS_APPIMAGE = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE",
                  "LD_LIBRARY_PATH", "LD_PRELOAD", "QT_PLUGIN_PATH",
                  "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH")


def _env_systeme_propre():
    """Environnement débarrassé de ce que l'AppImage a injecté, pour lancer
    un vrai processus système."""
    env = dict(os.environ)
    for cle in _VARS_APPIMAGE:
        env.pop(cle, None)
    return env


def _importer_image_a_l_echelle(chemin, largeur_mm, hauteur_mm):
    """Pose l'image redressée dans le document courant, à SA taille en mm.

    C'est le point de la manoeuvre : l'image sortant du redressement a une
    échelle exacte et connue, donc l'atelier peut la placer lui-même au bon
    format. Plus de taille à recopier à la main, donc plus d'occasion de se
    tromper d'un facteur."""
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Mesures")
    obj = doc.addObject("Image::ImagePlane", "PlancheRedressee")
    obj.ImageFile = chemin
    obj.XSize = largeur_mm
    obj.YSize = hauteur_mm
    obj.Label = os.path.splitext(os.path.basename(chemin))[0]
    doc.recompute()
    try:
        Gui.SendMsgToActiveView("ViewFit")
    except Exception:
        pass
    return obj


# Les planches et leur clé de rangement des photos.
#
# SOURCE UNIQUE, et ça compte : le bouton de redressement RANGE sous ces
# clés, la galerie LIT sous ces clés. Tant que les deux listes étaient
# écrites séparément, elles pouvaient diverger -- et pire, la galerie
# n'existait pas du tout : les photos étaient rangées quelque part que
# rien n'affichait, et le message promettait pourtant « rangée dans les
# photos du résultat » (constaté le 01/08/2026).
_PLANCHES = (("Planche 1 — foyer", "planche1"),
             ("Planche 2 — défocus", "planche2"),
             ("Autre planche", "planche_autre"))


def _gerer_planches_redressees(parent, apres=None):
    """Lister et supprimer des planches redressées, fichiers compris.

    Refaire une planche mieux gravée est le cas NORMAL de ce chantier : on
    grave, on mesure, on n'aime pas, on regrave. Sans moyen d'effacer,
    l'ancienne reste au milieu des bonnes -- et à 56 Mo la planche, le
    dossier gonfle. Le bouton « Supprimer la photo affichée » de la galerie
    ne suffisait pas : il n'enlève que l'aperçu, laissant l'image de mesure
    sur le disque."""
    planches = core.planches_redressees()
    if not planches:
        QtWidgets.QMessageBox.information(
            parent, "Planches redressées",
            "Aucune planche dans {}.".format(core.dossier_planches(creer=False)))
        return

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Planches redressées")
    dlg.resize(820, 460)
    v = QtWidgets.QVBoxLayout(dlg)
    v.addWidget(_WrapLabel(
        "Dossier : <code>{}</code> — {} planche(s), {:.0f} Mo au total. "
        "Sélection multiple possible (Ctrl / Maj).".format(
            core.dossier_planches(creer=False), len(planches),
            sum(p["octets"] for p in planches) / 1e6)))
    liste = QtWidgets.QListWidget()
    liste.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    for p in planches:
        infos = p["infos"] or {}
        reg = infos.get("reglette") or {}
        detail = []
        if infos.get("laser"):
            detail.append(infos["laser"])
        if infos.get("largeur_mm"):
            detail.append("{:.0f} × {:.0f} mm".format(
                infos["largeur_mm"], infos.get("hauteur_mm", 0)))
        # L'écart de réglette est LE critère pour choisir laquelle garder :
        # c'est la seule mesure indépendante des croix cliquées.
        detail.append("réglette {:+.2f} %".format(reg["erreur_pct"])
                      if reg.get("erreur_pct") is not None
                      else "réglette non vérifiée")
        detail.append("{:.0f} Mo, {} fichier(s)".format(
            p["octets"] / 1e6, len(p["fichiers"])))
        it = QtWidgets.QListWidgetItem("{}\n    {}".format(
            p["nom"], "  —  ".join(detail)))
        it.setData(QtCore.Qt.UserRole, p["base"])
        liste.addItem(it)
    v.addWidget(liste, 1)

    btns = QtWidgets.QHBoxLayout()
    btn_sup = QtWidgets.QPushButton("Supprimer les planches sélectionnées")
    btn_fermer = QtWidgets.QPushButton("Fermer")
    btns.addWidget(btn_sup, 1)
    btns.addWidget(btn_fermer, 0)
    v.addLayout(btns)

    def _supprimer():
        choisies = liste.selectedItems()
        if not choisies:
            QtWidgets.QMessageBox.information(
                dlg, "Supprimer", "Sélectionne d'abord une ou plusieurs planches.")
            return
        bases = [it.data(QtCore.Qt.UserRole) for it in choisies]
        detail = "\n".join(
            "  • " + os.path.basename(b) for b in bases[:12])
        if len(bases) > 12:
            detail += "\n  … et {} autre(s)".format(len(bases) - 12)
        # Une suppression NOMME ce qu'elle va détruire, et le nombre de
        # fichiers : une planche, c'est quatre fichiers, pas un.
        n_fic = sum(len(core._fichiers_planche(b)) for b in bases)
        if QtWidgets.QMessageBox.question(
                dlg, "Supprimer définitivement ?",
                "{} planche(s), soit {} fichier(s) :\n\n{}\n\n"
                "Image de mesure, fiche, aperçu et contrôle des repères "
                "seront effacés du disque, ainsi que les vignettes "
                "correspondantes de la galerie. Irréversible.".format(
                    len(bases), n_fic, detail),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return
        total_n = total_o = 0
        for b in bases:
            n, o = core.supprimer_planche(b)
            total_n += n
            total_o += o
        QtWidgets.QMessageBox.information(
            dlg, "Supprimé",
            "{} fichier(s) effacé(s), {:.0f} Mo libérés.".format(
                total_n, total_o / 1e6))
        if apres is not None:
            apres()
        dlg.accept()

    btn_sup.clicked.connect(_supprimer)
    btn_fermer.clicked.connect(dlg.reject)
    dlg.exec()


def _reposer_planche_redressee(parent):
    """Reposer dans le document une planche DÉJÀ redressée, à son échelle.

    Le redressement est un travail fait une fois : cliquer quatre croix,
    contrôler l'échelle sur la réglette. Rouvrir FreeCAD ne doit pas
    obliger à tout recommencer pour la seule raison que le document n'a pas
    été enregistré -- l'image, elle, est toujours sur le disque (constaté le
    01/08/2026 : document « Nouveau » jamais enregistré, et le seul moyen de
    remettre l'image était de recliquer les croix pour rien).

    La taille en mm vient de la fiche `.json` écrite à côté de l'image. Sans
    fiche (image d'avant la v2.21), on la déduit des pixels et de l'échelle
    demandée -- c'est exact tant que l'échelle est la bonne, et le panneau
    redresse toujours à 50 px/mm."""
    chemin, _f = QtWidgets.QFileDialog.getOpenFileName(
        parent, "Planche déjà redressée (…_redresse.png)",
        core.dossier_planches(), "Images redressées (*.png *.jpg);;Tous (*)")
    if not chemin:
        return
    fiche = os.path.splitext(chemin)[0] + ".json"
    largeur = hauteur = None
    if os.path.exists(fiche):
        try:
            with open(fiche) as fh:
                d = json.load(fh)
            largeur, hauteur = float(d["largeur_mm"]), float(d["hauteur_mm"])
            note = "fiche {} — {:.0f} px/mm".format(
                os.path.basename(fiche), d.get("pxmm", 0))
        except Exception as e:
            FreeCAD.Console.PrintWarning("Fiche illisible ({}).\n".format(e))
    if largeur is None:
        taille = QtGui.QImageReader(chemin).size()   # en-tête seul, pas l'image
        if not taille.isValid():
            QtWidgets.QMessageBox.critical(
                parent, "Reposer une planche", "Image illisible : " + chemin)
            return
        pxmm, ok = QtWidgets.QInputDialog.getDouble(
            parent, "Échelle de l'image",
            "Pas de fiche .json à côté de cette image (redressement antérieur\n"
            "à la v2.21). Échelle utilisée lors du redressement, en px/mm :",
            50.0, 1.0, 1000.0, 1)
        if not ok:
            return
        largeur, hauteur = taille.width() / pxmm, taille.height() / pxmm
        note = "déduite de {} x {} px à {:.0f} px/mm".format(
            taille.width(), taille.height(), pxmm)
    try:
        _importer_image_a_l_echelle(chemin, largeur, hauteur)
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            parent, "Reposer une planche", "Image non posée : {}".format(e))
        return
    QtWidgets.QMessageBox.information(
        parent, "Reposer une planche",
        "Posée à {:.3f} × {:.3f} mm ({}).\n\n"
        "Mesure à l'outil « Mesurer A → B » du bloc ② — et ZOOME avant de "
        "pointer.\n\nPense à ENREGISTRER ce document : tu n'auras plus à "
        "reposer l'image la prochaine fois.".format(largeur, hauteur, note))


def _redresser_photo_planche(parent, on_range=None):
    """Choisir une photo, la redresser via OpenCV, la ranger et la poser
    dans le document à l'échelle exacte.

    `base_defaut` = cotes de la mire telles que le générateur ACTUEL les
    produirait. Elles sont proposées, pas imposées : une planche gravée il
    y a six mois n'a pas forcément la mise en page d'aujourd'hui (c'est
    arrivé le 31/07/2026), et ses vraies cotes sont GRAVÉES dessus. On
    lit sur le bois, on corrige si besoin."""
    choix, ok = QtWidgets.QInputDialog.getItem(
        parent, "Quelle planche ?",
        "La planche photographiée détermine les cotes proposées et le\n"
        "rangement de la photo dans les résultats.",
        [lib for lib, _c in _PLANCHES], 0, False)
    if not ok:
        return
    planche = dict(_PLANCHES).get(choix, "planche_autre")
    base_defaut = _cotes_mire_defaut(planche)

    py = _python_systeme()
    if py is None:
        QtWidgets.QMessageBox.critical(
            parent, "Python système introuvable",
            "Le redressement a besoin d'OpenCV, absent du python de FreeCAD.\n"
            "Aucun /usr/bin/python3 trouvé.")
        return
    photos, _f = QtWidgets.QFileDialog.getOpenFileNames(
        parent, "Photo(s) de la planche — plusieurs possibles (gros plans)",
        os.path.expanduser("~"),
        "Images (*.jpg *.jpeg *.JPG *.png *.PNG *.tif *.tiff);;Tous (*)")
    if not photos:
        return
    base, ok = QtWidgets.QInputDialog.getText(
        parent, "Cotes de la mire",
        "Cotes du rectangle ENTRE CENTRES des 4 croix.\n\n"
        "Elles sont GRAVÉES sur la planche, sous la réglette (ex. « 140-60 ») :\n"
        "lis-les sur le bois plutôt que de faire confiance à cette proposition,\n"
        "qui vient de la mise en page ACTUELLE et peut ne pas correspondre à\n"
        "une planche gravée avant une évolution.",
        text=base_defaut)
    if not ok or not base.strip():
        return
    base = base.strip().replace("-", "x").replace(",", ".")

    # LES COTES SAISIES DÉSIGNENT-ELLES UNE AUTRE PLANCHE ?
    #
    # La planche est choisie AVANT de voir la photo, donc on peut très bien
    # cliquer « Planche 1 » et photographier la 2 -- c'est arrivé le
    # 01/08/2026. Les cotes, elles, sont lues sur le bois : elles sont donc
    # la source la plus fiable des deux, et quand les deux se contredisent,
    # c'est le choix initial qui a tort.
    #
    # Rien n'est faussé dans ce cas (l'échelle vient des cotes, qui sont
    # bonnes) -- mais la photo est RANGÉE sous la mauvaise planche, et son
    # fichier porte un nom qui ment. Or tout le travail de ce matin
    # consistait à rendre chaque planche identifiable sans mémoire.
    _connues = {cle: _cotes_mire_defaut(cle).replace("-", "x")
                for _lib, cle in _PLANCHES if cle != "planche_autre"}
    if planche in _connues and _connues[planche] != base:
        _autre = next((c for c, v in _connues.items()
                       if c != planche and v == base), None)
        if _autre is not None:
            _lib_autre = dict((c, l) for l, c in _PLANCHES)[_autre]
            _lib_choisi = dict((c, l) for l, c in _PLANCHES)[planche]
            rep = QtWidgets.QMessageBox.question(
                parent, "Ce sont les cotes d'une autre planche",
                "Tu as choisi « {} », mais les cotes saisies ({}) sont "
                "celles de « {} ».\n\n"
                "L'échelle sera juste dans les deux cas — elle vient des "
                "cotes. Mais la photo serait rangée sous « {} », et son "
                "fichier porterait ce nom-là.\n\n"
                "La ranger sous « {} » ?".format(
                    _lib_choisi, base.replace("x", "-"), _lib_autre,
                    _lib_choisi, _lib_autre),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Yes)
            if rep == QtWidgets.QMessageBox.Cancel:
                return
            if rep == QtWidgets.QMessageBox.Yes:
                planche = _autre

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "outils", "redresser_photo.py")
    horo = time.strftime("%Y%m%d-%H%M")
    faits, rates = [], []
    for i, photo in enumerate(photos, 1):
        suffixe = "" if len(photos) == 1 else "_{}".format(i)
        # Dossier À PART, et nom portant le LASER.
        #
        # À côté de la photo d'origine, les planches redressées se
        # perdaient au milieu des IMG_*.JPG du dossier d'échange. Et sans
        # le nom du laser sur le fichier, une largeur brûlée ne dit pas de
        # quel module elle vient : deux diodes différentes donnent deux
        # tables différentes, alors que le MÊME module rend ces mesures
        # réutilisables telles quelles par quelqu'un d'autre.
        sortie = os.path.join(
            core.dossier_planches(),
            core.nom_planche_redressee(planche, horo, suffixe) + ".png")
        infos = os.path.join(tempfile.gettempdir(), "redresse_{}.json".format(i))
        try:
            r = subprocess.run([py, script, photo, "--base", base,
                                "--pxmm", "50", "--sortie", sortie,
                                "--laser", core.active_laser_name(),
                                "--json", infos],
                               capture_output=True, text=True, timeout=900,
                               env=_env_systeme_propre())
        except Exception as e:
            rates.append("{} : {}".format(os.path.basename(photo), e))
            continue
        if r.returncode != 0 or not os.path.exists(infos):
            rates.append("{} : {}".format(os.path.basename(photo),
                                          (r.stderr or r.stdout or "").strip()[-300:]))
            continue
        with open(infos) as fh:
            d = json.load(fh)
        os.remove(infos)
        # La vérification par la réglette est ce qui distingue une échelle
        # CONTRÔLÉE d'une échelle simplement calculée : elle est écrite
        # dans la description, parce que c'est elle qu'on relira dans six
        # mois pour savoir si on peut croire les mesures de cette photo.
        reg = d.get("reglette")
        controle = ("réglette vérifiée à {:+.2f} %".format(reg["erreur_pct"])
                    if reg else "réglette NON détectée, échelle non vérifiée")
        # On range l'APERÇU, pas le PNG de mesure : celui-ci pèse 55 Mo
        # (12800 x 4300 sans perte) et la galerie n'a pas à le dupliquer --
        # 290 Mo se sont accumulés en une matinée avant qu'on s'en aperçoive,
        # le 01/08/2026. Le fichier de mesure reste à sa place, et son chemin
        # part dans la description pour qu'on le retrouve depuis la galerie.
        core.add_result_photo(
            planche, d.get("apercu") or d["fichier"],
            "redressée le {} — échelle {:.0f} px/mm, mire {:.0f}x{:.0f}, "
            "écart de diagonales {:.2f} %, {} — fichier de mesure : {}".format(
                time.strftime("%d/%m/%Y %H:%M"), d["pxmm"],
                d["base_mm"][0], d["base_mm"][1], d["ecart_diagonales_pct"],
                controle, d["fichier"]))
        try:
            _importer_image_a_l_echelle(d["fichier"], d["largeur_mm"], d["hauteur_mm"])
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                "Image non posée dans le document : {}\n".format(e))
        faits.append(d)

    if rates:
        QtWidgets.QMessageBox.warning(
            parent, "Redressement", "Photos non traitées :\n\n" + "\n".join(rates))
    if faits:
        ecarts = [d["reglette"]["erreur_pct"] for d in faits if d.get("reglette")]
        verdict = ("Échelle contrôlée sur la réglette gravée : {} — une mesure "
                   "INDÉPENDANTE des quatre croix.".format(
                       ", ".join("{:+.2f} %".format(e) for e in ecarts))
                   if ecarts else
                   "Réglette non détectée : l'échelle ne repose que sur les "
                   "quatre croix, rien ne la contrôle.")
        QtWidgets.QMessageBox.information(
            parent, "Redressement",
            "{} photo(s) redressée(s), rangée(s) dans les photos du résultat "
            "et posée(s) dans le document à l'échelle exacte.\n\n{}\n\n"
            "Mesure à l'outil Ligne du Draft — et ZOOME : à l'écran un clic "
            "vaut ~1 pixel, soit 0,16 mm si toute la planche tient dans la "
            "fenêtre.\n\nContrôle des repères écrit à côté de chaque photo "
            "(_reperes.jpg) : regarde-le avant de croire une mesure.".format(
                len(faits), verdict))
        if on_range is not None:
            # La galerie doit montrer la photo qu'on VIENT de ranger : sans
            # ça il faut fermer et rouvrir le panneau pour la voir.
            on_range(planche)


def _boutons_planches(form, ecrire):
    """Les boutons « Planche 1/2/3 » + « toutes en 1 fichier » (partagés
    entre la Grille de test et l'Assistant matériau) : chacun génère son
    G-code et le remet à `ecrire(gcode, chemin_defaut)` -- le recadrage au
    zéro pièce se fait à l'écriture. Renvoie (btn1, btn2, btn3, btn_combine)."""
    b1 = QtWidgets.QPushButton("Planche 1 — Foyer (S × F)")
    b1.setToolTip(
        "Grille de traits AU FOYER : S (bornée à s_max) × F jusqu'au maxi\n"
        "machine. Mesure la largeur brûlée de chaque trait (un trait vierge\n"
        "= seuil du matériau) -> largeur au foyer (feed-aware).\n"
        "Fichier séparé, recadré au zéro pièce (coin bas-gauche).")
    b1.clicked.connect(lambda: ecrire(core.generate_gcode_planche_focus(),
                                      "/tmp/planche1_foyer.ngc"))
    form.addRow(b1)

    b2 = QtWidgets.QPushButton("Planche 2 — Défocus (S × F, niveaux 15/36)")
    b2.setToolTip(
        "Traits AU DÉFOCUS : une grille S × F par niveau (~15 et 36 mm), en\n"
        "BALAYANT le feed (jusqu'à ~800 -- au-delà, ça ne marque quasiment\n"
        "jamais au défocus). Mesure les largeurs -> alimente le modèle\n"
        "feed-aware du remplissage (burn_width_defocus_scaled).\n"
        "Fichier séparé, recadré au zéro pièce.")
    b2.clicked.connect(lambda: ecrire(core.generate_gcode_planche_defocus(),
                                      "/tmp/planche2_defocus.ngc"))
    form.addRow(b2)

    b3 = QtWidgets.QPushButton("Planche 3 — Largeur du point (défocus)")
    b3.setToolTip(
        "Bande de calibration du POINT : Ø net au foyer + Ø à une hauteur\n"
        "connue -> le modèle d'élargissement du point. Réglages fins dans le\n"
        "mode « Bande de calibration défocus » (Préférences > Calibration du\n"
        "point) ; ce bouton grave la bande par défaut, recadrée au zéro pièce.")
    b3.clicked.connect(lambda: ecrire(core.generate_gcode_planche_spot(),
                                      "/tmp/planche3_point.ngc"))
    form.addRow(b3)

    b4 = QtWidgets.QPushButton("Toutes les planches (1 seul fichier)")
    b4.setToolTip(
        "Planches 1+2+3 empilées dans UN SEUL fichier -- un seul armement\n"
        "au début, une seule fin, au lieu de charger trois fichiers l'un\n"
        "après l'autre sur la machine. Même contenu que les trois boutons\n"
        "séparés ci-dessus, juste réunis.")
    b4.clicked.connect(lambda: ecrire(core.generate_gcode_planches_combinees(),
                                      "/tmp/planches_combinees.ngc"))
    form.addRow(b4)

    # --- mesurer une planche GRAVÉE, à partir d'une photo ---------------
    b5 = QtWidgets.QPushButton("Redresser une photo de planche…")
    b5.setToolTip(
        "Choisir une ou plusieurs photos d'une planche gravée (gros plans\n"
        "acceptés), cliquer ses 4 croix de mire, et l'atelier :\n"
        "  - redresse la perspective (OpenCV, python système) ;\n"
        "  - range l'image dans les photos du résultat ;\n"
        "  - la POSE dans le document à l'échelle exacte, en mm.\n"
        "\n"
        "Il ne reste qu'à mesurer à l'outil Ligne du Draft. Indispensable\n"
        "parce que FreeCAD met une image à l'échelle de façon UNIFORME : il\n"
        "ne corrige pas une photo prise de biais, et rien ne le signale.")
    form.addRow(b5)

    b6 = QtWidgets.QPushButton("Reposer une planche déjà redressée…")
    b6.setToolTip(
        "Repose dans le document une image DÉJÀ redressée, à son échelle\n"
        "exacte -- sans recliquer les quatre croix.\n"
        "\n"
        "À utiliser quand FreeCAD a été rouvert sans que le document ait\n"
        "été enregistré : le redressement, lui, est toujours sur le disque.\n"
        "La taille en mm vient de la fiche .json écrite à côté de l'image.")
    b6.clicked.connect(
        lambda: _reposer_planche_redressee(form.parentWidget() or form))
    form.addRow(b6)

    b7 = QtWidgets.QPushButton("Gérer / supprimer des planches…")
    b7.setToolTip(
        "Liste les planches redressées du dossier, avec leur laser, leurs\n"
        "cotes, l'écart mesuré sur la réglette et leur poids -- puis permet\n"
        "d'en supprimer.\n"
        "\n"
        "Regraver une planche mieux réussie est le cas normal : l'ancienne\n"
        "doit pouvoir partir, fichiers compris. L'écart de réglette est le\n"
        "bon critère pour choisir laquelle garder, c'est la seule mesure\n"
        "indépendante des croix cliquées.\n"
        "\n"
        "Supprime l'image de mesure, sa fiche, son aperçu, le contrôle des\n"
        "repères ET la vignette correspondante de la galerie.")
    form.addRow(b7)

    # --- Voir les planches redressées ---------------------------------
    # Sans ça, les photos rangées par le bouton ci-dessus n'étaient
    # affichées NULLE PART : le message annonçait « rangée dans les photos
    # du résultat » et il fallait aller ouvrir le dossier à la main
    # (constaté le 01/08/2026). Une donnée qu'on range sans jamais la
    # remontrer n'est pas rangée, elle est perdue poliment.
    combo_planche = QtWidgets.QComboBox()
    for libelle, cle in _PLANCHES:
        combo_planche.addItem(libelle, cle)
    combo_planche.setToolTip("Quelle planche afficher dans la galerie ci-dessous.")
    form.addRow("Photos de :", combo_planche)
    photo_pl = _make_photo_section(form, lambda: combo_planche.currentData(),
                                   titre="Planches redressées")
    combo_planche.currentIndexChanged.connect(lambda _i: photo_pl["reload"]())
    photo_pl["reload"]()

    def _apres_redressement(planche):
        i = combo_planche.findData(planche)
        if i >= 0:
            combo_planche.blockSignals(True)
            combo_planche.setCurrentIndex(i)
            combo_planche.blockSignals(False)
        # On sélectionne la DERNIÈRE : c'est celle qui vient d'être rangée.
        photo_pl["reload"](max(0, len(core.result_photos(planche)) - 1))

    b5.clicked.connect(lambda: _redresser_photo_planche(
        form.parentWidget() or form, on_range=_apres_redressement))
    b7.clicked.connect(lambda: _gerer_planches_redressees(
        form.parentWidget() or form, apres=photo_pl["reload"]))
    return b1, b2, b3, b4


class _MesuresPlanchesControleur:
    """Bloc partagé « saisie des mesures des planches » (Grille de test,
    Assistant matériau) : une _GrilleResultats pour le foyer (Planche 1 dans
    l'Assistant, ou la grille « Largeurs brûlées » dans Grille de test -- même
    forme de données) + une par niveau de défocus (Planche 2/grille défocus)
    + le bouton « Enregistrer les mesures ». Les titres des grilles ne disent
    PAS « Planche N » : la même mesure peut venir d'une planche dédiée ou
    d'une grille de test, et le nommer d'après la source figée dans l'un des
    deux panneaux serait faux dans l'autre. `get_material()` fournit le
    matériau courant ; reload() recharge depuis la config (anciennes mesures
    mono-feed -> colonne F800 du bon niveau, z_offset déjà ramené au niveau
    standard par load_burn_widths) ; l'enregistrement passe par
    save_burn_widths puis rappelle `on_saved` (rafraîchir liste des
    matériaux, déductions...). `parent` = le panneau hôte (boîtes de message
    via parent.form)."""

    POWERS = (1000, 800, 600, 400, 200)
    # Doit rester aligné sur les feeds par défaut de generate_gcode_planche_focus
    # (laser_core.py) : F6000 retiré le 27 juil. 2026 (ne marque plus depuis
    # un changement de lentille).
    #
    # F1000 et F1200 ajoutés le 31/07/2026. Il n'y avait RIEN entre 800 et
    # 1500, et c'est exactement là que le tramage « Lignes gravées » se
    # joue : à F800 le trait va de 0,10 à 0,30 mm, à F1500 il est plat à
    # 0,10. Tout ce que l'atelier racontait entre les deux (« F1000 ->
    # 0,23 ») était une DROITE tracée entre deux mesures, jamais une
    # mesure -- et `swell_max_feed` en dépend pour refuser ou non une
    # vitesse. Deux points intérieurs suffisent à encadrer l'effondrement ;
    # quatre rendraient la grille de saisie illisible dans un panneau de
    # 430 px de large.
    FEEDS_FOCUS = (200, 400, 800, 1000, 1200, 1500, 3000)
    # Doit rester aligné sur les feeds par défaut de generate_gcode_planche_defocus
    # (laser_core.py) : la grille de saisie n'a de colonnes que pour ce qui
    # est réellement gravé sur la planche. Resserré le 27 juil. 2026 (était
    # 400/800/1500/2000) -- au défocus, F1500/F2000 ne marquaient quasiment
    # jamais (0 mesure enregistrée à ces vitesses sur MDF malgré plusieurs
    # planches).
    FEEDS_DEFOCUS = (200, 400, 600, 800)

    def __init__(self, form, parent, get_material, on_saved=None,
                 get_niveau_cible=None):
        self._parent = parent
        self._get_material = get_material
        self._on_saved = on_saved
        # Défocus que le panneau hôte s'apprête à graver, s'il en connaît un
        # (« Défocus des cellules » de la Grille de test) : une planche
        # gravée à un niveau choisi doit avoir une grille où être saisie,
        # même si ce niveau n'a encore aucune mesure.
        self._get_niveau_cible = get_niveau_cible
        self._levels = []
        # --- mesurer A -> B SANS quitter cette saisie ------------------
        # L'outil Ligne du Draft affiche bien la distance, mais il occupe le
        # panneau des tâches -- or celui-ci est EXCLUSIF dans FreeCAD, donc
        # impossible d'avoir la grille de saisie ouverte en même temps.
        # D'où une mesure intégrée ICI : on clique la case à remplir, on
        # clique « Mesurer », on pointe deux fois dans la vue, et la valeur
        # tombe dans la case. Aucun aller-retour entre deux panneaux.
        self._mesure_cb = None
        self._mesure_pts = []
        self._mesure_cible = None
        self._perp = True
        self._blocs = []
        self._bloc_courant = None
        # Case visée, MÉMORISÉE au moment où elle prend le focus.
        #
        # La lire au clic sur le bouton ne pouvait pas marcher : à cet
        # instant le focus est DÉJÀ sur le bouton. Le commentaire d'origine
        # décrivait pourtant l'intention correcte -- le code faisait le
        # contraire, et le message d'erreur (« clique une case AVANT »)
        # accusait l'utilisateur d'un geste qu'il venait de faire.
        # Constaté au premier usage réel, le 01/08/2026.
        #
        # Mémoriser plutôt que lire au dernier moment couvre en plus le cas
        # normal : on désigne la case, PUIS on zoome dans la vue 3D (ce qui
        # y déplace le focus), et seulement ensuite on mesure.
        self._derniere_case = None
        self._serie = []
        self.grille_focus = _GrilleResultats(
            "Traits au FOYER : largeur (mm)",
            rows=self.POWERS, cols=self.FEEDS_FOCUS)
        self.grille_focus.caseFocus.connect(self._on_case_focus)
        form.addRow(self.grille_focus)
        form.addRow(self._creer_bloc(self.grille_focus))
        # Les panneaux hôtes et les tests parlent d'UN bouton : celui de la
        # grille du foyer, la seule qui ne soit jamais reconstruite.
        self.btn_mesurer = self._blocs[0].btn
        self.lbl_mesure = self._blocs[0].lbl
        # Les grilles de défocus sont RECONSTRUITES à chaque reload() : leurs
        # niveaux suivent les mesures du matériau courant, qui change quand
        # on change de matériau ou qu'on grave un nouveau niveau.
        self.grilles_defocus = {}
        self._boite_niveaux = QtWidgets.QWidget()
        self._pile_niveaux = QtWidgets.QVBoxLayout(self._boite_niveaux)
        self._pile_niveaux.setContentsMargins(0, 0, 0, 0)
        form.addRow(self._boite_niveaux)

        self.btn_save = QtWidgets.QPushButton("Enregistrer les mesures")
        self.btn_save.setToolTip(
            "Range ces largeurs pour le matériau indiqué. Indépendant de "
            "l'OK du panneau.\n"
            "Les mesures que ces grilles n'affichent pas (puissance, vitesse "
            "ou\ndéfocus hors grille) sont CONSERVÉES telles quelles.")
        self.btn_save.clicked.connect(self._on_save)
        form.addRow(self.btn_save)

    # ------------------------------------------------------------------
    # Mesure A -> B dans la vue 3D
    #
    # Motif Coin/Quarter NOUVEAU dans ce dépôt : la règle 5 du CLAUDE.md
    # interdit d'essayer ça pour la première fois dans la session vivante
    # de Christophe, et il n'existe pas de vue 3D en headless. Tout est
    # donc défensif, et le rappel est retiré dans TOUS les chemins --
    # laisser un callback branché sur la vue est le moyen le plus sûr de
    # rendre FreeCAD inutilisable jusqu'au redémarrage.
    # ------------------------------------------------------------------
    def _creer_bloc(self, grille):
        """Un bloc de mesure attaché à cette grille, mémorisé dans _blocs."""
        bloc = _BlocMesure(self._on_mesurer, self._on_perp)
        bloc.grille = grille
        bloc.chk_perp.setChecked(self._perp)
        self._blocs.append(bloc)
        return bloc

    def _blocs_vivants(self):
        """Les blocs dont le widget C++ existe encore.

        Les grilles de défocus sont DÉTRUITES à chaque reconstruction, et
        leurs blocs avec : parler à un objet C++ mort lève une RuntimeError
        au milieu d'une mesure. On filtre plutôt que de faire confiance."""
        vivants = []
        for b in self._blocs:
            try:
                b.btn.text()
            except RuntimeError:
                continue
            vivants.append(b)
        self._blocs = vivants
        return vivants

    def _on_perp(self, coche):
        """Le mode de mesure est UN réglage, affiché à plusieurs endroits :
        les cases se suivent, sinon deux blocs pourraient annoncer deux
        modes différents pour la même mesure."""
        self._perp = bool(coche)
        for b in self._blocs_vivants():
            if b.chk_perp.isChecked() != self._perp:
                b.chk_perp.blockSignals(True)
                b.chk_perp.setChecked(self._perp)
                b.chk_perp.blockSignals(False)

    def _bloc_de(self, sp):
        """Le bloc de la grille qui contient cette case, sinon celui du
        foyer -- il existe toujours."""
        for b in self._blocs_vivants():
            try:
                if b.grille.contient(sp):
                    return b
            except RuntimeError:
                continue
        return self._blocs[0]

    def _dire(self, texte, bloc=None):
        """Écrit le message DANS LE BLOC concerné : à quoi bon un bouton
        près de la grille si sa réponse s'affiche trois grilles plus bas."""
        (bloc or self._bloc_courant or self._blocs[0]).lbl.setText(texte)

    def _on_case_focus(self, sp):
        """Une case vient de prendre le focus : elle devient la cible, et la
        série de moyennage repart de zéro. Re-cliquer une case est donc le
        geste qui annule une série ratée -- pas besoin d'un bouton pour ça."""
        self._derniere_case = sp
        self._serie = []
        nom = self._nom_case(sp)
        if nom:
            self._dire("Case visée : <b>{}</b>. Clique « Mesurer A → B », "
                       "puis les deux bords du trait.".format(nom),
                       self._bloc_de(sp))

    def _distance(self, a, b):
        """(valeur retenue, dx, dy) selon le mode de mesure.

        EN TRAVERS (par défaut) : on ne garde que la plus grande des deux
        composantes, c'est-à-dire celle perpendiculaire au trait -- dy pour
        un trait horizontal, dx pour un vertical.

        La distance directe vaut hypot(dx, dy) : elle est donc TOUJOURS
        supérieure ou égale à la largeur réelle, et d'autant plus que les
        deux clics sont décalés latéralement. Sur un trait de 0,30 mm,
        0,20 mm de décalage donne 0,36 -- 20 % de trop, sans rien qui le
        signale. Une mesure de largeur ne doit pas dépendre de la main."""
        dx, dy = abs(b.x - a.x), abs(b.y - a.y)
        return (max(dx, dy) if self._perp else math.hypot(dx, dy)), dx, dy

    def _encaisser_mesure(self, d, dx, dy):
        """Range une mesure dans la case visée et renvoie le texte à afficher.

        Les bords d'un trait gravé ne sont pas droits -- c'est le grain qui
        décide. Des mesures successives sur la MÊME case sont donc cumulées
        en moyenne, et leur ÉTENDUE est affichée : c'est elle qui dit si le
        critère « où s'arrête la brûlure » a tenu d'un bout à l'autre, ce
        qu'une valeur seule ne dit jamais. Une étendue large n'invalide pas
        la moyenne, elle avertit que le trait lui-même varie.

        Hors du rappel de la vue 3D pour être testable : sans vue 3D en
        headless, laissée dans la fermeture, cette arithmétique-là ne serait
        vérifiée par rien."""
        self._serie.append(float(d))
        m = sum(self._serie) / len(self._serie)
        if self._mesure_cible is not None:
            self._mesure_cible.setValue(m)
        # dx ET dy sont toujours donnés, quel que soit le mode : c'est ce
        # qui permet de voir qu'on a pointé de travers.
        txt = "Mesure <b>{:.3f} mm</b> ({}) — dx {:.3f}, dy {:.3f}, directe " \
              "{:.3f} → {}".format(
                  d, "en travers" if self._perp else "distance directe",
                  dx, dy, math.hypot(dx, dy),
                  self._nom_case(self._mesure_cible) or "la case visée")
        if len(self._serie) > 1:
            txt += " — <b>moyenne de {} : {:.3f} mm</b> (étendue {:.3f})".format(
                len(self._serie), m, max(self._serie) - min(self._serie))
        else:
            txt += " — remesure pour moyenner, ou clique la case pour repartir."
        return txt

    def _nom_case(self, sp):
        """« S1000 / F800 (foyer) » — la grille est nommée elle aussi : les
        mêmes S et F existent au foyer ET à chaque niveau de défocus."""
        nom = self.grille_focus.nom_case(sp)
        if nom:
            return nom + " (foyer)"
        for dz, gr in self.grilles_defocus.items():
            try:
                nom = gr.nom_case(sp)
            except RuntimeError:
                continue
            if nom:
                return "{} (défocus {:g} mm)".format(nom, dz)
        return None

    def _vue3d(self):
        try:
            return Gui.ActiveDocument.ActiveView
        except Exception:
            return None

    def _fin_mesure(self):
        """Débranche le rappel, quoi qu'il arrive."""
        vue = self._vue3d()
        if vue is not None and self._mesure_cb is not None:
            try:
                vue.removeEventCallback("SoMouseButtonEvent", self._mesure_cb)
            except Exception:
                pass
        self._mesure_cb = None
        self._mesure_pts = []
        for b in self._blocs_vivants():
            b.btn.setText("Mesurer A → B dans la vue 3D")

    def _on_mesurer(self, bloc=None):
        self._bloc_courant = bloc or self._blocs[0]
        if self._mesure_cb is not None:          # 2e clic = annulation
            self._fin_mesure()
            self._dire("Mesure annulée.")
            return
        vue = self._vue3d()
        if vue is None:
            self._dire("Aucune vue 3D active : ouvre le document contenant "
                       "la photo redressée.")
            return
        # La case visée est celle MÉMORISÉE à son dernier focus, pas celle
        # que `focusWidget()` renvoie maintenant : à cet instant le focus
        # est sur le bouton (ou sur la vue 3D si on vient d'y zoomer).
        self._mesure_cible = self._derniere_case
        self._mesure_pts = []
        if self._mesure_cible is None:
            self._dire(
                "Clique d'abord la <b>case à remplir</b> dans une grille "
                "(décoche « Verrouiller les résultats » si elles sont "
                "grisées), puis reviens sur ce bouton.")
            return
        self._bloc_courant = self._bloc_de(self._mesure_cible)

        def _clic(info):
            try:
                if info.get("Type") != "SoMouseButtonEvent":
                    return
                if info.get("Button") != "BUTTON1" or info.get("State") != "DOWN":
                    return
                p = vue.getPoint(*info["Position"])
                self._mesure_pts.append(p)
                if len(self._mesure_pts) == 1:
                    self._bloc_courant.btn.setText(
                        "Point A pris — clique B (ou annule)")
                    self._dire("A = ({:.2f}, {:.2f})".format(
                        self._mesure_pts[0].x, self._mesure_pts[0].y))
                    return
                a, b = self._mesure_pts[0], self._mesure_pts[1]
                d, dx, dy = self._distance(a, b)
                self._fin_mesure()
                self._dire(self._encaisser_mesure(d, dx, dy))
            except Exception as e:                # jamais laisser le rappel branché
                self._fin_mesure()
                self._dire("Mesure interrompue : {}".format(e))

        try:
            self._mesure_cb = vue.addEventCallback("SoMouseButtonEvent", _clic)
        except Exception as e:
            self._mesure_cb = None
            self._dire("Mesure indisponible sur cette vue : {}".format(e))
            return
        self._bloc_courant.btn.setText("Clique le point A (ou annule)")
        # La cible est RAPPELÉE ici : c'est le dernier moment où la corriger
        # coûte un clic, et une valeur tombée dans la mauvaise case ne se
        # voit pas -- elle ressemble à une mesure.
        self.lbl_mesure.setText(
            "Cible : <b>{}</b>{}. Pointe A puis B dans la vue 3D. "
            "<b>Zoome</b> avant de pointer.".format(
                self._nom_case(self._mesure_cible) or "case sélectionnée",
                " — mesure n° {}".format(len(self._serie) + 1)
                if self._serie else ""))

    def _boite(self):
        return getattr(self._parent, "form", None)

    def _niveaux_a_afficher(self, mat):
        """Niveaux de défocus méritant une grille : ceux réellement mesurés
        sur le matériau, celui que l'hôte s'apprête à graver, et à défaut
        les niveaux standard (matériau neuf, rien de mesuré)."""
        niveaux = set(core.niveaux_defocus_mesures(mat) if mat else [])
        if self._get_niveau_cible:
            try:
                cible = float(self._get_niveau_cible() or 0.0)
            except (TypeError, ValueError):
                cible = 0.0
            if cible > 0:
                # Range la cible sur un niveau existant s'il est à portée,
                # pour ne pas créer une grille jumelle à 0,2 mm près.
                proche = min(niveaux, key=lambda L: abs(L - cible), default=None)
                if proche is None or abs(proche - cible) > core.SNAP_DEFOCUS_TOLERANCE_MM:
                    niveaux.add(round(cible, 3))
        if not niveaux:
            niveaux = {round(float(dz), 3) for dz in core.DEFOCUS_LEVELS_MM}
        return sorted(niveaux)

    def _reconstruire_niveaux(self, niveaux):
        """Refait les grilles de défocus pour la liste de niveaux donnée.
        Ne touche à rien si la liste n'a pas bougé -- reconstruire à chaque
        rafraîchissement effacerait une saisie en cours."""
        if niveaux == self._levels:
            return
        # Une mesure en cours pointerait sur des widgets qu'on s'apprête à
        # détruire : on la termine proprement AVANT, sinon son rappel reste
        # branché sur la vue 3D et FreeCAD devient inutilisable.
        self._fin_mesure()
        self._blocs = [b for b in self._blocs if b.grille is self.grille_focus]
        self._bloc_courant = None
        while self._pile_niveaux.count():
            item = self._pile_niveaux.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.grilles_defocus = {}
        for dz in niveaux:
            gr = _GrilleResultats(
                "Défocus {:g} mm : largeur (mm)".format(dz),
                rows=self.POWERS, cols=self.FEEDS_DEFOCUS)
            gr.caseFocus.connect(self._on_case_focus)
            self.grilles_defocus[dz] = gr
            self._pile_niveaux.addWidget(gr)
            self._pile_niveaux.addWidget(self._creer_bloc(gr))
        self._levels = list(niveaux)
        # Les cases visées viennent d'être détruites : garder un pointeur
        # dessus ferait planter le prochain setValue sur un objet C++ mort.
        self._derniere_case = None
        self._serie = []

    def reload(self):
        """Pré-remplit les grilles depuis les mesures déjà enregistrées pour
        le matériau courant (0 / « — » = non mesuré)."""
        mat = (self._get_material() or "").strip()
        self._reconstruire_niveaux(self._niveaux_a_afficher(mat))
        data = core.load_burn_widths(mat) if mat else {}
        self.grille_focus.set_values(
            {(float(pt.get("power", 0)), float(pt.get("feed", 0))):
             float(pt.get("width", 0.0)) for pt in data.get("focus", [])})
        par_niveau = {dz: {} for dz in self._levels}
        for pt in data.get("defocus", []):
            z = float(pt.get("z_offset", 0.0) or 0.0)
            if not self._levels:
                continue
            zk = min(self._levels, key=lambda L: abs(L - z))
            # BORNÉ : sans cette limite, un point mesuré à un défocus sans
            # grille s'affichait dans la grille du niveau le plus proche,
            # si loin fût-il -- et l'enregistrement le réécrivait ensuite
            # AU NIVEAU DE CETTE GRILLE. Une mesure à 60 mm rangée en 36.
            if abs(zk - z) > core.SNAP_DEFOCUS_TOLERANCE_MM:
                continue
            par_niveau[zk][(float(pt.get("power", 0)),
                            float(pt.get("feed", 800)))] = float(pt.get("width", 0.0))
        for dz, gr in self.grilles_defocus.items():
            gr.set_values(par_niveau.get(dz, {}))

    def _cellules_possedees(self):
        """(cases foyer, cases défocus) que ces grilles OCCUPENT, sous forme
        de clés. Tout ce qui n'y est pas appartient à quelqu'un d'autre et
        doit survivre à un enregistrement."""
        foyer = {(float(s), float(f))
                 for s in self.POWERS for f in self.FEEDS_FOCUS}
        defocus = {(float(s), float(f), float(dz))
                   for dz in self._levels
                   for s in self.POWERS for f in self.FEEDS_DEFOCUS}
        return foyer, defocus

    def _on_save(self):
        """Enregistre en FUSIONNANT.

        `save_burn_widths` REMPLACE la table du matériau : écrire seulement
        le contenu des grilles effaçait tout le reste. Sur le hêtre du
        30/07/2026, un clic sur ce bouton aurait supprimé **27 des 54**
        mesures en défocus -- toutes celles dont la puissance, la vitesse
        ou le niveau sortaient des grilles (S550, F650, défocus 30/55/60...).
        Des heures de pied à coulisse, sans un mot.

        On ne retire donc que les cases que ces grilles POSSÈDENT, et on y
        remet ce qu'elles affichent ; le reste est recopié tel quel."""
        mat = (self._get_material() or "").strip()
        if not mat:
            QtWidgets.QMessageBox.warning(
                self._boite(), "Mesures", "Indiquer un nom de matériau.")
            return
        # Lecture BRUTE : load_burn_widths range les défocus sur les niveaux
        # standard, et réécrire ces valeurs rangées déplacerait des mesures.
        brut = (core.load_config().get("burn_widths", {}) or {}).get(mat, {}) or {}
        cases_foyer, cases_defocus = self._cellules_possedees()
        conserves_f = [pt for pt in (brut.get("focus") or [])
                       if (float(pt.get("power", 0)), float(pt.get("feed", 0)))
                       not in cases_foyer]
        conserves_d = [pt for pt in (brut.get("defocus") or [])
                       if (float(pt.get("power", 0)), float(pt.get("feed", 0)),
                           float(pt.get("z_offset", 0) or 0)) not in cases_defocus]
        focus = [{"power": p, "feed": f, "width": round(w, 2)}
                 for (p, f), w in self.grille_focus.values().items()]
        defocus = [{"power": p, "feed": f, "width": round(w, 2), "z_offset": dz}
                   for dz, gr in self.grilles_defocus.items()
                   for (p, f), w in gr.values().items()]
        core.save_burn_widths(mat, {"focus": conserves_f + focus,
                                    "defocus": conserves_d + defocus})
        garde = len(conserves_f) + len(conserves_d)
        QtWidgets.QMessageBox.information(
            self._boite(), "Mesures",
            "{} mesure(s) foyer + {} défocus enregistrées pour « {} ».{}".format(
                len(focus), len(defocus), mat,
                "\n{} mesure(s) hors grille conservée(s).".format(garde)
                if garde else ""))
        self.reload()
        if self._on_saved:
            self._on_saved()


def _panel_header(form, icon_name, title):
    """Bandeau en tête de panneau : icône du mode + nom en gras/agrandi,
    suivi d'un trait. Repère visuel immédiat du mode ouvert. À droite,
    la signature de l'atelier : le chapeau du Verdier (discret, avec
    info-bulle) -- même dégradation silencieuse que l'icône du mode si
    le rendu SVG échoue."""
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
    # Petit bouton « tout replier / déplier » des sections du panneau.
    # Masqué ici (les sections n'existent pas encore) ; _activer_sections
    # le rend opérant et visible s'il y a au moins une section.
    btn_sections = QtWidgets.QToolButton()
    btn_sections.setObjectName("laserToggleSections")
    btn_sections.setAutoRaise(True)
    btn_sections.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
    btn_sections.setText("▸")
    btn_sections.setStyleSheet(
        "QToolButton#laserToggleSections {"
        "  color: #ff8a00; font-weight: bold;"
        "  background: transparent; border: none; }")
    btn_sections.setToolTip("Replier / déplier toutes les sections")
    btn_sections.setVisible(False)
    lay.addWidget(btn_sections, 0)
    ver = QtWidgets.QLabel("v" + core.VERSION)
    ver.setStyleSheet("color: #8a9199; font-size: 10px;")
    ver.setToolTip("Atelier Laser v" + core.VERSION)
    lay.addWidget(ver, 0)
    pm_hat = _icon_pixmap("chapeau.svg", 22)
    if pm_hat is not None:
        hat = QtWidgets.QLabel()
        hat.setPixmap(pm_hat)
        hat.setToolTip("Atelier Laser v{} -- Atelier du Verdier -- "
                       "atelierduverdier.fr".format(core.VERSION))
        lay.addWidget(hat, 0)
    form.addRow(row)
    _hline(form)


# --- Sections repliables ---------------------------------------------------
# Barre de titre pleine largeur (libellé NOIR à gauche, chevron d'état à
# droite), cliquable, dont l'état ouvert/fermé est MÉMORISÉ dans la config
# (clé = titre de la section). _activer_sections (appelé par _scrollable)
# regroupe a posteriori les rangées sous chaque barre.

_SECTION_STATES = None


def _section_states():
    global _SECTION_STATES
    if _SECTION_STATES is None:
        try:
            _SECTION_STATES = dict(core.load_config().get("sections") or {})
        except Exception:
            _SECTION_STATES = {}
    return _SECTION_STATES


def _section_state_get(cle, defaut):
    return bool(_section_states().get(cle, defaut))


def _section_state_set(cle, valeur):
    etats = _section_states()
    if etats.get(cle) == bool(valeur):
        return
    etats[cle] = bool(valeur)
    try:
        cfg = core.load_config()
        cfg["sections"] = etats
        core.save_config(cfg)
    except Exception:
        pass  # config non inscriptible : l'état reste au moins en mémoire


class _SectionHeader(QtWidgets.QFrame):
    """Barre de titre de section, pleine largeur : libellé en NOIR à gauche,
    petit chevron d'état (▸ repliée / ▾ dépliée) à droite. Toute la barre
    est cliquable. Remplace l'ancien bouton au texte orange."""

    toggled = QtCore.Signal(bool)

    def __init__(self, titre, icon_name=None, ouvert=False):
        super().__init__()
        self._titre = titre
        self._open = bool(ouvert)
        self.setProperty("laser_section", True)
        self.setObjectName("laserSection")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        # Les sections d'ÉTAPE (titre commençant par ①②③...) sont mises en
        # avant : fond teinté orange, liseré épais -- c'est la PROCÉDURE, à
        # suivre dans l'ordre ; les autres sections (réglages manuels) restent
        # sobres. Demande terrain : le novice doit voir le fil d'un coup d'œil.
        self._etape = bool(titre) and titre.lstrip()[:1] in "①②③④⑤⑥⑦⑧⑨"
        # Barre « carte » : coins arrondis, liseré orange de la maison à
        # gauche, fond neutre du thème qui s'éclaircit au survol. Tout est
        # peint par la feuille de style, ciblée par objectName pour
        # fonctionner malgré le sous-classement Python.
        if self._etape:
            self.setStyleSheet(
                "QFrame#laserSection {"
                "  background-color: rgba(255, 138, 0, 0.16);"
                "  border: 1px solid #ff8a00;"
                "  border-left: 6px solid #ff8a00;"
                "  border-radius: 6px;"
                "}"
                "QFrame#laserSection:hover { background-color: rgba(255, 138, 0, 0.28); }")
        else:
            self.setStyleSheet(
                "QFrame#laserSection {"
                "  background-color: palette(button);"
                "  border: 1px solid palette(mid);"
                "  border-left: 3px solid #ff8a00;"
                "  border-radius: 6px;"
                "}"
                "QFrame#laserSection:hover { background-color: palette(midlight); }")

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(9, 6, 11, 6)
        lay.setSpacing(8)
        # Petit picto thématique de la section, à gauche (si le SVG se charge).
        if icon_name:
            pm = _icon_pixmap(icon_name, 18)
            if pm is not None:
                ico = QtWidgets.QLabel()
                ico.setPixmap(pm)
                ico.setStyleSheet("background: transparent; border: none;")
                ico.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
                lay.addWidget(ico)
        self._lbl = QtWidgets.QLabel(titre)
        self._lbl.setStyleSheet(
            "font-weight: bold; background: transparent; border: none;"
            + (" font-size: 13px;" if self._etape else ""))
        self._lbl.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self._picto = QtWidgets.QLabel()  # chevron d'état, orange, à droite
        self._picto.setStyleSheet(
            "color: #ff8a00; font-weight: bold; background: transparent; border: none;")
        self._picto.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._lbl)
        lay.addStretch(1)
        lay.addWidget(self._picto)
        self._maj_picto()

    def _maj_picto(self):
        self._picto.setText("▾" if self._open else "▸")  # ▾ / ▸

    def text(self):
        return self._titre

    def isChecked(self):
        return self._open

    def setChecked(self, on):
        # Met à jour l'état + le chevron SANS émettre toggled (usage interne).
        on = bool(on)
        if on != self._open:
            self._open = on
            self._maj_picto()

    def _basculer(self):
        """Inverse l'état, met à jour le chevron et émet toggled."""
        self._open = not self._open
        self._maj_picto()
        self.toggled.emit(self._open)

    def set_open(self, on):
        """Force l'état ouvert/fermé DEPUIS L'EXTÉRIEUR (bouton « tout
        replier / déplier ») en émettant `toggled` comme un clic, pour que
        le conteneur suive et que l'état soit mémorisé."""
        if bool(on) != self._open:
            self._basculer()

    def mousePressEvent(self, event):
        self._basculer()
        super().mousePressEvent(event)


def _section(form, title, icon_name=None, ouvert=False):
    """Ajoute une barre de section repliable au formulaire. `icon_name` est
    conservé pour compatibilité d'appel mais n'est plus affiché (barre
    sobre : titre noir + chevron d'état à droite). Les rangées ajoutées
    APRÈS ce titre (jusqu'au titre suivant) sont regroupées dans un
    conteneur montré/caché par le clic -- regroupement fait a posteriori
    par _activer_sections (appelé par _scrollable), donc les panneaux
    gardent leurs `form.addRow(...)` tels quels. L'état ouvert/fermé est
    mémorisé dans la config d'une session à l'autre ; SANS état mémorisé
    (installation fraîche), toute section démarre REPLIÉE -- `ouvert` ne
    sert plus qu'à d'éventuels usages hors panneaux."""
    form.addRow(_SectionHeader(title, icon_name=icon_name, ouvert=ouvert))


def _maj_bouton_sections(bouton, entetes):
    """Met à jour le petit bouton « tout replier / déplier » de l'en-tête :
    visible seulement s'il y a des sections ; même chevron texte (▸/▾) que
    _SectionHeader._maj_picto -- ▾ (« Tout replier ») si au moins une
    section est ouverte, sinon ▸ (« Tout déplier »). Un QToolButton natif
    avec setArrowType() détonnait visuellement (icône encadrée) au milieu
    des libellés plats de l'en-tête."""
    if not entetes:
        bouton.setVisible(False)
        return
    bouton.setVisible(True)
    qqch_ouvert = any(h.isChecked() for h in entetes)
    bouton.setText("▾" if qqch_ouvert else "▸")
    bouton.setToolTip("Tout replier" if qqch_ouvert else "Tout déplier")


# Drapeau : suspend l'accordéon pendant un pliage/dépliage GROUPÉ (bouton
# « tout déplier ») -- sinon chaque ouverture replierait la précédente et il
# ne resterait que la dernière section ouverte.
_ACCORDEON_SUSPENDU = [False]


def _basculer_toutes_sections(bouton, entetes):
    """Replie toutes les sections si au moins une est ouverte, sinon les
    déplie toutes."""
    if not entetes:
        return
    ouvrir = not any(h.isChecked() for h in entetes)
    _ACCORDEON_SUSPENDU[0] = True
    try:
        for h in entetes:
            h.set_open(ouvrir)
    finally:
        _ACCORDEON_SUSPENDU[0] = False
    _maj_bouton_sections(bouton, entetes)


def _activer_sections(inner):
    """Regroupe les rangées d'un formulaire de panneau sous leurs titres
    de section (_section) et branche le pliage/dépliage. Les rangées de
    chaque section sont DÉPLACÉES (takeRow) dans un sous-formulaire dont
    la visibilité suit le bouton-titre : cacher le conteneur ne touche
    pas au setVisible() individuel des rangées (logique dynamique des
    styles de trait préservée)."""
    form = inner.layout()
    if not isinstance(form, QtWidgets.QFormLayout):
        return
    # Extraire toutes les rangées dans l'ordre.
    rangees = []
    while form.rowCount():
        res = form.takeRow(0)
        rangees.append((res.labelItem, res.fieldItem))
    # Paires (en-tête, conteneur) du panneau -- pour le mode ACCORDÉON
    # (ouvrir une section replie les autres, préférence sections_accordeon).
    paires = []

    def _remettre(cible, label_item, field_item):
        label = label_item.widget() if label_item is not None else None
        if field_item is None:
            if label is not None:
                cible.addRow(label)
            return
        champ = field_item.widget() if field_item.widget() is not None \
            else field_item.layout()
        if label is not None:
            cible.addRow(label, champ)
        elif champ is not None:
            cible.addRow(champ)

    cible = form   # racine tant qu'aucun titre de section n'est passé
    for label_item, field_item in rangees:
        w = field_item.widget() if field_item is not None else None
        if w is not None and w.property("laser_section"):
            form.addRow(w)
            conteneur = QtWidgets.QWidget()
            cible = QtWidgets.QFormLayout(conteneur)
            cible.setContentsMargins(14, 0, 0, 6)
            cible.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
            cible.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
            form.addRow(conteneur)
            # État ouvert/fermé mémorisé (clé = titre). Sans état mémorisé
            # (installation fraîche, section jamais touchée) : TOUT REPLIÉ --
            # le panneau s'ouvre court, les étapes ①②③ surlignées guident,
            # et l'accordéon (activé par défaut) fait le reste au clic.
            cle = w.text()
            etat = _section_state_get(cle, False)
            w.setChecked(etat)
            conteneur.setVisible(etat)
            paires.append((w, conteneur))

            def _toggle(on, c=conteneur, k=cle, entete=w):
                c.setVisible(on)
                _section_state_set(k, on)
                # ACCORDÉON (préférence, activé par défaut) : ouvrir une
                # section replie les autres -- moins de défilement, le
                # panneau reste court. Suspendu pendant « tout déplier ».
                if (on and getattr(core, "SECTIONS_ACCORDEON", True)
                        and not _ACCORDEON_SUSPENDU[0]):
                    for h2, c2 in paires:
                        if h2 is not entete and h2.isChecked():
                            h2.setChecked(False)   # sans ré-émettre toggled
                            c2.setVisible(False)
                            _section_state_set(h2.text(), False)
                # Re-calage du layout : sans lui, le DERNIER rang d'une
                # section rouverte peut rester rogné (hauteur du conteneur
                # figée avant que le rang soit mesuré).
                inner.layout().activate()
                inner.layout().activate()  # 2e passe : les WrapLabel viennent
                # de fixer leur hauteur minimale (resizeEvent synchrone) au
                # 1er passage, cette 2e passe l'applique -- sans elle un
                # flash d'une frame reste visible avant l'auto-correction.
                inner.adjustSize()
                QtCore.QTimer.singleShot(0, inner.adjustSize)
            w.toggled.connect(_toggle)
            continue
        _remettre(cible, label_item, field_item)

    # Bouton « tout replier / déplier » de l'en-tête (_panel_header) : le
    # rendre opérant s'il y a des sections dans ce panneau, et garder son
    # chevron/info-bulle synchronisé quand on plie/déplie à la main.
    bouton = inner.findChild(QtWidgets.QToolButton, "laserToggleSections")
    if bouton is not None:
        entetes = inner.findChildren(_SectionHeader)
        if not entetes:
            bouton.setVisible(False)
        else:
            bouton.clicked.connect(
                lambda _checked=False, b=bouton, es=entetes:
                _basculer_toutes_sections(b, es))
            for h in entetes:
                h.toggled.connect(
                    lambda _on, b=bouton, es=entetes: _maj_bouton_sections(b, es))
            _maj_bouton_sections(bouton, entetes)


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
    # Hauteur MINIMALE imposée : sans elle, le formulaire peut serrer la
    # rangée et rogner le bas du dessin (légende coupée en deux, signalé
    # le 31/07/2026). La taille indépendante de la densité d'écran, sinon
    # un affichage HiDPI réserve deux fois trop peu de place.
    try:
        lbl.setMinimumHeight(int(pm.deviceIndependentSize().height()))
    except AttributeError:                      # Qt plus ancien
        lbl.setMinimumHeight(int(pm.height() / max(1.0, pm.devicePixelRatio())))
    form.addRow(lbl)
    return lbl


def _hline(form):
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    form.addRow(line)


class _WheelGuard(QtCore.QObject):
    """Neutralise la molette sur les QSpinBox/QDoubleSpinBox/QComboBox tant
    qu'ils n'ont PAS le focus clavier : au lieu d'ajuster la valeur par
    inadvertance quand on fait défiler le panneau, l'événement est renvoyé à
    la zone défilante (le panneau défile). Un clic dans le champ lui donne le
    focus -> la molette l'ajuste alors normalement. Réglé une fois, appliqué à
    tous les panneaux via _neutraliser_molette (dans _scrollable)."""

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Wheel and not obj.hasFocus():
            sa = obj.parentWidget()
            while sa is not None and not isinstance(sa, QtWidgets.QAbstractScrollArea):
                sa = sa.parentWidget()
            try:
                if sa is not None and sa.viewport() is not None:
                    QtCore.QCoreApplication.sendEvent(sa.viewport(), event)
            except RuntimeError:
                pass
            return True   # le champ ne touche pas à sa valeur
        return False


_WHEEL_GUARD = None


def _neutraliser_molette(inner):
    """Pose le garde-molette (_WheelGuard) sur tous les spinbox/combos de
    `inner` et retire la prise de focus à la molette (StrongFocus). Corrige la
    modification accidentelle des valeurs quand on fait défiler un panneau."""
    global _WHEEL_GUARD
    if _WHEEL_GUARD is None:
        _WHEEL_GUARD = _WheelGuard()
    for w in inner.findChildren(QtWidgets.QWidget):
        if isinstance(w, (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)):
            w.setFocusPolicy(QtCore.Qt.StrongFocus)
            w.installEventFilter(_WHEEL_GUARD)


class _ScrollArea(QtWidgets.QScrollArea):
    """QScrollArea des panneaux, avec un « tassement » différé au premier
    affichage. Problème corrigé : à la 1re peinture, les _WrapLabel calculent
    leur hauteur pour la largeur SANS barre de défilement ; puis le contenu
    déborde, la barre verticale apparaît et rétrécit la largeur utile -> les
    paragraphes auraient besoin de plus de hauteur, mais aucun re-layout n'est
    déclenché -> chevauchement de texte, jusqu'à ce qu'un événement externe
    (redimensionnement, capture d'écran...) force une nouvelle mise en page.
    On force donc une ou deux passes différées APRÈS l'apparition de la barre,
    qui recalculent la hauteur de tous les _WrapLabel à la largeur définitive
    puis ré-activent la mise en page."""

    def __init__(self):
        super().__init__()
        self._tasse = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._tasse:
            self._tasse = True
            QtCore.QTimer.singleShot(0, self._tasser)
            QtCore.QTimer.singleShot(120, self._tasser)  # après apparition de la barre

    def _tasser(self):
        w = self.widget()
        if w is None:
            return
        try:
            for lbl in w.findChildren(_WrapLabel):
                lbl._ajuster_hauteur()
            lay = w.layout()
            if lay is not None:
                lay.activate()
        except RuntimeError:
            pass  # widget C++ déjà détruit


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
    _activer_sections(inner)
    _neutraliser_molette(inner)
    # Boutons assortis aux barres de section : coins arrondis, bord qui
    # passe au orange de la maison au survol, léger retour au clic. Ciblé
    # sur les QPushButton DE `inner` -> n'affecte pas OK/Annuler du panneau
    # de tâches FreeCAD (qui sont en dehors de ce widget).
    inner.setStyleSheet(inner.styleSheet() + """
        QPushButton {
            background-color: palette(button);
            border: 1px solid palette(mid);
            border-radius: 5px;
            padding: 5px 12px;
        }
        QPushButton:hover { border-color: #ff8a00; background-color: palette(midlight); }
        QPushButton:pressed { background-color: palette(dark); }
        QPushButton:disabled { color: palette(mid); border-color: palette(mid); }
    """)
    layout = inner.layout()
    if layout is not None:
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout.addRow(spacer)

    scroll = _ScrollArea()
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


# --- Aperçu photo réaliste (rendu du résultat gravé) -----------------------
# Peint chaque trait à sa LARGEUR brûlée et à sa TEINTE, les recouvrements
# s'assombrissant (mode Multiply). La teinte vient d'abord de la NOIRCEUR
# MESURÉE du nuancier du matériau (_tone_measured -> core.darkness_at) ;
# sans ton exploitable, repli sur la FLUENCE ARÉOLAIRE P/(largeur·vitesse)
# saturante : le MDF carbonise dès le seuil dépassé, au-delà plus d'énergie
# ne noircit presque plus. (Un premier prototype utilisait l'irradiance de
# crête P/(spot²·v) mais elle pénalisait trop le défocus : sur bois réel un
# remplissage S865 F600 défocalisé à 36 mm ressort BIEN FONCÉ, pas pâle --
# recalé sur une gravure réelle. Le modèle théorique surestime en revanche
# la noirceur des tons CLAIRS -- 5 % mesuré là où il prédit ~55 % sur MDF
# S400 F2000 --, d'où la priorité au nuancier mesuré.)

def _tone_burn(power, feed, width):
    """Teinte 0..1 (0 = rien, 1 = noir) depuis la fluence aréolaire
    P/(largeur·vitesse), saturante. `width` = largeur brûlée du trait (mm).
    Modèle THÉORIQUE de repli -- essayer d'abord _tone_measured."""
    import math
    if feed <= 0 or width <= 0:
        return 0.0
    fluence = power / (width * feed)
    return 1.0 - math.exp(-3.0 * fluence)


def _tone_measured(material, power, feed, z_offset=0.0):
    """Teinte 0..1 depuis la noirceur MESURÉE du nuancier du matériau
    (niveau de défocus mesuré le plus proche, interpolation bornée aux
    mesures -- cf. core.darkness_at). None si pas de matériau ou aucun ton
    exploitable : l'appelant retombe alors sur le modèle _tone_burn."""
    if not material:
        return None
    try:
        d = core.darkness_at(material, power, feed, z_offset)
    except Exception:
        return None
    return None if d is None else d / 100.0


_BOIS_APERCU = (208, 178, 138)      # fond de tous les aperçus photo


def _teinte_gravure(material, power, feed, width, z_offset=0.0, cache=None):
    """Teinte 0..1 d'une marque gravée : nuancier MESURÉ d'abord
    (_tone_measured), modèle théorique en repli (_tone_burn).

    `cache` : dict de mémoïsation OBLIGATOIRE dès qu'on peint une trame --
    `core.darkness_at` relit le nuancier dans la config à CHAQUE appel, et
    une trame compte des dizaines de milliers de points. On mémoïse sur les
    paramètres arrondis : deux points qui ne diffèrent que par un millième
    de mm/min gravent la même chose."""
    cle = (round(power), round(feed), round(z_offset, 3), round(width, 3))
    if cache is not None and cle in cache:
        return cache[cle]
    t = _tone_measured(material, power, feed, z_offset)
    if t is None:
        t = _tone_burn(power, feed, width)
    t = max(0.0, min(1.0, t))
    if cache is not None:
        cache[cle] = t
    return t


def _discretize_edge(edge, dist=0.3):
    """Arête Part -> liste de (x, y) échantillonnés."""
    pts = None
    for kw in ({"Distance": dist}, {"Deflection": dist}):
        try:
            pts = edge.discretize(**kw)
            break
        except Exception:
            pts = None
    return [(p.x, p.y) for p in pts] if pts else []


def _render_engraving_photo(strokes, scale=24.0, margin_mm=3.0,
                            wood=_BOIS_APERCU, max_px=2200,
                            collision_points=None):
    """`strokes` : liste de (points[(x,y)...], largeur_mm, teinte0..1).
    `collision_points` : points (x,y) natifs (mêmes coordonnées que
    `strokes`) où le bec serait trop proche de la surface voisine (cf.
    warnings_out de generate_gcode_curved) -- marqués en magenta par
    dessus le rendu, même couleur que create_collision_markers (vue 3D)
    pour rester cohérent entre les deux aperçus. Renvoie une QImage :
    fond bois, traits épais assombris par Multiply (superpositions plus
    foncées). None si rien à peindre."""
    xs = [p[0] for s in strokes for p in s[0]]
    ys = [p[1] for s in strokes for p in s[0]]
    if not xs:
        return None
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w_mm = (maxx - minx) + 2 * margin_mm
    h_mm = (maxy - miny) + 2 * margin_mm
    sc = scale
    if max(w_mm, h_mm) * sc > max_px:
        sc = max_px / max(w_mm, h_mm)
    W = max(1, int(w_mm * sc))
    H = max(1, int(h_mm * sc))
    img = QtGui.QImage(W, H, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(*wood))
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setCompositionMode(QtGui.QPainter.CompositionMode_Multiply)

    def to_px(pt):
        return QtCore.QPointF((pt[0] - minx + margin_mm) * sc,
                              H - (pt[1] - miny + margin_mm) * sc)

    for pts, width_mm, tone in strokes:
        if not pts:
            continue
        v = max(0.0, min(1.0, 1.0 - tone))  # facteur de multiplication du fond
        pen = QtGui.QPen(QtGui.QColor.fromRgbF(v, v, v))
        pen.setWidthF(max(1.0, width_mm * sc))
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        p.setPen(pen)
        if len(pts) == 1:
            p.drawPoint(to_px(pts[0]))
        else:
            path = QtGui.QPainterPath(to_px(pts[0]))
            for q in pts[1:]:
                path.lineTo(to_px(q))
            p.drawPath(path)

    if collision_points:
        # SourceOver (pas Multiply) : le repère doit rester magenta franc
        # par-dessus le rendu, pas assombri comme les traits.
        p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(255, 0, 204))
        r = max(2.5, 1.2 * sc)
        for pt in collision_points:
            p.drawEllipse(to_px(pt), r, r)

    p.end()
    return img


def _show_image_dialog(img, title):
    """Affiche une QImage dans une boîte, avec un bouton pour l'enregistrer."""
    dlg = QtWidgets.QDialog()
    dlg.setWindowTitle(title)
    lay = QtWidgets.QVBoxLayout(dlg)
    lbl = QtWidgets.QLabel()
    pix = QtGui.QPixmap.fromImage(img)
    if max(pix.width(), pix.height()) > 900:
        pix = pix.scaled(900, 900, QtCore.Qt.KeepAspectRatio,
                         QtCore.Qt.SmoothTransformation)
    lbl.setPixmap(pix)
    lay.addWidget(lbl)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    btn_save = QtWidgets.QPushButton("Enregistrer en PNG…")
    btn_close = QtWidgets.QPushButton("Fermer")
    row.addWidget(btn_save)
    row.addWidget(btn_close)
    lay.addLayout(row)

    def _save():
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            dlg, "Enregistrer l'aperçu",
            os.path.join(getattr(core, "GCODE_DIR", ""), "apercu_photo.png"),
            "Images PNG (*.png)")
        if path:
            img.save(path, "PNG")

    btn_save.clicked.connect(_save)
    btn_close.clicked.connect(dlg.accept)
    dlg.exec()


def _make_photo_section(form, cle_getter, titre="Photo du résultat"):
    """Section réutilisable « Photo du résultat » pour les modes de test :
    une LISTE DÉROULANTE de toutes les photos mémorisées + une vignette
    cliquable (agrandissement) + une description libre (défocus, focale…,
    pour ne plus s'y perdre si on en garde plusieurs) + boutons Ajouter et
    Supprimer. `cle_getter()` renvoie la clé courante (ex. « testgrid:MDF »)
    servant à ranger/retrouver les photos. `titre` permet de numéroter la
    section selon le flux du panneau (ex. « ③ Photo du résultat »). Renvoie
    {"reload": fn} : l'appelant appelle reload() en fin d'__init__ et à
    chaque changement de matériau."""
    _section(form, titre, "sect_photo.svg")
    form.addRow(_WrapLabel(
        "Garde une ou plusieurs photos de la pièce gravée + mesurée, pour "
        "comparer au réel plus tard. Choisis-en une dans la liste ; clique la "
        "vignette pour l'agrandir."))

    combo = QtWidgets.QComboBox()
    combo.setToolTip("Photos mémorisées pour ce test/matériau.")
    form.addRow("Photo :", combo)

    lbl = QtWidgets.QLabel()
    lbl.setAlignment(QtCore.Qt.AlignCenter)
    lbl.setMinimumHeight(150)
    lbl.setFrameShape(QtWidgets.QFrame.StyledPanel)
    lbl.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
    lbl.setToolTip("Clique pour agrandir.")
    form.addRow(lbl)

    edt_desc = QtWidgets.QLineEdit()
    edt_desc.setPlaceholderText("ex. « défocus 15 mm », « au foyer »…")
    edt_desc.setToolTip(
        "Note libre pour retrouver le réglage utilisé pour CETTE photo "
        "(défocus, focale…) -- surtout utile si tu en gardes plusieurs.")
    form.addRow("Description :", edt_desc)

    btn_add = QtWidgets.QPushButton("Ajouter une photo…")
    btn_add.setToolTip("Choisis une photo (JPG/PNG…) du résultat réel : elle "
                       "est copiée dans le dossier de l'atelier et ajoutée à "
                       "la liste de ce test/matériau.")
    form.addRow(btn_add)
    btn_del = QtWidgets.QPushButton("Supprimer la photo affichée")
    form.addRow(btn_del)

    state = {"items": []}

    def _show_thumb():
        i = combo.currentIndex()
        items = state["items"]
        if 0 <= i < len(items):
            pm = QtGui.QPixmap(items[i]["path"])
            if not pm.isNull():
                lbl.setPixmap(pm.scaled(320, 180, QtCore.Qt.KeepAspectRatio,
                                        QtCore.Qt.SmoothTransformation))
                lbl.setText("")
                edt_desc.setText(items[i]["description"])
                edt_desc.setEnabled(True)
                btn_del.setEnabled(True)
                return
        lbl.setPixmap(QtGui.QPixmap())
        lbl.setText("— aucune photo —")
        edt_desc.setText("")
        edt_desc.setEnabled(False)
        btn_del.setEnabled(False)

    def reload(select=None):
        cle = (cle_getter() or "").strip()
        items = core.result_photos(cle) if cle else []
        state["items"] = items
        combo.blockSignals(True)
        combo.clear()
        for i in range(len(items)):
            combo.addItem("Photo {}".format(i + 1))
        if items:
            idx = select if (select is not None and 0 <= select < len(items)) else 0
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        combo.setEnabled(bool(items))
        _show_thumb()

    def _on_add():
        cle = (cle_getter() or "").strip()
        if not cle:
            QtWidgets.QMessageBox.warning(
                None, "Photo", "Indique d'abord le matériau/test concerné.")
            return
        path, _f = QtWidgets.QFileDialog.getOpenFileName(
            None, "Choisir une photo du résultat", "",
            "Images (*.jpg *.jpeg *.png *.bmp *.webp)")
        if path and core.add_result_photo(cle, path):
            reload(select=len(state["items"]))   # sélectionne la nouvelle (dernière)

    def _on_del():
        i = combo.currentIndex()
        items = state["items"]
        if 0 <= i < len(items):
            core.delete_result_photo((cle_getter() or "").strip(), items[i]["file"])
            reload()

    def _on_desc_edited():
        i = combo.currentIndex()
        items = state["items"]
        if 0 <= i < len(items):
            core.set_photo_description(
                (cle_getter() or "").strip(), items[i]["file"], edt_desc.text())
            items[i]["description"] = edt_desc.text()

    def _on_click(_ev):
        i = combo.currentIndex()
        items = state["items"]
        if 0 <= i < len(items):
            img = QtGui.QImage(items[i]["path"])
            if not img.isNull():
                _show_image_dialog(img, "Photo du résultat")
    lbl.mousePressEvent = _on_click

    combo.currentIndexChanged.connect(lambda _i: _show_thumb())
    edt_desc.editingFinished.connect(_on_desc_edited)
    btn_add.clicked.connect(_on_add)
    btn_del.clicked.connect(_on_del)
    return {"reload": reload}


def _strokes_from_operation(op):
    """Traits (points, largeur_mm, teinte0..1) d'une opération de job
    combiné, pour l'aperçu photo. Gravure (filled/curved) peinte réaliste ;
    découpe (flat/curved_cut) en fin trait très sombre ; grille de test et
    types inconnus ignorés (rien d'utile à peindre ici)."""
    typ = op.get("type")
    p = op.get("params", {})
    half = core.calibrated_half_angle()
    strokes = []
    if typ == "filled":
        defocus = p.get("defocus", 0.0)
        spot_fill = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half)
        fp, ff = p.get("fill_power", 0.0), p.get("fill_feed", 1.0)
        fw = core.burn_width_defocus_scaled(fp, ff, defocus) or spot_fill
        ft = _tone_burn(fp, ff, fw)
        for e in (p.get("fill_edges") or []):
            pts = _discretize_edge(e)
            if pts:
                strokes.append((pts, fw, ft))
        if p.get("draw_contour", True) and p.get("contour_edges"):
            coff = p.get("contour_z_offset", 0.0)
            spot_c = core.spot_diameter_at_defocus(coff, core.SPOT_FOCUS_MM, half)
            cp, cf = p.get("contour_power", 0.0), p.get("contour_feed", 1.0)
            cw = core.burn_width_defocus_scaled(cp, cf, coff) or spot_c
            ct = _tone_burn(cp, cf, cw)
            for e in p["contour_edges"]:
                pts = _discretize_edge(e)
                if pts:
                    strokes.append((pts, cw, ct))
    elif typ == "curved":
        # Marquage : largeur selon le défocus effectif (z_focus au-dessus du
        # foyer -> point élargi) ET selon le STYLE (tirets, pointillé, vague,
        # dégradé) -- sinon tous les styles se ressembleraient dans l'aperçu.
        pw, fd = p.get("power", 0.0), p.get("feed", 1.0)
        defocus = max(0.0, p.get("z_focus", core.Z_WORK_MM) - core.Z_WORK_MM)
        style = p.get("style", "plein")
        spar = dict(p.get("style_params") or {})
        edges = p.get("edges") or []

        def _wid(dz):
            dz = max(0.0, dz)
            return (core.burn_width_defocus_scaled(pw, fd, dz)
                    or core.spot_diameter_at_defocus(dz, core.SPOT_FOCUS_MM, half)
                    or core.SPOT_FOCUS_MM)

        w = _wid(defocus)
        t = _tone_burn(pw, fd, w)
        if style in ("tirets", "pointille", "vague", "degrade"):
            chains = core.chain_edges(edges)
            if style == "tirets":
                for ch in chains:
                    for piece, on in core.dash_chain(ch, spar.get("dash_len", 3.0),
                                                      spar.get("gap_len", 2.0)):
                        if on and len(piece) >= 2:
                            strokes.append(([(q.x, q.y) for q in piece], w, t))
            elif style == "pointille":
                for ch in chains:
                    for d in core.dot_positions(ch, spar.get("dot_spacing", 1.5)):
                        strokes.append(([(d.x, d.y)], max(w, core.SPOT_FOCUS_MM), t))
            elif style == "vague":
                amp = spar.get("wave_amplitude", 0.0)
                for ch in chains:
                    s = core.wave_resample(ch, spar.get("wave_period", 5.0), amp)
                    for (pa, dza), (pb, dzb) in zip(s, s[1:]):
                        ww = _wid((dza + dzb) / 2.0)
                        strokes.append(([(pa.x, pa.y), (pb.x, pb.y)], ww,
                                        _tone_burn(pw, fd, ww)))
            else:                                   # degrade : largeur le long d'une direction
                ang = math.radians(spar.get("deg_angle", 0.0))
                ux, uy = math.cos(ang), math.sin(ang)
                allp = [q for ch in chains for q in ch]
                projs = [q.x * ux + q.y * uy for q in allp] or [0.0]
                pmin = min(projs)
                span = max(max(projs) - pmin, 1e-9)
                z0 = spar.get("deg_z_min", 0.0)
                z1 = spar.get("deg_z_max", 0.0)
                for ch in chains:
                    for qa, qb in zip(ch, ch[1:]):
                        frac = ((qa.x * ux + qa.y * uy) - pmin) / span
                        ww = _wid(z0 + (z1 - z0) * frac)
                        strokes.append(([(qa.x, qa.y), (qb.x, qb.y)], ww,
                                        _tone_burn(pw, fd, ww)))
        else:                                       # plein / défocus (point élargi)
            for e in edges:
                pts = _discretize_edge(e)
                if pts:
                    strokes.append((pts, w, t))
    elif typ in ("flat", "curved_cut"):
        # Découpe traversante : fin trait très sombre (le trait de coupe).
        for e in (p.get("edges") or []):
            pts = _discretize_edge(e)
            if pts:
                strokes.append((pts, max(core.SPOT_FOCUS_MM, 0.2), 0.9))
    return strokes


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


def _avertir_relief_sans_reference(parent_widget, edges, reference_shape):
    """Avant de générer un marquage/découpe courbe (génération directe OU
    ajout au job combiné) : si le motif varie vraiment en Z mais qu'aucun
    solide 3D de référence n'est sélectionné avec lui, le Z n'est
    qu'interpolé entre les points du motif ET le contrôle anti-collision
    du bec (cône) est silencieusement désactivé (pas de sonde exacte pour
    le nourrir, cf. generate_gcode_curved) -- un motif qui plonge dans une
    poche sans le solide sélectionné ne déclenche alors AUCUNE alerte, ni
    à l'écran ni même dans le G-code. À appeler à CHAQUE endroit où un tel
    motif quitte le panneau (génération directe ET `_build_combined_operation`)
    -- sinon le job combiné recontourne silencieusement l'alerte. Renvoie
    False si l'utilisateur annule la génération."""
    if reference_shape is not None:
        return True
    zs = []
    for e in edges:
        try:
            pts = e.discretize(Distance=core.DISCRETIZE_DISTANCE)
        except Exception:
            pts = [v.Point for v in getattr(e, "Vertexes", [])]
        zs.extend(p.z for p in pts)
    if not zs or max(zs) - min(zs) <= 0.5:
        return True
    reponse = QtWidgets.QMessageBox.warning(
        parent_widget, "Pas d'objet 3D de référence",
        "Le motif varie de {:.1f} mm en Z, mais le solide 3D d'origine "
        "n'est pas sélectionné avec lui.\n\n"
        "Sans lui, le Z n'est qu'interpolé entre les points du motif et le "
        "contrôle anti-collision du bec est DÉSACTIVÉ -- un plongeon dans "
        "une poche ou un décroché ne déclenchera AUCUNE alerte.\n\n"
        "Sélectionne le motif ET le solide 3D ensemble pour un suivi exact "
        "et le contrôle anti-collision.\n\nGénérer quand même ?".format(
            max(zs) - min(zs)),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No)
    return reponse == QtWidgets.QMessageBox.Yes


def _avertir_collision_detectee(parent_widget, count, quoi="gravure", determinant="cette"):
    """Après génération (sonde exacte active) : à `count` endroits, le bec
    (cône anti-collision) serait plus proche de la surface voisine que ne
    le permet le focus imposé -- jusqu'ici seulement écrit dans la vue
    Rapport de FreeCAD (pas toujours ouverte, facile à rater avant de
    lancer le job sur la machine pour de vrai). Fenêtre bloquante à la
    place. `determinant` accorde l'article à `quoi` ("cette gravure" /
    "cette découpe" / "ce job combiné"). Renvoie False si l'utilisateur
    annule la génération."""
    if not count:
        return True
    reponse = QtWidgets.QMessageBox.warning(
        parent_widget, "Risque de collision détecté",
        "À {} endroit(s), le bec (cône anti-collision) serait plus proche "
        "de la surface voisine que ne le permet le focus de {} {}.\n\n"
        "Le Z n'a PAS été modifié (le focus reste imposé) -- vérifie "
        "visuellement ces zones avant de lancer le job sur la machine.\n\n"
        "Générer quand même ?".format(count, determinant, quoi),
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        QtWidgets.QMessageBox.No)
    return reponse == QtWidgets.QMessageBox.Yes


def _write_gcode_with_dialog(parent_widget, gcode, default_path, recadrer_origine=True):
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
    # Recadrage au zéro pièce (Préférences « Origine G-code ») : amène le
    # coin bas-gauche du parcours (min X, min Y) sur (0,0), pour que le job
    # démarre au zéro machine quel que soit l'emplacement du dessin dans le
    # document. Les modes où la position est INTENTIONNELLE (Projection sur
    # pièce 3D, Test d'offsets fraise/laser) passent recadrer_origine=False.
    # G-code personnalisé GLOBAL (Préférences) : inséré ici, au point de
    # passage commun à tous les modes -- une seule fois par job, avant
    # l'armement / avant le M2 final.
    gcode = core.inserer_gcode_perso_global(gcode)
    if recadrer_origine and getattr(core, "GCODE_ORIGIN_BBOX", True):
        gcode = core.translate_gcode_origin(gcode)
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
    # Traçabilité : la version de l'atelier en toute première ligne de
    # chaque fichier écrit (une seule fois -- les jobs combinés passent
    # aussi par ici, jamais leurs corps individuels).
    stamp = "(LaserAtelier v{})".format(core.VERSION)
    if not gcode.startswith(stamp):
        gcode = stamp + "\n" + gcode
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
        # Quand l'entrée porte une donnée TEXTUELLE (nom de matériau, clé de
        # tramage), c'est elle qu'on enregistre : elle survit à une
        # réorganisation de la liste, un rang non. Les combos sans donnée, et
        # celles dont la donnée est un dict de réglage (cf. _make_shade_picker,
        # qu'il ne faut surtout pas recopier dans la config), gardent leur rang.
        d = w.currentData()
        return d if isinstance(d, str) else w.currentIndex()
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
            # Une valeur TEXTUELLE désigne l'entrée par sa donnée (ou, à
            # défaut, par son libellé) : un préréglage ou un réglage d'objet
            # survit alors à une réorganisation de la liste, ce qu'un rang ne
            # fait pas -- il désignerait silencieusement autre chose. Les
            # configs déjà écrites stockent des rangs, les deux formes restent
            # donc acceptées. Une chaîne qui ne correspond à rien ne change
            # rien : le défaut du widget vaut mieux qu'une entrée au hasard.
            if isinstance(v, str):
                for i in range(w.count()):
                    if w.itemData(i) == v or w.itemText(i) == v:
                        w.setCurrentIndex(i)
                        break
                return
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


def _form_du_widget(widget, form):
    """Le QFormLayout qui contient RÉELLEMENT la rangée du widget : les
    sections repliables (_activer_sections) déplacent les rangées dans
    des sous-formulaires, donc le `form` racine capturé par les closures
    des panneaux n'est plus forcément le bon."""
    parent = widget.parentWidget()
    lay = parent.layout() if parent is not None else None
    return lay if isinstance(lay, QtWidgets.QFormLayout) else form


def _set_row_visible(form, widget, visible):
    """Masque une LIGNE ENTIÈRE (libellé + champ) d'un QFormLayout.
    setVisible sur le seul champ laisse le libellé orphelin (lignes vides
    « Longueur tiret : » etc. quand un autre style est choisi).
    setRowVisible (Qt 6.4+) replie proprement la ligne ; repli manuel
    sur le libellé sinon."""
    form = _form_du_widget(widget, form)
    try:
        form.setRowVisible(widget, visible)
    except (AttributeError, TypeError, RuntimeError):
        widget.setVisible(visible)
        lbl = form.labelForField(widget)
        if lbl is not None:
            lbl.setVisible(visible)


# Réglages PAR FORME : propriété dynamique posée sur l'objet sélectionné au
# moment de la génération, sauvegardée AVEC le document (.FCStd). Rouvrir un
# panneau avec cette forme sélectionnée re-propose SES réglages (prioritaires
# sur les derniers réglages globaux du panneau).
_OBJ_PROP = "LaserAtelierReglages"


def _reglages_object(selection):
    """Premier objet de document de la sélection : le porteur des réglages
    par forme. None si la sélection est vide (panneaux sans forme)."""
    for so in (selection or []):
        obj = getattr(so, "Object", None)
        if obj is not None:
            return obj
    return None


def _sous_elements(selection):
    """Sous-éléments sélectionnés (Face1, Edge3...) du premier objet de la
    sélection, triés. Vide = objet entier. C'est ce qui permet à un MÊME
    sketch/SVG de porter plusieurs recettes : une par sous-sélection."""
    for so in (selection or []):
        if getattr(so, "Object", None) is not None:
            return sorted(getattr(so, "SubElementNames", None) or [])
    return []


def _cle_reglages(panel_key, selection):
    """Clé de stockage des réglages sur la forme : le mode seul pour une
    sélection d'objet entier, « mode@Face1+Face3 » pour une sous-sélection
    -- chaque zone d'un même objet garde ainsi SA recette."""
    subs = _sous_elements(selection)
    return panel_key + "@" + "+".join(subs) if subs else panel_key


def _restore_last_values(panel_key, fields, selection=None):
    """Pré-remplit les champs du panneau. Priorité : réglages portés par la
    FORME sélectionnée (propriété LaserAtelierReglages du document), sinon
    derniers réglages globaux du panneau (config utilisateur)."""
    values = core.load_config().get("last_" + panel_key)
    obj = _reglages_object(selection)
    if obj is not None and hasattr(obj, _OBJ_PROP):
        try:
            data = json.loads(getattr(obj, _OBJ_PROP) or "{}")
            cle = _cle_reglages(panel_key, selection)
            obj_values = data.get(cle)
            if obj_values is None and cle != panel_key:
                # sous-sélection jamais réglée : repli sur la recette de
                # l'objet entier si elle existe
                obj_values = data.get(panel_key)
            if isinstance(obj_values, dict):
                values = obj_values
                FreeCAD.Console.PrintMessage(
                    "Réglages restaurés depuis « {} »{}.\n".format(
                        getattr(obj, "Label", "objet"),
                        " [" + ", ".join(_sous_elements(selection)) + "]"
                        if _sous_elements(selection) else ""))
        except Exception:
            pass  # propriété corrompue : repli sur les derniers réglages
    if not isinstance(values, dict):
        return
    for name, widget in fields.items():
        if name in values:
            _widget_set(widget, values[name])


def _save_last_values(panel_key, fields, selection=None):
    values = {name: _widget_get(w) for name, w in fields.items()}
    cfg = core.load_config()
    cfg["last_" + panel_key] = values
    core.save_config(cfg)
    obj = _reglages_object(selection)
    if obj is None:
        return
    try:
        if not hasattr(obj, _OBJ_PROP):
            obj.addProperty("App::PropertyString", _OBJ_PROP, "LaserAtelier",
                            "Réglages de l'atelier laser, par mode (JSON)")
            obj.setEditorMode(_OBJ_PROP, 1)  # visible mais pas éditable à la main
        try:
            data = json.loads(getattr(obj, _OBJ_PROP, "") or "{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[_cle_reglages(panel_key, selection)] = values
        setattr(obj, _OBJ_PROP, json.dumps(data, ensure_ascii=False))
        FreeCAD.Console.PrintMessage(
            "Réglages attachés à « {} » -- sauvegarder le document pour les "
            "conserver.\n".format(getattr(obj, "Label", "objet")))
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "Réglages non attachés à l'objet : {}\n".format(exc))
    # Niveau 2 : un objet « Job » dans l'arborescence référence les sources
    # et ce mode -- double-clic dessus = rouvrir le panneau pré-rempli.
    try:
        import laser_jobs
        laser_jobs.creer_ou_maj_job(
            panel_key,
            [getattr(so, "Object", None) for so in (selection or [])],
            sous_elements=_sous_elements(selection))
    except Exception as exc:
        FreeCAD.Console.PrintWarning(
            "Job non créé dans l'arborescence : {}\n".format(exc))


# --- Job combiné : opérations empilées depuis les vrais modes ---------------
# En MÉMOIRE pour la session FreeCAD (les params portent des edges/probe =
# objets Part, non sérialisables en config). Chaque mode y ajoute son réglage
# COMPLET via « Ajouter au job combiné » ; le mode Job combiné lit cette liste.
_COMBINED_OPS = []

# Largeur par défaut de la planche nuancier, en cercles. 10 plutôt que les 5
# historiques : au-delà d'une trentaine de tons, 5 colonnes donnent une bande
# étroite et très haute (83 tons = 152 x 640 mm) qui gaspille la chute et se
# range mal ; 10 colonnes rendent la même planche à peu près carrée
# (292 x 348 mm) sans retirer un seul cercle.
NUANCIER_COLONNES_DEFAUT = 10


def _nuancier_geometrie(n_items, colonnes=None, n_lignes=1):
    """Disposition de la planche nuancier pour `n_items` cercles dont
    l'étiquette compte `n_lignes` lignes : constantes de dessin, nombre de
    colonnes/lignes retenu et encombrement du cadre.

    SOURCE UNIQUE, appelée par le constructeur de la planche ET par l'aperçu
    de taille du panneau : une taille annoncée qui recalculerait la mise en
    page de son côté finirait par mentir dès qu'on touche une constante ici
    (c'est exactement ce qui était arrivé aux graduations de la rampe).

    Le cercle est passé de Ø20 à Ø14 : Ø20 était plus large que nécessaire
    pour juger une teinte à l'œil, et c'est LUI qui fixait la largeur de
    cellule (cell_w = DIAM + GAP_X), donc la place laissée à l'étiquette.
    Combiné à l'étiquette empilée (cf. _nuancier_items), 83 tons de hêtre
    passent de 292 x 348 mm -- avec 76 % des étiquettes qui débordaient sur
    leur voisine -- à 243 x 328 mm, étiquettes lisibles et sans chevauchement."""
    n = max(int(n_items), 1)
    nl = max(int(n_lignes), 1)
    DIAM = 14.0
    GAP_X = 8.0            # espace horizontal entre cercles
    LABEL_GAP = 2.5        # cercle -> étiquette
    LABEL_H = 3.0          # hauteur nominale d'UNE ligne d'étiquette
    LABEL_INTERLIGNE = 0.8
    GAP_Y = 6.0            # espace vertical entre cellules
    MARGIN = 10.0          # marge intérieure au cadre
    TITLE_H = 5.0
    TITLE_GAP = 5.0
    cols = min(max(int(colonnes or NUANCIER_COLONNES_DEFAUT), 1), n)
    bloc_h = nl * LABEL_H + (nl - 1) * LABEL_INTERLIGNE
    cell_w = DIAM + GAP_X
    cell_h = DIAM + LABEL_GAP + bloc_h + GAP_Y
    nrows = (n + cols - 1) // cols
    content_h = nrows * cell_h - GAP_Y
    board_w = 2 * MARGIN + cols * DIAM + (cols - 1) * GAP_X
    board_h = content_h + 2 * MARGIN + TITLE_H + TITLE_GAP
    return {"DIAM": DIAM, "GAP_X": GAP_X, "LABEL_GAP": LABEL_GAP,
            "LABEL_H": LABEL_H, "LABEL_INTERLIGNE": LABEL_INTERLIGNE,
            "GAP_Y": GAP_Y, "MARGIN": MARGIN,
            "TITLE_H": TITLE_H, "TITLE_GAP": TITLE_GAP,
            "n_lignes": nl, "bloc_h": bloc_h,
            "cols": cols, "nrows": nrows, "cell_w": cell_w, "cell_h": cell_h,
            "board_w": board_w, "board_h": board_h,
            "y_sommet": board_h - MARGIN - TITLE_H - TITLE_GAP}


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


def _nuancier_items(source, material):
    """Liste (label_objet UNIQUE, texte gravé, recette 'filled') des cercles
    à graver, selon la source :

    - « tons »   : un cercle par TON MESURÉ du nuancier du matériau
      (core.load_shades) -- c'est la palette riche (ex. 34 gris MDF). Chaque
      ton reproduit sa puissance/vitesse mesurées ; on force fluence_on=False
      (sinon la compensation écrase la puissance du ton) et un espacement
      calé sur le DÉFOCUS de mesure du ton (z_offset) via
      spot_diameter_at_defocus x0.85, pour que le rendu = la mesure.
    - « preregles » : un cercle par préréglage matériau enregistré
      (core.load_presets('filled')), chacun avec ses propres réglages tels
      quels (fluence comprise). En général peu nombreux.

    Ordonnés du plus clair au plus foncé. Renvoie (items, erreur)."""
    if source == "tons":
        shades = core.load_shades(material)
        if not shades:
            return None, ("aucun ton mesuré pour « {} » -- saisis d'abord des "
                          "tons dans le mode « Nuancier » (ou choisis un autre "
                          "matériau).".format(material or "?"))
        half = core.calibrated_half_angle()
        items = []
        for i, s in enumerate(shades):     # load_shades trie déjà par noirceur
            z = float(s.get("z_offset", 0.0) or 0.0)
            spot = core.spot_diameter_at_defocus(max(0.0, z), core.SPOT_FOCUS_MM, half)
            recette = {"spacing": max(0.05, spot * 0.85), "angle": 45.0,
                       "fill_power": float(s.get("power", 500)),
                       "fill_feed": float(s.get("feed", 800)),
                       "perimeter": True, "contour": False,
                       "fill_style": 0, "fluence_on": False}
            # Étiquette EMPILÉE, une donnée par ligne. Sur une seule ligne,
            # « 100% S1000 F1000 » fait 58 mm de large pour une cellule qui en
            # offrait 27 : 89 des 117 tons mesurés débordaient sur leur voisin,
            # et le plancher de lisibilité (2,2 mm) interdisait de rétrécir
            # davantage. Empilé, le bloc ne fait plus que 14 mm de large et le
            # texte reprend sa taille nominale.
            resume = "{:g}% S{:g} F{:g}".format(
                s.get("darkness", 0), s.get("power", 0), s.get("feed", 0))
            lignes = ["{:g}%".format(s.get("darkness", 0)),
                      "S{:g}".format(s.get("power", 0)),
                      "F{:g}".format(s.get("feed", 0))]
            items.append(("{:02d} {}".format(i + 1, resume), lignes, recette))
        return items, None
    presets = core.load_presets("filled")
    if not presets:
        return None, ("aucun préréglage « filled » enregistré -- enregistres-en "
                      "dans Gravure remplie (section « Préréglage matériau »).")

    def _pn(v):
        return v.get("fill_power", 0.0) / max(v.get("fill_feed", 1.0), 1e-6)
    return [(nom, [nom], presets[nom])
            for nom in sorted(presets, key=lambda n: (_pn(presets[n]), n))], None


def _construire_nuancier_preregles(label_power=None, label_feed=None,
                                   source="tons", material="", colonnes=None):
    """Construit un document « nuancier physique » : un cercle Ø14 (face) par
    entrée (ton mesuré ou préréglage, cf. _nuancier_items), portant SA recette
    (LaserAtelierReglages) + un Job « filled » ; une étiquette gravée sous
    chaque cercle, un cadre et un titre daté regroupés en un objet Marquage +
    Job. Cercles du plus clair au plus foncé. Le G-code sort ensuite du job
    combiné. Renvoie (document, [Jobs], avertissement) ; jobs=None si rien à
    graver (message dans l'avertissement).

    `colonnes` : largeur de la grille de cercles. Le nombre de colonnes était
    plafonné à 5 : passé quelques dizaines de tons, la planche devenait une
    bande étroite et très haute (83 tons de hêtre = 152 x 640 mm), pénible à
    débiter dans une chute et à ranger. Les mêmes cercles sur 10 colonnes
    tiennent en 243 x 328 mm. None = NUANCIER_COLONNES_DEFAUT."""
    import Part
    import datetime
    import laser_jobs
    if label_power is None:
        label_power = core.LABEL_POWER
    if label_feed is None:
        label_feed = core.LABEL_FEED

    items, err = _nuancier_items(source, material)
    if not items:
        return None, None, err

    g = _nuancier_geometrie(len(items), colonnes,
                            max(len(l) for _lo, l, _r in items))
    DIAM, R = g["DIAM"], g["DIAM"] / 2.0
    GAP_X, LABEL_GAP, LABEL_H = g["GAP_X"], g["LABEL_GAP"], g["LABEL_H"]
    LABEL_INTERLIGNE = g["LABEL_INTERLIGNE"]
    GAP_Y, MARGIN = g["GAP_Y"], g["MARGIN"]
    TITLE_H, TITLE_GAP = g["TITLE_H"], g["TITLE_GAP"]
    COLS, cell_w, cell_h = g["cols"], g["cell_w"], g["cell_h"]
    nrows, board_w, board_h = g["nrows"], g["board_w"], g["board_h"]
    y_sommet = g["y_sommet"]

    # Titre : peu de tons -> peu de colonnes -> cadre étroit, mais le texte
    # (matériau + date + décompte) reste toujours aussi long. On réduit sa
    # hauteur en priorité (même logique que les étiquettes ci-dessous) ;
    # si même réduit au minimum lisible il déborde encore, on élargit le
    # cadre plutôt que de le laisser dépasser -- calculé AVANT le cadre
    # (coins) pour que celui-ci soit tracé à la bonne largeur finale.
    quoi = ("tons " + material) if source == "tons" else "prereglages"
    titre = "Nuancier {}  {}  ({} cercles)".format(
        quoi, datetime.date.today().isoformat(), len(items))
    title_h = TITLE_H
    tw, _th = core.single_line_text_extent(titre, title_h)
    title_maxw = board_w - 2 * MARGIN
    if tw > title_maxw and tw > 0:
        title_h = max(2.2, title_h * title_maxw / tw)
        tw, _th = core.single_line_text_extent(titre, title_h)
    if tw > title_maxw:
        board_w = tw + 2 * MARGIN

    doc = FreeCAD.newDocument(
        "Nuancier_tons" if source == "tons" else "Nuancier_preregles")
    jobs, ignores = [], []

    def _centre(i):
        col, row = i % COLS, i // COLS
        return (MARGIN + col * cell_w + R, y_sommet - row * cell_h - R)

    # 1) Un cercle-face par entrée, avec sa recette + un Job « filled ».
    for i, (label_obj, _grave, recette) in enumerate(items):
        cx, cy = _centre(i)
        try:
            face = Part.Face(Part.Wire(Part.makeCircle(R, FreeCAD.Vector(cx, cy, 0))))
        except Exception as exc:
            ignores.append("{} (cercle : {})".format(label_obj, exc))
            continue
        obj = doc.addObject("Part::Feature", "Ton")
        obj.Shape = face
        obj.Label = label_obj
        try:
            obj.addProperty("App::PropertyString", _OBJ_PROP, "LaserAtelier",
                            "Réglages de l'atelier laser, par mode (JSON)")
            obj.setEditorMode(_OBJ_PROP, 1)
            setattr(obj, _OBJ_PROP,
                    json.dumps({"filled": recette}, ensure_ascii=False))
        except Exception as exc:
            ignores.append("{} (recette : {})".format(label_obj, exc))
            continue
        job = laser_jobs.creer_ou_maj_job("filled", [obj])
        if job is not None:
            jobs.append(job)

    # 2) Étiquettes + cadre + titre daté : un seul objet Marquage + Job.
    deco = []
    coins = [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(board_w, 0, 0),
             FreeCAD.Vector(board_w, board_h, 0), FreeCAD.Vector(0, board_h, 0),
             FreeCAD.Vector(0, 0, 0)]
    for a, b in zip(coins[:-1], coins[1:]):
        deco.append(Part.LineSegment(a, b).toShape())
    deco += core.single_line_text_to_edges(
        titre, title_h, x0=MARGIN, y0=board_h - MARGIN - title_h)
    maxw = cell_w - 1.0
    for i, (_label_obj, lignes, _recette) in enumerate(items):
        cx, cy = _centre(i)
        y = cy - R - LABEL_GAP
        for txt in lignes:
            txt = txt[:40]
            h = LABEL_H
            w, _h = core.single_line_text_extent(txt, h)
            if w > maxw and w > 0:                 # trop long : on réduit
                h = max(2.2, h * maxw / w)
                w, _h = core.single_line_text_extent(txt, h)
            # Plancher de lisibilité atteint et ça déborde encore (nom de
            # préréglage à rallonge) : on tronque. Laisser dépasser ferait
            # se chevaucher deux étiquettes voisines, illisibles toutes les deux.
            while w > maxw and len(txt) > 1:
                txt = txt[:-1]
                w, _h = core.single_line_text_extent(txt, h)
            deco += core.single_line_text_to_edges(
                txt, h, x0=cx - w / 2.0, y0=y - h)
            y -= LABEL_H + LABEL_INTERLIGNE        # pas NOMINAL : les lignes
            # restent alignées d'une cellule à l'autre même si l'une a rétréci,
            # et le pas correspond au bloc_h qu'a compté _nuancier_geometrie.
    if deco:
        obj = doc.addObject("Part::Feature", "EtiquettesNuancier")
        obj.Shape = Part.Compound(deco)
        obj.Label = "Étiquettes + cadre"
        try:
            obj.addProperty("App::PropertyString", _OBJ_PROP, "LaserAtelier",
                            "Réglages de l'atelier laser, par mode (JSON)")
            obj.setEditorMode(_OBJ_PROP, 1)
            setattr(obj, _OBJ_PROP, json.dumps(
                {"curved": {"power": float(label_power), "feed": float(label_feed),
                            "style": 0, "fluence_on": False}}, ensure_ascii=False))
        except Exception:
            pass
        job = laser_jobs.creer_ou_maj_job("curved", [obj])
        if job is not None:
            jobs.append(job)

    doc.recompute()
    if getattr(FreeCAD, "GuiUp", False):
        try:
            Gui.activeDocument().activeView().viewTop()
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass
    warn = ("entrées ignorées :\n- " + "\n- ".join(ignores)) if ignores else None
    return doc, jobs, warn


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

        btn_save = QtWidgets.QPushButton("Sauvegarder")
        btn_save.setToolTip("Enregistre toutes les valeurs du panneau sous un nom.")
        _btn_icon(btn_save, "sect_preset.svg")
        btn_save.clicked.connect(self._on_save)
        btn_del = QtWidgets.QPushButton("Supprimer")
        btn_del.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        btn_del.clicked.connect(self._on_delete)
        _presets_row = QtWidgets.QWidget()
        _presets_h = QtWidgets.QHBoxLayout(_presets_row)
        _presets_h.setContentsMargins(0, 0, 0, 0)
        _presets_h.addWidget(btn_save)
        _presets_h.addWidget(btn_del)
        form.addRow(_presets_row)

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
    # QFormLayout n'honore pas le heightForWidth des paragraphes repliés
    # (rangée trop basse d'une ligne -> le widget suivant chevauche le bas
    # du texte). On met donc les paragraphes pleine largeur dans un
    # QVBoxLayout (qui, lui, respecte la hauteur repliée), et on réserve un
    # QFormLayout imbriqué aux seules paires libellé:champ (son usage prévu).
    outer = QtWidgets.QVBoxLayout(box)

    lbl = _WrapLabel(
        "À utiliser quand le matériau n'a PAS de nuancier. Défocaliser\n"
        "étale la puissance sur un point plus large : le trait pâlit.\n"
        "Renseigne UN réglage de RÉFÉRENCE connu bon (une gravure\n"
        "réussie) ; l'atelier garde le même ton en recalculant la\n"
        "puissance (fluence égale) pour la largeur et la vitesse\n"
        "actuelles.\n"
        "\n"
        "Avec un NUANCIER (ou le ton sur mesure interpolé) : laisse la\n"
        "case DÉCOCHÉE -- l'interpolation fait déjà ce travail, en mieux\n"
        "(courbe mesurée). Le % ci-dessous compare à TA référence : il\n"
        "peut être élevé sans danger si tu vises un ton foncé.")
    outer.addWidget(lbl)

    chk = QtWidgets.QCheckBox("Compenser la puissance automatiquement (matériau sans nuancier)")
    chk.setToolTip(
        "Coché : la puissance est CALCULÉE pour déposer la même énergie\n"
        "qu'à la référence, au défocus et à la vitesse actuels (la\n"
        "puissance saisie plus haut est alors ignorée). Décoché : la\n"
        "puissance saisie est utilisée telle quelle, et l'atelier indique\n"
        "seulement la fluence obtenue par rapport à la référence (à toi\n"
        "d'ajuster). Utile pour comparer les deux approches sur une chute.")
    outer.addWidget(chk)

    # La référence est une CALIBRATION (un réglage réussi), pas un paramètre
    # du job : verrouillée par défaut pour ne pas la changer par mégarde en
    # réglant le job. La case la déverrouille pour la modifier volontairement.
    edit_chk = QtWidgets.QCheckBox("Modifier la référence (déverrouiller)")
    edit_chk.setToolTip(
        "La référence est une calibration (un réglage de gravure réussi),\n"
        "pas un paramètre du job -- elle est VERROUILLÉE pour éviter de la\n"
        "changer sans le vouloir. Coche pour la modifier. Les valeurs restent\n"
        "lisibles et sauvegardées (préréglage matériau + dernière session).")
    outer.addWidget(edit_chk)

    refs = QtWidgets.QFormLayout()
    refs.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

    ref_power_w = QtWidgets.QDoubleSpinBox()
    ref_power_w.setRange(0, core.S_MAX)
    ref_power_w.setValue(ref_power)
    ref_power_w.setToolTip("Puissance (S) du réglage de référence connu bon.")
    refs.addRow("Réf. puissance (S) :", ref_power_w)

    ref_feed_w = QtWidgets.QDoubleSpinBox()
    ref_feed_w.setRange(1, 20000)
    ref_feed_w.setValue(ref_feed)
    ref_feed_w.setSuffix(" mm/min")
    ref_feed_w.setToolTip("Vitesse d'avance du réglage de référence.")
    refs.addRow("Réf. vitesse :", ref_feed_w)

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
    refs.addRow("Réf. largeur du point :", ref_spot_w)
    outer.addLayout(refs)

    # verrouillage : lecture seule + pas de flèches tant que « Modifier » est
    # décoché (setValue programmatique -- restauration/préréglages -- reste OK).
    def _set_ref_editable(on):
        for rw in (ref_power_w, ref_feed_w, ref_spot_w):
            rw.setReadOnly(not on)
            rw.setButtonSymbols(QtWidgets.QAbstractSpinBox.UpDownArrows if on
                                else QtWidgets.QAbstractSpinBox.NoButtons)
    edit_chk.toggled.connect(_set_ref_editable)
    _set_ref_editable(False)

    info = _WrapLabel("")
    outer.addWidget(info)

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
        txt += (" -- plus foncé que la référence. Normal si c'est voulu "
                "(ton foncé visé, nuancier/ton sur mesure) ; sinon, risque "
                "de sur-brûlage.")
        color = "#b0740a"
    else:
        txt += " -- proche de la référence."
        color = "#2e7d32"
    if suggested is not None:
        txt += " Pour l'égaler : S{:.0f}.".format(min(suggested, core.S_MAX))
    return (txt, color, None)


def _appliquer_priorite_nuancier(shade_picker, fluence):
    """Le nuancier matériau et la compensation de fluence fixent tous les
    deux la puissance -- les laisser actifs EN MÊME TEMPS est un piège
    vécu : un ton mesuré à S1000 remplacé en silence par un S529 CALCULÉ,
    sans rien pour le signaler (v1.80.1 et avant). Le nuancier gagne
    TOUJOURS quand un matériau y est choisi : il vient d'une gravure
    réelle, mesurée ; la compensation n'est qu'un calcul destiné aux
    matériaux qui n'ont pas encore de nuancier. On grise donc le bloc
    « Puissance vs défocus » (et on décoche sa case pour de vrai --
    griser seul n'empêche pas un calcul déjà coché de continuer à
    s'appliquer) dès qu'un matériau du nuancier est sélectionné.

    À appeler en tout PREMIER dans la fonction d'aperçu du panneau (avant
    de lire `fluence["chk"]` pour calculer une puissance effective) --
    ainsi la case est toujours à jour avant d'être lue, sans dépendre de
    l'ordre de connexion des signaux Qt."""
    box = fluence["container"]
    titre = getattr(box, "_titre_defaut_priorite_nuancier", None)
    if titre is None:
        titre = box.title()
        box._titre_defaut_priorite_nuancier = titre
    mat = shade_picker["mat"].currentData()
    if mat:
        if fluence["chk"].isChecked():
            fluence["chk"].setChecked(False)
        box.setEnabled(False)
        box.setTitle("{} -- inutile : {} a des tons mesurés".format(titre, mat))
    else:
        box.setEnabled(True)
        box.setTitle(titre)


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

        _section(form, "Par où commencer ? (première calibration)",
                 "sect_guide.svg")
        depart = _WrapLabel(
            "Tu viens d'installer l'atelier et rien n'est réglé ? Fais ces "
            "gravures de calibration DANS L'ORDRE : les étapes ★1 et ★2 une "
            "fois pour la machine, l'étape ★3 pour chaque nouveau matériau. "
            "Chaque panneau de calibration rappelle son numéro d'étape en tête.")
        form.addRow(depart)
        # Vue condensée (1 ligne/étape) : plusieurs actions sont jointes par
        # « puis » ici -- le détail numéroté vit dans le bandeau ★ de chaque
        # panneau (_calibration_banner), pas doublé ici.
        puces_calib = []
        for e in core.calibration_numbered_steps():
            puces_calib.append(
                "<b>★{n} — {mode}.</b> Pour {but} : {action} → reporte dans "
                "<b>{reporter}</b>.".format(
                    n=e["n"], mode=e["mode"], but=e["but"],
                    action=", puis ".join(e["action"]), reporter=e["reporter"]))
        for e in core.CALIBRATION_JOURNEY:
            if e["n"] is None:
                puces_calib.append(
                    "<b>★ Complément — {mode}.</b> Pour {but} : {action}.".format(
                        mode=e["mode"], but=e["but"],
                        action=", puis ".join(e["action"])))
        _bullet_list(form, puces_calib)

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
            "• Zéro Z sur la SURFACE de la pièce : la règle en CALIBRATION "
            "(bandes, grilles, kerf), où le Z de travail des Préférences "
            "reste une focale constante. En travail courant, zéro Z sur le "
            "martyre (plan de travail) convient aussi -- l'épaisseur de la "
            "pièce se règle alors via le décalage de surface / Z de départ.",
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


def _lancer_nuancier_physique(parent_form, source, material, colonnes=None):
    """Construit le nuancier physique (un cercle par ton mesuré ou par
    préréglage, recette + Job chacun + étiquettes), l'empile dans le job
    combiné et ouvre le panneau Job combiné, prêt à générer. Partagé entre
    le mode Nuancier et l'Assistant matériau. Confirme si le job combiné
    n'est pas vide. `colonnes` : cf. _construire_nuancier_preregles."""
    items, err = _nuancier_items(source, material)
    if not items:
        QtWidgets.QMessageBox.information(parent_form, "Nuancier", err)
        return
    if _COMBINED_OPS:
        rep = QtWidgets.QMessageBox.question(
            parent_form, "Job combiné",
            "Le job combiné contient déjà {} opération(s).\n\n"
            "Vider et repartir d'un nuancier propre ?\n"
            "(Non = ajouter le nuancier à la suite)".format(len(_COMBINED_OPS)),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            | QtWidgets.QMessageBox.Cancel)
        if rep == QtWidgets.QMessageBox.Cancel:
            return
        if rep == QtWidgets.QMessageBox.Yes:
            _COMBINED_OPS[:] = []
    doc, jobs, warn = _construire_nuancier_preregles(
        source=source, material=material, colonnes=colonnes)
    if not jobs:
        QtWidgets.QMessageBox.critical(
            parent_form, "Nuancier",
            "Construction impossible.\n" + (warn or ""))
        return
    import laser_jobs
    ajoutes, ignores = laser_jobs.ajouter_jobs_au_combine(jobs)
    msgs = [m for m in (warn,
                        ("Jobs ignorés :\n- " + "\n- ".join(ignores))
                        if ignores else None) if m]
    if not ajoutes:
        QtWidgets.QMessageBox.critical(
            parent_form, "Nuancier",
            "Aucune opération valide.\n" + "\n\n".join(msgs))
        return
    if msgs:
        QtWidgets.QMessageBox.warning(parent_form, "Nuancier", "\n\n".join(msgs))
    import commands
    commands._show(TaskPanelCombined())


# ==========================================================================
# NUANCIER MATÉRIAU (tons de gris mesurés)
# ==========================================================================
class TaskPanelNuancier:
    """Éditeur du nuancier : la palette de gris MESURÉE d'un matériau
    (cf. load_shades dans laser_core). On y consigne, après une grille ou
    une rampe de test, chaque ton jugé utile : réglage (S/F/défocus) +
    résultat mesuré (noirceur %, largeur). Dans les modes Marquage et
    Gravure remplie, choisir un de ces tons (bloc « Nuancier matériau »)
    l'applique aussitôt."""

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
               "(noirceur 0-100 % à l'oeil, largeur du trait).")

        _diagram(form, "diag_nuancier.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Grave d'abord une <b>Grille de test</b>, une <b>Rampe</b> "
            "ou les <b>Planches de calibration (1-3)</b>, et garde les cases/tons "
            "qui te plaisent.",
            "<b>2.</b> Choisis un <b>matériau</b> existant, ou tape un nouveau "
            "nom (ex.&nbsp;«&nbsp;MDF&nbsp;6mm&nbsp;»).",
            "<b>3.</b> Décoche le <b>verrou</b>, puis pour chaque ton retenu, "
            "«&nbsp;+ Ajouter un ton&nbsp;» et renseigne le <b>réglage</b> (S, F, "
            "défocus) <b>et ce qu'il produit</b>&nbsp;: noirceur 0-100&nbsp;% à "
            "l'œil (0 = matériau intact, 100 = noir max), largeur du trait au "
            "pied à coulisse, libellé libre.",
            "<b>4.</b> Clique <b>OK</b> pour enregistrer le tableau. La "
            "noirceur n'étant pas linéaire avec la puissance, ces mesures "
            "alimentent ensuite les <b>dégradés</b>, les <b>photos "
            "calibrées</b> et le «&nbsp;ton sur mesure&nbsp;» (ton mesuré le "
            "plus proche) — on mesure, on ne devine pas.",
        ])

        _section(form, "① Saisir les tons mesurés", "sect_measure.svg")
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
        # Le tableau des tons est LE registre du matériau : verrouillé par
        # défaut (édition et boutons), comme les grilles de mesures.
        self.chk_verrou_tons = _verrou(form, [self.table, btn_add, btn_del],
                                       titre="Verrouiller les tons")

        _section(form, "② Graver ce nuancier (planche physique)", "sect_preset.svg")
        _bullet_list(form, [
            "Grave une <b>planche de référence</b>&nbsp;: un cercle Ø20 par "
            "entrée, chacun avec sa recette et un <b>Job</b>, plus une "
            "étiquette gravée dessous, un cadre et la date. Ordonnés du plus "
            "clair au plus foncé.",
            "<b>Source</b> — <b>Tons mesurés</b>&nbsp;: un cercle par ton du "
            "nuancier du matériau choisi ci-dessus (la palette riche, ex.&nbsp;"
            "les 34 gris MDF)&nbsp;; défocus et puissance reproduits "
            "fidèlement. <b>Préréglages</b>&nbsp;: un cercle par préréglage "
            "matériau enregistré dans Gravure remplie.",
            "Le bouton crée le document, empile le tout dans le <b>Job "
            "combiné</b> et l'ouvre&nbsp;: tu revois l'aperçu, puis tu génères "
            "le fichier unique.",
        ])
        self.combo_nuancier_source = QtWidgets.QComboBox()
        self.combo_nuancier_source.addItem("Tons mesurés du nuancier", "tons")
        self.combo_nuancier_source.addItem("Préréglages enregistrés", "preregles")
        self.combo_nuancier_source.setToolTip(
            "Ce que représente chaque cercle :\n"
            "- Tons mesurés : la palette du matériau choisi (souvent\n"
            "  nombreux) -- c'est le nuancier au sens propre.\n"
            "- Préréglages : les recettes nommées de Gravure remplie.")
        form.addRow("Source des cercles :", self.combo_nuancier_source)

        self.spn_nuancier_cols = QtWidgets.QSpinBox()
        self.spn_nuancier_cols.setRange(1, 30)
        self.spn_nuancier_cols.setValue(NUANCIER_COLONNES_DEFAUT)
        self.spn_nuancier_cols.setToolTip(
            "Largeur de la planche, en cercles. Au-delà d'une trentaine de\n"
            "tons, peu de colonnes donnent une bande étroite et très haute\n"
            "qui gaspille la chute : 83 tons sur 5 colonnes font 152 x 640 mm,\n"
            "les mêmes sur 10 colonnes font 292 x 348 mm. Le nombre de cercles\n"
            "ne change pas, seule la forme de la planche.")
        form.addRow("Colonnes :", self.spn_nuancier_cols)

        self.lbl_nuancier_taille = _WrapLabel("")
        form.addRow(self.lbl_nuancier_taille)
        self.spn_nuancier_cols.valueChanged.connect(
            lambda _v: self._maj_taille_nuancier())
        self.combo_nuancier_source.currentIndexChanged.connect(
            lambda _i: self._maj_taille_nuancier())

        btn_nuancier = QtWidgets.QPushButton("Créer la planche nuancier…")
        _btn_icon(btn_nuancier, "filled.svg")
        btn_nuancier.setToolTip(
            "Crée un document nuancier : un cercle gravé par ton mesuré (ou\n"
            "par préréglage), empilés dans le Job combiné, prêt à générer.")
        btn_nuancier.clicked.connect(self._on_graver_preregles)
        form.addRow(btn_nuancier)

        self._photo = _make_photo_section(
            form, lambda: "nuancier:" + self.combo_mat.currentText().strip(),
            titre="③ Photo du résultat")

        self._reload_materials()
        self.combo_mat.activated.connect(
            lambda _i: (self._load_material(), self._photo["reload"](),
                        self._maj_taille_nuancier()))

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Nuancier matériau")
        self.form.setWindowIcon(_icon("nuancier.svg"))
        self._photo["reload"]()
        self._maj_taille_nuancier()

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

    def _on_graver_preregles(self):
        """Grave ce nuancier en planche physique : un cercle par ton mesuré
        (ou par préréglage, selon la source), recette + Job chacun +
        étiquettes, empilés dans le job combiné, prêt à générer."""
        _lancer_nuancier_physique(
            self.form,
            self.combo_nuancier_source.currentData() or "tons",
            self.combo_mat.currentText().strip(),
            colonnes=self.spn_nuancier_cols.value())

    def _maj_taille_nuancier(self):
        """Encombrement de la planche AVANT de la construire : passé quelques
        dizaines de tons, le nombre de colonnes décide si la planche tient
        dans une chute ou pas -- autant le voir en réglant, pas après avoir
        généré le job."""
        items, _err = _nuancier_items(
            self.combo_nuancier_source.currentData() or "tons",
            self.combo_mat.currentText().strip())
        if not items:
            self.lbl_nuancier_taille.setText("")
            return
        g = _nuancier_geometrie(len(items), self.spn_nuancier_cols.value(),
                                max(len(l) for _lo, l, _r in items))
        self.lbl_nuancier_taille.setText(
            "Planche : <b>{:.0f} × {:.0f} mm</b> — {} cercles sur {} colonne(s), "
            "{} ligne(s).".format(g["board_w"], g["board_h"], len(items),
                                  g["cols"], g["nrows"]))

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


class _PastilleReglage(QtWidgets.QAbstractButton):
    """Pastille cliquable d'un réglage mesuré : un disque teinté par la
    NOIRCEUR mesurée, avec sa légende dessous.

    Un point de la grille de largeurs n'a pas de noirceur jugée
    (darkness=None) : son disque est hachuré, jamais peint en blanc ou en
    gris moyen -- une teinte inventée se lirait comme une mesure et c'est
    précisément le piège que `reglages_disponibles` évite en gardant None.
    """

    DIAM = 54              # diamètre du disque, en pixels
    H_LEGENDE = 30         # place réservée aux deux lignes de légende

    def __init__(self, reglage, critere, parent=None):
        super().__init__(parent)
        self._r = reglage
        self._critere = critere
        self.setCheckable(True)
        self.setFixedSize(self.DIAM + 16, self.DIAM + self.H_LEGENDE)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(core.resume_reglage(reglage, critere)
                        + ("\n(largeur mesurée à la grille, noirceur non jugée)"
                           if reglage.get("darkness") is None else ""))

    def _legende(self):
        """Ligne 1 : le réglage. Ligne 2 : la valeur du critère de classement
        -- et si CELLE-LÀ n'a pas été mesurée, la mesure qui existe plutôt
        qu'un « -- » qui n'apprend rien. Classés par noirceur, les points de
        grille formaient sinon un bloc de pastilles hachurées toutes
        légendées « -- % », alors que chacun a une largeur au pied à
        coulisse. Rien n'est inventé : on montre une autre mesure, on ne
        comble pas le trou."""
        r = self._r
        l1 = "S{:.0f} F{:.0f}".format(r.get("power") or 0, r.get("feed") or 0)
        d, w = r.get("darkness"), r.get("width")
        txt_d = None if d is None else "{:.0f} %".format(d)
        txt_w = "{:.2f} mm".format(w) if w else None
        if self._critere == "largeur":
            ordre = (txt_w, txt_d)
        elif self._critere == "defocus":
            ordre = ("déf {:.0f}".format(r.get("z_offset") or 0), txt_d, txt_w)
        else:
            ordre = (txt_d, txt_w)
        return l1, next((t for t in ordre if t), "--")

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        d = self._r.get("darkness")
        cx = self.width() / 2.0
        disque = QtCore.QRectF(cx - self.DIAM / 2.0, 4.0, self.DIAM, self.DIAM)

        # Anneau d'état AVANT le disque : sur un ton noir, un liseré posé
        # par-dessus disparaîtrait dans la masse.
        if self.isChecked() or self.underMouse():
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor(255, 138, 0) if self.isChecked()
                       else QtGui.QColor(255, 138, 0, 90))
            p.drawEllipse(disque.adjusted(-4, -4, 4, 4))

        if d is None:
            p.setBrush(QtGui.QBrush(QtGui.QColor(150, 150, 150),
                                    QtCore.Qt.BDiagPattern))
        else:
            # Même conversion que l'aperçu photo : 100 % de noirceur = noir.
            g = max(0, min(255, 255 - int(round(float(d) / 100.0 * 255))))
            p.setBrush(QtGui.QColor(g, g, g))
        p.setPen(QtGui.QPen(QtGui.QColor(70, 70, 70), 1.0))
        p.drawEllipse(disque)

        l1, l2 = self._legende()
        f = p.font()
        f.setPointSizeF(max(6.5, f.pointSizeF() - 1.5))
        p.setFont(f)
        p.setPen(self.palette().color(QtGui.QPalette.WindowText))
        haut = int(disque.bottom()) + 2
        p.drawText(QtCore.QRect(0, haut, self.width(), 13),
                   QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter, l1)
        p.drawText(QtCore.QRect(0, haut + 12, self.width(), 13),
                   QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter, l2)
        p.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


def _choisir_reglage_visuel(parent, combo_shade, material, critere):
    """Grille de pastilles cliquables : le nuancier montré, pas décrit.
    Renvoie l'index d'item à sélectionner dans `combo_shade`, ou None.

    La grille est construite À PARTIR DU COMBO, pas d'un nouvel appel à
    `reglages_disponibles` : groupes, ordre et contenu sont donc les mêmes
    par construction -- une seconde lecture des mesures pourrait diverger de
    la liste affichée (mesure enregistrée entre-temps) et faire appliquer
    autre chose que la pastille cliquée.

    On renvoie un INDEX, pas le réglage : PySide fait transiter les données
    d'item par un QVariant et reconstruit un dict NEUF à chaque itemData(),
    donc deux lectures du même item ne sont jamais le même objet. Désigner
    l'entrée par son index et laisser le combo la rejouer est le seul lien
    fiable ; comparer des réglages par identité échouerait en silence."""
    modele = combo_shade.model()
    groupes, courant = [], None
    for i in range(combo_shade.count()):
        r = combo_shade.itemData(i)
        if r:
            if courant is None:            # réglages sans en-tête (cas rare)
                courant = ("", [])
                groupes.append(courant)
            courant[1].append((i, r))
        else:
            item = modele.item(i)
            if item is not None and not item.isEnabled():
                courant = (combo_shade.itemText(i).strip("─ "), [])
                groupes.append(courant)
    groupes = [g for g in groupes if g[1]]
    if not groupes:
        return None

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Nuancier {} — choisir un réglage".format(material or ""))
    dlg.setWindowIcon(_icon("nuancier.svg"))
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(_WrapLabel(
        "Chaque pastille est teintée par la <b>noirceur mesurée</b> du réglage. "
        "Clique celle qui convient : elle est appliquée aussitôt. Une pastille "
        "<b>hachurée</b> vient de la grille de largeurs brûlées — sa largeur est "
        "mesurée, mais sa noirceur n'a jamais été jugée."))

    interieur = QtWidgets.QWidget()
    vbox = QtWidgets.QVBoxLayout(interieur)
    groupe_boutons = QtWidgets.QButtonGroup(dlg)
    groupe_boutons.setExclusive(True)
    choisi = {"index": None}

    def _clic(bouton):
        choisi["index"] = bouton.property("index_combo")
        dlg.accept()

    COLS = 7
    for titre, entrees in groupes:
        if titre:
            lbl = QtWidgets.QLabel("<b>{}</b>".format(titre))
            lbl.setStyleSheet("margin-top:6px;")
            vbox.addWidget(lbl)
        bloc = QtWidgets.QWidget()
        grille = QtWidgets.QGridLayout(bloc)
        grille.setSpacing(4)
        for k, (idx, r) in enumerate(entrees):
            past = _PastilleReglage(r, critere)
            past.setProperty("index_combo", idx)
            past.setChecked(idx == combo_shade.currentIndex())
            groupe_boutons.addButton(past)
            past.clicked.connect(lambda _c=False, b=past: _clic(b))
            grille.addWidget(past, k // COLS, k % COLS)
        grille.setColumnStretch(COLS, 1)
        vbox.addWidget(bloc)
    vbox.addStretch(1)

    zone = QtWidgets.QScrollArea()
    zone.setWidgetResizable(True)
    zone.setWidget(interieur)
    lay.addWidget(zone, 1)
    boutons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
    boutons.button(QtWidgets.QDialogButtonBox.Cancel).setText("Annuler")
    boutons.rejected.connect(dlg.reject)
    lay.addWidget(boutons)
    dlg.resize(640, 620)
    dlg.exec()
    return choisi["index"]


def _make_shade_picker(form, on_apply):
    """Bloc « Nuancier matériau » réutilisable dans un panneau de mode :
    sélecteur matériau + ton mesuré + un lien « Voir la photo du
    nuancier » (désactivé si ce matériau n'en a pas) pour comparer au
    rendu réel avant de choisir un ton sur un simple numéro. Choisir un
    ton dans la liste L'APPLIQUE immédiatement (on_apply(shade) est
    appelé avec le dict du ton) -- même convention que le sélecteur de
    préréglages (_PresetController), l'entrée neutre « -- Choisir -- »
    en tête évitant toute application accidentelle au rechargement ou au
    changement de matériau. Renvoie ses widgets ; l'appelant appelle
    ["reload"]() en fin d'__init__."""
    _section(form, "Nuancier matériau", "sect_preset.svg")
    combo_mat = QtWidgets.QComboBox()
    combo_mat.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo_mat.setMinimumContentsLength(14)
    combo_mat.setToolTip(
        "Matériau du nuancier (tons de gris MESURÉS, cf. le mode Nuancier\n"
        "dans Tests & calibration). Sert aussi de matériau à l'aperçu\n"
        "photo. En changer ne modifie aucun réglage.")
    form.addRow("Matériau :", combo_mat)

    combo_critere = QtWidgets.QComboBox()
    for cle, libelle in core.CRITERES_CLASSEMENT:
        combo_critere.addItem(libelle, cle)
    combo_critere.setToolTip(
        "Comment regrouper et trier la liste ci-dessous. On ne cherche pas\n"
        "toujours la même chose : une NUANCE pour un marquage, une LARGEUR\n"
        "de trait pour un remplissage, un niveau de DÉFOCUS pour retrouver\n"
        "une gravure déjà faite. La valeur du critère choisi passe en tête\n"
        "de chaque ligne, pour la parcourir des yeux.")
    form.addRow("Classer par :", combo_critere)

    combo_shade = QtWidgets.QComboBox()
    combo_shade.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo_shade.setMinimumContentsLength(18)
    combo_shade.setToolTip(
        "Réglages MESURÉS de ce matériau, groupés par le critère ci-dessus.\n"
        "En choisir un remplit AUSSITÔT puissance/vitesse (et défocus s'il\n"
        "en a un) -- le rendu sur la pièce sera celui constaté au test.\n"
        "\n"
        "La liste réunit DEUX sources : les tons du Nuancier (noirceur jugée\n"
        "à l'oeil) et les points de la grille de largeurs brûlées (largeur\n"
        "au pied à coulisse). Une valeur non mesurée s'affiche « -- » : un\n"
        "point de grille n'a pas de noirceur, beaucoup de tons n'ont pas de\n"
        "largeur. Rien n'est recopié d'une table à l'autre, donc ajouter ou\n"
        "retirer une mesure se voit ici immédiatement.")
    form.addRow("Réglage :", combo_shade)

    btn_visuel = QtWidgets.QPushButton("Choisir dans le nuancier…")
    _btn_icon(btn_visuel, "nuancier.svg")
    btn_visuel.setToolTip(
        "Montre les réglages ci-dessus en PASTILLES teintées par leur\n"
        "noirceur mesurée, plutôt qu'en lignes de texte : on compare des\n"
        "nuances à l'oeil, pas des nombres. Cliquer une pastille applique\n"
        "son réglage, comme la liste.")
    btn_photo = QtWidgets.QPushButton("Voir la photo du nuancier")
    ligne_btn = QtWidgets.QHBoxLayout()
    ligne_btn.addWidget(btn_visuel)
    ligne_btn.addWidget(btn_photo)
    form.addRow(ligne_btn)

    def _reload_shades():
        combo_shade.blockSignals(True)
        combo_shade.clear()
        m = combo_mat.currentData()
        if m:
            combo_shade.addItem("-- Choisir --", None)
            critere = combo_critere.currentData() or "noirceur"
            groupes = core.grouper_reglages(core.reglages_disponibles(m), critere)
            for titre, entrees in groupes:
                # En-tête de groupe : une entrée désactivée, donc visible mais
                # non sélectionnable -- pas de faux réglage applicable.
                combo_shade.addItem("── {} ──".format(titre), None)
                modele = combo_shade.model().item(combo_shade.count() - 1)
                if modele is not None:
                    modele.setEnabled(False)
                for r in entrees:
                    combo_shade.addItem("    " + core.resume_reglage(r, critere), r)
        else:
            combo_shade.addItem("-- (aucune mesure) --", None)
        combo_shade.blockSignals(False)
        n_reglages = sum(1 for i in range(combo_shade.count())
                         if combo_shade.itemData(i))
        btn_visuel.setEnabled(n_reglages > 0)
        n = len(core.result_photos("nuancier:" + m)) if m else 0
        btn_photo.setEnabled(n > 0)
        if n == 1:
            tip = ("1 photo de la planche gravée pour ce matériau -- voir "
                   "le rendu réel avant d'appliquer un ton.")
        elif n > 1:
            tip = ("{} photos de la planche gravée pour ce matériau -- "
                   "clique pour choisir laquelle voir.".format(n))
        else:
            tip = ("Aucune photo enregistrée pour ce matériau (mode "
                   "Nuancier, section Photo du résultat).")
        btn_photo.setToolTip(tip)

    def _reload():
        combo_mat.blockSignals(True)
        combo_mat.clear()
        # Union des deux tables : un matériau dont on n'a mesuré que des
        # largeurs (jamais jugé de nuance) a quand même des réglages à
        # proposer -- il était invisible ici tant que seul le nuancier
        # comptait.
        mats = sorted(set(core.shade_materials()) | set(core.burn_width_materials()))
        if not mats:
            combo_mat.addItem("-- (aucune mesure) --", None)
        for m in mats:
            combo_mat.addItem(m, m)
        combo_mat.blockSignals(False)
        _reload_shades()

    combo_mat.currentIndexChanged.connect(lambda _i: _reload_shades())
    combo_critere.currentIndexChanged.connect(lambda _i: _reload_shades())

    def _apply(_i=None):
        s = combo_shade.currentData()
        if s:
            on_apply(s)
    combo_shade.currentIndexChanged.connect(_apply)

    def _on_visuel():
        idx = _choisir_reglage_visuel(
            btn_visuel, combo_shade, combo_mat.currentData() or "",
            combo_critere.currentData() or "noirceur")
        if idx is None:
            return
        if idx == combo_shade.currentIndex():
            _apply()          # même entrée : setCurrentIndex n'émettrait rien,
        else:                 # or cliquer une pastille doit toujours appliquer
            combo_shade.setCurrentIndex(idx)
    btn_visuel.clicked.connect(_on_visuel)

    def _on_photo():
        m = combo_mat.currentData()
        photos = core.result_photos("nuancier:" + m) if m else []
        if not photos:
            return

        def _show(p):
            img = QtGui.QImage(p["path"])
            if not img.isNull():
                _show_image_dialog(img, "Photo du nuancier -- {}".format(m))

        if len(photos) == 1:
            _show(photos[0])
            return
        # Plusieurs photos pour ce matériau (ex. plusieurs défocus) : un
        # menu plutôt qu'ouvrir la première au hasard, avec la description
        # de chacune (cf. _make_photo_section) pour savoir laquelle choisir.
        menu = QtWidgets.QMenu(btn_photo)
        for i, p in enumerate(photos):
            menu.addAction(p["description"] or "Photo {}".format(i + 1),
                           lambda _checked=False, p=p: _show(p))
        menu.exec(btn_photo.mapToGlobal(QtCore.QPoint(0, btn_photo.height())))
    btn_photo.clicked.connect(_on_photo)

    return {"mat": combo_mat, "shade": combo_shade, "reload": _reload}


def _make_shade_quick_add(form, get_material, titre=None, on_added=None):
    """Bloc compact « + Ajouter ce ton » : capture INLINE d'un ton juste
    après une gravure (Grille de test, Rampe), sans quitter le panneau ni
    ressaisir de mémoire dans le Nuancier. Écrit dans la MÊME liste que le
    Nuancier (core.load_shades/save_shades) pour le matériau de
    `get_material()` -- le Nuancier reste le registre complet (relecture,
    correction, suppression) ; ce bloc n'ajoute qu'un ton à la fois, remis
    aux valeurs par défaut après chaque ajout (saisie éphémère, pas de
    valeur « au repos » à protéger -> pas de verrou ici, contrairement à
    _GrilleResultats/Nuancier qui affichent en permanence des mesures déjà
    enregistrées). Pas de QMessageBox de confirmation : après une seule
    gravure on ajoute plusieurs tons candidats à la suite, un modal par clic
    recréerait la friction qu'on retire par ailleurs -- le résumé compteur
    sert de confirmation silencieuse. `titre` (optionnel) : sous-légende en
    gras si ce bloc partage sa section avec un autre contenu (ex. les
    grilles de largeurs) ; laisser None si la section englobante porte déjà
    un titre suffisant. `on_added()` est rappelé après un ajout réussi (ex.
    rafraîchir la liste de matériaux si le nom tapé était inédit). Renvoie
    {"reload": fn} -- reload() (fin d'__init__, et à chaque changement de
    matériau) met à jour le résumé « N ton(s) déjà enregistré(s) »."""
    if titre:
        form.addRow(_WrapLabel("<b>{}</b>".format(titre)))

    row = QtWidgets.QWidget()
    lay = QtWidgets.QFormLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)

    spn_darkness = QtWidgets.QDoubleSpinBox()
    spn_darkness.setRange(0.0, 100.0)
    spn_darkness.setSuffix(" %")
    spn_darkness.setValue(50.0)
    spn_darkness.setToolTip("Noirceur jugée à l'œil : 0 = matériau intact, 100 = noir max.")
    lay.addRow("Noirceur :", spn_darkness)

    spn_power = QtWidgets.QDoubleSpinBox()
    spn_power.setRange(0, core.S_MAX)
    spn_power.setValue(500.0)
    lay.addRow("Puissance S :", spn_power)

    spn_feed = QtWidgets.QDoubleSpinBox()
    spn_feed.setRange(1.0, 20000.0)
    spn_feed.setValue(800.0)
    spn_feed.setSuffix(" mm/min")
    lay.addRow("Vitesse F :", spn_feed)

    spn_defocus = QtWidgets.QDoubleSpinBox()
    spn_defocus.setRange(0.0, 60.0)
    spn_defocus.setDecimals(1)
    spn_defocus.setSuffix(" mm")
    lay.addRow("Défocus :", spn_defocus)

    spn_width = QtWidgets.QDoubleSpinBox()
    spn_width.setRange(0.0, 10.0)
    spn_width.setDecimals(2)
    spn_width.setSuffix(" mm")
    spn_width.setToolTip(
        "Ce que « largeur » veut dire dépend de la planche, et c'est le\n"
        "piège de cette saisie :\n"
        "  - traits ISOLÉS (planche de calibration) : la largeur brûlée,\n"
        "    mesurée au pied à coulisse ;\n"
        "  - APLAT en balayage (bande de noirceur) : l'ESPACEMENT DES\n"
        "    HACHURES. En balayage, ce qui gouverne l'énergie reçue n'est\n"
        "    pas la largeur d'un trait mais de combien on avance entre\n"
        "    deux passes -- s'y tromper fausse la courbe d'un facteur qui\n"
        "    peut atteindre 8.\n"
        "0 = non renseignée (le ton reste choisissable, mais n'alimente\n"
        "ni la photo calibrée ni « ton sur mesure », qui exigent un\n"
        "défocus ET une largeur).")
    lay.addRow("Largeur mesurée :", spn_width)

    edt_label = QtWidgets.QLineEdit()
    edt_label.setPlaceholderText("ex. gris moyen")
    lay.addRow("Libellé :", edt_label)

    form.addRow(row)

    btn_add = QtWidgets.QPushButton("+ Ajouter ce ton")
    btn_add.setToolTip(
        "Ajoute ce ton au nuancier de ce matériau (même registre que le\n"
        "mode Nuancier, qui reste l'endroit pour tout revoir/corriger).")
    form.addRow(btn_add)

    lbl_resume = _WrapLabel("")
    form.addRow(lbl_resume)

    def reload():
        mat = (get_material() or "").strip()
        n = len(core.load_shades(mat)) if mat else 0
        lbl_resume.setText(
            "{} ton(s) déjà enregistré(s) pour « {} ».".format(n, mat)
            if mat else "Indique un matériau pour voir ses tons enregistrés.")

    def _on_add():
        mat = (get_material() or "").strip()
        if not mat:
            QtWidgets.QMessageBox.warning(
                form.parentWidget(), "Ton", "Indiquer un nom de matériau.")
            return
        shades = core.load_shades(mat)
        shades.append({
            "darkness": spn_darkness.value(), "power": spn_power.value(),
            "feed": spn_feed.value(), "z_offset": spn_defocus.value(),
            "width": spn_width.value(), "label": edt_label.text().strip(),
        })
        core.save_shades(mat, shades)
        spn_darkness.setValue(50.0)
        spn_power.setValue(500.0)
        spn_feed.setValue(800.0)
        spn_defocus.setValue(0.0)
        spn_width.setValue(0.0)
        edt_label.clear()
        reload()
        if on_added:
            on_added()

    def appliquer(valeurs):
        """Pré-remplit les champs depuis ce que le panneau vient de graver.

        Appelé sur une action EXPLICITE (choisir un objectif), jamais depuis
        reload() : écraser une saisie en cours parce qu'on a changé de
        matériau serait une trahison de ce qui est tapé."""
        for cle, widget in (("darkness", spn_darkness), ("power", spn_power),
                            ("feed", spn_feed), ("z_offset", spn_defocus),
                            ("width", spn_width)):
            if valeurs.get(cle) is not None:
                widget.setValue(float(valeurs[cle]))
        if valeurs.get("label") is not None:
            edt_label.setText(str(valeurs["label"]))

    btn_add.clicked.connect(_on_add)
    return {"reload": reload, "appliquer": appliquer}


def _make_largeurs_libres(form, get_material, on_saved=None, lignes=8):
    """Table LIBRE de largeurs brûlées : (S, F, défocus, largeur) sans grille
    imposée -- le pendant de `_make_shade_quick_add`, pour la mesure et non
    pour le ton.

    Pourquoi elle existe. La saisie des largeurs passait uniquement par
    `_MesuresPlanchesControleur`, dont la grille est le MIROIR de la Planche 2 :
    puissances 1000..200, vitesses 200..800, niveaux de défocus 15 et 36. C'est
    juste pour une planche, qui grave une grille discrète. Mais la RAMPE mesure
    un CONTINUUM -- la puissance et la hauteur montent ensemble le long de
    chaque ligne, si bien qu'un point relevé vaut par exemple S980/F200 à
    défocus 60. Aucune de ces valeurs n'entre dans la grille. Relevé le
    30/07/2026 sur la première rampe Z gravée : cinq mesures exploitables, et
    nulle part où les mettre.

    Deux précautions, chacune payée par une leçon de ce projet :

    - **Fusion, jamais remplacement.** `save_burn_widths` ÉCRASE la table du
      matériau. On relit donc l'existant et on n'y remplace que les points de
      même (S, F, défocus). Un enregistrement ne doit jamais faire disparaître
      des mesures au pied à coulisse.
    - **Lecture BRUTE de la config**, pas via `load_burn_widths` : celle-ci
      ramène les défocus au niveau standard proche (15,34 -> 15). Passer par
      elle pour fusionner réécrirait les valeurs stockées de Christophe au
      passage. On ne touche que ce qu'on ajoute.

    Et le défocus tapé n'est PAS arrondi en silence : s'il tombe à moins de 5 mm
    d'un niveau standard, `load_burn_widths` le rangera là (un 40 devient 36).
    La table le dit avant d'enregistrer -- une valeur saisie à la main est
    délibérée, elle mérite qu'on prévienne plutôt qu'on corrige."""
    form.addRow(_WrapLabel(
        "<b>Largeurs mesurées au pied à coulisse</b> — une ligne par point "
        "relevé. La rampe fait monter la puissance ET la hauteur ensemble : "
        "relève donc la puissance qui correspond à l'endroit mesuré (elle est "
        "graduée sous la première ligne), pas celle du réglage. Défocus 0 = au "
        "foyer. Ces largeurs nourrissent le modèle de trait brûlé (remplissage, "
        "lignes gravées, traits épais décoratifs)."))
    table = QtWidgets.QTableWidget(lignes, 4)
    table.setHorizontalHeaderLabels(["Puissance S", "Vitesse F",
                                     "Défocus (mm)", "Largeur (mm)"])
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setMinimumHeight(26 * (lignes + 1))
    form.addRow(table)
    lbl = _WrapLabel("")
    form.addRow(lbl)
    btn = QtWidgets.QPushButton("Enregistrer ces largeurs")
    btn.setToolTip(
        "Ajoute ces points à la table des largeurs brûlées du matériau, sans "
        "toucher aux mesures déjà enregistrées. Indépendant de l'OK du panneau.")
    form.addRow(btn)

    # Ce que le dernier reload() a AFFICHÉ. Une ligne vidée par l'utilisateur
    # ne peut supprimer que parmi ces points-là : on ne retire jamais une
    # mesure qu'on ne lui a pas montrée.
    _affiches = []

    def _nombre(r, c):
        it = table.item(r, c)
        txt = (it.text() if it else "").strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    def _on_save():
        mat = (get_material() or "").strip()
        if not mat:
            QtWidgets.QMessageBox.warning(form.parentWidget(), "Largeurs",
                                          "Indiquer un nom de matériau.")
            return
        points, incomplets = [], 0
        for r in range(table.rowCount()):
            vals = [_nombre(r, c) for c in range(4)]
            if all(v is None for v in vals):
                continue
            s, f, dz, w = vals
            if None in (s, f, w) or s <= 0 or f <= 0 or w <= 0:
                incomplets += 1
                continue
            points.append((s, f, float(dz or 0.0), w))
        if not points:
            lbl.setText("<span style=\"color:#c62828\">Rien à enregistrer "
                        "(il faut au moins puissance, vitesse et largeur).</span>")
            return
        # Lecture BRUTE : ne pas passer par load_burn_widths, qui arrondit les
        # défocus au niveau standard et réécrirait l'existant (cf. docstring).
        table_mat = (core.load_config().get("burn_widths", {})
                     .get(mat, {}) or {})
        focus = list(table_mat.get("focus", []) or [])
        defocus = list(table_mat.get("defocus", []) or [])

        def _remplace(liste, cle, neuf):
            for i, pt in enumerate(liste):
                if cle(pt):
                    liste[i] = neuf
                    return False
            liste.append(neuf)
            return True

        # SUPPRESSION : un point qui avait été affiché et qui ne figure plus
        # dans la table a été effacé volontairement. Sans ça, corriger le
        # DÉFOCUS d'une mesure en créerait une seconde au lieu de la déplacer.
        # On ne retire QUE parmi ce que reload() a montré -- jamais une mesure
        # restée invisible à l'utilisateur.
        presents = {(s, f, dz) for s, f, dz, _w in points}
        retires = [cle for cle in _affiches if cle not in presents]
        if retires:
            defocus = [pt for pt in defocus
                       if (float(pt.get("power", 0)), float(pt.get("feed", 0)),
                           float(pt.get("z_offset", 0) or 0)) not in retires]

        ajouts = remplaces = 0
        arrondis = []
        for s, f, dz, w in points:
            if dz <= 1e-9:
                neuf = {"power": s, "feed": f, "width": round(w, 3)}
                nouveau = _remplace(
                    focus,
                    lambda pt, s=s, f=f: (abs(float(pt.get("power", 0)) - s) < 1e-6
                                          and abs(float(pt.get("feed", 0)) - f) < 1e-6),
                    neuf)
            else:
                neuf = {"power": s, "feed": f, "width": round(w, 3),
                        "z_offset": dz}
                nouveau = _remplace(
                    defocus,
                    lambda pt, s=s, f=f, dz=dz: (
                        abs(float(pt.get("power", 0)) - s) < 1e-6
                        and abs(float(pt.get("feed", 0)) - f) < 1e-6
                        and abs(float(pt.get("z_offset", 0) or 0) - dz) < 1e-6),
                    neuf)
                range_a = core._snap_defocus_level(dz)
                if abs(range_a - dz) > 1e-9:
                    arrondis.append((dz, range_a))
            ajouts += 1 if nouveau else 0
            remplaces += 0 if nouveau else 1
        core.save_burn_widths(mat, {"focus": focus, "defocus": defocus})
        msg = ("{} point(s) ajouté(s), {} remplacé(s){} pour « {} » — la "
               "table compte maintenant {} mesure(s) au foyer et {} en "
               "défocus.".format(
                   ajouts, remplaces,
                   ", {} supprimé(s)".format(len(retires)) if retires else "",
                   mat, len(focus), len(defocus)))
        if incomplets:
            msg += (" {} ligne(s) ignorée(s), incomplète(s)."
                    .format(incomplets))
        couleur = "#2e7d32"
        if arrondis:
            couleur = "#c62828"
            # Formulé en CONSÉQUENCE, pas en mécanisme. La première version
            # disait « seront relus au niveau standard le plus proche » :
            # Christophe n'a pas compris, et il avait raison -- « niveau
            # standard » n'est expliqué nulle part dans l'interface, et
            # « relu » décrit un détail d'implémentation. Ce qu'il faut
            # savoir tient en une phrase : cette mesure comptera comme si
            # elle avait été faite à telle hauteur.
            msg += (" <b>Attention</b> : {}. L'atelier regroupe les mesures "
                    "en défocus autour de hauteurs de référence ({}) et y "
                    "rattache tout ce qui en est à moins de 5 mm. La mesure "
                    "reste juste, mais elle servira comme si elle avait été "
                    "faite à cette hauteur — saisir cette valeur directement "
                    "revient au même.".format(
                        ", ".join("le défocus <b>{:.0f} mm</b> comptera comme "
                                  "<b>{:.0f} mm</b>".format(a, b)
                                  for a, b in arrondis),
                        ", ".join("{:.0f}".format(lv)
                                  for lv in core.DEFOCUS_LEVELS_MM)))
        garde = msg, couleur
        reload()          # la table remontre l'état RÉEL, pas la saisie
        lbl.setText("<span style=\"color:{}\">{}</span>".format(garde[1],
                                                                garde[0]))
        if on_saved:
            on_saved()

    btn.clicked.connect(_on_save)

    def _hors_grille(pt):
        """Un point que la grille figée ne sait PAS exprimer -- donc que
        cette table est seule à pouvoir relire et corriger."""
        G = _MesuresPlanchesControleur
        return (float(pt.get("power", 0)) not in G.POWERS
                or float(pt.get("feed", 0)) not in G.FEEDS_DEFOCUS
                or float(pt.get("z_offset", 0) or 0) not in core.DEFOCUS_LEVELS_MM)

    def reload():
        """Réaffiche les points HORS GRILLE déjà enregistrés.

        Sans ça la table est en écriture seule : Christophe a saisi ses cinq
        relevés de rampe, puis a voulu les corriger -- ils n'étaient plus là
        (30/07/2026). Une mesure qu'on ne peut pas relire ne peut pas être
        vérifiée, et c'est justement la donnée la plus chère du projet.

        On n'affiche QUE les points hors grille : les autres appartiennent à
        la grille de la Planche 2, qui les montre déjà et sait les corriger.
        Les rendre modifiables ici aussi ferait deux vérités pour une mesure."""
        lbl.setText("")
        mat = (get_material() or "").strip()
        pts = []
        if mat:
            brut = (core.load_config().get("burn_widths", {}).get(mat, {})
                    or {})
            pts = [pt for pt in (brut.get("defocus", []) or [])
                   if _hors_grille(pt)]
            pts.sort(key=lambda pt: (float(pt.get("z_offset", 0) or 0),
                                     float(pt.get("power", 0))))
        table.clearContents()
        table.setRowCount(max(lignes, len(pts) + 3))
        for r, pt in enumerate(pts):
            for c, v in enumerate((pt.get("power"), pt.get("feed"),
                                   pt.get("z_offset"), pt.get("width"))):
                txt = ("{:g}".format(float(v)) if v is not None else "")
                table.setItem(r, c, QtWidgets.QTableWidgetItem(txt))
        _affiches[:] = [(float(pt.get("power", 0)), float(pt.get("feed", 0)),
                         float(pt.get("z_offset", 0) or 0)) for pt in pts]
        if pts:
            lbl.setText("{} mesure(s) hors grille déjà enregistrée(s) pour "
                        "« {} » — corrige une valeur, ou vide une ligne pour "
                        "la supprimer, puis réenregistre.".format(len(pts), mat))

    return {"reload": reload, "table": table}


# ==========================================================================
# MODE : TEXTE TRAIT SIMPLE (police mono-trait Hershey)
# ==========================================================================
def _pixmap_alignement(cle, taille=18):
    """Petit pictogramme 4 barres (façon traitement de texte) pour un
    bouton d'alignement -- dessiné directement, pas besoin d'un fichier
    SVG à part pour 4 icônes aussi simples."""
    pm = QtGui.QPixmap(taille, taille)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(QtGui.QColor("#2f3540"))
    marge = 2.0
    h_barre = 2.2
    pas = (taille - 2 * marge) / 4.0
    largeur_pleine = taille - 2 * marge
    y = marge
    for i in range(4):
        lw = largeur_pleine if (cle == "justify" or i % 2 == 0) else largeur_pleine * 0.6
        if cle == "right":
            x = taille - marge - lw
        elif cle == "center":
            x = marge + (largeur_pleine - lw) / 2.0
        else:
            x = marge
        p.drawRoundedRect(QtCore.QRectF(x, y, lw, h_barre), 0.6, 0.6)
        y += pas
    p.end()
    return pm


# Alignement (mot-clé interne <-> drapeau Qt du bloc/paragraphe visé par
# le curseur du QPlainTextEdit) -- partagé entre la barre de boutons et
# accept() (qui relit l'alignement RÉEL de chaque ligne pour la gravure).
_ALIGN_QT = {
    "left": QtCore.Qt.AlignLeft,
    "center": QtCore.Qt.AlignHCenter,
    "right": QtCore.Qt.AlignRight,
    "justify": QtCore.Qt.AlignJustify,
}
_ALIGN_QT_INV = {int(v): k for k, v in _ALIGN_QT.items()}


class TaskPanelText:
    """Crée un texte en police MONO-TRAIT (trait simple) comme objet fil, à
    graver ensuite avec Marquage. Chaque lettre est dessinée d'un seul trait
    par branche (vrai « bâton », comme un traceur à plume) -- contrairement à
    ShapeString qui donne des contours pleins à remplir."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "text.svg", "Texte (trait simple)")
        _intro(form,
               "Grave du texte en TRAIT SIMPLE : chaque lettre est dessinée "
               "d'un seul trait par branche (comme un traceur à plume), pas "
               "en contour rempli -- polices Hershey mono-trait (domaine "
               "public).")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Tape le <b>texte</b> (Entrée = nouvelle ligne) : un "
            "aperçu apparaît en direct dans la vue 3D.",
            "<b>2.</b> Place le curseur sur une ligne et clique un <b>bouton "
            "d'alignement</b> (gauche/centre/droite/justifié) pour la caler "
            "indépendamment des autres, comme dans un traitement de texte.",
            "<b>3.</b> Choisis une <b>police</b> et règle la <b>hauteur</b> "
            "(des capitales) et les espacements.",
            "<b>4. OK</b> garde l'objet «&nbsp;Texte…&nbsp;» dans l'arbre "
            "(coin bas-gauche à l'origine) ; <b>Annuler</b> le supprime.",
            "<b>5.</b> Sélectionne-le et ouvre <b>Marquage</b> pour le graver "
            "(place-le d'abord, ou projette-le sur une surface courbe).",
        ])

        _section(form, "Texte", "sect_labels.svg")
        barre_align = QtWidgets.QHBoxLayout()
        barre_align.setSpacing(4)
        self._boutons_align = {}
        self._groupe_align = QtWidgets.QButtonGroup()
        self._groupe_align.setExclusive(True)
        for cle, titre in (
                ("left", "Aligner cette ligne à gauche"),
                ("center", "Centrer cette ligne"),
                ("right", "Aligner cette ligne à droite"),
                ("justify", "Justifier cette ligne (étire les espaces internes "
                 "-- sans effet sur une ligne d'un seul mot, faute d'espace "
                 "à étirer)")):
            b = QtWidgets.QToolButton()
            b.setCheckable(True)
            b.setIcon(QtGui.QIcon(_pixmap_alignement(cle)))
            b.setToolTip(titre)
            b.clicked.connect(lambda _chk, c=cle: self._appliquer_alignement(c))
            self._groupe_align.addButton(b)
            barre_align.addWidget(b)
            self._boutons_align[cle] = b
        self._boutons_align["left"].setChecked(True)
        barre_align.addStretch(1)
        form.addRow("Alignement :", barre_align)

        self.combo_font = QtWidgets.QComboBox()
        for cle, libelle in core.HERSHEY_FONTS.items():
            self.combo_font.addItem(libelle, cle)
        self.combo_font.setToolTip(
            "Police mono-trait (un seul passage de plume par branche).")
        form.addRow("Police :", self.combo_font)

        # Réglages de dimension juste à côté des icônes d'alignement --
        # tout ce qui règle l'ASPECT du texte regroupé au même endroit,
        # avant la boîte de saisie elle-même.
        self.spn_height = QtWidgets.QDoubleSpinBox()
        self.spn_height.setRange(1.0, 500.0)
        self.spn_height.setValue(10.0)
        self.spn_height.setDecimals(1)
        self.spn_height.setSuffix(" mm")
        self.spn_height.setToolTip(
            "Hauteur des CAPITALES (mm) ; minuscules et accents suivent.")
        form.addRow("Hauteur (capitale) :", self.spn_height)

        self.spn_cspace = QtWidgets.QDoubleSpinBox()
        self.spn_cspace.setRange(-10.0, 50.0)
        self.spn_cspace.setValue(0.0)
        self.spn_cspace.setDecimals(1)
        self.spn_cspace.setSuffix(" mm")
        self.spn_cspace.setToolTip(
            "Espace AJOUTÉ entre les lettres (négatif = resserrer).")
        form.addRow("Espacement lettres :", self.spn_cspace)

        self.spn_lspace = QtWidgets.QDoubleSpinBox()
        self.spn_lspace.setRange(1.0, 5.0)
        self.spn_lspace.setValue(1.6)
        self.spn_lspace.setDecimals(2)
        self.spn_lspace.setSingleStep(0.1)
        self.spn_lspace.setToolTip("Interligne, en multiples de la hauteur.")
        form.addRow("Interligne (× hauteur) :", self.spn_lspace)

        self.txt = QtWidgets.QTextEdit()
        self.txt.setAcceptRichText(False)
        self.txt.setPlaceholderText("Texte à graver (Entrée = nouvelle ligne)")
        self.txt.setMaximumHeight(90)
        self.txt.setPlainText("Atelier")
        self.txt.cursorPositionChanged.connect(self._sync_boutons_align)
        form.addRow(self.txt)

        self.lbl_info = _WrapLabel("")
        form.addRow(self.lbl_info)

        # Aperçu en direct dans la vue 3D : l'objet est créé/mis à jour au
        # fil de la frappe (pas seulement au clic sur OK) -- un délai
        # (anti-rebond) évite de régénérer la géométrie à chaque lettre.
        self._obj = None
        self._timer_apercu = QtCore.QTimer()
        self._timer_apercu.setSingleShot(True)
        self._timer_apercu.setInterval(250)
        self._timer_apercu.timeout.connect(self._maj_apercu)

        for w in (self.spn_height, self.spn_cspace, self.spn_lspace):
            w.valueChanged.connect(self._update_info)
            w.valueChanged.connect(self._demander_apercu)
        self.combo_font.currentIndexChanged.connect(self._update_info)
        self.combo_font.currentIndexChanged.connect(self._demander_apercu)
        self.txt.textChanged.connect(self._update_info)
        self.txt.textChanged.connect(self._demander_apercu)

        self._last_fields = {"text": self.txt, "height": self.spn_height,
                             "cspace": self.spn_cspace, "lspace": self.spn_lspace,
                             "font": self.combo_font}
        _restore_last_values("text", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Texte (trait simple)")
        self.form.setWindowIcon(_icon("text.svg"))
        self._update_info()
        self._maj_apercu()

    def _update_info(self):
        w, h = core.single_line_text_extent(
            self.txt.toPlainText(), self.spn_height.value(),
            self.spn_cspace.value(), self.spn_lspace.value(),
            font=self.combo_font.currentData())
        self.lbl_info.setText(
            "Encombrement : {:.1f} × {:.1f} mm.".format(w, h) if w > 0
            else "Saisis un texte.")

    def _appliquer_alignement(self, cle):
        """Applique l'alignement `cle` au(x) paragraphe(s) touché(s) par le
        curseur/la sélection courante -- comme le bouton d'alignement d'un
        traitement de texte, PAS un réglage global pour tout le bloc."""
        curseur = self.txt.textCursor()
        fmt = QtGui.QTextBlockFormat()
        fmt.setAlignment(_ALIGN_QT[cle])
        curseur.mergeBlockFormat(fmt)
        self.txt.setTextCursor(curseur)
        self.txt.setFocus()
        self._demander_apercu()

    def _sync_boutons_align(self):
        """Reflète dans la barre l'alignement RÉEL de la ligne où se trouve
        le curseur (déplacement au clic/aux flèches -- pas seulement après
        un clic sur un bouton)."""
        al = int(self.txt.textCursor().blockFormat().alignment())
        bouton = self._boutons_align.get(_ALIGN_QT_INV.get(al, "left"))
        if bouton is not None and not bouton.isChecked():
            bouton.setChecked(True)

    def _aligns_actuels(self):
        """Alignement RÉEL de chaque ligne du document (une valeur par
        bloc/paragraphe) -- partagé entre l'aperçu en direct et accept()."""
        aligns = []
        blk = self.txt.document().begin()
        while blk.isValid():
            aligns.append(_ALIGN_QT_INV.get(int(blk.blockFormat().alignment()), "left"))
            blk = blk.next()
        return aligns

    def _demander_apercu(self, *_args):
        """Programme une régénération de l'aperçu 3D dans peu (anti-rebond :
        chaque frappe redémarre le délai au lieu de l'empiler)."""
        self._timer_apercu.start()

    def _maj_apercu(self):
        """Crée/met à jour l'objet « Texte… » dans le document pour qu'il
        reflète EN DIRECT ce qui est tapé -- silencieux (texte vide = objet
        vidé, pas une erreur tant que la fenêtre reste ouverte)."""
        if FreeCAD.ActiveDocument is None:
            return
        self._obj, _err = core.create_single_line_text_object(
            self.txt.toPlainText(), self.spn_height.value(),
            self.spn_cspace.value(), self.spn_lspace.value(),
            align=self._aligns_actuels(), obj=self._obj,
            font=self.combo_font.currentData())

    def accept(self):
        self._timer_apercu.stop()
        _save_last_values("text", self._last_fields)
        obj, err = core.create_single_line_text_object(
            self.txt.toPlainText(), self.spn_height.value(),
            self.spn_cspace.value(), self.spn_lspace.value(),
            align=self._aligns_actuels(), obj=self._obj,
            font=self.combo_font.currentData())
        self._obj = obj
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage(
            "Texte créé : « {} ». Sélectionne-le puis ouvre Marquage pour le "
            "graver.\n".format(obj.Label))
        return True

    def reject(self):
        self._timer_apercu.stop()
        if self._obj is not None and FreeCAD.ActiveDocument is not None:
            try:
                FreeCAD.ActiveDocument.removeObject(self._obj.Name)
                FreeCAD.ActiveDocument.recompute()
            except Exception:
                pass  # déjà supprimé par ailleurs : rien à faire
        return True


# ==========================================================================
# MODE : CATALOGUE (planche d'exemples de plusieurs modes)
# ==========================================================================
class TaskPanelCatalogue:
    """Grave, en un seul job, une planche de RÉFÉRENCE : les styles de trait
    du Marquage (sur un mot exemple) + un exemple de gravure remplie, titrés.
    À graver sur une chute une fois les réglages calés. (La gravure photo se
    valide dans son propre mode, avec tous ses réglages.)"""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "catalogue.svg", "Catalogue (planche de référence)")
        _intro(form,
               "Grave sur une chute une planche de RÉFÉRENCE : les 6 styles de "
               "trait du Marquage (sur un mot exemple) + un exemple de gravure "
               "remplie, titrés, en un seul job. À garder une fois tes réglages "
               "calés : tu vois le rendu réel de chaque style sur ton matériau "
               "(« Aperçu photo » montre le rendu avant de graver). La gravure "
               "photo se teste dans son propre mode (Gravure photo), avec la "
               "mire des tramages et tous les réglages.")

        _section(form, "Contenu", "sect_options.svg")
        self.edt_sample = QtWidgets.QLineEdit("Laser")
        self.edt_sample.setToolTip("Mot exemple gravé dans chaque style.")
        form.addRow("Mot exemple :", self.edt_sample)
        self.chk_marquage = QtWidgets.QCheckBox("Marquage — les styles de trait")
        self.chk_marquage.setChecked(True)
        self.chk_remplie = QtWidgets.QCheckBox("Gravure remplie (étoile noire)")
        self.chk_remplie.setChecked(True)
        for c in (self.chk_marquage, self.chk_remplie):
            form.addRow(c)

        _section(form, "Puissance / vitesse", "sect_power.svg")
        self.spn_power = QtWidgets.QDoubleSpinBox()
        self.spn_power.setRange(0, core.S_MAX)
        self.spn_power.setValue(500)
        self.spn_power.setToolTip("Puissance (S) commune à tous les exemples.")
        form.addRow("Puissance (S) :", self.spn_power)
        self.spn_feed = QtWidgets.QDoubleSpinBox()
        self.spn_feed.setRange(1, 20000)
        self.spn_feed.setValue(1000)
        self.spn_feed.setSuffix(" mm/min")
        form.addRow("Vitesse :", self.spn_feed)

        _section(form, "Aperçu & génération", "sect_gcode.svg")
        self.btn_preview = QtWidgets.QPushButton()
        self.btn_preview.setToolTip(
            "Peint le rendu de la planche avant de graver -- chaque style\n"
            "distinct (tirets, pointillé, vague, point élargi, dégradé).")
        self.btn_preview.clicked.connect(self._on_preview)
        _preview_row(form, [(self.btn_preview, "sect_photo.svg")])
        form.addRow(_WrapLabel("OK grave la planche dans un seul fichier."))

        self._last_fields = {"sample": self.edt_sample, "power": self.spn_power,
                             "feed": self.spn_feed, "marquage": self.chk_marquage,
                             "remplie": self.chk_remplie}
        _restore_last_values("catalogue", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Catalogue (planche de référence)")
        self.form.setWindowIcon(_icon("catalogue.svg"))

    def _blocks(self):
        b = []
        if self.chk_marquage.isChecked():
            b.append("marquage")
        if self.chk_remplie.isChecked():
            b.append("remplie")
        return tuple(b)

    def _on_preview(self):
        if not self._blocks():
            QtWidgets.QMessageBox.warning(self.form, "Catalogue", "Coche au moins un bloc.")
            return
        ops = core.build_catalogue_ops(
            power=self.spn_power.value(), feed=self.spn_feed.value(),
            z_focus=core.Z_WORK_MM, sample_text=self.edt_sample.text().strip() or "Laser",
            blocks=self._blocks())
        strokes = []
        for op in ops:
            strokes.extend(_strokes_from_operation(op))
        if not strokes:
            QtWidgets.QMessageBox.information(self.form, "Aperçu photo", "Rien à afficher.")
            return
        img = _render_engraving_photo(strokes)
        if img is None:
            QtWidgets.QMessageBox.critical(self.form, "Aperçu photo", "Rendu impossible.")
            return
        _show_image_dialog(img, "Aperçu photo — Catalogue")

    def accept(self):
        if not self._blocks():
            QtWidgets.QMessageBox.warning(self.form, "Catalogue", "Coche au moins un bloc.")
            return False
        _save_last_values("catalogue", self._last_fields)
        gcode = core.generate_gcode_catalogue(
            power=self.spn_power.value(), feed=self.spn_feed.value(),
            z_focus=core.Z_WORK_MM, sample_text=self.edt_sample.text().strip() or "Laser",
            blocks=self._blocks())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/catalogue.ngc")

    def reject(self):
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

        _diagram(form, "diag_hatch.svg")

        # Seul des cinq panneaux à sélection à ne PAS avoir ce bouton.
        _reselect_button(form, self._on_recapture_selection,
                         lambda: self.selection)

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Sélectionne la <b>face 2D</b> (ou esquisse fermée) à "
            "remplir de hachures.",
            "<b>2. Type de remplissage</b>&nbsp;: Parallèles (zigzag), Croisées "
            "(grille, plus dense) ou Défocus (destiné à être gravé au point "
            "élargi pour noircir en un passage).",
            "<b>3. Espacement / angle</b>&nbsp;: règle l'écart entre lignes et "
            "l'angle. Le <b>retrait du bord</b> rentre les hachures pour que la "
            "brûlure ne déborde pas («&nbsp;Auto (½ point)&nbsp;»).",
            "<b>4.</b> Clique <b>OK</b>&nbsp;: crée un objet <code>Hachures</code>"
            " dans le document. <b>Aucun G-code ici</b> — c'est de la géométrie.",
            "<b>5.</b> Enchaîne&nbsp;: grave l'objet avec <b>Marquage de motif</b>,"
            " ou <b>projette-le</b> sur une surface 3D (<b>Projection</b>) avant "
            "marquage / découpe courbe.",
        ])

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
        self.btn_inset_auto = QtWidgets.QPushButton("Auto (½ point)")
        self.btn_inset_auto.setToolTip(
            "Remplit le retrait avec le RAYON du trait qui sera brûlé :\n"
            "- remplissage Parallèles/Croisées (gravé au foyer) : ½ point\n"
            "  au foyer, soit {:.2f} mm avec la calibration actuelle ;\n"
            "- remplissage Défocus : ½ point élargi déduit de l'espacement\n"
            "  (même calcul que la Gravure remplie).\n"
            "NB : à forte puissance la brûlure s'élargit un peu au-delà du\n"
            "point optique -- ajoute une petite marge, ou prends la ½\n"
            "largeur d'un trait MESURÉ du nuancier si tu vises ce réglage.".format(
                core.SPOT_FOCUS_MM / 2.0))

        def _inset_auto():
            if self.combo_filltype.currentIndex() == 2:  # Défocus
                half_angle = core.calibrated_half_angle()
                defocus = core.defocus_for_fill_spacing(
                    self.spn_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
                if defocus is None:
                    QtWidgets.QMessageBox.critical(
                        self.spn_inset, "Retrait du bord",
                        "Calibration du point invalide dans les Préférences\n"
                        "(icône engrenage) : impossible de calculer le point\n"
                        "élargi.")
                    return
                spot = core.spot_diameter_at_defocus(
                    defocus, core.SPOT_FOCUS_MM, half_angle)
            else:  # Parallèles / Croisées : trait net au foyer.
                # Si la planche de calibration a été mesurée, on prend la
                # plus GRANDE largeur brûlée mesurée (enveloppe : le S/F
                # du marquage n'est pas encore connu ici) ; sinon le
                # point calibré.
                spot = core.burn_width_focus_max() or core.SPOT_FOCUS_MM
            self.spn_inset.setValue(spot / 2.0)

        self.btn_inset_auto.clicked.connect(_inset_auto)
        row_inset = QtWidgets.QWidget()
        lay_inset = QtWidgets.QHBoxLayout(row_inset)
        lay_inset.setContentsMargins(0, 0, 0, 0)
        lay_inset.addWidget(self.spn_inset, 1)
        lay_inset.addWidget(self.btn_inset_auto)
        form.addRow("Retrait du bord :", row_inset)

        self.chk_hatch_contour = QtWidgets.QCheckBox("Ajouter le contour de la forme")
        self.chk_hatch_contour.setToolTip(
            "Ajoute le CONTOUR de la forme (bord de chaque face, trous\n"
            "compris) à l'objet Hachures créé : le mode Marquage grave\n"
            "ensuite hachures + contour en une seule opération.\n"
            "Le contour suit le bord ORIGINAL de la forme, pas le bord\n"
            "rentré par le retrait ci-dessus (le retrait ne concerne que\n"
            "la brûlure du remplissage).")
        form.addRow(self.chk_hatch_contour)

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
            "contour": self.chk_hatch_contour,
        }
        _restore_last_values("hatch", self._last_fields, selection=self.selection)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Hachures 2D")
        self.form.setWindowIcon(_icon("hatch.svg"))

    def accept(self):
        _save_last_values("hatch", self._last_fields, selection=self.selection)
        fill_type_map = {0: "paralleles", 1: "croisees", 2: "defocus"}
        fill_type = fill_type_map.get(self.combo_filltype.currentIndex(), "paralleles")
        obj, err = core.run_hatch_generation(
            self.selection, self.spn_spacing.value(), self.spn_angle.value(),
            fill_type=fill_type, inset=self.spn_inset.value(),
            contour=self.chk_hatch_contour.isChecked())
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return False
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))
        return True

    def _on_recapture_selection(self):
        """Reprend la sélection courante de la vue / de l'arbre (le panneau
        ne la capture qu'à son ouverture). Hachures lit la sélection au
        moment de CRÉER l'objet : il n'y a donc aucune géométrie mise en
        cache à reconstruire ici, contrairement aux modes de marquage."""
        self.selection = Gui.Selection.getSelectionEx()
        if not self.selection:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Aucune sélection courante. Sélectionne la face 2D (ou "
                "l'esquisse fermée) à remplir dans la vue ou l'arbre, puis "
                "reclique.")
        else:
            FreeCAD.Console.PrintMessage("Sélection reprise.\n")

    def reject(self):
        return True


# ==========================================================================
# MODE : GRAVURE REMPLIE (NOIR) -- remplissage défocus + contour au foyer
# ==========================================================================

def _decalage_surface_depuis_selection():
    """Mesure le décalage de surface depuis la sélection 3D.

    - 1 face plane horizontale : décalage = Z(face) - Z du DESSUS du
      solide qui la porte (le zéro machine est supposé sur le dessus de
      la pièce). Ex. fond d'une poche de 1 mm -> -1.00.
    - 2 faces : décalage = Z(2e face cliquée, la surface à GRAVER)
      - Z(1re face cliquée, la surface où est le ZÉRO).
    Renvoie (décalage, None) ou (None, message d'erreur)."""
    faces = []
    for so in Gui.Selection.getSelectionEx():
        obj = so.Object
        for name in (so.SubElementNames if so.HasSubObjects else []):
            sub = obj.getSubObject(name) if hasattr(obj, "getSubObject") else None
            if sub is None or getattr(sub, "ShapeType", "") != "Face":
                continue
            bb = sub.BoundBox
            if (bb.ZMax - bb.ZMin) > 1e-4:
                return None, ("La face « {} » n'est pas plane horizontale :\n"
                              "sélectionne des faces à plat (dessus de la pièce,\n"
                              "fond de poche...).".format(name))
            faces.append((bb.ZMin, obj))
    if not faces:
        return None, ("Sélectionne d'abord une ou deux faces dans la vue 3D :\n"
                      "- 1 face : la surface à graver -- mesurée par rapport au\n"
                      "  DESSUS de sa pièce (zéro machine sur le dessus) ;\n"
                      "- 2 faces : la face du ZÉRO d'abord, puis la surface à\n"
                      "  graver.")
    if len(faces) == 1:
        z, obj = faces[0]
        return z - obj.Shape.BoundBox.ZMax, None
    if len(faces) == 2:
        return faces[1][0] - faces[0][0], None
    return None, "Sélectionne 1 ou 2 faces (pas plus)."


def _make_surface_offset_row(form):
    """Ligne « Décalage de surface » : spinbox + bouton « Depuis la face
    sélectionnée ». Renvoie le QDoubleSpinBox. 0 = le zéro machine est SUR
    la surface gravée (comportement historique) ; -1 = la surface gravée
    est 1 mm SOUS le zéro (fond de poche, zéro gardé sur le dessus)."""
    spn = QtWidgets.QDoubleSpinBox()
    spn.setRange(-200.0, 200.0)
    spn.setDecimals(2)
    spn.setValue(0.0)
    spn.setSuffix(" mm")
    spn.setToolTip(
        "0 = le zéro machine est SUR la surface gravée (comportement\n"
        "historique : un job = une surface, re-zéro entre les surfaces).\n"
        "-1 = la surface gravée est 1 mm SOUS le zéro machine : permet de\n"
        "garder UN SEUL zéro (le dessus de la pièce) et de graver par ex.\n"
        "le fond d'une poche fraisée de 1 mm sans re-palper. Tout le job\n"
        "(Z de travail, survols) est décalé d'autant.\n"
        "En Marquage, surtout pour le mode À PLAT : laisser 0 en suivi\n"
        "de relief.\n"
        "Poche déjà modélisée en 3D ? La Projection sur surface 3D est\n"
        "plus sûre : elle projette le motif sur la vraie géométrie et\n"
        "montre en direct qu'il tombe bien dans la poche, alors que ce\n"
        "décalage est une valeur tapée à l'aveugle.")
    btn = QtWidgets.QPushButton("Depuis la face sélectionnée")
    btn.setToolTip(
        "Mesure le décalage depuis la vue 3D :\n"
        "- 1 face sélectionnée : Z de la face par rapport au DESSUS de\n"
        "  son solide (zéro supposé sur le dessus de la pièce) ;\n"
        "- 2 faces : la face du ZÉRO d'abord, puis la face à GRAVER.")

    def _apply():
        off, err = _decalage_surface_depuis_selection()
        if err:
            QtWidgets.QMessageBox.information(spn, "Décalage de surface", err)
            return
        spn.setValue(off)

    btn.clicked.connect(_apply)
    row = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(spn, 1)
    lay.addWidget(btn)
    form.addRow("Décalage de surface :", row)
    return spn


def _cle_geometrie_selection(selection):
    """Empreinte de la sélection pour mémoïser la géométrie de remplissage :
    (Name, hashCode de la Shape, sous-éléments) par objet. Le hashCode
    change dès que la forme est recalculée, ce qui invalide le cache."""
    items = []
    for so in selection or []:
        obj = so.Object
        try:
            code = obj.Shape.hashCode() if hasattr(obj, "Shape") else 0
        except Exception:
            code = 0
        subs = (tuple(so.SubElementNames)
                if getattr(so, "HasSubObjects", False) else ())
        items.append((getattr(obj, "Name", "?"), code, subs))
    return tuple(items)


# Mémo à UNE entrée (la dernière géométrie construite) partagé entre les
# aperçus photo successifs et la génération : sur un tracé SVG importé,
# reconstruire faces + hachures coûte plusieurs secondes (voire ~16 s
# avec un retrait qui échoue) -- itérer sur le ton ne change PAS la
# géométrie, seul le rendu doit être refait.
_MEMO_REMPLISSAGE = {"cle_faces": None, "faces": None,
                     "cle_edges": None, "edges": None}


class TaskPanelFilledEngraving:
    def __init__(self, selection):
        self.selection = selection
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _panel_header(form, "filled.svg", "Gravure remplie (noir)")
        _reselect_button(form, self._on_recapture_selection,
                         lambda: self.selection)
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

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Sélectionne la <b>forme 2D fermée</b> à noircir (face, "
            "esquisse fermée, ShapeString/texte Draft). Plusieurs lettres ou "
            "formes&nbsp;: sélectionne-les ensemble.",
            "<b>2.</b> Pose le <b>zéro machine</b>&nbsp;: X/Y au coin de "
            "référence, Z sur la surface à graver (mode Martyre ou Pièce). "
            "«&nbsp;Décalage de surface&nbsp;» sert à graver un fond de poche.",
            "<b>3. Matériau / ton</b>&nbsp;: applique un préréglage matériau ou "
            "choisis un ton du <b>Nuancier</b> (il s'applique aussitôt), sinon "
            "règle puissance/vitesse à la main. Sans nuancier, coche "
            "«&nbsp;Puissance vs défocus&nbsp;» et donne une référence connue.",
            "<b>4. Remplissage</b>&nbsp;: espacement des hachures (resserré "
            "automatiquement à la largeur brûlée mesurée), angle, style de "
            "trait. Option <b>dégradé</b> pour un fondu de puissance.",
            "<b>5. Contour</b> (recommandé pour une arête nette)&nbsp;: "
            "puissance/vitesse au foyer. Il est repassé après le remplissage, "
            "qui se glisse dessous&nbsp;— pas de liseré clair au bord.",
            "<b>6. Vérifie</b>&nbsp;: bouton «&nbsp;Aperçu photo&nbsp;» (rendu "
            "réaliste) et «&nbsp;Aperçu du trajet&nbsp;». Ajuste si le rendu "
            "paraît trop clair ou trop foncé.",
            "<b>7. Génère</b>&nbsp;: «&nbsp;Générer et sauvegarder le "
            "G-code…&nbsp;» (ou «&nbsp;Ajouter au job combiné&nbsp;»). Relis le "
            "<code>G0&nbsp;Z…</code> en tête du .ngc avant de lancer.",
        ])

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

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder")
        _btn_icon(self.btn_save_preset, "sect_preset.svg")
        self.btn_save_preset.setToolTip("Sauvegarde toutes les valeurs du panneau sous un nom.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer")
        self.btn_delete_preset.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        _mat_row = QtWidgets.QWidget()
        _mat_h = QtWidgets.QHBoxLayout(_mat_row)
        _mat_h.setContentsMargins(0, 0, 0, 0)
        _mat_h.addWidget(self.btn_save_preset)
        _mat_h.addWidget(self.btn_delete_preset)
        form.addRow(_mat_row)

        def _apply_shade(s):
            # Ton mesuré du nuancier -> puissance/vitesse du REMPLISSAGE,
            # ET (style plein uniquement -- les styles décoratifs gardent
            # l'espacement voulu, leurs vides sont un choix) l'espacement
            # qui donne un remplissage PLEIN avec ce réglage précis, sans
            # avoir à le deviner à la main : avant, il fallait faire
            # coïncider DEUX choix indépendants (le ton ET l'espacement) ;
            # un seul suffit désormais. L'espacement reste un champ normal
            # -- rien n'empêche de l'élargir ensuite pour aller plus vite
            # sur un aplat, au prix d'un remplissage moins net.
            self.spn_fill_power.setValue(s.get("power", self.spn_fill_power.value()))
            self.spn_fill_feed.setValue(s.get("feed", self.spn_fill_feed.value()))
            if self.combo_fill_style.currentIndex() == 0:
                espacement = core.espacement_pour_reglage(
                    s.get("power"), s.get("feed"), self._materiau(),
                    borne_haute=s.get("width") or None)
                if espacement:
                    self.spn_spacing.setValue(espacement)
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
        self.spn_surface_offset = _make_surface_offset_row(form)

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

        # Verdict court (le détail va en info-bulle) + bouton « Corriger »
        # qui applique le réglage mesuré suggéré -- même schéma que
        # _duration_row (label + bouton dans une seule ligne du formulaire).
        _ligne_recouvrement = QtWidgets.QWidget()
        _mise_en_page_recouvrement = QtWidgets.QHBoxLayout(_ligne_recouvrement)
        _mise_en_page_recouvrement.setContentsMargins(0, 0, 0, 0)
        self.lbl_recouvrement = _WrapLabel("")
        self.lbl_recouvrement.setToolTip(
            "Le remplissage sera-t-il PLEIN ? Compare le trait réellement\n"
            "BRÛLÉ (mesuré avec la planche de calibration, pour le matériau\n"
            "du bloc « Nuancier matériau ») au pas de hachure demandé. Si le\n"
            "trait est plus étroit que le pas, il reste du bois nu entre deux\n"
            "passes : le remplissage sort rayé, en gris, et pas noir.")
        self.btn_corriger_recouvrement = QtWidgets.QPushButton("Corriger")
        self.btn_corriger_recouvrement.setVisible(False)
        self.btn_corriger_recouvrement.clicked.connect(self._on_corriger_recouvrement)
        _mise_en_page_recouvrement.addWidget(self.lbl_recouvrement, 1)
        _mise_en_page_recouvrement.addWidget(self.btn_corriger_recouvrement, 0)
        form.addRow(_ligne_recouvrement)

        # Deuxième verdict, l'autre façon de rater un aplat : non plus le
        # bois nu, mais l'énergie déposée pour rien. « Alléger » et non
        # « Corriger » -- deux échecs opposés (rayé / trop cuit), deux
        # gestes opposés, le libellé doit les distinguer d'un coup d'oeil.
        _ligne_energie = QtWidgets.QWidget()
        _mise_en_page_energie = QtWidgets.QHBoxLayout(_ligne_energie)
        _mise_en_page_energie.setContentsMargins(0, 0, 0, 0)
        self.lbl_energie = _WrapLabel("")
        self.lbl_energie.setToolTip(
            "Énergie déposée par mm² d'aplat -- S / (pas x vitesse) --\n"
            "comparée au réglage NOIR le plus économe que tu aies mesuré\n"
            "sur ce matériau. Au-delà du noir, l'énergie en trop ne fait\n"
            "que creuser et roussir ; et à puissance égale elle se paie\n"
            "aussi en temps, exactement dans le même rapport.")
        self.btn_alleger = QtWidgets.QPushButton("Alléger")
        self.btn_alleger.setVisible(False)
        self.btn_alleger.clicked.connect(self._on_alleger)
        _mise_en_page_energie.addWidget(self.lbl_energie, 1)
        _mise_en_page_energie.addWidget(self.btn_alleger, 0)
        form.addRow(_ligne_energie)

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

        self.chk_fill_grad = QtWidgets.QCheckBox("Remplissage en dégradé")
        self.chk_fill_grad.setToolTip(
            "La puissance du remplissage varie LINÉAIREMENT le long d'une\n"
            "direction : de « Puissance remplissage » (début) à « S en fin\n"
            "de dégradé », d'un bord à l'autre de la forme. Style « plein »\n"
            "uniquement. L'espacement des hachures est resserré sur la\n"
            "largeur brûlée de la puissance la plus FAIBLE du dégradé\n"
            "(planche de calibration) pour rester uniforme partout.")
        form.addRow(self.chk_fill_grad)
        self.spn_grad_power_fin = QtWidgets.QDoubleSpinBox()
        self.spn_grad_power_fin.setRange(0, core.S_MAX)
        self.spn_grad_power_fin.setValue(200)
        self.spn_grad_power_fin.setToolTip(
            "Puissance (S) atteinte en FIN de dégradé (le début est la\n"
            "« Puissance remplissage » ci-dessus). Plus faible = plus clair.")
        form.addRow("S en fin de dégradé :", self.spn_grad_power_fin)
        self.spn_grad_angle = QtWidgets.QDoubleSpinBox()
        self.spn_grad_angle.setRange(0.0, 360.0)
        self.spn_grad_angle.setValue(0.0)
        self.spn_grad_angle.setSuffix(" °")
        self.spn_grad_angle.setToolTip(
            "Direction du dégradé dans le plan : 0° = de gauche à droite\n"
            "(début à gauche), 90° = de bas en haut, etc.")
        form.addRow("Direction du dégradé :", self.spn_grad_angle)

        def _update_grad_enabled(*_):
            actif = self.chk_fill_grad.isChecked()
            plein = self.combo_fill_style.currentIndex() == 0
            self.chk_fill_grad.setEnabled(plein)
            self.spn_grad_power_fin.setEnabled(actif and plein)
            self.spn_grad_angle.setEnabled(actif and plein)
        self.chk_fill_grad.toggled.connect(_update_grad_enabled)
        self.combo_fill_style.currentIndexChanged.connect(_update_grad_enabled)
        _update_grad_enabled()

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
            # Le nuancier gagne toujours sur la compensation de fluence --
            # en premier, avant de lire fluence["chk"] plus bas.
            _appliquer_priorite_nuancier(self._shade_picker, self._fluence)
            # Calibration du point : centralisée dans les Préférences.
            half_angle = core.calibrated_half_angle()
            defocus = core.defocus_for_fill_spacing(
                self.spn_spacing.value(), core.SPOT_FOCUS_MM, half_angle)
            if defocus is None:
                self.lbl_defocus_result.setText(
                    "Défocus calculé : -- (calibration du point invalide dans\n"
                    "les Préférences : le point au défocus de test doit être\n"
                    "plus large qu'au foyer).")
                # Sans défocus calculable, pas de pas de hachure fiable à
                # comparer : on masque plutôt que de laisser un verdict périmé.
                self._maj_recouvrement(None, None, 0.0, decoratif=True)
            else:
                spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
                # Retour de la correction par la planche (largeur brûlée
                # mesurée), même logique que _build_edges.
                spacing = self.spn_spacing.value()
                fill_width = spot
                if self.combo_fill_style.currentIndex() == 0:
                    power = self._effective_fill_power(defocus, half_angle)
                    burn = core.burn_width_defocus_scaled(
                        power, self.spn_fill_feed.value(), defocus, self._materiau())
                    if burn:
                        fill_width = min(spot, burn)
                    self._maj_recouvrement(burn, power, spacing, defocus)
                else:
                    self._maj_recouvrement(None, None, spacing, decoratif=True)
                inset = self._fill_inset(fill_width, half_angle)
                self.lbl_defocus_result.setText(
                    "Défocus calculé : {:.2f} mm (bec remonté d'autant) -- point\n"
                    "{:.3f} mm, remplissage rentré de {:.3f} mm du bord.\n"
                    "(Calibration du point : Préférences, icône engrenage.)".format(
                        defocus, spot, inset))
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
        # Le matériau choisit la table des largeurs brûlées : en changer
        # doit recalculer le verdict de recouvrement des hachures.
        self._shade_picker["mat"].currentIndexChanged.connect(
            lambda _i: _update_defocus_preview())
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
        # Le style de remplissage conditionne aussi la correction planche.
        self.combo_fill_style.currentIndexChanged.connect(lambda _i: _update_defocus_preview())
        self.combo_contour_style.currentIndexChanged.connect(lambda _i: _update_style_preview())
        for w in (self.spn_wave_period, self.spn_fill_wave_width, self.spn_fill_feed,
                  self.spn_contour_feed, self.spn_contour_width):
            w.valueChanged.connect(lambda _v: _update_style_preview())

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        _combined_add_button(form, self._on_add_to_combined)
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à la vitesse rapide des Préférences.")

        self.btn_save_gcode = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_save_gcode, "sect_gcode.svg")
        self.btn_save_gcode.setToolTip(
            "Génère le G-code avec les réglages actuels et propose le\n"
            "fichier de sauvegarde. Le bouton OK, lui, se contente de\n"
            "SAUVEGARDER LES RÉGLAGES (sur la forme + objet Job) et ferme\n"
            "le panneau sans générer.")
        self.btn_save_gcode.clicked.connect(self._on_save_gcode)
        form.addRow(self.btn_save_gcode)

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Crée un FICHIER À PART traçant le rectangle englobant, laser\n"
            "éteint (ou faisceau de visée : voir Préférences) -- à lancer\n"
            "seul pour vérifier le positionnement avant le vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Aperçu du trajet (vue 3D) : gris fin = transit éteint, rouge =\n"
            "gravure. Vérifie que le remplissage tient dans le contour.\n"
            "Purement visuel.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        self.btn_photo_preview = QtWidgets.QPushButton()
        self.btn_photo_preview.setToolTip(
            "Aperçu photo (rendu réaliste) : chaque trait à sa largeur brûlée\n"
            "et à sa teinte -- la noirceur MESURÉE du nuancier du matériau\n"
            "sélectionné ci-dessus quand elle existe, sinon un modèle\n"
            "théorique --, superpositions plus foncées.")
        self.btn_photo_preview.clicked.connect(self._on_photo_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg"),
                            (self.btn_photo_preview, "sect_photo.svg")])

        self._last_fields = {
            "spacing": self.spn_spacing, "surface_offset": self.spn_surface_offset, "angle": self.spn_angle,
            "fill_power": self.spn_fill_power, "fill_feed": self.spn_fill_feed,
            "perimeter": self.chk_perimeter,
            "contour": self.chk_contour, "contour_power": self.spn_contour_power,
            "contour_feed": self.spn_contour_feed, "contour_width": self.spn_contour_width,
            "fill_style": self.combo_fill_style, "contour_style": self.combo_contour_style,
            "fill_grad": self.chk_fill_grad, "grad_power_fin": self.spn_grad_power_fin,
            "grad_angle": self.spn_grad_angle,
            "dash_len": self.spn_dash_len, "gap_len": self.spn_gap_len,
            "dot_spacing": self.spn_dot_spacing, "dot_dwell_ms": self.spn_dot_dwell,
            "wave_period": self.spn_wave_period, "fill_wave_width": self.spn_fill_wave_width,
            "fluence_on": self._fluence["chk"], "ref_power": self._fluence["ref_power"],
            "ref_feed": self._fluence["ref_feed"], "ref_spot": self._fluence["ref_spot"],
        }
        _restore_last_values("filled", self._last_fields, selection=self.selection)

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

    def _materiau(self):
        """Matériau retenu pour les largeurs brûlées MESURÉES : celui du
        bloc « Nuancier matériau ». Sans lui, core ne sait choisir une
        table que s'il n'existe qu'un seul matériau mesuré -- dès le
        deuxième, la correction par la planche se désactivait en silence
        et les hachures restaient à l'espacement demandé, même quand le
        trait brûlé était deux fois plus étroit (remplissage rayé)."""
        picker = getattr(self, "_shade_picker", None)
        if picker is None:
            return None
        # currentData() est None sur l'entrée « -- (nuancier vide) -- » :
        # pas de currentText() ici, un libellé ne doit pas passer pour un
        # nom de matériau.
        return picker["mat"].currentData() or None

    def _maj_recouvrement(self, burn, power, spacing, defocus=0.0, decoratif=False):
        """Met à jour le verdict « le remplissage sera-t-il PLEIN ? » --
        la première question que pose une planche gravée. Compare le trait
        RÉELLEMENT brûlé (planche de calibration) au pas de hachure : s'il
        est plus étroit, il reste du bois nu entre deux passes et le
        remplissage sort rayé. Le libellé reste court (une clause) ; le
        détail (largeur mesurée, coût du resserrement) va dans l'info-bulle
        plutôt que dans un paragraphe à lire à chaque fois. Quand un
        réglage mesuré couvre le pas sans resserrer, le bouton « Corriger »
        l'applique directement -- élargir le trait vaut presque toujours
        mieux que tripler le nombre de lignes."""
        lbl = self.lbl_recouvrement
        btn = self.btn_corriger_recouvrement
        self._reglage_recouvrement_suggere = None
        # L'autre verdict en premier, pour qu'aucun des retours anticipés
        # ci-dessous ne le laisse afficher un état périmé.
        self._maj_energie(power, spacing, decoratif)
        if decoratif:
            # Tirets, pointillé, vague : les vides sont voulus.
            lbl.setText("")
            lbl.setToolTip("")
            lbl.setVisible(False)
            btn.setVisible(False)
            return
        lbl.setVisible(True)
        btn.setVisible(False)
        mat = self._materiau()
        if burn is None:
            lbl.setText("Recouvrement non vérifié.")
            lbl.setStyleSheet("color: #b0740a;")
            if not mat:
                # La liste « Nuancier matériau » ne propose que les matériaux
                # du nuancier : vide, il n'y a rien à choisir.
                lbl.setToolTip(
                    "Aucun matériau dans « Nuancier matériau » ci-dessus :\n"
                    "l'atelier ne sait pas quelle largeur brûlée comparer\n"
                    "au pas de hachure.")
            else:
                lbl.setToolTip(
                    "Aucune largeur brûlée mesurée pour {} (planche de\n"
                    "calibration, sections 1-2).".format(mat))
            return
        if burn >= spacing - 1e-6:
            lbl.setText("Remplissage plein (trait {:.2f} mm pour un pas de {:.2f} mm).".format(
                burn, spacing))
            lbl.setStyleSheet("color: #2e7d32;")
            lbl.setToolTip(
                "Trait brûlé mesuré à S{:.0f} : {:.2f} mm, au moins aussi\n"
                "large que le pas de {:.2f} mm -- pas de bande de bois nu\n"
                "entre deux passes.".format(power, burn, spacing))
            return
        ratio = spacing / max(burn, 1e-9)
        lbl.setText("Remplissage RAYÉ (trait {:.2f} mm pour un pas de {:.2f} mm).".format(
            burn, spacing))
        lbl.setStyleSheet("color: #b0740a;")
        tip = (
            "Trait brûlé mesuré à S{:.0f} : {:.2f} mm, plus étroit que le\n"
            "pas de {:.2f} mm demandé -- il reste du bois nu entre deux\n"
            "passes. L'atelier resserre les hachures à {:.2f} mm pour\n"
            "compenser, ce qui multiplie la durée du job par {:.1f}.".format(
                power, burn, spacing, min(spacing, burn), ratio))
        sugg = core.reglage_couvrant_le_pas(spacing, mat, defocus)
        if sugg:
            self._reglage_recouvrement_suggere = sugg
            btn.setText("Corriger : S{:.0f} / F{:.0f}".format(sugg["power"], sugg["feed"]))
            btn.setToolTip(
                "Applique S{:.0f} / F{:.0f} -- ce réglage MESURÉ brûle\n"
                "{:.2f} mm, assez pour couvrir le pas de {:.2f} mm sans\n"
                "resserrer les hachures.".format(
                    sugg["power"], sugg["feed"], sugg["width"], spacing))
            btn.setVisible(True)
        else:
            tip += (
                "\nAucun réglage mesuré ne couvre ce pas : élargis le\n"
                "trait (plus de puissance, moins de vitesse), ou mesure\n"
                "d'autres réglages avec la planche de calibration.")
        lbl.setToolTip(tip)

    def _on_corriger_recouvrement(self):
        """Bouton « Corriger » : applique le réglage mesuré suggéré par
        `_maj_recouvrement` (le plus rapide qui couvre le pas de hachure)
        et rafraîchit l'aperçu -- élargir le trait plutôt que resserrer
        les hachures."""
        sugg = getattr(self, "_reglage_recouvrement_suggere", None)
        if not sugg:
            return
        self.spn_fill_power.setValue(sugg["power"])
        self.spn_fill_feed.setValue(sugg["feed"])
        self._update_defocus_preview()

    def _reference_noire(self, mat):
        """Le remplissage NOIR le plus économe mesuré sur ce matériau,
        mémorisé le temps du panneau : la recherche bissecte une fois par
        ton candidat (~12 ms chacun) alors que l'aperçu se rafraîchit à
        chaque frappe. Un ton mesuré dans un autre panneau pendant ce
        temps-là n'apparaîtra qu'à la réouverture -- c'est le rythme réel
        de l'établi, on grave avant de ressaisir."""
        if not mat:
            return None
        cache = getattr(self, "_cache_reference_noire", None)
        if cache is None:
            cache = self._cache_reference_noire = {}
        if mat not in cache:
            cache[mat] = core.remplissage_noir_le_plus_econome(mat)
        return cache[mat]

    def _maj_energie(self, power, spacing, decoratif=False):
        """Verdict « ce remplissage coûte-t-il plus que nécessaire ? ».

        Le pendant du verdict de recouvrement : celui-là dit s'il restera
        du bois nu, celui-ci ce qu'on dépense au-delà du noir. Les deux
        échecs sont opposés et ne se voient pas au même endroit -- un aplat
        peut être parfaitement PLEIN et complètement surcuit. C'est
        exactement ce qui est arrivé le 30/07/2026 : un carré S1000/F800 au
        foyer au pas 0,26 (trait mesuré 0,30, donc verdict vert « plein »)
        est sorti carbonisé, et rien dans le panneau n'en disait un mot.

        Ce que la ligne annonce est un COÛT, pas un dommage : l'atelier ne
        sait pas prédire la carbonisation (sur MDF des tons jugés 97 %
        tiennent à 4x le plus économe). Elle compare deux remplissages
        calculés de la même façon et laisse trancher."""
        lbl = self.lbl_energie
        btn = self.btn_alleger
        self._reglage_allege = None
        btn.setVisible(False)
        mat = self._materiau()
        feed = self.spn_fill_feed.value()
        e = None if (decoratif or power is None) else core.energie_surfacique(
            power, feed, spacing)
        ref = None if e is None else self._reference_noire(mat)
        if ref is None:
            # Rien de mesuré à quoi se comparer : se taire plutôt que
            # d'afficher un chiffre sans référence.
            lbl.setText("")
            lbl.setVisible(False)
            return
        lbl.setVisible(True)
        rapport = e / ref["energie"]
        # La durée se calcule à part : elle ne suit l'énergie que si les
        # deux réglages ont la MÊME puissance (les deux varient en
        # 1/(pas x vitesse), l'énergie porte S en plus).
        duree = (ref["spacing"] * ref["feed"]) / max(spacing * feed, 1e-9)
        detail = (
            "Ce remplissage : S{:.0f} / F{:.0f} / pas {:.2f} mm.\n"
            "Le plus économe mesuré noir ({:.0f} %) : S{:.0f} / F{:.0f} /\n"
            "pas {:.2f} mm{}.\n"
            "Énergie par mm² : {:.2f} contre {:.2f} (indice S/(pas x F),\n"
            "pas des joules -- seul le rapport a un sens).".format(
                power, feed, spacing, ref["darkness"], ref["power"],
                ref["feed"], ref["spacing"],
                " en défocus {:.0f} mm".format(ref["z_offset"])
                if ref["z_offset"] else " au foyer",
                e, ref["energie"]))
        if rapport <= core.SEUIL_ENERGIE_REMPLISSAGE:
            lbl.setText("Énergie mesurée : {:.1f}x le noir le plus économe.".format(
                rapport))
            lbl.setStyleSheet("color: #2e7d32;")
            lbl.setToolTip(detail)
            return
        lbl.setText("Énergie EXCESSIVE : {:.1f}x le noir le plus économe, "
                    "et {:.1f}x plus long.".format(rapport, duree))
        lbl.setStyleSheet("color: #b0740a;")
        self._reglage_allege = ref
        btn.setText("Alléger : S{:.0f} / F{:.0f} / pas {:.2f}".format(
            ref["power"], ref["feed"], ref["spacing"]))
        btn.setToolTip(
            detail + "\n\nLe bouton applique ce réglage MESURÉ noir, pas et\n"
            "tout : même noir jugé, {:.1f}x moins d'énergie, {:.1f}x plus\n"
            "vite. Au-delà du noir l'énergie en trop ne fait que creuser.".format(
                rapport, duree))
        btn.setVisible(True)
        lbl.setToolTip(detail)

    def _on_alleger(self):
        """Bouton « Alléger » : applique le remplissage noir mesuré le plus
        économe -- puissance, vitesse ET pas, comme le fait déjà le clic
        sur un ton du nuancier. Le pas fait partie du réglage : c'est lui
        qui fixe le défocus, donc la largeur du trait, donc l'énergie."""
        ref = getattr(self, "_reglage_allege", None)
        if not ref:
            return
        self.spn_fill_power.setValue(ref["power"])
        self.spn_fill_feed.setValue(ref["feed"])
        self.spn_spacing.setValue(ref["spacing"])
        self._update_defocus_preview()

    def _effective_fill_power(self, defocus, half_angle):
        """Puissance de remplissage réellement émise : celle du champ, ou
        celle recalculée par la compensation de fluence si elle est cochée
        (c'est elle qui décide de la largeur brûlée réelle)."""
        power = self.spn_fill_power.value()
        spot = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
        _, _, p_eff = _fluence_advice(spot, power, self.spn_fill_feed.value(), self._fluence)
        return p_eff if p_eff is not None else power

    def _fill_inset(self, fill_width, half_angle):
        """Retrait du remplissage par rapport au contour (mm) : un rayon de
        brûlure, MOINS le rayon du trait de contour quand celui-ci est
        gravé. Le remplissage passe alors volontairement SOUS le contour
        (repassé au foyer par-dessus, il le masque) -- ce qui comble le
        petit liseré clair laissé au bord, surtout à FORT DÉFOCUS où le
        modèle optique surestime la brûlure réelle et rentre donc trop. Le
        débord vers l'extérieur est borné au rayon du contour : invisible.
        Sans contour, retrait plein (rayon de brûlure) pour ne pas déborder
        d'un bord qui, lui, resterait nu."""
        inset = fill_width / 2.0
        chk = getattr(self, "chk_contour", None)
        if chk is not None and chk.isChecked():
            c_off = self._contour_offset(half_angle)
            c_spot = core.spot_diameter_at_defocus(c_off, core.SPOT_FOCUS_MM, half_angle)
            c_burn = core.burn_width_defocus_scaled(
                self.spn_contour_power.value(), self.spn_contour_feed.value(), c_off,
                self._materiau()) or c_spot
            inset = max(0.0, inset - c_burn / 2.0)
        return inset

    def _build_edges(self, silent=False):
        """Renvoie (fill_edges, contour_edges, defocus, contour_z_offset) ou
        (None, None, None, None) si la sélection est vide ou la calibration
        défocus invalide."""
        self._burn_note = None
        cle_faces = _cle_geometrie_selection(self.selection)
        if (_MEMO_REMPLISSAGE["cle_faces"] == cle_faces
                and _MEMO_REMPLISSAGE["faces"]):
            faces = _MEMO_REMPLISSAGE["faces"]
        else:
            faces = core.get_faces_from_selection_for_hatch(self.selection)
            _MEMO_REMPLISSAGE["cle_faces"] = cle_faces
            _MEMO_REMPLISSAGE["faces"] = faces
            _MEMO_REMPLISSAGE["cle_edges"] = None  # géométrie changée
        if not faces:
            if not silent:
                hint = ""
                if any("Hachures" in getattr(so.Object, "Label", "")
                       for so in (self.selection or [])):
                    hint = ("\n\nTa sélection contient des objets de TRAITS "
                            "(Hachures...). Ce mode fabrique lui-même le "
                            "remplissage à partir d'une forme FERMÉE -- pour "
                            "graver des traits existants, utilise plutôt le "
                            "mode « Marquage de motif ».")
                QtWidgets.QMessageBox.critical(
                    self.form, "Erreur",
                    "Aucune face 2D fermée trouvée dans la sélection\n"
                    "(face, Draft, ou sketch à fils fermés)." + hint)
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
        spacing = self.spn_spacing.value()
        hatch_spacing, fill_width = spacing, spot
        # Correction par la planche de calibration : au défocus la brûlure
        # RÉELLE est plus étroite que le point optique aux faibles
        # puissances (0,50 mm à S200 contre 1,18 optique sur MDF) -- c'est
        # elle qui décide si deux hachures se rejoignent. Si le matériau a
        # des mesures, l'espacement et le rentré s'alignent dessus (jamais
        # élargis au-delà de la demande). Style "plein" uniquement : les
        # autres styles de remplissage sont décoratifs, leurs vides sont
        # voulus.
        if self.combo_fill_style.currentIndex() == 0:
            power = self._effective_fill_power(defocus, half_angle)
            # En dégradé, la zone la plus CLAIRE (S le plus faible) a la
            # brûlure la plus étroite : c'est elle qui dicte l'espacement.
            if self.chk_fill_grad.isChecked():
                s0 = max(self.spn_fill_power.value(), 1e-9)
                power = power * min(1.0, self.spn_grad_power_fin.value() / s0)
            burn = core.burn_width_defocus_scaled(power, self.spn_fill_feed.value(),
                                                  defocus, self._materiau())
            if burn:
                hatch_spacing = min(spacing, burn)
                fill_width = min(spot, burn)
                if hatch_spacing < spacing - 1e-6:
                    self._burn_note = (
                        "Espacement resserre a {:.2f} mm : brulure mesuree "
                        "{:.2f} mm a S{:.0f}, planche de calibration".format(
                            hatch_spacing, burn, power))
        fill_inset = self._fill_inset(fill_width, half_angle)
        cle_edges = (cle_faces, round(hatch_spacing, 6),
                     round(self.spn_angle.value(), 6), round(fill_inset, 6),
                     self.chk_perimeter.isChecked())
        if _MEMO_REMPLISSAGE["cle_edges"] == cle_edges:
            fill_edges, contour_edges = _MEMO_REMPLISSAGE["edges"]
        else:
            fill_edges, contour_edges = core.build_filled_engraving_edges(
                faces, hatch_spacing, self.spn_angle.value(),
                fill_inset=fill_inset,
                add_perimeter=self.chk_perimeter.isChecked())
            _MEMO_REMPLISSAGE["cle_edges"] = cle_edges
            _MEMO_REMPLISSAGE["edges"] = (fill_edges, contour_edges)
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
        fill_power = self._effective_fill_power(defocus, half_angle)
        grad_fin = None
        if self.chk_fill_grad.isChecked() and fill_style == "plein":
            # Le S de fin subit le même rapport que le S de début si la
            # compensation de fluence a modifié la puissance effective.
            s0 = max(self.spn_fill_power.value(), 1e-9)
            grad_fin = self.spn_grad_power_fin.value() * fill_power / s0
        return {
            "grad_power_fin": grad_fin,
            "grad_angle_deg": self.spn_grad_angle.value(),
            "header_note": getattr(self, "_burn_note", None),
            "z_focus": core.Z_WORK_MM + self.spn_surface_offset.value(),
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

    def _on_recapture_selection(self):
        """Reprend la sélection courante de la vue / de l'arbre (le panneau ne
        la capture qu'à son ouverture)."""
        self.selection = Gui.Selection.getSelectionEx()
        self._update_duration_preview()
        if not self.selection:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Aucune sélection courante. Sélectionne la forme fermée (face, "
                "sketch, ShapeString) dans la vue ou l'arbre, puis reclique.")
        else:
            FreeCAD.Console.PrintMessage("Sélection reprise.\n")

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

    def _on_photo_preview(self):
        """Rendu réaliste (image) du résultat gravé : remplissage à sa
        largeur/teinte et contour repassé par-dessus."""
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return
        half_angle = core.calibrated_half_angle()
        strokes = []
        # Remplissage : largeur = brûlure mesurée (sinon point optique) ;
        # teinte = noirceur mesurée du nuancier (matériau du bloc
        # « Nuancier matériau »), sinon modèle de fluence.
        mat_nuancier = (self._shade_picker["mat"].currentData()
                        or self._shade_picker["mat"].currentText())
        fill_power = self._effective_fill_power(defocus, half_angle)
        spot_fill = core.spot_diameter_at_defocus(defocus, core.SPOT_FOCUS_MM, half_angle)
        fill_width = core.burn_width_defocus_scaled(
            fill_power, self.spn_fill_feed.value(), defocus, self._materiau()) or spot_fill
        fill_tone = _tone_measured(mat_nuancier, fill_power,
                                   self.spn_fill_feed.value(), defocus)
        if fill_tone is None:
            fill_tone = _tone_burn(fill_power, self.spn_fill_feed.value(), fill_width)
        for e in (fill_edges or []):
            pts = _discretize_edge(e)
            if pts:
                strokes.append((pts, fill_width, fill_tone))
        # Contour repassé (si coché), net au foyer -> plus foncé.
        if self.chk_contour.isChecked() and contour_edges:
            c_power = self.spn_contour_power.value()
            spot_c = core.spot_diameter_at_defocus(contour_z_offset, core.SPOT_FOCUS_MM, half_angle)
            c_width = core.burn_width_defocus_scaled(
                c_power, self.spn_contour_feed.value(), contour_z_offset,
                self._materiau()) or spot_c
            c_tone = _tone_measured(mat_nuancier, c_power,
                                    self.spn_contour_feed.value(), contour_z_offset)
            if c_tone is None:
                c_tone = _tone_burn(c_power, self.spn_contour_feed.value(), c_width)
            for e in contour_edges:
                pts = _discretize_edge(e)
                if pts:
                    strokes.append((pts, c_width, c_tone))
        if not strokes:
            QtWidgets.QMessageBox.information(
                self.form, "Aperçu photo", "Rien à afficher (aucun trait).")
            return
        img = _render_engraving_photo(strokes)
        if img is None:
            QtWidgets.QMessageBox.critical(self.form, "Aperçu photo", "Rendu impossible.")
            return
        _show_image_dialog(img, "Aperçu photo — Gravure remplie")

    def _build_combined_operation(self):
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return None
        if not fill_edges and not self.chk_contour.isChecked():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Rien à graver : le remplissage est vide (motif plus fin que\n"
                "le point défocalisé) et le contour est décoché.")
            return None
        _save_last_values("filled", self._last_fields, selection=self.selection)
        return {"type": "filled",
                "label": "Gravure remplie (S{:.0f})".format(self.spn_fill_power.value()),
                "params": dict(fill_edges=fill_edges, contour_edges=contour_edges,
                               **self._gen_kwargs(defocus, contour_z_offset))}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def accept(self):
        """OK : sauvegarde les réglages (forme + objet Job + derniers
        réglages du panneau) et ferme -- la génération du G-code passe
        par le bouton « Générer et sauvegarder le G-code… »."""
        _save_last_values("filled", self._last_fields, selection=self.selection)
        return True

    def _on_save_gcode(self):
        _save_last_values("filled", self._last_fields, selection=self.selection)
        fill_edges, contour_edges, defocus, contour_z_offset = self._build_edges()
        if fill_edges is None:
            return False
        if not fill_edges and not self.chk_contour.isChecked():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Rien à graver : le remplissage est vide (motif plus fin que\n"
                "le point défocalisé) et le contour est décoché.")
            return False

        gcode = core.generate_gcode_filled_engraving(
            fill_edges, contour_edges,
            **self._gen_kwargs(defocus, contour_z_offset))

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

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Prépare le <b>motif 2D à plat</b> (texte ShapeString, "
            "hachures, tracés Draft) et la <b>surface 3D</b> cible (sphère, "
            "vague, coque…).",
            "<b>2.</b> Dans la vue 3D, sélectionne les <b>motifs 2D ET la "
            "surface</b>, tout ensemble. L'état ci-dessous passe au vert quand "
            "la sélection est valide (exactement une surface + ≥ 1 motif).",
            "<b>3.</b> Clique <b>OK</b>&nbsp;: les motifs sont projetés sur la "
            "surface en un objet <code>Motif_Projete</code>.",
            "<b>4.</b> Enchaîne avec <b>Marquage de motif</b> ou <b>Découpe "
            "courbe</b>&nbsp;: sélectionne l'objet projeté <b>+</b> le modèle 3D "
            "pour graver/découper en suivant le relief.",
        ])

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
# MODE : IMPORT SVG (géométrie directe, sans détour DXF)
# ==========================================================================
class TaskPanelImportSVG:
    """Panneau minimal : choisir un .svg, OK importe. Un Part::Feature par
    élément <path> d'origine (sélectionnable individuellement ensuite),
    couleur de remplissage posée en couleur de trait. Rien à persister
    entre sessions, pas de génération de G-code ici."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        _panel_header(form, "import_svg.svg", "Importer un dessin SVG")
        _intro(form,
               "Importe un fichier .svg directement en objets géométriques : "
               "un objet par tracé d'origine, prêt pour Hachures, Gravure "
               "remplie ou Marquage.",
               "Les courbes (Bézier, arcs) sont aplaties en petits segments, "
               "comme partout dans l'atelier. La couleur de remplissage de "
               "chaque tracé (héritée des groupes) devient sa couleur de "
               "trait dans l'arbre -- une aide visuelle pour repérer les "
               "zones. Pas encore pris en charge (signalé à l'import, jamais "
               "bloquant) : <code>&lt;use&gt;</code>, dégradés, "
               "<code>&lt;clipPath&gt;</code>/<code>&lt;mask&gt;</code>, "
               "images matricielles incorporées, classes CSS. Pour du texte, "
               "convertis-le en tracés dans Inkscape avant l'export.")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Choisis le fichier <b>.svg</b> ci-dessous.",
            "<b>2.</b> Clique <b>OK</b>&nbsp;: chaque tracé "
            "<code>&lt;path&gt;</code> d'origine devient UN objet, "
            "sélectionnable individuellement (utile pour appliquer ensuite "
            "des tons différents par zone).",
            "<b>3.</b> Enchaîne avec <b>Hachures</b>, <b>Gravure remplie</b> "
            "ou <b>Marquage de motif</b> sur les objets importés.",
        ])

        _section(form, "Fichier", "sect_preview.svg")
        self.edt_path = QtWidgets.QLineEdit()
        self.edt_path.setToolTip("Chemin du fichier SVG à importer.")
        btn_browse = QtWidgets.QPushButton("Parcourir...")
        btn_browse.clicked.connect(self._on_browse)
        row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.edt_path, 1)
        row_layout.addWidget(btn_browse, 0)
        form.addRow("Fichier SVG :", row)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Importer un dessin SVG")
        self.form.setWindowIcon(_icon("import_svg.svg"))

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self.form, "Choisir un fichier SVG",
            self.edt_path.text() or os.path.expanduser("~"),
            "Fichiers SVG (*.svg);;Tous les fichiers (*)")
        if path:
            self.edt_path.setText(path)

    def accept(self):
        path = self.edt_path.text().strip()
        if not path:
            QtWidgets.QMessageBox.warning(
                self.form, "Import SVG", "Choisis d'abord un fichier .svg.")
            return False
        import svg_import
        count, warnings = svg_import.import_svg_file(path)
        for w in warnings:
            FreeCAD.Console.PrintWarning("Import SVG : {}\n".format(w))
        if count == 0:
            QtWidgets.QMessageBox.critical(
                self.form, "Import SVG",
                "\n".join(warnings) or "Aucun tracé exploitable dans ce fichier.")
            return False
        FreeCAD.Console.PrintMessage(
            "Import SVG : {} objet(s) créé(s) depuis {}.\n".format(
                count, os.path.basename(path)))
        if warnings:
            QtWidgets.QMessageBox.information(
                self.form, "Import SVG",
                "{} objet(s) importé(s), avec {} avertissement(s) -- "
                "détail dans la vue Rapport.".format(count, len(warnings)))
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
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
        self._formlayout = form

        _panel_header(form, "kerf.svg", "Calibration kerf")
        _calibration_banner(form, "Calibration kerf")
        _intro(form,
               "Deux tests, à découper ensuite en mode Découpe multi-passes : "
               "le CARRÉ pour MESURER le kerf, le TENON + MORTAISE pour VALIDER "
               "l'ajustement réel une fois le kerf connu.")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Choisis le test&nbsp;: <b>Carré</b> (mesure du kerf) ou "
            "<b>Tenon + mortaise</b> (validation de l'ajustement). Règle la "
            "taille&nbsp;; OK crée la géométrie.",
            "<b>2.</b> Découpe-la en <b>Découpe multi-passes</b>, avec "
            "<b>Compensation de kerf = 0</b>.",
            "<b>3.</b> Mesure la pièce&nbsp;: <b>kerf = taille dessinée − taille "
            "mesurée</b>. Reporte cette valeur dans «&nbsp;Compensation de "
            "kerf&nbsp;» des modes de découpe.",
            "<b>4. Valide</b> (facultatif)&nbsp;: découpe le <b>tenon + "
            "mortaise</b>, insère le tenon dans chaque mortaise et retiens le "
            "<b>jeu</b> (gravé sous chacune) qui donne l'ajustement voulu&nbsp;— "
            "serré pour coller, glissant pour du démontable.",
        ])

        _section(form, "① Graver le test", "sect_contour.svg")
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

        self.btn_creer_test = QtWidgets.QPushButton("Créer le test dans le document")
        _btn_icon(self.btn_creer_test, "sect_contour.svg")
        self.btn_creer_test.setToolTip(
            "Crée la géométrie du test (carré, ou tenons) dans le document :\n"
            "découpe-la ensuite avec le mode Découpe. Le panneau reste ouvert\n"
            "pour saisir la mesure (②). OK, lui, ferme le panneau.")
        self.btn_creer_test.clicked.connect(self._on_creer_test)
        form.addRow(self.btn_creer_test)

        self._build_kerf_measures(form)
        self._photo = _make_photo_section(form, lambda: "kerf",
                                          titre="③ Photo du résultat")

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Calibration kerf")
        self.form.setWindowIcon(_icon("kerf.svg"))
        self._photo["reload"]()

    def _build_kerf_measures(self, form):
        """Section ② : petit calcul de kerf inline. On grave le carré
        (Compensation = 0), on mesure la pièce, kerf = dessiné − mesuré."""
        _section(form, "② Entrer les mesures (kerf)", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "Après avoir découpé le CARRÉ (Compensation de kerf = 0), mesure "
            "la pièce au pied à coulisse. Le kerf est calculé ici : reporte-le "
            "dans « Compensation de kerf » des modes de découpe."))
        self.spn_measured = QtWidgets.QDoubleSpinBox()
        self.spn_measured.setRange(0.0, 200.0)
        self.spn_measured.setDecimals(2)
        self.spn_measured.setSuffix(" mm")
        self.spn_measured.setSpecialValueText("—")
        self.spn_measured.setToolTip(
            "Côté du carré RÉELLEMENT obtenu, mesuré au pied à coulisse.")
        form.addRow("Taille mesurée :", self.spn_measured)
        self.chk_verrou_kerf = _verrou(form, [self.spn_measured])
        self.lbl_kerf = _WrapLabel("Kerf = — (saisis la taille mesurée)")
        form.addRow(self.lbl_kerf)
        self.spn_measured.valueChanged.connect(self._update_kerf)
        self.spn_size.valueChanged.connect(self._update_kerf)
        self._update_kerf()

    def _update_kerf(self):
        drawn = self.spn_size.value()
        meas = self.spn_measured.value()
        if meas <= 0:
            self.lbl_kerf.setText("Kerf = — (saisis la taille mesurée)")
            return
        self.lbl_kerf.setText(
            "<b>Kerf = {:.2f} mm</b> (dessiné {:.1f} − mesuré {:.2f}) — "
            "reporte-le dans « Compensation de kerf ».".format(
                drawn - meas, drawn, meas))

    def _sync_mode(self):
        fit = self.combo_test.currentIndex() == 1
        for w in self._square_rows:
            _set_row_visible(self._formlayout, w, not fit)
        for w in self._fit_rows:
            _set_row_visible(self._formlayout, w, fit)

    def _on_creer_test(self):
        """Crée la géométrie du test dans le document (carré, ou tenons) --
        le panneau RESTE ouvert (mesure du kerf ② après la découpe)."""
        if self.combo_test.currentIndex() == 1:
            objs, err = core.create_fit_test_pattern(
                self.spn_tenon_w.value(), self.spn_tenon_h.value(),
                self.spn_nslots.value(), self.spn_clr_start.value(),
                self.spn_clr_step.value())
            if err:
                QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
                return
            noms = ", ".join(o.Name for o in objs)
            FreeCAD.Console.PrintMessage(
                "Succès : {} créé(s). Graver « ...gravure » (jeux + cote du "
                "tenon, faible puissance) et découper « ...decoupe » avec ta "
                "Compensation de kerf.\n".format(noms))
            return
        obj, err = core.create_kerf_test_pattern(self.spn_size.value())
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return
        FreeCAD.Console.PrintMessage("Succès : objet '{}' créé.\n".format(obj.Name))

    def accept(self):
        # OK = fermer. La création du test passe par le bouton de ①.
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
        _calibration_banner(form, "Bande de calibration défocus")
        _intro(form,
               "Grave une rangée de traits à hauteur de bec croissante "
               "(étiquetée) : le trait le <b>plus fin</b> donne le foyer, "
               "les traits larges la divergence du faisceau.")
        _diagram(form, "diag_defocus.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>Portée&nbsp;:</b> calibre uniquement la <b>divergence du "
            "point</b> (2 mesures, valables pour tout le laser actif) -- "
            "pas les largeurs brûlées ni les tons, qui se saisissent dans "
            "la Grille de test/Rampe et le Nuancier.",
            "<b>1.</b> Pose le <b>zéro Z</b> sur la surface d'une chute. Aucune "
            "sélection requise.",
            "<b>2. Balayage en hauteur (Z)</b>&nbsp;: plage de hauteurs de bec "
            "(du foyer vers le haut) et pas&nbsp;; chaque trait est étiqueté de "
            "sa hauteur.",
            "<b>3. Traits</b>&nbsp;: règle puissance/vitesse -- une "
            "<b>rampe de puissance</b> (puissance croissante) garde les "
            "traits très défocalisés visibles. Option <b>plusieurs "
            "bandes</b> pour graver une bande par vitesse en un seul job, "
            "chaque bande étiquetée de sa vitesse.",
            "<b>4. Génère et grave</b>, puis mesure au pied à coulisse&nbsp;: "
            "(1)&nbsp;le trait le plus fin → ton <b>Z de foyer</b> et sa largeur "
            "= «&nbsp;point au foyer&nbsp;»&nbsp;; (2)&nbsp;un trait bien plus "
            "large → sa hauteur moins le foyer = <b>défocus de test</b>, sa "
            "largeur = «&nbsp;point au défocus&nbsp;».",
            "<b>5.</b> <b>« Enregistrer la calibration du point »</b> "
            "ci-dessous (②) range ces trois mesures pour le laser actif&nbsp;: "
            "elles servent à tous les modes (remplissage noir, styles "
            "vague/défocus…) -- inutile de repasser par les Préférences.",
        ])

        self._presets = _PresetController(form, inner, "defocus_calib", lambda: self._last_fields)

        _section(form, "① Graver — balayage en hauteur (Z)", "sect_zheight.svg")
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

        self.btn_generer = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_generer, "sect_gcode.svg")
        self.btn_generer.setToolTip(
            "Génère le G-code de la bande avec les réglages ci-dessous et\n"
            "propose l'enregistrement. Le panneau reste ouvert pour saisir\n"
            "les mesures (②) après la gravure. OK, lui, ferme le panneau.")
        self.btn_generer.clicked.connect(self._on_generer)
        form.addRow(self.btn_generer)

        # PROCÉDURE D'ABORD : ② mesures et ③ photo suivent directement ①
        # (le novice suit les étapes) ; les réglages manuels viennent après.
        self._build_spot_measures(form)
        self._photo = _make_photo_section(form, lambda: "defocus",
                                          titre="③ Photo du résultat")

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
            lbl = _form_du_widget(self.spn_feed, form).labelForField(self.spn_feed)
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

        _section(form, "Aperçus & génération", "sect_gcode.svg")
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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])

        self._last_fields = {
            "zstart": self.spn_zstart, "zstep": self.spn_zstep,
            "nmarks": self.spn_nmarks, "length": self.spn_length,
            "rowgap": self.spn_rowgap, "power": self.spn_power,
            "power_end": self.spn_power_end, "feed": self.spn_feed,
            "nbands": self.spn_nbands, "feed_end": self.spn_feed_end,
            "band_gap": self.spn_band_gap,
            "labels": self.chk_labels, "power_labels": self.chk_power_labels,
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
        self._photo["reload"]()

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
            "label_z": self.spn_label_z.value(),
        }

    def _build_spot_measures(self, form):
        """Section ② : la calibration du point, saisie INLINE (au lieu d'aller
        dans les Préférences). Ø net au foyer + Ø mesuré à une hauteur de test
        connue -> le modèle d'élargissement du point en découle (utilisé
        partout : remplissages, nuancier, planche)."""
        _section(form, "② Entrer les mesures (calibration du point)", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "Mesure la LARGEUR du trait le plus net (au foyer) et celle d'un "
            "trait gravé bec relevé d'une hauteur connue. « Enregistrer » range "
            "ces valeurs dans le laser actif (appliqué tout de suite)."))
        self.spn_spot_focus = QtWidgets.QDoubleSpinBox()
        self.spn_spot_focus.setRange(0.01, 5.0)
        self.spn_spot_focus.setDecimals(2)
        self.spn_spot_focus.setSingleStep(0.01)
        self.spn_spot_focus.setSuffix(" mm")
        self.spn_spot_focus.setValue(core.SPOT_FOCUS_MM)
        self.spn_spot_focus.setToolTip("Ø (largeur) du trait le plus net, au foyer.")
        form.addRow("Ø du point au foyer :", self.spn_spot_focus)

        self.spn_spot_ztest = QtWidgets.QDoubleSpinBox()
        self.spn_spot_ztest.setRange(0.1, 200.0)
        self.spn_spot_ztest.setDecimals(1)
        self.spn_spot_ztest.setSuffix(" mm")
        self.spn_spot_ztest.setValue(core.SPOT_TEST_DEFOCUS_MM)
        self.spn_spot_ztest.setToolTip(
            "Hauteur dont le bec a été relevé au-dessus du foyer pour le trait "
            "de test défocalisé.")
        form.addRow("Hauteur de test :", self.spn_spot_ztest)

        self.spn_spot_dtest = QtWidgets.QDoubleSpinBox()
        self.spn_spot_dtest.setRange(0.01, 20.0)
        self.spn_spot_dtest.setDecimals(2)
        self.spn_spot_dtest.setSingleStep(0.01)
        self.spn_spot_dtest.setSuffix(" mm")
        self.spn_spot_dtest.setValue(core.SPOT_TEST_DIAMETER_MM)
        self.spn_spot_dtest.setToolTip("Ø (largeur) du trait mesuré à cette hauteur de test.")
        form.addRow("Ø mesuré à cette hauteur :", self.spn_spot_dtest)

        self.chk_verrou_spot = _verrou(
            form, [self.spn_spot_focus, self.spn_spot_ztest, self.spn_spot_dtest])

        self.btn_save_spot = QtWidgets.QPushButton("Enregistrer la calibration du point")
        self.btn_save_spot.setToolTip(
            "Range ces trois valeurs dans les réglages du laser actif "
            "(appliqué tout de suite, sans redémarrer).")
        self.btn_save_spot.clicked.connect(self._on_save_spot)
        form.addRow(self.btn_save_spot)

    def _on_save_spot(self):
        if self.spn_spot_dtest.value() <= self.spn_spot_focus.value():
            QtWidgets.QMessageBox.warning(
                self.form, "Calibration du point",
                "Le Ø mesuré au défocus doit être plus grand que le Ø au foyer "
                "(le point s'élargit en s'éloignant du foyer).")
            return
        core.save_settings({
            "spot_focus_mm": self.spn_spot_focus.value(),
            "spot_test_defocus_mm": self.spn_spot_ztest.value(),
            "spot_test_diameter_mm": self.spn_spot_dtest.value(),
        })
        QtWidgets.QMessageBox.information(
            self.form, "Calibration du point",
            "Calibration du point enregistrée pour le laser actif.")

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

    def _on_generer(self):
        """Génère le G-code du test et propose l'enregistrement -- le panneau
        RESTE ouvert (les mesures ② se saisissent après la gravure)."""
        _save_last_values("defocus_calib", self._last_fields)
        gcode = core.generate_gcode_defocus_calibration(
            **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/calibration_defocus.ngc")

    def accept(self):
        # OK = mémoriser les réglages et fermer. La génération passe par le
        # bouton « Générer... » de la section ① (même convention que les
        # panneaux de forme).
        _save_last_values("defocus_calib", self._last_fields)
        return True

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
        _calibration_banner(form, "Test rampe puissance / vitesse (lignes)")
        _intro(form,
               "Grave de longues lignes, UNE PAR VITESSE, avec la puissance "
               "qui MONTE le long de chaque ligne : on repère d'un coup où le "
               "trait apparaît et où il sature, à chaque vitesse. Complément "
               "continu de la Grille de test (cellules discrètes).")
        _diagram(form, "diag_ramp.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Pose le <b>zéro Z</b> sur la surface d'une chute. Aucune "
            "sélection requise.",
            "<b>2. Lignes (vitesses)</b>&nbsp;: longueur des lignes et liste des "
            "vitesses&nbsp;— une ligne par vitesse.",
            "<b>3. Rampe de puissance</b>&nbsp;: puissance min→max qui monte le "
            "long de chaque ligne, et nombre de paliers (si le trait se "
            "pointille à haute vitesse en S/PWM, baisse le nombre de paliers "
            "— chaque changement de puissance fait micro-branler la machine).",
            "<b>4. Rampe de hauteur (Z)</b> (option)&nbsp;: le bec monte aussi "
            "le long de la ligne (défocus progressif).",
            "<b>5. Génère et grave.</b> La règle graduée sous la 1re ligne "
            "donne la puissance sous chaque point&nbsp;: repère où le trait "
            "<b>apparaît</b> et où il <b>sature</b>, à chaque vitesse, puis "
            "ajoute les bons réglages directement en <b>② Reporter les tons "
            "retenus</b> ci-dessous.",
        ])

        self._presets = _PresetController(form, inner, "powerramp", lambda: self._last_fields)

        _section(form, "① Graver — lignes (vitesses)", "sect_power.svg")
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

        self.btn_generer = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_generer, "sect_gcode.svg")
        self.btn_generer.setToolTip(
            "Génère le G-code de la rampe avec les réglages ci-dessous et\n"
            "propose l'enregistrement. Le panneau reste ouvert pour reporter\n"
            "les tons (②) après la gravure. OK, lui, ferme le panneau.")
        self.btn_generer.clicked.connect(self._on_generer)
        form.addRow(self.btn_generer)

        # Procédure d'abord : ② et ③ suivent ① ; réglages manuels après.
        self._build_ramp_next(form)
        self._photo = _make_photo_section(form, lambda: "powerramp",
                                          titre="③ Photo du résultat")

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



        _section(form, "Aperçus & génération", "sect_gcode.svg")
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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])

        self._last_fields = {
            "length": self.spn_length, "nlines": self.spn_nlines, "gap": self.spn_gap,
            "feed_min": self.spn_feed_min, "feed_max": self.spn_feed_max,
            "power_min": self.spn_power_min, "power_max": self.spn_power_max,
            "steps": self.spn_steps, "zramp": self.chk_zramp, "z_end": self.spn_z_end,
            "labels": self.chk_labels,
            }
        _restore_last_values("powerramp", self._last_fields)
        self._presets.on_loaded = self._update_duration_preview

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Test rampe puissance / vitesse (lignes)")
        self.form.setWindowIcon(_icon("powerramp.svg"))

        self._update_duration_preview()
        self._photo["reload"]()
        self._ton_rapide["reload"]()
        self._largeurs["reload"]()

    def _build_ramp_next(self, form):
        """Section ② : la rampe ne donne pas une mesure chiffrée mais un
        éventail de tons -- on les ajoute ici même, sans quitter le panneau
        (même registre que le Nuancier, cf. _make_shade_quick_add)."""
        _section(form, "② Reporter les tons retenus", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "La rampe sert à CHOISIR : repère les lignes dont le rendu te "
            "plaît, puis ajoute leur ton ci-dessous (noirceur 0-100 %, "
            "réglage S/F/défocus, largeur). Active « Rampe Z » en ① pour "
            "mesurer un ton EN DÉFOCUS avec largeur -- c'est ce qu'exige "
            "« Ton sur mesure » (Marquage) pour interpoler. Le Nuancier "
            "reste le registre complet pour tout revoir ou corriger."))

        self.combo_mat = QtWidgets.QComboBox()
        self.combo_mat.setEditable(True)
        self.combo_mat.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mat.setMinimumContentsLength(14)
        mats = core.shade_materials() or core.burn_width_materials()
        self.combo_mat.addItems(mats)
        self.combo_mat.setCurrentText(mats[0] if mats else "MDF")
        self.combo_mat.setToolTip(
            "Matériau caractérisé : les tons retenus y sont rangés. "
            "Choisis-en un ou tape un nouveau nom.")
        form.addRow("Matériau :", self.combo_mat)
        self.combo_mat.currentIndexChanged.connect(lambda _i: self._ton_rapide["reload"]())
        self.combo_mat.lineEdit().editingFinished.connect(lambda: self._ton_rapide["reload"]())

        self._ton_rapide = _make_shade_quick_add(
            form, lambda: self.combo_mat.currentText(),
            on_added=self._maj_liste_materiaux)

        # Le ton et la LARGEUR sont deux mesures distinctes de la même
        # planche : l'un dit quel gris rend le bois, l'autre quelle épaisseur
        # le laser brûle. La rampe donne les deux, et jusqu'ici seule la
        # première avait où aller.
        self._largeurs = _make_largeurs_libres(
            form, lambda: self.combo_mat.currentText(),
            on_saved=self._maj_liste_materiaux)

    def _maj_liste_materiaux(self):
        """Après un ajout : rafraîchit la liste des matériaux du sélecteur
        (un nouveau nom vient peut-être d'apparaître). Même pattern que
        TaskPanelTestGrid._maj_liste_materiaux."""
        cur = self.combo_mat.currentText()
        self.combo_mat.blockSignals(True)
        self.combo_mat.clear()
        self.combo_mat.addItems(core.shade_materials() or core.burn_width_materials())
        self.combo_mat.setCurrentText(cur)
        self.combo_mat.blockSignals(False)

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

    def _on_generer(self):
        """Génère le G-code de la rampe et propose l'enregistrement -- le
        panneau RESTE ouvert (report des tons ② après la gravure)."""
        if not self._valid_ranges(warn=True):
            return
        _save_last_values("powerramp", self._last_fields)
        gcode = core.generate_gcode_power_ramp_lines(
            **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/test_rampe_puissance.ngc")

    def accept(self):
        # OK = mémoriser les réglages et fermer (génération : bouton de ①).
        _save_last_values("powerramp", self._last_fields)
        return True

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
        _calibration_banner(form, "Test des offsets X/Y du laser")
        _intro(form,
               "Job MIXTE fraise + laser : fraise une croix sur X0 Y0, puis "
               "grave une croix laser au même X0 Y0 programmé. L'écart mesuré "
               "entre les deux croix = l'erreur d'offsets X/Y du T{} dans "
               "tool.tbl. Lunettes laser obligatoires.".format(int(core.LASER_TOOL)))
        _diagram(form, "diag_offset.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1. Sécurité</b>&nbsp;: <b>lunettes laser obligatoires</b>. Chute "
            "de bois sur le martyre, <b>prévoir large</b> (si un signe d'offset "
            "est faux, la croix laser peut partir loin) ; fraise à graver "
            "montée à la main, zéro X/Y à l'œil au centre de la chute. Aucune "
            "sélection.",
            "<b>2. Croix (géométrie)</b>&nbsp;: taille des bras de la croix.",
            "<b>3. Croix fraisée / Croix laser</b>&nbsp;: profondeur et vitesse "
            "de la fraise, puissance et vitesse du laser.",
            "<b>4. Génère et lance.</b> Monte la glissière laser pendant la "
            "pause du 2e changement d'outil.",
            "<b>5. Mesure l'écart</b> entre les deux croix&nbsp;: dX = X&nbsp;"
            "laser − X&nbsp;fraisé (signé, sens machine). Corrige "
            "<code>tool.tbl</code>&nbsp;: X_nouveau = X_actuel − dX (idem Y).",
        ])

        self._presets = _PresetController(form, inner, "offset_test", lambda: self._last_fields)

        _section(form, "① Graver — croix (géométrie)", "sect_options.svg")
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

        self.btn_generer = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_generer, "sect_gcode.svg")
        self.btn_generer.setToolTip(
            "Génère le G-code du test (croix fraisée + croix laser, réglages\n"
            "des sections ci-dessous) et propose l'enregistrement. Le panneau\n"
            "reste ouvert pour saisir l'écart (②). OK, lui, ferme le panneau.")
        self.btn_generer.clicked.connect(self._on_generer)
        form.addRow(self.btn_generer)

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

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Hors changements d'outil et palpages (durée machine réelle\n"
            "nettement plus longue).")

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Trace les deux croix dans la vue 3D (superposées par\n"
            "construction : c'est la machine qui révèle l'écart réel).")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])

        self._last_fields = {
            "half": self.spn_half, "surface_z": self.spn_surface_z,
            "mill_tool": self.spn_mill_tool, "rpm": self.spn_rpm,
            "mill_feed": self.spn_mill_feed, "depth": self.spn_depth,
            "zfocus": self.spn_zfocus, "power": self.spn_power,
            "laser_feed": self.spn_laser_feed,
        }
        _restore_last_values("offset_test", self._last_fields)
        self._presets.on_loaded = self._update_duration_preview

        self._build_offset_measures(form)
        self._photo = _make_photo_section(form, lambda: "offset",
                                          titre="③ Photo du résultat")

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Test des offsets X/Y du laser")
        self.form.setWindowIcon(_icon("offset_test.svg"))

        self._update_duration_preview()
        self._photo["reload"]()

    def _build_offset_measures(self, form):
        """Section ② : saisie de l'écart mesuré entre la croix laser et la
        croix fraisée -> correction d'offset X/Y à reporter dans la table
        d'outils du laser (tool.tbl ; l'atelier ne gère pas tool.tbl)."""
        _section(form, "② Entrer les mesures (écart des croix)", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "Mesure l'écart entre le centre de la croix LASER et celui de la "
            "croix FRAISÉE : dX = X_laser − X_fraisé, dY = Y_laser − Y_fraisé "
            "(signés). La correction à reporter dans tool.tbl est calculée "
            "ci-dessous."))
        self.spn_dx = QtWidgets.QDoubleSpinBox()
        self.spn_dx.setRange(-50.0, 50.0)
        self.spn_dx.setDecimals(2)
        self.spn_dx.setSingleStep(0.05)
        self.spn_dx.setSuffix(" mm")
        self.spn_dx.setToolTip("Écart en X entre croix laser et croix fraisée (signé).")
        form.addRow("Écart dX :", self.spn_dx)
        self.spn_dy = QtWidgets.QDoubleSpinBox()
        self.spn_dy.setRange(-50.0, 50.0)
        self.spn_dy.setDecimals(2)
        self.spn_dy.setSingleStep(0.05)
        self.spn_dy.setSuffix(" mm")
        self.spn_dy.setToolTip("Écart en Y entre croix laser et croix fraisée (signé).")
        form.addRow("Écart dY :", self.spn_dy)
        self.chk_verrou_offset = _verrou(form, [self.spn_dx, self.spn_dy])
        self.lbl_offset = _WrapLabel("Saisis l'écart mesuré (dX, dY).")
        form.addRow(self.lbl_offset)
        self.spn_dx.valueChanged.connect(self._update_offset)
        self.spn_dy.valueChanged.connect(self._update_offset)

    def _update_offset(self):
        dx, dy = self.spn_dx.value(), self.spn_dy.value()
        if dx == 0 and dy == 0:
            self.lbl_offset.setText("Saisis l'écart mesuré (dX, dY).")
            return
        tool = int(getattr(core, "LASER_TOOL", 100))
        self.lbl_offset.setText(
            "<b>Correction outil laser (T{}) : X {:+.2f}, Y {:+.2f} mm</b> — "
            "à ajouter à ses offsets dans tool.tbl.".format(tool, -dx, -dy))

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

    def _on_generer(self):
        """Génère le G-code du test (croix fraisée + croix laser) et propose
        l'enregistrement -- le panneau RESTE ouvert (saisie de l'écart ②)."""
        _save_last_values("offset_test", self._last_fields)
        gcode = core.generate_gcode_offset_test(
            **self._gen_kwargs())
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return
        # Position intentionnelle (calage fraise/laser) : pas de recadrage.
        _write_gcode_with_dialog(
            self.form, gcode, "/tmp/test_offsets_laser.ngc", recadrer_origine=False)

    def accept(self):
        # OK = mémoriser les réglages et fermer (génération : bouton de ①).
        _save_last_values("offset_test", self._last_fields)
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : GRAVURE PHOTO (TRAME DE POINTS)
# ==========================================================================
# Un tramage = une ligne de ce tableau. AVANT, chacune de ces propriétés
# était un test d'index EN DUR, dispersé sur un millier de lignes : vingt
# comparaisons du genre `if idx in (5, 6)`. Ajouter un tramage obligeait à
# les retrouver toutes, et les trois bugs livrés le 29/07/2026 viennent
# exactement de là -- une coche verte sans texte, un réglage de défocus
# affiché dans un tramage qui grave au foyer, et un tramage qui refusait
# parce que la vitesse par défaut du panneau ne lui convenait pas. Trois
# symptômes, une seule cause : la connaissance du tramage n'était écrite
# nulle part, seulement recalculée site par site.
#
# Chaque champ est une propriété INTRINSÈQUE du tramage, pas un réglage
# d'interface : ce qui doit être visible ou actif s'en déduit, jamais
# l'inverse. L'ordre du tuple EST l'ordre de la liste déroulante.
_TRAMAGES = (
    # balayage      : ligne parcourue en continu (sinon : un point par case,
    #                 donc des micro-traits dont la DURÉE fait le gris)
    # duree_variable: la durée du point porte le gris (dwell mini utile)
    # nuancier      : consulte la courbe noirceur->fluence des tons mesurés
    # au_foyer      : grave au foyer, donc « largeur du point » (qui pilote
    #                 le défocus) n'a aucun sens ici
    # grain         : le gris est la FORME d'une marque visible à l'oeil nu
    #                 -> demande de la place (cf. les 100 mm minimum)
    # seuil_blanc   : sait laisser du bois nu sous un seuil de noirceur
    # puissance     : S se règle à la main (sinon : calculée par pixel)
    # reglage       : réglage supplémentaire propre à ce tramage
    dict(cle="diffusion", nom="Diffusion (Floyd-Steinberg)",
         balayage=False, duree_variable=False, nuancier=False, au_foyer=False,
         grain=False, seuil_blanc=False, puissance=True, reglage=None),
    dict(cle="duree", nom="Durée variable",
         balayage=False, duree_variable=True, nuancier=False, au_foyer=False,
         grain=False, seuil_blanc=True, puissance=True, reglage=None),
    dict(cle="lignes", nom="Lignes calibrées (nuancier)",
         balayage=True, duree_variable=False, nuancier=True, au_foyer=False,
         grain=False, seuil_blanc=True, puissance=False, reglage=None),
    dict(cle="dither", nom="Diffusion en lignes (points fins, rapide)",
         balayage=True, duree_variable=False, nuancier=False, au_foyer=False,
         grain=False, seuil_blanc=False, puissance=True, reglage=None),
    dict(cle="zdots", nom="Gros points Z (taille variable, artistique)",
         balayage=False, duree_variable=True, nuancier=False, au_foyer=False,
         grain=True, seuil_blanc=True, puissance=True, reglage=None),
    dict(cle="simili", nom="Similigravure (trame 45°, sans calibration)",
         balayage=True, duree_variable=False, nuancier=False, au_foyer=True,
         grain=True, seuil_blanc=False, puissance=True,
         reglage="espacement"),
    # seuil_blanc a longtemps valu False ici : le mode était né du principe
    # « jamais de bois nu ». Mais son palier le plus bas n'est pas « rien »
    # -- c'est la puissance la plus basse MESURÉE, donc un trait de 0,10 mm,
    # soit 33 % de couverture au pas 0,30. Un fond blanc sortait gris uni
    # (planche du 31/07/2026). Le « jamais de bois nu » visait les TROUS
    # dans les demi-teintes, pas le fond blanc, qui doit rester nu.
    dict(cle="enfle", nom="Lignes gravées (trait qui enfle)",
         balayage=True, duree_variable=False, nuancier=False, au_foyer=True,
         grain=True, seuil_blanc=True, puissance=False,
         reglage="trait_mini"),
)

# Le MATÉRIAU est demandé dès qu'une donnée mesurée entre en jeu : la courbe
# du nuancier pour les lignes calibrées, la table des largeurs brûlées pour
# les deux tramages au foyer (et la teinte de l'aperçu dans tous les cas).
def _tramage_veut_materiau(t):
    return bool(t["nuancier"] or t["au_foyer"])


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

        _diagram(form, "diag_photo.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1. Image</b>&nbsp;: «&nbsp;Parcourir…&nbsp;» pour charger un "
            "PNG/JPG (ou «&nbsp;Photo de démonstration&nbsp;»). Aucune sélection "
            "dans la vue 3D n'est requise.",
            "<b>2. Cadre &amp; taille</b>&nbsp;: règle la <b>largeur</b> de "
            "l'image et le <b>pas de trame</b> (il pilote la finesse ET la "
            "durée). Tourne l'angle si l'image doit être pivotée&nbsp;; le gamma "
            "éclaircit/assombrit l'ensemble.",
            "<b>3. Tramage &amp; puissance</b>&nbsp;: choisis le tramage "
            "(Floyd-Steinberg recommandé, lignes calibrées, points Z…) et la "
            "puissance. «&nbsp;Mire des tramages&nbsp;» les compare sur une "
            "chute.",
            "<b>4.</b> Pose le <b>zéro machine</b>&nbsp;: X/Y au coin "
            "<b>bas-gauche</b> (l'image y est posée en X0&nbsp;Y0), Z sur la "
            "surface.",
            "<b>5. Vérifie</b>&nbsp;: «&nbsp;Aperçu photo&nbsp;» (le rendu "
            "sur le bois, en grand&nbsp;— c'est lui qui te dira si les demi-"
            "teintes tiennent), «&nbsp;Aperçu des points&nbsp;» (vue 3D) et "
            "«&nbsp;Aperçu cadrage&nbsp;» (fichier séparé, à blanc).",
            "<b>6. Génère</b>&nbsp;: «&nbsp;Générer et sauvegarder le "
            "G-code…&nbsp;». Compter ~2-4 points/seconde&nbsp;— un pas de trame "
            "trop fin donne un job très long.",
        ])

        self._presets = _PresetController(
            form, inner, "photo", lambda: self._last_fields,
            on_loaded=lambda: self._update_grid_info())

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

        btn_demo = QtWidgets.QPushButton("Photo de démonstration (libre de droits)")
        btn_demo.setToolTip(
            "Charge la photo de test fournie avec l'atelier : Guy de\n"
            "Maupassant photographié par Nadar (1888, domaine public) --\n"
            "un portrait ancien riche en dégradés (visage, moustache,\n"
            "costume), idéal pour comparer les tramages et régler la\n"
            "tonalité avant d'utiliser tes photos.")
        btn_demo.clicked.connect(self._on_demo_photo)
        form.addRow(btn_demo)

        self.spn_width = QtWidgets.QDoubleSpinBox()
        self.spn_width.setRange(5.0, 500.0)
        self.spn_width.setValue(60.0)
        self.spn_width.setSuffix(" mm")
        self.spn_width.setToolTip(
            "Largeur gravée. La hauteur suit les proportions de l'image.")
        form.addRow("Largeur cible :", self.spn_width)

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

        self.spn_gamma = QtWidgets.QDoubleSpinBox()
        self.spn_gamma.setRange(0.3, 3.0)
        self.spn_gamma.setDecimals(2)
        self.spn_gamma.setSingleStep(0.1)
        self.spn_gamma.setValue(1.0)
        self.spn_gamma.setToolTip(
            "Correction de tonalité (gamma sur la noirceur) : > 1 ÉCLAIRCIT\n"
            "les tons moyens (une photo colorée/saturée sort souvent trop\n"
            "foncée en gris -- essaye 1.5 à 2.0), < 1 assombrit. Les zones\n"
            "éclaircies passent sous le Seuil blanc et ne sont plus gravées.\n"
            "L'aperçu suit en direct.")
        form.addRow("Tonalité (gamma) :", self.spn_gamma)

        self.lbl_grid = _WrapLabel("Grille : --")
        form.addRow(self.lbl_grid)

        # Aperçu du rendu tramé (l'image telle qu'elle sera piquetée) --
        # LE retour visuel qui compte pour une photo, mis à jour avec les
        # réglages. Pixellisé volontairement : chaque pixel = un point.
        self.lbl_halftone_preview = QtWidgets.QLabel()
        self.lbl_halftone_preview.setAlignment(QtCore.Qt.AlignHCenter)
        self.lbl_halftone_preview.setToolTip(
            "Aperçu du RÉSULTAT sur le bois, avec le tramage courant :\n"
            "points pour les tramages à points, gris calibrés pour les\n"
            "lignes calibrées. Se met à jour avec l'image, la largeur, le\n"
            "pas, le tramage, la tonalité, le négatif et le seuil blanc.\n"
            "Le bouton « Aperçu photo », plus bas, montre le même rendu\n"
            "en grand.")
        form.addRow(self.lbl_halftone_preview)

        self.btn_sampler = QtWidgets.QPushButton("Mire des tramages (comparatif sur chute)")
        self.btn_sampler.setToolTip(
            "Génère un fichier de TEST : le même dégradé de gris (10 patchs,\n"
            "10 à 100 %) gravé par LES SEPT tramages, en bandes étiquetées\n"
            "1=Diffusion points, 2=Durée variable, 3=Lignes calibrées,\n"
            "4=Diffusion en lignes, 5=Gros points Z, 6=Similigravure 45°,\n"
            "7=Lignes gravées -- avec les réglages courants du panneau.\n"
            "Chaque bande est gravée DANS SON RÉGIME : les bandes 6 et 7 au\n"
            "foyer (leur grain doit être net), et la 7 à la vitesse où son\n"
            "trait enfle encore, sinon elle ne montrerait qu'un aplat.\n"
            "À graver sur une chute pour comparer les styles et choisir.")
        self.btn_sampler.clicked.connect(self._on_sampler)
        form.addRow(self.btn_sampler)

        _section(form, "Tramage & puissance", "sect_power.svg")
        self.combo_mode = QtWidgets.QComboBox()
        # Liste construite depuis _TRAMAGES : l'ordre affiché et la table qui
        # décrit ces tramages ne peuvent plus diverger, c'est la même source.
        # La donnée portée par chaque entrée est sa CLÉ, jamais son rang.
        for _t in _TRAMAGES:
            self.combo_mode.addItem(_t["nom"], _t["cle"])
        self.combo_mode.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mode.setMinimumContentsLength(17)
        self.combo_mode.setToolTip(
            "Diffusion : points TOUS identiques (durée max), leur densité\n"
            "locale rend le gris -- robuste, pas de demi-teinte à calibrer.\n"
            "Durée variable : un point par case non blanche, durée du pulse\n"
            "proportionnelle à la noirceur -- rendu plus doux, mais dépend\n"
            "de la réponse du matériau (à valider sur une chute).\n"
            "Lignes calibrées : chaque ligne balayée EN CONTINU, puissance\n"
            "modulée pixel par pixel via la courbe noirceur->fluence du\n"
            "NUANCIER (tons mesurés) -- gris calibrés, et bien plus rapide\n"
            "que les points (pas d'arrêt par pixel).\n"
            "Diffusion en lignes : le MÊME rendu points que Diffusion, mais\n"
            "balayé en continu, faisceau allumé/éteint par pixel à puissance\n"
            "fixe -- l'esthétique des points, à la vitesse d'un balayage\n"
            "(point fin au foyer : largeur du point à 0).\n"
            "Similigravure : trame régulière à 45° façon journal, où c'est le\n"
            "DIAMÈTRE du point qui rend le gris. Chaque point est brûlé à\n"
            "fond, toujours pareil : aucun nuancier n'est consulté, le gris\n"
            "est une surface. C'est le tramage à choisir quand les gris\n"
            "calibrés sortent irréguliers -- le seuil de brûlure du bois ne\n"
            "décide plus à la place de l'image. À graver AU FOYER.\n"
            "Lignes gravées : lignes continues, faisceau jamais coupé, dont\n"
            "l'ÉPAISSEUR rend le gris -- fin dans les clairs, épais dans les\n"
            "foncés, comme une gravure sur cuivre. Le gris est là aussi une\n"
            "géométrie, mais lue sur les LARGEURS BRÛLÉES mesurées et non\n"
            "sur le nuancier. Plus jamais de bois nu. AU FOYER, et sous\n"
            "F1500 : au-delà le trait n'enfle plus.")
        form.addRow("Tramage :", self.combo_mode)

        self.spn_line_min = QtWidgets.QDoubleSpinBox()
        self.spn_line_min.setRange(0.02, 3.0)
        self.spn_line_min.setDecimals(2)
        self.spn_line_min.setSingleStep(0.05)
        self.spn_line_min.setValue(0.10)
        self.spn_line_min.setSuffix(" mm")
        self.spn_line_min.setToolTip(
            "Lignes gravées : épaisseur du trait dans les BLANCS -- la ligne\n"
            "n'est jamais coupée, c'est son minimum. Le maximum, lui, est\n"
            "celui que le matériau donne à pleine puissance (mesuré).\n"
            "Plus ce minimum est bas, plus le contraste est grand : le\n"
            "contraste vaut 1 - mini/maxi. La plage réellement disponible\n"
            "s'affiche sous la grille.")
        form.addRow("Épaisseur mini du trait :", self.spn_line_min)

        # Le pendant HAUT de « épaisseur mini ». La table des largeurs ne
        # connaît que la largeur, jamais la PROFONDEUR : à pleine puissance
        # le trait fait bien la largeur annoncée, mais il peut creuser et
        # laisser la surface striée. Aucune mesure de l'atelier ne prédit
        # ça -- d'où un plafond réglé à la main, à l'oeil, sur une chute.
        self.spn_power_max = QtWidgets.QDoubleSpinBox()
        self.spn_power_max.setRange(0.0, core.S_MAX)
        self.spn_power_max.setDecimals(0)
        self.spn_power_max.setSingleStep(25.0)
        self.spn_power_max.setValue(core.S_MAX)
        self.spn_power_max.setToolTip(
            "Lignes gravées : puissance du trait le plus NOIR.\n"
            "\n"
            "À pleine puissance le trait atteint sa largeur maximale, mais\n"
            "sur certains bois il CREUSE : la surface ressort striée au\n"
            "lieu d'être marquée. La table des largeurs ne peut pas le\n"
            "prévoir, elle ne mesure que la largeur -- jamais la profondeur.\n"
            "\n"
            "Sur le papier, baisser ce plafond rogne le haut de la plage :\n"
            "sur hêtre F800 au pas 0,30, S900 donne 0,28 mm au lieu de 0,30,\n"
            "soit 58 points de contraste au lieu de 67. Le verdict affiche\n"
            "cette plage-là, qui est bien celle que le G-code produit.\n"
            "\n"
            "MAIS le bois dit autre chose, et il a le dernier mot. Mesuré le\n"
            "31/07/2026 sur hêtre à F800, au foyer, pas 0,30, par deux voies\n"
            "indépendantes :\n"
            "  - deux portraits identiques gravés à 100 % et à 90 % : même\n"
            "    noirceur d'ensemble, mais des NOIRS PROFONDS plus denses à\n"
            "    90 % (surface sous 30 % de luminance : 20,4 -> 22,6 %) ;\n"
            "  - une planche de 10 aplats S600-S1000 classée à l'oeil :\n"
            "    S925 jugé le plus foncé, DEVANT S950, S975 et S1000.\n"
            "\n"
            "Autrement dit la noirceur SATURE vers S900-950, et au-delà on\n"
            "creuse sans noircir. Les points de contraste perdus sont donc\n"
            "en grande partie théoriques. 92 % est le réglage retenu ici.\n"
            "\n"
            "Ce constat vaut pour CE bois à CETTE vitesse : sur un autre\n"
            "matériau, regrave la planche d'aplats avant de conclure.\n"
            "\n"
            "À S max : aucun plafond (comportement d'origine).")
        form.addRow("Puissance maxi du trait :", self.spn_power_max)

        # Ce qu'on fait de ce qui passe SOUS le seuil de blanc. Deux
        # réponses honnêtes, pas une bonne et une mauvaise : « Bois nu »
        # est franc mais crée une marche (rien, puis d'un coup 33 % de
        # couverture) ; « Pointillé » comble justement cette marche, seul
        # moyen de descendre sous le plancher du mode puisque la largeur,
        # elle, s'arrête à la puissance la plus basse mesurée.
        self.combo_fond = QtWidgets.QComboBox()
        self.combo_fond.addItem("Bois nu (net)", "nu")
        self.combo_fond.addItem("Pointillé dégressif (dégradé doux)", "pointille")
        self.combo_fond.setToolTip(
            "Lignes gravées : ce que devient une case SOUS le seuil blanc.\n"
            "\n"
            "Bois nu : rien n'est gravé. Net, mais c'est une MARCHE --\n"
            "  au-dessus du seuil le trait apparaît d'un coup à ~33 % de\n"
            "  couverture. Idéal sur un fond blanc franc.\n"
            "\n"
            "Pointillé dégressif : le trait le plus fin, mais intermittent,\n"
            "  de plus en plus clairsemé vers le blanc pur. La couverture\n"
            "  descend continûment de 33 % à 0 au lieu de sauter : pas de\n"
            "  contour visible sur un dégradé doux. C'est le SEUL moyen\n"
            "  d'aller sous le plancher du mode -- la largeur, elle, ne\n"
            "  descend pas plus bas que la puissance la plus faible mesurée.\n"
            "\n"
            "Sans effet si le seuil blanc vaut 0.")
        form.addRow("Sous le seuil :", self.combo_fond)

        self.spn_dot_spacing = QtWidgets.QDoubleSpinBox()
        self.spn_dot_spacing.setRange(0.3, 5.0)
        self.spn_dot_spacing.setDecimals(2)
        self.spn_dot_spacing.setSingleStep(0.1)
        self.spn_dot_spacing.setValue(1.27)
        self.spn_dot_spacing.setSuffix(" mm")
        self.spn_dot_spacing.setToolTip(
            "Similigravure : distance entre deux points de la trame.\n"
            "Plus c'est serré, plus l'image est fine mais moins il y a de\n"
            "niveaux de gris -- la maille compte 2k² pixels, avec\n"
            "k = espacement / (pas × √2), arrondi. L'espacement et le nombre\n"
            "de niveaux RÉELLEMENT obtenus s'affichent sous la grille.\n"
            "1,27 mm au pas 0,15 donne 72 niveaux, trame bien visible.")
        form.addRow("Espacement des points :", self.spn_dot_spacing)

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
            "Seuil blanc : aucune case dont la noirceur est sous ce seuil\n"
            "n'est gravée -- évite de piqueter/hâler les blancs.\n"
            "\n"
            "Sur « Lignes gravées », c'est le réglage qui rend le fond\n"
            "VRAIMENT blanc : sans lui, la case la plus claire grave quand\n"
            "même le trait le plus fin (la puissance la plus basse mesurée),\n"
            "soit ~33 % de couverture au pas 0,30 sur hêtre. Le mouvement\n"
            "reste continu, seul le faisceau s'éteint.\n"
            "\n"
            "À 0 : faisceau jamais coupé (comportement d'origine).")
        form.addRow("Seuil blanc :", self.spn_white)

        # --- Vitesse de balayage des lignes calibrées ---

        def _sync_mode():
            # TOUT vient de _TRAMAGES : aucun rang de liste n'apparaît ici.
            t = self._tramage()
            # Un point par case -> sa DURÉE fait le gris. En balayage continu,
            # il n'y a pas de point, donc pas de durée à régler.
            self.spn_dwell_max.setEnabled(not t["balayage"])
            self.spn_dwell_min.setEnabled(t["duree_variable"])
            self.spn_power.setEnabled(t["puissance"])
            self.spn_white.setEnabled(t["seuil_blanc"])
            _set_row_visible(form, self.combo_photo_mat,
                             _tramage_veut_materiau(t))
            _set_row_visible(form, self.spn_dot_spacing,
                             t["reglage"] == "espacement")
            _set_row_visible(form, self.spn_line_min,
                             t["reglage"] == "trait_mini")
            # Le choix du fond n'a de sens que pour les lignes gravées (les
            # autres tramages à seuil coupent, point), et seulement si un
            # seuil est effectivement demandé.
            _set_row_visible(form, self.spn_power_max,
                             t["reglage"] == "trait_mini")
            _set_row_visible(form, self.combo_fond,
                             t["reglage"] == "trait_mini")
            self.combo_fond.setEnabled(self.spn_white.value() > 0.0)
            # « Largeur du point » pilote le DÉFOCUS : elle n'a aucun sens
            # pour un tramage qui grave au foyer, où la largeur du trait vient
            # de la puissance (lignes gravées) ou n'est qu'un grain de trame
            # (similigravure). L'afficher laissait le verdict de recouvrement
            # raisonner sur un point de 0,80 mm pendant que la machine en
            # traçait un de 0,10 à 0,30.
            _set_row_visible(form, self.spn_spot_width, not t["au_foyer"])
            _set_row_visible(form, self.spn_line_feed, t["balayage"])
        self.combo_mode.currentIndexChanged.connect(lambda _i: _sync_mode())
        # Le sélecteur de fond se grise quand le seuil retombe à 0 : sans
        # seuil, rien ne passe dessous, il n'y a rien à choisir.
        self.spn_white.valueChanged.connect(lambda _v: _sync_mode())
        # appel initial déplacé plus bas : _sync_mode touche combo_photo_mat,
        # désormais créé dans la section « Trait & matière » qui suit.

        # Les trois réglages ci-dessous sont COUPLÉS et étaient dispersés
        # dans trois sections : largeur/pas donnent le recouvrement, et
        # largeur/matériau disent si l'on grave dans le régime où les tons
        # ont été mesurés. Séparés, l'écart ne se voyait pas -- une photo
        # gravée à défocus 8,8 alors que le nuancier était mesuré à 15
        # sortait uniformément noire sans le moindre avertissement.
        _section(form, "Trait & matière", "sect_zheight.svg")

        self.combo_photo_mat = QtWidgets.QComboBox()
        self.combo_photo_mat.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_photo_mat.setMinimumContentsLength(14)
        self.combo_photo_mat.setToolTip(
            "Matériau du nuancier : la courbe noirceur->fluence de ses tons\n"
            "MESURÉS (en défocus) pilote la puissance de chaque pixel.")
        for m in core.shade_materials():
            self.combo_photo_mat.addItem(m, m)
        if self.combo_photo_mat.count() == 0:
            self.combo_photo_mat.addItem("-- (nuancier vide) --", None)
        form.addRow("Matériau (nuancier) :", self.combo_photo_mat)

        self.spn_line_feed = QtWidgets.QDoubleSpinBox()
        self.spn_line_feed.setRange(1, 20000)
        self.spn_line_feed.setValue(1000)
        self.spn_line_feed.setSuffix(" mm/min")
        self.spn_line_feed.setToolTip(
            "Vitesse de balayage des lignes. Elle fait partie du RÉGIME :\n"
            "à énergie identique, plus c'est lent, plus c'est foncé -- une\n"
            "courbe n'est donc valable qu'à la vitesse où elle a été mesurée.\n"
            "La puissance de chaque pixel =\n"
            "fluence(noirceur) x largeur x vitesse : si trop de pixels\n"
            "saturent à S max (commentaire en tête du G-code), ralentir.")
        form.addRow("Vitesse des lignes :", self.spn_line_feed)

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

        self.lbl_regime = _WrapLabel("")
        form.addRow(self.lbl_regime)
        self.btn_corriger_regime = QtWidgets.QPushButton(
            "Corriger : aligner sur la calibration (point et vitesse)")
        self.btn_corriger_regime.clicked.connect(self._corriger_regime)
        form.addRow(self.btn_corriger_regime)
        for _w in (self.spn_spot_width, self.spn_pitch, self.spn_line_feed):
            _w.valueChanged.connect(lambda _v: self._maj_regime())
        self.combo_photo_mat.currentIndexChanged.connect(lambda _i: self._maj_regime())
        self.combo_mode.currentIndexChanged.connect(lambda _i: self._maj_regime())
        _sync_mode()
        self._maj_regime()      # verdict visible DÈS l'ouverture, pas seulement
        # après avoir touché un champ : c'est à l'ouverture qu'on hérite d'un
        # réglage de la session précédente, et donc là qu'un écart passe.

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Dominée par les pulses (G4) et les arrêts à chaque point.")

        self.btn_frame_preview = QtWidgets.QPushButton("Générer l'aperçu cadrage (fichier séparé)")
        self.btn_frame_preview.setToolTip(
            "Fichier à part traçant le rectangle englobant de l'image, à\n"
            "lancer seul pour vérifier le positionnement avant le vrai job.")
        self.btn_frame_preview.clicked.connect(self._on_frame_preview)
        form.addRow(self.btn_frame_preview)

        self.btn_photo_preview = QtWidgets.QPushButton()
        self.btn_photo_preview.setToolTip(
            "Aperçu photo : le rendu du résultat sur le bois, en grand,\n"
            "avec le tramage courant -- points, lignes ou gris calibrés\n"
            "selon le tramage choisi. Les gris des « lignes calibrées »\n"
            "passent par la MÊME conversion que le G-code, et l'aperçu\n"
            "annonce le bois resté nu et les ombres écrasées au maximum.\n"
            "À regarder avant de graver : une planche de moins à brûler.")
        self.btn_photo_preview.clicked.connect(self._on_photo_preview)

        self.btn_dots_preview = QtWidgets.QPushButton()
        self.btn_dots_preview.setToolTip(
            "Dessine chaque point de la trame (petite croix) dans la vue 3D,\n"
            "à sa position réelle -- pour vérifier l'emprise et la densité\n"
            "sur le modèle. Purement visuel.")
        self.btn_dots_preview.clicked.connect(self._on_dots_preview)
        _preview_row(form, [(self.btn_photo_preview, "sect_photo.svg"),
                            (self.btn_dots_preview, "btn_view3d.svg")])

        self._last_fields = {
            "image": self.edt_image, "width": self.spn_width,
            "pitch": self.spn_pitch, "invert": self.chk_invert,
            "rotation": self.combo_rotation,
            "mode": self.combo_mode, "power": self.spn_power,
            "dwell_min": self.spn_dwell_min, "dwell_max": self.spn_dwell_max,
            "white": self.spn_white, "spot_width": self.spn_spot_width,
            "line_feed": self.spn_line_feed, "gamma": self.spn_gamma,
            "dot_spacing": self.spn_dot_spacing,
            "line_min": self.spn_line_min,
            "power_max": self.spn_power_max,
            "fond_clair": self.combo_fond,
            # Le MATÉRIAU manquait, et c'est le réglage dont tout le régime
            # dépend : sans lui une recette « Hêtre » ne pouvait pas
            # sélectionner le Hêtre, et une session repartait sur le premier
            # matériau de la liste sans le dire. Stocké par son NOM (la donnée
            # de l'entrée), donc insensible à l'ordre du nuancier.
            "material": self.combo_photo_mat,
        }
        _restore_last_values("halftone", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Gravure photo (trame de points)")
        self.form.setWindowIcon(_icon("halftone.svg"))

        for _sig in (self.edt_image.textChanged, self.spn_width.valueChanged,
                     self.spn_pitch.valueChanged, self.spn_white.valueChanged,
                     self.spn_gamma.valueChanged,
                     self.spn_dot_spacing.valueChanged,
                     self.spn_line_min.valueChanged,
                     self.spn_power_max.valueChanged,
                     # la mise en garde « trait plus étroit que le pas » de
                     # la similigravure dépend aussi de ces trois-là
                     self.spn_power.valueChanged,
                     self.spn_line_feed.valueChanged):
            _sig.connect(lambda *_a: self._update_grid_info())
        self.combo_photo_mat.currentIndexChanged.connect(
            lambda _i: self._update_grid_info())
        self.combo_mode.currentIndexChanged.connect(lambda _i: self._update_grid_info())
        self.combo_rotation.currentIndexChanged.connect(lambda _i: self._update_grid_info())
        self.chk_invert.toggled.connect(lambda _v: self._update_grid_info())
        self._update_grid_info()

    def _on_demo_photo(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "resources", "demo", "photo_demo.jpg")
        if not os.path.isfile(path):
            QtWidgets.QMessageBox.warning(
                self.form, "Photo de démonstration",
                "Photo de démo introuvable ({}).".format(path))
            return
        self.edt_image.setText(path)

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
        gamma = self.spn_gamma.value()
        darkness = []
        for y in range(scaled.height()):
            drow = []
            for x in range(scaled.width()):
                g = QtGui.qGray(scaled.pixel(x, y)) / 255.0
                d = g if invert else 1.0 - g
                if gamma != 1.0:
                    d = d ** gamma       # >1 : tons moyens éclaircis
                drow.append(d)
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
        texte = ("Image {} x {} px ({}) -- grille {} x {} cases = {:.0f} x "
                 "{:.0f} mm ({} points max).".format(
                     img.width(), img.height(),
                     "portrait" if img.height() > img.width() else "paysage",
                     cols, rows, (cols - 1) * pitch, (rows - 1) * pitch,
                     cols * rows))
        t = self._tramage()
        if t["cle"] == "simili":
            # L'espacement demandé est arrondi à la maille : autant montrer
            # ce qu'on aura VRAIMENT, et combien de gris il en reste.
            k = core.am_screen_k(self.spn_dot_spacing.value(), pitch)
            reel = core.am_screen_spacing(k, pitch)
            texte += (" Trame : {:.2f} mm entre points ({:.0f} en travers), "
                      "{} niveaux de gris.".format(
                          reel, (cols - 1) * pitch / reel if reel else 0,
                          2 * k * k))
        if t["grain"]:
            # Ces tramages rendent le gris par la FORME d'une marque
            # visible à l'oeil nu (diamètre, point de trame, épaisseur du
            # trait). Il faut donc assez de marques en travers de l'image
            # pour que le motif s'effface derrière le sujet -- une affaire
            # de TAILLE gravée, que le pas seul ne dit pas. Constaté à
            # l'atelier le 30/07/2026 : un portrait en lignes gravées sur
            # 80 mm de large, le grain se voyait plus que le visage.
            large = (cols - 1) * pitch
            if large < 100.0:
                texte += (" Ce tramage a besoin de place : à {:.0f} mm de "
                          "large le grain se voit plus que le sujet, viser "
                          "<b>100 mm au minimum</b>.".format(large))
        # Tout ce qui concerne le TRAIT (largeurs mesurées, recouvrement,
        # trait qui n'enfle plus) est dit une seule fois, sous « Trait &
        # matière » -- cf. _verdict_au_foyer. Ici on s'en tient à la grille.
        self.lbl_grid.setText(texte)
        self._maj_regime()
        self._update_halftone_preview()

    _PREVIEW_MAX_CELLS = 250000  # plafond du tramage d'APERÇU (coût borné)

    _MARGE_APERCU_MM = 2.0

    def _render_photo_preview(self, darkness, largeur_px=240):
        """Rendu réaliste, sur fond bois, de ce que le tramage COURANT
        gravera -- chaque tramage peint comme il grave, jamais comme un
        autre. Renvoie (QImage, note) ou (None, raison).

        Les tons viennent du nuancier MESURÉ du matériau quand il existe,
        du modèle théorique sinon (cf. _teinte_gravure). Le tramage
        « lignes calibrées » passe, lui, par la fonction du générateur
        elle-même (core.photo_line_power_fn) : l'aperçu ne peut donc pas
        montrer autre chose que ce que le G-code demandera."""
        h = len(darkness)
        w = len(darkness[0]) if h else 0
        pitch = self.spn_pitch.value()
        if h < 1 or w < 1 or pitch <= 0:
            return None, "grille vide"
        t = self._tramage()
        material = self.combo_photo_mat.currentData()
        white = self.spn_white.value() / 100.0
        spot = self.spn_spot_width.value()
        power = self.spn_power.value()
        marge = self._MARGE_APERCU_MM
        sc = max(1.0, largeur_px / float(w * pitch + 2 * marge))

        if t["nuancier"]:
            return self._apercu_lignes_calibrees(darkness, pitch, sc, marge)

        # Tramages à marques : on peint chaque marque à sa position, sa
        # largeur brûlée et sa teinte, puis _render_engraving_photo compose
        # le tout sur le bois (les recouvrements s'assombrissent).
        cache = {}
        seg = max(0.05, min(0.3 * pitch, 0.2))
        demi = seg / 2.0
        half_angle = core.calibrated_half_angle()
        strokes = []

        # Les tramages à points brûlent en MICRO-TRAITS : leur vitesse vient
        # de la durée du pulse (F = seg/durée), pas du réglage de vitesse.
        # Elle tombe souvent bien en dessous des vitesses auxquelles le
        # nuancier a été mesuré -- et `darkness_at` borne alors aux mesures
        # SANS LE DIRE : le point le plus bref et le plus long ressortent
        # à la même noirceur, et l'aperçu affiche une photo plate qui a
        # pourtant l'air d'une mesure. Repéré le 29/07/2026 sur Hêtre
        # (micro-traits F200-1200, tons mesurés F650-2000, tout à 22 %).
        # Règle : si le régime sort du domaine mesuré, TOUT le rendu passe
        # au modèle théorique et l'aperçu l'annonce -- même règle pour tous
        # les tramages, qu'on le voie ou non à l'écran.
        if t["balayage"]:
            feeds = [self.spn_line_feed.value()]
        else:
            feeds = [max(1.0, seg / max(d / 1000.0, 1e-3) * 60.0)
                     for d in (self.spn_dwell_min.value(),
                               self.spn_dwell_max.value())]
        # Un tramage AU FOYER ne défocalise pas : dans un cas le point doit
        # rester net (similigravure), dans l'autre c'est la largeur brûlée au
        # foyer qui répond à la puissance (lignes gravées).
        z_ref = 0.0 if t["au_foyer"] else (core.defocus_for_spot_diameter(
            spot, core.SPOT_FOCUS_MM, half_angle) or 0.0)
        plage = core.shade_feed_range(material, z_ref)
        theorique = plage is None or not all(
            plage[0] - 1e-6 <= f <= plage[1] + 1e-6 for f in feeds)
        hors = "" if not theorique else (
            "gris théoriques : ce tramage brûle à F{:.0f}-{:.0f}, hors des "
            "vitesses mesurées{} — à valider sur une chute".format(
                min(feeds), max(feeds),
                "" if plage is None else " (F{:.0f}-{:.0f})".format(*plage)))
        def teinte(pw, feed, largeur, z_off):
            if theorique:
                return max(0.0, min(1.0, _tone_burn(pw, feed, largeur)))
            return _teinte_gravure(material, pw, feed, largeur, z_off, cache)

        dwell_min = self.spn_dwell_min.value() / 1000.0
        dwell_max = self.spn_dwell_max.value() / 1000.0
        largeur = spot if spot > 0 else core.SPOT_FOCUS_MM
        if t["cle"] == "zdots":
            dot_max = spot if spot > core.SPOT_FOCUS_MM else max(
                pitch * 0.9, core.SPOT_FOCUS_MM * 3)
            p_z = power or core.S_MAX
            for x, y, dia in core.zdots_marks(darkness, pitch,
                                              core.SPOT_FOCUS_MM, dot_max,
                                              white):
                # Même chaîne que generate_gcode_photo_zdots : le diamètre
                # fixe le défocus, et la durée suit la surface du point --
                # c'est la TAILLE qui porte l'image, pas le gris.
                z_off = core.defocus_for_spot_diameter(
                    dia, core.SPOT_FOCUS_MM, half_angle) or 0.0
                dw = dwell_min + (dwell_max - dwell_min) * (dia / dot_max) ** 2
                f_dot = max(1.0, seg / max(dw, 1e-3) * 60.0)
                strokes.append(([(x, y)], dia,
                                teinte(p_z, f_dot, dia, z_off)))
        elif t["cle"] == "enfle":
            # Lignes gravées : une case = un segment d'un PAS, dont la
            # LARGEUR porte le gris. On passe par la table du générateur,
            # et on fusionne les cases de même niveau exactement comme
            # _emit_raster_rows fusionne les S égaux -- l'aperçu dessine
            # donc les mêmes segments que la machine gravera.
            feed_l = self.spn_line_feed.value()
            niv = core.swell_power_levels(
                material, feed_l, self.spn_line_min.value(),
                power_max=self.spn_power_max.value())
            if niv is None:
                return None, core.swell_refus_message(
                    material, feed_l, self.spn_power_max.value())
            puissances, w_min, w_max = niv
            n = len(puissances)
            # Seuil de blanc ET fond pointillé viennent de la MÊME grille
            # que le générateur : sans ça l'aperçu montrerait un fond blanc
            # que la machine graverait quand même (ou l'inverse), et le
            # pointillé — qui dépend de la POSITION de la case — serait
            # forcément dessiné ailleurs.
            grille = core.swell_niveaux_grille(
                darkness, n, self.spn_white.value() / 100.0,
                self.combo_fond.currentData())
            t = teinte(puissances[-1], feed_l, w_max, 0.0)
            for row in range(h):
                y = (h - 1 - row) * pitch
                col = 0
                while col < w:
                    k0 = grille[row][col]
                    c0 = col
                    while col < w and grille[row][col] == k0:
                        col += 1
                    if k0 is None:      # bois nu : rien à peindre
                        continue
                    largeur_k = w_min + (w_max - w_min) * k0 / float(n - 1)
                    strokes.append(([(c0 * pitch, y), (col * pitch, y)],
                                    largeur_k, t))
        elif t["cle"] in ("dither", "simili"):
            # Deux tramages BINAIRES balayés : chaque case allumée est
            # brûlée sur un PAS entier, à puissance et vitesse fixes. Seul
            # l'algorithme qui décide des cases change -- diffusion d'erreur
            # (densité de points) ou trame à 45° (diamètre des points).
            feed_l = self.spn_line_feed.value()
            if t["cle"] == "simili":
                # Au foyer, et à la largeur BRÛLÉE mesurée si on l'a : c'est
                # elle qui donne l'engraissement des points, donc l'écart
                # entre le gris demandé et celui qui sortira du bois.
                largeur = core.burn_width_at(power, feed_l, material) \
                    or core.SPOT_FOCUS_MM
                # Le k de l'aperçu se calcule sur le pas RÉELLEMENT en main
                # (la grille est réduite), pour garder le bon nombre de
                # points en travers de l'image.
                pas_eff = self.spn_width.value() / max(1, w - 1)
                binaire = core.am_halftone_screen(
                    darkness, core.am_screen_k(self.spn_dot_spacing.value(),
                                               pas_eff))
            else:
                binaire = core.floyd_steinberg_dither(darkness)
            if not binaire:
                return None, "trame impossible à construire"
            t = teinte(power, feed_l, largeur, z_ref)
            for row in range(h):
                y = (h - 1 - row) * pitch
                for col in range(w):
                    if binaire[row][col]:
                        strokes.append((
                            [(col * pitch, y), ((col + 1) * pitch, y)],
                            largeur, t))
        else:
            # Diffusion : points tous identiques, la densité porte l'image.
            # Durée variable : un point par case, c'est la durée du pulse
            # (donc la vitesse du micro-trait) qui porte le gris.
            for x, y, dw in core.halftone_dots(
                    darkness, pitch, dwell_min, dwell_max,
                    mode="duree" if t["cle"] == "duree" else "diffusion",
                    white_threshold=white):
                f_dot = max(1.0, seg / max(dw, 1e-3) * 60.0)
                strokes.append(([(x - demi, y), (x + demi, y)], largeur,
                                teinte(power, f_dot, largeur, z_ref)))

        if not strokes:
            return None, "aucun point à graver (seuil blanc trop haut ?)"
        img = _render_engraving_photo(strokes, scale=sc, margin_mm=marge,
                                      max_px=max(largeur_px, 1200))
        if img is None:
            return None, "rendu impossible"
        # Pas de compte de marques dans la note : l'aperçu tourne sur une
        # grille réduite, le chiffre serait faux. On annonce plutôt D'OÙ
        # viennent les gris -- ça, c'est vrai à toutes les échelles.
        return img, hors or "tons mesurés sur le nuancier « {} »".format(
            material or "?")

    def _apercu_lignes_calibrees(self, darkness, pitch, sc, marge):
        """Tramage « lignes calibrées » : pas de marques isolées mais un
        balayage continu, donc une CASE peinte par pixel. On passe par la
        fonction du générateur, puis on remonte de S à la noirceur
        réellement obtenue -- ce qui rend visibles les deux pertes que la
        noirceur demandée cache : les pixels sous le seuil (bois nu) et
        les ombres écrasées sur le plafond S_MAX."""
        h = len(darkness)
        w = len(darkness[0])
        largeur = self.spn_spot_width.value()
        if largeur <= 0:
            largeur = max(pitch, core.SPOT_FOCUS_MM)
        conv = core.photo_line_power_fn(
            self.combo_photo_mat.currentData(), pitch, largeur,
            self.spn_line_feed.value(), self.spn_white.value() / 100.0)
        if conv is None:
            return None, ("le nuancier de ce matériau n'a pas 2 tons en "
                          "défocus : impossible de calibrer les gris")
        puissance, infos = conv
        tons = core.photo_line_tone_table(puissance)
        s_max = max(tons)

        cases = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
        nus = plafonnes = 0
        for y in range(h):
            ligne = darkness[y]
            for x in range(w):
                s = puissance(ligne[x])
                if s <= 0:
                    nus += 1
                    cases.setPixel(x, y, QtGui.qRgb(*_BOIS_APERCU))
                    continue
                if s >= s_max:
                    plafonnes += 1
                v = 1.0 - tons.get(s, 0.0)
                cases.setPixel(x, y, QtGui.qRgb(int(_BOIS_APERCU[0] * v),
                                                int(_BOIS_APERCU[1] * v),
                                                int(_BOIS_APERCU[2] * v)))
        # Même cadrage que les tramages à marques (marge de bois autour).
        W = max(1, int((w * pitch + 2 * marge) * sc))
        H = max(1, int((h * pitch + 2 * marge) * sc))
        img = QtGui.QImage(W, H, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(*_BOIS_APERCU))
        p = QtGui.QPainter(img)
        # Sans lissage : la machine grave VRAIMENT des lignes discrètes au
        # pas de trame, l'aperçu ne doit pas les fondre en dégradé.
        p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)
        p.drawImage(QtCore.QRectF(marge * sc, marge * sc,
                                  w * pitch * sc, h * pitch * sc), cases)
        p.end()
        n = float(w * h)
        return img, "{:.0f} % de bois nu, {:.0f} % d'ombres écrasées à S{:.0f}".format(
            100.0 * nus / n, 100.0 * plafonnes / n, s_max)

    # Deux plafonds, parce que les deux surfaces n'ont pas le même budget :
    # la vignette se recalcule à CHAQUE réglage touché, l'aperçu plein
    # format part d'un clic explicite. Peindre 250 000 marques dans 240 px
    # coûtait jusqu'à 1,8 s pour un résultat où dix marques tombent sur le
    # même pixel -- le panneau devenait pâteux dès qu'on tournait un bouton.
    _VIGNETTE_MAX_CELLS = 20000

    def _update_halftone_preview(self):
        """Vignette du panneau : le MÊME rendu que le bouton « Aperçu
        photo », en petit. Sur une trame très fine, calculé sur une grille
        RÉDUITE (représentatif, coût borné) -- la génération réelle, elle,
        utilise toujours la grille exacte."""
        darkness = self._build_rows(silent=True,
                                    max_cells=self._VIGNETTE_MAX_CELLS)
        if darkness is None:
            self.lbl_halftone_preview.setVisible(False)
            return
        img, _note = self._render_photo_preview(darkness, largeur_px=240)
        if img is None:
            self.lbl_halftone_preview.setVisible(False)
            return
        self.lbl_halftone_preview.setPixmap(QtGui.QPixmap.fromImage(img))
        self.lbl_halftone_preview.setVisible(True)

    def _on_photo_preview(self):
        """Aperçu photo plein format, comme dans les autres modes.

        Le sablier ne couvre QUE le rendu. Il englobait aussi l'affichage,
        or `_show_image_dialog` est MODAL (`exec`) : le curseur restait donc
        en « occupé » pendant tout le temps que la fenêtre était ouverte,
        alors que plus rien ne travaillait. Signalé le 31/07/2026 -- la
        fenêtre marchait très bien, seul le curseur mentait."""
        darkness = self._build_rows(max_cells=self._PREVIEW_MAX_CELLS)
        if darkness is None:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            img, note = self._render_photo_preview(darkness, largeur_px=900)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if img is None:
            QtWidgets.QMessageBox.warning(
                self.form, "Aperçu photo",
                "Rendu impossible : {}.".format(note))
            return
        _show_image_dialog(img, "Aperçu photo — {} ({})".format(
            self.combo_mode.currentText(), note))

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

    def _tramage(self):
        """La ligne de `_TRAMAGES` du tramage courant -- le SEUL endroit du
        panneau qui traduit un rang de liste en propriétés. Tout le reste
        interroge le dict, jamais l'index : c'est ce qui rend impossible
        d'ajouter un tramage en oubliant l'un de ses vingt sites."""
        idx = self.combo_mode.currentIndex()
        return _TRAMAGES[idx if 0 <= idx < len(_TRAMAGES) else 0]

    def _gen_kwargs(self):
        return {
            "pitch": self.spn_pitch.value(),
            "z_work": core.Z_WORK_MM + (core.defocus_for_spot_diameter(
                self.spn_spot_width.value(), core.SPOT_FOCUS_MM,
                core.calibrated_half_angle()) or 0.0),
            "power": self.spn_power.value(),
            "dwell_min_s": self.spn_dwell_min.value() / 1000.0,
            "dwell_max_s": self.spn_dwell_max.value() / 1000.0,
            # `mode` ne concerne que generate_gcode_halftone (points, tramages
            # « diffusion » et « durée variable ») : il se lit sur la CLÉ, pas
            # sur `duree_variable` -- les gros points Z portent aussi ce
            # drapeau et ne passent pas par ce générateur.
            "mode": "duree" if self._tramage()["cle"] == "duree" else "diffusion",
            "white_threshold": self.spn_white.value() / 100.0,
        }

    def _generate(self, rows, **extra):
        """Route vers le bon générateur selon le tramage : points
        (generate_gcode_halftone) ou lignes calibrées nuancier
        (generate_gcode_photo_lines)."""
        cle = self._tramage()["cle"]
        if cle == "lignes":
            k = self._gen_kwargs()
            width = self.spn_spot_width.value()
            if width <= 0:
                # Sans largeur choisie : le pas de trame (lignes jointives).
                width = max(k["pitch"], core.SPOT_FOCUS_MM)
            return core.generate_gcode_photo_lines(
                rows, pitch=k["pitch"],
                z_work=core.Z_WORK_MM + (core.defocus_for_spot_diameter(
                    width, core.SPOT_FOCUS_MM, core.calibrated_half_angle()) or 0.0),
                feed=self.spn_line_feed.value(), line_width=width,
                material=self.combo_photo_mat.currentData(),
                white_threshold=k["white_threshold"], **extra)
        if cle == "zdots":
            k = self._gen_kwargs()
            dot_max = self.spn_spot_width.value()
            if dot_max <= core.SPOT_FOCUS_MM:
                dot_max = max(k["pitch"] * 0.9, core.SPOT_FOCUS_MM * 3)
            return core.generate_gcode_photo_zdots(
                rows, pitch=k["pitch"], z_focus=core.Z_WORK_MM,
                power=self.spn_power.value() or core.S_MAX,
                dot_min_mm=core.SPOT_FOCUS_MM, dot_max_mm=dot_max,
                dwell_min_s=k["dwell_min_s"], dwell_max_s=k["dwell_max_s"],
                white_threshold=k["white_threshold"], **extra)
        if cle == "dither":
            k = self._gen_kwargs()
            return core.generate_gcode_photo_dither_lines(
                rows, pitch=k["pitch"], z_work=k["z_work"],
                power=self.spn_power.value(), feed=self.spn_line_feed.value(),
                **extra)
        if cle == "simili":
            # Similigravure : le point doit être NET, c'est lui le grain de
            # la trame -- on grave au foyer, sans tenir compte de la
            # « largeur du point » (qui pilote le défocus des autres modes).
            k = self._gen_kwargs()
            return core.generate_gcode_photo_am(
                rows, pitch=k["pitch"], z_work=core.Z_WORK_MM,
                power=self.spn_power.value(), feed=self.spn_line_feed.value(),
                dot_spacing_mm=self.spn_dot_spacing.value(), **extra)
        if cle == "enfle":
            # Lignes gravées : au foyer aussi -- c'est la largeur brûlée au
            # foyer qui répond à la puissance (3x), pas celle du défocus.
            k = self._gen_kwargs()
            return core.generate_gcode_photo_swell_lines(
                rows, pitch=k["pitch"], z_work=core.Z_WORK_MM,
                feed=self.spn_line_feed.value(),
                material=self.combo_photo_mat.currentData(),
                line_min_mm=self.spn_line_min.value(),
                white_threshold=self.spn_white.value() / 100.0,
                fond_clair=self.combo_fond.currentData(),
                power_max=self.spn_power_max.value(), **extra)
        # Repli : les deux tramages à POINTS. Un tramage ajouté à _TRAMAGES
        # sans brancher son générateur tomberait ici et sortirait une trame
        # de points, silencieusement -- du G-code valide pour le mauvais
        # tramage, le pire des cas. On refuse en le disant.
        if cle not in ("diffusion", "duree"):
            FreeCAD.Console.PrintError(
                "Tramage « {} » sans générateur : il est déclaré dans "
                "_TRAMAGES mais _generate ne le route pas. Aucun G-code "
                "produit (plutôt qu'une trame de points muette).\n".format(cle))
            return None
        return core.generate_gcode_halftone(rows, **self._gen_kwargs(), **extra)

    def _update_duration_preview(self):
        rows = self._build_rows(silent=True)
        if rows is None:
            self.lbl_duration.setText("Durée estimée : -- (aucune image valide)")
            return
        gcode = self._generate(rows, quiet=True)
        if not gcode:
            self.lbl_duration.setText("Durée estimée : -- (image blanche, ou nuancier insuffisant ?)")
            return
        seconds = core.estimate_job_time_seconds(gcode)
        self.lbl_duration.setText("Durée estimée : {}".format(core.format_duration(seconds)))

    def _on_frame_preview(self):
        rows = self._build_rows()
        if rows is None:
            return
        gcode = self._generate(rows, frame_only=True)
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code d'aperçu généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_photo.ngc")

    def _defocus_calibration(self):
        """Défocus auquel les tons EXPLOITABLES du matériau ont été mesurés
        (ceux qui nourrissent darkness_fluence_curve : défocus ET largeur),
        ou None. C'est le régime dans lequel la courbe est valable."""
        mat = self.combo_photo_mat.currentData()
        if not mat:
            return None
        zs = [float(s.get("z_offset", 0) or 0) for s in core.load_shades(mat)
              if (s.get("z_offset", 0) or 0) > 0 and (s.get("width", 0) or 0) > 0]
        return sum(zs) / len(zs) if zs else None

    def _feeds_calibration(self):
        """Vitesses auxquelles les tons EXPLOITABLES ont été jugés, triées.

        La vitesse fait partie du régime, et ce n'est pas une subtilité :
        quatre bandes gravées à énergie par millimètre RIGOUREUSEMENT
        identique (S croît avec F, donc S/F reste constant) rendent des
        noirceurs très différentes -- plus c'est lent, plus c'est foncé
        (constaté le 29/07/2026 sur hêtre, F650 saturait dès le 2e palier
        quand F2000 tenait jusqu'au 6e). La noirceur dépend donc aussi du
        TEMPS d'exposition, que la fluence ignore. Une courbe n'est valable
        qu'au voisinage de la vitesse où elle a été mesurée."""
        mat = self.combo_photo_mat.currentData()
        if not mat:
            return []
        return sorted({float(s.get("feed", 0) or 0) for s in core.load_shades(mat)
                       if (s.get("z_offset", 0) or 0) > 0
                       and (s.get("width", 0) or 0) > 0
                       and (s.get("feed", 0) or 0) > 0})

    def _maj_regime(self):
        """Verdict en direct sur les trois réglages couplés de la section.

        Deux écarts se lisent ici, et aucun ne se voyait avant : le RÉGIME
        (grave-t-on au défocus où les tons ont été mesurés ?) et le
        RECOUVREMENT (le pas est-il plus fin que le trait ?). Un point plus
        serré que la calibration concentre la puissance sur une surface
        plus petite -- l'écart est en CARRÉ du rapport des diamètres, donc
        1,45x de point en moins = 2,1x de densité en plus, et la photo sort
        uniformément noire sans que rien ne l'annonce (constaté le
        29/07/2026 : nuancier mesuré à défocus 15, panneau réglé sur 8,75)."""
        half = core.calibrated_half_angle()
        largeur = self.spn_spot_width.value()
        pas = self.spn_pitch.value()
        z_cal = self._defocus_calibration()
        if largeur <= 0:
            largeur = max(pas, core.SPOT_FOCUS_MM)
        z_photo = core.defocus_for_spot_diameter(
            largeur, core.SPOT_FOCUS_MM, half) or 0.0
        recouvre = largeur / pas if pas > 0 else 0.0
        bouton, msgs, ok = False, [], True
        # Le régime ne compte que pour « Lignes calibrées » : les autres
        # tramages n'utilisent pas la courbe, les alarmer serait du bruit.
        # Le RECOUVREMENT, lui, est signalé dans tous les cas -- il tient à
        # la géométrie du balayage, pas à la calibration.
        if not self._tramage()["nuancier"]:
            pass
        elif z_cal is None:
            msgs.append("Aucun ton mesuré en défocus AVEC sa largeur pour ce "
                        "matériau : la courbe est vide, le tramage « Lignes "
                        "calibrées » ne pourra pas s'en servir.")
            ok = False
        else:
            l_cal = core.spot_diameter_at_defocus(z_cal, core.SPOT_FOCUS_MM, half)
            ratio = (l_cal / largeur) ** 2 if largeur > 0 else 0.0
            if abs(z_photo - z_cal) <= 1.5:
                msgs.append("Point {:.2f} mm → défocus {:.1f} mm, conforme aux "
                            "tons mesurés ({:.1f} mm).".format(largeur, z_photo, z_cal))
            else:
                ok = False
                bouton = True
                msgs.append(
                    "Point {:.2f} mm → défocus {:.1f} mm, alors que les tons de "
                    "ce matériau sont mesurés à <b>{:.1f} mm</b>. La gravure sera "
                    "<b>{:.1f}× plus {}</b> que la calibration et sortira "
                    "trop {}. Largeur à viser : <b>{:.2f} mm</b>.".format(
                        largeur, z_photo, z_cal, max(ratio, 1.0 / max(ratio, 1e-9)),
                        "dense" if ratio > 1 else "diffuse",
                        "foncée" if ratio > 1 else "claire", l_cal))
        # Vitesse : la courbe n'est valable qu'au voisinage de celle où elle
        # a été mesurée (cf. _feeds_calibration).
        if self._tramage()["nuancier"]:
            fcal = self._feeds_calibration()
            fphoto = self.spn_line_feed.value()
            if fcal and not (min(fcal) * 0.9 <= fphoto <= max(fcal) * 1.1):
                ok = False
                bouton = True
                cible = min(fcal, key=lambda f: abs(f - fphoto))
                msgs.append(
                    "Vitesse F{:.0f}, alors que les tons de ce matériau ont été "
                    "jugés à {}. À énergie égale, plus c'est lent plus c'est "
                    "foncé : hors de cette plage la courbe ne s'applique plus. "
                    "Vitesse à viser : <b>F{:.0f}</b>.".format(
                        fphoto, " ou ".join("F{:.0f}".format(f) for f in fcal),
                        cible))
        # Le recouvrement se calcule sur « Largeur du point », qui pilote le
        # DÉFOCUS. Un tramage qui grave au foyer n'a pas de point
        # défocalisé : y appliquer ce verdict ferait raisonner sur 0,80 mm
        # pendant que la machine trace 0,10 à 0,30. Ils ont le leur, bâti
        # sur les largeurs brûlées MESURÉES -- et il a sa place ici, sous
        # les trois réglages qu'il concerne (matériau, vitesse, pas).
        if self._tramage()["au_foyer"]:
            ok, bouton = self._verdict_au_foyer(msgs, pas)
        elif recouvre > 1.05:
            msgs.append("Pas {:.2f} mm pour un trait de {:.2f} : chaque point "
                        "est repassé {:.1f}×, l'atelier en tient compte.".format(
                            pas, largeur, recouvre))
        elif recouvre < 0.95 and recouvre > 0:
            msgs.append("Pas {:.2f} mm plus large que le trait ({:.2f}) : il "
                        "restera du bois nu entre les lignes.".format(pas, largeur))
        else:
            # Le cas qui va bien mérite une PHRASE, pas une coche nue. Sans
            # ce dernier cas, un pas rigoureusement égal au trait (recouvre
            # entre 0,95 et 1,05) ne produisait aucun message et le verdict
            # s'affichait « ✓ » tout seul -- impossible de savoir s'il
            # approuvait quelque chose ou s'il n'avait rien trouvé à dire.
            msgs.append("Pas {:.2f} mm pour un trait de {:.2f} : les lignes "
                        "se touchent juste, sans bois nu ni repasse.".format(
                            pas, largeur))
        self.lbl_regime.setText(
            "<span style=\"color:{}\">{} {}</span>".format(
                "#2e7d32" if ok else "#c62828", "✓" if ok else "⚠",
                " ".join(msgs)))
        self.btn_corriger_regime.setVisible(bouton)

    def _verdict_au_foyer(self, msgs, pas):
        """Verdict des tramages qui gravent AU FOYER, bâti sur les
        largeurs brûlées mesurées. Renvoie (ok, bouton).

        Ces tramages ne consultent pas le nuancier, mais ils dépendent
        entièrement de la table de kerf : c'est elle qui dit si le trait
        peut enfler (lignes gravées) et s'il tiendra dans le pas sans que
        les lignes se recouvrent (les deux)."""
        mat = self.combo_photo_mat.currentData()
        feed = self.spn_line_feed.value()
        enfle = self._tramage()["reglage"] == "trait_mini"
        plage = core.burn_width_range(mat, feed)
        if plage is None:
            msgs.append("Aucune largeur brûlée mesurée pour ce matériau : "
                        "passe par « Calibration du kerf », ce tramage n'a "
                        "que ça pour travailler.")
            return False, False
        # Le plafond de puissance rogne le HAUT de la plage : le verdict doit
        # partir de la table PLAFONNÉE -- la MÊME que le générateur -- sinon
        # il annonce un trait maxi et un contraste que le G-code ne produira
        # pas. Un seul appel, dont on tire à la fois le refus et la plage.
        plafond = self.spn_power_max.value() if enfle else None
        niveaux = (core.swell_power_levels(mat, feed, self.spn_line_min.value(),
                                           power_max=plafond)
                   if enfle else None)
        if enfle and niveaux is not None:
            plage = (niveaux[1], niveaux[2])
        if enfle and (niveaux is None or plage[1] - plage[0] < 1e-9):
            # Majuscule sur la PREMIÈRE lettre seulement : capitalize()
            # rabattrait « F800 » en « f800 » dans la suite du message.
            m = core.swell_refus_message(mat, feed, plafond)
            msgs.append(m[:1].upper() + m[1:])
            return False, False
        if enfle:
            w_min = max(self.spn_line_min.value(), plage[0])
            w_max = plage[1]
            # Le contraste, c'est l'ÉCART DE COUVERTURE réellement obtenu --
            # de fin/pas à épais/pas, ce dernier plafonné à 100 %. Pas le
            # rapport fin/épais : celui-là ne dépend pas du pas et reste
            # obstinément le même pendant que l'image change à vue d'oeil
            # (signalé le 29/07/2026, « toujours 56 % alors que la photo
            # noircit quand je diminue le pas »).
            #
            # Cet écart passe par un MAXIMUM au pas qui vaut exactement le
            # trait le plus épais, et redescend des deux côtés : au-dessus
            # les noirs n'atteignent jamais 100 %, en dessous ils y sont
            # déjà et seuls les clairs s'assombrissent. Sur hêtre à F800
            # (0,10 → 0,30 mm) : 67 points au pas 0,30, mais 50 au pas 0,40
            # comme au pas 0,20.
            bas = w_min / pas
            haut = min(1.0, w_max / pas)
            ecart = haut - bas
            ecart_max = 1.0 - w_min / w_max
            msgs.append(
                "Trait <b>{:.2f} → {:.2f} mm</b> à F{:.0f} : couverture "
                "{:.0f} → {:.0f} %, contraste <b>{:.0f} points</b>.".format(
                    w_min, w_max, feed, 100.0 * bas, 100.0 * haut,
                    100.0 * ecart))
            # Ce plancher de couverture est aussi ce que reçoit une case
            # BLANCHE, faute de seuil : le palier le plus bas n'est pas
            # « rien », c'est la puissance la plus basse mesurée. Un fond
            # blanc sortait donc gris uni (planche du 31/07/2026). Le dire
            # AVANT de graver, avec le chiffre, plutôt qu'après sur le bois.
            seuil = self.spn_white.value() / 100.0
            if seuil <= 0.0 and bas > 0.05:
                msgs.append(
                    "<b>Sans seuil blanc, le blanc pur grave quand même</b> "
                    "un trait de {:.2f} mm, soit <b>{:.0f} % de couverture</b> "
                    "— un fond blanc sortira gris uni, et le choix «&nbsp;Sous "
                    "le seuil&nbsp;» reste sans effet. Monte «&nbsp;Seuil "
                    "blanc&nbsp;» à 5-8 %.".format(w_min, 100.0 * bas))
                # ROUGE, pas vert. Le verdict décrivait ce défaut tout en
                # affichant une coche verte : personne ne lit un avertissement
                # sous un ✓. C'est exactement ce qui a laissé partir un aperçu
                # au fond gris uni le 31/07/2026, alors que le panneau
                # l'annonçait mot pour mot.
                return False, False
            elif seuil > 0.0 and self.combo_fond.currentData() == "pointille":
                msgs.append(
                    "Seuil blanc {:.0f} %, fond <b>pointillé</b> : sous cette "
                    "noirceur le trait le plus fin s'espace, donc la "
                    "couverture descend continûment de {:.0f} % à 0 — pas de "
                    "marche dans les dégradés.".format(100.0 * seuil,
                                                       100.0 * bas))
            elif seuil > 0.0:
                msgs.append(
                    "Seuil blanc {:.0f} % : sous cette noirceur, bois nu "
                    "(faisceau coupé, mouvement continu). Le passage au-dessus "
                    "du seuil est une <b>marche</b> à {:.0f} % de couverture ; "
                    "le fond «&nbsp;pointillé&nbsp;» l'adoucit.".format(
                        100.0 * seuil, 100.0 * bas))
            # LA VITESSE D'ABORD, LE PAS ENSUITE. Au-delà de la plus rapide
            # utile, le trait cesse d'enfler jusqu'au bout : c'est toute la
            # plage qui rétrécit. Conseiller alors de resserrer le pas
            # revient à s'aligner sur une plage déjà amputée -- alors qu'il
            # suffit de ralentir, et le pas était bon. Relevé sur la
            # première photo gravée dans ce tramage (30/07/2026) : F1000 au
            # pas 0,30 mm, trait plafonné à 0,23 au lieu de 0,30, et le
            # panneau conseillait le pas 0,23. 43 points au lieu de 67.
            rapide = core.swell_max_feed(mat)
            lente = core.burn_width_range(mat, rapide) if rapide else None
            if lente and feed > rapide + 1e-9:
                w_lent = max(self.spn_line_min.value(), lente[0])
                ecart_lent = min(1.0, lente[1] / pas) - w_lent / pas
                if ecart_lent > ecart + 0.01:
                    msgs.append(
                        "À <b>F{:.0f}</b> — la plus rapide où le trait enfle "
                        "encore à fond — il irait jusqu'à {:.2f} mm : "
                        "<b>{:.0f} points</b> de contraste au même pas. "
                        "Ralentir rapporte plus que resserrer le pas.".format(
                            rapide, lente[1], 100.0 * ecart_lent))
                    return False, False
            if abs(pas - w_max) > 0.005:
                conseil = ("Contraste maximal ({:.0f} points) au pas "
                           "<b>{:.2f} mm</b>, celui qui vaut le trait le plus "
                           "épais.".format(100.0 * ecart_max, w_max))
                if pas < w_max:
                    conseil += (" Plus fin, les noirs saturent déjà : seuls "
                                "les clairs s'assombrissent.")
                msgs.append(conseil)
                # Simple conseil tant que la perte reste modeste ; alerte
                # quand on laisse vraiment du contraste sur la table.
                if ecart < 0.8 * ecart_max:
                    return False, False
            return True, False
        # À partir d'ici : similigravure seule (les lignes gravées ont rendu
        # leur verdict au-dessus). Un point brûlé à fond, donc la largeur du
        # haut de la plage.
        trait = plage[1]
        msgs.append("Points brûlés à {:.2f} mm à F{:.0f}.".format(trait, feed))
        if trait > pas + 1e-9:
            msgs.append("Le trait dépasse le pas ({:.2f} mm) : les lignes se "
                        "recouvrent dans les foncés. Pas ≥ <b>{:.2f} mm</b> "
                        "pour les garder distinctes.".format(pas, trait))
            return False, False
        if pas > trait + 1e-9:
            msgs.append("Pas {:.2f} mm plus large que le trait : la trame "
                        "sortira <b>{:.0f} % trop claire</b> (bois nu entre "
                        "les lignes). Pas à viser : <b>{:.2f} mm</b>.".format(
                            pas, 100.0 * (1.0 - trait / pas), trait))
            return False, False
        return True, False

    def _corriger_regime(self):
        """Aligne largeur du point ET vitesse sur la calibration -- les deux
        axes du régime, corrigés ensemble : n'en rattraper qu'un laisse la
        courbe hors de son domaine tout autant."""
        z_cal = self._defocus_calibration()
        if z_cal is not None:
            self.spn_spot_width.setValue(core.spot_diameter_at_defocus(
                z_cal, core.SPOT_FOCUS_MM, core.calibrated_half_angle()))
        fcal = self._feeds_calibration()
        if fcal:
            f = self.spn_line_feed.value()
            if not (min(fcal) * 0.9 <= f <= max(fcal) * 1.1):
                self.spn_line_feed.setValue(min(fcal, key=lambda x: abs(x - f)))

    def _on_sampler(self):
        """Mire comparative : le même dégradé gravé par les SEPT tramages
        (bandes étiquetées 1-7), avec les réglages courants du panneau.

        Les réglages propres aux tramages 6 et 7 (espacement de trame, trait
        mini) sont passés même quand leurs champs sont masqués : la mire les
        grave TOUS, quel que soit le tramage sélectionné -- c'est justement à
        ça qu'elle sert."""
        k = self._gen_kwargs()
        width = self.spn_spot_width.value()
        if width <= 0:
            width = max(k["pitch"], core.SPOT_FOCUS_MM)
        gcode = core.generate_gcode_photo_sampler(
            pitch=k["pitch"],
            z_work=core.Z_WORK_MM + (core.defocus_for_spot_diameter(
                width, core.SPOT_FOCUS_MM, core.calibrated_half_angle()) or 0.0),
            dwell_min_s=k["dwell_min_s"], dwell_max_s=k["dwell_max_s"],
            power=self.spn_power.value() or core.S_MAX / 2.0,
            feed=self.spn_line_feed.value(), line_width=width,
            material=self.combo_photo_mat.currentData(),
            dot_spacing_mm=self.spn_dot_spacing.value(),
            line_min_mm=self.spn_line_min.value(),
            white_threshold=k["white_threshold"])
        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code de mire généré.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/mire_tramages_photo.ngc")

    def accept(self):
        _save_last_values("halftone", self._last_fields)
        rows = self._build_rows()
        if rows is None:
            return False

        gcode = self._generate(rows, )

        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Aucun G-code généré : image toute blanche au seuil actuel, ou "
                "(tramage Lignes calibrées) nuancier sans 2 tons en défocus.")
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
        _calibration_banner(form, "Grille de test puissance / vitesse")

        _bullet_list(form, [
            "<b>1.</b> Nouveau matériau à calibrer de façon standard&nbsp;? "
            "Utilise plutôt l'<b>Assistant matériau</b> (planches, mesures "
            "et déductions regroupées) : reste ici seulement pour une "
            "plage personnalisée ou une découpe.",
            "<b>2.</b> Grave une grille de cellules sur une chute (aucune "
            "sélection requise)&nbsp;: chaque cellule teste un couple "
            "puissance/vitesse ; choisis la meilleure à l'œil.",
        ])
        _diagram(form, "diag_grid.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Aucune sélection requise&nbsp;: la grille ne dépend "
            "d'aucun objet du document.",
            "<b>2. Mode &amp; plages</b>&nbsp;: gravure ou découpe, plage de "
            "puissances (colonnes&nbsp;X) et de vitesses (lignes&nbsp;Y), nombre "
            "de cellules.",
            "<b>3. Cellules &amp; remplissage</b>&nbsp;: taille des cellules, "
            "plein ou contour, étiquettes S/F imprimées sur la pièce.",
            "<b>4. Hauteur (Z) de test</b>&nbsp;: rejoue la même grille à une "
            "autre hauteur (bec défocalisé) pour caractériser un matériau, une "
            "hauteur à la fois.",
            "<b>5. Génère et grave</b> sur une chute. Choisis la meilleure "
            "cellule à l'œil, puis reporte S/F au mode <b>Nuancier</b> (pour "
            "un ton) ou en préréglage.",
        ])

        # ① GRAVER : d'abord un « objectif » (préréglage recommandé prêt à
        # graver selon ce qu'on veut mesurer), puis les préréglages nommés par
        # matériau (jeu complet de réglages sauvegardé sous un nom).
        _section(form, "① Graver — préréglage recommandé", "sect_preset.svg")

        self._recipes = [
            ("nuancier_clair", {
                "label": "Nuancier — tons clairs (défocus)",
                "mode": 0, "power_min": 200, "power_max": 600, "power_steps": 4,
                "feed_min": 1000, "feed_max": 4000, "feed_steps": 4,
                "filltype": 2, "hatch_spacing": 1.0, "border": True,
                "note": "16 cases du clair (S200/F4000 ≈ 5 %) au foncé "
                        "(S600/F1000 ≈ 74 %, raccord avec le nuancier mesuré). "
                        "Point élargi ≈ 1 mm : complète le bas du nuancier."}),
            # Les deux objectifs « largeurs » gravent EXACTEMENT les lignes et
            # colonnes de la grille de saisie ② -- listes tirées des mêmes
            # constantes, pour que l'alignement soit structurel et non une
            # coïncidence à entretenir. Il ne l'était pas : cet objectif-ci
            # gravait 400/1800/3200/4600/6000 quand ② n'accepte que
            # 200/400/800/1500/3000, soit quatre vitesses sur cinq sans
            # aucune case où être saisies -- et F6000 ne marque plus depuis
            # le changement de lentille du 27 juil. 2026.
            ("largeurs_foyer", {
                "label": "Largeurs brûlées — grille au foyer",
                "mode": 0,
                "powers": sorted(_MesuresPlanchesControleur.POWERS),
                "feeds": list(_MesuresPlanchesControleur.FEEDS_FOCUS),
                # 2 mm entre traits, pour des traits ISOLÉS mesurables un
                # par un. À 0,20 mm -- la valeur d'avant -- les cases lentes
                # et puissantes sortaient en APLAT, où la largeur d'un trait
                # ne se mesure pas, alors que c'est précisément ce que la
                # note demande de faire.
                # Pourquoi 2 et pas 1 : le hêtre et le MDF plafonnent à
                # 0,30/0,34 mm au foyer, mais le SAPIN est mesuré à 1,00 mm
                # (S1000/F400) -- un résineux brûle bien plus large. Un
                # espacement calé sur les feuillus aurait rendu la planche
                # illisible sur résineux, en silence.
                "filltype": 0, "hatch_spacing": 2.0, "cell_size": 16.0,
                "border": True,
                "note": "Traits ISOLÉS au foyer, aux puissances et vitesses "
                        "exactes de la grille de saisie ② : mesure la LARGEUR "
                        "d'un trait au pied à coulisse, case par case."}),
            ("largeurs_defocus", {
                "label": "Largeurs brûlées — grille en défocus",
                "powers": sorted(_MesuresPlanchesControleur.POWERS),
                "feeds": list(_MesuresPlanchesControleur.FEEDS_DEFOCUS),
                # Vitesses LENTES, et c'est tout l'enjeu : en défocus le point
                # est ~4x plus large qu'au foyer, donc la densité de puissance
                # chute d'autant et un trait ISOLÉ ne marque plus au-delà de
                # ~F1000. Une première version visait F1000-4000 (la plage des
                # tons du nuancier) : 18 cases sur 25 sont sorties vierges sur
                # hêtre. Les largeurs déjà mesurées de l'atelier le disaient
                # d'ailleurs -- toutes entre F200 et F800.
                #
                # Les paliers viennent maintenant des constantes de ② : la
                # version d'avant gravait S400/550/700/850/1000 et
                # F200/650/1100/1550/2000, dont trois puissances et quatre
                # vitesses n'avaient aucune case de saisie.
                "mode": 0,
                "filltype": 0, "hatch_spacing": 3.0, "border": True,
                "cell_defocus": 15.0, "cell_size": 16.0,
                "note": "Traits ISOLÉS en défocus 15 mm : l'espacement de 3 mm "
                        "dépasse largement le point élargi (~1,15 mm), donc "
                        "chaque trait se mesure seul au pied à coulisse.\n"
                        "Grave-la DEUX FOIS, en ne changeant que l'espacement "
                        "des hachures : à 3 mm pour mesurer la LARGEUR d'un "
                        "trait, puis à 1 mm pour juger la NOIRCEUR en aplat. "
                        "Un aplat ne se juge pas sur des traits espacés, et "
                        "une largeur ne se mesure pas sur un aplat -- il faut "
                        "les deux vues du même réglage.\n"
                        "Vitesses volontairement LENTES : en défocus, un trait "
                        "isolé cesse de marquer bien avant les vitesses où "
                        "vivent les tons clairs. Le haut de l'échelle de "
                        "noirceur restera donc peut-être sans largeur "
                        "mesurable -- c'est une limite physique, pas un "
                        "réglage à forcer. Mesure ce qui est lisible.\n"
                        "Reporte ensuite chaque case dans Nuancier « + Ajouter "
                        "un ton » avec SES DEUX mesures : c'est le couple "
                        "noirceur+largeur en défocus qui alimente la photo "
                        "calibrée et le « ton sur mesure ». Une largeur au "
                        "foyer, ou une noirceur sans largeur, ne leur sert à "
                        "rien."}),
            ("noirceur_balayage", {
                "label": "Noirceur — bande en balayage (photo calibrée)",
                "mode": 0,
                # UNE SEULE vitesse, et c'est toute la raison d'être de cet
                # objectif. La noirceur ne dépend pas que de l'énergie : à
                # énergie par millimètre rigoureusement égale, plus c'est
                # lent, plus c'est foncé (établi le 29/07/2026 sur quatre
                # bandes). Une courbe bâtie sur des tons mesurés à des
                # vitesses mélangées est donc incohérente par construction
                # -- c'était le cas, clairs à F2000 et foncés à F650, et
                # aucune correction de formule ne pouvait la sauver.
                "feeds": [2000.0],
                # Puissances réparties de 200 à 1000... puis DÉLIBÉRÉMENT
                # mélangées. Alignées par ordre croissant, les cases se
                # jugent les unes par rapport aux autres et l'oeil
                # reconstruit une progression régulière sans qu'on s'en
                # aperçoive : une première série ainsi jugée est sortie en
                # progressions arithmétiques exactes, avec 11 % de paires
                # inversées par rapport à l'ordre des énergies. Chaque case
                # porte sa puissance gravée sous elle, la lecture reste
                # directe.
                "powers": [200.0, 644.0, 378.0, 822.0, 556.0,
                           1000.0, 289.0, 733.0, 467.0, 911.0],
                "filltype": 0, "hatch_spacing": 0.80, "cell_size": 16.0,
                "cell_defocus": 15.0, "border": True,
                # Pré-remplit « + Ajouter ce ton » avec la vitesse, le
                # défocus et surtout la LARGEUR = le pas de hachure.
                "ton_balayage": True,
                "note": "Bande d'APLATS gravés comme une photo : même "
                        "vitesse, même défocus, même pas que la gravure "
                        "visée. C'est elle qui alimente la courbe "
                        "noirceur → énergie, donc la photo calibrée et le "
                        "« ton sur mesure ».\n"
                        "Juge la noirceur de chaque case (0 = bois intact, "
                        "100 = noir max) et reporte-la dans « + Ajouter ce "
                        "ton » ci-dessous — les champs sont déjà remplis, "
                        "il ne reste que la noirceur et la puissance de la "
                        "case.\n"
                        "La LARGEUR à saisir est l'ESPACEMENT DES HACHURES, "
                        "pas une mesure au pied à coulisse : en balayage, "
                        "ce qui gouverne l'énergie reçue par le bois est de "
                        "combien on avance entre deux passes. C'est "
                        "pré-rempli pour cette raison.\n"
                        "Les puissances sont volontairement dans le "
                        "désordre : rangées par ordre croissant, les cases "
                        "se jugent les unes par rapport aux autres et l'œil "
                        "fabrique une progression régulière qui n'existe "
                        "pas. Chaque case porte sa puissance gravée "
                        "en dessous.\n"
                        "Cette calibration ne vaut QUE pour la vitesse, le "
                        "défocus et le pas gravés ici. Changer l'un des "
                        "trois pour la gravure finale la sort de son "
                        "régime."}),
            ("decoupe", {
                "label": "Découpe — trouver le passage",
                "mode": 1, "power_min": 400, "power_max": 1000, "power_steps": 4,
                "feed_min": 100, "feed_max": 600, "feed_steps": 4,
                "border": False,
                "note": "Contours seuls : repère la case qui traverse "
                        "proprement en une passe."}),
        ]
        self.combo_recipe = QtWidgets.QComboBox()
        self.combo_recipe.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_recipe.setMinimumContentsLength(20)
        self.combo_recipe.addItem("— (réglages manuels) —", None)
        for key, r in self._recipes:
            self.combo_recipe.addItem(r["label"], key)
        self.combo_recipe.setToolTip(
            "Remplit d'un coup toute la grille (mode, plages S/F, "
            "remplissage) avec des réglages prêts à graver selon la donnée "
            "que tu veux obtenir. Tu peux ensuite ajuster à la main.")
        form.addRow("Objectif :", self.combo_recipe)

        self.lbl_recipe_note = _WrapLabel("")
        self.lbl_recipe_note.setVisible(False)
        form.addRow(self.lbl_recipe_note)
        self.combo_recipe.currentIndexChanged.connect(self._on_recipe_selected)

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

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder")
        _btn_icon(self.btn_save_preset, "sect_preset.svg")
        self.btn_save_preset.setToolTip(
            "Sauvegarde les valeurs actuelles de TOUT le panneau sous un\n"
            "NOUVEAU nom de préréglage, sans toucher aux préréglages\n"
            "existants (confirmation demandée si le nom choisi existe déjà).")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer")
        self.btn_delete_preset.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        _mat_row = QtWidgets.QWidget()
        _mat_h = QtWidgets.QHBoxLayout(_mat_row)
        _mat_h.setContentsMargins(0, 0, 0, 0)
        _mat_h.addWidget(self.btn_save_preset)
        _mat_h.addWidget(self.btn_delete_preset)
        form.addRow(_mat_row)

        self.btn_generer = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_generer, "sect_gcode.svg")
        self.btn_generer.setToolTip(
            "Crée les cellules dans le document, génère le G-code de la\n"
            "grille (réglages des sections ci-dessous) et propose\n"
            "l'enregistrement. Le panneau reste ouvert pour saisir les\n"
            "largeurs (②) après la gravure. OK, lui, ferme le panneau.")
        self.btn_generer.clicked.connect(self._on_generer)
        form.addRow(self.btn_generer)

        # Procédure d'abord : ② mesures et ③ photo suivent directement ① ;
        # les réglages manuels de la grille viennent après.
        self._build_measures_section(form)
        self._photo = _make_photo_section(
            form, lambda: "testgrid:" + self.edt_measure_mat.currentText().strip(),
            titre="③ Photo du résultat")

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

        # Un objectif peut FIXER les paliers au lieu d'une plage : les
        # champs ci-dessus deviennent alors incapables de les décrire (une
        # plage répartit linéairement, et les colonnes de saisie des
        # largeurs sont géométriques). On les verrouille et on affiche les
        # valeurs réellement gravées -- afficher une plage qui ne
        # correspond pas au job serait pire que ne rien afficher.
        self.lbl_paliers = _WrapLabel("")
        self.lbl_paliers.setVisible(False)
        self.lbl_paliers.setStyleSheet("color: #2e7d32;")
        form.addRow(self.lbl_paliers)
        self._paliers_objectif = (None, None)
        self._champs_plages = (
            self.spn_power_min, self.spn_power_max, self.spn_power_steps,
            self.spn_feed_min, self.spn_feed_max, self.spn_feed_steps)

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

        self.spn_cell_defocus = QtWidgets.QDoubleSpinBox()
        self.spn_cell_defocus.setRange(0.0, 60.0)
        self.spn_cell_defocus.setDecimals(2)
        self.spn_cell_defocus.setValue(0.0)
        self.spn_cell_defocus.setSuffix(" mm")
        self.spn_cell_defocus.setToolTip(
            "Écart au foyer appliqué aux CELLULES SEULES : elles se gravent\n"
            "à « Hauteur (Z) de test » + cette valeur, pendant que les\n"
            "étiquettes d'axe et le cadre restent au foyer, donc nets et\n"
            "lisibles. Écarter tout le job (en montant la hauteur de test)\n"
            "défocaliserait aussi les chiffres, qui baveraient.\n"
            "0 = tout au foyer. Ignoré en remplissage « Défocus (noir) »,\n"
            "où le défocus est déduit de l'espacement des hachures.")
        form.addRow("Défocus des cellules :", self.spn_cell_defocus)
        # Changer le niveau qu'on va graver ouvre sa grille de saisie dans
        # ② : sans ça, on grave une planche à 25 mm et il n'existe nulle
        # part où en noter les largeurs.
        self.spn_cell_defocus.valueChanged.connect(
            lambda _v: self._mesures.reload())

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

        self.combo_line_style = QtWidgets.QComboBox()
        self.combo_line_style.addItems(["Plein", "Tirets", "Pointillé"])
        self.combo_line_style.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_line_style.setMinimumContentsLength(14)
        self.combo_line_style.setToolTip(
            "Style du trait de remplissage des cellules : plein, tirets\n"
            "(tronçons espacés) ou pointillé (micro-traits) -- pour tester le\n"
            "rendu d'un style à travers la matrice puissance/vitesse.\n"
            "Vague et dégradé sont des effets de défocus (Z) : à tester dans\n"
            "Marquage, pas dans une grille à Z fixe.")
        form.addRow("Style de trait :", self.combo_line_style)

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

        # Un champ décrit par le résumé de préréglage (_preset_summary),
        # modifié à la main, invalide ce résumé -- voir _on_champ_manuel_modifie.
        for _w in (self.combo_mode, self.combo_filltype):
            _w.currentIndexChanged.connect(self._on_champ_manuel_modifie)
        for _w in (self.spn_power_min, self.spn_power_max, self.spn_power_steps,
                   self.spn_feed_min, self.spn_feed_max, self.spn_feed_steps,
                   self.spn_cell_size, self.spn_gap, self.spn_zwork,
                   self.spn_cell_defocus,
                   self.spn_hatch_spacing, self.spn_hatch_angle,
                   self.spn_border_power, self.spn_border_feed):
            _w.valueChanged.connect(self._on_champ_manuel_modifie)
        for _w in (self.chk_proximity, self.chk_labels, self.chk_border):
            _w.toggled.connect(self._on_champ_manuel_modifie)

        _section(form, "Aperçus & génération", "sect_gcode.svg")
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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel dans la vue 3D de FreeCAD : gris fin =\n"
            "transit laser éteint (G0), rouge épais = gravure/découpe\n"
            "laser allumé (G1). Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])
        _combined_add_button(form, self._on_add_to_combined)

        self.edt_measure_mat.currentIndexChanged.connect(
            lambda _i: self._reload_measures_and_photo())
        self.edt_measure_mat.lineEdit().editingFinished.connect(
            self._reload_measures_and_photo)

        self._last_fields = {
            "mode": self.combo_mode, "power_min": self.spn_power_min,
            "power_max": self.spn_power_max, "power_steps": self.spn_power_steps,
            "feed_min": self.spn_feed_min, "feed_max": self.spn_feed_max,
            "feed_steps": self.spn_feed_steps, "cell_size": self.spn_cell_size,
            "gap": self.spn_gap, "zwork": self.spn_zwork, "filltype": self.combo_filltype,
            "line_style": self.combo_line_style,
            "hatch_spacing": self.spn_hatch_spacing, "hatch_angle": self.spn_hatch_angle,
            "proximity": self.chk_proximity,
            "labels": self.chk_labels, "border": self.chk_border,
            "border_power": self.spn_border_power,
            "border_feed": self.spn_border_feed,
        }
        _restore_last_values("testgrid", self._last_fields)

        self.form = _scrollable(inner)
        self.form.setWindowTitle("Grille de test puissance/vitesse")
        self.form.setWindowIcon(_icon("testgrid.svg"))

        self._populate_preset_combo()
        self._update_duration_preview()
        self._photo["reload"]()

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
            lines.append("Étiquettes S{:g} F{:g} (Préférences)".format(
                core.LABEL_POWER, core.LABEL_FEED))
        if values.get("border_enabled", True):
            lines.append("Cadre au foyer S{:g} F{:g}".format(
                values.get("border_power", 0), values.get("border_feed", 0)))
        return "\n".join(lines)

    def _line_style(self):
        """Style de trait du remplissage des cellules (combo -> clé core)."""
        return ("plein", "tirets", "pointille")[self.combo_line_style.currentIndex()]

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
        self.chk_border.setChecked(values.get("border_enabled", self.chk_border.isChecked()))
        self.spn_border_power.setValue(values.get("border_power", self.spn_border_power.value()))
        self.spn_border_feed.setValue(values.get("border_feed", self.spn_border_feed.value()))
        self.lbl_preset_summary.setText(self._preset_summary(values))
        self.lbl_preset_summary.setVisible(True)

    def _on_champ_manuel_modifie(self, *_args):
        """Masque le résumé du préréglage dès qu'un champ qu'il décrit est
        modifié à la main : sans ça, le résumé restait affiché avec les
        valeurs du DERNIER préréglage chargé même après les avoir
        personnalisées, juste au-dessus du bouton Générer -- donnant
        l'impression trompeuse que Générer va reproduire ce préréglage
        plutôt que les valeurs actuelles des champs (ce qu'il fait déjà
        correctement)."""
        self.lbl_preset_summary.setVisible(False)

    def _on_save_preset(self):
        # Champ vierge (pas pré-rempli avec le préréglage courant) : la
        # sauvegarde AJOUTE un nouveau préréglage par défaut, elle ne
        # remplace un existant que si on tape volontairement son nom --
        # et seulement après confirmation, ci-dessous.
        name, ok = QtWidgets.QInputDialog.getText(
            self.form, "Sauvegarder le préréglage",
            "Nom du préréglage (matériau) :")
        name = name.strip()
        if not ok or not name:
            return
        if name in core.all_presets("testgrid"):
            reply = QtWidgets.QMessageBox.question(
                self.form, "Préréglage existant",
                "Un préréglage « {} » existe déjà -- le remplacer ?".format(name),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            if reply != QtWidgets.QMessageBox.Yes:
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
            cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(),
            quiet=True, line_style=self._line_style(), **self._border_kwargs()
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
        elif mode == "gravure":
            # Défocus SAISI, indépendant de l'espacement : nécessaire pour
            # graver des traits isolés (espacement large) à un défocus donné,
            # ce que le remplissage « Défocus (noir) » ne sait pas exprimer --
            # il déduit le défocus de l'espacement, donc un espacement large
            # y donnerait un point énorme au lieu de traits séparés.
            cell_z_offset = self.spn_cell_defocus.value()
        if cell_z_offset > 0:
            # Rayon du point élargi à ce défocus : on rentre la zone
            # hachurée d'autant pour que la brûlure ne déborde pas du carré.
            spot = core.spot_diameter_at_defocus(
                cell_z_offset, core.SPOT_FOCUS_MM, core.calibrated_half_angle())
            fill_inset = spot / 2.0

        powers, feeds = getattr(self, "_paliers_objectif", (None, None))
        cells = core.build_test_grid_cells(
            mode,
            self.spn_power_min.value(), self.spn_power_max.value(), self.spn_power_steps.value(),
            self.spn_feed_min.value(), self.spn_feed_max.value(), self.spn_feed_steps.value(),
            self.spn_cell_size.value(), self.spn_gap.value(),
            fill_type=fill_type,
            hatch_spacing=self.spn_hatch_spacing.value(), hatch_angle=self.spn_hatch_angle.value(),
            fill_inset=fill_inset,
            powers=powers, feeds=feeds,
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
            cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(), quiet=True,
            line_style=self._line_style(), **self._border_kwargs()
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
                               cell_z_offset=cell_z_offset, use_proximity=self.chk_proximity.isChecked(),
                               **self._border_kwargs())}

    def _on_add_to_combined(self):
        op = self._build_combined_operation()
        if op:
            _add_to_combined_job(op)

    def _on_recipe_selected(self, index):
        """Applique un « objectif » recommandé : remplit d'un coup mode,
        plages S/F et remplissage avec un jeu de réglages prêt à graver.
        Grise le préréglage matériau tant que l'objectif gouverne les
        réglages affichés -- deux points de départ actifs à la fois (recette
        générique vs réglages sauvegardés d'un matériau) n'a pas de sens."""
        key = self.combo_recipe.itemData(index)
        r = dict(self._recipes).get(key) if key else None
        self.combo_preset.setEnabled(r is None)
        self.btn_delete_preset.setEnabled(r is None)
        if r is not None:
            self.combo_preset.blockSignals(True)
            self.combo_preset.setCurrentIndex(0)
            self.combo_preset.blockSignals(False)
            self.lbl_preset_summary.setVisible(False)
        if not r:
            self.lbl_recipe_note.setVisible(False)
            self._appliquer_paliers(None, None)
            return
        self.combo_mode.setCurrentIndex(r.get("mode", 0))
        self._appliquer_paliers(r.get("powers"), r.get("feeds"))
        if "power_min" in r:
            self.spn_power_min.setValue(r["power_min"])
            self.spn_power_max.setValue(r["power_max"])
            self.spn_power_steps.setValue(r["power_steps"])
        if "feed_min" in r:
            self.spn_feed_min.setValue(r["feed_min"])
            self.spn_feed_max.setValue(r["feed_max"])
            self.spn_feed_steps.setValue(r["feed_steps"])
        if "filltype" in r:
            self.combo_filltype.setCurrentIndex(r["filltype"])
        if "hatch_spacing" in r:
            self.spn_hatch_spacing.setValue(r["hatch_spacing"])
        if "cell_size" in r:
            self.spn_cell_size.setValue(r["cell_size"])
        # Le défocus s'applique aux CELLULES SEULES, jamais en montant la
        # hauteur de test : celle-ci emporterait les étiquettes d'axe et le
        # cadre avec elle, qui sortiraient baveux au lieu de rester nets.
        # La hauteur est REMISE au foyer, sans condition : le panneau restaure
        # ses derniers champs d'une session à l'autre, donc une hauteur
        # défocalisée laissée là traînerait dans tous les jobs suivants sans
        # que rien ne le dise (c'est arrivé : une version de l'objectif
        # défocus montait z_work, et la valeur restait collée après coup).
        self.spn_zwork.setValue(core.Z_WORK_MM)
        self.spn_cell_defocus.setValue(r.get("cell_defocus", 0.0))
        self.chk_border.setChecked(r.get("border", True))
        self.lbl_recipe_note.setText("\U0001f4a1 " + r["note"])
        self.lbl_recipe_note.setVisible(True)
        # Objectif jugé à l'œil : on prépare la saisie du ton avec ce qui
        # vient d'être gravé. Surtout la LARGEUR, qui vaut ici le PAS de
        # hachure et non une mesure au pied à coulisse -- pré-remplir vaut
        # mieux qu'avertir.
        ton = getattr(self, "_ton_rapide", None)
        if r.get("ton_balayage") and ton:
            ton["appliquer"]({
                "feed": self.spn_feed_min.value(),
                "z_offset": self.spn_cell_defocus.value(),
                "width": self.spn_hatch_spacing.value(),
                "label": "balayage F{:.0f} pas {:.2f}".format(
                    self.spn_feed_min.value(), self.spn_hatch_spacing.value()),
            })

    def _appliquer_paliers(self, powers, feeds):
        """Fixe (ou libère) les paliers imposés par un objectif.

        Quand ils sont imposés, les champs de plage sont VERROUILLÉS et les
        valeurs réellement gravées affichées : une plage min/max/nombre
        répartit linéairement et ne sait donc pas décrire les colonnes de
        la grille de saisie, qui sont géométriques (200, 400, 800, 1500,
        3000). Laisser les champs modifiables afficherait une plage que le
        job n'utilise pas -- une interface qui ment sur ce qu'elle grave.

        Les champs restent RENSEIGNÉS (min, max, nombre du palier réel)
        pour que les préréglages sauvegardés et la restauration de session
        continuent de fonctionner à l'identique."""
        self._paliers_objectif = (list(powers) if powers else None,
                                  list(feeds) if feeds else None)
        impose = bool(powers or feeds)
        for champ in self._champs_plages:
            champ.setEnabled(not impose)
        if not impose:
            self.lbl_paliers.setVisible(False)
            return
        if powers:
            self.spn_power_min.setValue(min(powers))
            self.spn_power_max.setValue(max(powers))
            self.spn_power_steps.setValue(len(powers))
        if feeds:
            self.spn_feed_min.setValue(min(feeds))
            self.spn_feed_max.setValue(max(feeds))
            self.spn_feed_steps.setValue(len(feeds))

        def _liste(vals):
            return ", ".join("{:g}".format(v) for v in vals)

        morceaux = []
        if powers:
            morceaux.append("Puissances gravées : S{}".format(_liste(powers)))
        if feeds:
            morceaux.append("Vitesses gravées : F{}".format(_liste(feeds)))
        self.lbl_paliers.setText(
            " — ".join(morceaux) + ". Ce sont exactement les lignes et "
            "colonnes de la grille de saisie ② : chaque case gravée aura "
            "une case où être saisie.")
        self.lbl_paliers.setVisible(True)

    def _build_measures_section(self, form):
        """Section ② : saisie INLINE des largeurs brûlées mesurées sur la
        planche/grille (foyer + défocus), qui alimentent l'interpolation
        largeur(S, F). Remplace l'ancien dialogue séparé « Saisir les
        mesures… » -- on grave au-dessus, on mesure ici, juste en dessous."""
        _section(form, "② Entrer les mesures", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "Une fois la planche/grille gravée : mesure la LARGEUR brûlée de "
            "chaque trait au pied à coulisse (1/10 mm) et saisis-la ici. "
            "Laisse « — » pour un trait non mesuré ou vierge. Ces valeurs "
            "servent au bouton « Auto (½ point) » des Hachures et au calage du "
            "remplissage."))

        self.edt_measure_mat = QtWidgets.QComboBox()
        self.edt_measure_mat.setEditable(True)
        self.edt_measure_mat.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.edt_measure_mat.setMinimumContentsLength(14)
        mats = core.burn_width_materials() or core.shade_materials()
        self.edt_measure_mat.addItems(mats)
        self.edt_measure_mat.setCurrentText(mats[0] if mats else "MDF")
        self.edt_measure_mat.setToolTip(
            "Matériau caractérisé : les mesures y sont rangées (et la photo du "
            "résultat ci-dessous). Choisis-en un ou tape un nouveau nom.")
        form.addRow("Matériau mesuré :", self.edt_measure_mat)

        # Grilles de saisie alignées sur les planches (bloc partagé avec
        # l'Assistant matériau) : chaque grille intègre son verrou (coché par
        # défaut) et la neutralisation de la molette.
        self._mesures = _MesuresPlanchesControleur(
            form, self, lambda: self.edt_measure_mat.currentText(),
            on_saved=self._maj_liste_materiaux,
            # Le défocus que ① va graver : ② lui ouvre une grille même si
            # ce niveau n'a encore jamais été mesuré. `getattr` parce que
            # cette section se construit AVANT le champ « Défocus des
            # cellules » -- l'ordre de lecture du panneau est la procédure
            # (① graver, ② mesurer), pas l'ordre des dépendances.
            get_niveau_cible=lambda: getattr(
                getattr(self, "spn_cell_defocus", None), "value", lambda: 0.0)())
        self._mesures.reload()

        # Une grille de test se lit AUSSI à l'œil -- c'est même son usage
        # premier (« on lit la meilleure case »). Le jugement se saisit donc
        # ici, dans le même ②, au lieu d'un aller-retour vers le Nuancier
        # avec les valeurs retenues de mémoire. L'objectif « Noirceur —
        # bande en balayage » y pré-remplit vitesse, défocus et pas.
        self._ton_rapide = _make_shade_quick_add(
            form, lambda: self.edt_measure_mat.currentText(),
            titre="Noirceur jugée à l'œil (nuancier)",
            on_added=self._maj_liste_materiaux)
        self.edt_measure_mat.currentIndexChanged.connect(
            lambda _i: self._ton_rapide["reload"]())
        self.edt_measure_mat.lineEdit().editingFinished.connect(
            lambda: self._ton_rapide["reload"]())
        self._ton_rapide["reload"]()

    def _reload_measures(self):
        self._mesures.reload()

    def _reload_measures_and_photo(self):
        self._reload_measures()
        if getattr(self, "_photo", None):
            self._photo["reload"]()

    def _maj_liste_materiaux(self):
        """Après un enregistrement : rafraîchit la liste des matériaux du
        sélecteur (un nouveau nom vient peut-être d'apparaître)."""
        cur = self.edt_measure_mat.currentText()
        self.edt_measure_mat.blockSignals(True)
        self.edt_measure_mat.clear()
        self.edt_measure_mat.addItems(core.burn_width_materials() or core.shade_materials())
        self.edt_measure_mat.setCurrentText(cur)
        self.edt_measure_mat.blockSignals(False)

    def _on_generer(self):
        """Crée les cellules dans le document, génère le G-code de la grille
        et propose l'enregistrement -- le panneau RESTE ouvert (saisie des
        largeurs ② après la gravure)."""
        if self.spn_power_max.value() < self.spn_power_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Puissance max doit être >= puissance min.")
            return
        if self.spn_feed_max.value() < self.spn_feed_min.value():
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Vitesse max doit être >= vitesse min.")
            return
        _save_last_values("testgrid", self._last_fields)

        mode, fill_type, cells, cell_z_offset = self._build_cells()
        if cells is None:
            return

        objs, err = core.create_test_grid_object(mode, cells)
        if err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", err)
            return

        power_labels, feed_labels, label_edges = self._build_label_edges(cells)
        label_obj, lbl_err = core.create_test_grid_label_object(power_labels, feed_labels)
        if lbl_err:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", lbl_err)
            return

        core.print_test_grid_legend(mode, cells, self.spn_power_steps.value(), self.spn_feed_steps.value())

        gcode = core.generate_gcode_test_grid(
            cells, self.spn_zwork.value(),
            label_edges=label_edges if self.chk_labels.isChecked() else None,
            cell_z_offset=cell_z_offset,
            use_proximity=self.chk_proximity.isChecked(),
            line_style=self._line_style(), **self._border_kwargs()
        )

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return

        FreeCAD.Console.PrintMessage("Succès : {} cellules créées.\n".format(len(objs)))
        if not _write_gcode_with_dialog(self.form, gcode, "/tmp/grille_test.ngc"):
            # Sauvegarde abandonnée : les objets tout juste créés sont
            # retirés du document -- re-cliquer « Générer » regénère tout,
            # les garder produirait des cellules en double.
            doc = FreeCAD.ActiveDocument
            for obj in objs + ([label_obj] if label_obj is not None else []):
                doc.removeObject(obj.Name)
            doc.recompute()

    def accept(self):
        # OK = mémoriser les réglages et fermer (génération : bouton de ①).
        _save_last_values("testgrid", self._last_fields)
        return True

    def reject(self):
        return True


# ==========================================================================
# MODE : MARQUAGE SUR SURFACE COURBE
# ==========================================================================
class TaskPanelCurved:
    def __init__(self, selection):
        self.selection = selection
        # _source_edges = la sélection brute (le contour) ; _edges = ce qu'on grave.
        self._source_edges, self._reference_shape = self._get_edges()
        self._edges = self._source_edges
        # Sonde Z gardée pour toute la durée de vie du panneau : la surface
        # de référence ne change pas pendant que le panneau est ouvert, donc
        # les raycasts d'un premier calcul (ouverture, aperçu durée...)
        # profitent aux suivants au lieu d'être refaits à chaque fois.
        self._probe = core.make_ray_probe(self._reference_shape) if self._reference_shape is not None else None
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldsStayAtSizeHint)
        _panel_header(form, "curved.svg", "Marquage de motif (plat ou courbe)")
        self.btn_resel = _reselect_button(form, self._on_recapture_selection,
                                          lambda: self.selection)
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
               "le motif projeté (Motif_Projete) ET le modèle 3D d'origine, "
               "les deux en même temps.",
               "Le modèle 3D permet une sonde exacte du relief pendant le "
               "marquage (sans lui, le Z n'est qu'interpolé entre les points "
               "déjà projetés). Cinq styles de trait : plein, tirets, "
               "pointillé, vague défocus (le Z ondule, trait qui varie en "
               "largeur), et défocus point élargi (noircir un remplissage en "
               "un passage) -- tous suivent le relief. Le Z de travail et la "
               "marge de transit viennent des Préférences.")

        _diagram(form, "diag_marquage.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Sélectionne le <b>motif</b>. Pièce PLATE&nbsp;: le motif "
            "2D seul. Surface COURBE&nbsp;: le motif projeté (<code>Motif_Projete"
            "</code>) <b>ET</b> le modèle 3D d'origine, les deux ensemble.",
            "<b>2.</b> Pose le <b>zéro machine</b>&nbsp;: X/Y au coin de "
            "référence, Z sur le point haut de la surface. Avec le modèle 3D le "
            "relief est sondé exactement&nbsp;; sans lui le Z est seulement "
            "interpolé entre les points projetés.",
            "<b>3. Matériau / ton</b>&nbsp;: applique un préréglage, ou un ton "
            "du <b>Nuancier</b> via «&nbsp;Calculer le réglage (interpolé)&nbsp;»,"
            " sinon règle puissance/vitesse à la main.",
            "<b>4. Style de trait</b>&nbsp;: plein, tirets, pointillé, vague "
            "défocus (trait qui ondule en largeur) ou point élargi (noircit un "
            "remplissage en un passage). Tous suivent le relief.",
            "<b>5. Vérifie</b>&nbsp;: «&nbsp;Aperçu photo&nbsp;» (rendu réaliste)"
            " et «&nbsp;Aperçu du trajet&nbsp;». «&nbsp;Mire des styles&nbsp;» "
            "compare les styles sur une chute.",
            "<b>6. Génère</b>&nbsp;: «&nbsp;Générer et sauvegarder le "
            "G-code…&nbsp;» (ou «&nbsp;Ajouter au job combiné&nbsp;»). Relis le "
            "<code>G0&nbsp;Z…</code> en tête du .ngc avant de lancer.",
        ])

        _section(form, "Préréglage matériau", "sect_preset.svg")
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/Z\n"
            "travail/marge) -- en choisir un remplit automatiquement les\n"
            "champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder")
        _btn_icon(self.btn_save_preset, "sect_preset.svg")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer")
        self.btn_delete_preset.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        _mat_row = QtWidgets.QWidget()
        _mat_h = QtWidgets.QHBoxLayout(_mat_row)
        _mat_h.setContentsMargins(0, 0, 0, 0)
        _mat_h.addWidget(self.btn_save_preset)
        _mat_h.addWidget(self.btn_delete_preset)
        form.addRow(_mat_row)

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

        # --- Ton sur mesure : largeur + noirceur choisies, vitesse calculée
        # par interpolation ENTRE les tons mesurés du nuancier (courbe
        # noirceur -> fluence P/(d·v), tons en défocus uniquement).
        self.spn_custom_width = QtWidgets.QDoubleSpinBox()
        self.spn_custom_width.setRange(0.05, 30.0)
        self.spn_custom_width.setDecimals(2)
        self.spn_custom_width.setValue(1.0)
        self.spn_custom_width.setSuffix(" mm")
        self.spn_custom_width.setToolTip(
            "Largeur de trait voulue -- pilote le DÉFOCUS via la calibration\n"
            "du point (comme le style Défocus).")
        form.addRow("Sur mesure -- largeur :", self.spn_custom_width)

        self.spn_custom_dark = QtWidgets.QDoubleSpinBox()
        self.spn_custom_dark.setRange(0, 100)
        self.spn_custom_dark.setDecimals(0)
        self.spn_custom_dark.setValue(60)
        self.spn_custom_dark.setSuffix(" %")
        self.spn_custom_dark.setToolTip(
            "Noirceur visée -- pilote la VITESSE, interpolée entre les tons\n"
            "mesurés du nuancier (bornée aux noirceurs mesurées, pas\n"
            "d'extrapolation).")
        form.addRow("Sur mesure -- noirceur :", self.spn_custom_dark)

        self.btn_custom_shade = QtWidgets.QPushButton("Calculer le réglage (interpolé)")
        self.btn_custom_shade.setToolTip(
            "À la puissance S courante (champ ci-dessous), calcule la vitesse\n"
            "qui donne la noirceur visée pour cette largeur, par interpolation\n"
            "entre les tons MESURÉS du matériau sélectionné ci-dessus --\n"
            "et règle style Défocus + largeur + vitesse. Interpolé = à\n"
            "valider sur une chute (les tons mesurés restent la référence).")
        self.btn_custom_shade.clicked.connect(self._on_custom_shade)
        form.addRow(self.btn_custom_shade)

        self.lbl_custom_shade = _WrapLabel("")
        form.addRow(self.lbl_custom_shade)

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
        self.spn_surface_offset = _make_surface_offset_row(form)

        _section(form, "Style de trait", "sect_options.svg")
        self.combo_style = QtWidgets.QComboBox()
        self.combo_style.addItems(
            ["Trait plein", "Tirets", "Pointillé", "Vague défocus", "Défocus (point élargi)",
             "Dégradé de largeur (sur la pièce)",
             "Dégradé de largeur (le long du tracé)",
             "Dégradé de puissance (le long du tracé)"])
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
            "mais appliqué au motif projeté).\n"
            "\n"
            "Les deux DÉGRADÉS ne font pas la même chose malgré leurs noms :\n"
            "  sur la pièce : chaque trait s'épaissit selon sa POSITION\n"
            "    (direction réglable). Pensé pour des HACHURES : la zone\n"
            "    couvre de plus en plus, donc elle s'ombre d'un bord à\n"
            "    l'autre. Sur un trait SEUL, ça donne juste un trait qui\n"
            "    s'élargit.\n"
            "  le long du tracé : UN trait dont la largeur suit son\n"
            "    PARCOURS, du début à la fin. Un fuseau.\n"
            "\n"
            "Ces deux-là font varier la LARGEUR, à puissance CONSTANTE. Un\n"
            "trait plus large reçoit moins d'énergie par mm² : il n'est pas\n"
            "plus noir, il est plus large -- et souvent plus pâle.\n"
            "\n"
            "  Dégradé de PUISSANCE : l'inverse. Le bec ne bouge pas, donc\n"
            "    la largeur non plus ; c'est la TEINTE qui va du clair au\n"
            "    foncé le long du tracé. C'est celui-là qu'il faut pour un\n"
            "    vrai dégradé de gris sur un trait.\n"
            "\n"
            "Tous les styles suivent le relief comme le trait plein.")
        form.addRow("Style de trait :", self.combo_style)

        # Un petit schéma par style, empilés ici : un seul est visible à la
        # fois (_update_style_ui). Le dessin dit d'un coup d'oeil ce qu'un
        # paragraphe explique mal -- en particulier la différence entre les
        # deux « dégradés », dont les noms se ressemblent alors que l'un
        # suit la POSITION dans l'espace et l'autre le PARCOURS du trait.
        # L'ordre suit celui du menu, index par index.
        self._diagrammes_style = [
            _diagram(form, "diag_style_plein.svg", 260, 78),
            _diagram(form, "diag_style_tirets.svg", 260, 78),
            _diagram(form, "diag_style_pointille.svg", 260, 78),
            _diagram(form, "diag_style_vague.svg", 260, 78),
            _diagram(form, "diag_style_defocus.svg", 260, 78),
            _diagram(form, "diag_style_degrade_dir.svg", 260, 78),
            _diagram(form, "diag_fuseau.svg", 260, 78),
            _diagram(form, "diag_style_degrade_puissance.svg", 260, 78),
        ]

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

        self.spn_deg_angle = QtWidgets.QDoubleSpinBox()
        self.spn_deg_angle.setRange(0, 360); self.spn_deg_angle.setValue(0.0)
        self.spn_deg_angle.setSuffix(" °")
        self.spn_deg_angle.setToolTip("Direction du dégradé (0° = de gauche à droite).")
        form.addRow("Dégradé -- direction :", self.spn_deg_angle)
        self.spn_deg_w0 = QtWidgets.QDoubleSpinBox()
        self.spn_deg_w0.setRange(0.05, 30.0); self.spn_deg_w0.setDecimals(2)
        self.spn_deg_w0.setValue(0.3); self.spn_deg_w0.setSuffix(" mm")
        self.spn_deg_w0.setToolTip("Largeur du trait au DÉBUT du dégradé (fin/net = point au foyer).")
        form.addRow("Dégradé -- largeur début :", self.spn_deg_w0)
        self.spn_deg_w1 = QtWidgets.QDoubleSpinBox()
        self.spn_deg_w1.setRange(0.05, 30.0); self.spn_deg_w1.setDecimals(2)
        self.spn_deg_w1.setValue(2.0); self.spn_deg_w1.setSuffix(" mm")
        self.spn_deg_w1.setToolTip("Largeur du trait à la FIN du dégradé (large/doux = défocalisé).")
        form.addRow("Dégradé -- largeur fin :", self.spn_deg_w1)

        # RAMPE DE PUISSANCE SUPERPOSÉE aux deux dégradés de LARGEUR.
        #
        # Le 31/07/2026, la spirale gravée à S1000 constant de 0,3 à 4 mm
        # est sortie marbrée au bout large (fluence effondrée d'un facteur
        # 13) et carbonisée au bout fin, au foyer. Demande de Christophe :
        # « corréler la puissance de début à celle de fin afin que j'aie du
        # noir mais pas carbonisé ». Décochée = comportement d'avant, au
        # bit près.
        self.chk_deg_s = QtWidgets.QCheckBox(
            "Faire varier aussi la puissance le long du dégradé")
        self.chk_deg_s.setToolTip(
            "Sans ça, S reste CONSTANT pendant que la largeur varie, donc\n"
            "la fluence évolue comme 1/largeur : le trait large sort pâle\n"
            "et marbré, le trait fin sort creusé et brûlé.\n"
            "\n"
            "Coché, la puissance rampe le long du même parcours que la\n"
            "largeur. Le bouton « Compenser la fluence » calcule la valeur\n"
            "qui donnerait une teinte constante.")
        form.addRow("", self.chk_deg_s)

        # Le dégradé de PUISSANCE : la teinte va du clair au foncé le long
        # du tracé, à largeur de trait CONSTANTE. C'est ce que les deux
        # « dégradés de largeur » ne savent pas faire -- eux montent le bec
        # à puissance constante, donc le trait s'élargit et pâlit.
        self.spn_deg_s0 = QtWidgets.QDoubleSpinBox()
        self.spn_deg_s0.setRange(0.0, core.S_MAX)
        self.spn_deg_s0.setDecimals(0)
        self.spn_deg_s0.setSingleStep(25.0)
        self.spn_deg_s0.setValue(150.0)
        self.spn_deg_s0.setToolTip(
            "Puissance au DÉBUT du tracé. Basse = trait très clair.\n"
            "0 = le trait ne commence à marquer qu'un peu plus loin.")
        form.addRow("Dégradé -- puissance début :", self.spn_deg_s0)

        self.spn_deg_s1 = QtWidgets.QDoubleSpinBox()
        self.spn_deg_s1.setRange(0.0, core.S_MAX)
        self.spn_deg_s1.setDecimals(0)
        self.spn_deg_s1.setSingleStep(25.0)
        self.spn_deg_s1.setValue(core.S_MAX)
        self.spn_deg_s1.setToolTip(
            "Puissance à la FIN du tracé. Haute = trait foncé.\n"
            "\n"
            "Le BEC ne bouge pas : Z reste constant du début à la fin,\n"
            "et le point optique aussi. Le trait s'élargit quand même un\n"
            "peu, parce qu'à basse puissance seul le coeur du faisceau\n"
            "dépasse le seuil de brûlure du bois -- mesuré sur hêtre au\n"
            "foyer à F800 : 0,10 mm à S200 contre 0,30 à S1000.\n"
            "\n"
            "C'est donc d'abord un dégradé de TEINTE, avec un trait qui\n"
            "s'épaissit en même temps -- rien à voir avec les dégradés de\n"
            "largeur, qui montent le bec et PÂLISSENT en s'élargissant.")
        form.addRow("Dégradé -- puissance fin :", self.spn_deg_s1)

        # Le bouton donne le CHIFFRE plutôt qu'un conseil : S proportionnel
        # au diamètre du point (`core.puissance_fluence_largeur`, le même
        # modèle que le style vague -- une seule formule pour une seule
        # grandeur). Le libellé dit ensuite franchement quand la valeur
        # tombe sous la plus basse puissance MESURÉE : là, plus personne ne
        # sait si le trait marque encore.
        self.btn_deg_fluence = QtWidgets.QPushButton("Compenser la fluence")
        self.btn_deg_fluence.setToolTip(
            "Calcule la puissance de fin qui donnerait la MÊME teinte\n"
            "qu'au début, en suivant la largeur du trait.")
        self.btn_deg_fluence.clicked.connect(self._on_deg_fluence)
        self.lbl_deg_fluence = _WrapLabel("")
        form.addRow("", self.btn_deg_fluence)
        form.addRow("", self.lbl_deg_fluence)

        # Sur une BOUCLE FERMÉE, une rampe simple ramène la largeur de fin
        # juste à côté de celle de départ : le raccord se voit. L'aller-
        # retour atteint la largeur de fin à MI-PARCOURS et referme sur la
        # largeur de départ. Réglable plutôt qu'imposé : les deux rendus
        # se défendent, et c'est le dessin qui tranche.
        self.combo_deg_boucle = QtWidgets.QComboBox()
        self.combo_deg_boucle.addItem("Marche visible à la fermeture", "marche")
        self.combo_deg_boucle.addItem("Aller-retour (fermeture invisible)", "aller_retour")
        self.combo_deg_boucle.setToolTip(
            "Ce que devient la rampe sur un contour FERMÉ (cercle, boucle).\n"
            "\n"
            "Marche visible : la largeur va du début à la fin le long du\n"
            "  tracé, donc en revenant au point de départ elle saute de la\n"
            "  largeur de fin à celle de début. Littéral et prévisible.\n"
            "\n"
            "Aller-retour : la largeur de fin est atteinte à MI-PARCOURS,\n"
            "  puis redescend ; la boucle se referme sans aucun raccord.\n"
            "  « Largeur à la fin » désigne alors le milieu du contour.\n"
            "\n"
            "Sans effet sur un trait OUVERT : l'aller-retour y ramènerait\n"
            "la largeur de départ, ce qui contredirait « largeur à la fin ».")
        form.addRow("Boucle fermée :", self.combo_deg_boucle)

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
            # Le nuancier gagne toujours sur la compensation de fluence --
            # en premier, avant de lire fluence["chk"] plus bas.
            _appliquer_priorite_nuancier(self._shade_picker, self._fluence)
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
            for w in (self.spn_deg_w0, self.spn_deg_w1):
                _set_row_visible(form, w, idx in (5, 6))
            # La case n'a de sens que sur les deux dégradés de LARGEUR : le
            # dégradé de PUISSANCE rampe S par construction.
            _set_row_visible(form, self.chk_deg_s, idx in (5, 6))
            rampe_s = idx == 7 or (idx in (5, 6) and self.chk_deg_s.isChecked())
            for w in (self.spn_deg_s0, self.spn_deg_s1):
                _set_row_visible(form, w, rampe_s)
            for w in (self.btn_deg_fluence, self.lbl_deg_fluence):
                _set_row_visible(form, w, idx in (5, 6) and self.chk_deg_s.isChecked())
            _set_row_visible(form, self.spn_deg_angle, idx == 5)
            # Le choix de fermeture vaut pour les DEUX rampes le long du
            # tracé : elles partagent `rampe_trace_dz`.
            _set_row_visible(form, self.combo_deg_boucle, idx in (6, 7))
            # La puissance globale n'a plus de sens quand elle est rampée.
            self.spn_power.setEnabled(not rampe_s)
            for i, diag in enumerate(self._diagrammes_style):
                # _diagram renvoie None si le rendu SVG a échoué : ne jamais
                # planter le panneau pour un dessin manquant.
                if diag is not None:
                    _set_row_visible(form, diag, i == idx)
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
                self.spn_power.setEnabled(
                    not rampe_s and not self._fluence["chk"].isChecked())
            else:
                self.lbl_style_info.setVisible(False)
                # `not rampe_s` et pas `True` : ces deux lignes s'exécutent
                # APRÈS le grisage décidé plus haut et l'écrasaient. Le
                # dégradé de puissance livré en v2.12.0 laissait donc son
                # champ « Puissance » actif alors qu'il ne sert plus à rien
                # -- deux mécanismes sur le même widget, le dernier gagne.
                self.spn_power.setEnabled(not rampe_s)

        self._update_style_ui = _update_style_ui
        self.combo_style.currentIndexChanged.connect(lambda _i: _update_style_ui())
        # Changer de matériau change qui a un nuancier : le bloc fluence
        # doit se griser/dégriser tout de suite, pas au prochain champ modifié.
        self._shade_picker["mat"].currentIndexChanged.connect(lambda _i: _update_style_ui())
        for w in (self.spn_wave_width, self.spn_wave_period, self.spn_feed, self.spn_spot_width,
                  self.spn_power, self._fluence["ref_power"], self._fluence["ref_feed"],
                  self._fluence["ref_spot"]):
            w.valueChanged.connect(lambda _v: _update_style_ui())
        self._fluence["chk"].toggled.connect(lambda _v: _update_style_ui())
        self.chk_deg_s.toggled.connect(lambda _v: _update_style_ui())

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))

        self.chk_origin_bbox = QtWidgets.QCheckBox(
            "Recadrer au zéro pièce (coin bas-gauche à 0,0)")
        self.chk_origin_bbox.setChecked(bool(getattr(core, "GCODE_ORIGIN_BBOX", True)))
        self.chk_origin_bbox.setToolTip(
            "Même réglage que Préférences > Machine / G-code -- rappelé ici\n"
            "juste avant de générer, pour ne pas l'oublier. Décoche pour un\n"
            "marquage sur une pièce déjà positionnée précisément (fraisage\n"
            "puis gravure sur la MÊME pièce sans reprendre le zéro) : sinon\n"
            "ce job est recadré tout seul et se retrouve décalé par rapport\n"
            "à ce qui a déjà été usiné.")
        self.chk_origin_bbox.toggled.connect(
            lambda on: core.save_settings({"gcode_origin_bbox": on}))
        form.addRow(self.chk_origin_bbox)

        self.btn_save_gcode = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_save_gcode, "sect_gcode.svg")
        self.btn_save_gcode.setToolTip(
            "Génère le G-code avec les réglages actuels et propose le\n"
            "fichier de sauvegarde. Le bouton OK, lui, se contente de\n"
            "SAUVEGARDER LES RÉGLAGES (sur la forme + objet Job) et ferme\n"
            "le panneau sans générer.")
        self.btn_save_gcode.clicked.connect(self._on_save_gcode)
        form.addRow(self.btn_save_gcode)

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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Aperçu du trajet (vue 3D) : gris fin = transit laser éteint (G0),\n"
            "rouge épais = gravure laser allumé (G1). Purement visuel.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        self.btn_photo_preview = QtWidgets.QPushButton()
        self.btn_photo_preview.setToolTip(
            "Aperçu photo (rendu réaliste) : chaque trait à sa largeur brûlée\n"
            "et à sa teinte -- la noirceur MESURÉE du nuancier du matériau\n"
            "sélectionné ci-dessus quand elle existe, sinon un modèle\n"
            "théorique.")
        self.btn_photo_preview.clicked.connect(self._on_photo_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg"),
                            (self.btn_photo_preview, "sect_photo.svg")])
        _combined_add_button(form, self._on_add_to_combined)

        self.btn_style_sampler = QtWidgets.QPushButton("Mire des styles (fichier séparé)")
        self.btn_style_sampler.setToolTip(
            "Grave le MÊME trait droit avec chacun des 6 styles (bandes\n"
            "étiquetées 1-6 : plein, tirets, pointillé, vague, défocus,\n"
            "dégradé), aux puissance/vitesse et réglages de style courants\n"
            "du panneau -- pour comparer les rendus sur une chute du\n"
            "matériau et choisir un style en connaissance de cause.")
        self.btn_style_sampler.clicked.connect(self._on_style_sampler)
        form.addRow(self.btn_style_sampler)

        self.btn_style_showcase = QtWidgets.QPushButton(
            "Planche des styles (exemples numérotés)")
        self.btn_style_showcase.setToolTip(
            "Grave un MOT exemple dans chaque style (plein, tirets, pointillé,\n"
            "vague, défocus point élargi à 1/2/3 mm, dégradé), chaque exemple\n"
            "NUMÉROTÉ et légendé au foyer -- une planche de référence à garder\n"
            "après calibration : on voit le rendu réel sur de vraies lettres,\n"
            "pas sur un simple trait. Puissance/vitesse et réglages de style\n"
            "courants du panneau.")
        self.btn_style_showcase.clicked.connect(self._on_style_showcase)
        form.addRow(self.btn_style_showcase)

        self._last_fields = {
            "power": self.spn_power, "feed": self.spn_feed, "surface_offset": self.spn_surface_offset,
            "style": self.combo_style, "dash_len": self.spn_dash_len,
            "gap_len": self.spn_gap_len, "dot_spacing": self.spn_dot_spacing,
            "dot_dwell_ms": self.spn_dot_dwell, "wave_period": self.spn_wave_period,
            "wave_width": self.spn_wave_width, "spot_width": self.spn_spot_width,
            # Les cinq champs du dégradé manquaient depuis leur création :
            # un fuseau réglé se perdait à la fermeture du panneau, et un
            # préréglage ne le rapportait pas non plus (cf. plus bas).
            "deg_angle": self.spn_deg_angle, "deg_w0": self.spn_deg_w0,
            "deg_w1": self.spn_deg_w1, "deg_boucle": self.combo_deg_boucle,
            "deg_s0": self.spn_deg_s0, "deg_s1": self.spn_deg_s1,
            "deg_s_rampe": self.chk_deg_s,
            "fluence_on": self._fluence["chk"], "ref_power": self._fluence["ref_power"],
            "ref_feed": self._fluence["ref_feed"], "ref_spot": self._fluence["ref_spot"],
        }
        _restore_last_values("curved", self._last_fields, selection=self.selection)

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

    def _on_style_sampler(self):
        sk = self._style_kwargs()["style_params"]
        gcode = core.generate_gcode_style_sampler(
            power=self.spn_power.value(), feed=self.spn_feed.value(),
            z_focus=core.Z_WORK_MM, style_params=sk,
            spot_width=self.spn_spot_width.value())
        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Aucun G-code généré pour la mire des styles.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/mire_styles.ngc")

    def _on_style_showcase(self):
        text, ok = QtWidgets.QInputDialog.getText(
            self.form, "Planche des styles",
            "Mot exemple à graver dans chaque style :", text="Laser")
        if not ok:
            return
        sk = self._style_kwargs()["style_params"]
        gcode = core.generate_gcode_style_showcase(
            power=self.spn_power.value(), feed=self.spn_feed.value(),
            z_focus=core.Z_WORK_MM, sample_text=text or "Laser",
            style_params=sk)
        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur",
                "Aucun G-code généré pour la planche des styles.")
            return
        _write_gcode_with_dialog(self.form, gcode, "/tmp/planche_styles.ngc")

    def _on_recapture_selection(self):
        """Reprend la sélection courante (vue 3D / arbre) : le panneau ne la
        capture qu'à l'ouverture, or on sélectionne souvent après coup."""
        self.selection = Gui.Selection.getSelectionEx()
        self._source_edges, self._reference_shape = self._get_edges()
        self._probe = (core.make_ray_probe(self._reference_shape)
                       if self._reference_shape is not None else None)
        if not self._source_edges:
            self._edges = self._source_edges
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Aucun segment dans la sélection courante. Sélectionne le "
                "motif (ex. l'objet Hachures) dans la vue ou l'arbre, puis "
                "reclique ce bouton.")
        else:
            self._edges = self._source_edges
            FreeCAD.Console.PrintMessage(
                "Sélection reprise : {} segment(s).\n".format(len(self._source_edges)))
        self._update_duration_preview()

    def _on_custom_shade(self):
        material = self._shade_picker["mat"].currentData()
        if not material:
            QtWidgets.QMessageBox.information(
                self.form, "Ton sur mesure",
                "Le nuancier est vide : mesure d'abord quelques tons (mode "
                "Nuancier) -- l'interpolation se fait entre des tons MESURÉS.")
            return
        power = self.spn_power.value()
        if power <= 0:
            power = core.S_MAX
            self.spn_power.setValue(power)
        width = self.spn_custom_width.value()
        res = core.feed_for_custom_shade(
            material, self.spn_custom_dark.value(), width, power)
        if res is None:
            QtWidgets.QMessageBox.information(
                self.form, "Ton sur mesure",
                "Pas assez de tons exploitables sur « {} » : il faut au moins "
                "2 tons EN DÉFOCUS (largeur, vitesse et puissance renseignées) "
                "pour interpoler. Pour en obtenir : mode Rampe puissance/"
                "vitesse, coche « Rampe Z », mesure la largeur au pied à "
                "coulisse sur la pièce gravée, puis « + Ajouter ce ton » dans "
                "ce même panneau.".format(material))
            return
        feed, fluence, clamped = res
        self.combo_style.setCurrentIndex(4)      # style Défocus (point élargi)
        self.spn_spot_width.setValue(width)
        self.spn_feed.setValue(feed)
        defocus = core.defocus_for_spot_diameter(
            width, core.SPOT_FOCUS_MM, core.calibrated_half_angle()) or 0.0
        txt = ("Interpolé : style Défocus, largeur {:.2f} mm (défocus "
               "{:.1f} mm), S{:.0f}, F{:.0f} -> noirceur visée {:.0f}%".format(
                   width, defocus, power, feed, clamped))
        if abs(clamped - self.spn_custom_dark.value()) > 0.5:
            txt += " (borné : noirceur mesurée de {:.0f}% max/min sur ce matériau)".format(clamped)
        if feed > 6000:
            txt += " -- vitesse très élevée : baisse la puissance S ou vise plus foncé."
        elif feed < 30:
            txt += " -- vitesse très basse : trait large + foncé au-delà du raisonnable à cette S."
        txt += " À valider sur une chute."
        self.lbl_custom_shade.setText(txt)
        self._update_style_ui()
        self._update_duration_preview()

    def _z_focus(self):
        """Z de travail effectif : foyer des Préférences, remonté du
        défocus si le style « Défocus (point élargi) » est choisi. Le
        défocus est calculé depuis la LARGEUR DE POINT voulue via la
        calibration (le point élargi noircit en un passage)."""
        base = core.Z_WORK_MM + self.spn_surface_offset.value()
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

    def _on_deg_fluence(self):
        """Remplit la puissance de fin avec celle qui donnerait la MÊME
        teinte qu'au début, puis dit franchement ce que ça vaut.

        Modèle : fluence = P/(largeur.v), donc S proportionnel à la largeur
        (`core.puissance_fluence_largeur`, le même que le style vague). Le
        cas de la spirale du 31/07/2026 -- 0,3 -> 4 mm -- demande S75 au
        bout fin, sous la plus basse puissance jamais MESURÉE sur ce bois
        (S200 sur hêtre à F800). En dessous, la table de largeurs ne dit
        plus rien : le trait peut ne pas marquer du tout. On donne le
        chiffre ET la limite, le bois tranchera."""
        w0, w1 = self.spn_deg_w0.value(), self.spn_deg_w1.value()
        s0 = self.spn_deg_s0.value()
        s1 = core.puissance_fluence_largeur(s0, w0, w1)
        if s1 is None:
            self.lbl_deg_fluence.setText(
                "Largeurs inexploitables : impossible de calculer la "
                "compensation.")
            return
        s1 = max(0.0, min(core.S_MAX, s1))
        self.spn_deg_s1.setValue(round(s1 / 5.0) * 5.0)

        txt = ("Teinte constante : S{:.0f} à {:.2f} mm -> S{:.0f} à {:.2f} mm "
               "(S suit la largeur).".format(s0, w0, s1, w1))
        mat = (self._shade_picker["mat"].currentData()
               or self._shade_picker["mat"].currentText())
        table = core.burn_width_power_table(mat, self.spn_feed.value()) if mat else None
        plancher = min(p for p, _w in table) if table else None
        if plancher is not None and s1 < plancher:
            txt += (" ATTENTION : S{:.0f} est SOUS la plus basse puissance "
                    "mesurée sur {} à F{:.0f} (S{:.0f}) -- en dessous, on ne "
                    "sait pas si le trait marque encore. Réduis l'écart de "
                    "largeurs, ou accepte une teinte qui varie.".format(
                        s1, mat, self.spn_feed.value(), plancher))
        elif s1 >= core.S_MAX:
            txt += (" Borné à S{:.0f} : la compensation exacte demanderait "
                    "davantage que ce que la machine peut donner.".format(core.S_MAX))
        self.lbl_deg_fluence.setText(txt)

    def _strokes_degrade(self, idx, power, feed, _tone_ignore=None):
        """Traits de l'aperçu pour les deux styles à largeur VARIABLE.

        Un `stroke` porte UNE largeur : pour montrer un fuseau il faut donc
        découper le tracé et donner à chaque morceau la largeur qu'il aura
        vraiment. Les dz viennent des mêmes fonctions que le générateur
        (`rampe_direction_dz` / `rampe_trace_dz`), et la largeur de la même
        `burn_width_defocus_scaled` que le reste de l'aperçu : l'image ne
        peut donc pas raconter autre chose que le G-code.

        On chaîne les arêtes comme le générateur, parce que la rampe « le
        long du tracé » court sur une CHAÎNE et non sur une arête isolée.
        """
        sp = self._style_kwargs()["style_params"]
        chains = core.chain_edges(self._edges)
        if not chains:
            return []
        half = core.calibrated_half_angle()
        mat_nuancier = (self._shade_picker["mat"].currentData()
                        or self._shade_picker["mat"].currentText())
        dz_dir = (core.rampe_direction_dz(
            chains, sp.get("deg_angle", 0.0),
            sp.get("deg_z_min", 0.0), sp.get("deg_z_max", 0.0))
            if idx == 5 else None)
        # Même fonction que le générateur pour la rampe SPATIALE de
        # puissance : l'aperçu ne peut pas inventer une autre rampe.
        dz_dir_s = (core.rampe_direction_dz(
            chains, sp.get("deg_angle", 0.0),
            sp.get("deg_s_debut", power), sp.get("deg_s_fin", power))
            if idx == 5 and sp.get("deg_s_rampe") else None)

        cache = {}

        def largeur(dz, s=None):
            # Largeur BRÛLÉE mesurée si on l'a, sinon le point optique.
            # `s` : puissance LOCALE quand une rampe de puissance est
            # superposée au dégradé de largeur -- elle change la largeur
            # brûlée autant que la teinte, les deux doivent la voir.
            #
            # LE MATÉRIAU EST OBLIGATOIRE. Sans lui, `_burn_width_material`
            # ne devine que si UN SEUL matériau est mesuré ; dès qu'il y en
            # a deux (hêtre + MDF ici) il renvoie None, `burn_width_...`
            # aussi, et l'aperçu retombait EN SILENCE sur le point optique
            # -- 0,30 mm partout au foyer là où le bois brûle 0,10 à S200.
            # Le repli existe pour un matériau non mesuré, pas pour masquer
            # un argument oublié. Même défaut, même correctif que Gravure
            # remplie en v1.80.0.
            return (core.burn_width_defocus_scaled(
                        power if s is None else s, feed, dz, mat_nuancier)
                    or core.spot_diameter_at_defocus(
                        dz, core.SPOT_FOCUS_MM, half)
                    or core.SPOT_FOCUS_MM)

        # « Une mesure bornée n'est pas une mesure » : `darkness_at` borne la
        # vitesse à la plage réellement mesurée et rend la valeur du bord,
        # EN SILENCE. Hors de cette plage on repasse au modèle -- même garde
        # que l'aperçu photo, pour la même raison.
        #
        # Et la garde se fait AU DÉFOCUS COURANT, pas une fois pour toutes :
        # sur ce hêtre la plage mesurée vaut F400-6000 au foyer mais
        # F1000-4000 à défocus 36. Un trait qui rampe du foyer au défocus
        # traverse donc les deux, et une garde prise au foyer laisserait
        # passer un F400 qui n'a jamais été mesuré là-haut.
        def _mesure_utilisable(dz):
            p = core.shade_feed_range(mat_nuancier, dz)
            return p is not None and p[0] - 1e-6 <= feed <= p[1] + 1e-6

        def teinte_a(dz, w, s=None):
            """La teinte VARIE avec le défocus, elle aussi.

            L'aperçu peignait tous les morceaux d'une même teinte, calculée
            une fois sur la largeur moyenne. Or à puissance CONSTANTE, un
            trait deux fois plus large reçoit deux fois moins d'énergie par
            unité de surface : il est plus large ET PLUS PÂLE. Mesuré sur
            un 0,3 -> 3 mm : fluence 8,00 au départ contre 0,71 à l'arrivée,
            soit 11x moins. Peindre le bout large aussi noir que le fin
            était donc un mensonge, et il cachait justement ce qui surprend
            dans ce style (signalé le 31/07/2026).

            Mémoïsé sur le dz arrondi : `_tone_measured` relit la config,
            et un appel par segment coûterait aussi cher qu'une lecture de
            config par pixel (même piège que l'aperçu photo).
            """
            pw = power if s is None else s
            cle = (round(dz, 1), round(pw / 5.0) * 5)
            if cle not in cache:
                ton = (_tone_measured(mat_nuancier, pw, feed, dz)
                       if _mesure_utilisable(dz) else None)
                if ton is None:
                    ton = _tone_burn(pw, feed, w)
                cache[cle] = max(0.0, min(1.0, ton))
            return cache[cle]

        # Dégradé de PUISSANCE : l'inverse des deux autres. La largeur ne
        # bouge pas (le bec reste à sa hauteur) et c'est la TEINTE qui
        # rampe. On peint donc une largeur unique et une teinte par
        # morceau, calculée à la puissance de ce morceau.
        if idx == 7:
            cache_s = {}

            def largeur_s(s):
                # Le bec ne bouge pas, mais le TRAIT s'élargit quand même :
                # à basse puissance, seul le coeur du faisceau dépasse le
                # seuil de brûlure du bois. Mesuré sur hêtre au foyer à
                # F800 : 0,10 mm à S200 contre 0,30 à S1000, soit 3x.
                # L'aperçu peignait une largeur unique, et le G-code
                # annonçait « largeur inchangee » -- vrai du point OPTIQUE,
                # faux de ce qu'on voit sur la planche.
                return largeur(0.0, s)

            def teinte_s(s):
                cle = round(s / 5.0) * 5
                if cle not in cache_s:
                    ton = (_tone_measured(mat_nuancier, cle, feed, 0.0)
                           if _mesure_utilisable(0.0) else None)
                    if ton is None:
                        ton = _tone_burn(cle, feed, largeur_s(cle))
                    cache_s[cle] = max(0.0, min(1.0, ton))
                return cache_s[cle]

            strokes = []
            for chain in chains:
                if len(chain) < 2:
                    continue
                ss = core.rampe_trace_dz(
                    chain, sp.get("deg_s_debut", power),
                    sp.get("deg_s_fin", power),
                    bool(sp.get("deg_aller_retour", False)))
                for i in range(len(chain) - 1):
                    a_, b_ = chain[i], chain[i + 1]
                    s_pt = (ss[i] + ss[i + 1]) / 2.0
                    strokes.append(([(a_.x, a_.y), (b_.x, b_.y)],
                                    largeur_s(s_pt), teinte_s(s_pt)))
            return strokes

        strokes = []
        for chain in chains:
            if len(chain) < 2:
                continue
            if dz_dir is not None:
                dzs = [dz_dir(p) for p in chain]
            else:
                dzs = core.rampe_trace_dz(
                    chain, sp.get("deg_z_min", 0.0), sp.get("deg_z_max", 0.0),
                    bool(sp.get("deg_aller_retour", False)))
            # Rampe de puissance optionnelle, sur le MÊME paramétrage que
            # la largeur : sans elle, l'aperçu montrerait le fuseau que
            # Christophe a gravé le 31/07/2026 -- marbré au large,
            # carbonisé au fin.
            ss = None
            if sp.get("deg_s_rampe"):
                s0 = sp.get("deg_s_debut", power)
                s1 = sp.get("deg_s_fin", power)
                ss = ([dz_dir_s(p) for p in chain] if dz_dir_s is not None
                      else core.rampe_trace_dz(
                          chain, s0, s1,
                          bool(sp.get("deg_aller_retour", False))))
            for i in range(len(chain) - 1):
                a_, b_ = chain[i], chain[i + 1]
                dz = (dzs[i] + dzs[i + 1]) / 2.0
                s_pt = None if ss is None else (ss[i] + ss[i + 1]) / 2.0
                w = largeur(dz, s_pt)
                strokes.append(([(a_.x, a_.y), (b_.x, b_.y)], w,
                                teinte_a(dz, w, s_pt)))
        return strokes

    def _style_kwargs(self):
        # Le style « Défocus » (index 4) est un trait PLEIN gravé plus haut
        # (cf. _z_focus) : le point élargi fait le noir, le tracé reste
        # continu. D'où style="plein" ici, la différence est portée par le Z.
        style_map = {0: "plein", 1: "tirets", 2: "pointille", 3: "vague",
                     4: "plein", 5: "degrade", 6: "degrade_trace",
                     7: "degrade_puissance"}
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
                "deg_angle": self.spn_deg_angle.value(),
                "deg_z_min": core.defocus_for_spot_diameter(self.spn_deg_w0.value(), core.SPOT_FOCUS_MM, core.calibrated_half_angle()) or 0.0,
                "deg_z_max": core.defocus_for_spot_diameter(self.spn_deg_w1.value(), core.SPOT_FOCUS_MM, core.calibrated_half_angle()) or 0.0,
                "deg_aller_retour": self.combo_deg_boucle.currentData() == "aller_retour",
                "deg_s_debut": self.spn_deg_s0.value(),
                "deg_s_fin": self.spn_deg_s1.value(),
                # Rampe de puissance SUPERPOSÉE aux dégradés de largeur.
                # Décochée, le générateur reprend exactement son ancienne
                # branche : les fichiers d'avant restent reproductibles.
                "deg_s_rampe": self.chk_deg_s.isChecked(),
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
        self.spn_deg_angle.setValue(values.get("deg_angle", self.spn_deg_angle.value()))
        self.spn_deg_w0.setValue(values.get("deg_w0", self.spn_deg_w0.value()))
        self.spn_deg_w1.setValue(values.get("deg_w1", self.spn_deg_w1.value()))
        self.combo_deg_boucle.setCurrentIndex(
            values.get("deg_boucle", self.combo_deg_boucle.currentIndex()))
        self.spn_deg_s0.setValue(values.get("deg_s0", self.spn_deg_s0.value()))
        self.spn_deg_s1.setValue(values.get("deg_s1", self.spn_deg_s1.value()))
        self.chk_deg_s.setChecked(bool(values.get(
            "deg_s_rampe", self.chk_deg_s.isChecked())))
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
            "deg_angle": self.spn_deg_angle.value(),
            "deg_w0": self.spn_deg_w0.value(),
            "deg_w1": self.spn_deg_w1.value(),
            "deg_boucle": self.combo_deg_boucle.currentIndex(),
            "deg_s0": self.spn_deg_s0.value(),
            "deg_s1": self.spn_deg_s1.value(),
            "deg_s_rampe": self.chk_deg_s.isChecked(),
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
        warnings_out = {}
        gcode = core.generate_gcode_curved(
            self._edges, self._effective_power(), self.spn_feed.value(),
            self._z_focus(), core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
            warnings_out=warnings_out,
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
        # nozzle_marking_points est déjà en coordonnées NATIVES (capturé
        # avant to_machine_z dans generate_gcode_curved) -- pas de décalage
        # Z à appliquer, contrairement à rapid/mark ci-dessus.
        core.create_collision_markers(
            FreeCAD.ActiveDocument, warnings_out.get("nozzle_marking_points", []))

    def _on_photo_preview(self):
        """Rendu réaliste (image) du marquage : chaque trait à sa largeur
        brûlée et sa teinte (projection XY du relief)."""
        if not self._edges:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return
        pw, fd = self._effective_power(), self.spn_feed.value()
        # Largeur du trait selon le STYLE : le point élargi (défocus) et les
        # styles à Z variable élargissent le trait -- sinon l'aperçu resterait
        # à la largeur au foyer quoi qu'on règle.
        idx = self.combo_style.currentIndex()
        half = core.calibrated_half_angle()
        # Matériau OBLIGATOIRE ici aussi (cf. `largeur` dans
        # _strokes_degrade) : sans lui l'aperçu peignait le point optique.
        mat_largeur = (self._shade_picker["mat"].currentData()
                       or self._shade_picker["mat"].currentText())
        w_focus = core.burn_width_defocus_scaled(
            pw, fd, 0.0, mat_largeur) or core.SPOT_FOCUS_MM
        z_tone = 0.0
        if idx == 4:                                   # Défocus (point élargi)
            defocus = core.defocus_for_spot_diameter(
                self.spn_spot_width.value(), core.SPOT_FOCUS_MM, half) or 0.0
            width = core.burn_width_defocus_scaled(
                pw, fd, defocus, mat_largeur) or self.spn_spot_width.value()
            z_tone = defocus
        elif idx == 3:                                 # Vague : moyenne foyer/max
            width = (w_focus + self.spn_wave_width.value()) / 2.0
        elif idx in (5, 6, 7):
            # Les deux dégradés ont une largeur qui VARIE : la peindre
            # constante (l'ancienne moyenne des deux valeurs) montrait une
            # ligne uniforme là où la machine trace un fuseau -- signalé
            # le 31/07/2026 sur un 0,3 -> 3 mm rendu en trait fin. On sort
            # donc par un chemin dédié qui découpe le tracé.
            width = (self.spn_deg_w0.value() + self.spn_deg_w1.value()) / 2.0
        else:                                          # plein / tirets / pointillé
            width = w_focus
        # Teinte : noirceur mesurée du nuancier (matériau du bloc
        # « Nuancier matériau »), sinon modèle de fluence.
        mat_nuancier = (self._shade_picker["mat"].currentData()
                        or self._shade_picker["mat"].currentText())
        tone = _tone_measured(mat_nuancier, pw, fd, z_tone)
        if tone is None:
            tone = _tone_burn(pw, fd, width)
        if idx in (5, 6, 7):
            strokes = self._strokes_degrade(idx, pw, fd)
        else:
            strokes = []
            for e in self._edges:
                pts = _discretize_edge(e)
                if pts:
                    strokes.append((pts, width, tone))
        if not strokes:
            QtWidgets.QMessageBox.information(
                self.form, "Aperçu photo", "Rien à afficher (aucun trait).")
            return
        # Génération à blanc (quiet, gcode jeté) juste pour récupérer les
        # points de collision -- même sonde que le vrai G-code, pour que
        # le repère magenta de cet aperçu corresponde à celui de la vue 3D.
        warnings_out = {}
        core.generate_gcode_curved(
            self._edges, pw, fd, self._z_focus(), core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
            warnings_out=warnings_out, **self._style_kwargs()
        )
        collision_points = [(pt.x, pt.y) for pt in warnings_out.get("nozzle_marking_points", [])]
        img = _render_engraving_photo(strokes, collision_points=collision_points)
        if img is None:
            QtWidgets.QMessageBox.critical(self.form, "Aperçu photo", "Rendu impossible.")
            return
        _show_image_dialog(img, "Aperçu photo — Marquage")

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
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_marquage.ngc")

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        if not _avertir_relief_sans_reference(self.form, self._edges, self._reference_shape):
            return None
        _save_last_values("curved", self._last_fields, selection=self.selection)
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
        """OK : sauvegarde les réglages (forme + objet Job + derniers
        réglages du panneau) et ferme -- la génération du G-code passe
        par le bouton « Générer et sauvegarder le G-code… »."""
        _save_last_values("curved", self._last_fields, selection=self.selection)
        return True

    def _on_save_gcode(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False
        if not _avertir_relief_sans_reference(self.form, self._edges, self._reference_shape):
            return False

        _save_last_values("curved", self._last_fields, selection=self.selection)
        FreeCAD.Console.PrintMessage(
            "Chaînage des segments connectés... ({})\n".format(
                "objet 3D de référence détecté" if self._reference_shape is not None else "pas d'objet 3D, interpolation"))

        warnings_out = {}
        gcode = core.generate_gcode_curved(
            self._edges,
            self._effective_power(),
            self.spn_feed.value(),
            self._z_focus(),
            core.TRANSIT_MARGIN_MM,
            reference_shape=self._reference_shape,
            probe=self._probe,
            warnings_out=warnings_out,
            **self._style_kwargs()
        )

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        # Marqueurs posés AVANT la fenêtre d'avertissement : la vue 3D
        # montre déjà les points en cause dès que l'utilisateur ferme le
        # dialogue -- pas besoin d'un clic « aperçu du trajet » séparé.
        core.create_collision_markers(
            FreeCAD.ActiveDocument, warnings_out.get("nozzle_marking_points", []))
        if not _avertir_collision_detectee(
                self.form, warnings_out.get("nozzle_marking_warnings", 0), "gravure"):
            return False

        # Bouton : le panneau reste ouvert quoi qu'il arrive -- re-cliquer
        # regénère avec les réglages courants.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/marquage.ngc")

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
        _reselect_button(form, self._on_recapture_selection,
                         lambda: self.selection)
        # WrapLongRows (pas DontWrapRows) : le panneau des tâches est étroit
        # et non redimensionnable de manière fiable (bug de redimensionnement
        # observé côté FreeCAD) -- avec DontWrapRows, chaque ligne est forcée
        # sur une seule ligne horizontale quoi qu'il arrive, ce qui pousse le
        # formulaire plus large que le panneau et force un ascenseur
        # horizontal. WrapLongRows fait passer le champ sous son libellé dès
        # que la place manque, donc tout reste visible sans avoir besoin
        # d'élargir la fenêtre.
        form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)

        _diagram(form, "diag_flat.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Sélectionne le(s) <b>profil(s) fermé(s)</b> à découper "
            "(faces, esquisses fermées, contours). Plusieurs pièces&nbsp;: "
            "sélectionne-les ensemble.",
            "<b>2.</b> Pose le <b>zéro machine</b>&nbsp;: X/Y au coin de "
            "référence, Z sur le <b>dessus</b> de la pièce&nbsp;— le foyer "
            "descend passe après passe selon l'épaisseur.",
            "<b>3. Matériau</b>&nbsp;: applique un préréglage, ou règle "
            "épaisseur / nombre de passes / puissance / vitesse. Le <b>kerf</b> "
            "compense la largeur du trait pour rester à la cote.",
            "<b>4. Attaches &amp; amorce</b>&nbsp;: ajoute des attaches (ponts "
            "de matière) pour que la pièce ne se libère pas en fin de coupe, et "
            "une amorce si besoin.",
            "<b>5. Copies en matrice</b> (option)&nbsp;: répète la découpe en "
            "grille X/Y pour débiter plusieurs pièces.",
            "<b>6. Vérifie</b>&nbsp;: «&nbsp;Aperçu cadrage&nbsp;» (fichier "
            "séparé, à blanc sur la chute) puis «&nbsp;Aperçu du trajet&nbsp;».",
            "<b>7. Génère</b>&nbsp;: «&nbsp;Générer et sauvegarder le "
            "G-code…&nbsp;». Relis le <code>G0&nbsp;Z…</code> et la hauteur de "
            "bec avant de lancer.",
        ])

        _section(form, "Préréglage matériau", "sect_preset.svg")
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/épaisseur/\n"
            "passes/finition/rampe/kerf) -- en choisir un remplit\n"
            "automatiquement les champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder")
        _btn_icon(self.btn_save_preset, "sect_preset.svg")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer")
        self.btn_delete_preset.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        _mat_row = QtWidgets.QWidget()
        _mat_h = QtWidgets.QHBoxLayout(_mat_row)
        _mat_h.setContentsMargins(0, 0, 0, 0)
        _mat_h.addWidget(self.btn_save_preset)
        _mat_h.addWidget(self.btn_delete_preset)
        form.addRow(_mat_row)

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

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences) -- la vraie vitesse rapide de\n"
            "ta machine n'est pas connue ici.".format(core.RAPID_FEED_MM_MIN))

        self.btn_save_gcode = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_save_gcode, "sect_gcode.svg")
        self.btn_save_gcode.setToolTip(
            "Génère le G-code avec les réglages actuels et propose le\n"
            "fichier de sauvegarde. Le bouton OK, lui, se contente de\n"
            "SAUVEGARDER LES RÉGLAGES (sur la forme + objet Job) et ferme\n"
            "le panneau sans générer.")
        self.btn_save_gcode.clicked.connect(self._on_save_gcode)
        form.addRow(self.btn_save_gcode)

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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel dans la vue 3D de FreeCAD : gris fin =\n"
            "transit laser éteint (G0), rouge épais = découpe laser allumé\n"
            "(G1). Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])
        _combined_add_button(form, self._on_add_to_combined)

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
        _restore_last_values("flat", self._last_fields, selection=self.selection)

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

    def _on_recapture_selection(self):
        """Reprend la sélection courante de la vue / de l'arbre (le panneau ne
        la capture qu'à son ouverture)."""
        self.selection = Gui.Selection.getSelectionEx()
        self._edges = core.get_all_edges_from_selection(self.selection)
        self._update_duration_preview()
        if not self._edges:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Aucun segment dans la sélection courante. Sélectionne le "
                "tracé à découper, puis reclique ce bouton.")
        else:
            FreeCAD.Console.PrintMessage(
                "Sélection reprise : {} segment(s).\n".format(len(self._edges)))

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
        _write_gcode_with_dialog(self.form, gcode, "/tmp/apercu_cadrage_decoupe_plat.ngc")

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        _save_last_values("flat", self._last_fields, selection=self.selection)
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
        """OK : sauvegarde les réglages (forme + objet Job + derniers
        réglages du panneau) et ferme -- la génération du G-code passe
        par le bouton « Générer et sauvegarder le G-code… »."""
        _save_last_values("flat", self._last_fields, selection=self.selection)
        return True

    def _on_save_gcode(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False

        _save_last_values("flat", self._last_fields, selection=self.selection)

        FreeCAD.Console.PrintMessage("Chaînage des segments connectés...\n")
        gcode = core.generate_gcode_flat_multipass(
            self._edges_for_job(),
            self.spn_power.value(),
            self.spn_feed.value(),
            self.spn_thickness.value(),
            self.spn_passes.value(),
            **self._build_gcode_kwargs(),
        )

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False

        # Bouton : le panneau reste ouvert, re-cliquer regénère.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/decoupe_plat.ngc")

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
        _reselect_button(form, self._on_recapture_selection,
                         lambda: self.selection)
        _intro(form,
               "Découpe en plusieurs passes EN SUIVANT LE RELIEF d'une "
               "surface courbe. Sélectionne le motif projeté (Motif_Projete) "
               "ET le modèle 3D d'origine, les deux en même temps.",
               "Le modèle 3D permet une sonde exacte du relief. Chaque passe "
               "recule le foyer un peu plus DANS la matière (comme la découpe "
               "à plat : épaisseur / nombre de passes), tout en suivant le "
               "relief natif à chaque point du tracé. Compensation de kerf, "
               "ordre trous-avant-contour et optimisation par proximité "
               "disponibles comme à plat.")

        _diagram(form, "diag_curvedcut.svg")

        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Sélectionne le motif projeté (<code>Motif_Projete</code>) "
            "<b>ET</b> le modèle 3D d'origine, les deux en même temps.",
            "<b>2.</b> Pose le <b>zéro machine</b>&nbsp;: X/Y au coin de "
            "référence, Z sur le point haut de la surface&nbsp;— le relief est "
            "sondé exactement à chaque point pendant la découpe.",
            "<b>3. Matériau</b>&nbsp;: applique un préréglage, ou règle "
            "épaisseur / nombre de passes / puissance / vitesse. Chaque passe "
            "recule le foyer un peu plus DANS la matière, tout en suivant le "
            "relief.",
            "<b>4. Kerf &amp; ordre</b>&nbsp;: compensation de kerf, trous "
            "avant contour et optimisation par proximité, exactement comme à "
            "plat.",
            "<b>5. Vérifie</b>&nbsp;: «&nbsp;Aperçu cadrage&nbsp;» (fichier "
            "séparé) puis «&nbsp;Aperçu du trajet&nbsp;».",
            "<b>6. Génère</b>&nbsp;: «&nbsp;Générer et sauvegarder le "
            "G-code…&nbsp;». Relis le <code>G0&nbsp;Z…</code> en tête avant de "
            "lancer.",
        ])

        _section(form, "Préréglage matériau", "sect_preset.svg")
        self.combo_preset = QtWidgets.QComboBox()
        self.combo_preset.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_preset.setMinimumContentsLength(14)
        self.combo_preset.setToolTip(
            "Préréglages matériau sauvegardés (puissance/vitesse/épaisseur/\n"
            "passes/Z travail/finition/rampe/kerf) -- en choisir un remplit\n"
            "automatiquement les champs ci-dessous.")
        form.addRow("Préréglage matériau :", self.combo_preset)
        self.combo_preset.currentIndexChanged.connect(self._on_preset_selected)

        self.btn_save_preset = QtWidgets.QPushButton("Sauvegarder")
        _btn_icon(self.btn_save_preset, "sect_preset.svg")
        self.btn_save_preset.setToolTip("Sauvegarde les valeurs actuelles sous un nom de préréglage.")
        self.btn_save_preset.clicked.connect(self._on_save_preset)
        self.btn_delete_preset = QtWidgets.QPushButton("Supprimer")
        self.btn_delete_preset.setToolTip("Supprime le préréglage sélectionné (les ★ d'usine sont protégés).")
        self.btn_delete_preset.clicked.connect(self._on_delete_preset)
        _mat_row = QtWidgets.QWidget()
        _mat_h = QtWidgets.QHBoxLayout(_mat_row)
        _mat_h.setContentsMargins(0, 0, 0, 0)
        _mat_h.addWidget(self.btn_save_preset)
        _mat_h.addWidget(self.btn_delete_preset)
        form.addRow(_mat_row)

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

        _section(form, "Aperçus & génération", "sect_gcode.svg")
        self.lbl_duration = _duration_row(
            form, self._update_duration_preview,
            "Approximative : G1 selon distance/avance programmée, G0\n"
            "(transit) à une vitesse rapide SUPPOSÉE de {:.0f}mm/min\n"
            "(réglable dans Préférences).".format(core.RAPID_FEED_MM_MIN))

        self.btn_save_gcode = QtWidgets.QPushButton("Générer et sauvegarder le G-code…")
        _btn_icon(self.btn_save_gcode, "sect_gcode.svg")
        self.btn_save_gcode.setToolTip(
            "Génère le G-code avec les réglages actuels et propose le\n"
            "fichier de sauvegarde. Le bouton OK, lui, se contente de\n"
            "SAUVEGARDER LES RÉGLAGES (sur la forme + objet Job) et ferme\n"
            "le panneau sans générer.")
        self.btn_save_gcode.clicked.connect(self._on_save_gcode)
        form.addRow(self.btn_save_gcode)

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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Affiche le trajet réel (TOUTES les passes) dans la vue 3D :\n"
            "gris fin = transit laser éteint (G0), rouge épais = découpe\n"
            "laser allumé (G1) -- les passes profondes apparaissent sous la\n"
            "surface du modèle, comme la vraie profondeur de coupe.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg")])
        _combined_add_button(form, self._on_add_to_combined)

        self._last_fields = {
            "power": self.spn_power, "feed": self.spn_feed,
            "z_focus": self.spn_zfocus, "marge": self.spn_marge,
            "thickness": self.spn_thickness, "n_passes": self.spn_passes,
            "use_finish": self.chk_finish, "finish_feed": self.spn_finish_feed,
            "use_power_ramp": self.chk_power_ramp, "power_end": self.spn_power_end,
            "kerf": self.spn_kerf, "hole_first": self.chk_hole_first,
            "proximity": self.chk_proximity,
        }
        _restore_last_values("curved_cut", self._last_fields, selection=self.selection)

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

    def _on_recapture_selection(self):
        """Reprend la sélection courante de la vue / de l'arbre (le panneau ne
        la capture qu'à son ouverture)."""
        self.selection = Gui.Selection.getSelectionEx()
        self._edges, self._reference_shape = self._get_edges()
        self._probe = (core.make_ray_probe(self._reference_shape)
                       if self._reference_shape is not None else None)
        self._update_duration_preview()
        if not self._edges:
            QtWidgets.QMessageBox.warning(
                self.form, "Sélection",
                "Aucun segment dans la sélection courante. Sélectionne le "
                "tracé (et le modèle 3D) puis reclique ce bouton.")
        else:
            FreeCAD.Console.PrintMessage(
                "Sélection reprise : {} segment(s).\n".format(len(self._edges)))

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
        warnings_out = {}
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape, quiet=True, probe=self._probe,
            warnings_out=warnings_out, **self._build_gcode_kwargs(),
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
        # nozzle_cut_points est déjà en coordonnées NATIVES (capturé avant
        # to_machine_z) -- pas de décalage Z à appliquer ici.
        core.create_collision_markers(
            FreeCAD.ActiveDocument, warnings_out.get("nozzle_cut_points", []))

    def _build_combined_operation(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return None
        if not _avertir_relief_sans_reference(self.form, self._edges, self._reference_shape):
            return None
        _save_last_values("curved_cut", self._last_fields, selection=self.selection)
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
        """OK : sauvegarde les réglages (forme + objet Job + derniers
        réglages du panneau) et ferme -- la génération du G-code passe
        par le bouton « Générer et sauvegarder le G-code… »."""
        _save_last_values("curved_cut", self._last_fields, selection=self.selection)
        return True

    def _on_save_gcode(self):
        if not self._edges:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun segment trouvé (vérifie la sélection).")
            return False
        if not _avertir_relief_sans_reference(self.form, self._edges, self._reference_shape):
            return False

        _save_last_values("curved_cut", self._last_fields, selection=self.selection)

        FreeCAD.Console.PrintMessage(
            "Chaînage des segments connectés... ({})\n".format(
                "objet 3D de référence détecté" if self._reference_shape is not None else "pas d'objet 3D, interpolation"))
        warnings_out = {}
        gcode = core.generate_gcode_curved_cut(
            self._edges, self.spn_power.value(), self.spn_feed.value(),
            self.spn_thickness.value(), self.spn_passes.value(),
            self.spn_zfocus.value(), self.spn_marge.value(),
            reference_shape=self._reference_shape,
            probe=self._probe,
            warnings_out=warnings_out,
            **self._build_gcode_kwargs(),
        )

        if not gcode:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Aucun G-code généré.")
            return False
        core.create_collision_markers(
            FreeCAD.ActiveDocument, warnings_out.get("nozzle_cut_points", []))
        if not _avertir_collision_detectee(
                self.form, warnings_out.get("nozzle_cut_warnings", 0), "découpe"):
            return False

        # Bouton : le panneau reste ouvert, re-cliquer regénère.
        return _write_gcode_with_dialog(self.form, gcode, "/tmp/decoupe_courbe.ngc")

    def reject(self):
        return True


# ==========================================================================
# MODE : JOB COMBINÉ (PLUSIEURS OPÉRATIONS, UN SEUL ARMEMENT)
# ==========================================================================
# ASSISTANT MATÉRIAU (le fil de calibration en un panneau)
# ==========================================================================
class TaskPanelAssistant:
    """ASSISTANT MATÉRIAU : caractériser un matériau du début à la fin, dans
    un seul panneau -- ① graver les trois planches, ② mesurer (mêmes grilles
    que la Grille de test), ③ photo du résultat (rangée par matériau, clé
    "assistant:<matériau>"), ④ déduire (état du modèle, sonde d'interpolation,
    nuancier physique). Pure orchestration : générateurs et saisie sont ceux
    des modes autonomes (Grille, Rampe, Bande défocus, Nuancier), qui restent
    utilisables séparément."""

    def __init__(self):
        inner = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(inner)
        _panel_header(form, "assistant.svg", "Assistant matériau")
        _intro(form,
               "Caractérise un matériau du début à la fin : grave les trois "
               "planches, mesure au pied à coulisse, saisis — l'atelier en "
               "déduit largeurs et espacements pour tous les modes. Les modes "
               "autonomes (Grille, Rampe, Bande défocus, Nuancier) restent : "
               "l'Assistant les orchestre sans les remplacer. Prérequis, une "
               "fois par laser : la calibration du point (Planche 3, saisie "
               "dans le mode « Bande de calibration défocus » ou les "
               "Préférences).")

        self.combo_mat = QtWidgets.QComboBox()
        self.combo_mat.setEditable(True)
        self.combo_mat.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_mat.setMinimumContentsLength(14)
        self.combo_mat.setToolTip(
            "Matériau caractérisé : les mesures (①②) et le nuancier y sont "
            "rangés.\nChoisis-en un dans la liste, ou tape un nouveau nom -- "
            "les mesures\nci-dessous repartent alors à zéro, jusqu'à ce que "
            "tu enregistres\nles siennes. « Nouveau matériau » vide le champ "
            "pour toi.")
        form.addRow("Matériau :", self.combo_mat)

        self.btn_nouveau_mat = QtWidgets.QPushButton("Nouveau matériau…")
        self.btn_nouveau_mat.setToolTip(
            "Vide le champ ci-dessus pour caractériser un matériau qui "
            "n'existe\npas encore -- tape son nom, grave/mesure (①②), "
            "« Enregistrer les\nmesures » le crée réellement (rien n'est "
            "créé avant ça).")
        self.btn_nouveau_mat.clicked.connect(self._on_nouveau_materiau)
        form.addRow(self.btn_nouveau_mat)

        self.btn_supprimer_mat = QtWidgets.QPushButton("Supprimer ce matériau")
        self.btn_supprimer_mat.setToolTip(
            "Efface les mesures (①②) ET le nuancier de ce matériau. "
            "Irréversible.")
        self.btn_supprimer_mat.clicked.connect(self._on_supprimer_materiau)
        form.addRow(self.btn_supprimer_mat)

        _section(form, "① Graver les trois planches", "sect_power.svg")
        form.addRow(_WrapLabel(
            "Trois fichiers séparés, chacun recadré au zéro pièce (coin "
            "bas-gauche de la chute, sur le dessus). Grave-les sur le même "
            "matériau et dans les mêmes conditions (filet d'air, propreté de "
            "la lentille) que tes futurs jobs."))
        _boutons_planches(form, self._ecrire_planche)

        _section(form, "② Entrer les mesures (largeurs)", "sect_measure.svg")
        form.addRow(_WrapLabel(
            "Mesure la LARGEUR brûlée de chaque trait au pied à coulisse "
            "(1/10 mm). « — » = non mesuré ; un trait vierge est une donnée "
            "(seuil du matériau), laisse-le à « — ». Décoche le verrou d'une "
            "grille pour saisir, puis « Enregistrer les mesures »."))
        self._mesures = _MesuresPlanchesControleur(
            form, self, lambda: self.combo_mat.currentText(),
            on_saved=self._on_mesures_enregistrees)

        self._photo = _make_photo_section(
            form, lambda: "assistant:" + self.combo_mat.currentText().strip(),
            titre="③ Photo du résultat")

        _section(form, "④ Déduire (modèle & nuancier)", "sect_preset.svg")
        self.lbl_etat = _WrapLabel("")
        form.addRow(self.lbl_etat)
        # Sonde d'interpolation : montre en direct la largeur que le modèle
        # prédit pour un réglage donné -- la preuve que les mesures servent.
        self.spn_sonde_s = QtWidgets.QDoubleSpinBox()
        self.spn_sonde_s.setRange(0.0, core.S_MAX)
        self.spn_sonde_s.setDecimals(0)
        self.spn_sonde_s.setValue(min(600.0, core.S_MAX))
        form.addRow("Sonde — puissance S :", self.spn_sonde_s)
        self.spn_sonde_f = QtWidgets.QDoubleSpinBox()
        self.spn_sonde_f.setRange(1.0, 20000.0)
        self.spn_sonde_f.setDecimals(0)
        self.spn_sonde_f.setValue(800.0)
        self.spn_sonde_f.setSuffix(" mm/min")
        form.addRow("Sonde — vitesse F :", self.spn_sonde_f)
        self.spn_sonde_dz = QtWidgets.QDoubleSpinBox()
        self.spn_sonde_dz.setRange(0.0, 60.0)
        self.spn_sonde_dz.setDecimals(1)
        self.spn_sonde_dz.setValue(12.0)
        self.spn_sonde_dz.setSuffix(" mm")
        self.spn_sonde_dz.setToolTip(
            "Hauteur du bec AU-DESSUS du foyer (0 = au foyer).")
        form.addRow("Sonde — défocus :", self.spn_sonde_dz)
        self.lbl_sonde = _WrapLabel("")
        form.addRow(self.lbl_sonde)
        for w in (self.spn_sonde_s, self.spn_sonde_f, self.spn_sonde_dz):
            w.valueChanged.connect(self._maj_sonde)

        self.btn_nuancier = QtWidgets.QPushButton(
            "Construire le nuancier physique (tons mesurés)…")
        self.btn_nuancier.setToolTip(
            "Un cercle gravé par TON MESURÉ du matériau (mode Nuancier),\n"
            "recette + Job chacun + étiquettes, empilés dans le job combiné\n"
            "(ouvre le panneau Job combiné, prêt à générer).")
        self.btn_nuancier.clicked.connect(self._on_nuancier)
        form.addRow(self.btn_nuancier)
        form.addRow(_WrapLabel(
            "Les TONS (noirceur 0-100 %) se découvrent avec la Rampe ou la "
            "Grille de test et se consignent dans le mode Nuancier — "
            "l'Assistant grave ensuite leur planche physique ci-dessus."))

        self.combo_mat.currentIndexChanged.connect(self._on_mat_change)
        self.combo_mat.lineEdit().editingFinished.connect(self._on_mat_change)

        self._reload_liste_materiaux()
        self._mesures.reload()
        self._photo["reload"]()
        self._maj_deductions()

        self.form = _scrollable(inner)

    def _ecrire_planche(self, gcode, chemin):
        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Génération vide (calibration invalide ?).")
            return
        _write_gcode_with_dialog(self.form, gcode, chemin)

    def _on_mat_change(self, *_):
        self._mesures.reload()
        self._photo["reload"]()
        self._maj_deductions()

    def _reload_liste_materiaux(self, garder=None):
        """Recharge la liste déroulante depuis la config (union des
        matériaux mesurés ET du nuancier -- un matériau qui n'a que l'un
        des deux doit rester visible), en conservant la sélection/le texte
        courant. Même pattern que TaskPanelNuancier._reload_materials.
        Appelée après « Enregistrer les mesures » : sans ça, un matériau
        tout juste créé disparaît de la liste dès qu'on choisit un autre
        matériau, et il fallait fermer/rouvrir le panneau pour le
        retrouver."""
        actuel = (garder if garder is not None
                  else self.combo_mat.currentText()).strip()
        mats = sorted(set(core.burn_width_materials()) | set(core.shade_materials())) or ["MDF"]
        self.combo_mat.blockSignals(True)
        self.combo_mat.clear()
        self.combo_mat.addItems(mats)
        self.combo_mat.setCurrentText(actuel if actuel else mats[0])
        self.combo_mat.blockSignals(False)

    def _on_nouveau_materiau(self):
        """Vide le champ pour caractériser un matériau qui n'existe pas
        encore -- ne crée rien tout seul (« Enregistrer les mesures » s'en
        charge) : juste l'équivalent explicite de taper un nom inédit."""
        self.combo_mat.blockSignals(True)
        self.combo_mat.setCurrentIndex(-1)
        self.combo_mat.setEditText("")
        self.combo_mat.blockSignals(False)
        self.combo_mat.setFocus()
        self._on_mat_change()

    def _on_supprimer_materiau(self):
        mat = self.combo_mat.currentText().strip()
        if not mat:
            return
        reponse = QtWidgets.QMessageBox.question(
            self.form, "Supprimer « {} »".format(mat),
            "Effacer TOUTES les mesures (①②) et le nuancier de « {} » "
            "?\n\nIrréversible.".format(mat),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if reponse != QtWidgets.QMessageBox.Yes:
            return
        core.save_burn_widths(mat, {})
        core.save_shades(mat, [])
        self._reload_liste_materiaux(garder="")
        self._on_mat_change()

    def _on_mesures_enregistrees(self):
        """Callback de _MesuresPlanchesControleur après « Enregistrer les
        mesures » : un matériau tout juste créé doit rester sélectionnable
        dans la liste, pas seulement tapé au clavier."""
        self._reload_liste_materiaux()
        self._maj_deductions()

    def _maj_deductions(self):
        self._maj_etat()
        self._maj_sonde()

    def _maj_etat(self):
        """Résumé de ce que le modèle sait du matériau : mesures au foyer,
        couverture par niveau de défocus (le feed est-il balayé ?), tons."""
        mat = self.combo_mat.currentText().strip()
        data = core.load_burn_widths(mat) if mat else {}
        focus = data.get("focus") or []
        dfc = data.get("defocus") or []
        shades = core.load_shades(mat) if mat else []
        if not (focus or dfc or shades):
            self.lbl_etat.setText(
                "<b>« {} » : aucune mesure.</b> Grave les planches (①), "
                "mesure, saisis (②) — le modèle s'active tout seul.".format(
                    mat or "?"))
            return
        par_niveau = {}
        for pt in dfc:
            z = round(float(pt.get("z_offset", 0) or 0), 3)
            par_niveau.setdefault(z, set()).add(float(pt.get("feed", 800)))
        morceaux = ["<b>« {} »</b> : {} mesure(s) au foyer".format(
            mat, len(focus))]
        for z in sorted(par_niveau):
            feeds = sorted(par_niveau[z])
            morceaux.append("défocus {:.0f} mm : {} vitesse(s) ({})".format(
                z, len(feeds), ", ".join("F{:.0f}".format(f) for f in feeds)))
        feed_aware = any(len(v) >= 2 for v in par_niveau.values())
        morceaux.append("largeur au défocus sensible au feed : {}".format(
            "<b>oui</b>" if feed_aware
            else "non (une seule vitesse mesurée — grave la Planche 2)"))
        morceaux.append("{} ton(s) au nuancier".format(len(shades)))
        self.lbl_etat.setText(" · ".join(morceaux) + ".")

    def _maj_sonde(self, *_):
        mat = self.combo_mat.currentText().strip()
        w = core.burn_width_defocus_scaled(
            self.spn_sonde_s.value(), self.spn_sonde_f.value(),
            self.spn_sonde_dz.value(), mat) if mat else None
        if not w:
            self.lbl_sonde.setText(
                "Sonde : aucune mesure exploitable pour ce matériau "
                "(grave et saisis d'abord la Planche 2).")
            return
        self.lbl_sonde.setText(
            "<b>Largeur brûlée prédite : {:.2f} mm</b> → espacement plein "
            "conseillé : <b>{:.2f} mm</b> (largeur × 0,9 : 10 % de "
            "recouvrement). <i>Informatif : la Gravure remplie resserre déjà "
            "son espacement toute seule sur cette mesure ; pour forcer une "
            "autre valeur, règle « Espacement remplissage » dans son "
            "panneau.</i>".format(w, w * 0.9))

    def _on_nuancier(self):
        _lancer_nuancier_physique(self.form, "tons",
                                  self.combo_mat.currentText().strip())

    def accept(self):
        return True

    def reject(self):
        return True


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
        _diagram(form, "diag_combined.svg")

        # Mode d'emploi en tête, replié par défaut. La liste des opérations a
        # SA PROPRE section (ouverte) juste après : sinon, « Mode d'emploi »
        # étant l'unique section du panneau, toutes les rangées suivantes
        # seraient aspirées dans son repli (il fallait la déplier pour voir
        # ses propres jobs).
        _section(form, "Mode d'emploi", "sect_guide.svg")
        _bullet_list(form, [
            "<b>1.</b> Dans chaque mode combinable (Découpe plat/courbe, "
            "Marquage, Grille de test…), règle l'opération comme d'habitude "
            "puis clique «&nbsp;➕ Ajouter au job combiné&nbsp;».",
            "<b>2.</b> Reviens ici&nbsp;: la <b>liste</b> empile les opérations "
            "dans l'ordre d'exécution. Monte / descends / supprime pour les "
            "ordonner.",
            "<b>3. Vérifie</b>&nbsp;: «&nbsp;Aperçu cadrage&nbsp;» (fichier "
            "séparé), «&nbsp;Aperçu du trajet&nbsp;» et «&nbsp;Aperçu "
            "photo&nbsp;» (rendu de tout le job d'un coup).",
            "<b>4.</b> Clique <b>OK</b>&nbsp;: le job part en <b>un seul "
            "fichier</b>&nbsp;— un seul armement (<code>M3</code>) au début, un "
            "seul désarmement (<code>M5</code>)/<code>M2</code> à la fin.",
        ])

        _section(form, "Opérations à graver", "sect_options.svg")
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

        self.btn_toolpath_preview = QtWidgets.QPushButton()
        self.btn_toolpath_preview.setToolTip(
            "Aperçu du trajet (vue 3D) de TOUT le job combiné : gris fin =\n"
            "transit laser éteint (G0), rouge épais = laser allumé (G1).\n"
            "Purement visuel, ne génère aucun fichier.")
        self.btn_toolpath_preview.clicked.connect(self._on_toolpath_preview)
        self.btn_photo_preview = QtWidgets.QPushButton()
        self.btn_photo_preview.setToolTip(
            "Aperçu photo (rendu réaliste) de TOUT le job combiné : gravures\n"
            "à leur largeur/teinte réelles, découpes en fins traits sombres.\n"
            "Rendu théorique du résultat final avant de graver.")
        self.btn_photo_preview.clicked.connect(self._on_photo_preview)
        _preview_row(form, [(self.btn_toolpath_preview, "btn_view3d.svg"),
                            (self.btn_photo_preview, "sect_photo.svg")])

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

    def _combined_collision_points(self):
        """Points de collision (repère natif, aucun décalage Z nécessaire
        -- cf. create_collision_markers) réunis sur TOUTES les opérations
        curved/curved_cut du job en une seule liste. Génération complète
        à part, G-code jeté (comme TaskPanelCurved._on_photo_preview) :
        contrairement à rapid/mark, un point de collision n'a pas besoin
        d'être isolé par opération, donc pas besoin de la boucle
        opération-par-opération de _on_toolpath_preview ici."""
        w = {}
        core.generate_gcode_combined(self.operations, quiet=True, warnings_out=w)
        return w.get("nozzle_points", [])

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
        core.create_collision_markers(FreeCAD.ActiveDocument, self._combined_collision_points())

    def _on_photo_preview(self):
        """Rendu réaliste (image) de TOUT le job combiné : chaque opération
        peinte à sa largeur/teinte, dans l'ordre de la liste (les dernières
        se superposent aux premières)."""
        if not self.operations:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Ajoute au moins une opération avant l'aperçu.")
            return
        strokes = []
        for op in self.operations:
            strokes.extend(_strokes_from_operation(op))
        if not strokes:
            QtWidgets.QMessageBox.information(
                self.form, "Aperçu photo",
                "Rien à peindre (opérations vides ou uniquement des grilles "
                "de test).")
            return
        collision_points = [(pt.x, pt.y) for pt in self._combined_collision_points()]
        img = _render_engraving_photo(strokes, collision_points=collision_points)
        if img is None:
            QtWidgets.QMessageBox.critical(self.form, "Aperçu photo", "Rendu impossible.")
            return
        _show_image_dialog(img, "Aperçu photo — Job combiné")

    def accept(self):
        if not self.operations:
            QtWidgets.QMessageBox.critical(self.form, "Erreur", "Ajoute au moins une opération avant de lancer le job.")
            return False

        warnings_out = {}
        gcode = core.generate_gcode_combined(self.operations, warnings_out=warnings_out)

        if not gcode:
            QtWidgets.QMessageBox.critical(
                self.form, "Erreur", "Aucun G-code généré (vérifie que les opérations contiennent de la géométrie).")
            return False

        # Marqueurs posés AVANT la fenêtre d'avertissement, comme sur les
        # modes directs (Marquage/Découpe courbe) : déjà visibles dans la
        # vue 3D dès que l'utilisateur ferme le dialogue.
        core.create_collision_markers(FreeCAD.ActiveDocument, warnings_out.get("nozzle_points", []))
        if not _avertir_collision_detectee(
                self.form, warnings_out.get("nozzle_warnings", 0), "job combiné", "ce"):
            return False

        # Bouton : le panneau reste ouvert, re-cliquer regénère.
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

        self.edt_planches_dir = QtWidgets.QLineEdit(settings["planches_dir"])
        self.edt_planches_dir.setToolTip(
            "Dossier où sont rangées les PLANCHES REDRESSÉES (image de\n"
            "mesure, sa fiche .json, son aperçu et le contrôle des repères).\n"
            "\n"
            "À part des photos d'origine, volontairement : une planche\n"
            "redressée n'est pas une photo, c'est un instrument de mesure à\n"
            "l'échelle exacte. Rangée avec les photos brutes, elle se perd.\n"
            "\n"
            "Le nom du fichier porte le LASER ACTIF : une largeur brûlée n'a\n"
            "de sens que pour le module qui l'a gravée -- et quelqu'un qui a\n"
            "le même module peut reprendre ces mesures sans refaire l'établi.")
        btn_browse_pl = QtWidgets.QPushButton("Parcourir...")
        btn_browse_pl.clicked.connect(self._browse_planches_dir)
        row_pl = QtWidgets.QWidget()
        row_pl_layout = QtWidgets.QHBoxLayout(row_pl)
        row_pl_layout.setContentsMargins(0, 0, 0, 0)
        row_pl_layout.addWidget(self.edt_planches_dir, 1)
        row_pl_layout.addWidget(btn_browse_pl, 0)
        form.addRow("Dossier des planches :", row_pl)

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

        # Étiquettes gravées des tests/planches : réglées UNE fois ici (par
        # laser), plus de champs répétés dans chaque panneau de test.
        self.spn_label_power = QtWidgets.QDoubleSpinBox()
        self.spn_label_power.setRange(0, core.S_MAX)
        self.spn_label_power.setDecimals(0)
        self.spn_label_power.setValue(float(settings.get("label_power", 600.0)))
        self.spn_label_power.setToolTip(
            "Puissance (S) de gravure des étiquettes des tests, planches et\n"
            "nuanciers (S600 : lisible sans carboniser sur la plupart des bois).")
        form.addRow("Étiquettes — puissance :", self.spn_label_power)
        self.spn_label_feed = QtWidgets.QDoubleSpinBox()
        self.spn_label_feed.setRange(1, 20000)
        self.spn_label_feed.setDecimals(0)
        self.spn_label_feed.setSuffix(" mm/min")
        self.spn_label_feed.setValue(float(settings.get("label_feed", 800.0)))
        self.spn_label_feed.setToolTip("Vitesse d'avance de gravure des étiquettes.")
        form.addRow("Étiquettes — vitesse :", self.spn_label_feed)

        self.btn_export = QtWidgets.QPushButton("Exporter réglages + photos (.zip)…")
        self.btn_export.setToolTip(
            "Crée une archive .zip contenant TOUS les réglages (préréglages,\n"
            "nuancier, calibration, profils laser…) ET toutes les photos de\n"
            "résultats -- à ranger en lieu sûr, au cas où. Restauration :\n"
            "dézipper « laser_atelier_config.json » dans le dossier app-data\n"
            "de FreeCAD, et « photos_resultats » dans le dossier de l'atelier.")
        self.btn_export.clicked.connect(self._on_export_all)
        form.addRow(self.btn_export)

        self.btn_import = QtWidgets.QPushButton("Importer une sauvegarde…")
        self.btn_import.setToolTip(
            "Restaure une archive .zip précédemment exportée : REMPLACE tous\n"
            "les réglages actuels (préréglages, nuancier, calibration, profils\n"
            "laser…) et rétablit les photos. Pour récupérer après une perte ou\n"
            "transférer la config sur une autre machine.")
        self.btn_import.clicked.connect(self._on_import_all)
        form.addRow(self.btn_import)

        _section(form, "Interface", "sect_options.svg")
        self.chk_accordeon = QtWidgets.QCheckBox(
            "Sections en accordéon (en ouvrir une replie les autres)")
        self.chk_accordeon.setChecked(bool(settings.get("sections_accordeon", True)))
        self.chk_accordeon.setToolTip(
            "Coché : dans les panneaux, ouvrir une section replie les autres\n"
            "-- moins de défilement. Décoché : les sections restent ouvertes\n"
            "indépendamment (comportement libre). Le bouton « tout déplier »\n"
            "de l'en-tête ouvre tout dans les deux cas.")
        form.addRow(self.chk_accordeon)

        _section(form, "Machine / G-code", "sect_options.svg")
        self.edt_spindle = QtWidgets.QLineEdit(settings["spindle_select"])
        self.edt_spindle.setToolTip(
            "Sélecteur multi-broche ajouté aux commandes S/M3/M5 (LinuxCNC :\n"
            "\"$1\" = spindle 1 = laser). Ignoré en dialecte GRBL (aucun\n"
            "sélecteur n'est émis).")
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

        self.combo_dialect = QtWidgets.QComboBox()
        self.combo_dialect.addItem("LinuxCNC", "linuxcnc")
        self.combo_dialect.addItem("GRBL", "grbl")
        self.combo_dialect.addItem("grblHAL", "grblhal")
        idx_d = self.combo_dialect.findData(settings.get("gcode_dialect", "linuxcnc"))
        self.combo_dialect.setCurrentIndex(max(0, idx_d))
        self.combo_dialect.setToolTip(
            "Contrôleur cible du G-code généré, PAR PROFIL laser :\n"
            "- LinuxCNC (défaut) : multi-broche $n, T/M6 + G43 H, G64.\n"
            "- GRBL (1.1 classique) : pas de sélecteur de broche ni de\n"
            "  changement d'outil (T/M6/G43 omis), pas de G64 (lissage\n"
            "  natif, réglage $11), armement en M4 = mode laser.\n"
            "  Prérequis côté GRBL : $32=1 (mode laser) et $30 égal à\n"
            "  l'Échelle de puissance max ci-dessous. Le sélecteur de\n"
            "  broche et le numéro d'outil sont alors ignorés.\n"
            "  Zéro Z : à poser sur la surface (cale, réglet... -- aucun\n"
            "  palpeur requis).\n"
            "- grblHAL : comme GRBL (M4, pas de $n ni G64), mais AVEC le\n"
            "  changement d'outil et la compensation T/M6 + G43 H --\n"
            "  nécessite un firmware compilé avec la table d'outils\n"
            "  (option N_TOOLS). Le numéro d'outil laser est utilisé.")
        form.addRow("Dialecte G-code :", self.combo_dialect)

        self.chk_m67 = QtWidgets.QCheckBox(
            "Puissance par M67 (sortie analogique synchronisée)")
        self.chk_m67.setChecked(bool(settings.get("puissance_par_m67", False)))
        self.chk_m67.setToolTip(
            "LinuxCNC seulement. Envoie la puissance par « M67 E0 Q<valeur> »\n"
            "au lieu du mot « S ». M67 est SYNCHRONISÉ avec le mouvement : la\n"
            "valeur est appliquée au début du bloc suivant sans vider la file\n"
            "de trajectoire.\n"
            "\n"
            "POURQUOI : sur la PrintNC, un mot S entre deux G1 fait ARRÊTER la\n"
            "machine, même sur des segments parfaitement colinéaires. Prouvé\n"
            "par deux fichiers de géométrie identique -- S constant fluide,\n"
            "S variable saccadé. Un portrait de 172 614 blocs de 0,30 mm\n"
            "annoncé 1h30 est parti pour 4 h, soit ~76 ms par bloc là où il en\n"
            "faudrait 22 : le temps d'un aller-retour avec arrêt aux deux\n"
            "bouts. Gain attendu ~3x sur tout tramage qui module la puissance.\n"
            "\n"
            "PRÉREQUIS CÔTÉ MACHINE : motion.analog-out-00 doit alimenter la\n"
            "chaîne de puissance du laser dans le HAL. Sans ce câblage, le\n"
            "laser ne tire PAS et le job sort blanc, sans erreur. Le HAL de la\n"
            "PrintNC additionne les deux sources (sum2), donc les deux modes\n"
            "fonctionnent et l'on peut basculer sans rien recâbler.\n"
            "Ignoré en GRBL/grblHAL, qui ne connaissent pas M67.")
        form.addRow(self.chk_m67)

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

        self.chk_origin_bbox = QtWidgets.QCheckBox(
            "Recadrer au zéro pièce (coin bas-gauche à 0,0)")
        self.chk_origin_bbox.setChecked(bool(settings.get("gcode_origin_bbox", True)))
        self.chk_origin_bbox.setToolTip(
            "À l'écriture, décale chaque G-code pour que le coin BAS-GAUCHE\n"
            "du parcours (min X, min Y) tombe sur (0,0) : le job démarre à\n"
            "ton zéro machine quel que soit l'endroit où le dessin est posé\n"
            "dans le document. Recommandé pour la gravure/découpe à plat.\n"
            "Décoche pour un marquage sur une pièce 3D placée à un endroit\n"
            "précis (la position du dessin est alors respectée). Sans effet\n"
            "sur le Test d'offsets (jamais recadré).")
        form.addRow(self.chk_origin_bbox)

        # G-code personnalisé GLOBAL : un seul couple avant/après pour tous
        # les modes (remplace les anciennes sections par panneau).
        self.txt_gcode_pre = _gcode_editor("G-code inséré avant chaque job (optionnel)")
        self.txt_gcode_pre.setToolTip(
            "Texte libre inséré tel quel au début de CHAQUE job généré\n"
            "(après l'en-tête et la remontée de sécurité, avant l'armement\n"
            "du laser ; une seule fois par job combiné). Ex. : M-code\n"
            "d'air assist, message, attente.")
        self.txt_gcode_pre.setPlainText(settings.get("gcode_pre_global", ""))
        form.addRow("G-code avant :", self.txt_gcode_pre)

        self.txt_gcode_post = _gcode_editor("G-code inséré après chaque job (optionnel)")
        self.txt_gcode_post.setToolTip(
            "Texte libre inséré tel quel à la fin de CHAQUE job généré\n"
            "(après le désarmement du laser, avant la fin de programme ;\n"
            "une seule fois par job combiné).")
        self.txt_gcode_post.setPlainText(settings.get("gcode_post_global", ""))
        form.addRow("G-code après :", self.txt_gcode_post)

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

    def _browse_planches_dir(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.form, "Dossier des planches redressées",
            self.edt_planches_dir.text() or os.path.expanduser("~"))
        if path:
            self.edt_planches_dir.setText(path)

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
        idx_d = self.combo_dialect.findData(s.get("gcode_dialect", "linuxcnc"))
        self.combo_dialect.setCurrentIndex(max(0, idx_d))
        self.chk_m67.setChecked(bool(s.get("puissance_par_m67", False)))
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

    def _on_export_all(self):
        """Exporte tous les réglages + photos dans une archive .zip choisie
        par l'utilisateur (sauvegarde à ranger en lieu sûr)."""
        default = os.path.join(os.path.expanduser("~"),
                               "laseratelier_sauvegarde.zip")
        path, _f = QtWidgets.QFileDialog.getSaveFileName(
            self.form, "Exporter réglages + photos", default,
            "Archive ZIP (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        ok, msg = core.export_all(path)
        (QtWidgets.QMessageBox.information if ok
         else QtWidgets.QMessageBox.critical)(self.form, "Export", msg)

    def _on_import_all(self):
        """Restaure une sauvegarde .zip (remplace réglages + photos). Ferme le
        panneau ensuite : ses champs sont devenus obsolètes, cliquer OK
        ré-écraserait la config tout juste importée."""
        path, _f = QtWidgets.QFileDialog.getOpenFileName(
            self.form, "Importer une sauvegarde", os.path.expanduser("~"),
            "Archive ZIP (*.zip)")
        if not path:
            return
        if QtWidgets.QMessageBox.warning(
                self.form, "Importer une sauvegarde",
                "Cela REMPLACE tous les réglages actuels (préréglages, "
                "nuancier, calibration, profils laser…) et rétablit les photos "
                "de l'archive. Continuer ?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return
        ok, msg = core.import_all(path)
        if not ok:
            QtWidgets.QMessageBox.critical(self.form, "Import", msg)
            return
        QtWidgets.QMessageBox.information(
            self.form, "Import",
            msg + "\n\nLe panneau Réglages va se fermer : rouvre-le (ou "
            "redémarre FreeCAD) pour voir tous les champs à jour.")
        Gui.Control.closeDialog()

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
        # Champ LARGE, et une consigne : ce nom n'est plus une étiquette
        # interne depuis la v2.22, il part dans le nom de fichier des
        # planches redressées. Une case de 15 caractères invitait à taper
        # « Bleu » là où il faut une référence de matériel.
        dlg = QtWidgets.QInputDialog(self.form)
        dlg.setWindowTitle("Renommer le laser")
        dlg.setInputMode(QtWidgets.QInputDialog.TextInput)
        dlg.setLabelText(
            "Nom du module laser — mets sa RÉFÉRENCE, pas une couleur.\n\n"
            "Il part dans le nom des planches redressées et dans leur fiche :\n"
            "c'est lui qui dit à quel matériel appartiennent les mesures, et\n"
            "ce qui permet à quelqu'un ayant le même module de les reprendre.\n\n"
            "Exemple : LT-80W-AA-PRO")
        dlg.setTextValue(core.active_laser_name())
        for champ in dlg.findChildren(QtWidgets.QLineEdit):
            champ.setMinimumWidth(420)       # le dialogue s'élargit pour suivre
        if not dlg.exec() or not dlg.textValue().strip():
            return
        core.rename_laser(core.active_laser_id(), dlg.textValue().strip())
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
        if not self.edt_planches_dir.text().strip():
            QtWidgets.QMessageBox.warning(
                self.form, "Préférences",
                "Le dossier des planches redressées ne peut pas être vide.")
            return False
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
            "gcode_dialect": self.combo_dialect.currentData(),
            "puissance_par_m67": self.chk_m67.isChecked(),
            "gcode_dir": self.edt_gcode_dir.text().strip(),
            "planches_dir": self.edt_planches_dir.text().strip(),
            "gcode_origin_bbox": self.chk_origin_bbox.isChecked(),
            "sections_accordeon": self.chk_accordeon.isChecked(),
            "gcode_pre_global": self.txt_gcode_pre.toPlainText(),
            "gcode_post_global": self.txt_gcode_post.toPlainText(),
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
            "label_power": self.spn_label_power.value(),
            "label_feed": self.spn_label_feed.value(),
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
