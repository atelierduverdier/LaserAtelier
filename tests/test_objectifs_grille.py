# -*- coding: utf-8 -*-
"""Un objectif ne doit jamais graver une case qui n'a nulle part où être saisie.

Les deux objectifs « Largeurs brûlées » de la Grille de test gravent une
planche dont on mesure ensuite chaque case au pied à coulisse, dans la
grille de saisie ②. Encore faut-il que la case existe.

Elle n'existait pas. L'objectif au FOYER gravait F400/1800/3200/4600/6000
quand ② n'a de colonnes que pour 200/400/800/1500/3000 : quatre vitesses
sur cinq sans destination. Celui en DÉFOCUS gravait S400/550/700/850/1000 ×
F200/650/1100/1550/2000 : trois puissances et quatre vitesses sans
destination. L'atelier faisait graver une planche puis refusait ses
résultats — et F6000 ne marque plus depuis un changement de lentille, ce
que le code notait déjà à deux endroits.

La cause tient à un détail : les paliers d'une plage min/max/nombre sont
répartis LINÉAIREMENT, alors que les colonnes de saisie sont une
progression géométrique. Aucune plage ne peut les décrire. D'où les listes
explicites, tirées des MÊMES constantes que la grille de saisie, pour que
l'alignement soit structurel et non une coïncidence à entretenir.
"""
from PySide6 import QtWidgets

from harness import preparer, sans_dialogues, texte

h = preparer()
core, tp = h.core, h.tp
# Ce test CLIQUE « + Ajouter ce ton » : une boîte modale
# attendrait un clic humain pour toujours.
sans_dialogues()
G = tp._MesuresPlanchesControleur

# Il n'y a plus d'objectif « largeurs au foyer » : la PLANCHE 1 grave
# exactement cette grille, en traits simples et avec un cadrage de mesure
# automatique, la ou l'objectif gravait ~8 traits par case pour les memes
# 35 nombres. Retire le 03/08/2026. La propriete d'alignement n'est pas
# perdue pour autant -- elle est verifiee sur la planche 1 en §2bis.
CIBLES = {
    "largeurs_defocus": (G.POWERS, G.FEEDS_DEFOCUS),
}


def paliers_lineaires(a, b, n):
    """La répartition qu'utilise build_test_grid_cells sans liste."""
    return [a if n == 1 else a + (b - a) * i / float(n - 1) for i in range(n)]


# --- 1. Une plage ne PEUT PAS décrire les colonnes du foyer -------------
# C'est la raison d'être des listes : le prouver plutôt que l'affirmer.
cols = sorted(G.FEEDS_FOCUS)
trouve = None
for n in range(2, 21):
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            vals = paliers_lineaires(float(cols[i]), float(cols[j]), n)
            if len(vals) >= len(cols) and all(
                    any(abs(v - c) < 1e-6 for v in vals) for c in cols):
                trouve = (cols[i], cols[j], n)
assert trouve is None, (
    "une plage linéaire décrit les colonnes du foyer : les listes "
    "explicites ne servent plus à rien", trouve)
print("1. aucune plage min/max/nombre ne peut produire {} (progression "
      "géométrique) : les listes explicites sont nécessaires OK".format(cols))

# --- 2. Chaque case gravée a une case de saisie ------------------------
p = tp.TaskPanelTestGrid()
recettes = dict(p._recipes)
for cle, (lignes, colonnes) in CIBLES.items():
    idx = [i for i in range(p.combo_recipe.count())
           if p.combo_recipe.itemData(i) == cle]
    assert idx, "objectif « {} » introuvable".format(cle)
    p.combo_recipe.setCurrentIndex(idx[0])
    _mode, _fill, cellules, _dz = p._build_cells()
    assert cellules, ("aucune cellule construite", cle)
    s_gravees = sorted({round(float(c["power"]), 3) for c in cellules})
    f_gravees = sorted({round(float(c["feed"]), 3) for c in cellules})
    orphelines = [(s, f) for s in s_gravees for f in f_gravees
                  if s not in [float(x) for x in lignes]
                  or f not in [float(x) for x in colonnes]]
    assert not orphelines, (
        "cases gravées sans case de saisie", cle, orphelines[:4])
    assert s_gravees == sorted(float(x) for x in lignes), (cle, s_gravees)
    assert f_gravees == sorted(float(x) for x in colonnes), (cle, f_gravees)
    print("   {:<18} grave S{} x F{}  =  les {} lignes et {} colonnes de ② "
          "OK".format(cle, s_gravees, f_gravees, len(lignes), len(colonnes)))

    # Ce que l'ANCIENNE version aurait gravé, pour prouver que le contrôle
    # discrimine. Elle est conservée telle quelle dans ce test, puisque le
    # code ne la porte plus.
    ancien = {"largeurs_defocus": (200.0, 2000.0, 5)}[cle]
    perdues = [f for f in paliers_lineaires(*ancien)
               if f not in [float(x) for x in colonnes]]
    assert perdues, ("l'ancienne plage n'orphelinait rien : ce contrôle ne "
                     "prouve plus rien", cle)
    print("      (l'ancienne plage gravait {} sans destination)".format(
        [round(f) for f in perdues]))
print("2. l'objectif « largeurs en défocus » tombe pile sur la grille ② OK")

# --- 2bis. La PLANCHE 1 porte desormais la mesure au foyer -------------
# L'alignement etait garanti par un commentaire (« doit rester aligne sur
# les feeds par defaut de generate_gcode_planche_focus ») et par rien
# d'autre. Maintenant qu'elle est la SEULE planche des largeurs au foyer,
# on le verifie.
assert sorted(float(x) for x in core.PLANCHE_FOCUS_POWERS) == \
       sorted(float(x) for x in G.POWERS), (
    "la planche 1 ne grave plus les lignes de la saisie ②",
    core.PLANCHE_FOCUS_POWERS, G.POWERS)
assert sorted(float(x) for x in core.PLANCHE_FOCUS_FEEDS) == \
       sorted(float(x) for x in G.FEEDS_FOCUS), (
    "la planche 1 ne grave plus les colonnes de la saisie ②",
    core.PLANCHE_FOCUS_FEEDS, G.FEEDS_FOCUS)
print("2bis. la Planche 1 grave S{} x F{} = la grille ② au foyer OK".format(
    sorted(int(x) for x in core.PLANCHE_FOCUS_POWERS),
    sorted(int(x) for x in core.PLANCHE_FOCUS_FEEDS)))

# --- 3. F6000 ne marque plus : il ne doit plus être gravé --------------
assert not [f for f in core.PLANCHE_FOCUS_FEEDS if float(f) > 3000.0], (
    "la planche 1 grave encore au-delà de F3000, qui ne marque plus depuis "
    "le changement de lentille du 27/07/2026", core.PLANCHE_FOCUS_FEEDS)
print("3. plus aucune case au-delà de F3000 (lentille changée le 27/07/2026) OK")

# --- 4. Les traits de MESURE doivent rester ISOLÉS ---------------------
# Sinon on ne mesure pas la largeur d'un trait mais celle d'un aplat --
# exactement ce que la note demande de faire. La propriete vaut pour les
# deux porteurs : l'entre-rangs de la planche 1, et l'espacement de
# l'objectif en defocus.
# CHAQUE PLANCHE SE COMPARE A SON PROPRE REGIME. Confondre les deux fait
# tomber le controle sans rien apprendre : la brulure la plus large jamais
# mesuree est 3,72 mm, relevee a 55 mm de defocus (planche 2b), alors que
# la planche 1 grave AU FOYER ou le meme bois fait 0,10 a 1,00 mm.
def plus_large_a(niveau, tol=core.SNAP_DEFOCUS_TOLERANCE_MM):
    w = 0.0
    for mat in core.burn_width_materials():
        bw = core.load_burn_widths(mat)
        pts = (bw.get("focus") or []) if niveau <= 0 else (bw.get("defocus") or [])
        for pt in pts:
            z = float(pt.get("z_offset", 0) or 0)
            if niveau <= 0 or abs(z - niveau) <= tol:
                w = max(w, float(pt.get("width", 0) or 0))
    return w

import inspect as _insp
_row_gap = float(_insp.signature(
    core.disposition_planche_focus).parameters["row_gap"].default)
_dz_obj = recettes["largeurs_defocus"]["cell_defocus"]
for nom, ecart, niveau in (
        ("planche 1 (entre-rangs)", _row_gap, 0.0),
        ("objectif défocus {:.0f}".format(_dz_obj),
         recettes["largeurs_defocus"]["hatch_spacing"], _dz_obj)):
    large = plus_large_a(niveau)
    assert large > 0, ("aucune largeur mesurée à ce régime", nom)
    assert ecart > large * 1.5, (
        "{} : l'écart de {} mm n'est pas assez grand devant la brûlure la "
        "plus large mesurée À CE RÉGIME ({} mm) -- les traits se toucheront "
        "et il n'y aura plus de largeur à mesurer".format(nom, ecart, large))
    print("4. {:<24} écart {:.2f} mm contre {:.2f} mm de brûlure la plus "
          "large à ce régime : traits isolés OK".format(nom, ecart, large))

# --- 4bis. Un objectif de MESURE grave des traits HORIZONTAUX ----------
# `profil_trait` moyenne les COLONNES de l'image : le trait doit etre
# horizontal, sinon la moyenne traverse du bois nu et la largeur lue n'a
# aucun sens. Le panneau est a 45 deg par defaut, et jusqu'au 03/08/2026
# aucun objectif ne pouvait imposer l'angle -- la planche sortait en
# diagonale, ni mesurable a la main ni cadrable automatiquement.
assert recettes["largeurs_defocus"].get("hatch_angle") == 0.0, (
    "l'objectif de mesure ne force pas l'angle a 0 : ses traits sortiront "
    "en diagonale et ne seront pas mesurables",
    recettes["largeurs_defocus"].get("hatch_angle"))
_i = [i for i in range(p.combo_recipe.count())
      if p.combo_recipe.itemData(i) == "largeurs_defocus"][0]
p.combo_recipe.setCurrentIndex(_i)
assert abs(p.spn_hatch_angle.value()) < 1e-9, (
    "l'angle du panneau n'a pas suivi la recette", p.spn_hatch_angle.value())
print("4bis. l'objectif de mesure impose des traits HORIZONTAUX (0 deg) OK")

# --- 5. Les champs de plage sont verrouillés, et libérés ensuite -------
# Une plage affichée que le job n'utilise pas serait une interface qui ment.
assert all(not c.isEnabled() for c in p._champs_plages), (
    "les champs de plage restent modifiables alors que l'objectif fixe les "
    "paliers")
assert not p.lbl_paliers.isHidden(), "les paliers gravés ne sont pas affichés"
affiche = texte(p.lbl_paliers.text())
# Les vitesses de l'objectif SELECTIONNE (defocus depuis le 03/08/2026,
# l'objectif au foyer ayant ete retire au profit de la planche 1) -- pas
# une liste ecrite en dur, qui rendrait ce controle faux au premier
# changement d'objectif.
for f in G.FEEDS_DEFOCUS:
    assert str(int(f)) in affiche, ("vitesse absente de l'affichage", f, affiche)
p.combo_recipe.setCurrentIndex(0)          # — (réglages manuels) —
assert all(c.isEnabled() for c in p._champs_plages), (
    "les champs de plage restent verrouillés après retour aux réglages "
    "manuels")
assert p.lbl_paliers.isHidden(), "l'affichage des paliers survit à l'objectif"
_m, _f, cellules, _dz = p._build_cells()
assert cellules, "plus rien ne se construit en réglages manuels"
print("5. paliers imposés : champs verrouillés + valeurs affichées ; retour "
      "aux réglages manuels : tout est libéré OK")

# --- 6. Les objectifs de JUGEMENT gardent leurs plages libres ----------
# Ils ne se mesurent pas au pied à coulisse : rien à aligner, et une plage
# y est le bon outil.
for cle in ("nuancier_clair", "decoupe"):
    r = recettes[cle]
    assert "powers" not in r and "feeds" not in r, (
        "un objectif de jugement s'est vu imposer des paliers", cle)
    assert "power_min" in r and "feed_min" in r, (cle, "plage manquante")
print("6. « nuancier clair » et « découpe » gardent leurs plages libres OK")

# --- 7. La bande de noirceur en balayage -------------------------------
# C'est elle qui alimente `darkness_fluence_curve`, donc la photo calibrée
# et le « ton sur mesure ». Cette courbe n'accepte QUE les tons réunissant
# un défocus > 0 ET une largeur > 0 : un nuancier riche en noirceurs mais
# sans largeur ne lui sert à rien, et c'est un piège silencieux.
r = recettes["noirceur_balayage"]
idx = [i for i in range(p.combo_recipe.count())
       if p.combo_recipe.itemData(i) == "noirceur_balayage"][0]
p.combo_recipe.setCurrentIndex(idx)
_m, _f, cellules, dz = p._build_cells()
vitesses = {round(float(c["feed"]), 3) for c in cellules}
assert len(vitesses) == 1, (
    "la bande doit tenir sur UNE vitesse : à énergie égale, plus c'est "
    "lent plus c'est foncé, et une courbe à vitesses mélangées est "
    "incohérente par construction", sorted(vitesses))
assert dz > 0, ("la bande doit être gravée en défocus", dz)

# Les puissances couvrent la plage, mais PAS dans l'ordre : rangées par
# ordre croissant, les cases se jugent les unes par rapport aux autres.
ordre = [float(c["power"]) for c in sorted(cellules, key=lambda c: c["col"])]
assert len(ordre) >= 8, ("trop peu de paliers pour juger une échelle", ordre)
assert ordre != sorted(ordre) and ordre != sorted(ordre, reverse=True), (
    "les puissances sont rangées dans l'ordre : l'œil reconstruira une "
    "progression régulière qui n'existe pas", ordre)
voisins_consecutifs = [
    (a, b) for a, b in zip(ordre, ordre[1:])
    if abs(sorted(ordre).index(a) - sorted(ordre).index(b)) == 1]
assert not voisins_consecutifs, (
    "deux paliers consécutifs en énergie sont côte à côte sur la planche",
    voisins_consecutifs)
print("7. bande : {} cases sur la SEULE vitesse F{:.0f}, défocus {:g} mm, "
      "puissances mélangées OK".format(
          len(cellules), sorted(vitesses)[0], dz))

# --- 8. La saisie du ton est pré-remplie, largeur = LE PAS -------------
# Pré-remplir plutôt qu'avertir : c'est l'erreur qui coûte un facteur 8.
champs = p._ton_rapide
MAT_TEST = u"Test balayage"
p.edt_measure_mat.setCurrentText(MAT_TEST)
p.combo_recipe.setCurrentIndex(0)
p.combo_recipe.setCurrentIndex(idx)          # rejoue l'application
# On relit par le comportement plutôt que par les widgets : ajouter le ton
# et vérifier ce qui a été ENREGISTRÉ est la seule preuve qui compte.
for b in p.form.findChildren(QtWidgets.QPushButton):
    if b.text() == "+ Ajouter ce ton":
        b.click()
        break
else:
    raise AssertionError("bouton « + Ajouter ce ton » absent de la Grille de test")
tons = core.load_shades(MAT_TEST)
assert len(tons) == 1, ("le ton n'a pas été enregistré", tons)
t = tons[0]
assert abs(float(t["feed"]) - sorted(vitesses)[0]) < 1e-6, (
    "vitesse non pré-remplie", t)
assert abs(float(t["z_offset"]) - dz) < 1e-6, ("défocus non pré-rempli", t)
assert abs(float(t["width"]) - r["hatch_spacing"]) < 1e-9, (
    "la largeur pré-remplie n'est pas le PAS de hachure -- c'est "
    "exactement l'erreur qui fausse la courbe d'un facteur 8",
    t.get("width"), r["hatch_spacing"])
print("8. « + Ajouter ce ton » pré-rempli : F{:.0f}, défocus {:g}, largeur "
      "{:.2f} = le pas de hachure OK".format(
          float(t["feed"]), float(t["z_offset"]), float(t["width"])))

# --- 9. Le ton produit est EXPLOITABLE par la courbe -------------------
# Le seul contrôle qui dise que cet objectif sert à quelque chose.
assert float(t.get("z_offset", 0) or 0) > 0 and float(t.get("width", 0) or 0) > 0, (
    "le ton produit n'a pas le couple défocus+largeur qu'exige "
    "darkness_fluence_curve", t)
print("9. le ton porte le couple défocus>0 ET largeur>0 qu'exige la courbe "
      "noirceur → énergie OK")

# --- 10. Le parcours ★ nomme des objectifs qui EXISTENT ----------------
# Le parcours de première calibration (CALIBRATION_JOURNEY) est ce que
# suit quelqu'un qui n'a rien de mesuré : il alimente le Guide rapide ET
# le bandeau ★ en tête de chaque panneau de calibration. Il cite les
# objectifs par leur libellé -- donc en toutes lettres, sans que rien ne
# vérifie qu'ils existent. Ajouter un objectif sans l'y inscrire, ou en
# renommer un, laisse un parcours qui envoie dans le vide, en silence.
libelles = {r["label"] for _cle, r in p._recipes}
cites = []
for etape in core.CALIBRATION_JOURNEY:
    for action in etape["action"]:
        for lib in libelles:
            if lib in action:
                cites.append(lib)
assert cites, "le parcours ne cite plus aucun objectif"
# Tout objectif cité doit exister : c'est garanti par construction
# ci-dessus. L'inverse est le vrai contrôle -- les objectifs de MESURE
# doivent tous être dans le parcours, sinon on grave sans savoir pourquoi.
mesure = {"largeurs_defocus", "noirceur_balayage"}
manquants = [cle for cle in mesure
             if dict(p._recipes)[cle]["label"] not in cites]
assert not manquants, (
    "des objectifs de mesure ne sont dans AUCUNE étape du parcours : un "
    "atelier qui suit le guide à la lettre finira sans ces données",
    manquants)
# ET L'INVERSE, qui manquait : le parcours ne doit citer AUCUN objectif
# disparu. Le 03/08/2026 il envoyait encore choisir « Largeurs brûlées —
# grille au foyer », retire le matin meme -- un atelier qui suit le guide
# cherchait dans la liste une entree qui n'y est plus. Le controle
# existant ne pouvait pas le voir : il ne regarde que les objectifs
# PRESENTS. On cherche donc la forme « Objectif « ... » » dans le texte,
# et on exige que chaque nom cite ainsi existe.
import re as _re_j
_cites_nommes = set()
for etape in core.CALIBRATION_JOURNEY:
    for action in etape["action"]:
        for m in _re_j.finditer("Objectif\s*«\s*([^»]+?)\s*»", action):
            _cites_nommes.add(m.group(1))
_fantomes = sorted(n for n in _cites_nommes if n not in libelles)
assert not _fantomes, (
    "le parcours envoie choisir un Objectif qui n'existe pas dans la liste",
    _fantomes, sorted(libelles))
print("10. le parcours ★ cite les {} objectifs de mesure, et aucun fantôme "
      "({} nom(s) vérifié(s)) OK".format(len(mesure), len(_cites_nommes)))

# --- La zone F800-F1500 doit être MESURABLE ----------------------------
# Il n'y avait rien entre 800 et 1500, et c'est exactement là que le
# tramage « Lignes gravées » se joue : à F800 le trait va de 0,10 à
# 0,30 mm, à F1500 il est plat. Tout ce que l'atelier annonçait entre les
# deux était une droite tracée entre deux mesures. Ajouté le 31/07/2026.
cols = list(tp._MesuresPlanchesControleur.FEEDS_FOCUS)
interieurs = [f for f in cols if 800 < f < 1500]
assert len(interieurs) >= 2, (
    "la zone où le trait cesse d'enfler doit être encadrée par au moins "
    "deux vitesses mesurables", cols)
assert cols == sorted(cols), ("colonnes non triées", cols)

# La Planche 1 doit graver EXACTEMENT ces vitesses -- sinon on regrave un
# carton dont les cases n'ont nulle part où être saisies (défaut v2.3.1).
import re as _re
_g = core.generate_gcode_planche_focus()
_fs = sorted({int(float(m.group(1))) for m in _re.finditer(r"F([\d.]+)", _g)})
_manque = [f for f in cols if f not in _fs]
assert not _manque, ("la Planche 1 ne grave pas toutes les colonnes de ②",
                     _manque, _fs)
print("Zone F800-F1500 : {} vitesses intérieures ({}), gravées par la "
      "Planche 1 et saisissables en ② OK".format(
          len(interieurs), interieurs))

print("\nTOUS LES TESTS objectifs_grille PASSENT")
