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

print("\nTOUS LES TESTS panneaux PASSENT")
