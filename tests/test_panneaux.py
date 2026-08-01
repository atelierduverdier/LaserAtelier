# -*- coding: utf-8 -*-
"""Garde-fou large : tout s'ouvre, tout génère, rien ne dit du vide.

Trois bugs du 29/07/2026 seraient tombés ici, et aucun n'était subtil :
une coche verte sans texte sous « Trait & matière », un réglage de défocus
affiché dans un tramage qui grave au foyer, et un tramage qui refusait de
s'afficher parce que la vitesse par défaut du panneau ne lui convenait
pas. Trois symptômes différents, une seule cause : personne ne vérifiait
que chaque tramage, pris un par un, produit quelque chose de cohérent.
"""
import inspect
import sys

from harness import preparer, texte, image_demo

h = preparer()
core, tp = h.core, h.tp

# --- 1. Tous les panneaux se construisent -------------------------------
ouverts, rates, sautes = [], [], []
for nom in sorted(dir(tp)):
    if not nom.startswith("TaskPanel"):
        continue
    cls = getattr(tp, nom)
    requis = [p for _n, p in list(inspect.signature(cls.__init__)
                                  .parameters.items())[1:]
              if p.default is inspect.Parameter.empty
              and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]
    if requis:
        sautes.append(nom)          # exige une vraie sélection 3D
        continue
    try:
        cls()
        ouverts.append(nom)
    except Exception as exc:
        rates.append((nom, repr(exc)[:120]))
for nom, exc in rates:
    print("   ÉCHEC {} : {}".format(nom, exc))
assert not rates, rates
assert len(ouverts) >= 14, ouverts
print("1. {} panneaux construits sans erreur ({} sautés : ils exigent une "
      "sélection 3D) OK".format(len(ouverts), len(sautes)))

# --- 2. Le panneau photo : chaque tramage, un par un --------------------
img = image_demo()
assert img, "aucune image de test disponible"
p = tp.TaskPanelHalftone()
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
assert u"Hêtre" in mats, mats
p.combo_photo_mat.setCurrentIndex(mats.index(u"Hêtre"))
p.edt_image.setText(img)
p.spn_width.setValue(40.0)
p.spn_gamma.setValue(1.0)

# Chaque tramage a un régime qui lui convient : imposer la vitesse des
# lignes calibrées aux « lignes gravées » les fait refuser, à juste titre.
REGIMES = {"enfle": (0.30, 800.0)}
DEFAUT = (0.80, 2000.0)

assert p.combo_mode.count() == len(tp._TRAMAGES), (
    "la liste déroulante et _TRAMAGES ont divergé",
    p.combo_mode.count(), len(tp._TRAMAGES))
for idx in range(p.combo_mode.count()):
    p.combo_mode.setCurrentIndex(idx)
    nom = p.combo_mode.currentText()
    pas, feed = REGIMES.get(tp._TRAMAGES[idx]["cle"], DEFAUT)
    p.spn_pitch.setValue(pas)
    p.spn_line_feed.setValue(feed)
    rows = p._build_rows(silent=True, max_cells=30000)
    assert rows, (idx, nom, "grille vide")

    g = p._generate(rows, quiet=True)
    assert g, (idx, nom, "aucun G-code")
    # Tout job laser doit armer, désarmer et finir : un G-code tronqué
    # laisserait le faisceau armé.
    assert "M2" in g, (nom, "pas de fin de programme")
    assert core.cmd_path_blend() in g, (nom, "G64 absent")
    # Règle non négociable : jamais de G4 (pause) FAISCEAU ALLUMÉ. Le HAL
    # met la puissance à zéro à l'arrêt, donc une pause allumée ne grave
    # rien -- le job sortirait silencieusement blanc. On suit l'état du
    # faisceau ligne à ligne au lieu de chercher un motif dans le texte.
    s_courant = 0
    for l in g.split("\n"):
        import re as _re
        ms = _re.search(r"\bS(\d+)", l)
        if ms:
            s_courant = int(ms.group(1))
        if l.startswith("G4 "):
            assert s_courant == 0, (nom, "pause faisceau allumé", l)

    img_ap, note = p._render_photo_preview(rows, largeur_px=200)
    assert img_ap is not None, (idx, nom, note)
    assert note and len(note) > 5, (idx, nom, "note d'aperçu vide")

    # Le verdict « Trait & matière » ne doit JAMAIS être une coche nue.
    v = texte(p.lbl_regime)
    assert len(v) > 8, (idx, nom, "verdict vide", repr(v))
    print("   [{}] {:<44} {:>6} lignes, aperçu + verdict OK".format(
        idx, nom[:44], len(g.split("\n"))))
print("2. les {} tramages génèrent, s'affichent et se prononcent OK".format(
    len(tp._TRAMAGES)))

# --- 3. L'INTERFACE SUIT LA TABLE, pour chaque tramage -------------------
# Depuis v2, un tramage est une ligne de `_TRAMAGES` et tout ce qui est
# visible ou actif s'en déduit. Ce test ferme la boucle : il ne réécrit pas
# les rangs à la main (c'était le défaut d'avant -- deux listes d'index à
# garder d'accord, celle du code et celle du test), il relit la table et
# exige que le panneau la respecte. Ajouter un tramage sans câbler l'un de
# ses réglages échoue ici, sur la ligne fautive.
CHAMPS = (
    # (libellé, widget, trait attendu, "visible" ou "actif")
    ("largeur du point", "spn_spot_width", lambda t: not t["au_foyer"], "visible"),
    ("vitesse des lignes", "spn_line_feed", lambda t: t["balayage"], "visible"),
    ("matériau", "combo_photo_mat", tp._tramage_veut_materiau, "visible"),
    ("espacement de trame", "spn_dot_spacing",
     lambda t: t["reglage"] == "espacement", "visible"),
    ("trait mini", "spn_line_min",
     lambda t: t["reglage"] == "trait_mini", "visible"),
    ("puissance", "spn_power", lambda t: t["puissance"], "actif"),
    ("seuil blanc", "spn_white", lambda t: t["seuil_blanc"], "actif"),
    ("durée maxi", "spn_dwell_max", lambda t: not t["balayage"], "actif"),
    ("durée mini", "spn_dwell_min", lambda t: t["duree_variable"], "actif"),
)
cles = [t["cle"] for t in tp._TRAMAGES]
assert len(set(cles)) == len(cles), ("deux tramages partagent une clé", cles)
for idx, t in enumerate(tp._TRAMAGES):
    p.combo_mode.setCurrentIndex(idx)
    assert p.combo_mode.currentText() == t["nom"], (idx, t["nom"])
    assert p.combo_mode.currentData() == t["cle"], (idx, t["cle"])
    assert p._tramage() is t, ("_tramage() ne rend pas la bonne ligne", idx)
    for libelle, attr, attendu, genre in CHAMPS:
        w = getattr(p, attr)
        reel = (not w.isHidden()) if genre == "visible" else w.isEnabled()
        assert reel == bool(attendu(t)), (
            t["cle"], libelle, genre, "réel={}".format(reel),
            "table={}".format(bool(attendu(t))))
    print("   {:<10} {} champs conformes à sa ligne de table OK".format(
        t["cle"], len(CHAMPS)))
print("3. l'interface se déduit de _TRAMAGES, aucun rang codé en dur OK")

# --- 3bis. Un tramage sans générateur REFUSE, il ne bricole pas ----------
# Le repli de `_generate` produit une trame de POINTS. Un tramage ajouté à
# la table sans être routé y tomberait et sortirait du G-code valide pour le
# mauvais tramage -- le pire des cas, indétectable à la lecture du fichier.
faux = dict(tp._TRAMAGES[0], cle="tramage_fantome", nom="Fantôme")
vraie_table = tp._TRAMAGES
tp._TRAMAGES = vraie_table + (faux,)
try:
    p.combo_mode.addItem(faux["nom"], faux["cle"])
    p.combo_mode.setCurrentIndex(len(vraie_table))
    p.spn_pitch.setValue(0.80)
    p.spn_line_feed.setValue(2000.0)
    rows = p._build_rows(silent=True, max_cells=30000)
    assert p._generate(rows, quiet=True) is None, (
        "un tramage non routé a produit du G-code (une trame de points) "
        "au lieu de refuser")
finally:
    p.combo_mode.removeItem(len(vraie_table))
    tp._TRAMAGES = vraie_table
    p.combo_mode.setCurrentIndex(0)
print("3bis. tramage déclaré mais non routé : refus explicite, pas de trame "
      "de points muette OK")

# --- 4. Un refus est un refus MOTIVÉ ------------------------------------
p.combo_mode.setCurrentIndex(6)
p.spn_line_feed.setValue(2000.0)        # au-delà, le trait n'enfle plus
rows = p._build_rows(silent=True, max_cells=30000)
im, note = p._render_photo_preview(rows, largeur_px=200)
assert im is None, "le tramage aurait dû refuser"
rapide = core.swell_max_feed(u"Hêtre")
assert rapide and "F{:.0f}".format(rapide) in note, (
    "un refus doit nommer la vitesse qui marche, pas seulement celle qui "
    "échoue", note)
assert p._generate(rows, quiet=True) is None, \
    "l'aperçu refuse mais le générateur produit quand même du G-code"
print("4. hors régime : aperçu ET générateur refusent, en nommant F{:.0f} "
      "OK".format(rapide))


# --- 5. Le sablier ne doit pas survivre au calcul ----------------------
# Signalé le 31/07/2026 : « le pointeur de ma souris est en mode travail,
# pourtant il fonctionne bien ». Le curseur d'attente enveloppait le rendu
# ET l'affichage, or _show_image_dialog est MODAL : le sablier restait donc
# affiché tout le temps que la fenêtre était ouverte. On lit le curseur au
# moment PRÉCIS où le dialogue s'ouvre -- c'est là qu'il se voit.
from PySide6 import QtWidgets

p5 = tp.TaskPanelHalftone()
p5.edt_image.setText(image_demo())
p5.spn_width.setValue(30.0)
p5.combo_mode.setCurrentIndex(0)

vu = {}
vrai_dialog = tp._show_image_dialog
tp._show_image_dialog = lambda img, titre: vu.__setitem__(
    "pendant", QtWidgets.QApplication.overrideCursor())
try:
    p5._on_photo_preview()
finally:
    tp._show_image_dialog = vrai_dialog

assert "pendant" in vu, "l'aperçu n'a pas ouvert de fenêtre"
assert vu["pendant"] is None, (
    "le sablier est encore forcé pendant que la fenêtre modale est "
    "affichée : le curseur annonce un calcul qui est fini")
assert QtWidgets.QApplication.overrideCursor() is None, (
    "un curseur forcé a survécu à l'aperçu")
print("5. aperçu photo : curseur normal pendant l'affichage, et aucun "
      "curseur forcé qui survive OK")


# --- 6. Reprendre la sélection : les CINQ panneaux, pas quatre ---------
# Le bouton existait depuis longtemps mais manquait dans Hachures, et
# surtout il ne s'annonçait pas : Christophe a redemandé la fonction le
# 31/07/2026 alors qu'elle était sous ses yeux dans Marquage. D'où une
# ligne d'état qui passe au rouge dès que la vue 3D montre autre chose.
from PySide6 import QtWidgets as _Qw, QtCore as _Qc


class _FauxObjet:
    def __init__(self, nom):
        self.Name = nom


class _FauxSel:
    def __init__(self, nom, subs=()):
        self.Object = _FauxObjet(nom)
        self.SubElementNames = tuple(subs)


# La signature doit distinguer les objets ET leurs sous-éléments, sans
# dépendre de l'ordre de clic.
_s = tp._signature_selection
assert _s([_FauxSel("L", ("Edge1",))]) == _s([_FauxSel("L", ("Edge1",))])
assert _s([_FauxSel("L", ("Edge1",))]) != _s([_FauxSel("L", ("Edge2",))])
assert _s([_FauxSel("A")]) != _s([_FauxSel("A"), _FauxSel("B")])
assert _s([_FauxSel("A"), _FauxSel("B")]) == _s([_FauxSel("B"), _FauxSel("A")])

_panneaux = (("Hachures 2D", tp.TaskPanelHatch),
             ("Gravure remplie", tp.TaskPanelFilledEngraving),
             ("Marquage de motif", tp.TaskPanelCurved),
             ("Découpe plate", tp.TaskPanelFlat),
             ("Découpe courbe", tp.TaskPanelCurvedCut))
_vraie_sel = tp.Gui.Selection.getSelectionEx
for _nom, _cls in _panneaux:
    _p = _cls([])
    _btn = [x for x in _p.form.findChildren(_Qw.QPushButton)
            if "reprendre la s" in x.text().lower()]
    assert _btn, ("panneau sans bouton de reprise", _nom)
    _lbl = [x for x in _p.form.findChildren(_Qw.QLabel)
            if "Sélection 3D" in x.text()]
    assert _lbl, ("panneau sans indicateur de sélection", _nom)
    assert not _btn[0].isEnabled(), (
        "sélection identique : le bouton ne doit rien proposer", _nom)
    # La vue 3D montre maintenant autre chose.
    tp.Gui.Selection.getSelectionEx = lambda: [_FauxSel("Trait", ("Edge1",))]
    try:
        for _tm in _btn[0].findChildren(_Qc.QTimer):
            _tm.timeout.emit()
        assert _btn[0].isEnabled(), ("sélection différente : le bouton doit "
                                     "s'activer", _nom)
        assert "différente" in texte(_lbl[0]), (_nom, texte(_lbl[0]))
    finally:
        tp.Gui.Selection.getSelectionEx = _vraie_sel
    assert hasattr(_p, "_on_recapture_selection"), _nom
print("6. les 5 panneaux à sélection ont bouton + indicateur, et l'indicateur "
      "s'allume quand la vue 3D diverge OK")

print("\nTOUS LES TESTS panneaux PASSENT")


# --- Redressement de photo + mesure A→B (v2.16.0) --------------------
# Ces deux fonctions parlent à OpenCV (absent du python FreeCAD) et à la
# vue 3D (inexistante en headless) : on ne peut donc PAS les exécuter
# ici. Ce qu'on vérifie, c'est ce qui casserait en silence -- une fonction
# disparue, un bouton débranché, un rappel Coin laissé accroché.
import os as _os
import re as _re2
from PySide6 import QtWidgets as _Qt

assert hasattr(tp, "_redresser_photo_planche")
assert hasattr(tp, "_cotes_mire_defaut")
assert hasattr(tp, "_python_systeme")
assert hasattr(tp, "_importer_image_a_l_echelle")

# Les cotes proposees viennent du generateur COURANT, jamais d'un nombre
# ecrit en dur : c'est ce qui les empeche de se perimer.
for planche, gen in (("planche1", core.generate_gcode_planche_focus),
                     ("planche2", core.generate_gcode_planche_defocus)):
    prop = tp._cotes_mire_defaut(planche)
    m = _re2.search(r"rectangle de ([\d.]+) x ([\d.]+) mm", gen(quiet=True))
    assert prop == "{:.0f}-{:.0f}".format(float(m.group(1)), float(m.group(2))), (
        planche, prop, m.group(1), m.group(2))
assert tp._cotes_mire_defaut("inconnue") == "140-60"
print("redressement : cotes proposees tirees du generateur courant OK")

# Le script externe existe, et il expose bien le contrat que le panneau
# consomme (--json, --base, --sortie). Un renommage silencieux la-bas
# casserait le bouton ici.
_script = _os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                        "outils", "redresser_photo.py")
assert _os.path.exists(_script), _script
_src = open(_script).read()
for opt in ("--json", "--base", "--sortie", "--pxmm", "--gcode"):
    assert '"{}"'.format(opt) in _src, opt
# L'apercu leger : le PNG de mesure pese 55 Mo et la galerie ne doit pas le
# dupliquer (290 Mo accumules en une matinee le 01/08/2026).
assert '"apercu"' in _src, "le script doit annoncer un apercu dans son JSON"
assert 'IMWRITE_JPEG_QUALITY' in _src, "l'apercu doit etre un JPEG, pas un PNG"
print("redressement : outils/redresser_photo.py present, options du contrat OK")

# La galerie des planches lit sous LES MEMES cles que celles sous
# lesquelles le redressement range. Tant que les deux listes etaient
# ecrites separement, elles pouvaient diverger -- et la galerie n'existait
# meme pas : les photos partaient quelque part que rien n'affichait, sous
# un message promettant « rangee dans les photos du resultat ».
assert hasattr(tp, "_PLANCHES")
_cles = {c for _l, c in tp._PLANCHES}
assert _cles == {"planche1", "planche2", "planche_autre"}, _cles
_hote2 = _Qt.QWidget()
_form2 = _Qt.QFormLayout(_hote2)
tp._boutons_planches(_form2, lambda *a, **k: None)
_combos = [w for w in _hote2.findChildren(_Qt.QComboBox)
           if {w.itemData(i) for i in range(w.count())} == _cles]
assert _combos, (
    "aucune liste deroulante n'offre les cles des planches : la galerie "
    "n'est pas branchee, les photos rangees ne sont affichees NULLE PART")
# ... et une vignette cliquable pour les regarder, pas seulement une liste.
assert any(l.cursor().shape() == tp.QtCore.Qt.PointingHandCursor
           for l in _hote2.findChildren(_Qt.QLabel)), \
    "pas de vignette cliquable dans la galerie des planches"
print("redressement : galerie des planches branchee sur les memes cles OK")

# Reposer une planche DEJA redressee, sans recliquer les quatre croix.
# Le 01/08/2026, FreeCAD rouvert sans que le document ait ete enregistre :
# l'image etait toujours sur le disque, et le seul moyen de la remettre
# etait de refaire tout le redressement.
assert hasattr(tp, "_reposer_planche_redressee")
assert any("Reposer" in b.text() for b in _hote2.findChildren(_Qt.QPushButton)), \
    "pas de bouton pour reposer une planche deja redressee"
# La fiche .json doit etre ecrite TOUJOURS, pas seulement quand le panneau
# demande --json : sinon une image redressee a la main n'a pas sa taille.
_i_fiche = _src.index('os.path.splitext(sortie)[0] + ".json"')
_i_opt = _src.index("if a.json:")
assert _i_fiche < _i_opt, (
    "la fiche .json doit etre ecrite avant/hors du bloc « if a.json », "
    "sinon elle depend de l'appelant")
print("redressement : bouton « Reposer » + fiche .json toujours ecrite OK")

# --- Dossier a part, et le LASER dans le nom (v2.22.0) ---------------
# Une largeur brulee n'a de sens que pour le module qui l'a gravee : deux
# diodes differentes donnent deux tables differentes, et inversement le
# MEME module rend ces mesures reutilisables telles quelles par quelqu'un
# d'autre. Sans le laser sur le fichier, cette reutilisation demande de se
# souvenir -- autant dire qu'elle n'aura pas lieu.
assert ("planches_dir", "PLANCHES_DIR", str) == core._USER_SETTINGS[
    [k for k, *_ in core._USER_SETTINGS].index("planches_dir")][:3]
assert '"planches_dir"' in open(
    _os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                  "task_panels.py")).read(), "le reglage doit etre enregistre"

# Un slug ne doit JAMAIS contenir de separateur : « Diode 40W/gauche »
# ecrirait dans un sous-dossier, ou nulle part.
for brut in ("LT-80W-AA-PRO", "Bleu 450 nm", "Diode 40W (déportée)", "a//b", "  "):
    slug = core.slug_fichier(brut, "laser")
    assert slug and "/" not in slug and " " not in slug, (brut, slug)
assert core.slug_fichier("Diode 40W (déportée)") == "Diode-40W-deportee"

_nom = core.nom_planche_redressee("planche1", "20260801-0745",
                                  laser="LT-80W-AA-PRO")
assert _nom == "LT-80W-AA-PRO_planche1_20260801-0745_redresse", _nom
assert core.nom_planche_redressee("planche2", "20260801-0745", "_2",
                                  laser="Bleu 450 nm").startswith("Bleu-450-nm_")

# Le dossier est CREE au besoin -- mais jamais celui de l'utilisateur
# pendant un test : on repointe la globale sur un jetable.
import tempfile as _tf
_ancien = core.PLANCHES_DIR
core.PLANCHES_DIR = _os.path.join(_tf.mkdtemp(), "planches")
assert not _os.path.isdir(core.PLANCHES_DIR)
assert core.dossier_planches() == core.PLANCHES_DIR
assert _os.path.isdir(core.PLANCHES_DIR), "le dossier doit etre cree"
core.PLANCHES_DIR = _ancien

# Le panneau ecrit LA-BAS, plus a cote de la photo d'origine.
_tp_src = open(_os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                             "task_panels.py")).read()
_i = _tp_src.index("def _redresser_photo_planche")
_corps = _tp_src[_i:_i + 6000]
assert "core.dossier_planches()" in _corps and "core.nom_planche_redressee" in _corps
assert '"--laser"' in _corps, "le laser doit partir dans la fiche du redressement"
print("redressement : dossier a part + laser dans le nom du fichier OK")

# --- Supprimer une planche, fichiers compris (v2.23.0) ---------------
# Regraver une planche mieux reussie est le cas NORMAL : l'ancienne doit
# pouvoir partir. Le bouton « Supprimer la photo affichee » de la galerie
# n'enlevait que l'apercu et laissait les 55 Mo de l'image de mesure.
import json as _js
_ancien2 = core.PLANCHES_DIR
core.PLANCHES_DIR = _os.path.join(_tf.mkdtemp(), "planches")
_d = core.dossier_planches()


def _faux_planche(nom, taille, err):
    b = _os.path.join(_d, nom)
    open(b + ".png", "wb").write(b"x" * taille)
    open(b + "_apercu.jpg", "wb").write(b"x" * 100)
    open(b + "_reperes.jpg", "wb").write(b"x" * 100)
    _js.dump({"fichier": b + ".png", "laser": "LT-80W-AA-PRO",
              "largeur_mm": 256.0, "hauteur_mm": 86.0,
              "reglette": {"erreur_pct": err}}, open(b + ".json", "w"))
    return b


_a = _faux_planche("LT-80W-AA-PRO_planche1_20260801-0745_redresse", 4000, 0.12)
_b = _faux_planche("LT-80W-AA-PRO_planche1_20260801-0745_2_redresse", 3000, 1.30)
_lst = core.planches_redressees()
assert len(_lst) == 2, _lst
assert all(len(p["fichiers"]) == 4 for p in _lst), "4 fichiers par planche"
assert _lst[0]["infos"]["laser"] == "LT-80W-AA-PRO"
assert _lst[0]["octets"] > 0

# LE piege : « ..._0745_redresse » est un prefixe possible d'un voisin.
# Un startswith brut emporterait la planche d'a cote, et une suppression
# n'a pas droit a l'a-peu-pres.
_n, _o = core.supprimer_planche(_a)
assert _n == 4, _n
assert _o >= 4000, _o
_restant = core.planches_redressees()
assert [p["base"] for p in _restant] == [_b], (
    "la planche voisine a ete emportee par la suppression : " + str(_restant))
assert _os.path.isfile(_b + ".png") and _os.path.isfile(_b + "_apercu.jpg")
core.PLANCHES_DIR = _ancien2
assert hasattr(tp, "_gerer_planches_redressees")
assert any("supprimer" in b.text().lower()
           for b in _hote2.findChildren(_Qt.QPushButton)), \
    "pas de bouton pour gerer/supprimer des planches"
print("planches : inventaire, suppression des 4 fichiers, voisine intacte OK")

# Mesure A→B : sans vue 3D, le bouton doit REFUSER proprement et ne
# laisser aucun rappel branché -- un callback oublié sur la vue rend
# FreeCAD inutilisable jusqu'au redemarrage.
class _FauxParent:
    form = None
_hote = _Qt.QWidget()          # garder une reference : sans elle, Qt
_form = _Qt.QFormLayout(_hote)  # detruit le widget et le layout avec
_ctrl = tp._MesuresPlanchesControleur(_form, _FauxParent(), lambda: "Hêtre")
assert _ctrl._vue3d() is None, "pas de vue 3D attendue en headless"
_ctrl._on_mesurer()
assert _ctrl._mesure_cb is None, "aucun rappel ne doit rester branché"
assert "vue 3D" in _ctrl.lbl_mesure.text(), _ctrl.lbl_mesure.text()
_ctrl._fin_mesure()          # doit etre sur meme si rien n'est branche
assert _ctrl._mesure_cb is None
print("mesure A->B : refus propre sans vue 3D, aucun rappel laisse OK")

# --- La case visee doit SURVIVRE au clic sur le bouton (v2.17.1) -----
# Defaut du 01/08/2026, au premier usage reel : la cible etait lue par
# QApplication.focusWidget() DANS le rappel de clic, donc APRES que le
# bouton ait pris le focus -- toujours None. Le panneau repondait « aucune
# case n'avait le focus : clique une case AVANT » a quelqu'un qui venait
# exactement de le faire.
from PySide6 import QtCore as _QtC, QtGui as _QtG

assert _ctrl.btn_mesurer.focusPolicy() == _QtC.Qt.NoFocus, (
    "le bouton doit etre NoFocus, sinon il vole le cadre de focus a la case")

_case = _ctrl.grille_focus.cells()[(1000.0, 800.0)]
_QtC.QCoreApplication.sendEvent(_case, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
assert _ctrl._derniere_case is _case, "le focus d'une case doit la memoriser"
assert _ctrl._serie == [], "une nouvelle case repart d'une serie vide"
assert "S1000 / F800" in _ctrl.lbl_mesure.text(), _ctrl.lbl_mesure.text()

# Le bouton peut bien prendre le focus a son tour : la cible tient.
_QtC.QCoreApplication.sendEvent(_ctrl.btn_mesurer,
                                _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
assert _ctrl._derniere_case is _case, (
    "la case visee ne doit pas etre perdue quand le bouton prend le focus -- "
    "c'est EXACTEMENT le defaut que ce test gele")
print("mesure A->B : la case visee survit au focus du bouton OK")

# La moyenne : trois mesures sur la meme case -> moyenne ecrite dans la
# case, etendue annoncee. Le controle se demontre : la valeur ecrite n'est
# aucune des trois mesures prises isolement.
_ctrl._mesure_cible = _case
_ctrl._serie = []
for _d in (0.300, 0.340, 0.320):
    _txt = _ctrl._encaisser_mesure(_d, _d, 0.0)
assert abs(_case.value() - 0.32) < 1e-6, _case.value()
assert "moyenne de 3" in _txt, _txt
assert "0.040" in _txt or "0,040" in _txt, "l'etendue doit etre annoncee : " + _txt
assert _case.value() not in (0.300, 0.340), (
    "la case doit contenir la MOYENNE, pas la derniere mesure")
# Re-cliquer la case repart de zero : c'est le geste qui annule une serie.
_QtC.QCoreApplication.sendEvent(_case, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
assert _ctrl._serie == [], "re-cliquer la case doit vider la serie"
print("mesure A->B : moyenne de 3 = 0,320 mm, etendue 0,040, remise a zero OK")

# Les grilles de defocus sont DETRUITES a chaque reconstruction : garder un
# pointeur dessus ferait planter le prochain setValue sur un objet C++ mort.
_ctrl._reconstruire_niveaux([15.0, 36.0])
_defoc = _ctrl.grilles_defocus[36.0].cells()[(1000.0, 200.0)]
_QtC.QCoreApplication.sendEvent(_defoc, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
assert _ctrl._derniere_case is _defoc
assert "defocus 36 mm" in _ctrl._nom_case(_defoc).replace("é", "e"), \
    _ctrl._nom_case(_defoc)
_ctrl._reconstruire_niveaux([15.0])
assert _ctrl._derniere_case is None, (
    "une reconstruction des grilles doit oublier la case visee : elle vient "
    "d'etre detruite cote C++")
print("mesure A->B : cible oubliee a la reconstruction des grilles OK")

# --- Un bloc de mesure SOUS CHAQUE grille (v2.19.0) ------------------
# Un seul bouton en bas obligeait a faire defiler le panneau entre chaque
# valeur. Les blocs des grilles de defocus sont detruits a chaque
# reconstruction : la liste doit etre elaguee, sinon on parle a un widget
# C++ mort au milieu d'une mesure.
_ctrl._reconstruire_niveaux([15.0, 36.0, 60.0])
assert len(_ctrl._blocs) == 4, "1 bloc foyer + 3 defocus : " + str(len(_ctrl._blocs))
assert _ctrl._blocs[0].grille is _ctrl.grille_focus
_ctrl._reconstruire_niveaux([15.0])
assert len(_ctrl._blocs) == 2, "1 bloc foyer + 1 defocus : " + str(len(_ctrl._blocs))
assert len(_ctrl._blocs_vivants()) == 2, "aucun bloc mort ne doit rester"

# Le message part dans le bloc de LA grille concernee, pas trois grilles
# plus bas -- sinon le bouton rapproche ne sert a rien.
_case_d = _ctrl.grilles_defocus[15.0].cells()[(800.0, 400.0)]
_QtC.QCoreApplication.sendEvent(_case_d, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
_bloc_d = _ctrl._bloc_de(_case_d)
assert _bloc_d is not _ctrl._blocs[0], "le bloc du defocus n'est pas celui du foyer"
assert "S800 / F400" in _bloc_d.lbl.text(), _bloc_d.lbl.text()
assert "S800 / F400" not in _ctrl.lbl_mesure.text(), (
    "le message ne doit pas partir dans le bloc du foyer")
print("mesure A->B : un bloc par grille, message dans le bon bloc OK")

# --- Mesurer EN TRAVERS, pas en diagonale (v2.19.0) ------------------
# La distance directe vaut hypot(dx, dy) : elle est TOUJOURS >= la largeur
# reelle des que les deux clics sont decales lateralement, et rien ne le
# signale. Le controle se demontre : les deux modes doivent differer.
import types as _types
_A = _types.SimpleNamespace(x=10.000, y=20.000)
_B = _types.SimpleNamespace(x=10.200, y=20.300)   # trait de 0,30, clic decale de 0,20

_ctrl._perp = True
_d_perp, _dx, _dy = _ctrl._distance(_A, _B)
assert abs(_d_perp - 0.300) < 1e-9, _d_perp
assert abs(_dx - 0.200) < 1e-9 and abs(_dy - 0.300) < 1e-9

_ctrl._perp = False
_d_dir = _ctrl._distance(_A, _B)[0]
assert abs(_d_dir - 0.3605551) < 1e-6, _d_dir
assert _d_dir > _d_perp, (
    "si les deux modes donnent la meme chose, ce test ne prouve rien")
assert (_d_dir / _d_perp - 1) > 0.20, (
    "20 % d'ecart attendu sur ce cas : c'est l'erreur que le mode en "
    "travers supprime")

# Un trait VERTICAL doit marcher aussi : c'est la plus grande composante
# qui est retenue, pas dy en dur.
_ctrl._perp = True
_V = _types.SimpleNamespace(x=10.300, y=20.200)
assert abs(_ctrl._distance(_A, _V)[0] - 0.300) < 1e-9
print("mesure A->B : en travers 0,300 mm contre 0,361 en direct (+20 %) OK")

# Le mode est UN reglage : les cases a cocher se suivent, sinon deux blocs
# annonceraient deux modes differents pour la meme mesure.
_ctrl._blocs[1].chk_perp.setChecked(False)
assert _ctrl._perp is False
assert not _ctrl._blocs[0].chk_perp.isChecked(), "les cases doivent se suivre"
_ctrl._blocs[0].chk_perp.setChecked(True)
assert all(b.chk_perp.isChecked() for b in _ctrl._blocs)
print("mesure A->B : le mode reste unique sur tous les blocs OK")


# --- L'AppImage empoisonne tout sous-processus (v2.16.1) -------------
# Premier clic sur « Redresser une photo » le 01/08/2026 : « Fatal Python
# error: Failed to import encodings module ». L'AppImage FreeCAD impose
# PYTHONHOME à tout son environnement, donc le python SYSTÈME cherchait sa
# bibliothèque standard dans l'AppImage et mourait avant d'exécuter une
# ligne. Les variables Qt/LD sont tout aussi dangereuses ici : OpenCV 5
# ouvre sa fenêtre avec Qt6, et lui faire charger les Qt de l'AppImage
# plante sans message utile.
import subprocess as _sp

for _v in ("PYTHONHOME", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH"):
    assert _v in tp._VARS_APPIMAGE, _v
_pollue = dict(_os.environ)
_pollue["PYTHONHOME"] = "/tmp/.mount_FreeCAxxxxx/usr"
_propre = {k: v for k, v in _pollue.items() if k not in tp._VARS_APPIMAGE}
assert "PYTHONHOME" not in _propre

_py = tp._python_systeme()
if _py:
    # Le contrôle se DÉMONTRE : pollué, ça meurt ; assaini, ça marche.
    _ko = _sp.run([_py, "-c", "print(1)"], env=_pollue,
                  capture_output=True, text=True)
    _ok = _sp.run([_py, "-c", "print(1)"], env=_propre,
                  capture_output=True, text=True)
    assert _ko.returncode != 0, (
        "PYTHONHOME de l'AppImage devrait tuer le python systeme -- si ce "
        "test passe un jour, c'est que l'environnement a change, pas que le "
        "correctif est inutile")
    assert _ok.returncode == 0, _ok.stderr[-300:]
    print("environnement : pollue -> code {}, assaini -> code {} OK".format(
        _ko.returncode, _ok.returncode))
else:
    print("environnement : pas de python systeme, controle saute")
