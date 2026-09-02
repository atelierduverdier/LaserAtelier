# -*- coding: utf-8 -*-
"""L'import rend CE QUE LE DESSIN MONTRE -- ni plus, ni moins, ni ailleurs.

Cinq défauts relevés à la lecture ligne à ligne de `svg_import.py` le
02/09/2026, tous reproduits avant d'être décrits. Le fichier avait déjà été
audité le matin même : ceux-ci sont ce qu'une lecture suivie ajoute.

1. CE QUI EST MASQUÉ PARTAIT SUR LE BOIS. `display:none` et
   `visibility:hidden` n'étaient pas lus -- or éteindre un calque de
   construction avant d'exporter est le geste le plus ordinaire d'Inkscape.
   Mesuré sur un fichier montrant UN rectangle : quatre tracés importés,
   zéro avertissement.
2. UNE ELLIPSE LIGHTBURN NE SUIVAIT PAS SA `XForm`. Elle était écrite en
   deux arcs de rayons Rx/Ry avec une rotation d'axe ZÉRO : seuls les deux
   sommets tournaient, le ventre des arcs non. Mesuré sur une 20×5 tournée
   de 45° : 116,6 mm de large au lieu de 29,2.
3. LE MÊME DESSIN ATTERRISSAIT À DEUX ENDROITS selon qu'il portait un
   viewBox ou non : y de -7,94 à -2,65 mm d'un côté, 42,06 à 47,35 de
   l'autre. Sous l'origine, donc hors table.
4. TROIS SILENCES : `width="100%"` devenait 100 unités utilisateur (un
   rectangle inventé, gravé), `preserveAspectRatio="none"` était ignoré
   sans un mot, et tout `Type` de forme LightBurn autre que Path/Ellipse/
   Group disparaissait entre le .lbrn2 et le SVG.
5. DEUX JEUX DE MATRICES dans un seul fichier -- `IDENTITE`/`_composer`/
   `_appliquer` recopiaient mot pour mot `IDENTITY`/`matrix_mul`/
   `matrix_apply` cent lignes plus haut.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()

import math                                                   # noqa: E402
import os                                                     # noqa: E402
import tempfile                                               # noqa: E402
import xml.etree.ElementTree as ET                            # noqa: E402
from collections import Counter                               # noqa: E402
import svg_import as S                                        # noqa: E402

ENTETE = ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" '
          'height="100mm" viewBox="0 0 100 100">')


def importer(corps, entete=ENTETE):
    return S.parse_svg_root(ET.fromstring(entete + corps + "</svg>"))


def xs_de(rec):
    return [p[0] for sp in rec["subpaths"] for p in sp["points"]]


print("=" * 66)
print("§1  Ce qui est masqué dans le dessin ne part pas sur le bois")
print("=" * 66)

# Les quatre façons de masquer, plus le rectangle qu'on voit vraiment.
recs, av = importer(
    '<g id="visible"><rect x="0" y="0" width="10" height="10"/></g>'
    '<g id="calque_eteint" style="display:none">'
    '  <rect x="20" y="20" width="10" height="10"/></g>'
    '<rect x="40" y="40" width="10" height="10" visibility="hidden"/>'
    '<rect x="60" y="60" width="10" height="10" display="none"/>'
    '<rect x="80" y="80" width="10" height="10" style="visibility:collapse"/>')
print("   tracés importés : %d   (l'écran en montre 1)" % len(recs))
assert len(recs) == 1, (
    "%d tracés importés pour un seul visible : un calque masqué se grave"
    % len(recs))
assert min(xs_de(recs[0])) < 1e-6, "ce n'est pas le rectangle visible"
assert any("masqué" in m for m in av), (
    "les éléments masqués sont écartés SANS LE DIRE : %s" % av)
assert "4" in " ".join(av), "l'avertissement ne dit pas combien : %s" % av
print("   les quatre masqués sont écartés, et comptés : ✓  (%s)" % av[0])

# LA RÈGLE N'EST PAS LA MÊME POUR LES DEUX, et les confondre ferait
# disparaître du dessin légitime : `visibility` s'hérite mais un descendant
# peut la reprendre ; `display:none` emporte tout, sans recours.
recs, _ = importer('<g visibility="hidden">'
                   '  <rect x="0" y="0" width="5" height="5"/>'
                   '  <rect x="10" y="0" width="5" height="5" '
                   'visibility="visible"/></g>')
assert len(recs) == 1 and min(xs_de(recs[0])) > 1.0, (
    "un descendant qui reprend visibility:visible doit s'importer : %d tracé(s)"
    % len(recs))
recs, _ = importer('<g style="display:none">'
                   '<rect x="0" y="0" width="5" height="5" '
                   'visibility="visible"/></g>')
assert not recs, "display:none doit emporter tout son sous-arbre"
print("   visibility se reprend, display:none non : ✓")


print()
print("=" * 66)
print("§2  Une ellipse LightBurn suit sa XForm, rotation comprise")
print("=" * 66)


def inverse(m):
    a, b, c, d, e, f = m
    det = a * d - c * b
    return (d / det, -b / det, -c / det, a / det,
            (c * f - d * e) / det, (b * e - a * f) / det)


RX, RY = 20.0, 5.0
co, si = math.cos(math.radians(45)), math.sin(math.radians(45))
CAS = [
    ("rotation 45°", (co, si, -si, co, 0.0, 0.0)),
    ("rotation 30° + échelles 2 et 0,5",
     S.matrix_mul((math.cos(math.radians(30)), math.sin(math.radians(30)),
                   -math.sin(math.radians(30)), math.cos(math.radians(30)),
                   10.0, -3.0), (2.0, 0.0, 0.0, 0.5, 0.0, 0.0))),
    ("cisaillement", (1.0, 0.0, 0.4, 1.0, 5.0, 5.0)),
]
for nom, m in CAS:
    forme = ET.fromstring('<Shape Type="Ellipse" Rx="%g" Ry="%g"/>' % (RX, RY))
    d = S._ellipse(forme, m)
    sp, _ = S.path_d_to_subpaths(d)
    pts = sp[0]["points"]
    # ON NE COMPARE PAS LA FONCTION À ELLE-MÊME : chaque point produit,
    # ramené dans le repère local par la matrice INVERSE, doit tomber sur
    # l'ellipse x²/rx² + y²/ry² = 1. C'est la définition, pas le code.
    inv = inverse(m)
    ecart = max(abs((lambda u, v: (u / RX) ** 2 + (v / RY) ** 2 - 1.0)(
        *S.matrix_apply(inv, x, y))) for x, y in pts)
    # Emprise : demi-diamètres de l'ellipse transformée, formule fermée.
    a, b, c, dd = m[0], m[1], m[2], m[3]
    demi_x = math.hypot(a * RX, c * RY)
    demi_y = math.hypot(b * RX, dd * RY)
    ox, oy = S.matrix_apply(m, 0.0, 0.0)
    lx = max(x for x, _ in pts) - min(x for x, _ in pts)
    ly = max(y for _, y in pts) - min(y for _, y in pts)
    print("   %-34s écart à l'ellipse %.2e   %.2f × %.2f mm"
          % (nom, ecart, lx, ly))
    # 1e-4 et non zéro : le `d` s'écrit à quatre décimales, ce qui déplace
    # chaque point de 5e-5 mm au plus. L'ancien défaut, lui, sortait de
    # l'ellipse de plusieurs MILLIMÈTRES.
    assert ecart < 1e-4, (
        "%s : les points ne sont pas sur l'ellipse transformée (écart %.3e) "
        "-- la XForm n'est suivie que par les sommets" % (nom, ecart))
    assert abs(lx - 2 * demi_x) < 0.05 and abs(ly - 2 * demi_y) < 0.05, (
        "%s : emprise %.2f × %.2f au lieu de %.2f × %.2f"
        % (nom, lx, ly, 2 * demi_x, 2 * demi_y))
print("   les points tombent sur l'ellipse, l'emprise est la bonne : ✓")

# Le relevé qui sert à cadrer le SVG produit voit la même chose.
releve = []
S._ellipse(ET.fromstring('<Shape Type="Ellipse" Rx="5" Ry="3"/>'),
           (1.0, 0.0, 0.0, 1.0, 100.0, 200.0), releve)
assert abs(min(x for x, _ in releve) - 95.0) < 1e-6, releve[:3]
assert abs(max(y for _, y in releve) - 203.0) < 1e-6, releve[:3]
print("   le relevé des bornes suit : ✓")


print()
print("=" * 66)
print("§3  Le même dessin atterrit au même endroit, viewBox ou non")
print("=" * 66)

AVEC = ('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" '
        'viewBox="0 0 377.9528 188.9764">')
SANS = '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm">'
ys = []
for entete in (AVEC, SANS):
    recs, _ = importer('<rect x="10" y="10" width="20" height="20"/>', entete)
    pts = [p for sp in recs[0]["subpaths"] for p in sp["points"]]
    ys.append((min(p[1] for p in pts), max(p[1] for p in pts)))
print("   avec viewBox : y de %.2f à %.2f mm" % ys[0])
print("   sans viewBox : y de %.2f à %.2f mm" % ys[1])
assert min(ys[1]) > 0, (
    "sans viewBox le dessin part SOUS l'origine (y = %.2f) : hors table"
    % min(ys[1]))
assert abs(ys[0][0] - ys[1][0]) < 0.01 and abs(ys[0][1] - ys[1][1]) < 0.01, (
    "deux placements pour un seul dessin : %s contre %s" % (ys[0], ys[1]))
print("   un seul placement : ✓")

# Et quand le fichier ne dit NI viewBox NI hauteur, on ne sait pas : on ne
# fabrique pas un repère, l'ancien comportement reste.
recs, _ = importer('<rect x="10" y="10" width="20" height="20"/>',
                   '<svg xmlns="http://www.w3.org/2000/svg">')
assert recs, "un SVG sans viewBox ni hauteur doit tout de même s'importer"
print("   sans viewBox NI hauteur, rien n'est inventé : ✓")


print()
print("=" * 66)
print("§4  Rien ne se perd, ni ne s'invente, sans un mot")
print("=" * 66)

# `width="100%"` valait 100 unités utilisateur : un rectangle FABRIQUÉ.
recs, av = importer('<rect x="0" y="0" width="100%" height="100%"/>'
                    '<rect x="10" y="10" width="20" height="20"/>')
print("   width=\"100%%\" → %d tracé(s), %s" % (len(recs), av))
assert len(recs) == 1, "un pourcentage devient une longueur inventée"
assert any("géométrie" in m for m in av), (
    "la forme illisible disparaît sans un mot : %s" % av)

# preserveAspectRatio="none" demande deux échelles ; on n'en applique qu'une.
_, av = importer('<rect x="0" y="0" width="10" height="10"/>',
                 ENTETE[:-1] + ' preserveAspectRatio="none">')
assert any("preserveAspectRatio" in m for m in av), (
    "l'étirement par axe est ignoré en silence : %s" % av)
print("   preserveAspectRatio=\"none\" annoncé : ✓")

# rgb() séparé par des espaces : la forme moderne rendait NOIR.
for texte in ("rgb(255 0 0)", "rgb(255,0,0)", "rgb(100% 0% 0%)"):
    assert S.parse_color(texte) == (1.0, 0.0, 0.0), (
        "%s n'est pas lu : un tracé rouge arrive noir" % texte)
print("   rgb() se lit avec virgules OU espaces : ✓")

# Un type de forme LightBurn inconnu ne s'évapore plus entre les deux
# formats -- on ne prétend pas savoir lesquels existent, on compte ce
# qu'on n'a pas su lire.
CHEMIN = os.path.join(tempfile.mkdtemp(prefix="fidele-"), "essai.lbrn2")
with open(CHEMIN, "w", encoding="utf-8") as fh:
    fh.write('<LightBurnProject>'
             '<Shape Type="Path"><XForm>1 0 0 1 0 0</XForm>'
             '<VertList>V0 0V10 0V10 5</VertList></Shape>'
             '<Shape Type="Inconnu"><XForm>1 0 0 1 0 0</XForm></Shape>'
             '<Shape><XForm>1 0 0 1 0 0</XForm></Shape>'
             '</LightBurnProject>')
ign = Counter()
chemins, _bornes = S.convertir_lightburn(CHEMIN, ign)
print("   .lbrn2 : %d chemin(s) traduit(s), non traduits %s"
      % (len(chemins), dict(ign)))
assert len(chemins) == 1, "le chemin valide doit passer"
assert sum(ign.values()) == 2, (
    "des formes LightBurn disparaissent entre les deux formats sans un "
    "mot : %s" % dict(ign))
assert "Inconnu" in ign, "le type non traduit n'est pas nommé : %s" % dict(ign)
# La signature reste compatible : les deux appelants existants la gardent.
chemins2, bornes2 = S.convertir_lightburn(CHEMIN)
assert chemins2 == chemins, "convertir_lightburn a changé de contrat"
print("   ce qui n'est pas traduit est nommé et compté : ✓")

# Un tracé sans longueur ne se soustrait plus du compte en silence.
import FreeCAD                                                # noqa: E402
_doc = FreeCAD.newDocument("EssaiImportFidele")
try:
    svg = os.path.join(os.path.dirname(CHEMIN), "plat.svg")
    with open(svg, "w", encoding="utf-8") as fh:
        fh.write(ENTETE + '<line x1="5" y1="5" x2="5" y2="5"/>'
                 '<rect x="10" y="10" width="20" height="20"/></svg>')
    n, av = S.import_svg_file(svg)
    print("   %d objet(s) créé(s), %s" % (n, av))
    assert n == 1, "le rectangle doit arriver"
    assert any("longueur" in m for m in av), (
        "un tracé sans longueur baisse le compte sans un mot : %s" % av)
finally:
    FreeCAD.closeDocument("EssaiImportFidele")
print("   un tracé sans longueur est annoncé : ✓")


print()
print("=" * 66)
print("§5  Un seul jeu de matrices dans le fichier")
print("=" * 66)

for nom in ("IDENTITE", "_composer", "_appliquer"):
    assert not hasattr(S, nom), (
        "%s recopie encore une fonction de la section C : deux copies de la "
        "même arithmétique, dont une seule sera corrigée un jour" % nom)
assert S.matrix_mul(S.IDENTITY, (2, 0, 0, 2, 1, 1)) == (2, 0, 0, 2, 1, 1)
print("   IDENTITY / matrix_mul / matrix_apply, et rien d'autre : ✓")

print()
print("TOUT EST VERT")
