# -*- coding: utf-8 -*-
"""Un aplat PLEIN peut être complètement surcuit, et rien ne le disait.

Le 30/07/2026, un carré S1000/F800 au foyer au pas 0,26 est sorti
CARBONISÉ sur Hêtre. Le panneau, lui, affichait son verdict vert :
« Remplissage plein (trait 0,30 mm pour un pas de 0,26 mm) » — parfaitement
exact, et complètement à côté. Le recouvrement et la surcuisson sont deux
échecs OPPOSÉS ; vérifier l'un ne dit rien de l'autre.

D'où la ligne « Énergie ». Ce qu'elle annonce est un COÛT, pas un dommage :
l'atelier ne sait pas prédire la carbonisation (sur MDF, des tons jugés
97 % tiennent à 4x le réglage le plus économe). Elle compare deux
remplissages calculés de la MÊME façon et laisse trancher.

Le piège de méthode que ce test protège en priorité : la largeur stockée
sur un ton est tantôt une largeur brûlée au pied à coulisse, tantôt le PAS
d'une bande gravée en balayage. Diviser par l'une puis par l'autre compare
deux grandeurs différentes. Sur Hêtre l'écart entre les deux lectures est
d'un facteur 8 — de quoi désigner le mauvais réglage de référence sans que
rien ne cloche à l'écran.
"""
from harness import preparer, texte

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"

# --- 1. L'indice d'énergie est bien S/(pas x vitesse) --------------------
assert abs(core.energie_surfacique(1000, 800, 0.26) - 4.8077) < 1e-3
assert core.energie_surfacique(1000, 800, 0) is None, "pas nul non gardé"
assert core.energie_surfacique(1000, 0, 0.26) is None, "vitesse nulle non gardée"
print("1. energie_surfacique = S/(pas x F), et None sur un terme nul OK")

# --- 2. La référence est le MOINS cher, pas le premier trouvé ------------
ref = core.remplissage_noir_le_plus_econome(MAT)
assert ref, "aucun réglage noir mesuré sur {}".format(MAT)
candidats = []
for ton in core.load_shades(MAT):
    d, s, f = ton.get("darkness"), ton.get("power"), ton.get("feed")
    if d is None or float(d) < 95 or not s or not f:
        continue
    pas = core.espacement_pour_reglage(float(s), float(f), MAT,
                                       borne_haute=ton.get("width") or None)
    if pas:
        candidats.append((core.energie_surfacique(float(s), float(f), pas),
                          float(s), float(f)))
assert candidats, "le nuancier n'a plus de ton noir exploitable"
moins_cher = min(c[0] for c in candidats)
assert abs(ref["energie"] - moins_cher) < 1e-9, (
    "la référence n'est pas la moins chère", ref["energie"], sorted(candidats))
assert ref["darkness"] >= 95.0, ("référence pas jugée noire", ref)
print("2. référence = le moins cher des {} tons noirs mesurés : S{:.0f} F{:.0f} "
      "pas {:.2f} -> {:.3f} OK".format(
          len(candidats), ref["power"], ref["feed"], ref["spacing"],
          ref["energie"]))

# --- 3. Les DEUX côtés se calculent pareil, et ça CHANGE la réponse -----
# Le pas de la référence doit venir du même calcul que celui qu'on
# applique en cliquant ce ton, jamais de sa largeur stockée. Ce n'est pas
# une élégance : sur les données de l'atelier, la lecture par largeur
# désigne un AUTRE réglage.
ton_ref = [t for t in core.load_shades(MAT)
           if float(t.get("power", 0) or 0) == ref["power"]
           and float(t.get("feed", 0) or 0) == ref["feed"]]
borne = (ton_ref[0].get("width") or None) if ton_ref else None
attendu = core.espacement_pour_reglage(ref["power"], ref["feed"], MAT,
                                       borne_haute=borne)
assert abs(ref["spacing"] - attendu) < 1e-9, (
    "le pas de la référence ne vient pas de espacement_pour_reglage",
    ref["spacing"], attendu)

# La lecture NAÏVE : diviser par la largeur stockée du ton.
naif = None
for ton in core.load_shades(MAT):
    d, s, f = ton.get("darkness"), ton.get("power"), ton.get("feed")
    w = ton.get("width") or 0
    if d is None or float(d) < 95 or not s or not f or not w:
        continue
    e = core.energie_surfacique(float(s), float(f), float(w))
    if naif is None or e < naif[0]:
        naif = (e, float(s), float(f), float(w))
if naif:
    coherent = core.espacement_pour_reglage(
        naif[1], naif[2], MAT, borne_haute=naif[3])
    assert coherent, "pas calculable pour le candidat naïf"
    e_coherent = core.energie_surfacique(naif[1], naif[2], coherent)
    assert e_coherent > naif[0], (
        "la lecture naïve ne sous-estime plus rien : ce contrôle ne prouve "
        "plus rien", naif, e_coherent)
    assert (naif[1], naif[2]) != (ref["power"], ref["feed"]), (
        "la lecture par largeur stockée désigne le MÊME réglage : le "
        "contrôle ne discrimine plus sur ces données", naif)
    print("   la largeur stockée {:.2f} de S{:.0f}/F{:.0f} annonce {:.3f} "
          "alors que son vrai pas {:.2f} coûte {:.3f} (x{:.1f}) -- elle "
          "aurait volé la place de référence".format(
              naif[3], naif[1], naif[2], naif[0], coherent, e_coherent,
              e_coherent / naif[0]))
print("3. le pas des deux côtés vient de espacement_pour_reglage OK")

# --- 4. Le panneau : PLEIN et pourtant surcuit --------------------------
from PySide6 import QtWidgets

# Sélection VIDE : les faux objets n'ont pas de BoundBox, et rien ici ne
# dépend de la géométrie -- seulement des réglages de brûlage.
p = tp.TaskPanelFilledEngraving([])
combo_mat = p._shade_picker["mat"]
idx = [i for i in range(combo_mat.count()) if combo_mat.itemData(i) == MAT]
assert idx, "le matériau {} n'est pas proposé".format(MAT)
combo_mat.setCurrentIndex(idx[0])
p.combo_fill_style.setCurrentIndex(0)          # style plein
p.spn_fill_power.setValue(1000)
p.spn_fill_feed.setValue(800)
p.spn_spacing.setValue(0.26)
p._update_defocus_preview()

recouvrement = texte(p.lbl_recouvrement.text())
energie = texte(p.lbl_energie.text())
assert "plein" in recouvrement.lower(), (
    "le carré carbonisé doit rester jugé PLEIN -- c'est tout le problème",
    recouvrement)
assert "EXCESSIVE" in energie, ("aucun avertissement d'énergie sur le "
                                "réglage qui a carbonisé", energie)
# isHidden() et non isVisibleTo(form) : la section « Remplissage » peut
# être REPLIÉE (son état est persisté dans la config), auquel cas tout
# ce qu'elle contient est invisible et l'assertion testerait le
# repliement au lieu de la logique du verdict.
assert not p.btn_alleger.isHidden(), "bouton « Alléger » caché"
assert p.btn_corriger_recouvrement.isHidden(), (
    "le bouton de recouvrement ne doit PAS s'afficher : le remplissage est "
    "plein")
print("4. S1000/F800 pas 0,26 : recouvrement « {} » ET énergie « {} » OK".format(
    recouvrement, energie))

# --- 5. « Alléger » applique les TROIS champs ---------------------------
# Le pas fait partie du réglage : c'est lui qui fixe le défocus, donc la
# largeur du trait, donc l'énergie. L'oublier ne changerait presque rien.
p.btn_alleger.click()
assert abs(p.spn_fill_power.value() - ref["power"]) < 1e-6, p.spn_fill_power.value()
assert abs(p.spn_fill_feed.value() - ref["feed"]) < 1e-6, p.spn_fill_feed.value()
assert abs(p.spn_spacing.value() - round(ref["spacing"], 2)) < 0.011, (
    "le pas n'a pas été appliqué", p.spn_spacing.value(), ref["spacing"])
apres = texte(p.lbl_energie.text())
assert "EXCESSIVE" not in apres, (
    "après avoir allégé, l'avertissement persiste", apres)
print("5. « Alléger » applique S + F + pas, et le verdict repasse au vert : "
      "« {} » OK".format(apres))

# --- 6. Styles décoratifs : les deux lignes se taisent ------------------
# Tirets, pointillé, vague : les vides sont voulus, il n'y a pas d'aplat
# dont parler.
if p.combo_fill_style.count() > 1:
    p.combo_fill_style.setCurrentIndex(1)
    p._update_defocus_preview()
    assert p.lbl_energie.isHidden(), (
        "la ligne énergie parle sur un style décoratif",
        p.lbl_energie.text())
    p.combo_fill_style.setCurrentIndex(0)
    p._update_defocus_preview()
print("6. style décoratif : la ligne énergie se tait OK")

# --- 7. Sans matériau mesuré, se taire plutôt qu'inventer ---------------
vide = [i for i in range(combo_mat.count()) if not combo_mat.itemData(i)]
if vide:
    combo_mat.setCurrentIndex(vide[0])
    p._update_defocus_preview()
    assert p.lbl_energie.isHidden(), (
        "un chiffre d'énergie affiché sans référence mesurée",
        p.lbl_energie.text())
    print("7. aucun matériau choisi : la ligne énergie se tait OK")
else:
    print("7. (pas d'entrée « sans matériau » dans ce nuancier)")
assert p._reference_noire(None) is None, "matériau vide non géré"
assert p._reference_noire(u"Materiau Inexistant") is None
print("   sans matériau / matériau inconnu : aucune référence, pas "
      "d'exception OK")

# --- 8. Un matériau sans ton noir ne fait pas tomber le panneau ---------
assert core.remplissage_noir_le_plus_econome(u"Materiau Inexistant") is None
print("8. matériau inconnu -> None, pas d'exception OK")

print("\nTOUS LES TESTS energie_remplissage PASSENT")
