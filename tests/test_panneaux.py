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
# La case « Fuseau » est partagée par la spirale et les rangées, et
# son état est MÉMORISÉ : sans ce décochage explicite, ce test juge
# le fuseau au lieu de la modulation par la puissance -- exactement
# le piège du plafond de puissance ci-dessus.
p.chk_fuseau_z.setChecked(False)
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
assert u"Hêtre" in mats, mats
p.combo_photo_mat.setCurrentIndex(mats.index(u"Hêtre"))
p.edt_image.setText(img)
p.spn_width.setValue(40.0)
p.spn_gamma.setValue(1.0)

# Chaque tramage a un régime qui lui convient : imposer la vitesse des
# lignes calibrées aux « lignes gravées » les fait refuser, à juste titre.
# F200 pas 0,34 : sous le plafond S900 de l'atelier, F800 ne donne plus
# que 1,33x et le tramage refuse -- à juste titre, depuis que la table
# du hêtre est mesurée et non plus fabriquée (01/08/2026).
REGIMES = {"enfle": (0.34, 200.0)}
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
# Sur un matériau FABRIQUÉ ICI, pas sur celui de l'atelier.
#
# Ce test lisait la table du Hêtre et supposait qu'au-delà de F800 le trait
# n'enfle plus. Le 01/08/2026 Christophe a mesuré F1000 à F3000 sur une
# planche fraîche : la colonne n'est plus plate, `swell_max_feed` est passé
# de 800 à 3000, et le test est tombé -- alors que le code n'avait pas
# bougé. Un test qui dépend des mesures de l'utilisateur casse quand
# l'utilisateur MESURE, ce qui est exactement ce qu'on lui demande de faire.
MAT_PLAT = "TestTraitPlat"
core.save_burn_widths(MAT_PLAT, {
    "focus": (
        # Enfle sous F800...
        [{"power": s_, "feed": 800.0, "width": w}
         for s_, w in ((200.0, 0.10), (400.0, 0.15), (600.0, 0.20),
                       (800.0, 0.25), (1000.0, 0.30))]
        # ...et RIGOUREUSEMENT plat au-dessus : plus rien à moduler.
        + [{"power": s_, "feed": f_, "width": 0.10}
           for s_ in (200.0, 400.0, 600.0, 800.0, 1000.0)
           for f_ in (1500.0, 3000.0)]),
    "defocus": [],
})
if p.combo_photo_mat.findData(MAT_PLAT) < 0:
    p.combo_photo_mat.addItem(MAT_PLAT, MAT_PLAT)
p.combo_photo_mat.setCurrentIndex(p.combo_photo_mat.findData(MAT_PLAT))
assert p.combo_photo_mat.currentData() == MAT_PLAT, (
    "le panneau lit currentData() : un item sans donnee vaut None")
assert core.swell_power_levels(MAT_PLAT, 800.0, 0.10) is not None, (
    "le materiau de test doit ENFLER a F800, sinon le refus a F2000 ne "
    "prouve rien")
assert core.swell_power_levels(MAT_PLAT, 2000.0, 0.10) is None, (
    "le materiau de test doit etre PLAT a F2000")
p.combo_mode.setCurrentIndex(6)
p.spn_line_feed.setValue(2000.0)        # au-delà, le trait n'enfle plus
rows = p._build_rows(silent=True, max_cells=30000)
im, note = p._render_photo_preview(rows, largeur_px=200)
assert im is None, "le tramage aurait dû refuser"
rapide = core.swell_max_feed(MAT_PLAT)
assert rapide and "F{:.0f}".format(rapide) in note, (
    "un refus doit nommer la vitesse qui marche, pas seulement celle qui "
    "échoue", note)
assert p._generate(rows, quiet=True) is None, \
    "l'aperçu refuse mais le générateur produit quand même du G-code"
core.save_burn_widths(MAT_PLAT, {})      # on ne laisse pas de faux materiau
p.combo_photo_mat.setCurrentIndex(p.combo_photo_mat.findData(u"Hêtre"))
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
# La case « Fuseau » est partagée par la spirale et les rangées, et
# son état est MÉMORISÉ : sans ce décochage explicite, ce test juge
# le fuseau au lieu de la modulation par la puissance -- exactement
# le piège du plafond de puissance ci-dessus.
p5.chk_fuseau_z.setChecked(False)
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
assert _cles == {"planche1", "planche2", "planche2b", "planche_autre"}, _cles
# Toute planche qui se GRAVE doit pouvoir se REDRESSER : la 2b avait été
# ajoutée aux boutons sans être ajoutée ici (01/08/2026), donc sa photo
# n'avait nulle part où aller.
for _lib, _cle in tp._PLANCHES:
    if _cle == "planche_autre":
        continue
    _cotes = tp._cotes_mire_defaut(_cle)
    assert _cotes != "140-60" or _cle == "planche1", (
        "« {} » retombe sur les cotes par defaut : son generateur n'est pas "
        "branche dans _cotes_mire_defaut".format(_lib), _cotes)
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
# Jusqu'a la fin de la fonction, pas une fenetre de N caracteres : la
# question du NOM (v2.44.0) a allonge le corps et sorti "--laser" d'une
# fenetre de 6000, faisant tomber le test sur du code pourtant correct.
_j = _tp_src.index("\ndef ", _i + 10)
_corps = _tp_src[_i:_j]
assert "core.dossier_planches()" in _corps and "core.nom_planche_redressee" in _corps
assert '"--laser"' in _corps, "le laser doit partir dans la fiche du redressement"
assert '"--nom"' in _corps, "le nom saisi doit partir dans la fiche aussi"
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
# Deverrouiller d'abord : depuis la v2.31.1 l'outil respecte le cadenas,
# et une grille est verrouillee par defaut.
_ctrl.grille_focus._chk.setChecked(False)
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


# --- Cotes saisies contre planche choisie (v2.25.0) ------------------
# La planche est choisie AVANT de voir la photo : on peut cliquer
# « Planche 1 » et photographier la 2. C'est arrive le 01/08/2026 --
# echelle juste (elle vient des cotes, qui sont lues sur le bois), mais
# photo rangee sous la mauvaise planche et fichier au nom mensonger.
_cotes = {c: tp._cotes_mire_defaut(c).replace("-", "x")
          for _l, c in tp._PLANCHES if c != "planche_autre"}
assert set(_cotes) == {"planche1", "planche2", "planche2b"}, _cotes
# Le controle se demontre : les deux planches doivent avoir des cotes
# DIFFERENTES, sinon il n'y a rien a distinguer et le garde-fou est vide.
assert len(set(_cotes.values())) == len(_cotes), (
    "deux planches partagent les memes cotes : le garde-fou ne peut plus "
    "les distinguer, et ce test ne prouve rien", _cotes)
# Et il doit bien exister dans le code, avec la bascule vers l'autre.
_src_tp = open(_os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                             "task_panels.py")).read()
_i = _src_tp.index("def _redresser_photo_planche")
_corps = _src_tp[_i:_i + 9000]
assert "planche = _autre" in _corps, (
    "le garde-fou doit pouvoir CORRIGER le rangement, pas seulement avertir")
assert "QtWidgets.QMessageBox.Cancel" in _corps, "et pouvoir annuler"
print("redressement : cotes {} -> toutes distinguables, garde-fou en "
      "place OK".format(", ".join(sorted(_cotes.values()))))


# --- La galerie dit QUELLE planche elle montre (v2.26.0) -------------
# « J'ai redressé la défocus [...] mais dans la liste je ne la vois pas » :
# le selecteur etait ajoute AVANT _make_photo_section, donc au-dessus de la
# carte de section -- visuellement rattache a la section PRECEDENTE. On
# croyait a une liste unique, et une planche rangee sous une autre cle
# passait pour perdue.
_hote3 = _Qt.QWidget()
_form3 = _Qt.QFormLayout(_hote3)
tp._boutons_planches(_form3, lambda *a, **k: None)
_cles_pl = {c for _l, c in tp._PLANCHES}
_combo_pl = next(w for w in _hote3.findChildren(_Qt.QComboBox)
                 if {w.itemData(i) for i in range(w.count())} == _cles_pl)
# Rang de chaque widget dans le formulaire.
_rangs = {}
for r in range(_form3.rowCount()):
    for role in (_Qt.QFormLayout.LabelRole, _Qt.QFormLayout.FieldRole,
                 _Qt.QFormLayout.SpanningRole):
        it = _form3.itemAt(r, role)
        if it is not None and it.widget() is not None:
            _rangs.setdefault(it.widget(), r)
_r_combo = _rangs.get(_combo_pl)
assert _r_combo is not None, "selecteur de planche absent du formulaire"
_entetes = [r for w, r in _rangs.items()
            if isinstance(w, tp._SectionHeader) and r < _r_combo]
assert _entetes, "aucun titre de section au-dessus du selecteur"
# Le selecteur doit suivre IMMEDIATEMENT le titre : place avant l'appel a
# _make_photo_section il tombait au-dessus de la carte, donc rattache
# visuellement a la section PRECEDENTE.
assert max(_entetes) == _r_combo - 1, (
    "le selecteur doit etre la premiere rangee SOUS le titre de section",
    max(_entetes), _r_combo)
print("galerie : selecteur de planche placé DANS la carte de section OK")

# Le champ description doit tenir un texte long : l'atelier en ecrit
# lui-meme plus de 200 caracteres, et on ne complete pas a l'aveugle.
_desc = [w for w in _hote3.findChildren(tp._ZoneTexte)]
assert _desc, "la description doit etre une zone multi-lignes, pas une ligne"
_z = _desc[0]
_long = "redressée le 01/08/2026 09:09 — échelle 50 px/mm, mire 140x60, " \
        "écart de diagonales 0.15 %, réglette vérifiée à +0.19 % — " \
        "fichier de mesure : LT-80W-AA-PRO_planche1_20260801-0909_redresse.png"
_z.setPlainText(_long)
assert _z.toPlainText() == _long
assert _z.height() >= 60, ("la zone doit montrer plusieurs lignes", _z.height())
assert hasattr(_z, "edition_terminee"), "elle doit prevenir a la sortie du champ"
print("galerie : description multi-lignes, {} caractères tenus OK".format(len(_long)))


# --- Ce que la grille NE PEUT PAS montrer doit être DIT (v2.28.0) -----
# Une grille de défocus naît dès qu'un point existe à ce niveau, mais elle
# n'a de cases que pour POWERS x FEEDS_DEFOCUS. Les points venus de la
# Rampe portent des puissances interpolees (S585, S716, S909, S980) :
# aucune case ne leur correspond, et la grille s'affichait VIDE.
# « A quoi sert cela alors ? » -- 01/08/2026.
_hote4 = _Qt.QWidget()
_form4 = _Qt.QFormLayout(_hote4)
_c4 = tp._MesuresPlanchesControleur(_form4, _FauxParent(), lambda: "BoisHorsGrille")
core.save_burn_widths("BoisHorsGrille", {"focus": [], "defocus": [
    # DANS la grille...
    {"power": 1000.0, "feed": 800.0, "width": 1.10, "z_offset": 15.0},
    # ...et HORS de la grille : S909 n'est aucune de ses lignes.
    {"power": 909.0, "feed": 400.0, "width": 3.00, "z_offset": 55.0},
]})
_c4.reload()
assert 55.0 in _c4.grilles_defocus, sorted(_c4.grilles_defocus)
assert not _c4.grilles_defocus[55.0].values(), (
    "S909 ne peut pas s'afficher : la grille DOIT rester vide, "
    "c'est le fait qu'il faut annoncer")
_l55 = _c4.lbl_hors_grille[55.0]
assert _l55.isVisibleTo(_hote4) or _l55.text(), "rien n'annonce la mesure cachee"
assert "S909" in _l55.text() and "F400" in _l55.text() and "3.00" in _l55.text(), \
    _l55.text()
# Et là où tout est affichable, aucun avertissement : sinon il devient du
# bruit qu'on cesse de lire.
assert _c4.grilles_defocus[15.0].values(), "S1000/F800 devrait s'afficher"
assert not _c4.lbl_hors_grille[15.0].text(), (
    "pas d'avertissement quand tout tient dans la grille",
    _c4.lbl_hors_grille[15.0].text())
core.save_burn_widths("BoisHorsGrille", {})
print("mesures hors grille : annoncées sous la grille, silence sinon OK")


# --- Aucun bouton ne doit tomber DANS une section repliable (v2.29.1) -
# `_activer_sections` regroupe les rangees qui SUIVENT un titre de section
# dans un conteneur montre/cache. Un bouton ajoute apres `_make_photo_section`
# se retrouve donc a l'interieur de « Planches redressees » et DISPARAIT
# quand elle est fermee. « Je ne vois pas la planche2b dans la liste »,
# 01/08/2026 : le bouton existait, il etait avale.
_hote5 = _Qt.QWidget()
_form5 = _Qt.QFormLayout(_hote5)
tp._boutons_planches(_form5, lambda *a, **k: None)
_pos = {}
for _r in range(_form5.rowCount()):
    for _role in (_Qt.QFormLayout.LabelRole, _Qt.QFormLayout.FieldRole,
                  _Qt.QFormLayout.SpanningRole):
        _it = _form5.itemAt(_r, _role)
        if _it is not None and _it.widget() is not None:
            _pos.setdefault(_it.widget(), _r)
_r_titre = min([r for w, r in _pos.items()
                if isinstance(w, tp._SectionHeader)] or [10 ** 6])
_boutons_planche = [w for w, _r in _pos.items()
                    if isinstance(w, _Qt.QPushButton)
                    and w.text().startswith("Planche")]
assert len(_boutons_planche) >= 4, [b.text() for b in _boutons_planche]
for _b in _boutons_planche:
    assert _pos[_b] < _r_titre, (
        "« {} » est place APRES un titre de section : il sera avale par "
        "la section repliable et invisible quand elle est fermee".format(
            _b.text()), _pos[_b], _r_titre)
assert any("2b" in b.text() for b in _boutons_planche), \
    [b.text() for b in _boutons_planche]
# La 2b est une VARIANTE de la 2 (mêmes grilles, niveaux profonds), pas une
# quatrième planche : elle doit suivre immédiatement la 2, l'ordre des
# boutons devant dire la parenté. Demande de Christophe le 01/08/2026.
_ordre = sorted(_boutons_planche, key=lambda b: _pos[b])
_txt = [b.text() for b in _ordre]
_i2 = next(i for i, t in enumerate(_txt) if t.startswith("Planche 2 "))
assert _txt[_i2 + 1].startswith("Planche 2b"), (
    "la Planche 2b doit suivre immédiatement la Planche 2", _txt)
print("boutons de planche : les {} restent HORS des sections repliables OK"
      .format(len(_boutons_planche)))


# --- Une photo trop grande n'est pas « aucune photo » (v2.29.2) -------
# Qt refuse toute image depassant QImageReader.allocationLimit() (256 Mo)
# et renvoie une image NULLE. Une planche redressee de 13600x5100 px fait
# 277 Mo decompressee : la vignette restait vide, le panneau affichait
# « — aucune photo — » sur une photo qui existe, ET grisait le bouton
# Supprimer -- donc la seule photo qu'on voulait jeter etait justement
# celle qu'on ne pouvait pas jeter. Constate le 01/08/2026.
from PySide6 import QtGui as _QtG
assert hasattr(tp, "_image_bornee")
import tempfile as _tf2
_dj = _tf2.mkdtemp()
_gros = _os.path.join(_dj, "gros.png")
_im = _QtG.QImage(3000, 2000, _QtG.QImage.Format_RGB32)
_im.fill(_QtG.QColor(200, 150, 100))
assert _im.save(_gros), "impossible d'ecrire l'image de test"

# On ABAISSE la limite plutot que de fabriquer une image de 300 Mo : elle
# vaut 256 Mo dans le FreeCAD de l'atelier et 1024 ici, donc la fixer
# rendrait le test dependant de l'environnement -- et ecrire un PNG de
# 16000x16000 pour le prouver serait absurde.
_limite = _QtG.QImageReader.allocationLimit()
_QtG.QImageReader.setAllocationLimit(1)          # 1 Mo : 3000x2000 = 24 Mo
try:
    # Le controle se demontre : brut, Qt refuse ; borne, il accepte.
    assert _QtG.QPixmap(_gros).isNull(), (
        "sous une limite de 1 Mo, une image de 24 Mo doit etre refusee -- "
        "sinon ce test ne prouve rien")
    _img, _souci = tp._image_bornee(_gros, 640, 360)
    assert _img is not None, ("la lecture bornee doit reussir la ou QPixmap "
                              "echoue", _souci)
    assert _img.width() <= 640 and _img.height() <= 360, (
        _img.width(), _img.height())
finally:
    _QtG.QImageReader.setAllocationLimit(_limite)
# La limite Qt doit etre REMISE : la lever durablement exposerait tout
# FreeCAD a un fichier aberrant.
assert _QtG.QImageReader.allocationLimit() == _limite, (
    "la limite d'allocation n'a pas ete restauree",
    _QtG.QImageReader.allocationLimit(), _limite)
# Et un plafond a nous, pour qu'un fichier absurde ne fasse pas tomber
# FreeCAD : au-dela, on refuse EN LE DISANT.
assert tp.PLAFOND_LECTURE_IMAGE_MO >= 1024

# Et un fichier vraiment illisible doit DIRE pourquoi, pas rendre None muet.
_ko = _os.path.join(_dj, "pas_une_image.png")
open(_ko, "wb").write(b"ceci n'est pas une image")
_img2, _souci2 = tp._image_bornee(_ko, 640, 360)
assert _img2 is None and _souci2, (_img2, _souci2)
print("vignette : lue bornée là où QPixmap échoue (limite abaissée) OK")


# --- Le verrou vaut AUSSI pour l'outil de mesure (v2.31.1) -----------
# `setValue` ignore `setReadOnly` : le clavier etait bloque et l'outil
# A -> B ecrivait quand meme. « Coche ou pas, je peux inserer la mesure »
# -- 01/08/2026. Pire, il ecrasait SANS UN MOT une valeur deja mesuree
# (3,35 mm remplaces par 0,42 pendant la reproduction), c'est-a-dire
# exactement ce contre quoi le verrou existe. Un verrou qui ne retient
# qu'une main sur deux ne protege rien : il rassure a tort.
_hote6 = _Qt.QWidget()
_form6 = _Qt.QFormLayout(_hote6)
_c6 = tp._MesuresPlanchesControleur(_form6, _FauxParent(), lambda: u"Hêtre")
_c6.reload()
_gr6 = _c6.grille_focus
_sp6 = _gr6.cells()[(1000.0, 800.0)]
assert _gr6._chk.isChecked(), "le verrou doit etre coche par defaut"
assert _sp6.isReadOnly()

_avant = _sp6.value()
_c6._mesure_cible = _sp6
_c6._serie = []
_msg6 = _c6._encaisser_mesure(0.42, 0.01, 0.42)
assert _sp6.value() == _avant, (
    "l'outil de mesure a ecrit dans une case VERROUILLEE", _avant, _sp6.value())
assert "verrouill" in _msg6.lower(), _msg6
assert _c6._serie == [], "une mesure refusee ne doit pas entrer dans la moyenne"

# Le controle se demontre : deverrouille, la meme mesure passe.
_gr6._chk.setChecked(False)
assert not _sp6.isReadOnly()
_msg6b = _c6._encaisser_mesure(0.42, 0.01, 0.42)
assert abs(_sp6.value() - 0.42) < 1e-9, (
    "deverrouille, la mesure doit s'ecrire -- sinon ce test ne prouve rien",
    _sp6.value())
assert "verrouill" not in _msg6b.lower(), _msg6b
_gr6._chk.setChecked(True)
print("verrou : l'outil de mesure respecte le cadenas, et le dit OK")


# --- Le job combiné peignait le point OPTIQUE (v2.32.0) --------------
# Trou ouvert depuis la v2.13.2, documenté comme tel : les trois appels de
# `_strokes_from_operation` ne passaient PAS le materiau, donc
# `burn_width_defocus_scaled` renvoyait None des qu'il y a plus d'un
# materiau mesure -- et l'apercu retombait EN SILENCE sur le point
# optique, plus large que la brulure reelle.
#
# Le materiau voyage A COTE de `params`, jamais dedans : params est le jeu
# exact de kwargs du generateur, une cle en plus casserait l'appel
# **params. C'est ce qui avait laisse ce trou ouvert.
assert len(core.burn_width_materials()) >= 2, (
    "il faut au moins deux materiaux mesures pour que l'omission se voie -- "
    "avec un seul, core devine et le defaut reste invisible")
_op = {"type": "curved", "materiau": u"Hêtre",
       "params": {"power": 1000.0, "feed": 200.0,
                  "z_focus": core.Z_WORK_MM + 15.0, "edges": []}}
_sans = dict(_op); _sans.pop("materiau")
_pw, _fd, _dz = 1000.0, 200.0, 15.0
_mesure = core.burn_width_defocus_scaled(_pw, _fd, _dz, u"Hêtre")
_devine = core.burn_width_defocus_scaled(_pw, _fd, _dz)
_optique = core.spot_diameter_at_defocus(_dz, core.SPOT_FOCUS_MM,
                                         core.calibrated_half_angle())
assert _mesure and abs(_mesure - _optique) > 0.05, (
    "brulure et point optique doivent differer, sinon ce test ne prouve rien",
    _mesure, _optique)
assert _devine is None, (
    "avec deux materiaux mesures, core DOIT refuser de deviner", _devine)
# Et le panneau transmet bien la cle.
_src_tp2 = open(_os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                              "task_panels.py")).read()
assert _src_tp2.count('"materiau":') >= 2, (
    "les constructeurs d'operation doivent porter le materiau")
_i2 = _src_tp2.index("def _strokes_from_operation")
_corps2 = _src_tp2[_i2:_i2 + 4000]
assert 'op.get("materiau")' in _corps2, "l'apercu doit lire le materiau"
assert "defocus, mat)" in _corps2 and "coff, mat)" in _corps2 \
    and "dz, mat)" in _corps2, (
    "les TROIS appels doivent passer le materiau, pas un ou deux")
print("job combiné : matériau transmis à l'aperçu ({:.2f} mm mesurés contre "
      "{:.2f} optiques) OK".format(_mesure, _optique))


# --- Mesurer à la LIGNE, sur le profil moyenné (v2.33.0) -------------
# Idee de Christophe le 01/08/2026 : « si a la place du curseur j'avais une
# ligne horizontale que je place la ou il me semble etre la moyenne sur
# toute la brulure ». Le bord d'une brulure n'est pas une ligne mais une
# RAMPE ; une lecture prise sur UNE colonne varie enormement, la meme
# moyennee sur la longueur du trait est stable.
from PySide6 import QtCore as _QtC3
assert hasattr(tp, "profil_trait") and hasattr(tp, "largeur_au_seuil")
assert hasattr(tp, "_VueProfilTrait") and hasattr(tp, "_DialogueMesureTrait")

# Trait SYNTHETIQUE : noyau noir, bords en rampe, et du bruit colonne par
# colonne -- exactement ce qui rend un clic unique instable.
import numpy as _np
_H, _W, _PX = 300, 600, 50.0
_rng = _np.random.default_rng(4)
_a = _np.full((_H, _W), 200.0)
for _x in range(_W):
    _c = 150 + _rng.integers(-12, 13)          # le trait ondule
    _demi = 50 + _rng.integers(-6, 7)          # ... et sa largeur varie
    # LE GRAIN : une colonne sur dix, la brulure part beaucoup plus loin.
    # C'est lui qui rend une lecture ponctuelle instable -- et c'est
    # exactement ce que moyenner supprime, puisqu'il ne pese qu'un dixieme.
    if _rng.random() < 0.10:
        _demi += 28
    for _y in range(_H):
        _d = abs(_y - _c)
        if _d < _demi - 10:
            _a[_y, _x] = 30
        elif _d < _demi + 10:                   # la rampe
            _a[_y, _x] = 30 + 170 * (_d - (_demi - 10)) / 20.0
_a = _np.clip(_a + _rng.integers(-6, 7, _a.shape), 0, 255).astype(_np.uint8)
_img = _QtG.QImage(_a.tobytes(), _W, _H, _W, _QtG.QImage.Format_Grayscale8).copy()

_prof, _bois = tp.profil_trait(_img)
assert _prof is not None and len(_prof) == _H, (len(_prof) if _prof is not None else None)
assert 0.9 < _bois / 200.0 < 1.1, _bois

# LE controle qui compte, et il se demontre : moyenner doit ETRE plus
# stable que lire une colonne. Si les deux se valaient, la fenetre entiere
# n'aurait aucune raison d'exister.
_par_seuil = [tp.largeur_au_seuil(_prof, s)[2] / _PX for s in (0.4, 0.5, 0.6)]
_etendue_profil = max(_par_seuil) - min(_par_seuil)
_cols = []
# TOUTES les colonnes, pas une sur vingt : un clic tombe n'importe ou, et
# echantillonner large ratait justement les colonnes a grain (50 sur 600,
# aucune parmi les 30 tirees -- le test se mesurait mal lui-meme).
for _x in range(_W):
    _d = _np.flatnonzero(_a[:, _x] / _bois < 0.5)
    if len(_d):
        _cols.append((_d[-1] - _d[0] + 1) / _PX)
_etendue_col = max(_cols) - min(_cols)
assert _etendue_col > 3 * _etendue_profil, (
    "le profil moyenné doit être NETTEMENT plus stable qu'une colonne, "
    "sinon cette fenêtre ne sert à rien", _etendue_col, _etendue_profil)

# La conversion pixels -> mm est l'enjeu : une erreur ici fausse tout en
# silence.
_vue = tp._VueProfilTrait(_img, _PX)
_vue._y = [30.0, 30.0 + 2.5 * _PX]
assert abs(_vue.distance_mm() - 2.5) < 1e-9, _vue.distance_mm()
# Et le placement de depart doit tomber sur le repere 50 %, pas n'importe ou.
_vue2 = tp._VueProfilTrait(_img, _PX)
assert abs(_vue2.distance_mm() - tp.largeur_au_seuil(_prof, 0.5)[2] / _PX) < 0.05
print("mesure à la ligne : colonne ±{:.2f} mm contre profil ±{:.2f} mm, "
      "conversion exacte OK".format(_etendue_col, _etendue_profil))


# --- « Retenir cette largeur » n'écrivait nulle part (v2.33.1) --------
# `_encaisser_mesure` ecrit dans `self._mesure_cible`, et `_on_mesure_image`
# ne le posait JAMAIS : il lisait la case dans une variable locale. Le
# bouton disait « Retenir cette largeur » et n'ecrivait nulle part -- ou,
# pire, dans la case d'une mesure precedente restee la. Vu au premier usage
# reel, le 01/08/2026.
_hote7 = _Qt.QWidget()
_form7 = _Qt.QFormLayout(_hote7)
_c7 = tp._MesuresPlanchesControleur(_form7, _FauxParent(), lambda: u"Hêtre")
_c7.reload()
_c7.grille_focus._chk.setChecked(False)
_sp7 = _c7.grille_focus.cells()[(600.0, 400.0)]
_QtC.QCoreApplication.sendEvent(_sp7, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
# Le chemin que suit `_on_mesure_image` : viser, PUIS encaisser.
assert _c7._derniere_case is _sp7
_c7._mesure_cible = _c7._derniere_case
_c7._serie = []
_c7._encaisser_mesure(3.740, 0.0, 3.740)
assert abs(_sp7.value() - 3.740) < 1e-6, (
    "la largeur retenue doit atterrir dans la case visée", _sp7.value())
# Le controle se demontre : SANS poser la cible, rien n'est ecrit -- c'est
# exactement le defaut, et il ne doit pas pouvoir revenir sans que ce test
# le voie.
_sp7.setValue(0.0)
_c7._mesure_cible = None
_c7._serie = []
_c7._encaisser_mesure(3.740, 0.0, 3.740)
assert _sp7.value() == 0.0, "sans cible posée, rien ne doit être écrit"

# L'image s'ouvre toute seule : la plus recente du dossier, puis retenue
# pour la seance -- on mesure des dizaines de cases sur une meme planche.
assert hasattr(_c7, "_image_mesure") and hasattr(_c7, "_image_de_mesure")
_planches = core.planches_redressees()
if _planches:
    _img7 = _c7._image_de_mesure()
    assert _img7 and _os.path.isfile(_img7), _img7
    assert _os.path.splitext(_img7)[0] == _planches[0]["base"], (
        "ce doit être l'image de MESURE de la planche la plus récente, pas "
        "son aperçu ni son contrôle de repères", _img7)
    assert _c7._image_de_mesure() == _img7, "et elle doit être retenue"
    _c7._changer_image()
    assert _c7._image_mesure is None, "« Changer de planche » doit l'oublier"
    print("mesure sur image : largeur écrite dans la case, planche {} ouverte "
          "d'office OK".format(_os.path.basename(_img7)[:34]))
else:
    print("mesure sur image : largeur écrite dans la case OK (aucune planche "
          "redressée pour tester l'ouverture automatique)")


# --- Enchaîner les cases sans fermer la fenêtre (v2.34.0) ------------
# « Il faut pour chaque ligne ouvrir et fermer [...] la difficulte c'est de
# savoir dans quelle case va la mesure que je viens de faire »
# -- 01/08/2026. Deux choses : la case visee doit etre ECRITE dans la
# fenetre, et « Retenir -> case suivante » doit avancer tout seul.
_hote8 = _Qt.QWidget()
_form8 = _Qt.QFormLayout(_hote8)
_c8 = tp._MesuresPlanchesControleur(_form8, _FauxParent(), lambda: u"Hêtre")
_c8.reload()
_gr8 = _c8.grille_focus
_gr8._chk.setChecked(False)
_dep = _gr8.cells()[(1000.0, 200.0)]
_QtC.QCoreApplication.sendEvent(_dep, _QtG.QFocusEvent(_QtC.QEvent.FocusIn))
_c8._mesure_cible = _c8._derniere_case

# L'ORDRE suit celui du bois : une colonne de vitesse a la fois, du haut
# vers le bas. Un ordre par lignes ferait sauter d'une colonne a l'autre
# entre chaque mesure, alors que les traits sont empiles par colonne.
_vus, _cur, _n = [], _c8._mesure_cible, 0
while _cur is not None and _n < 7:
    _vus.append(_c8._nom_case(_cur))
    _c8._mesure_cible = _cur
    _c8._serie = []
    _suiv, _ = _c8._retenir_depuis_image(1.0 + _n * 0.1)
    # `_retenir_depuis_image` renvoie desormais un INDEX (la fenetre porte
    # une liste deroulante de cases), pas un nom.
    _cur = _c8._mesure_cible if _suiv is not None else None
    _n += 1
assert _vus[:5] == ["S{} / F200 (foyer)".format(s) for s in (1000, 800, 600, 400, 200)], _vus
assert _vus[5].startswith("S1000 / F400"), (
    "après la dernière puissance d'une colonne, on passe à la vitesse "
    "suivante -- pas à la ligne suivante", _vus)

# Et chaque valeur est allee dans SA case, pas toutes dans la meme.
_ecrits = [_gr8.cells()[(float(s), 200.0)].value()
           for s in (1000, 800, 600, 400, 200)]
assert _ecrits == [1.0, 1.1, 1.2, 1.3, 1.4], _ecrits

# La fenetre AFFICHE la case visee : sans ca, une valeur qui atterrit dans
# la mauvaise case ne se voit pas, elle ressemble a une mesure.
import inspect as _insp2
_sig8 = _insp2.signature(tp._DialogueMesureTrait.__init__)
assert "noms_cases" in _sig8.parameters and "on_retenir" in _sig8.parameters, _sig8
_src8 = open(_os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                           "task_panels.py")).read()
_i8 = _src8.index("class _DialogueMesureTrait")
_fin8 = _src8.find("\nclass ", _i8 + 10)
_corps8 = _src8[_i8:_fin8 if _fin8 > 0 else len(_src8)]
assert "La mesure ira dans" in _corps8, "la case visée doit être écrite dans la fenêtre"
assert "combo_cible" in _corps8, "et choisissable DANS la fenêtre"
assert "_retenir_et_suivant" in _corps8 and "Retenir → case suivante" in _corps8
print("enchaînement : {} cases dans l'ordre du bois, chacune sa valeur OK".format(
    len(_vus)))


# --- Choisir la planche dans le panneau (v2.35.0) --------------------
# « Je veux calculer les lignes au foyer, mais je n'ai pas le choix, il
# m'ouvre le dernier et c'est le defocus » -- 01/08/2026. L'ouverture
# automatique prenait la plus RECENTE, sans le dire, et il fallait passer
# par un dialogue de fichiers pour en sortir. Un automatisme qui choisit a
# votre place doit au minimum montrer ce qu'il a choisi.
_hote9 = _Qt.QWidget()
_form9 = _Qt.QFormLayout(_hote9)
_c9 = tp._MesuresPlanchesControleur(_form9, _FauxParent(), lambda: u"Hêtre")
_c9.reload()
_cb9 = _c9._blocs[0].combo_planche
assert _cb9 is not None and _cb9.count() >= 1

_planches9 = core.planches_redressees()
if _planches9:
    # La liste doit contenir les planches, et une seule entree par planche
    # -- l'apercu et le controle des reperes ne sont pas des planches.
    assert _cb9.count() == len(_planches9), (_cb9.count(), len(_planches9))
    _libelles = [_cb9.itemText(i) for i in range(_cb9.count())]
    # PAS « commence par Planche », et PAS NON PLUS « commence par une
    # majuscule » : Christophe redresse aussi des « Autre planche », et il
    # NOMME ses planches lui-meme depuis la v2.44 -- « tons défocus 15,34
    # pas 1,0 » commence en minuscule et c'est parfaitement legitime. Ce
    # test a rougi DEUX fois pour la meme raison de fond : il verifiait un
    # indice de la propriete (la casse) au lieu de la propriete. Ce qui
    # compte est que le libelle ne soit pas le nom de FICHIER brut.
    _bases9 = {_os.path.basename(p.get("base") or "") for p in _planches9}
    for _l9 in _libelles:
        assert _l9, "libelle vide"
        assert _l9 not in _bases9, (
            "le libelle est le nom de fichier brut, pas un nom", _l9)
        assert len(_l9) <= 60, ("libelle illisible tant il est long", _l9)
    # Le libelle doit etre LISIBLE : la planche, l'heure, les cotes -- pas
    # un nom de fichier de 60 caracteres.
    assert any("h" in l and "(" in l for l in _libelles), _libelles
    # Chaque entree pointe sur l'image de MESURE, pas sur un derive.
    for i in range(_cb9.count()):
        _d = _cb9.itemData(i)
        assert _d and _os.path.isfile(_d), _d
        assert not _d.endswith(("_apercu.jpg", "_reperes.jpg")), _d

    # Choisir une planche qui n'est PAS la plus recente doit tenir.
    _autre = None
    for i in range(_cb9.count()):
        if _cb9.itemData(i) != _c9._image_mesure:
            _autre = _cb9.itemData(i)
            break
    if _autre:
        _c9._on_planche_choisie(_autre)
        assert _c9._image_mesure == _autre
        assert _c9._image_de_mesure() == _autre, (
            "« Mesurer » doit ouvrir la planche CHOISIE, pas la plus récente")
        # Un seul choix pour toutes les grilles.
        assert all(b.combo_planche.currentData() == _autre
                   for b in _c9._blocs_vivants()), (
            "les listes des différents blocs doivent se suivre")
    print("choix de planche : {} planches listées, sélection tenue OK".format(
        _cb9.count()))
else:
    assert _cb9.itemData(0) is None
    print("choix de planche : liste vide annoncée proprement OK")




# --- « Rien ne se passe » : deux refus muets (v2.35.1) ---------------
# « J'ai choisi ma planche 1, puis mesurer l'image redressee et rien ne se
# passe » -- 01/08/2026. Deux refus se cumulaient, tous deux annonces dans
# un LIBELLE discret : aucune case visee (il fallait avoir clique une case
# dans le panneau) et grille verrouillee. Un refus qu'on ne voit pas est un
# logiciel qui ne repond pas.
_hoteA = _Qt.QWidget()
_formA = _Qt.QFormLayout(_hoteA)
_cA = tp._MesuresPlanchesControleur(_formA, _FauxParent(), lambda: u"Hêtre")
_cA.reload()

# La fenetre choisit la case ELLE-MEME : plus de dependance a un clic
# prealable ailleurs dans le panneau.
assert hasattr(_cA, "_cases_ordonnees") and hasattr(_cA, "_viser_index")
_casesA = _cA._cases_ordonnees(_cA.grille_focus)
assert len(_casesA) == len(_cA.POWERS) * len(_cA.FEEDS_FOCUS), len(_casesA)
# ... dans l'ordre du bois : une colonne de vitesse a la fois.
_nomsA = [_cA._nom_case(w) for w in _casesA[:6]]
assert _nomsA[:5] == ["S{} / F200 (foyer)".format(s)
                      for s in (1000, 800, 600, 400, 200)], _nomsA
assert _nomsA[5].startswith("S1000 / F400"), _nomsA

# Le verrou n'est plus un refus muet : le code DOIT poser la question.
_srcA = open(_os.path.join(_os.path.dirname(_os.path.abspath(tp.__file__)),
                           "task_panels.py")).read()
_iA = _srcA.index("def _on_mesure_image")
_finA = _srcA.index("\n    def ", _iA + 10)
_corpsA = _srcA[_iA:_finA]
assert "QMessageBox.question" in _corpsA, (
    "la grille verrouillée doit être ANNONCÉE et proposer l'ouverture, "
    "pas refuser dans un libellé")
assert "Clique d'abord la <b>case à remplir</b>" not in _corpsA, (
    "il ne doit plus être nécessaire d'avoir cliqué une case avant")

# Et la fenetre porte une LISTE de cases, pas un libelle fige.
import inspect as _insp3
_sigA = _insp3.signature(tp._DialogueMesureTrait.__init__)
assert "noms_cases" in _sigA.parameters and "on_cible" in _sigA.parameters, _sigA
_iD = _srcA.index("class _DialogueMesureTrait")
_finD = _srcA.find("\nclass ", _iD + 10)
_corpsD = _srcA[_iD:_finD if _finD > 0 else len(_srcA)]
assert "combo_cible" in _corpsD and "La mesure ira dans" in _corpsD
print("mesure sur image : la fenêtre choisit sa case ({} en liste), verrou "
      "annoncé OK".format(len(_casesA)))

# --- Sortie PROPRE ------------------------------------------------------
# Tout ce qui devait etre verifie l'a ete : les assertions sont au-dessus,
# et une seule qui echoue leve avant d'arriver ici.
#
# Restait un echec ALEATOIRE, environ une fois sur quatre, SANS trace : le
# script sortait en code 1 apres avoir affiche tous ses OK. Ce n'est pas un
# test qui tombe, c'est la fermeture de Qt/FreeCAD qui rend la main sur un
# code non nul -- ce fichier construit une dizaine de fenetres, chacune
# avec ses grilles, ses filtres d'evenements et ses minuteurs, et l'ordre
# de destruction n'est garanti par personne.
#
# Une suite qui rougit une fois sur quatre sans raison apprend a ignorer le
# rouge, ce qui est pire que pas de suite du tout. On lache donc les
# --- Un document toujours ouvert ---------------------------------------
# Sans document actif, 15 des 21 boutons sont GRISES (leur IsActive exige
# un document) et les 6 autres ouvrent une fenetre de taches la ou FreeCAD
# n'a aucune vue pour l'accueillir : elle part derriere la fenetre
# principale et devient inatteignable. Christophe l'a rencontre le
# 02/08/2026 en ouvrant FreeCAD puis l'atelier sans rien creer.
import re as _redoc
_src_cmd = open(_os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "commands.py")).read()
assert "def assurer_document" in _src_cmd, "le garde-fou a disparu"
# Il est appele AVANT l'ouverture de la fenetre, pas apres : une fenetre
# deja partie derriere ne revient pas.
assert "    assurer_document()" in _src_cmd, (
    "_show n'assure plus de document : la fenetre s'ouvrira derriere la "
    "fenetre principale quand aucun document n'est ouvert")
assert _src_cmd.index("    assurer_document()") \
    < _src_cmd.index("Gui.Control.showDialog(panel)"), (
    "le document doit exister AVANT showDialog -- une fenetre deja partie "
    "derriere ne revient pas")
# Et il ne cree RIEN quand un document est deja la : on n'ajoute pas un
# onglet vide a cote du travail en cours.
assert "if FreeCAD.ActiveDocument is not None:" in _src_cmd

_src_ini = open(_os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "InitGui.py")).read()
_act = _src_ini[_src_ini.index("def Activated"):]
_act = _act[:_act.index("def Deactivated")]
assert "newDocument" in _act, "l'atelier doit ouvrir un document en s'activant"
assert "ActiveDocument is None" in _act, (
    "il ne doit creer un document QUE s'il n'y en a aucun")
print("document : l'atelier en assure un, et n'en cree pas un deuxieme OK")

# --- Un paragraphe doit RENDRE la place qu'il n'utilise plus ------------
# Christophe, 03/08/2026 : « probleme de mise en page » sur le verdict des
# lignes gravees. Mesure : `_WrapLabel` grandissait mais ne redescendait
# JAMAIS. `heightForWidth` d'un QLabel replie repond d'apres la BOITE
# courante et non d'apres le texte, donc une fois la hauteur minimale
# montee il rendait indefiniment l'ancienne valeur -- 102 px conserves pour
# un texte qui en demande 17, et le widget suivant pousse 85 px trop bas.
# Le verdict de ce panneau passe de 2 a 5 lignes selon le regime : il
# gardait donc en permanence la place du pire message jamais affiche.
_hote_par = _Qt.QWidget()
_lay_par = _Qt.QFormLayout(_hote_par)
_par = tp._WrapLabel("")
_lay_par.addRow(_par)
_apres = _Qt.QLabel("SUIVANT")
_lay_par.addRow(_apres)
_hote_par.setAttribute(tp.QtCore.Qt.WA_DontShowOnScreen, True)
_hote_par.resize(500, 400)
_hote_par.show()


def _hauteurs_par(nb_mots):
    _par.setText("<span>x " + "verdict " * nb_mots + "</span>")
    for _ in range(12):
        _Qt.QApplication.processEvents()
    return _par.height(), _apres.y()


_h_court, _y_court = _hauteurs_par(4)
_h_long, _y_long = _hauteurs_par(60)
_h_retour, _y_retour = _hauteurs_par(4)
assert _h_long > _h_court + 20, ("un paragraphe long doit grandir la rangee",
                                 _h_court, _h_long)
assert _h_retour == _h_court, (
    "le paragraphe garde la hauteur du pire message affiche", _h_court,
    _h_long, _h_retour)
assert _y_retour == _y_court, (
    "le widget suivant reste pousse vers le bas", _y_court, _y_retour)
print("paragraphe : {} -> {} -> {} px, la rangee rend la place OK".format(
    _h_court, _h_long, _h_retour))

# references, on laisse Qt digerer, et on sort explicitement.
# --- LES RÉGLAGES NE DOIVENT PAS VIVRE DANS LE MODE D'EMPLOI -----------
# Christophe, 05/08/2026 : « dans hachure les réglages sont dans modes
# d'emploi ». Toute rangée posée après un `_section` appartient à son repli.
# Quand « Mode d'emploi » -- replié par défaut -- est la DERNIÈRE section
# d'un panneau, tout ce qui suit disparaît avec lui.
#
# Le job combiné avait évité ce piège en v2.71 et son commentaire le disait
# déjà ; il vivait encore dans Hachures. Le contrôle porte donc sur TOUS les
# panneaux, pas sur celui qui a été signalé : c'est exactement la famille
# qu'il fallait balayer.
import re as _re_sec                                          # noqa: E402
_src_tp = _i.getsource(tp) if False else open(
    _os.path.join(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))), "task_panels.py"),
    encoding="utf-8").read().splitlines()
_cls = [(_k, _l.split(":")[0][6:]) for _k, _l in enumerate(_src_tp)
        if _l.startswith("class TaskPanel")]
_cls.append((len(_src_tp), "FIN"))
_coupables = []
for (_a, _nomc), (_b, _x) in zip(_cls, _cls[1:]):
    _bloc = _src_tp[_a:_b]
    _secs = [(_k, _re_sec.search(r'_section\(form,\s*"([^"]+)"', _l).group(1))
             for _k, _l in enumerate(_bloc)
             if _re_sec.search(r'_section\(form,\s*"', _l)]
    if not _secs:
        continue
    _dk, _dn = _secs[-1]
    # TOUTE rangée, avec ou sans libellé. Le motif d'origine exigeait
    # `form.addRow("…"` et laissait donc passer `form.addRow(self.lbl_status)`
    # -- exactement la rangée avalée du panneau Projection, signalée par
    # Christophe une fois le contrôle déjà en place. Un balayage trop étroit
    # rassure sans protéger.
    _apres = [_k for _k, _l in enumerate(_bloc)
              if _k > _dk and _re_sec.search(r'form\.addRow\(', _l)]
    if _apres and _dn == "Mode d'emploi":
        _coupables.append((_nomc, len(_apres)))
assert not _coupables, (
    "des réglages sont posés après « Mode d'emploi », dernière section du "
    "panneau : ils disparaissent quand on le replie", _coupables)
print("sections : aucun panneau ne range ses réglages dans son mode "
      "d'emploi ({} panneaux balayés) OK".format(len(_cls) - 1))


for _nom_w, _w in list(globals().items()):
    if _nom_w.startswith("_hote") and isinstance(_w, _Qt.QWidget):
        try:
            _w.setParent(None)
            _w.deleteLater()
        except Exception:
            pass
_Qt.QApplication.processEvents()
sys.stdout.flush()
sys.stderr.flush()
_os._exit(0)

