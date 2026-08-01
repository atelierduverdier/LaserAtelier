# -*- coding: utf-8 -*-
"""Tramage « Lignes gravées » : le trait enfle avec l'image.

Ce que ce tramage promet : le gris est une LARGEUR, lue sur les largeurs
brûlées MESURÉES, sans nuancier. La ligne n'est jamais coupée.

Faits relevés sur hêtre le 29/07/2026, et que ces tests figent : au foyer
la largeur va de 0,10 à 0,30 mm (3,0x), identique à F200, F400 ET F800 ;
à partir de F1500 elle est PLATE à 0,10 et le tramage n'a plus d'objet.
Les gros traits du défocus (jusqu'à 2,60 mm) ne servent à rien ici : leur
rapport n'est que de 1,4x, donc un contraste plus faible.
"""
import re

from harness import (preparer, texte, hauteurs_z, puissances,
                     image_demo, figer_largeurs)

h = preparer()
core, tp = h.core, h.tp
MAT = u"Hêtre"
# Table du foyer FIGÉE : ce test suppose une forme précise
# (enfle sous F800, plat au-dessus). Sans ça il rougit dès que
# l'atelier mesure -- arrivé le 01/08/2026.
figer_largeurs(core, MAT)

# --- 1. La table de largeurs est croissante et bornée aux mesures -------
t = core.burn_width_power_table(MAT, 400.0)
assert t, "aucune table de largeurs"
ws = [w for _s, w in t]
assert ws == sorted(ws), "la largeur redescend quand la puissance monte"
assert (abs(ws[0] - 0.10) < 1e-9 and abs(ws[-1] - 0.30) < 1e-9), (ws[0], ws[-1])
print("1. table F400 : {} points, largeur {:.2f} -> {:.2f} mm, croissante OK"
      .format(len(t), ws[0], ws[-1]))

# --- 2. Ne JAMAIS descendre sous la plus faible puissance mesurée -------
# burn_width_at borne aux mesures : sous la plage il rend la largeur du
# bord, si bien que S0 semble donner un trait de 0,10 mm alors qu'il ne
# grave rien. Un tramage qui promet une ligne continue ne doit pas choisir
# une puissance dont on ne sait rien.
mesures = core.load_burn_widths(MAT)["focus"]
s_mini_mesure = min(float(e["power"]) for e in mesures)
niveaux = core.swell_power_levels(MAT, 800.0, 0.10)
assert niveaux is not None
puiss, w_min, w_max = niveaux
assert min(puiss) > 0, "un niveau à S0 : la ligne ne graverait rien"
assert min(puiss) >= s_mini_mesure - 1e-9, (min(puiss), s_mini_mesure)
assert puiss == sorted(puiss), "les S ne sont pas croissants"
# Les deux extrêmes doivent redonner les largeurs voulues À LA MESURE.
assert abs(core.burn_width_at(puiss[0], 800.0, MAT) - w_min) < 1e-9
assert abs(core.burn_width_at(puiss[-1], 800.0, MAT) - w_max) < 1e-9
print("2. {} niveaux de S{} à S{} (jamais S0, jamais sous la mesure), et les "
      "extrêmes redonnent {:.2f} et {:.2f} mm OK".format(
          len(puiss), puiss[0], puiss[-1], w_min, w_max))

# --- 3. La vitesse : rien ne change dessous, tout s'arrête au-dessus ----
for f in (200.0, 400.0, 800.0):
    assert core.burn_width_range(MAT, f) == (0.10, 0.30), (f,)
for f in (1500.0, 3000.0):
    p_ = core.burn_width_range(MAT, f)
    assert p_ and abs(p_[1] - p_[0]) < 1e-9, (f, p_)
assert core.swell_max_feed(MAT) == 800.0, core.swell_max_feed(MAT)
print("3. F200/F400/F800 identiques (0.10-0.30), F1500+ plat ; la plus rapide "
      "utile est bien F800 OK")

# --- 4. Le défocus a un moins bon RAPPORT que le foyer ------------------
# C'est ce rapport, pas la largeur absolue, qui fait le contraste.
d = core.load_burn_widths(MAT).get("defocus") or []


def rapport(z, f):
    pts = sorted((float(e["power"]), float(e["width"])) for e in d
                 if abs(float(e.get("z_offset", 0) or 0) - z) < 1e-6
                 and abs(float(e["feed"]) - f) < 1e-6)
    return pts[-1][1] / pts[0][1] if len(pts) >= 3 else None


r_foyer = 0.30 / 0.10
for z, f in ((15.0, 400.0), (15.0, 200.0), (36.0, 200.0)):
    r = rapport(z, f)
    assert r is not None and r < r_foyer, (z, f, r)
print("4. rapport au foyer {:.1f}x contre {:.1f}x à défocus 15 et {:.1f}x à "
      "défocus 36 : le foyer gagne OK".format(
          r_foyer, rapport(15.0, 400.0), rapport(36.0, 200.0)))

# --- 5. Plancher réglable, borné aux mesures ----------------------------
n2 = core.swell_power_levels(MAT, 800.0, 0.20)
assert (n2[1], n2[2]) == (0.20, 0.30), n2[1:]
assert n2[0][0] > puiss[0], "le plancher n'a pas relevé la puissance"
assert core.swell_power_levels(MAT, 800.0, 5.0)[1] == 0.30     # trop haut
assert core.swell_power_levels(MAT, 800.0, 0.001)[1] == 0.10   # trop bas
print("5. plancher à 0.20 mm pris en compte ; valeurs hors plage ramenées aux "
      "mesures OK")

# --- 6. Refus net, jamais de G-code mensonger ---------------------------
assert core.swell_power_levels(MAT, 2000.0, 0.10) is None
assert core.swell_power_levels(u"MatiereInconnue", 800.0, 0.10) is None
img = [[min(1.0, (x + y) / 60.0) for x in range(40)] for y in range(30)]
assert core.generate_gcode_photo_swell_lines(
    img, 0.3, core.Z_WORK_MM, 2000.0, MAT, quiet=True) is None
msg = core.swell_refus_message(MAT, 2000.0)
assert "F800" in msg, ("le refus doit nommer la vitesse qui marche", msg)
print("6. F2000 et matériau inconnu refusés, et le refus nomme F800 OK")

# --- 7. Le G-code : au foyer, faisceau jamais coupé --------------------
g = core.generate_gcode_photo_swell_lines(img, 0.30, core.Z_WORK_MM, 800.0,
                                          MAT, line_min_mm=0.10, quiet=True)
assert g, "aucun G-code"
s_grave = puissances(g, gravure_seule=True)
assert 0 not in s_grave, "un G1 à S0 : la ligne est coupée quelque part"
assert len(s_grave) > 5, ("le trait n'a presque pas de niveaux",
                          sorted(s_grave))
assert core.Z_WORK_MM in hauteurs_z(g), ("doit graver AU FOYER",
                                         sorted(hauteurs_z(g)))
assert "(Trait : 0.10 a 0.30 mm -- couverture 33 a 100 %)" in g, \
    [l for l in g.split("\n") if "Trait" in l]
print("7. G-code : {} niveaux de S sur les G1, aucun à S0, gravé à Z={:.2f} OK"
      .format(len(s_grave), core.Z_WORK_MM))

# --- 8. Pas trop fin : signalé ----------------------------------------
serre = core.generate_gcode_photo_swell_lines(img, 0.15, core.Z_WORK_MM,
                                              800.0, MAT, quiet=True)
assert "ATTENTION" in serre and "recouvrent" in serre
assert "ATTENTION" not in g, "faux positif au pas 0.30"
print("8. pas 0.15 < trait maxi : le G-code prévient ; au pas 0.30 il se tait "
      "OK")

# --- 9. L'aperçu et le G-code sortent de la MÊME table -----------------
p = tp.TaskPanelHalftone()
mats = [p.combo_photo_mat.itemText(i) for i in range(p.combo_photo_mat.count())]
p.combo_photo_mat.setCurrentIndex(mats.index(MAT))
p.edt_image.setText(image_demo())
p.spn_width.setValue(40.0)
p.combo_mode.setCurrentIndex(6)
p.spn_pitch.setValue(0.30)
p.spn_line_feed.setValue(800.0)
p.spn_line_min.setValue(0.10)
p.spn_gamma.setValue(1.0)
rows = p._build_rows(silent=True, max_cells=30000)
gp = p._generate(rows, quiet=True)
assert gp and "lignes gravees" in gp.lower(), (gp or "")[:200]
attendus = set(core.swell_power_levels(MAT, 800.0, 0.10)[0])
# S0 sur un G1 n'est PAS une gravure : c'est la traversée d'une plage
# blanche, faisceau coupé et mouvement continu (le panneau applique son
# seuil de blanc par défaut). On ne contrôle donc que les S qui brûlent.
# Le test 7, lui, appelle le générateur SANS seuil et garde l'invariant
# d'origine « aucun G1 à S0 ».
emis = {s for s in puissances(gp, gravure_seule=True) if s > 0}
inconnus = emis - attendus
assert not inconnus, ("le G-code émet des S absents de la table partagée",
                      sorted(inconnus)[:5])
print("9. les {} valeurs de S gravantes sortent toutes de swell_power_levels, "
      "la table que l'aperçu utilise aussi OK".format(len(emis)))

# --- 10. Aucune diffusion d'erreur dans ce tramage ---------------------
vrai = core.floyd_steinberg_dither
appels = {"n": 0}
core.floyd_steinberg_dither = lambda *a, **k: (
    appels.__setitem__("n", appels["n"] + 1) or vrai(*a, **k))
try:
    im, note = p._render_photo_preview(rows, largeur_px=200)
finally:
    core.floyd_steinberg_dither = vrai
assert im is not None, note
assert appels["n"] == 0, "les lignes gravées passent par une diffusion"
print("10. aperçu rendu sans diffusion d'erreur -- note : « {} » OK"
      .format(note))


# --- 11. Le BLANC doit pouvoir rester du bois nu ------------------------
# Le défaut, relevé sur une planche le 31/07/2026 : le fond blanc pur
# sortait GRIS UNI. Le palier le plus bas de ce tramage n'est pas « rien »
# -- c'est la puissance la plus basse MESURÉE (S200 sur hêtre), donc un
# trait de 0,10 mm : 33 % du bois brûlé au pas 0,30, pour du blanc.
#
# Ce contrôle se démontre lui-même : il rejoue d'abord SANS seuil pour
# prouver que le blanc gravait vraiment, sinon il ne prouverait rien.
blanches = [[0.0] * 8, [0.0] * 8, [1.0] * 8]
sans = core.generate_gcode_photo_swell_lines(
    blanches, pitch=0.30, z_work=core.Z_WORK_MM, feed=800.0,
    material=MAT, line_min_mm=0.10, quiet=True)
assert sans, "génération refusée sans seuil"
niv0 = core.swell_power_levels(MAT, 800.0, 0.10)[0][0]
assert niv0 > 0, "le palier le plus bas devrait être une puissance réelle"
assert niv0 in puissances(sans, gravure_seule=True), (
    "sans seuil, une case blanche devrait graver à S{} -- si ce n'est plus "
    "le cas, ce contrôle ne démontre plus rien".format(niv0))

avec = core.generate_gcode_photo_swell_lines(
    blanches, pitch=0.30, z_work=core.Z_WORK_MM, feed=800.0,
    material=MAT, line_min_mm=0.10, quiet=True, white_threshold=0.08)
assert avec, "génération refusée avec seuil"
# Une rangée entièrement blanche ne doit produire AUCUN G1 gravant à sa
# hauteur : _emit_raster_rows saute les lignes vides. On compte les G1
# porteurs d'une puissance non nulle, ligne par ligne.
def _g1_gravants(g):
    n, s = 0, 0
    for l in g.split("\n"):
        m = re.search(r"\bS(\d+)", l)
        if m and not l.startswith("G1"):
            s = int(m.group(1))
        m67 = re.search(r"M67 E0 Q(\d+)", l)
        if m67:
            s = int(m67.group(1))
        if l.startswith("G1"):
            m = re.search(r"\bS(\d+)", l)
            if m:
                s = int(m.group(1))
            if s > 0:
                n += 1
    return n

assert _g1_gravants(avec) < _g1_gravants(sans), (
    "le seuil de blanc n'a rien coupé", _g1_gravants(sans), _g1_gravants(avec))
# Et la seule rangée qui reste gravée est la NOIRE : 8 cases à S max.
smax = core.swell_power_levels(MAT, 800.0, 0.10)[0][-1]
assert puissances(avec, gravure_seule=True) == {smax}, (
    "avec un seuil à 8 %, seule la rangée noire doit graver",
    sorted(puissances(avec, gravure_seule=True)))
print("11. blanc pur : sans seuil il grave à S{} ({:.0f} % de couverture au "
      "pas 0,30) ; avec seuil 8 % il ne reste que la rangée noire (S{}) OK"
      .format(niv0, 100.0 * 0.10 / 0.30, smax))

# --- 12. Aperçu et G-code d'accord sur le blanc -------------------------
# La règle de la maison : l'aperçu ne refait jamais ses propres calculs.
# Les deux passent par core.swell_niveau, donc un fond blanc peint doit
# correspondre à un fond blanc gravé.
n_niv = len(core.swell_power_levels(MAT, 800.0, 0.10)[0])
assert core.swell_niveau(0.0, n_niv, 0.0) == 0, "sans seuil, 0 -> palier 0"
assert core.swell_niveau(0.0, n_niv, 0.08) is None, "avec seuil, 0 -> bois nu"
assert core.swell_niveau(0.5, n_niv, 0.08) is not None, "un gris moyen reste gravé"
assert core.swell_niveau(1.0, n_niv, 0.08) == n_niv - 1, "le noir reste au max"
print("12. swell_niveau, source unique du générateur ET de l'aperçu : "
      "blanc -> bois nu, gris et noir inchangés OK")


# --- 13. Fond pointillé : une rampe continue, sans marche ---------------
# Le seuil « bois nu » règle le fond blanc mais laisse une MARCHE : rien,
# puis d'un coup w_min/pas de couverture. Le fond pointillé comble
# exactement cet intervalle en espaçant le trait le plus fin. C'est le
# seul moyen de descendre sous le plancher du mode : la largeur, elle,
# s'arrête à la puissance la plus basse mesurée.
puiss13, w_min13, w_max13 = core.swell_power_levels(MAT, 800.0, 0.10)
n13, PAS, SEUIL = len(puiss13), 0.30, 0.08
plancher = w_min13 / PAS


def couverture(d, fond, seuil=SEUIL, cote=24):
    """Part de bois brûlé pour une plage uniforme de noirceur `d`."""
    g = core.swell_niveaux_grille([[d] * cote for _ in range(cote)],
                                  n13, seuil, fond)
    allumes = [k for ligne in g for k in ligne if k is not None]
    if not allumes:
        return 0.0
    largeur = sum(w_min13 + (w_max13 - w_min13) * k / float(n13 - 1)
                  for k in allumes) / len(allumes)
    return (len(allumes) / float(cote * cote)) * largeur / PAS


rampe = [couverture(d / 1000.0, "pointille")
         for d in range(0, int(SEUIL * 1000), 5)]
assert rampe[0] == 0.0, ("le blanc PUR doit rester nu même en pointillé",
                         rampe[0])
assert all(b >= a - 1e-9 for a, b in zip(rampe, rampe[1:])), (
    "la couverture du pointillé n'est pas monotone", rampe)
assert rampe[-1] > 0.9 * plancher, (
    "le pointillé ne rejoint pas le plancher du mode", rampe[-1], plancher)
# Le raccord doit être franc-bord : juste sous le seuil et juste dessus,
# la même couverture. C'est ce que le remappage de la branche continue
# rend possible -- sans lui il restait 5 points d'écart.
dessous = couverture(SEUIL - 0.001, "pointille")
dessus = couverture(SEUIL, "pointille")
assert abs(dessous - dessus) < 0.02, (
    "marche résiduelle au seuil", dessous, dessus)
assert abs(dessus - plancher) < 1e-6, (
    "la branche continue ne repart pas du trait le plus fin",
    dessus, plancher)
# Et le fond « nu » reste franc : rien du tout sous le seuil.
assert couverture(SEUIL - 0.001, "nu") == 0.0, "le fond nu grave sous le seuil"
print("13. fond pointillé : couverture 0 → {:.0f} % continue et monotone, "
      "raccord exact au seuil ({:.1f} % des deux côtés) ; le fond nu reste "
      "à 0 OK".format(100.0 * plancher, 100.0 * dessus))

# --- 14. Sans seuil, RIEN ne change (non-régression) --------------------
# Le remappage [seuil, 1] -> [0, n-1] ne doit toucher personne quand il
# n'y a pas de seuil : c'est l'identité, et les fichiers déjà gravés
# doivent rester reproductibles.
for d in (0.0, 0.25, 0.5, 0.75, 1.0):
    attendu = max(0, min(n13 - 1, int(round(d * (n13 - 1)))))
    assert core.swell_niveau(d, n13, 0.0) == attendu, (d, attendu)
g_sans = core.generate_gcode_photo_swell_lines(
    [[0.0] * 6, [0.5] * 6, [1.0] * 6], pitch=PAS, z_work=core.Z_WORK_MM,
    feed=800.0, material=MAT, line_min_mm=0.10, quiet=True)
assert 0 not in puissances(g_sans, gravure_seule=True), (
    "sans seuil, le faisceau ne doit jamais être coupé")
print("14. sans seuil : paliers identiques à l'ancienne formule et aucun "
      "G1 à S0 -- le comportement d'origine est intact OK")

# --- 15. L'aperçu passe par la MÊME grille que le G-code ---------------
# Le pointillé dépend de la POSITION de la case : un aperçu qui le
# recalculerait de son côté dessinerait des points ailleurs que la
# machine, et personne ne le verrait avant le bois.
vraie_grille = core.swell_niveaux_grille
appels = {"n": 0}
core.swell_niveaux_grille = lambda *a, **k: (
    appels.__setitem__("n", appels["n"] + 1) or vraie_grille(*a, **k))
try:
    p.spn_white.setValue(8.0)
    idx = p.combo_fond.findData("pointille")
    assert idx >= 0, "le sélecteur de fond n'a pas d'entrée « pointille »"
    p.combo_fond.setCurrentIndex(idx)
    rows15 = p._build_rows(silent=True, max_cells=20000)
    im15, note15 = p._render_photo_preview(rows15, largeur_px=160)
finally:
    core.swell_niveaux_grille = vraie_grille
assert im15 is not None, note15
assert appels["n"] > 0, ("l'aperçu recalcule le pointillé au lieu de passer "
                         "par swell_niveaux_grille")
print("15. l'aperçu appelle swell_niveaux_grille ({} fois) : il ne peut pas "
      "dessiner un pointillé différent de celui gravé OK".format(appels["n"]))

# --- 16. Un verdict VERT ne doit pas décrire un défaut ------------------
# Le 31/07/2026, un aperçu au fond gris uni est parti alors que le panneau
# l'annonçait mot pour mot -- sous une coche verte. Personne ne lit un
# avertissement sous un ✓. À seuil nul sur ce tramage, le verdict doit
# donc être ROUGE, puisqu'il décrit un fond blanc qui sortira gris.
p.combo_mode.setCurrentIndex(6)
p.spn_pitch.setValue(0.30)
p.spn_line_feed.setValue(800.0)
p.spn_line_min.setValue(0.10)
for i in range(p.combo_photo_mat.count()):
    if p.combo_photo_mat.itemData(i) == MAT:
        p.combo_photo_mat.setCurrentIndex(i)
        break
p.spn_white.setValue(0.0)
p._maj_regime()
brut0 = p.lbl_regime.text()
assert "c62828" in brut0, ("à seuil nul le verdict doit être rouge", brut0[:120])
assert "⚠" in brut0, "à seuil nul le verdict doit porter le pictogramme d'alerte"
p.spn_white.setValue(5.0)
p._maj_regime()
brut5 = p.lbl_regime.text()
assert "2e7d32" in brut5, ("avec un seuil le verdict redevient vert", brut5[:120])
print("16. seuil nul -> verdict ROUGE (le fond sortira gris) ; seuil 5 % -> "
      "vert. Un ✓ ne décrit plus un défaut OK")


# --- 17. Plafond de puissance : ne pas creuser le bois -----------------
# Relevé À L'ÉTABLI le 31/07/2026, en cours de gravure : à pleine
# puissance sur hêtre F800 le trait fait bien 0,30 mm, mais il CREUSE et
# la surface ressort striée. La table des largeurs ne peut pas le prévoir
# -- elle mesure la largeur, jamais la profondeur. D'où un plafond réglé
# à la main, et un test qui vérifie qu'il est respecté partout.
def _s_reels(g):
    """S/Q qui pilotent le faisceau. Les COMMENTAIRES en contiennent aussi
    (« 90 % de S1000 ») : les compter ferait croire que le plafond fuit."""
    vals = set()
    for l in g.split("\n"):
        if l.startswith("("):
            continue
        m = re.search(r"\bS(\d+)", l) or re.search(r"M67 E0 Q(\d+)", l)
        if m and int(m.group(1)) > 0:
            vals.add(int(m.group(1)))
    return vals


img17 = [[x / 19.0 for x in range(20)] for _ in range(6)]
sans = core.generate_gcode_photo_swell_lines(
    img17, 0.30, core.Z_WORK_MM, 800.0, MAT, line_min_mm=0.10, quiet=True)
assert max(_s_reels(sans)) == 1000, sorted(_s_reels(sans))[-3:]
for cap in (950.0, 900.0, 800.0, 600.0):
    g17 = core.generate_gcode_photo_swell_lines(
        img17, 0.30, core.Z_WORK_MM, 800.0, MAT, line_min_mm=0.10,
        quiet=True, power_max=cap)
    assert g17, ("le plafond S%.0f ne devrait pas empêcher de générer" % cap)
    haut = max(_s_reels(g17))
    assert haut <= cap + 1e-9, ("le G-code dépasse le plafond", cap, haut)
    # et la plage annoncée doit RÉTRÉCIR par le haut, jamais par le bas
    niv = core.swell_power_levels(MAT, 800.0, 0.10, power_max=cap)
    assert niv is not None and abs(niv[1] - 0.10) < 1e-9, niv
    assert niv[2] < 0.30 + 1e-9, niv
print("17. plafond respecté à S950/900/800/600 ; sans plafond le G-code monte "
      "bien à S1000 OK")

# Trop bas : refus NET, et le message accuse le plafond, pas la vitesse.
assert core.swell_power_levels(MAT, 800.0, 0.10, power_max=150.0) is None
assert core.generate_gcode_photo_swell_lines(
    img17, 0.30, core.Z_WORK_MM, 800.0, MAT, quiet=True,
    power_max=150.0) is None
m17 = core.swell_refus_message(MAT, 800.0, 150.0)
assert "plafond" in m17.lower() and "S200" in m17, m17
assert "F800" not in m17, ("le refus accuse la vitesse alors que le fautif "
                           "est le plafond", m17)
print("18. plafond S150 (sous la plus faible mesure) : refus net, et le "
      "message nomme le PLAFOND, pas la vitesse OK")

print("\nTOUS LES TESTS lignes_gravees PASSENT")


# --- 18. Un rapport insuffisant n'est pas une modulation (v2.27.0) ----
# Le critere etait « la plage n'est pas EXACTEMENT plate » : un centieme
# d'ecart suffisait a promettre une modulation. Le 01/08/2026 la nouvelle
# planche du hetre a donne 0,10 -> 0,13 mm a F1500 (un pixel et demi sur
# l'image redressee) et le panneau s'est mis a accepter des vitesses ou le
# trait ne module rien.
MAT_R = "TestRapport"


def _table(rapport):
    """Materiau ou F400 module franchement (3x) et F800 au rapport voulu.

    Deux vitesses et non une : avec une seule, un refus tombe dans la
    branche « le trait ne varie a AUCUNE vitesse mesuree » et on ne teste
    plus le seuil mais le cas degenere."""
    core.save_burn_widths(MAT_R, {"focus": (
        [{"power": s_, "feed": 400.0, "width": w}
         for s_, w in ((200.0, 0.10), (600.0, 0.20), (1000.0, 0.30))]
        + [{"power": s_, "feed": 800.0,
            "width": round(0.10 * (1 + (rapport - 1) * (s_ - 200.0) / 800.0), 4)}
           for s_ in (200.0, 600.0, 1000.0)]), "defocus": []})


# Le controle se DEMONTRE : de part et d'autre du seuil, verdicts opposes.
_table(core.SWELL_RAPPORT_MINI - 0.2)
assert core.swell_power_levels(MAT_R, 800.0, 0.10) is None, (
    "un rapport sous le seuil doit etre refuse",
    core.burn_width_range(MAT_R, 800.0))
_msg = core.swell_refus_message(MAT_R, 800.0)
assert "{:.1f}x".format(core.SWELL_RAPPORT_MINI) in _msg, _msg
assert "F400" in _msg, ("le refus doit nommer la vitesse qui marche", _msg)

_table(core.SWELL_RAPPORT_MINI + 0.2)
assert core.swell_power_levels(MAT_R, 800.0, 0.10) is not None, (
    "un rapport au-dessus du seuil doit passer : sinon le test ne prouve rien",
    core.burn_width_range(MAT_R, 800.0))
print("18. seuil de rapport {:.1f}x : {:.1f}x refuse, {:.1f}x accepte OK".format(
    core.SWELL_RAPPORT_MINI, core.SWELL_RAPPORT_MINI - 0.2,
    core.SWELL_RAPPORT_MINI + 0.2))

# --- 19. Le refus ne doit pas renvoyer vers une vitesse REFUSEE -------
# Defaut constate a la minute ou le seuil a ete pose : swell_max_feed
# gardait l'ancien critere (« pas exactement plat ») et le message disait
# « descendre a F3000 » alors que F3000 etait lui-meme refuse. Un message
# et un verdict qui se contredisent sont pires que pas de message.
core.save_burn_widths(MAT_R, {"focus": (
    # F800 module vraiment...
    [{"power": s_, "feed": 800.0, "width": w}
     for s_, w in ((200.0, 0.10), (600.0, 0.20), (1000.0, 0.30))]
    # ...F1500 et F3000 juste un peu, sous le seuil.
    + [{"power": s_, "feed": f_, "width": w}
       for f_ in (1500.0, 3000.0)
       for s_, w in ((200.0, 0.10), (600.0, 0.11), (1000.0, 0.13))]),
    "defocus": []})
_rapide = core.swell_max_feed(MAT_R)
assert _rapide == 800.0, ("swell_max_feed doit appliquer le MEME seuil",
                          _rapide, core.burn_width_range(MAT_R, 3000.0))
assert core.swell_power_levels(MAT_R, _rapide, 0.10) is not None, (
    "la vitesse nommee par le refus doit elle-meme etre acceptee")
assert "F{:.0f}".format(_rapide) in core.swell_refus_message(MAT_R, 3000.0)
core.save_burn_widths(MAT_R, {})
print("19. la vitesse nommee par le refus est elle-meme acceptee OK")

# --- 20. Le refus et son explication lisent la MEME plage ----------------
# Constate le 01/08/2026 sur la vraie planche du hetre : le panneau refusait
# sous le plafond S900 (1,33x) et expliquait sans lui (1,50x), d'ou la
# phrase « soit 1.50x -- sous le rapport 1.5x », qui se contredit seule.
MAT_P = u"TestPlafond"
core.save_burn_widths(MAT_P, {"focus": [
    # Sous S900 la plage est plate ; il faut S1000 pour qu'elle enfle.
    {"power": s_, "feed": 800.0, "width": w}
    for s_, w in ((200.0, 0.12), (600.0, 0.13), (900.0, 0.16),
                  (1000.0, 0.24))], "defocus": []})
_sans = core.swell_plage(MAT_P, 800.0)
_avec = core.swell_plage(MAT_P, 800.0, 900.0)
assert _sans[2] >= core.SWELL_RAPPORT_MINI > _avec[2], (_sans, _avec)
assert core.swell_power_levels(MAT_P, 800.0, 0.10, power_max=900.0) is None
_msg = core.swell_refus_message(MAT_P, 800.0, 900.0)
# Le rapport CITE doit etre celui qui a decide, donc sous le seuil.
import re as _re
_cites = [float(x) for x in _re.findall(r"soit ([\d.]+)x", _msg)]
assert _cites and all(r < core.SWELL_RAPPORT_MINI for r in _cites), (_cites, _msg)
assert "PLAFOND" in _msg and "S900" in _msg, ("le plafond est la cause, "
                                              "le message doit le nommer", _msg)
# Le plafond nomme doit etre le plus BAS qui debloque -- pas le palier
# mesure au-dessus : on ne demande pas plus de puissance que necessaire.
_assez = core.swell_plafond_suffisant(MAT_P, 800.0)
assert _assez is not None and 900.0 < _assez <= 1000.0, _assez
assert "S{:.0f}".format(_assez) in _msg, ("le message doit nommer CE "
                                          "plafond-la", _assez, _msg)
# Et il doit vraiment debloquer, sinon le conseil renvoie dans le mur.
assert core.swell_power_levels(MAT_P, 800.0, 0.10, power_max=_assez) is not None
# Un cheveu en dessous, il ne debloque plus : c'est bien le MINIMUM.
assert core.swell_plage(MAT_P, 800.0, _assez - 5.0)[2] < core.SWELL_RAPPORT_MINI
core.save_burn_widths(MAT_P, {})
print("20. le refus et son explication lisent la meme plage OK")

# --- 21. Le verbe suit le sens ------------------------------------------
# « Descendre a F3000 » depuis F800 se lisait comme une faute de frappe et
# faisait douter de tout le message : F3000 est plus RAPIDE, pas plus lent.
MAT_V = u"TestVerbe"
core.save_burn_widths(MAT_V, {"focus": (
    # F200 enfle, F800 non : le conseil doit dire « Descendre ».
    [{"power": s_, "feed": 200.0, "width": w}
     for s_, w in ((200.0, 0.16), (1000.0, 0.34))]
    + [{"power": s_, "feed": 800.0, "width": w}
       for s_, w in ((200.0, 0.12), (1000.0, 0.13))]), "defocus": []})
_m = core.swell_refus_message(MAT_V, 800.0)
assert "Descendre a F200" in _m.replace("à", "a"), _m
core.save_burn_widths(MAT_V, {"focus": (
    # L'inverse : seule la vitesse HAUTE enfle -> « Passer a ».
    [{"power": s_, "feed": 200.0, "width": w}
     for s_, w in ((200.0, 0.12), (1000.0, 0.13))]
    + [{"power": s_, "feed": 800.0, "width": w}
       for s_, w in ((200.0, 0.16), (1000.0, 0.34))]), "defocus": []})
_m = core.swell_refus_message(MAT_V, 200.0)
assert "Passer a F800" in _m.replace("à", "a"), _m
assert "Descendre" not in _m, ("nommer une vitesse plus rapide en disant "
                               "« descendre »", _m)
core.save_burn_widths(MAT_V, {})
print("21. le verbe du conseil suit le sens de la vitesse OK")
