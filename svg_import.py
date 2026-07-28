# -*- coding: utf-8 -*-
"""Import SVG natif -- © Atelier du Verdier

Analyse un fichier .svg directement (xml.etree de la bibliothèque standard,
sans détour par l'import Draft/DXF de FreeCAD) et produit un Part::Feature
par élément <path> d'origine : Shape = Part.Compound d'edges nus (ni faces
ni fils), exactement la convention que le reste de l'atelier sait déjà
consommer depuis les imports Draft SVG/DXF. La couleur de remplissage de
chaque tracé (héritée des <g> parents) est posée en ViewObject.LineColor,
comme aide visuelle.

Module feuille : aucune dépendance sur laser_core/task_panels/laser_jobs,
et surtout AUCUN import FreeCAD/Part au niveau module -- seules les trois
fonctions de construction (_subpath_to_edges, _record_to_object,
import_svg_file) les importent localement. Toute la couche d'analyse
(grammaire du `d`, aplatissement Bézier/arc, transformations, couleurs)
est du Python pur, testable sans le moindre stub.

Pas de courbes OCCT (Bézier/BSpline/Arc) : comme partout ailleurs dans
l'atelier, les courbes sont aplaties en chaînes de petits segments
Part.LineSegment. Hors périmètre (signalé par avertissement, jamais une
erreur dure) : <use>, dégradés, <clipPath>/<mask>/<filter>, <image>
matricielle, cascade CSS par classes.
"""

import math
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter


class SvgParseError(ValueError):
    """Donnée SVG inattendue dans un attribut `d` (position incluse)."""


# ==========================================================================
# A. GRAMMAIRE DU CHEMIN `d` (tokenizer + machine à états)
# ==========================================================================

# Tolérance d'aplatissement par défaut, en mm : même jugement « assez fin
# pour un trait laser » que DISCRETIZE_DISTANCE de laser_core (constante
# locale volontairement dupliquée pour garder ce module sans dépendance).
FLATTEN_TOL_MM = 0.3

_ARG_COUNT = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
              "Q": 4, "T": 2, "A": 7, "Z": 0}
_COMMAND_LETTERS = set("MLHVCSQTAZmlhvcsqtaz")
_SEPARATORS = set(" \t\r\n,")

_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def _skip_sep(d, i):
    """Avance le curseur au-delà des espaces/virgules."""
    n = len(d)
    while i < n and d[i] in _SEPARATORS:
        i += 1
    return i


def _read_number(d, i):
    """Lit un nombre SVG à partir de `i` ; retourne (valeur, curseur suivant)."""
    i = _skip_sep(d, i)
    m = _NUMBER_RE.match(d, i)
    if not m:
        raise SvgParseError("nombre attendu à l'offset {}".format(i))
    return float(m.group(0)), m.end()


def _read_flag(d, i):
    """Lit un drapeau d'arc : EXACTEMENT un caractère '0' ou '1'.

    Indispensable en dehors de _read_number : le SVG colle les drapeaux
    large-arc/sweep contre la valeur suivante sans séparateur (« ...,0,111.8 »
    peut signifier drapeau=1, drapeau=1, x=1.8 -- une regex de flottant
    avalerait « 11 » en entier)."""
    i = _skip_sep(d, i)
    if i >= len(d) or d[i] not in "01":
        raise SvgParseError("drapeau 0/1 attendu à l'offset {}".format(i))
    return int(d[i]), i + 1


def _iter_path_tokens(d):
    """Générateur de tokens (lettre, [arguments…]) d'un attribut `d`.

    Gère la règle de répétition implicite : une lettre suivie de plusieurs
    groupes d'arguments (ex. un M puis deux groupes `c` sans re-préfixe).
    Z/z produit toujours exactement ('Z'|'z', []) sans répétition. Lève
    SvgParseError au point d'erreur -- les tokens déjà produits restent
    exploitables par l'appelant (interprétation au fil de l'eau)."""
    i = _skip_sep(d, 0)
    n = len(d)
    while i < n:
        letter = d[i]
        if letter not in _COMMAND_LETTERS:
            raise SvgParseError(
                "commande inconnue « {} » à l'offset {}".format(letter, i))
        i += 1
        arity = _ARG_COUNT[letter.upper()]
        if arity == 0:
            yield letter, []
            i = _skip_sep(d, i)
            continue
        is_arc = letter.upper() == "A"
        while True:
            group = []
            for pos in range(arity):
                if is_arc and pos in (3, 4):
                    val, i = _read_flag(d, i)
                else:
                    val, i = _read_number(d, i)
                group.append(val)
            yield letter, group
            i = _skip_sep(d, i)
            # Répétition implicite : encore des chiffres avant la
            # prochaine lettre ?
            if i >= n or d[i] in _COMMAND_LETTERS:
                break


def tokenize_path(d):
    """Découpe un attribut `d` complet en liste de tokens (lève si malformé)."""
    return list(_iter_path_tokens(d))


def path_d_to_subpaths(d, tol=FLATTEN_TOL_MM):
    """Interprète un attribut `d` en sous-tracés aplatis.

    Retourne (subpaths, warnings) où chaque sous-tracé est
    {"points": [(x, y), …], "closed": bool}. Sur Z/z le point de départ est
    ré-ajouté explicitement s'il n'est pas déjà confondu avec le point
    courant : le pipeline hachures/gravure existant (chain_edges,
    Part.sortEdges) exige une chaîne littéralement fermée. Une donnée
    malformée arrête l'analyse de CE tracé : on retourne les sous-tracés
    déjà complets plus un avertissement, sans jamais lever."""
    subpaths = []
    warnings = []
    current = (0.0, 0.0)
    subpath_start = (0.0, 0.0)
    points = None
    last_control = None       # dernier point de contrôle C/S ou Q/T
    last_cmd = ""

    def _finish(closed=False):
        nonlocal points
        if points is not None and len(points) >= 2:
            if closed:
                fx, fy = points[0]
                lx, ly = points[-1]
                if math.hypot(lx - fx, ly - fy) > 1e-9:
                    points.append((fx, fy))
            subpaths.append({"points": points, "closed": closed})
        points = None

    try:
        for letter, args in _iter_path_tokens(d):
            rel = letter.islower()
            cmd = letter.upper()
            ox, oy = current if rel else (0.0, 0.0)

            if cmd == "M":
                _finish(False)
                current = (args[0] + ox, args[1] + oy)
                subpath_start = current
                points = [current]
            elif cmd == "Z":
                if points is not None:
                    current = subpath_start
                    _finish(True)
                    # Un tracé peut continuer après Z (nouveau sous-tracé
                    # implicite depuis le point de départ).
                    points = [current]
            elif points is None:
                # Commande de dessin sans M préalable : point courant
                # implicite (0,0), rare mais toléré.
                points = [current]

            if cmd == "L":
                current = (args[0] + ox, args[1] + oy)
                points.append(current)
            elif cmd == "H":
                current = (args[0] + ox, current[1])
                points.append(current)
            elif cmd == "V":
                current = (current[0], args[0] + oy)
                points.append(current)
            elif cmd in ("C", "S"):
                if cmd == "C":
                    c1 = (args[0] + ox, args[1] + oy)
                    c2 = (args[2] + ox, args[3] + oy)
                    end = (args[4] + ox, args[5] + oy)
                else:
                    if last_cmd in ("C", "S") and last_control is not None:
                        c1 = (2 * current[0] - last_control[0],
                              2 * current[1] - last_control[1])
                    else:
                        c1 = current
                    c2 = (args[0] + ox, args[1] + oy)
                    end = (args[2] + ox, args[3] + oy)
                points.extend(flatten_cubic_bezier(current, c1, c2, end, tol))
                last_control = c2
                current = end
            elif cmd in ("Q", "T"):
                if cmd == "Q":
                    c1 = (args[0] + ox, args[1] + oy)
                    end = (args[2] + ox, args[3] + oy)
                else:
                    if last_cmd in ("Q", "T") and last_control is not None:
                        c1 = (2 * current[0] - last_control[0],
                              2 * current[1] - last_control[1])
                    else:
                        c1 = current
                    end = (args[0] + ox, args[1] + oy)
                points.extend(flatten_quadratic_bezier(current, c1, end, tol))
                last_control = c1
                current = end
            elif cmd == "A":
                rx, ry, phi_deg, laf, sf = args[0], args[1], args[2], int(args[3]), int(args[4])
                end = (args[5] + ox, args[6] + oy)
                center = svg_arc_to_center(current[0], current[1], rx, ry,
                                           phi_deg, laf, sf, end[0], end[1])
                if center is None:
                    points.append(end)   # dégénéré : trait droit, selon la spec
                else:
                    cx, cy, arx, ary, phi, th1, dth = center
                    points.extend(flatten_arc(cx, cy, arx, ary, phi, th1, dth, tol))
                current = end

            if cmd not in ("C", "S", "Q", "T"):
                last_control = None
            last_cmd = cmd
    except SvgParseError as exc:
        warnings.append("tracé interrompu ({})".format(exc))

    _finish(False)
    return subpaths, warnings


# ==========================================================================
# B. APLATISSEMENT BÉZIER / ARC (mathématiques pures)
# ==========================================================================

def _point_line_dist(p, a, b):
    """Distance perpendiculaire de p à la droite (a, b)."""
    abx, aby = b[0] - a[0], b[1] - a[1]
    length = math.hypot(abx, aby)
    if length < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    return abs(abx * (p[1] - a[1]) - aby * (p[0] - a[0])) / length


def _mid(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def flatten_cubic_bezier(p0, p1, p2, p3, tol=FLATTEN_TOL_MM, depth=0, max_depth=24):
    """Aplati une Bézier cubique en points (p0 exclu, p3 inclus).

    Test de platitude : distance des points de contrôle à la corde ;
    subdivision de De Casteljau à t=0.5 sinon."""
    if depth >= max_depth or max(_point_line_dist(p1, p0, p3),
                                 _point_line_dist(p2, p0, p3)) <= tol:
        return [p3]
    p01, p12, p23 = _mid(p0, p1), _mid(p1, p2), _mid(p2, p3)
    p012, p123 = _mid(p01, p12), _mid(p12, p23)
    p0123 = _mid(p012, p123)
    return (flatten_cubic_bezier(p0, p01, p012, p0123, tol, depth + 1, max_depth)
            + flatten_cubic_bezier(p0123, p123, p23, p3, tol, depth + 1, max_depth))


def flatten_quadratic_bezier(p0, p1, p2, tol=FLATTEN_TOL_MM, depth=0, max_depth=24):
    """Aplati une Bézier quadratique en points (p0 exclu, p2 inclus)."""
    if depth >= max_depth or _point_line_dist(p1, p0, p2) <= tol:
        return [p2]
    p01, p12 = _mid(p0, p1), _mid(p1, p2)
    p012 = _mid(p01, p12)
    return (flatten_quadratic_bezier(p0, p01, p012, tol, depth + 1, max_depth)
            + flatten_quadratic_bezier(p012, p12, p2, tol, depth + 1, max_depth))


def svg_arc_to_center(x1, y1, rx, ry, phi_deg, large_arc_flag, sweep_flag, x2, y2):
    """Paramétrisation centrale W3C d'un arc SVG.

    Retourne (cx, cy, rx, ry, phi, theta1, delta_theta) ou None si l'arc
    est dégénéré (rayon nul ou extrémités confondues : trait droit)."""
    if abs(x1 - x2) < 1e-12 and abs(y1 - y2) < 1e-12:
        return None
    rx, ry = abs(rx), abs(ry)
    if rx < 1e-12 or ry < 1e-12:
        return None
    phi = math.radians(phi_deg)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)

    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    # Correction des rayons trop petits (fréquent dans les fichiers réels).
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1.0:
        s = math.sqrt(lam)
        rx *= s
        ry *= s

    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(0.0, num / den))   # clamp : le flottant peut passer sous 0
    if large_arc_flag == sweep_flag:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = co * (-ry) * x1p / rx

    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2.0

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    theta1 = ang(1.0, 0.0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = ang((x1p - cxp) / rx, (y1p - cyp) / ry,
                (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep_flag and delta > 0:
        delta -= 2 * math.pi
    elif sweep_flag and delta < 0:
        delta += 2 * math.pi
    return cx, cy, rx, ry, phi, theta1, delta


def flatten_arc(cx, cy, rx, ry, phi, theta1, delta_theta, tol=FLATTEN_TOL_MM):
    """Échantillonne un arc d'ellipse en points (theta1 exclu, fin incluse)."""
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    r = max(rx, ry, 1e-6)
    max_step = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - tol / r)))
    if max_step < 1e-6:
        max_step = 1e-6
    n = max(2, min(200, int(math.ceil(abs(delta_theta) / max_step))))
    pts = []
    for k in range(1, n + 1):
        t = theta1 + delta_theta * k / n
        ct, st = math.cos(t), math.sin(t)
        pts.append((cx + rx * cos_phi * ct - ry * sin_phi * st,
                    cy + rx * sin_phi * ct + ry * cos_phi * st))
    return pts


# ==========================================================================
# C. COMPOSITION DE TRANSFORMATIONS (matrices affines 2D)
# ==========================================================================

# (a, b, c, d, e, f) représente [[a, c, e], [b, d, f], [0, 0, 1]],
# le même ordre que matrix(a,b,c,d,e,f) en SVG.
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def matrix_mul(m1, m2):
    """Produit m1 · m2 (appliquer m2 d'abord, puis m1)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + c1 * b2,
            b1 * a2 + d1 * b2,
            a1 * c2 + c1 * d2,
            b1 * c2 + d1 * d2,
            a1 * e2 + c1 * f2 + e1,
            b1 * e2 + d1 * f2 + f1)


def matrix_apply(m, x, y):
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def matrix_translate(tx, ty=0.0):
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def matrix_scale(sx, sy=None):
    if sy is None:
        sy = sx
    return (sx, 0.0, 0.0, sy, 0.0, 0.0)


def matrix_rotate(deg, cx=0.0, cy=0.0):
    rad = math.radians(deg)
    co, si = math.cos(rad), math.sin(rad)
    m = (co, si, -si, co, 0.0, 0.0)
    if cx or cy:
        m = matrix_mul(matrix_mul(matrix_translate(cx, cy), m),
                       matrix_translate(-cx, -cy))
    return m


def matrix_skew_x(deg):
    return (1.0, 0.0, math.tan(math.radians(deg)), 1.0, 0.0, 0.0)


def matrix_skew_y(deg):
    return (1.0, math.tan(math.radians(deg)), 0.0, 1.0, 0.0, 0.0)


_TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")


def parse_transform(s):
    """Compose un attribut transform="…" en une seule matrice.

    Les opérations sont multipliées à gauche dans l'ordre du document :
    transform="A B" équivaut à A(B(point))."""
    m = IDENTITY
    if not s:
        return m
    for name, raw_args in _TRANSFORM_RE.findall(s):
        args = [float(v) for v in _NUMBER_RE.findall(raw_args)]
        if name == "matrix" and len(args) == 6:
            op = tuple(args)
        elif name == "translate" and args:
            op = matrix_translate(args[0], args[1] if len(args) > 1 else 0.0)
        elif name == "scale" and args:
            op = matrix_scale(args[0], args[1] if len(args) > 1 else None)
        elif name == "rotate" and args:
            if len(args) >= 3:
                op = matrix_rotate(args[0], args[1], args[2])
            else:
                op = matrix_rotate(args[0])
        elif name == "skewX" and args:
            op = matrix_skew_x(args[0])
        elif name == "skewY" and args:
            op = matrix_skew_y(args[0])
        else:
            continue
        m = matrix_mul(m, op)
    return m


# ==========================================================================
# D. VIEWBOX / ÉCHELLE MM, ET COULEUR DE REMPLISSAGE
# ==========================================================================

_MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "in": 25.4,
                "pt": 25.4 / 72.0, "pc": 25.4 / 6.0, "px": 25.4 / 96.0}


def parse_length_mm(s):
    """Convertit une longueur SVG (avec suffixe éventuel) en millimètres."""
    s = (s or "").strip()
    m = _NUMBER_RE.match(s)
    if not m:
        raise SvgParseError("longueur illisible : {!r}".format(s))
    value = float(m.group(0))
    unit = s[m.end():].strip().lower()
    if unit == "%":
        raise SvgParseError("longueur en % non prise en charge")
    return value * _MM_PER_UNIT.get(unit, 25.4 / 96.0)


def parse_viewbox(s):
    vals = [float(v) for v in _NUMBER_RE.findall(s or "")]
    if len(vals) != 4 or vals[2] <= 0 or vals[3] <= 0:
        return None
    return tuple(vals)


def compute_svg_scale(root):
    """(échelle mm/unité, minx, miny, hauteur du viewBox ou None).

    Sans width/height (cas des exports Illustrator décoratifs), la taille
    intrinsèque vaut le viewBox en px CSS à 96 dpi -> 25.4/96 mm/unité.
    La hauteur sert à retourner l'axe Y (SVG : Y vers le bas ; FreeCAD :
    Y vers le haut) pour garder l'orientation vue dans Inkscape."""
    default = 25.4 / 96.0
    vb = parse_viewbox(root.get("viewBox"))
    if vb is None:
        return default, 0.0, 0.0, None
    minx, miny, vbw, vbh = vb
    for attr, vb_dim in (("width", vbw), ("height", vbh)):
        raw = root.get(attr)
        if raw:
            try:
                return parse_length_mm(raw) / vb_dim, minx, miny, vbh
            except SvgParseError:
                continue
    return default, minx, miny, vbh


_NAMED_COLORS = {
    "black": (0.0, 0.0, 0.0), "white": (1.0, 1.0, 1.0),
    "red": (1.0, 0.0, 0.0), "green": (0.0, 0.5, 0.0),
    "lime": (0.0, 1.0, 0.0), "blue": (0.0, 0.0, 1.0),
    "yellow": (1.0, 1.0, 0.0), "cyan": (0.0, 1.0, 1.0),
    "aqua": (0.0, 1.0, 1.0), "magenta": (1.0, 0.0, 1.0),
    "fuchsia": (1.0, 0.0, 1.0), "gray": (0.5, 0.5, 0.5),
    "grey": (0.5, 0.5, 0.5), "silver": (0.75, 0.75, 0.75),
    "orange": (1.0, 0.647, 0.0), "purple": (0.5, 0.0, 0.5),
    "brown": (0.647, 0.165, 0.165), "maroon": (0.5, 0.0, 0.0),
    "navy": (0.0, 0.0, 0.5), "olive": (0.5, 0.5, 0.0),
    "teal": (0.0, 0.5, 0.5), "pink": (1.0, 0.753, 0.796),
}

_RGB_FUNC_RE = re.compile(r"rgb\s*\(\s*([^)]*)\)", re.IGNORECASE)


def parse_color(value):
    """#rgb, #rrggbb, rgb(...), ou mot-clé -> (r, g, b) en 0..1, sinon None."""
    if not value:
        return None
    v = value.strip().lower()
    if v.startswith("#"):
        h = v[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return tuple(int(h[k:k + 2], 16) / 255.0 for k in (0, 2, 4))
            except ValueError:
                return None
        return None
    m = _RGB_FUNC_RE.match(v)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) == 3:
            try:
                out = []
                for p in parts:
                    if p.endswith("%"):
                        out.append(max(0.0, min(1.0, float(p[:-1]) / 100.0)))
                    else:
                        out.append(max(0.0, min(1.0, float(p) / 255.0)))
                return tuple(out)
            except ValueError:
                return None
        return None
    return _NAMED_COLORS.get(v)


def _style_prop(style_attr, prop):
    """Extrait la valeur de `prop` d'un attribut style="a:b;c:d"."""
    for chunk in (style_attr or "").split(";"):
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            if k.strip().lower() == prop:
                return v.strip()
    return None


def own_fill_string(elem):
    """Remplissage propre à l'élément (style= prioritaire sur fill=)."""
    return _style_prop(elem.get("style"), "fill") or elem.get("fill")


def own_stroke_string(elem):
    return _style_prop(elem.get("style"), "stroke") or elem.get("stroke")


def resolve_fill_color(elem, inherited_fill):
    """Couleur de remplissage résolue en (r, g, b) 0..1.

    Priorité : fill propre > hérité > noir (défaut SVG). fill="none"
    retombe sur le stroke PROPRE de l'élément, sinon noir. Une valeur
    non analysable (dégradé url(#…), currentColor…) retombe sur noir."""
    raw = own_fill_string(elem)
    if raw is None:
        raw = inherited_fill
    if raw is None:
        return (0.0, 0.0, 0.0)
    if raw.strip().lower() == "none":
        stroke = own_stroke_string(elem)
        if stroke and stroke.strip().lower() != "none":
            return parse_color(stroke) or (0.0, 0.0, 0.0)
        return (0.0, 0.0, 0.0)
    return parse_color(raw) or (0.0, 0.0, 0.0)


# ==========================================================================
# E. PARCOURS DE L'ARBRE XML ET POINT D'ENTRÉE D'ANALYSE
# ==========================================================================

_SKIP_DESCEND = {"defs"}
_UNSUPPORTED = {"use", "image", "linearGradient", "radialGradient", "pattern",
                "clipPath", "mask", "filter", "text", "symbol", "marker",
                "style"}

_UNSUPPORTED_LABELS = {
    "use": "réutilisation <use>",
    "image": "image matricielle",
    "linearGradient": "dégradé linéaire",
    "radialGradient": "dégradé radial",
    "pattern": "motif <pattern>",
    "clipPath": "découpe <clipPath>",
    "mask": "masque <mask>",
    "filter": "filtre graphique",
    "text": "texte <text> (convertir en tracés dans Inkscape)",
    "symbol": "symbole <symbol>",
    "marker": "marqueur <marker>",
    "style": "feuille de style CSS (classes non résolues)",
}


def _local_tag(elem):
    """Nom de balise sans le préfixe {namespace}."""
    tag = elem.tag
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _walk(elem, matrix, inherited_fill, tol, records, skipped):
    for child in elem:
        tag = _local_tag(child)
        if tag in _SKIP_DESCEND:
            continue
        if tag in _UNSUPPORTED:
            skipped[tag] += 1
            continue
        child_matrix = matrix_mul(matrix, parse_transform(child.get("transform")))
        if tag == "path" and child.get("d"):
            subpaths, warns = path_d_to_subpaths(child.get("d"), tol)
            if warns:
                skipped["_malformed"] += len(warns)
            transformed = []
            for sp in subpaths:
                pts = [matrix_apply(child_matrix, x, y) for x, y in sp["points"]]
                transformed.append({"points": pts, "closed": sp["closed"]})
            if transformed:
                records.append({
                    "subpaths": transformed,
                    "fill_rgb": resolve_fill_color(child, inherited_fill),
                    "svg_id": child.get("id"),
                })
        else:
            # <g>, <svg> imbriqué (traité comme un simple groupe), ou
            # balise inconnue mais inoffensive : on descend toujours,
            # pour ne jamais perdre de géométrie par excès de rigueur.
            child_fill = own_fill_string(child) or inherited_fill
            _walk(child, child_matrix, child_fill, tol, records, skipped)


def parse_svg_root(root):
    """Analyse un arbre SVG déjà chargé -> (records, warnings).

    L'axe Y est retourné (miroir dans le viewBox) : le SVG compte Y vers
    le bas, FreeCAD vers le haut -- sans ce retournement le dessin gravé
    serait en miroir vertical par rapport à ce qu'affiche Inkscape."""
    scale, minx, miny, vbh = compute_svg_scale(root)
    tol_user_units = FLATTEN_TOL_MM / scale
    if vbh is not None:
        initial = matrix_mul(matrix_scale(scale, -scale),
                             matrix_translate(-minx, -(miny + vbh)))
    else:
        initial = matrix_scale(scale, -scale)
    initial = matrix_mul(initial, parse_transform(root.get("transform")))
    records = []
    skipped = Counter()
    _walk(root, initial, own_fill_string(root), tol_user_units, records, skipped)
    warnings = []
    for tag, count in sorted(skipped.items()):
        if tag == "_malformed":
            warnings.append(
                "{} tracé(s) partiellement illisible(s) (donnée malformée)".format(count))
        else:
            warnings.append("{} élément(s) <{}> ignoré(s) : {}".format(
                count, tag, _UNSUPPORTED_LABELS.get(tag, "non pris en charge")))
    return records, warnings


def parse_svg_string(text):
    """Variante depuis une chaîne (tests sans fichier temporaire)."""
    return parse_svg_root(ET.fromstring(text))


def parse_svg_file(filepath):
    return parse_svg_root(ET.parse(filepath).getroot())


# ==========================================================================
# CONSTRUCTION FREECAD (imports locaux uniquement)
# ==========================================================================

_GENERIC_ID_RE = re.compile(r"^(path|rect|circle|ellipse|polygon|polyline|g|svg)[-_]?\d*$",
                            re.IGNORECASE)


def _subpath_to_edges(points, closed, z=0.0):
    """Convertit une liste de points en edges Part.LineSegment."""
    import FreeCAD
    import Part
    edges = []
    vecs = [FreeCAD.Vector(x, y, z) for x, y in points]
    for i in range(len(vecs) - 1):
        if vecs[i].distanceToPoint(vecs[i + 1]) > 1e-7:
            edges.append(Part.LineSegment(vecs[i], vecs[i + 1]).toShape())
    if closed and len(vecs) >= 3 and vecs[-1].distanceToPoint(vecs[0]) > 1e-7:
        edges.append(Part.LineSegment(vecs[-1], vecs[0]).toShape())
    return edges


def _label_for_record(record, index):
    svg_id = record.get("svg_id")
    if svg_id and not _GENERIC_ID_RE.match(svg_id):
        return svg_id
    return "Tracé SVG {:02d}".format(index)


def _record_to_object(doc, record, index):
    """Crée un Part::Feature pour un enregistrement de tracé, ou None si vide."""
    import Part
    edges = []
    for sp in record["subpaths"]:
        edges.extend(_subpath_to_edges(sp["points"], sp["closed"]))
    if not edges:
        return None
    obj = doc.addObject("Part::Feature", "MotifSVG")
    obj.Shape = Part.Compound(edges)
    obj.Label = _label_for_record(record, index)
    if hasattr(obj, "ViewObject"):
        obj.ViewObject.LineColor = record["fill_rgb"]
        obj.ViewObject.LineWidth = 1.0
    return obj


def import_svg_file(filepath):
    """Importe un fichier SVG dans le document actif.

    Retourne (nombre d'objets créés, [avertissements]). Un seul
    doc.recompute() pour tout le fichier -- c'est précisément ce qui rend
    cet import rapide face au détour DXF fragmenté."""
    import FreeCAD
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return 0, ["Ouvre (ou crée) un document d'abord."]
    if not os.path.isfile(filepath):
        return 0, ["Fichier introuvable : {}".format(filepath)]
    try:
        records, warnings = parse_svg_file(filepath)
    except (ET.ParseError, OSError) as exc:
        return 0, ["Fichier SVG illisible : {}".format(exc)]
    if not records:
        return 0, warnings + ["Aucun tracé <path> exploitable dans ce fichier."]
    count = 0
    for i, rec in enumerate(records, start=1):
        if _record_to_object(doc, rec, i) is not None:
            count += 1
    doc.recompute()
    return count, warnings
