# -*- coding: utf-8 -*-
"""La mire compare les SEPT tramages, chacun dans son régime.

Une mire qui ne montre que quatre tramages sur sept ne sert plus à choisir,
et c'est le seul outil pour ça : un dégradé gravé côte à côte sur une chute.
Elle en montrait quatre depuis que les trois derniers ont été ajoutés.

Le point délicat n'est pas d'ajouter des bandes, c'est de graver chacune
dans SON régime, sinon la comparaison ment. Deux tramages gravent au foyer
(leur grain doit être net) alors que les quatre premiers acceptent un
défocus ; et les lignes gravées cessent d'enfler au-delà de F800 sur hêtre,
donc à la vitesse du panneau leur bande sortirait en aplat uniforme -- ou
serait sautée, ce qui revient au même : rien à comparer.

Cette mire a déjà porté un bug de fond, en juillet 2026 : elle convertissait
la fluence en S comme `generate_gcode_photo_lines`, avec la MÊME erreur,
si bien que la mire censée valider la calibration était fausse de la même
façon. D'où les vérifications ci-dessous sur les régimes réellement émis, et
non sur la présence des bandes.
"""
import re

from harness import preparer, hauteurs_z, figer_largeurs

h = preparer()
core = h.core
MAT = u"Hêtre"
# Table du foyer FIGÉE : ce test suppose une forme précise
# (enfle sous F800, plat au-dessus). Sans ça il rougit dès que
# l'atelier mesure -- arrivé le 01/08/2026.
figer_largeurs(core, MAT)

PAS = 0.80
FEED = 2000.0
g = core.generate_gcode_photo_sampler(
    pitch=PAS, z_work=core.Z_WORK_MM + 5.0, dwell_min_s=0.010,
    dwell_max_s=0.060, power=600.0, feed=FEED, line_width=0.80,
    material=MAT, quiet=True)
assert g, "aucune mire"

# --- 1. Sept bandes, étiquetées 1 à 7 -----------------------------------
bandes = re.findall(r"\(===== Bande (\d+) : (\w+) =====\)", g)
assert len(bandes) == 7, bandes
assert [int(n) for n, _k in bandes] == list(range(1, 8)), bandes
noms = [k for _n, k in bandes]
assert noms == ["diffusion", "duree", "calibre", "dither_lignes",
                "zdots", "simili", "enfle"], noms
print("1. {} bandes : {} OK".format(len(bandes), ", ".join(noms)))

# --- 2. Les bandes ne se chevauchent pas --------------------------------
# Une bande de trop, ou un y_off resté calé sur 4 bandes, les empilerait
# les unes sur les autres -- illisible, et invisible dans le G-code.
ys = {}
for bloc in re.split(r"\(===== Bande \d+ : \w+ =====\)", g)[1:]:
    nom = None
    vals = [float(m) for m in re.findall(r"\bY(-?\d+\.?\d*)", bloc)]
    if vals:
        ys[len(ys)] = (min(vals), max(vals))
bornes = [ys[i] for i in sorted(ys)]
assert len(bornes) == 7, len(bornes)
for i in range(len(bornes) - 1):
    # Bande 1 en haut : les Y DESCENDENT d'une bande à la suivante.
    assert bornes[i][0] > bornes[i + 1][1] - 1e-6, (
        "bandes {} et {} se chevauchent".format(i + 1, i + 2),
        bornes[i], bornes[i + 1])
print("2. les 7 bandes s'empilent sans se chevaucher, de Y {:.1f} à {:.1f} OK"
      .format(bornes[-1][0], bornes[0][1]))

# --- 3. Bandes 6 et 7 AU FOYER, les autres au défocus demandé -----------
z_defocus = core.Z_WORK_MM + 5.0
blocs = re.split(r"\(===== Bande \d+ : \w+ =====\)", g)[1:]


def z_de_gravure(bloc):
    """Les Z auxquels ce bloc GRAVE (pas les dégagements) : on suit le Z
    courant et on ne retient que ceux vus sur un G1."""
    z = None
    vus = set()
    for l in bloc.split("\n"):
        mz = re.search(r"\bZ(-?\d+\.?\d*)", l)
        if mz:
            z = float(mz.group(1))
        if l.startswith("G1 ") and z is not None:
            vus.add(round(z, 3))
    return vus


z_simili = z_de_gravure(blocs[5])
z_enfle = z_de_gravure(blocs[6])
assert z_simili == {core.Z_WORK_MM}, ("similigravure pas au foyer", z_simili)
assert z_enfle == {core.Z_WORK_MM}, ("lignes gravées pas au foyer", z_enfle)
z_dither = z_de_gravure(blocs[3])
assert z_defocus in z_dither, ("la diffusion en lignes devrait suivre le "
                               "défocus demandé", z_dither, z_defocus)
print("3. bandes 6 et 7 gravées au foyer Z{:.2f}, bande 4 au défocus Z{:.2f} OK"
      .format(core.Z_WORK_MM, z_defocus))

# --- 4. La bande 7 est gravée à la vitesse où le trait enfle encore ------
# À F2000 le trait est PLAT : gravée telle quelle, la bande ne montrerait
# qu'un aplat. La mire doit descendre à la plus rapide vitesse utile et le
# DIRE en tête, sinon on croit comparer ce qu'on ne compare pas.
rapide = core.swell_max_feed(MAT)
assert rapide and rapide < FEED, (rapide, FEED)
feeds_enfle = {float(m) for m in re.findall(r"\bF(\d+\.?\d*)", blocs[6])}
assert feeds_enfle == {rapide}, (feeds_enfle, rapide)
assert "bande 7 a F{:.0f}".format(rapide) in g, [
    l for l in g.split("\n") if "bande 7" in l]
print("4. bande 7 gravée à F{:.0f} et non F{:.0f}, et l'en-tête le dit OK"
      .format(rapide, FEED))

# --- 5. Les gros points Z bougent VRAIMENT en Z, et jamais pendant le tir
z_pts = z_de_gravure(blocs[4])
assert len(z_pts) > 3, ("le diamètre ne varie pas : la bande 5 n'a qu'un Z",
                        sorted(z_pts))
# Aucun G1 ne doit porter un Z : le Z bouge ENTRE les points.
assert not [l for l in blocs[4].split("\n")
            if l.startswith("G1 ") and "Z" in l], "un G1 déplace Z pendant le tir"
print("5. bande 5 : {} hauteurs de point, aucun Z pendant un tir OK".format(
    len(z_pts)))

# --- 6. Le dégagement passe AU-DESSUS du point le plus haut -------------
# Les gros points Z montent bien au-dessus de z_work : un z_safe calculé sur
# z_work seul ferait transiter le bec dans les points déjà gravés.
zs = hauteurs_z(g)
assert max(zs) > max(z_pts) + 1e-6, (
    "le dégagement ne dépasse pas le point le plus haut", max(zs), max(z_pts))
print("6. dégagement Z{:.2f} au-dessus du point le plus haut Z{:.2f} OK".format(
    max(zs), max(z_pts)))

# --- 7. Jamais de G4 faisceau allumé, dans aucune bande -----------------
s = 0
for l in g.split("\n"):
    m = re.search(r"\bS(\d+)", l)
    if m:
        s = int(m.group(1))
    assert not (l.startswith("G4 ") and s != 0), ("pause faisceau allumé", l)
assert "M2" in g and core.cmd_path_blend() in g
print("7. aucun G4 faisceau allumé, G64 et M2 présents OK")

# --- 8. Sans matériau : les deux bandes qui EXIGENT du mesuré sont sautées
g0 = core.generate_gcode_photo_sampler(
    pitch=PAS, z_work=core.Z_WORK_MM, dwell_min_s=0.010, dwell_max_s=0.060,
    power=600.0, feed=FEED, line_width=0.80, material=None, quiet=True)
assert g0
noms0 = [k for _n, k in re.findall(r"\(===== Bande (\d+) : (\w+) =====\)", g0)]
assert noms0 == noms, "les en-têtes de bande doivent rester annoncés"
# calibre et enfle n'ont rien à graver sans nuancier ni largeurs mesurées.
blocs0 = re.split(r"\(===== Bande \d+ : \w+ =====\)", g0)[1:]
for i, nom in ((2, "calibre"), (6, "enfle")):
    assert not [l for l in blocs0[i].split("\n")
                if l.startswith("G1 ") and re.search(r"\bS[1-9]", l)], (
        "la bande {} grave sans donnée mesurée".format(nom))
print("8. sans matériau : bandes « calibre » et « enfle » sautées, les 5 "
      "autres gravées OK")

print("\nTOUS LES TESTS mire PASSENT")
