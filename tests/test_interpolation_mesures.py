# -*- coding: utf-8 -*-
"""Le repli « plus proche voisin » de `_bilinear_burn`, sur grille trouée.

Nuancier et largeurs brûlées passent tous deux par `_bilinear_burn`. Les
grilles de LARGEURS sont quasi pleines (1 trou sur Hêtre, 0 sur MDF) : le
repli n'y sert presque jamais. Le NUANCIER, lui, se remplit ton par ton au
gré des planches — 14 tons au foyer sur Hêtre pour 25 croisements, soit
44 % de trous — et c'est là que le repli décide de tout.

Il comparait `(|ΔS|, |ΔF|)` en lexicographique, donc la puissance passait
AVANT la vitesse quel que soit l'écart : le seul S1000 mesuré au foyer
l'étant à F6000, `darkness_at` rendait **42 % de F400 à F6000** — une
ligne parfaitement plate, et S1000 plus clair que S800.

Démenti à l'établi le 30/07/2026 : le carré plein S1000/F800 au foyer, au
pas 0,26, est sorti CARBONISÉ là où l'atelier annonçait 42 %. Une planche
gravée, encore une fois, contre un modèle qui se croyait mesuré.

Ce test protège la propriété, pas le cas signalé : aucune mesure isolée ne
doit répondre pour toute sa colonne, et aucun point réellement mesuré ne
doit être déformé par le repli.
"""
import math

from harness import preparer

h = preparer()
core = h.core
MAT = u"Hêtre"


def pt(s, f, v, cle="width"):
    return {"power": float(s), "feed": float(f), cle: float(v)}


def _lexicographique(pts, power, feed, key="width"):
    """L'ANCIENNE métrique, rejouée telle quelle. Elle sert deux fois : à
    prouver que ce test aurait attrapé le défaut (§2), et à prouver que la
    correction ne déplace rien là où les mesures sont denses (§5). Un test
    qui ne peut pas échouer ne garantit rien."""
    svals = sorted({float(p["power"]) for p in pts})
    fvals = sorted({float(p["feed"]) for p in pts})
    grid = {(float(p["power"]), float(p["feed"])): float(p[key]) for p in pts}

    def _bracket(vals, x):
        x = min(max(x, vals[0]), vals[-1])
        for a, b in zip(vals, vals[1:]):
            if a <= x <= b:
                return a, b, x
        return vals[-1], vals[-1], x

    def _g(sv, fv):
        w = grid.get((sv, fv))
        if w is None:
            w = float(min(pts, key=lambda p: (abs(float(p["power"]) - sv),
                                              abs(float(p["feed"]) - fv)))[key])
        return w

    s1, s2, sx = _bracket(svals, float(power))
    f1, f2, fx = _bracket(fvals, float(feed))
    ts = 0.0 if s2 == s1 else (sx - s1) / (s2 - s1)
    tf = 0.0 if f2 == f1 else ((math.log(fx) - math.log(f1))
                               / (math.log(f2) - math.log(f1)))
    return ((_g(s1, f1) * (1 - ts) + _g(s2, f1) * ts) * (1 - tf)
            + (_g(s1, f2) * (1 - ts) + _g(s2, f2) * ts) * tf)


# --- 1. La propriété, sur un nuage où la bonne réponse est évidente ------
# Trois puissances, pour que les écarts soient des FRACTIONS d'étendue et
# non des égalités de bord : sur un nuage à deux puissances et deux
# vitesses, toute case trouée est un coin et les deux voisins sont à
# distance 1 par construction -- le test passerait sur un ex aequo tranché
# par l'ordre de la liste, ce qui ne prouverait rien.
#
# Case trouée (1000, 400). Deux candidats : la puissance EXACTE mais quinze
# fois plus rapide, ou un quart d'étendue de puissance plus bas à la
# vitesse EXACTE. Le second est seize fois plus proche -- et c'est celui
# que l'ordre lexicographique refusait toujours.
nuage = [pt(200, 400, 10.0), pt(200, 6000, 5.0),
         pt(800, 400, 100.0), pt(1000, 6000, 42.0)]
v = core._bilinear_burn(nuage, 1000.0, 400.0)
assert abs(v - 100.0) < 1e-6, (
    "le repli a choisi le point 15x plus rapide au seul motif qu'il "
    "partageait la puissance", v)
print("1. case trouée : le voisin à la VITESSE exacte gagne (100,0), pas "
      "celui à la puissance exacte 15x plus loin OK")

# Le symétrique, contre une sur-correction : quand la vitesse voisine est
# vraiment proche (400 contre 500), la puissance exacte doit reprendre la
# main sur une puissance quatre fois plus éloignée.
nuage2 = [pt(200, 400, 10.0), pt(200, 6000, 5.0),
          pt(1000, 500, 95.0), pt(1000, 6000, 42.0)]
v2 = core._bilinear_burn(nuage2, 1000.0, 400.0)
assert abs(v2 - 95.0) < 1e-6, ("le repli ignore la puissance exacte", v2)
print("   et le symétrique : à vitesse voisine, la puissance exacte gagne OK")

# --- 2. Aucune mesure isolée ne répond pour toute sa colonne -------------
tons = [s for s in core.load_shades(MAT)
        if not float(s.get("z_offset", 0) or 0)
        and s.get("darkness") is not None
        and float(s.get("power", 0) or 0) > 0
        and float(s.get("feed", 0) or 0) > 0]
assert tons, "le nuancier Hêtre n'a plus de ton au foyer"
puissances = sorted({float(s["power"]) for s in tons})
vitesses = sorted({float(s["feed"]) for s in tons})
mesures = {(float(s["power"]), float(s["feed"])) for s in tons}
trous = len(puissances) * len(vitesses) - len(mesures)
plates = []
for s in puissances:
    vals = [core.darkness_at(MAT, s, f, 0.0) for f in vitesses]
    vals = [x for x in vals if x is not None]
    if vals and max(vals) - min(vals) < 1e-6:
        plates.append((s, vals[0]))
assert not plates, (
    "une puissance rend la MÊME noirceur à toutes les vitesses mesurées : "
    "c'est la mesure isolée qui a repris toute la colonne", plates)
print("2. nuancier Hêtre au foyer ({} tons, {} trous sur {} cases) : aucune "
      "ligne de puissance plate sur {} vitesses OK".format(
          len(tons), trous, len(puissances) * len(vitesses), len(vitesses)))

# La preuve que ce contrôle discrimine, sur un jeu FIGÉ.
#
# Cette démonstration rejouait l'ancienne métrique sur les tons Hêtre
# VIVANTS. Elle a cessé de tenir dès que Christophe a saisi le ton
# S1000/F800 -- justement celui que la planche carbonisée réclamait : avec
# deux mesures dans la colonne S1000, plus de ligne plate, et le contrôle
# tombait en échec alors que le code était juste. Une démonstration ne doit
# pas s'éteindre parce que la donnée s'améliore : on fige donc ici la
# grille TELLE QU'ELLE ÉTAIT le 30/07/2026 -- un seul S1000, mesuré à
# F6000, et des colonnes basses correctement balayées.
trouee = [pt(200, 400, 8.0, "darkness"), pt(200, 2000, 4.0, "darkness"),
          pt(600, 400, 70.0, "darkness"), pt(600, 2000, 30.0, "darkness"),
          pt(800, 400, 90.0, "darkness"), pt(800, 2000, 55.0, "darkness"),
          pt(1000, 6000, 42.0, "darkness")]
f_test = [400.0, 800.0, 2000.0, 6000.0]
avant = [_lexicographique(trouee, 1000.0, f, "darkness") for f in f_test]
assert max(avant) - min(avant) < 1e-6, (
    "l'ancienne métrique devrait rendre S1000 plat sur cette grille trouée",
    avant)
apres = [core._bilinear_burn(trouee, 1000.0, f, key="darkness") for f in f_test]
assert max(apres) - min(apres) > 1.0, (
    "la métrique corrigée rend elle aussi la colonne plate : la correction "
    "ne sert à rien", apres)
assert apres[0] > apres[-1], (
    "à S1000, F400 doit rester plus foncé que F6000", apres)
print("   (sur la grille trouée figée : l'ancienne métrique rendait {:.0f} % "
      "à TOUTES les vitesses, la corrigée s'étale de {:.0f} à {:.0f} % -- le "
      "contrôle discrimine bien)".format(avant[0], min(apres), max(apres)))

# Le cas exact démenti par le bois : S1000 doit noircir quand on ralentit.
lent = core.darkness_at(MAT, 1000.0, 800.0, 0.0)
rapide = core.darkness_at(MAT, 1000.0, 6000.0, 0.0)
assert lent > rapide + 10.0, (
    "à S1000 le foyer rend autant à F800 qu'à F6000 -- or F800 carbonise",
    lent, rapide)
print("   S1000 : {:.0f} % à F800 contre {:.0f} % à F6000 (plus lent = plus "
      "noir) OK".format(lent, rapide))

# --- 3. Plus lent = plus noir, sur TOUTE la grille -----------------------
# Établi expérimentalement le 29/07/2026 (quatre bandes à énergie égale).
# Le repli ne doit jamais produire l'inverse.
inversions = []
for s in puissances:
    precedent = None
    for f in vitesses:
        d = core.darkness_at(MAT, s, f, 0.0)
        if precedent is not None and d > precedent + 1e-6:
            inversions.append((s, f, precedent, d))
        precedent = d
assert not inversions, ("noirceur qui REMONTE quand la vitesse augmente",
                        inversions)
print("3. les {} lignes de puissance décroissent toutes avec la vitesse "
      "OK".format(len(puissances)))

# --- 4. Un point MESURÉ n'est jamais déformé par le repli ----------------
# L'invariant qui doit tenir quelle que soit la métrique : sur une case
# réellement mesurée, l'interpolateur rend la mesure, au chiffre près.
controles = 0
for materiau in core.burn_width_materials():
    table = core.load_burn_widths(materiau)
    for point in table.get("focus") or []:
        w = core.burn_width_at(float(point["power"]), float(point["feed"]),
                               materiau)
        assert w is not None and abs(w - float(point["width"])) < 1e-6, (
            "largeur au foyer déformée", materiau, point, w)
        controles += 1
for materiau in core.shade_materials():
    tons_m = [s for s in core.load_shades(materiau)
              if s.get("darkness") is not None
              and float(s.get("power", 0) or 0) > 0
              and float(s.get("feed", 0) or 0) > 0]
    # Deux tons peuvent partager (S, F) à un même défocus avec des noirceurs
    # différentes (jugements de planches distinctes) : la grille n'en garde
    # qu'un, on ne contrôle donc que les couples non ambigus.
    vus = {}
    for s in tons_m:
        cle = (round(float(s.get("z_offset", 0) or 0), 3),
               float(s["power"]), float(s["feed"]))
        vus.setdefault(cle, set()).add(float(s["darkness"]))
    for (dz, s, f), valeurs in vus.items():
        if len(valeurs) > 1:
            continue
        d = core.darkness_at(materiau, s, f, dz)
        assert d is not None and abs(d - list(valeurs)[0]) < 1e-6, (
            "noirceur mesurée déformée", materiau, dz, s, f, d, valeurs)
        controles += 1
print("4. {} points réellement mesurés (largeurs + nuancier, tous matériaux "
      "et tous défocus) rendus à l'identique OK".format(controles))

# --- 5. Sur grille PLEINE, la correction ne change rien ------------------
# La preuve d'innocuité : là où les mesures sont denses, l'ancienne
# métrique et la nouvelle donnent le même résultat.
ecarts = 0
compares = 0
for materiau in core.burn_width_materials():
    pts_f = core.load_burn_widths(materiau).get("focus") or []
    if len(pts_f) < 4:
        continue
    for s in range(200, 1001, 50):
        for f in (200, 400, 800, 1500, 3000, 6000):
            a = _lexicographique(pts_f, s, f)
            b = core._bilinear_burn(pts_f, s, f)
            compares += 1
            if abs(a - b) > 1e-9:
                ecarts += 1
assert ecarts == 0, (
    "la correction déplace des largeurs brûlées : les grilles ne sont pas "
    "aussi pleines qu'on le croyait", ecarts, compares)
print("5. {} largeurs comparées sur les grilles pleines : 0 écart avec "
      "l'ancienne métrique OK".format(compares))

print("\nTOUS LES TESTS interpolation_mesures PASSENT")
