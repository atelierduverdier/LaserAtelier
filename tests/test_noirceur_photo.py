# -*- coding: utf-8 -*-
"""Lecture de la noirceur sur photo redressee : geometrie et normalisation.

Le piege central est un RETOURNEMENT : le G-code a Y vers le HAUT, l'image
Y vers le BAS. Une erreur de sens ne casse rien -- elle lit des cases
voisines, avec des valeurs parfaitement plausibles, et le nuancier entier
part a l'envers sans qu'aucune exception ne se leve.
"""
from harness import preparer
h = preparer()
core = h.core

# --- 1. Le repere de la mire, et le sens du Y ---------------------------
INFOS = {"x0": 10.0, "y0": 20.0, "largeur": 100.0, "hauteur": 60.0,
         "power": 150.0, "feed": 300.0, "laser": "bleu"}
COTE, PAS = 6.0, 8.0
cells = [{"row": r, "col": c, "power": 200.0 + 100 * c, "feed": 400.0,
          "x0": 10.0 + c * PAS, "y0": 20.0 + r * PAS}
         for r in range(3) for c in range(4)]
f = core.fiche_grille_noirceur(cells, COTE, INFOS, marge_lecture=0.0)
assert f and len(f["cases"]) == 12, f
par = {(c["row"], c["col"]): c for c in f["cases"]}

# La case row=0 est la plus BASSE sur la machine, donc la plus HAUTE en y
# d'image : son y0 d'image doit etre le plus GRAND des trois rangees.
y0 = [par[(r, 0)]["y0"] for r in range(3)]
assert y0[0] > y0[1] > y0[2], ("le Y n'est pas retourne : la rangee 0 est en "
                               "bas sur la machine, donc en BAS de l'image", y0)
# Et la colonne 0 reste a gauche : le X, lui, ne se retourne pas.
x0 = [par[(0, c)]["x0"] for c in range(4)]
assert x0 == sorted(x0), ("le X ne doit PAS etre retourne", x0)

# Case (0,0) : coin machine (10,20)-(16,26), mire en (10,20) haute de 60.
# Image : x 0..6 ; y = 80-26=54 .. 80-20=60.
c00 = par[(0, 0)]
for cle, attendu in (("x0", 0.0), ("x1", 6.0), ("y0", 54.0), ("y1", 60.0)):
    assert abs(c00[cle] - attendu) < 1e-9, (cle, c00[cle], attendu)
# Toute case tient DANS la mire : sinon on lirait hors de la photo.
for c in f["cases"]:
    assert 0 <= c["x0"] < c["x1"] <= INFOS["largeur"], c
    assert 0 <= c["y0"] < c["y1"] <= INFOS["hauteur"], c
print("1. le repere de la mire retourne le Y et pas le X OK")

# --- 2. La marge de lecture rogne le BORD, pas le centre ----------------
f2 = core.fiche_grille_noirceur(cells, COTE, INFOS, marge_lecture=0.25)
d = par[(0, 0)]
r = [c for c in f2["cases"] if (c["row"], c["col"]) == (0, 0)][0]
assert r["x0"] > d["x0"] and r["x1"] < d["x1"], (d, r)
# Le CENTRE ne bouge pas : on lit moins large, pas ailleurs.
for a, b in (("x0", "x1"), ("y0", "y1")):
    assert abs((r[a] + r[b]) - (d[a] + d[b])) < 1e-9, (a, b, d, r)
print("2. la marge de lecture rogne le bord sans deplacer le centre OK")

# --- 3. mm -> pixels : la marge du redressement --------------------------
photo = {"largeur_mm": 110.0, "base_mm": [100.0, 60.0], "pxmm": 40.0}
assert abs(core.marge_photo(photo) - 5.0) < 1e-9, core.marge_photo(photo)
px = core.case_en_pixels(par[(0, 0)], photo["pxmm"], core.marge_photo(photo))
assert px == (200, 2360, 440, 2600), px
assert core.marge_photo({}) == 0.0
print("3. mm -> pixels passe par la marge du redressement OK")

# --- 4. La normalisation, et son refus ----------------------------------
assert abs(core.noirceur_normalisee(200.0, 200.0, 40.0) - 0.0) < 1e-9
assert abs(core.noirceur_normalisee(40.0, 200.0, 40.0) - 100.0) < 1e-9
assert abs(core.noirceur_normalisee(120.0, 200.0, 40.0) - 50.0) < 1e-9
# Insensible a l'exposition : tout decaler d'un facteur ne change rien.
for k in (0.5, 1.4):
    assert abs(core.noirceur_normalisee(120.0*k, 200.0*k, 40.0*k) - 50.0) < 1e-6, k
# Hors bornes : borne, jamais negatif ni au-dela de 100.
assert core.noirceur_normalisee(230.0, 200.0, 40.0) == 0.0
assert core.noirceur_normalisee(10.0, 200.0, 40.0) == 100.0
# Deux reperes trop proches : REFUS, pas un pourcentage sur du bruit.
assert core.noirceur_normalisee(100.0, 120.0, 100.0) is None, (
    "un ecart de %g niveaux doit etre refuse" % core.ECART_REPERES_MINI)
assert core.noirceur_normalisee(100.0, 100.0, 100.0) is None
print("4. la normalisation est insensible a l'exposition, et refuse le bruit OK")

# --- 5. Cas vides -------------------------------------------------------
assert core.fiche_grille_noirceur([], COTE, INFOS) is None
assert core.fiche_grille_noirceur(cells, COTE, None) is None
assert core.bbox_grille_test([], COTE) is None
bb = core.bbox_grille_test(cells, COTE)
assert bb == (10.0, 20.0, 10.0 + 3*PAS + COTE, 20.0 + 2*PAS + COTE), bb
print("5. entrees vides : None plutot qu'une fiche a moitie vraie OK")

# --- 6. Le panneau : case a cocher, mire gravee, fiche deposee ----------
from harness import sans_dialogues
sans_dialogues()
tp = h.tp
p = tp.TaskPanelTestGrid()
assert hasattr(p, "chk_mire"), "la case « mire » manque au panneau Grille"
# PAS d'assertion sur l'etat COCHE : il est memorise d'une session a
# l'autre, donc il vaut ce que Christophe a laisse. Un test qui rougit
# parce qu'il a coche une case apprend a ignorer le rouge.
assert "mire" in p._last_fields, "la case doit se souvenir entre deux sessions"
assert hasattr(p, "_deposer_fiche_grille"), "le depot de fiche manque"

# La mire change VRAIMENT le G-code produit, et seulement quand on coche.
COTE = 6.0
_cells = core.build_test_grid_cells("gravure", 200.0, 1000.0, 3, 400.0, 800.0, 2,
                                    COTE, 2.0, fill_type="paralleles",
                                    hatch_spacing=0.4)
_sans = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                      mire=False, quiet=True)
_avec = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                      mire=True, quiet=True)
assert "Mire de mesure" not in _sans, "mire gravee sans avoir ete demandee"
assert "Mire de mesure" in _avec, "mire demandee mais absente du G-code"
assert len(_avec) > len(_sans), (len(_avec), len(_sans))

# La mire est AU FOYER : la planche ne doit pas gagner une troisieme hauteur
# quand les cellules sont defocalisees, sinon la reference serait floue.
import re as _re2
def _hauteurs(g):
    return sorted({round(float(m.group(1)), 3)
                   for l in g.split("\n") for m in [_re2.search(r"\bZ(-?[\d.]+)", l)] if m})
_defoc = core.generate_gcode_test_grid(_cells, core.Z_WORK_MM, cell_size=COTE,
                                       mire=True, cell_z_offset=12.0, quiet=True)
_h = _hauteurs(_defoc)
assert core.Z_WORK_MM in _h, ("la mire doit rester au foyer", _h)
assert len(_h) == 3, ("foyer + defocus + retrait, pas une de plus", _h)
print("6. la case grave la mire, au foyer, et seulement si on la coche OK")

# --- 7. Une section NEUVE s'ouvre : sinon la nouveaute nait invisible ----
# Le defaut demande par l'appelant etait ignore (`_section_state_get(cle,
# False)` en dur), si bien qu'une section que PERSONNE n'a jamais repliee
# -- puisqu'elle vient d'exister -- s'ouvrait fermee. Trois fonctionnalites
# ont ete cherchees sans etre trouvees pour cette raison le 01/08/2026.
_e = tp._SectionHeader("Section neuve de test", ouvert=True)
assert _e.ouvert_par_defaut() is True
assert tp._SectionHeader("Autre", ouvert=False).ouvert_par_defaut() is False
# Le clic bouge l'etat COURANT, jamais le defaut.
_e.setChecked(False)
assert _e.ouvert_par_defaut() is True, "le defaut ne doit pas suivre les clics"

# Et la case de la mire est reellement VISIBLE dans le panneau -- pour une
# section NEUVE. L'etat memorise est celui de Christophe : l'accordeon
# l'enregistre des qu'il deplie autre chose, et un test bati dessus rougit
# parce qu'il s'est servi du logiciel. On repart donc d'un etat efface.
tp._section_states().pop("Mesure sur photo", None)
_p2 = tp.TaskPanelTestGrid()
assert not _p2.chk_mire.isHidden(), "la case de la mire est cachee"
_par = _p2.chk_mire.parentWidget()
assert _par is not None and _par.isVisibleTo(_par.parentWidget() or _par), (
    "la case est dans une section repliee : elle existe et ne se voit pas")
# Un etat MEMORISE prime toujours sur le defaut : replier reste un choix.
tp._section_states()["Mesure sur photo"] = False
_p3 = tp.TaskPanelTestGrid()
assert _p3.chk_mire.parentWidget() is not None
assert not _p3.chk_mire.parentWidget().isVisibleTo(
    _p3.chk_mire.parentWidget().parentWidget()), (
    "une section repliee A LA MAIN doit le rester")
del tp._section_states()["Mesure sur photo"]
print("7. une section neuve s'ouvre, une section repliee a la main le reste OK")

# --- 8. Le VRAI bouton, pas les helpers qui l'entourent -----------------
# Le 01/08/2026 le panneau appelait `self.spn_cell`, un widget qui n'existe
# pas : cliquer « Generer » creait les objets 3D puis levait une
# AttributeError avant d'ecrire la moindre ligne de G-code. Rien ne l'a vu,
# parce que la verification appelait `_deposer_fiche_grille` DIRECTEMENT et
# enjambait la ligne cassee. On verifie le chemin qu'on CLIQUE.
import os as _os, tempfile as _tf, json as _json
_ecrits = []
_vrai_write = tp._write_gcode_with_dialog
def _faux_write(parent, gcode, defaut, **kw):
    d = _tf.mkdtemp()
    chemin = _os.path.join(d, _os.path.basename(defaut))
    with open(chemin, "w") as fh:
        fh.write(gcode)
    _ecrits.append(chemin)
    return chemin
tp._write_gcode_with_dialog = _faux_write
# Le bouton cree de vrais objets : sans document actif il refuse, et le
# test croirait avoir eprouve le chemin alors qu'il s'est arrete a la
# premiere ligne.
_doc = h.FreeCAD.newDocument("EssaiGrilleMire")
try:
    _pg = tp.TaskPanelTestGrid()
    _pg.chk_mire.setChecked(True)
    _pg.combo_mode.setCurrentIndex(0)
    _pg.combo_filltype.setCurrentIndex(2)
    _pg.spn_hatch_spacing.setValue(1.0)
    _pg.spn_power_min.setValue(200.0); _pg.spn_power_max.setValue(1000.0)
    _pg.spn_power_steps.setValue(6)
    _pg.spn_feed_min.setValue(400.0); _pg.spn_feed_max.setValue(4000.0)
    _pg.spn_feed_steps.setValue(4)
    _pg.spn_cell_size.setValue(10.0); _pg.spn_gap.setValue(3.0)
    _pg._on_generer()                      # LE BOUTON
finally:
    tp._write_gcode_with_dialog = _vrai_write
assert _ecrits, "le bouton Generer n'a produit aucun fichier"
_g = open(_ecrits[0]).read()
assert "Mire de mesure" in _g, "case cochee, mais pas de mire dans le G-code"
_fiche = _os.path.splitext(_ecrits[0])[0] + "_grille.json"
assert _os.path.isfile(_fiche), ("la fiche n'a pas ete deposee a cote du G-code",
                                 _ecrits[0])
_f8 = _json.load(open(_fiche))
assert len(_f8["cases"]) == 24, len(_f8["cases"])
# La mire doit aussi exister dans le DOCUMENT : un apercu qui ne montre pas
# ce qui sera grave ne permet pas de verifier l'encombrement.
_noms = [o.Name for o in _doc.Objects]
assert any("Mire" in n for n in _noms), (
    "la mire n'apparait pas dans la vue 3D", _noms[:8])
print("8. le bouton Generer produit G-code + fiche + mire visible OK")

# --- 9. LES QUATRE appels au generateur, pas seulement celui du bouton --
# Trois aperçus -- duree, cadrage, trajet -- ignoraient la mire et
# decrivaient donc une planche plus PETITE que celle qui sortira. Le
# cadrage est le pire : il sert justement a verifier que la piece tient,
# et il tracait un rectangle amputee des 25 mm de reglette.
import inspect as _insp
_src = _insp.getsource(tp.TaskPanelTestGrid)
_appels = _src.count("core.generate_gcode_test_grid(")
_avec = _src.count("self._kw_mire()")
assert _appels >= 4, ("moins d'appels que prevu", _appels)
assert _avec >= _appels, (
    "un appel au generateur n'emporte pas la mire : l'apercu decrirait "
    "une planche plus petite que la vraie", _appels, _avec)

# Et le CADRAGE, en vrai : avec mire, le rectangle doit etre plus grand.
_doc2 = h.FreeCAD.newDocument("EssaiCadrageMire")
try:
    _pc = tp.TaskPanelTestGrid()
    _pc.spn_power_min.setValue(200.0); _pc.spn_power_max.setValue(1000.0)
    _pc.spn_power_steps.setValue(3)
    _pc.spn_feed_min.setValue(400.0); _pc.spn_feed_max.setValue(2000.0)
    _pc.spn_feed_steps.setValue(2)
    _pc.spn_cell_size.setValue(10.0); _pc.spn_gap.setValue(3.0)
    _mode, _ft, _cl, _dz = _pc._build_cells(silent=True)
    _, _, _le = _pc._build_label_edges(_cl)

    def _cadre(avec):
        _pc.chk_mire.setChecked(avec)
        g = core.generate_gcode_test_grid(
            _cl, _pc.spn_zwork.value(), label_edges=_le,
            cell_z_offset=_dz, frame_only=True,
            **dict(_pc._border_kwargs(), **_pc._kw_mire()))
        ys = [float(m.group(1)) for l in g.split("\n")
              for m in [__import__("re").search(r"Y(-?[\d.]+)", l)] if m]
        return min(ys), max(ys)

    _sans_y = _cadre(False)
    _avec_y = _cadre(True)
    assert _avec_y[0] < _sans_y[0] - 10.0, (
        "le cadrage avec mire doit descendre BIEN plus bas (la reglette)",
        _sans_y, _avec_y)
    print("9. les 4 appels emportent la mire ; le cadrage descend de "
          "%.0f mm de plus OK" % (_sans_y[0] - _avec_y[0]))
finally:
    h.FreeCAD.closeDocument(_doc2.Name)
h.FreeCAD.closeDocument(_doc.Name)


# --- 10. La LECTURE, sur une planche fabriquee de toutes pieces ---------
# On peint une fausse photo redressee dont on CONNAIT la noirceur de
# chaque case, et on verifie que le lecteur retrouve ce qu'on y a mis.
# C'est le seul moyen d'eprouver la chaine avant que le bois existe.
from PySide6 import QtGui as _QtGui, QtCore as _QtCore

_INF = {"x0": 0.0, "y0": 0.0, "largeur": 100.0, "hauteur": 80.0}
_COTE, _PAS = 10.0, 13.0
_cells10 = [{"row": r, "col": c, "power": 200.0 + 200 * c, "feed": 400.0 + 400 * r,
             "x0": 2.0 + c * _PAS, "y0": 2.0 + r * _PAS}
            for r in range(4) for c in range(5)]
_f10 = core.fiche_grille_noirceur(_cells10, _COTE, _INF)
_PXMM, _MARGE = 20.0, 5.0
_W = int((_INF["largeur"] + 2 * _MARGE) * _PXMM)
_H = int((_INF["hauteur"] + 2 * _MARGE) * _PXMM)
_im = _QtGui.QImage(_W, _H, _QtGui.QImage.Format_RGB32)
_im.fill(_QtGui.QColor(210, 200, 180))          # bois nu
_p10 = _QtGui.QPainter(_im)
# Noirceur VOULUE : croissante avec la colonne, decroissante avec la rangee.
_voulu = {}
for c in _f10["cases"]:
    v = 100.0 * (c["col"] / 4.0) * (1.0 - 0.3 * c["row"] / 3.0)
    _voulu[(c["row"], c["col"])] = v
    # bois 210 -> noir 30 : le gris peint suit exactement la definition.
    g = int(round(210 - (210 - 30) * v / 100.0))
    x0, y0, x1, y1 = tp._DialogueNoirceur._px.__get__(
        type("F", (), {"_marge": _MARGE, "_pxmm": _PXMM})())(
        (c["x0"], c["y0"], c["x1"], c["y1"]))
    _p10.fillRect(_QtCore.QRect(x0, y0, x1 - x0, y1 - y0), _QtGui.QColor(g, g, g))
# Une case VRAIMENT noire quelque part, pour l'ancre : c'est (3,4) a 70 %,
# on force donc un carre noir dans la marge pour ne pas fausser la grille.
_p10.end()

# Le gris moyen doit retrouver ce qui a ete peint.
_c00 = [c for c in _f10["cases"] if (c["row"], c["col"]) == (0, 0)][0]
_faux = type("F", (), {"_marge": _MARGE, "_pxmm": _PXMM})()
_rect = tp._DialogueNoirceur._px.__get__(_faux)(
    (_c00["x0"], _c00["y0"], _c00["x1"], _c00["y1"]))
assert abs(tp._gris_moyen(_im, _rect) - 210.0) < 1.0, tp._gris_moyen(_im, _rect)

# La lecture complete : ancres = bois nu peint (210) et la case la plus
# sombre reellement presente.
_gris = {}
for c in _f10["cases"]:
    r = tp._DialogueNoirceur._px.__get__(_faux)((c["x0"], c["y0"], c["x1"], c["y1"]))
    _gris[(c["row"], c["col"])] = tp._gris_moyen(_im, r)
_gn = min(_gris.values())
_lu = {k: core.noirceur_normalisee(g, 210.0, _gn) for k, g in _gris.items()}
_vmax = max(_voulu.values())
_ecarts = [abs(_lu[k] - _voulu[k] * 100.0 / _vmax) for k in _voulu]
assert max(_ecarts) < 2.0, ("la lecture s'ecarte de ce qui a ete peint",
                            max(_ecarts))
# Et le SENS : plus noir a droite, moins noir quand la rangee monte.
assert _lu[(0, 4)] > _lu[(0, 0)], "la noirceur doit croitre avec la colonne"
assert _lu[(0, 4)] > _lu[(3, 4)], "elle doit decroitre quand la rangee monte"
print("10. la lecture retrouve la noirceur peinte a %.1f point pres, "
      "et dans le bon sens OK" % max(_ecarts))

# --- 11. Le repere « bois nu » ne tombe pas dans une case ---------------
_cand = core.reperes_candidats(_f10)
assert _cand, "aucun croisement d'ecart propose"
_r = core.marge_lecture_mm if hasattr(core, "marge_lecture_mm") else \
    _f10["marge_lecture"] * _f10["cote_case_mm"]
def _vrai10(c):
    return (c["x0"] - _r, c["y0"] - _r, c["x1"] + _r, c["y1"] + _r)
for _cx0, _cy0, _cx1, _cy1 in _cand:
    for c in _f10["cases"]:
        a, b, cc, d = _vrai10(c)
        assert _cx1 <= a or _cx0 >= cc or _cy1 <= b or _cy0 >= d, (
            "un repere de bois nu chevauche une case gravee", c["row"], c["col"])
# Et sur la fausse photo, ils lisent le MEME gris qu'un coin de bois
# intact. Comparer a une RELATION et non a un litteral : le bois peint est
# (210,200,180), dont la luminance vaut 200,7 -- attendre 210 revenait a
# confondre la composante rouge avec le gris, et le test tombait sur une
# valeur pourtant juste.
_bois_pur = tp._gris_moyen(_im, (2, 2, 40, 40))
for cand in _cand[:6]:
    g = tp._gris_moyen(_im, tp._DialogueNoirceur._px.__get__(_faux)(cand))
    assert g is not None and abs(g - _bois_pur) < 1.0, (
        "un repere de bois nu ne lit pas le meme gris qu'un coin intact",
        g, _bois_pur)
print("11. les %d reperes de bois nu proposes lisent tous du bois intact OK"
      % len(_cand))

print("\nTOUS LES TESTS noirceur_photo PASSENT")
