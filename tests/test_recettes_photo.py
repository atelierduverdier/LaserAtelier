# -*- coding: utf-8 -*-
"""Les recettes photo doivent poser le panneau DANS UN RÉGIME VALIDE.

Une recette n'est pas un raccourci d'ergonomie, c'est une affirmation :
« avec ces réglages, ce matériau rend ces gris ». Les quatre recettes livrées
jusqu'ici visaient toutes le MDF, aucune ne couvrait les deux tramages sans
calibration, et surtout la recette calibrée MDF demandait un point de 0,80 mm
-- donc un défocus de 8,75 -- alors que son propre nuancier est mesuré à
12,20. Soit (1,00/0,80)² = 1,56x de densité de puissance en trop, exactement
la faute que v1.90.0 avait diagnostiquée ailleurs. Le `gamma 1.5` de ces
recettes compensait ce mauvais régime au lieu de le corriger.

Ce test refuse toute recette calibrée hors du régime de ses propres tons.
"""
from harness import preparer, texte

h = preparer()
core, tp = h.core, h.tp
RECETTES = core.all_presets("photo")
assert RECETTES, "aucune recette photo"

# --- 1. `mode` porte une CLÉ de tramage, jamais un rang ------------------
cles = {t["cle"] for t in tp._TRAMAGES}
for nom, r in RECETTES.items():
    assert isinstance(r["mode"], str), (nom, "mode encore stocké en rang", r["mode"])
    assert r["mode"] in cles, (nom, r["mode"], sorted(cles))
print("1. les {} recettes désignent leur tramage par sa clé OK".format(
    len(RECETTES)))

# --- 2. Une recette CALIBRÉE grave au défocus de ses propres tons --------
# `spot_width` pilote le défocus. L'erreur va comme le CARRÉ du rapport des
# diamètres, donc un écart discret sur ce champ suffit à tout noircir.
ha = core.calibrated_half_angle()
n_cal = 0
for nom, r in RECETTES.items():
    if r["mode"] != "lignes":
        continue
    mat = r.get("material")
    assert mat, (nom, "une recette calibrée sans matériau ne veut rien dire")
    tons = [s for s in core.load_shades(mat)
            if float(s.get("z_offset", 0) or 0) > 0
            and float(s.get("width", 0) or 0) > 0
            and s.get("darkness") is not None]
    assert tons, (nom, mat, "aucun ton n'alimente la courbe")
    z_mes = sorted({round(float(s["z_offset"]), 2) for s in tons})
    assert len(z_mes) == 1, (nom, "tons mesurés à plusieurs défocus", z_mes)
    z_recette = core.defocus_for_spot_diameter(
        r["spot_width"], core.SPOT_FOCUS_MM, ha) or 0.0
    assert abs(z_recette - z_mes[0]) < 0.3, (
        nom, "hors régime : la recette grave à défocus {:.2f} alors que les "
        "tons sont mesurés à {:.2f}".format(z_recette, z_mes[0]))
    # La vitesse doit être dans la plage réellement mesurée.
    plage = core.shade_feed_range(mat, z_mes[0])
    assert plage and plage[0] - 1e-6 <= r["line_feed"] <= plage[1] + 1e-6, (
        nom, "vitesse hors des tons mesurés", r["line_feed"], plage)
    # Le pas ne doit pas dépasser la largeur brûlée du ton le plus FONCÉ :
    # ce sont les noirs qui doivent être pleins. Un ton clair brûle forcément
    # plus fin (à faible puissance, seul le coeur du faisceau franchit le
    # seuil), et le bois nu qu'il laisse est précisément ce qui le rend clair
    # -- exiger la couverture sur le ton le plus clair ferait resserrer le pas
    # pour rien. C'est bien la version foncée du reproche fait au premier
    # portrait calibré : 27 % de la planche non gravée.
    plus_fonce = max(tons, key=lambda s: float(s["darkness"]))
    larg = float(plus_fonce["width"])
    assert r["pitch"] <= larg + 1e-6, (
        nom, "les noirs laisseront du bois nu", r["pitch"], larg)
    print("   {:<46} défocus {:.2f} = mesuré {:.2f}, F{:.0f} dans {}, pas "
          "{:.2f} <= trait du noir {:.2f} OK".format(
              nom[:46], z_recette, z_mes[0], r["line_feed"], plage,
              r["pitch"], larg))
    n_cal += 1
assert n_cal >= 2, ("il faut une recette calibrée par matériau mesuré", n_cal)
print("2. les {} recettes calibrées sont dans le régime de leurs tons OK"
      .format(n_cal))

# --- 3. Les tramages à GRAIN ont la place qu'ils demandent --------------
for nom, r in RECETTES.items():
    t = [x for x in tp._TRAMAGES if x["cle"] == r["mode"]][0]
    if t["grain"]:
        assert r["width"] >= 100.0, (
            nom, "un tramage à grain sous 100 mm de large : le grain se verra "
            "plus que le sujet", r["width"])
print("3. toute recette à grain fait au moins 100 mm de large OK")

# --- 4. Lignes gravées : au pas OPTIMAL, et à une vitesse qui enfle ------
enfle = [(n, r) for n, r in RECETTES.items() if r["mode"] == "enfle"]
assert enfle, "aucune recette pour le tramage retenu à l'atelier"
for nom, r in enfle:
    mat = r["material"]
    rapide = core.swell_max_feed(mat)
    assert r["line_feed"] <= rapide + 1e-6, (
        nom, "au-delà de F{:.0f} le trait n'enfle plus à fond".format(rapide))
    plage = core.burn_width_range(mat, r["line_feed"])
    # Le contraste passe par un maximum au pas = trait le plus épais.
    assert abs(r["pitch"] - plage[1]) < 1e-6, (
        nom, "pas non optimal", r["pitch"], plage[1])
    print("   {:<46} F{:.0f} <= F{:.0f}, pas {:.2f} = trait maxi OK".format(
        nom[:46], r["line_feed"], rapide, r["pitch"]))
print("4. la recette « lignes gravées » est au contraste maximal OK")

# --- 5. Similigravure : les lignes doivent se TOUCHER -------------------
for nom, r in RECETTES.items():
    if r["mode"] != "simili":
        continue
    trait = core.burn_width_at(r["power"], r["line_feed"], r["material"])
    assert trait and r["pitch"] <= trait + 1e-6, (
        nom, "pas plus large que le trait brûlé : la trame sortira peignée "
        "et toute l'image s'éclaircira", r["pitch"], trait)
    k = core.am_screen_k(r["dot_spacing"], r["pitch"])
    assert 2 * k * k >= 8, (nom, "trop peu de niveaux de gris", 2 * k * k)
    print("   {:<46} pas {:.2f} <= trait {:.2f}, {} niveaux de gris OK".format(
        nom[:46], r["pitch"], trait, 2 * k * k))
print("5. la similigravure grave des lignes jointives OK")

# --- 6. Appliquée pour de vrai, la recette pose bien le panneau ---------
# Le test décisif : une recette qui ne s'applique pas est un texte mort. Une
# valeur TEXTUELLE dans une combo n'était pas restaurée avant (int(v) levait,
# l'exception était avalée, le défaut restait) -- donc « material »: "Hêtre"
# n'aurait rien fait du tout.
p = tp.TaskPanelHalftone()
nom_h = "Portrait Hêtre -- lignes gravées (le plus sûr)"
assert nom_h in RECETTES, sorted(RECETTES)
tp._restore_last_values_depuis = None       # (aucun état résiduel à craindre)
for cle, w in p._last_fields.items():
    if cle in RECETTES[nom_h]:
        tp._widget_set(w, RECETTES[nom_h][cle])
assert p.combo_photo_mat.currentData() == u"Hêtre", (
    "le matériau de la recette n'a pas été appliqué",
    p.combo_photo_mat.currentData())
assert p._tramage()["cle"] == "enfle", p._tramage()["cle"]
assert abs(p.spn_pitch.value() - 0.30) < 1e-9
assert abs(p.spn_line_feed.value() - 800.0) < 1e-9
# Et le verdict du panneau doit alors être VERT : c'est le régime optimal.
p._maj_regime()
assert "#2e7d32" in p.lbl_regime.text(), (
    "la recette « la plus sûre » ne passe pas son propre verdict",
    texte(p.lbl_regime))
assert "67 points" in texte(p.lbl_regime), texte(p.lbl_regime)
print("6. recette appliquée : matériau Hêtre, tramage enfle, pas 0.30, F800, "
      "verdict VERT à 67 points OK")

# --- 7. Aller-retour de persistance sur une combo à données -------------
# `_widget_get` doit rendre le NOM, pas le rang, sinon la sauvegarde annule
# le bénéfice de la lecture.
assert tp._widget_get(p.combo_photo_mat) == u"Hêtre", tp._widget_get(p.combo_photo_mat)
assert tp._widget_get(p.combo_mode) == "enfle", tp._widget_get(p.combo_mode)
# Un rang (ancienne config) doit rester compris.
tp._widget_set(p.combo_mode, 0)
assert p._tramage()["cle"] == "diffusion", "un rang hérité n'est plus compris"
# Une valeur qui ne correspond à rien ne doit RIEN changer.
tp._widget_set(p.combo_mode, "tramage_inexistant")
assert p._tramage()["cle"] == "diffusion", "une clé inconnue a bougé la liste"
print("7. persistance par NOM, rangs hérités toujours compris, clé inconnue "
      "sans effet OK")

print("\nTOUS LES TESTS recettes_photo PASSENT")
