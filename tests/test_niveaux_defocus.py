# -*- coding: utf-8 -*-
"""Le niveau de défocus est LIBRE, et ② ne détruit plus ce qu'il n'affiche pas.

Trois défauts se tenaient par la main, tous découverts en auditant la
procédure de calibration le 30/07/2026 :

1. **`_on_save` de ② remplaçait la table au lieu de la fusionner.** Or
   `save_burn_widths` écrase le matériau. Sur le hêtre de l'atelier, un
   clic sur « Enregistrer les mesures » aurait supprimé **27 des 54**
   mesures en défocus — toutes celles dont la puissance, la vitesse ou le
   niveau sortaient des grilles. Des heures de pied à coulisse, sans un
   mot, sur simple clic d'un bouton qui promet d'enregistrer.

2. **`reload` rangeait un point dans la grille du niveau le plus proche,
   sans limite de distance.** Une mesure à 60 mm s'affichait donc dans la
   grille « 36 mm », et l'enregistrement la réécrivait à 36.

3. **Les grilles n'existaient que pour 15 et 36 mm.** Graver une planche à
   un autre défocus ne menait nulle part : la mesure n'avait aucune case.
   Et `_snap_defocus_level`, avec ses 5 mm de tolérance, ramenait de toute
   façon un 40 choisi à 36.

Ce test protège les trois. Le premier est le plus important : c'est le
seul qui puisse détruire une donnée irremplaçable.
"""
from harness import preparer, sans_dialogues

h = preparer()
core, tp = h.core, h.tp
# Ce test CLIQUE « Enregistrer les mesures », qui confirme par une boîte
# modale : sans ça, il attendrait un clic humain pour toujours.
dialogues = sans_dialogues()
MAT = u"Hêtre"
G = tp._MesuresPlanchesControleur

# --- 1. La tolérance de rangement ne peut plus avaler un niveau choisi --
assert core.SNAP_DEFOCUS_TOLERANCE_MM <= 2.0, core.SNAP_DEFOCUS_TOLERANCE_MM
# Les graduations de la rampe Z sont espacées de 5 mm : la tolérance doit
# rester bien en dessous de la moitié, sinon deux graduations voisines
# peuvent se ranger sur le même niveau.
assert core.SNAP_DEFOCUS_TOLERANCE_MM < 2.5, (
    "la tolérance peut confondre deux graduations de rampe (5 mm d'écart)")
assert abs(core._snap_defocus_level(15.34) - 15.0) < 1e-9, "15,34 doit donner 15"
assert abs(core._snap_defocus_level(40.0) - 40.0) < 1e-9, "40 doit rester 40"
print("1. rangement à {:.1f} mm : absorbe le bruit (15,34 -> 15), respecte un "
      "niveau choisi (40 -> 40) OK".format(core.SNAP_DEFOCUS_TOLERANCE_MM))

# --- 2. Un niveau à une seule puissance n'ANCRE pas le modèle -----------
# Il aplatirait toute la plage qu'il borne : _bilinear_burn rend la même
# largeur pour toutes les puissances d'un niveau qui n'en mesure qu'une.
niveaux = {}
for pt in core.load_burn_widths(MAT).get("defocus") or []:
    z = round(float(pt.get("z_offset", 0) or 0), 3)
    if z > 0 and pt.get("width"):
        niveaux.setdefault(z, []).append(pt)
maigres = [z for z, pts in niveaux.items()
           if len({float(p["power"]) for p in pts}) < 2]
riches = [z for z in niveaux if z not in maigres]
assert maigres and riches, (
    "il faut des niveaux maigres ET riches pour que ce contrôle prouve "
    "quelque chose", sorted(niveaux))
retenus = core._niveaux_exploitables(niveaux)
assert sorted(retenus) == sorted(riches), (
    "les niveaux à une seule puissance ancrent encore le modèle",
    sorted(retenus), sorted(riches))
print("2. niveaux {} retenus, {} écartés (une seule puissance mesurée) OK"
      .format(sorted(riches), sorted(maigres)))

# La conséquence mesurable : la largeur ne s'effondre plus entre 15 et 36.
w30 = core.burn_width_defocus_scaled(1000, 200, 30.0, MAT)
w15 = core.burn_width_defocus_scaled(1000, 200, 15.0, MAT)
w36 = core.burn_width_defocus_scaled(1000, 200, 36.0, MAT)
assert w15 < w30 < w36, (
    "la largeur à 30 mm sort de l'encadrement 15-36 : un niveau maigre "
    "l'aplatit encore", w15, w30, w36)
print("   S1000/F200 : {:.2f} à 15 mm, {:.2f} à 30, {:.2f} à 36 — croissant OK"
      .format(w15, w30, w36))

# Repli : sans aucun niveau riche, on garde tout plutôt que rien.
seuls_maigres = {z: niveaux[z] for z in maigres}
assert core._niveaux_exploitables(seuls_maigres) == seuls_maigres, (
    "sans niveau riche, le repli doit garder les mesures disponibles")
print("   sans aucun niveau riche : repli sur tout ce qui existe OK")

# --- 3. Les grilles de ② suivent les niveaux MESURÉS --------------------
from PySide6 import QtWidgets

p = tp.TaskPanelTestGrid()
p.edt_measure_mat.setCurrentText(MAT)
p.spn_cell_defocus.setValue(0.0)
p._mesures.reload()
mesures = core.niveaux_defocus_mesures(MAT)
assert mesures, "le hêtre n'a plus de niveau mesuré"
affiches = sorted(p._mesures.grilles_defocus)
for z in mesures:
    assert z in affiches, ("niveau mesuré sans grille de saisie", z, affiches)
print("3. ② affiche une grille pour chacun des {} niveaux mesurés : {} OK"
      .format(len(mesures), affiches))

# --- 4. …et pour le niveau qu'on s'apprête à GRAVER ---------------------
p.spn_cell_defocus.setValue(25.0)
assert 25.0 in p._mesures.grilles_defocus, (
    "graver à 25 mm n'ouvre aucune grille : la mesure n'aurait nulle part "
    "où aller", sorted(p._mesures.grilles_defocus))
# Un niveau à portée de tolérance ne doit PAS créer de grille jumelle.
p.spn_cell_defocus.setValue(15.5)
assert 15.5 not in p._mesures.grilles_defocus, (
    "une grille jumelle est apparue à 0,5 mm d'un niveau existant",
    sorted(p._mesures.grilles_defocus))
assert 15.0 in p._mesures.grilles_defocus
p.spn_cell_defocus.setValue(0.0)
print("4. graver à 25 mm ouvre sa grille ; à 15,5 mm on réutilise celle de "
      "15 OK")

# --- 5. LE contrôle qui compte : enregistrer ne détruit RIEN ------------
avant = core.load_config().get("burn_widths", {}).get(MAT, {})
cles_avant = {(float(pt.get("power", 0)), float(pt.get("feed", 0)),
               float(pt.get("z_offset", 0) or 0))
              for pt in (avant.get("defocus") or [])}
n_foyer_avant = len(avant.get("focus") or [])
assert len(cles_avant) > 20, "trop peu de mesures pour que le test morde"

p._mesures.reload()
for b in p.form.findChildren(QtWidgets.QPushButton):
    if b.text() == "Enregistrer les mesures":
        b.click()
        break
else:
    raise AssertionError("bouton « Enregistrer les mesures » introuvable")

apres = core.load_config().get("burn_widths", {}).get(MAT, {})
cles_apres = {(float(pt.get("power", 0)), float(pt.get("feed", 0)),
               float(pt.get("z_offset", 0) or 0))
              for pt in (apres.get("defocus") or [])}
perdues = cles_avant - cles_apres
assert not perdues, (
    "des mesures en défocus ont DISPARU à l'enregistrement",
    len(perdues), sorted(perdues)[:5])
assert len(apres.get("focus") or []) >= n_foyer_avant, (
    "des mesures au foyer ont disparu", n_foyer_avant,
    len(apres.get("focus") or []))
print("5. enregistrement : {} mesures en défocus avant, {} après, AUCUNE "
      "perdue OK".format(len(cles_avant), len(cles_apres)))

# Et la preuve que le contrôle mord : combien de ces mesures les grilles
# sont-elles seulement capables d'afficher ?
cases_f, cases_d = p._mesures._cellules_possedees()
hors = [c for c in cles_avant if c not in cases_d]
assert hors, ("toutes les mesures tiennent dans les grilles : ce contrôle "
              "ne prouve plus rien")
print("   ({} des {} mesures ne tiennent dans AUCUNE grille — c'est très "
      "exactement ce que l'ancienne version effaçait)".format(
          len(hors), len(cles_avant)))

# --- 6. Une saisie dans une grille est bien enregistrée ----------------
# La fusion ne doit pas se contenter de tout conserver : ce qu'on tape doit
# arriver. On écrit dans une case VIDE d'un niveau affiché.
niveau = sorted(p._mesures.grilles_defocus)[0]
grille = p._mesures.grilles_defocus[niveau]
cible = None
for (s, f), cellule in grille.cells().items():
    if (float(s), float(f), float(niveau)) not in cles_apres:
        cible = (s, f, cellule)
        break
if cible is None:
    print("6. (toutes les cases de la première grille sont déjà mesurées)")
else:
    s, f, cellule = cible
    cellule.setValue(1.23)
    for b in p.form.findChildren(QtWidgets.QPushButton):
        if b.text() == "Enregistrer les mesures":
            b.click()
            break
    final = core.load_config().get("burn_widths", {}).get(MAT, {})
    trouve = [pt for pt in (final.get("defocus") or [])
              if abs(float(pt.get("power", 0)) - float(s)) < 1e-9
              and abs(float(pt.get("feed", 0)) - float(f)) < 1e-9
              and abs(float(pt.get("z_offset", 0) or 0) - float(niveau)) < 1e-9]
    assert trouve and abs(float(trouve[0]["width"]) - 1.23) < 1e-9, (
        "la valeur saisie n'a pas été enregistrée", s, f, niveau, trouve)
    cles_final = {(float(pt.get("power", 0)), float(pt.get("feed", 0)),
                   float(pt.get("z_offset", 0) or 0))
                  for pt in (final.get("defocus") or [])}
    assert not (cles_apres - cles_final), "la saisie a fait perdre des mesures"
    print("6. saisie S{:.0f}/F{:.0f} déf {:g} = 1,23 mm enregistrée, sans "
          "rien perdre OK".format(float(s), float(f), niveau))

print("\nTOUS LES TESTS niveaux_defocus PASSENT")
