# -*- coding: utf-8 -*-
"""Cadrage automatique du trait à mesurer, sur la planche 1.

Ce que ces tests gardent : un cadre posé par le calcul doit tomber sur le
trait que la machine a RÉELLEMENT gravé. Les positions sont donc relues
dans le G-code produit, jamais recalculées avec la même formule que le
code testé -- une vérification qui rejoue sa propre arithmétique passe au
vert en décrivant exactement le même décalage que le défaut.

Un cadre décalé d'une rangée est le pire cas possible ici : il ne lève
aucune exception, il ne se voit pas à l'écran, et il rend une largeur
parfaitement plausible -- celle de la puissance voisine.
"""
import re

from harness import preparer

h = preparer()
core = h.core

# --- 1. Le G-code et les cadres décrivent les mêmes traits --------------

g = core.generate_gcode_planche_focus()
assert g, "la planche 1 ne génère plus de G-code"

# Chaque trait est précédé de son commentaire : c'est le seul lien fiable
# entre un mouvement et le couple (S, F) qui l'a produit.
reels = {}
cur = None
for ligne in g.splitlines():
    m = re.match(r"\(-- Planche 1 : S(\d+) F(\d+) --\)", ligne.strip())
    if m:
        cur = (float(m.group(1)), float(m.group(2)))
        continue
    if cur is None:
        continue
    mv = re.match(r"G[01] X([-\d.]+) Y([-\d.]+)", ligne.strip())
    if mv:
        reels.setdefault(cur, []).append((float(mv.group(1)),
                                          float(mv.group(2))))

cadres, infos = core.cadres_planche_focus()
assert len(cadres) == len(reels), (
    "autant de cadres que de traits gravés", len(cadres), len(reels))
print("1. {} traits gravés, {} cadres proposés OK".format(len(reels),
                                                          len(cadres)))

# --- 2. Chaque cadre est centré sur SON trait ---------------------------

# Le G-code est recadré au zéro pièce à l'écriture, donc les Y absolus
# diffèrent d'une translation ; ce qui doit être vrai, c'est que l'écart
# soit LE MÊME pour les 35 traits. Une dispersion non nulle voudrait dire
# qu'un cadre suit une autre rangée que la sienne.
y_haut = infos["y0"] + infos["hauteur"]
par_cle = {(c["power"], c["feed"]): c for c in cadres}
ecarts = []
for cle, pts in reels.items():
    c = par_cle.get(cle)
    assert c is not None, ("aucun cadre pour", cle)
    ecarts.append(abs((c["y0"] + c["y1"]) / 2.0 - (y_haut - pts[0][1])))
disp = max(ecarts) - min(ecarts)
assert disp < 1e-6, ("un cadre ne suit pas son trait", disp, sorted(ecarts))
print("2. dispersion des écarts Y : {:.9f} mm OK".format(disp))

# --- 3. Un cadre contient UN trait, jamais deux -------------------------

hauteur = max(c["y1"] - c["y0"] for c in cadres)
milieux = sorted({round((c["y0"] + c["y1"]) / 2.0, 4) for c in cadres})
ecart_rangees = min(b - a for a, b in zip(milieux, milieux[1:]))
assert hauteur < ecart_rangees, (
    "le cadre mord sur la rangée voisine", hauteur, ecart_rangees)
print("3. cadre {:.1f} mm de haut pour {:.1f} mm entre rangées OK".format(
    hauteur, ecart_rangees))

# --- 4. La mire n'est pas cadrée comme un trait de mesure ---------------

# `_ajouter_mire` allonge la bande EN PLACE : les bras des croix et les
# graduations de la réglette sont des segments horizontaux eux aussi, et
# proposeraient de mesurer la mire dans une case de la grille.
attendus = {(float(p), float(f))
            for p in core._powers_capped(core.PLANCHE_FOCUS_POWERS)
            for f in core.PLANCHE_FOCUS_FEEDS}
obtenus = set(par_cle)
assert obtenus == attendus, ("cadres étrangers à la grille",
                             obtenus ^ attendus)
print("4. {} couples (S, F), aucun venu de la mire OK".format(len(obtenus)))

# --- 5. Les traits obliques sont refusés, pas cadrés de travers ---------

# Le profil est moyenné colonne par colonne et les deux lignes de mesure
# sont horizontales : un trait oblique n'y est pas mesurable. Mieux vaut
# ne rien proposer que proposer un cadre où la mesure serait fausse.
band_oblique = [([(0.0, 0.0), (10.0, 5.0)], 500.0, 800.0, "(oblique)")]
assert core.cadres_traits_planche(band_oblique, infos) == [], (
    "un trait oblique ne doit pas être cadré")
band_droit = [([(0.0, 3.0), (10.0, 3.0)], 500.0, 800.0, "(droit)")]
assert len(core.cadres_traits_planche(band_droit, infos)) == 1
print("5. trait oblique refusé, trait horizontal accepté OK")

# --- 6. Entrées vides : on ne propose rien, on ne casse pas -------------

assert core.cadres_traits_planche([], infos) == []
assert core.cadres_traits_planche(band_droit, None) == []
print("6. bande vide / mire absente : liste vide, sans exception OK")

# --- 7. La mise en page est une SOURCE UNIQUE ---------------------------

# Le générateur et le cadrage doivent appeler la même disposition. Si
# quelqu'un réintroduit un calcul parallèle dans le générateur, les Y
# cesseront de coïncider -- ce que le point 2 attrape -- mais autant dire
# ici pourquoi la fonction existe.
band, labels = core.disposition_planche_focus(core.PLANCHE_FOCUS_POWERS,
                                              core.PLANCHE_FOCUS_FEEDS)
assert len(band) == len(core.PLANCHE_FOCUS_POWERS) * len(core.PLANCHE_FOCUS_FEEDS)
assert labels, "les étiquettes de la planche ont disparu"
print("7. disposition partagée : {} traits, {} arêtes d'étiquette OK".format(
    len(band), len(labels)))

print("\nOK : cadrage automatique aligné sur la planche réellement gravée.")
