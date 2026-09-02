# -*- coding: utf-8 -*-
"""L'import SVG natif : ce qu'il lit, à quelle taille, et ce qu'il dit.

Aucun essai ne couvrait ce module en propre -- seulement de biais, par
l'import LightBurn. Un audit du 02/09/2026 y a trouvé six défauts, dont
deux qui se paient sur le bois : les cinq sixièmes des formes SVG
disparaissaient sans un mot, et un fichier dont le width et le height ne
concordent pas avec son viewBox arrivait DEUX FOIS TROP GRAND.

La couche d'analyse n'importe ni FreeCAD ni Part : tout se mesure ici sans
le moindre stub, et c'est exactement pourquoi elle a été écrite ainsi.
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from harness import preparer                                  # noqa: E402

h = preparer()

import math                                                   # noqa: E402
import xml.etree.ElementTree as ET                            # noqa: E402
import svg_import as S                                        # noqa: E402


def bornes(d, tol=0.001):
    sp, _ = S.path_d_to_subpaths(d, tol=tol)
    pts = [p for s in sp for p in s["points"]]
    return (min(x for x, _ in pts), min(y for _, y in pts),
            max(x for x, _ in pts), max(y for _, y in pts))


class Faux(dict):
    """Un élément XML réduit à ses attributs."""
    def get(self, cle, defaut=None):
        return dict.get(self, cle, defaut)


print("=" * 62)
print("§1  Les six formes qui ne sont pas des <path>")
print("=" * 62)

SVG_MIXTE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     width="100mm" height="100mm">
  <path d="M0 0 L10 0 L10 10 Z"/>
  <rect x="20" y="20" width="30" height="30"/>
  <rect x="60" y="20" width="30" height="20" rx="5"/>
  <circle cx="60" cy="60" r="10"/>
  <ellipse cx="80" cy="20" rx="8" ry="4"/>
  <polygon points="5,90 15,90 10,80"/>
  <polyline points="30,90 40,90 40,80"/>
  <line x1="50" y1="90" x2="60" y2="90"/>
</svg>"""

recs, avertissements = S.parse_svg_root(ET.fromstring(SVG_MIXTE))
print("   formes dans le fichier : 8   tracés importés : %d" % len(recs))
assert len(recs) == 8, (
    "%d tracés sur 8 : des formes de base disparaissent encore, et un "
    "fichier mixte arrive amputé sans un mot" % len(recs))
print("   les huit arrivent : ✓")

# La géométrie, pas seulement la présence : un rectangle rendu de travers
# se grave de travers.
ATTENDU = [
    ("rect", Faux(x="20", y="20", width="30", height="40"), (20, 20, 50, 60), True),
    ("rect", Faux(x="0", y="0", width="40", height="20", rx="5"), (0, 0, 40, 20), True),
    ("circle", Faux(cx="60", cy="60", r="10"), (50, 50, 70, 70), True),
    ("ellipse", Faux(cx="0", cy="0", rx="8", ry="4"), (-8, -4, 8, 4), True),
    ("line", Faux(x1="1", y1="2", x2="7", y2="9"), (1, 2, 7, 9), False),
    ("polygon", Faux(points="5,90 15,90 10,80"), (5, 80, 15, 90), True),
    ("polyline", Faux(points="30,90 40,90 40,80"), (30, 80, 40, 90), False),
]
for tag, elem, attendu, doit_fermer in ATTENDU:
    d = S.forme_en_d(tag, elem)
    assert d, "%s ne produit aucun tracé" % tag
    obtenu = bornes(d)
    ecart = max(abs(a - b) for a, b in zip(obtenu, attendu))
    print("   %-9s bornes (%.2f, %.2f)-(%.2f, %.2f)   écart %.4f mm"
          % ((tag,) + obtenu + (ecart,)))
    assert ecart < 0.02, "%s : géométrie fausse, %s au lieu de %s" % (
        tag, obtenu, attendu)
    sp, _ = S.path_d_to_subpaths(d, tol=0.001)
    assert all(s["closed"] for s in sp) == doit_fermer, (
        "%s : la fermeture du contour n'est pas celle qu'attend le pipeline "
        "hachures (chain_edges exige une chaîne littéralement fermée)" % tag)
print("   géométrie et fermeture conformes : ✓")

# LES COINS ARRONDIS NE SONT PAS DÉCORATIFS : rendre un rectangle arrondi à
# angles vifs serait une géométrie fausse, et silencieuse. Les bornes sont
# les mêmes des deux côtés -- seul le coin le dit.
vif = S.forme_en_d("rect", Faux(x="0", y="0", width="40", height="20"))
rond = S.forme_en_d("rect", Faux(x="0", y="0", width="40", height="20", rx="5"))
n_vif = len(S.path_d_to_subpaths(vif, tol=0.001)[0][0]["points"])
n_rond = len(S.path_d_to_subpaths(rond, tol=0.001)[0][0]["points"])
print("   rect vif : %d points   rect arrondi (r=5) : %d points"
      % (n_vif, n_rond))
assert n_rond > n_vif + 40, (
    "le rectangle arrondi sort avec %d points : ses coins sont vifs"
    % n_rond)
# aucun point ne doit tomber DANS le coin coupé par l'arrondi
coin = [(x, y) for s in S.path_d_to_subpaths(rond, tol=0.001)[0]
        for x, y in s["points"] if x < 4.9 and y < 4.9
        and (5 - x) ** 2 + (5 - y) ** 2 > 5.05 ** 2]
assert not coin, "des points restent dans le coin que l'arrondi retire : %s" % coin[:3]
# et rx seul doit valoir ry, comme le veut le SVG
rx_seul = S.forme_en_d("rect", Faux(x="0", y="0", width="40", height="20", rx="5"))
ry_seul = S.forme_en_d("rect", Faux(x="0", y="0", width="40", height="20", ry="5"))
assert rx_seul == ry_seul, "rx seul doit valoir ry, et réciproquement"
print("   l'arrondi est bien là, et rx seul vaut ry : ✓")

# Le rond doit être rond : c'est ce qui se voit sur la pièce.
sp, _ = S.path_d_to_subpaths(S.forme_en_d("circle", Faux(cx="0", cy="0", r="10")),
                             tol=0.001)
ecart = max(abs(math.hypot(x, y) - 10.0) for s in sp for x, y in s["points"])
print("   écart max au cercle théorique : %.5f mm" % ecart)
assert ecart < 0.002, "le cercle s'écarte de %.4f mm" % ecart

# Une forme sans géométrie se DIT, elle ne se perd pas.
recs2, av2 = S.parse_svg_root(ET.fromstring(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
    '<rect x="0" y="0" width="0" height="5"/><circle cx="1" cy="1" r="0"/></svg>'))
print("   formes dégénérées : %d tracé(s), avertissements %s" % (len(recs2), av2))
assert not recs2 and av2, "une forme sans géométrie disparaît en silence"
print("   les dégénérées sont annoncées : ✓")

print()
print("=" * 62)
print("§2  L'échelle : le plus petit rapport, comme le veut « meet »")
print("=" * 62)

# Le SVG applique preserveAspectRatio="xMidYMid meet" par défaut : quand
# width et height ne concordent pas avec le viewBox, il RÉDUIT. Prendre
# celui de width -- testé en premier -- rendait 1,000 là où la norme dit
# 0,500 : la pièce se gravait au DOUBLE de sa taille.
for w, hh, attendu in [("100mm", "100mm", 1.0), ("100mm", "50mm", 0.5),
                       ("50mm", "100mm", 0.5), ("100mm", None, 1.0),
                       (None, "50mm", 0.5)]:
    attrs = " ".join('%s="%s"' % (k, v)
                     for k, v in (("width", w), ("height", hh)) if v)
    r = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" %s '
                      'viewBox="0 0 100 100"/>' % attrs)
    echelle = S.compute_svg_scale(r)[0]
    print("   width=%-7s height=%-7s → %.3f" % (w, hh, echelle))
    assert abs(echelle - attendu) < 1e-9, (
        "échelle %.3f au lieu de %.3f : le dessin arriverait %.1f fois trop "
        "grand" % (echelle, attendu, echelle / attendu))
print("   le plus petit rapport l'emporte : ✓")

# Sans viewBox, les unités utilisateur sont des px CSS à 96 dpi.
r = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">'
                  '<path d="M0 0L96 0"/></svg>')
x = S.parse_svg_root(r)[0][0]["subpaths"][0]["points"][-1][0]
print("   sans viewBox : 96 unités → %.4f mm" % x)
assert abs(x - 25.4) < 1e-6, "96 px doivent faire un pouce"

print()
print("=" * 62)
print("§3  Ce qui ne doit pas se deviner en silence")
print("=" * 62)

for texte, attendu in [("10mm", 10.0), ("10px", 25.4 / 9.6), ("10", 25.4 / 9.6)]:
    assert abs(S.parse_length_mm(texte) - attendu) < 1e-9, texte
try:
    S.parse_length_mm("10em")
    raise AssertionError("« 10em » est accepté : le repli silencieux sur px "
                         "invente une taille")
except S.SvgParseError as exc:
    print("   « 10em » → refusé (%s) : ✓" % exc)

# width="0" faisait tomber tout l'import sur une ZeroDivisionError.
r = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" '
                  'viewBox="0 0 100 100"><path d="M0 0L96 0"/></svg>')
recs3, _ = S.parse_svg_root(r)
x = recs3[0]["subpaths"][0]["points"][-1][0]
print("   width=\"0\" → %d tracé, 96 unités → %.4f mm" % (len(recs3), x))
assert abs(x - 25.4) < 1e-6, "une échelle nulle doit revenir au défaut"

# UN FILL VIDE EST UNE VALEUR INVALIDE, donc ignorée : l'élément hérite de
# son parent, comme le veut le SVG. Le `or` d'avant rendait la chaîne vide,
# que resolve_fill_color ne savait pas analyser et rabattait sur le NOIR --
# un tracé rouge par héritage sortait noir dans l'arbre FreeCAD.
assert S.own_fill_string(Faux(fill="")) is None, (
    "fill=\"\" est rendu tel quel au lieu d'être ignoré")
assert S.own_fill_string(Faux(fill="  ")) is None, "un fill d'espaces non plus"
assert S.resolve_fill_color(Faux(fill=""), "#ff0000") == (1.0, 0.0, 0.0), (
    "un fill vide retombe sur le noir au lieu d'hériter du rouge du parent")
assert S.resolve_fill_color(Faux(fill=""), None) == (0.0, 0.0, 0.0), (
    "sans parent coloré, le noir reste le défaut SVG")
assert S.own_fill_string(Faux(fill="#00ff00")) == "#00ff00", (
    "une vraie couleur doit passer")
print("   fill=\"\" est ignoré et l'héritage joue : ✓")

print()
print("=" * 62)
print("§4  Les bornes d'une conversion LightBurn")
print("=" * 62)

# Elles se relevaient à la regex dans le `d` déjà écrit : rayons et
# DRAPEAUX d'arc y entraient comme des coordonnées.
releve = []
S._ellipse(Faux(Rx="5", Ry="3"),
           S._composer(S.IDENTITE, (1, 0, 0, 1, 100.0, 200.0)), releve)
xs = [p[0] for p in releve]
ys = [p[1] for p in releve]
print("   ellipse 5x3 en (100, 200) → x [%.1f, %.1f]  y [%.1f, %.1f]"
      % (min(xs), max(xs), min(ys), max(ys)))
for obtenu, attendu, nom in ((min(xs), 95.0, "xmin"), (max(xs), 105.0, "xmax"),
                             (min(ys), 197.0, "ymin"), (max(ys), 203.0, "ymax")):
    assert abs(obtenu - attendu) < 1e-6, (
        "%s = %.1f au lieu de %.1f : les drapeaux d'arc entrent dans les "
        "bornes, le canevas grandit et le dessin part dans un coin"
        % (nom, obtenu, attendu))
# Et pour un <Shape Type="Path"> : les sommets réels, pas les points de
# contrôle des cubiques, qui débordent la courbe (−80 relevé pour une
# courbe qui ne descend qu'à −60).
FORME = ET.fromstring(
    '<Shape Type="Path"><XForm>1 0 0 1 100 200</XForm>'
    '<VertList>V0 0c0x1c1x1V10 0c0x1c1x1V10 5c0x1c1x1</VertList>'
    '<PrimList>L0 1L1 2L2 0</PrimList></Shape>')
releve_p = []
S._chemin(FORME, S._xform(FORME), releve_p)
xs = [p[0] for p in releve_p]
ys = [p[1] for p in releve_p]
print("   triangle en (100, 200) → x [%.1f, %.1f]  y [%.1f, %.1f]"
      % (min(xs), max(xs), min(ys), max(ys)))
for obtenu, attendu, nom in ((min(xs), 100.0, "xmin"), (max(xs), 110.0, "xmax"),
                             (min(ys), 200.0, "ymin"), (max(ys), 205.0, "ymax")):
    assert abs(obtenu - attendu) < 1e-6, (
        "%s = %.1f au lieu de %.1f : les sommets du chemin ne sont pas relevés"
        % (nom, obtenu, attendu))
print("   les bornes sont celles du dessin : ✓")

print()
print("=" * 62)
print("§5  Les pièges déjà payés tiennent toujours")
print("=" * 62)

# Drapeaux d'arc collés à la valeur suivante.
sp, _ = S.path_d_to_subpaths("M0 0A5 5 0 0,1 11.8 0")
fin = sp[0]["points"][-1]
print("   « A5 5 0 0,1 11.8 0 » finit en x = %.4f" % fin[0])
assert abs(fin[0] - 11.8) < 1e-6, (
    "une regex de flottant a avalé les drapeaux : x = %.4f" % fin[0])

# M suivi de groupes répétés = LINETO implicites.
sp, _ = S.path_d_to_subpaths("M0 0 10 0 20 0")
assert len(sp) == 1 and len(sp[0]["points"]) == 3, (
    "la répétition implicite du M perd le premier segment")

# Un sous-tracé continue après Z.
sp, _ = S.path_d_to_subpaths("M0 0L10 0L10 10Z L20 20")
assert len(sp) == 2, "un tracé qui continue après Z est perdu"

# Un `d` malformé garde ce qui a été lu.
sp, av = S.path_d_to_subpaths("M0 0L10 0 L bêtise")
assert sp and av, "un `d` malformé doit rendre les sous-tracés complets"
print("   drapeaux, répétition implicite, Z, `d` malformé : ✓")

print()
print("TOUT EST VERT")
