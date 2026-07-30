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
REGIMES = {6: (0.30, 800.0)}
DEFAUT = (0.80, 2000.0)

assert p.combo_mode.count() == 7, p.combo_mode.count()
for idx in range(p.combo_mode.count()):
    p.combo_mode.setCurrentIndex(idx)
    nom = p.combo_mode.currentText()
    pas, feed = REGIMES.get(idx, DEFAUT)
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
print("2. les 7 tramages génèrent, s'affichent et se prononcent OK")

# --- 3. Les réglages affichés sont ceux qui S'APPLIQUENT -----------------
# « Largeur du point » pilote le DÉFOCUS : l'afficher dans un tramage qui
# grave au foyer faisait raisonner le verdict sur 0,80 mm pendant que la
# machine traçait 0,10 à 0,30.
AU_FOYER = (5, 6)
for idx in range(7):
    p.combo_mode.setCurrentIndex(idx)
    nom = p.combo_mode.currentText()
    visible = not p.spn_spot_width.isHidden()
    assert visible == (idx not in AU_FOYER), (idx, nom, "largeur du point")
    assert (not p.spn_dot_spacing.isHidden()) == (idx == 5), (idx, nom)
    assert (not p.spn_line_min.isHidden()) == (idx == 6), (idx, nom)
    # Les tramages qui calculent la puissance par pixel ne doivent pas
    # laisser croire qu'on la règle à la main.
    assert p.spn_power.isEnabled() == (idx not in (2, 6)), (idx, nom, "puissance")
print("3. réglages visibles/actifs cohérents avec chaque tramage OK")

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

print("\nTOUS LES TESTS panneaux PASSENT")
