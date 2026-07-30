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
from harness import preparer, texte

h = preparer()
core, tp = h.core, h.tp
G = tp._MesuresPlanchesControleur

CIBLES = {
    "largeurs_foyer": (G.POWERS, G.FEEDS_FOCUS),
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
    ancien = {"largeurs_foyer": (400.0, 6000.0, 5),
              "largeurs_defocus": (200.0, 2000.0, 5)}[cle]
    perdues = [f for f in paliers_lineaires(*ancien)
               if f not in [float(x) for x in colonnes]]
    assert perdues, ("l'ancienne plage n'orphelinait rien : ce contrôle ne "
                     "prouve plus rien", cle)
    print("      (l'ancienne plage gravait {} sans destination)".format(
        [round(f) for f in perdues]))
print("2. les deux objectifs « largeurs » tombent pile sur la grille ② OK")

# --- 3. F6000 ne marque plus : il ne doit plus être gravé --------------
idx = [i for i in range(p.combo_recipe.count())
       if p.combo_recipe.itemData(i) == "largeurs_foyer"][0]
p.combo_recipe.setCurrentIndex(idx)
_m, _f, cellules, _dz = p._build_cells()
assert not [c for c in cellules if float(c["feed"]) > 3000.0], (
    "l'objectif au foyer grave encore au-delà de F3000, qui ne marque plus "
    "depuis le changement de lentille")
print("3. plus aucune case au-delà de F3000 (lentille changée le 27/07/2026) OK")

# --- 4. Au foyer, les traits doivent rester ISOLÉS ---------------------
# Sinon on ne mesure pas la largeur d'un trait mais celle d'un aplat --
# exactement ce que la note de l'objectif demande de faire.
pas = recettes["largeurs_foyer"]["hatch_spacing"]
plus_large = 0.0
for mat in core.burn_width_materials():
    for pt in core.load_burn_widths(mat).get("focus") or []:
        plus_large = max(plus_large, float(pt.get("width", 0) or 0))
assert plus_large > 0, "aucune largeur au foyer mesurée : contrôle impossible"
assert pas > plus_large * 1.5, (
    "l'espacement de l'objectif au foyer ({} mm) n'est pas assez grand "
    "devant la brûlure la plus large jamais mesurée ({} mm) : les cases "
    "sortiront en aplat".format(pas, plus_large))
print("4. espacement au foyer {:.2f} mm contre {:.2f} mm de brûlure la plus "
      "large mesurée : traits isolés OK".format(pas, plus_large))

# --- 5. Les champs de plage sont verrouillés, et libérés ensuite -------
# Une plage affichée que le job n'utilise pas serait une interface qui ment.
assert all(not c.isEnabled() for c in p._champs_plages), (
    "les champs de plage restent modifiables alors que l'objectif fixe les "
    "paliers")
assert not p.lbl_paliers.isHidden(), "les paliers gravés ne sont pas affichés"
affiche = texte(p.lbl_paliers.text())
for f in G.FEEDS_FOCUS:
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

print("\nTOUS LES TESTS objectifs_grille PASSENT")
