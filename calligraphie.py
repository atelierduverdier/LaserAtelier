# -*- coding: utf-8 -*-
"""Calligraphie : une police d'ordinateur gravée en PLEINS ET DÉLIÉS.

Christophe, le 03/08/2026, deux fichiers `.otf` à l'appui : « j'aimerais bien
des écritures en lié-délié de ce style, avec la fonction qui fait bouger la
tête en Z ».

LE PRINCIPE. Une police calligraphique est un CONTOUR rempli : on ne peut pas
la graver au trait sans perdre ce qui en fait la calligraphie, l'alternance
des pleins et des déliés. Ce module en extrait deux choses :

  * le SQUELETTE -- la ligne médiane de la lettre, ce que la plume a parcouru ;
  * la LARGEUR LOCALE en chaque point de ce squelette.

Le squelette devient la trajectoire XY, la largeur devient la hauteur Z via le
fuseau (`laser_core.echelle_fuseau_z`). Les pleins et déliés ne sont donc plus
DESSINÉS, ils sont produits par le mouvement de la tête -- une seule passe, un
seul trait, comme un vrai geste de plume.

CE MODULE NE LIT AUCUNE POLICE DU DÉPÔT. Il prend le chemin d'un fichier sur
le disque de l'utilisateur. Les polices calligraphiques du commerce sont
presque toutes en licence « usage personnel » : les embarquer ici, dans un
dépôt public sous LGPL, serait une violation de licence. Elles restent chez
leur propriétaire, ce module ne fait que les lire.

AUCUN IMPORT FreeCAD NI Qt AU NIVEAU MODULE -- même règle que `svg_import.py`,
et pour la même raison : toute la couche géométrique se teste telle quelle,
sans stub. `numpy`, `scipy` et `PIL` sont déjà des dépendances de l'atelier
(aperçu photo, redressement de planches).

Sections :
  A -- Rendu de la police en image
  B -- Squelette et largeur locale
  C -- Traçage : des pixels aux gestes
  D -- Point d'entrée
"""

import math
import os

# Taille de rendu de la police, en pixels d'oeil (em). Ce n'est PAS la taille
# gravée : le passage aux millimètres se fait après, par simple facteur. La
# valeur fixe la seule chose qui compte ici, la précision RELATIVE -- à 600 px
# d'em, le délié le plus fin de Blacksword fait encore 4 px de large, assez
# pour que la transformée de distance en donne une largeur crédible.
EM_PX = 600

# Fenêtre de lissage du profil de largeur, en mm de trajet. La transformée de
# distance sur une image tramée est bruitée au pixel : sans lissage la largeur
# repart vers le haut 55 fois sur un trait de 5 mm, et le Z passerait son temps
# à corriger un bruit de rendu. Une fenêtre de 1 mm efface le pixel sans
# toucher au geste (un plein de calligraphie s'étale sur 5 à 30 mm).
LISSAGE_MM = 1.0

# Sous cette longueur, une chaîne est un artefact d'amincissement (une barbe
# sur un empattement), pas un trait. La graver coûte deux mouvements de tête
# pour une marque invisible.
MIN_CHAINE_MM = 0.8

# Pas d'échantillonnage du trait le long du chemin, en mm.
PAS_ARC_MM = 0.4

_V8 = [(-1, 0), (-1, 1), (0, 1), (1, 1),
       (1, 0), (1, -1), (0, -1), (-1, -1)]     # P2..P9, sens horaire


class ErreurCalligraphie(Exception):
    """Ce qui empêche de graver, dit en une phrase montrable à l'écran."""


def _numpy():
    import numpy
    return numpy


# =======================================================================
# A -- RENDU DE LA POLICE EN IMAGE
# =======================================================================

def polices_disponibles(dossiers=None):
    """Fichiers .otf/.ttf trouvés, pour peupler un sélecteur.

    On regarde les dossiers de polices de l'utilisateur, jamais le dépôt :
    cf. l'en-tête du module."""
    dossiers = dossiers or [
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        os.path.expanduser("~/Projets/Fonts"),
        "/usr/share/fonts",
    ]
    trouve = {}
    for d in dossiers:
        if not os.path.isdir(d):
            continue
        for racine, _sd, fichiers in os.walk(d):
            for f in fichiers:
                if f.lower().endswith((".otf", ".ttf")):
                    trouve.setdefault(f, os.path.join(racine, f))
    return sorted(trouve.items())


def rendre_texte(chemin_police, texte, em_px=EM_PX, marge=None):
    """Le texte tramé en noir sur blanc, par FreeType (via PIL).

    On passe par le rendu de PIL plutôt que par les contours de fontTools :
    FreeType applique la règle de remplissage NON NULLE, et les scripts
    calligraphiques ont des contours qui se CHEVAUCHENT (une boucle repasse
    sur son propre fût). Reconstituer le remplissage à la main donnerait des
    trous là où la lettre est pleine -- et un trou dans le remplissage
    devient un trou dans le squelette, donc un trait coupé en deux."""
    from PIL import Image, ImageDraw, ImageFont
    np = _numpy()
    if not texte:
        raise ErreurCalligraphie("Aucun texte à graver.")
    try:
        police = ImageFont.truetype(chemin_police, int(em_px))
    except Exception as exc:
        raise ErreurCalligraphie(
            "Police illisible ({}) : {}".format(
                os.path.basename(chemin_police), exc))
    marge = int(marge if marge is not None else em_px * 0.15)
    sonde = ImageDraw.Draw(Image.new("L", (8, 8)))
    bb = sonde.textbbox((0, 0), texte, font=police)
    larg, haut = bb[2] - bb[0], bb[3] - bb[1]
    if larg <= 0 or haut <= 0:
        raise ErreurCalligraphie(
            "Cette police ne trace aucun des caractères demandés.")
    img = Image.new("L", (larg + 2 * marge, haut + 2 * marge), 0)
    ImageDraw.Draw(img).text((marge - bb[0], marge - bb[1]), texte,
                             font=police, fill=255)
    return np.array(img) > 127


# =======================================================================
# B -- SQUELETTE ET LARGEUR LOCALE
# =======================================================================

def _decale(b, dy, dx):
    np = _numpy()
    return np.roll(np.roll(b, dy, 0), dx, 1)


def _huit_voisins(b):
    return [_decale(b, dy, dx) for dy, dx in _V8]


def nombre_transitions(sq):
    """Nombre de passages 0->1 en tournant autour du pixel (le « A » de
    Zhang-Suen). Vaut 1 sur une extrémité, 2 sur un trait, >=3 sur une
    vraie jonction.

    C'EST LE BON CRITÈRE, et compter les voisins ne l'est pas : un trait
    diagonal tramé monte en escalier, et ses pixels ont alors TROIS voisins
    8-connexes sans qu'il y ait le moindre croisement. Confondre les deux
    hache le mot en confettis -- mesuré le 03/08/2026 sur « Verdier » en
    Blacksword : 282 morceaux dont le plus long faisait 5,6 mm, au lieu de
    ~130 gestes dont le plus long fait 31 mm. Le rendu sortait en pointillés
    et j'ai d'abord cru que la tête ne suivait pas en Z."""
    np = _numpy()
    P = _huit_voisins(sq)
    seq = P + [P[0]]
    A = sum(((~seq[i]) & seq[i + 1]).astype(np.int8) for i in range(8))
    return A * sq


def amincir(b, max_iter=400):
    """Amincissement de Zhang-Suen : l'encre réduite à un trait d'un pixel,
    en conservant la connexité et la position médiane."""
    np = _numpy()
    b = b.copy()
    for _ in range(max_iter):
        change = False
        for pas in (0, 1):
            P = _huit_voisins(b)
            B = sum(p.astype(np.int8) for p in P)
            seq = P + [P[0]]
            A = sum(((~seq[i]) & seq[i + 1]).astype(np.int8) for i in range(8))
            if pas == 0:
                c1 = ~(P[0] & P[2] & P[4])
                c2 = ~(P[2] & P[4] & P[6])
            else:
                c1 = ~(P[0] & P[2] & P[6])
                c2 = ~(P[0] & P[4] & P[6])
            sup = b & (B >= 2) & (B <= 6) & (A == 1) & c1 & c2
            if sup.any():
                b = b & ~sup
                change = True
        if not change:
            break
    return b


def largeur_locale(b):
    """Largeur de l'encre en chaque pixel : deux fois la distance au bord.

    C'est la définition même du diamètre de la plume à cet endroit -- le
    plus grand disque inscrit dans la lettre, centré sur le squelette.

    ESSAYÉ ET REJETÉ le 03/08/2026 : mesurer plutôt la corde
    PERPENDICULAIRE au trajet, au motif qu'un disque inscrit dans un
    croisement englobe les trois branches. L'idée est juste, le résultat
    est bien pire -- la direction du trajet, estimée sur un squelette
    tramé, se trompe assez souvent de 45° pour que le rayon parte DANS LE
    SENS du trait et mesure sa longueur : des traits à 10 mm là où la
    police en demande 3,8.

    Ce qui a tranché est un BALAYAGE TRAMÉ (le disque promené le long du
    chemin, comparé pixel à pixel à la lettre), et non la somme
    « largeur × longueur » -- celle-ci surestime toujours, puisqu'un trait
    qui tourne se recouvre lui-même et qu'un croisement est compté une fois
    par branche. C'est elle qui m'avait fait croire à un défaut de +40 %
    qui n'existait pas. Au balayage : disque inscrit = 99 % de la lettre
    couverte pour 4 % de débordement ; corde perpendiculaire = 52 à 67 %
    de débordement. Le disque gagne, et de loin."""
    from scipy import ndimage
    return 2.0 * ndimage.distance_transform_edt(b)


# =======================================================================
# C -- TRAÇAGE : DES PIXELS AUX GESTES
# =======================================================================

def _voisins(sq, y, x):
    H, W = sq.shape
    return [(y + dy, x + dx) for dy, dx in _V8
            if 0 <= y + dy < H and 0 <= x + dx < W and sq[y + dy, x + dx]]


def tracer(sq, min_px=3):
    """Chaînes maximales de pixels, d'un nœud au suivant, boucles comprises.

    Un nœud est une extrémité ou une jonction au sens de
    `nombre_transitions`. Une arête déjà parcourue arrête la marche : sans
    cela un cycle (le « o » d'une cursive) fait tourner la boucle sans fin."""
    np = _numpy()
    A = nombre_transitions(sq)
    noeud = sq & (A != 2)
    vus = set()
    chaines = []
    for y0, x0 in zip(*np.nonzero(noeud)):
        y0, x0 = int(y0), int(x0)
        for v in _voisins(sq, y0, x0):
            if (y0, x0) + v in vus:
                continue
            ch, prec, cur = [(y0, x0)], (y0, x0), v
            while True:
                if prec + cur in vus:
                    break
                vus.add(prec + cur)
                vus.add(cur + prec)
                ch.append(cur)
                if noeud[cur]:
                    break
                suite = [n for n in _voisins(sq, *cur) if n != prec]
                if not suite:
                    break
                prec, cur = cur, suite[0]
            if len(ch) >= min_px:
                chaines.append(ch)
    # Boucles pures : sans le moindre nœud, personne ne les a démarrées.
    reste = sq.copy()
    for ch in chaines:
        for y, x in ch:
            reste[y, x] = False
    for y0, x0 in zip(*np.nonzero(reste)):
        y0, x0 = int(y0), int(x0)
        if not reste[y0, x0]:
            continue
        ch, cur = [(y0, x0)], (y0, x0)
        reste[y0, x0] = False
        while True:
            suite = [n for n in _voisins(sq, *cur) if reste[n]]
            if not suite:
                break
            cur = suite[0]
            reste[cur] = False
            ch.append(cur)
        if len(ch) >= min_px:
            # NE REFERMER QUE SI ON EST VRAIMENT REVENU AU DÉPART. La marche
            # gloutonne peut mourir dans une impasse à l'autre bout du mot ;
            # y raccrocher le premier pixel invente un trait droit qui
            # traverse tout, et ce trait EST GRAVÉ. Vu le 03/08/2026 sur
            # « Atelier du Verdier » : une barre continue en travers des
            # dix-huit lettres, que j'ai d'abord prise pour un défaut de
            # l'aperçu.
            if _adjacent(ch[-1], ch[0]):
                ch.append(ch[0])
            chaines.append(ch)
    return _couper_aux_sauts(chaines)


def _adjacent(a, b):
    return abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1


def _couper_aux_sauts(chaines, saut_max=3.0, min_px=3):
    """Coupe toute chaîne là où deux points consécutifs ne se touchent pas.

    L'INVARIANT du traçage : une chaîne est un chemin de pixels VOISINS. Tout
    ce qui suit (rééchantillonnage, lissage, fuseau, G-code) interpole entre
    points consécutifs, donc un seul saut se transforme en trait gravé --
    silencieusement, et d'autant plus visible qu'il est long. Plutôt que de
    faire confiance à chaque producteur de chaînes, on vérifie ici, une fois,
    à la sortie."""
    out = []
    for ch in chaines:
        bout = [ch[0]]
        for a, b in zip(ch, ch[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) > saut_max:
                if len(bout) >= min_px:
                    out.append(bout)
                bout = [b]
            else:
                bout.append(b)
        if len(bout) >= min_px:
            out.append(bout)
    return out


def _direction(ch, depuis_debut, n=6):
    """Direction du bout d'une chaîne, moyennée sur n pixels (le pixel seul
    est trop bruité pour dire où le trait allait)."""
    seg = ch[:n + 1] if depuis_debut else ch[-(n + 1):][::-1]
    if len(seg) < 2:
        return (0.0, 0.0)
    dy = seg[0][0] - seg[-1][0]
    dx = seg[0][1] - seg[-1][1]
    m = math.hypot(dx, dy) or 1.0
    return (dy / m, dx / m)


def coudre(chaines, tol=0.55):
    """Recolle les chaînes qui se PROLONGENT à travers une jonction.

    Une cursive traverse ses propres croisements : le fût du « V » puis la
    liaison vers le « e » sont UN geste, et l'amincissement les coupe en
    deux parce qu'un troisième trait passe par là. Sans couture, la tête
    relève et repique au milieu d'une lettre -- et surtout le fuseau perd sa
    place : lever le Z demande de la LONGUEUR (cf. `longueur_mini_fuseau`),
    donc hacher le trait, c'est raboter les pleins.

    Le critère est la continuité de direction : on joint deux bouts voisins
    si repartir sur le second prolonge le premier plutôt que de rebrousser.
    `tol` est le cosinus minimal ; au-dessous, on préfère deux traits nets à
    un coude inventé."""
    ch = [list(c) for c in chaines]
    encore, garde = True, 0
    while encore and garde <= len(ch) + 5:
        encore = False
        garde += 1
        for i in range(len(ch)):
            if ch[i] is None:
                continue
            for bout_i in (0, 1):
                pi = ch[i][-1] if bout_i else ch[i][0]
                di = _direction(ch[i], bout_i == 0)
                meilleur, score = None, tol
                for j in range(len(ch)):
                    if j == i or ch[j] is None:
                        continue
                    for bout_j in (0, 1):
                        pj = ch[j][-1] if bout_j else ch[j][0]
                        if abs(pi[0] - pj[0]) > 2 or abs(pi[1] - pj[1]) > 2:
                            continue
                        dj = _direction(ch[j], bout_j == 0)
                        s = -(di[0] * dj[0] + di[1] * dj[1])
                        if s > score:
                            meilleur, score = (j, bout_j), s
                if meilleur:
                    j, bout_j = meilleur
                    a = ch[i] if bout_i else ch[i][::-1]
                    b = ch[j][::-1] if bout_j else ch[j]
                    ch[i] = a + b
                    ch[j] = None
                    encore = True
                    break
    # La couture concatène : si l'une des deux moitiés portait un saut, il
    # survit dans le résultat. On repasse donc le même filtre.
    return _couper_aux_sauts([c for c in ch if c])


def _reechantillonner(pts, largeurs, pas):
    """Un point tous les `pas` mm le long de la chaîne, largeur interpolée."""
    np = _numpy()
    d = [0.0]
    for i in range(1, len(pts)):
        d.append(d[-1] + math.hypot(pts[i][0] - pts[i - 1][0],
                                    pts[i][1] - pts[i - 1][1]))
    if d[-1] <= 0.0:
        return [], [], 0.0
    if d[-1] < pas:
        return [pts[0], pts[-1]], [largeurs[0], largeurs[-1]], d[-1]
    s = list(np.arange(0.0, d[-1], pas)) + [d[-1]]
    xs = np.interp(s, d, [p[0] for p in pts])
    ys = np.interp(s, d, [p[1] for p in pts])
    ls = np.interp(s, d, largeurs)
    return list(zip(xs, ys)), list(ls), d[-1]


# =======================================================================
# D -- POINT D'ENTRÉE
# =======================================================================

def chaines_calligraphie(chemin_police, texte, largeur_mm=None,
                         hauteur_mm=None, em_px=EM_PX, lissage_mm=LISSAGE_MM,
                         min_chaine_mm=MIN_CHAINE_MM, pas_arc_mm=PAS_ARC_MM):
    """Le texte, prêt à graver : des gestes en millimètres, largeur comprise.

    Renvoie `(chaines, infos)`. Une chaîne est une liste de triplets
    `(x_mm, y_mm, largeur_mm)`, dans le repère CNC (Y vers le HAUT, origine
    en bas à gauche du texte). `infos` porte les dimensions et les largeurs
    extrêmes que la POLICE demande -- c'est à l'appelant de confronter cela
    à ce que le matériau sait faire.

    La taille se donne par `largeur_mm` OU `hauteur_mm` ; l'autre suit, les
    proportions de la police n'étant pas négociables."""
    np = _numpy()
    from scipy import ndimage

    b = rendre_texte(chemin_police, texte, em_px=em_px)
    H, W = b.shape
    if largeur_mm and largeur_mm > 0:
        mm_px = float(largeur_mm) / float(W)
    elif hauteur_mm and hauteur_mm > 0:
        mm_px = float(hauteur_mm) / float(H)
    else:
        raise ErreurCalligraphie(
            "Donne une largeur ou une hauteur de texte en mm.")

    larg_px = largeur_locale(b)
    sq = amincir(b)
    if not sq.any():
        raise ErreurCalligraphie("Rien à graver : le texte rendu est vide.")

    brutes = coudre(tracer(sq, min_px=3))
    fenetre = max(3, int(round(lissage_mm / max(pas_arc_mm, 1e-6))))
    chaines, w_min, w_max, longueur = [], float("inf"), 0.0, 0.0
    for ch in brutes:
        # Repère CNC : Y vers le haut, alors que la ligne 0 de l'image est
        # en haut. Sans ce retournement le texte sortirait en miroir.
        pts = [(x * mm_px, (H - 1 - y) * mm_px) for y, x in ch]
        lar = [larg_px[y, x] * mm_px for y, x in ch]
        p2, l2, lg = _reechantillonner(pts, lar, pas_arc_mm)
        if len(p2) < 2 or lg < min_chaine_mm:
            continue
        if len(l2) >= 5:
            l2 = list(ndimage.uniform_filter1d(
                np.array(l2), size=fenetre, mode="nearest"))
        chaines.append([(float(x), float(y), float(w))
                        for (x, y), w in zip(p2, l2)])
        w_min = min(w_min, min(l2))
        w_max = max(w_max, max(l2))
        longueur += lg
    if not chaines:
        raise ErreurCalligraphie(
            "Aucun trait assez long à cette taille -- agrandis le texte.")
    infos = {
        "largeur_mm": W * mm_px,
        "hauteur_mm": H * mm_px,
        "mm_px": mm_px,
        "largeur_trait_min": w_min,
        "largeur_trait_max": w_max,
        "rapport": w_max / max(w_min, 1e-9),
        "n_chaines": len(chaines),
        "longueur_mm": longueur,
    }
    return chaines, infos
