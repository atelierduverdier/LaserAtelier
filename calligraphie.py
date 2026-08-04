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

# Fenêtre de l'OUVERTURE morphologique du profil de largeur, en mm de
# trajet. Elle rabote les renflements plus COURTS qu'elle -- typiquement la
# bosse d'un croisement, où le disque inscrit tient toute la jonction -- en
# laissant intact le galbe d'un plein, qui s'étale sur des millimètres.
# Réglée sur mesure le 04/08/2026 : à 2,8 mm, le saut de largeur médian d'un
# point au suivant tombe de 0,45 à 0,30 mm sur « Swirly Canalope » et de
# 0,34 à 0,23 sur Blacksword, pour un point de couverture. Plus large
# lisserait davantage mais amaigrirait les pleins.
OUVERTURE_MM = 2.8

# Élagage des BARBES de l'amincissement. Une barbe est un appendice à
# extrémité libre, greffé sur un trait, et si court qu'il tient dans
# l'épaisseur de ce trait : le graver ne dépose pas un point d'encre de plus,
# puisque le disque du trait porteur couvre déjà tout son parcours. On la
# mesure donc EN MULTIPLE DE LA LARGEUR LOCALE, pas en millimètres absolus.
#
# Le seuil absolu d'avant (0,8 mm) jetait tout ce qui était court, y compris
# ce qui n'était pas une barbe : sur « La Graziela Script Demo », 89 chaînes
# sur 158 -- dont LES DEUX POINTS DES « i », qui sont des taches d'encre à
# part entière. Christophe, 04/08/2026, comparaison à l'appui : « il y a des
# coupures dans la tienne ».
BARBE_MAX_LARGEURS = 1.0

# Un trait ISOLÉ (ses deux bouts libres, aucune jonction) n'est jamais une
# barbe : c'est un point d'i, un accent, une ponctuation, une virgule de
# liaison. On le garde quelle que soit sa longueur -- mais on refuse le
# résidu d'un pixel, qui ne dessine rien.
MIN_TRAIT_ISOLE_MM = 0.15

# UN GESTE PLUS COURT QUE LA MOITIÉ DE SA PROPRE LARGEUR N'EST PAS UN TRAIT.
# Le disque du trait dans lequel il se trouve a déjà couvert tout son
# parcours : le graver ne dépose rien de plus, et coûte un relevage, un
# transit et une plongée. Mesuré le 04/08/2026 sur « Atelier du Verdier » à
# 200 mm : les élaguer retire 62 gestes sur La Graziela et 158 sur
# Blacksword, pour 0,50 et 0,33 point de couverture -- du trajet à vide
# contre rien.
#
# C'est aussi ce qui interdit le geste de longueur NULLE, dont il y avait
# 19 : un G1 immobile faisceau allumé ne grave RIEN (le HAL ramène la
# puissance à zéro à l'arrêt), donc il aurait coûté deux mouvements pour
# une marque inexistante.
GESTE_MINI_EN_LARGEURS = 0.5

# Pas d'échantillonnage du trait le long du chemin, en mm.
PAS_ARC_MM = 0.4

# Part MINIMALE d'encre neuve pour qu'un geste vaille d'être gravé. Un geste
# dont le disque tombe entièrement dans ce qu'un autre a déjà brûlé ne dépose
# rien : il coûte un relevage, un transit, une plongée, et laisse DEUX
# terminaisons franches de plus au milieu d'un plein.
#
# Le seuil ne se choisit pas au goût, il se lit dans la mesure. Sur « Atelier
# du Verdier », l'apport de chaque geste se répartit en deux tas séparés par
# un fossé : d'un côté 0 %, de l'autre 10 % et plus. Jeter à 2 %, à 5 % ou à
# 10 % retire EXACTEMENT le même lot sur trois polices sur quatre -- La
# Graziela, Swirly Canalope, Byliner. 5 % tombe au milieu du plateau.
APPORT_MINI = 0.05

# SOUDURE des bouts qui se touchent presque, en multiple de la largeur locale.
# `parcourir` apparie nœud par nœud, donc deux jonctions voisines laissent
# chacune pendre une branche, et les deux bouts se retrouvent à un ou deux
# pixels l'un de l'autre sans jamais se voir. La tête relève, transite et
# replonge AU MÊME ENDROIT : ce demi-millimètre est brûlé deux fois, avec deux
# arrêts en prime, et il ressort en pâté noir. Quatorze de ces amas sur les
# cinquante extrémités de « Atelier du Verdier ».
#
# Le seuil est proportionnel -- l'écart doit tenir dans la largeur de l'encre
# à cet endroit -- donc insensible à la taille du texte. Balayé sur La
# Graziela : 0,5 donne 26 gestes, 1,0 et 1,5 en donnent 22, 2,0 en donne 21,
# à couverture et débordement inchangés (97,3 % et 18,2 %). On prend le début
# du plateau.
SOUDURE_EN_LARGEURS = 1.0

# FUSION des jonctions, en multiple du RAYON de l'encre. Deux traits qui se
# croisent de biais ne donnent pas un nœud à quatre branches mais deux nœuds
# à trois, reliés par un pont d'un ou deux pixels : c'est ce pont qui permet
# à l'appariement de coudre une branche à la mauvaise et de couper un trait
# en son milieu. Au-delà du rayon du disque inscrit, le « pont » est un vrai
# morceau de lettre et doit le rester.
FUSION_EN_LARGEURS = 1.0

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
        # MARCHER DES DEUX CÔTÉS. Le germe est pris dans l'ordre de balayage
        # de l'image, donc presque jamais à un bout : ne partir que dans un
        # sens coupait en deux tout ce que cette branche ramasse -- et elle
        # ramasse la MOITIÉ du squelette (2 235 px sur 4 709 pour
        # « Atelier »), puisque toute boucle fermée est sans nœud.
        #
        # Chaque coupure de trop est DEUX terminaisons de plus, et une
        # terminaison au milieu d'un plein se grave en pâté : la tête se
        # lève à pleine largeur. Christophe, 04/08/2026, dix-sept pâtés
        # entourés en rouge sur sa gravure -- 23 % des extrémités tombaient
        # là où le trait fait plus de 0,5 mm.
        reste[y0, x0] = False
        moities = []
        for _ in (0, 1):
            bout, cur = [], (y0, x0)
            while True:
                suite = [n for n in _voisins(sq, *cur) if reste[n]]
                if not suite:
                    break
                cur = suite[0]
                reste[cur] = False
                bout.append(cur)
            moities.append(bout)
        ch = moities[1][::-1] + [(y0, x0)] + moities[0]
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


# ==========================================================================
# LE SQUELETTE COMME GRAPHE : un geste par trait, pas un par morceau
# ==========================================================================
# Quatre approches ont échoué avant celle-ci, toutes pour la même raison :
# on optimisait un parcours sur une structure qu'on n'avait pas comptée.
# D'où deux INVARIANTS vérifiés avant tout usage, et non après :
#   1. couverture -- chaque pixel du squelette est dans exactement une arête ;
#   2. continuité -- deux points consécutifs d'une arête sont voisins.
#
# Ce qui ne marche PAS, et qui semble pourtant naturel : retirer les pixels
# de jonction et laisser les composantes connexes séparer les arêtes. Un
# squelette est 8-connexe, donc les deux pixels de part et d'autre d'un nœud
# restent voisins EN DIAGONALE : rien n'est séparé, et les « arêtes »
# obtenues sont des paquets qu'aucun ordre ne range -- sauts jusqu'à 222 px
# (mesuré le 04/08/2026). Il faut passer par le graphe des PIXELS.
ORTHO = [(-1, 0), (0, 1), (1, 0), (0, -1)]
DIAG = [(-1, 1), (1, 1), (1, -1), (-1, -1)]


def adjacence(sq):
    np = _numpy()
    """pixel -> voisins, DIAGONALES REDONDANTES ÔTÉES.

    Si A et B se touchent en diagonale mais partagent un voisin orthogonal
    dans le squelette, le chemin A-C-B existe déjà : garder A-B en plus
    donne un triangle, donc un pixel de degré 3 là où le trait est droit --
    une fausse jonction, et une miette de plus à chaque escalier."""
    H, W = sq.shape
    adj = {}
    pix = [(int(y), int(x)) for y, x in zip(*np.nonzero(sq))]
    ens = set(pix)
    for p in pix:
        y, x = p
        v = []
        for dy, dx in ORTHO:
            q = (y + dy, x + dx)
            if q in ens:
                v.append(q)
        for dy, dx in DIAG:
            q = (y + dy, x + dx)
            if q not in ens:
                continue
            # un voisin orthogonal commun rendrait cette diagonale inutile
            if (y + dy, x) in ens or (y, x + dx) in ens:
                continue
            v.append(q)
        adj[p] = v
    return adj


def fusionner_jonctions(aretes, larg_px, k_largeurs=FUSION_EN_LARGEURS):
    """Recolle les jonctions qu'un MÊME disque d'encre contient.

    UN CROISEMENT N'EST PAS DEUX JONCTIONS. Quand deux traits se croisent de
    biais -- et une cursive n'est faite que de ça -- l'amincissement ne peut
    pas produire un nœud à quatre branches : il en fabrique DEUX à trois
    branches, reliés par un pont d'un ou deux pixels. `parcourir` apparie
    nœud par nœud ; à chacun des deux il marie deux branches sur trois, et
    rien ne l'empêche de coudre « barre-gauche + pont + fût-bas ».

    Le résultat est un V là où il fallait deux traits droits, et les deux
    autres branches restent pendantes. Mesuré sur un simple X de deux barres :
    4 gestes au lieu de 2, dont un qui rebrousse (`droit = -0,00`) et deux
    moitiés qui s'arrêtent pile au centre. Christophe, 04/08/2026, capture
    annotée 1-2-3 : « pour le t le 3e est coupé en son centre, normalement on
    trace une ligne 1 puis 2 puis 3 ».

    Le critère est physique et proportionnel : les deux points de branchement
    tiennent dans le même disque inscrit, donc leur écart est plus petit que
    le RAYON de l'encre à cet endroit. Le pont n'est alors pas un morceau de
    lettre, c'est un artefact de tramage.

    On ne supprime pas le pont : on l'AJOUTE à chaque branche du second nœud,
    qui se termine alors sur le premier. Les chaînes restent continues, donc
    l'invariant « une chaîne ne saute jamais » vaut encore, et aucun pixel du
    squelette ne disparaît."""
    ar = [list(a) for a in aretes]
    for _passe in range(len(ar) + 5):
        deg = {}
        for a in ar:
            deg[a[0]] = deg.get(a[0], 0) + 1
            deg[a[-1]] = deg.get(a[-1], 0) + 1
        pont = None
        for i, a in enumerate(ar):
            n1, n2 = a[0], a[-1]
            if n1 == n2 or deg.get(n1, 0) < 3 or deg.get(n2, 0) < 3:
                continue
            lg = sum(math.hypot(q[0] - p[0], q[1] - p[1])
                     for p, q in zip(a, a[1:]))
            rayon = 0.5 * float(larg_px[n1[0], n1[1]])
            if lg <= k_largeurs * rayon:
                pont = (i, n1, n2, a)
                break
        if pont is None:
            break
        i, n1, n2, a = pont
        for j, b in enumerate(ar):
            if j == i:
                continue
            # Toute branche qui aboutit sur n2 se prolonge par le pont
            # jusqu'à n1 : les deux nœuds n'en font plus qu'un.
            if b[-1] == n2:
                ar[j] = b + a[::-1][1:]
            elif b[0] == n2:
                ar[j] = a[:-1] + b
        del ar[i]
    return ar


def construire(sq):
    """(aretes, cycles, rapport). Une arête = liste de pixels, bout à bout."""
    np = _numpy()
    adj = adjacence(sq)
    noeuds = {p for p, v in adj.items() if len(v) != 2}
    aretes, vus = [], set()
    for n in noeuds:
        for v in adj[n]:
            if (n, v) in vus:
                continue
            chem, prec, cur = [n], n, v
            while True:
                vus.add((prec, cur))
                vus.add((cur, prec))
                chem.append(cur)
                if cur in noeuds:
                    break
                suite = [w for w in adj[cur] if w != prec]
                if not suite:
                    break
                prec, cur = cur, suite[0]
            aretes.append(chem)
    # cycles purs : que des pixels de degré 2, aucun nœud pour les amorcer
    restants = set(adj) - {p for a in aretes for p in a}
    cycles = []
    while restants:
        depart = next(iter(restants))
        cyc, cur, prec = [depart], depart, None
        restants.discard(depart)
        while True:
            suite = [w for w in adj[cur] if w != prec and w in restants]
            if not suite:
                break
            prec, cur = cur, suite[0]
            restants.discard(cur)
            cyc.append(cur)
        if len(cyc) >= 3:
            cyc.append(cyc[0])          # un cycle se referme
            cycles.append(cyc)
    # --- LES DEUX INVARIANTS ---
    couverts = {p for a in aretes for p in a} | {p for c in cycles for p in c}
    tous = set(adj)
    saut_max = 0.0
    for a in aretes + cycles:
        for p, q in zip(a, a[1:]):
            saut_max = max(saut_max, math.hypot(q[0] - p[0], q[1] - p[1]))
    rapport = {
        "squelette": len(tous), "couverts": len(couverts & tous),
        "manquants": len(tous - couverts), "saut_max": saut_max,
        "noeuds": len(noeuds), "aretes": len(aretes), "cycles": len(cycles),
    }
    return aretes, cycles, rapport


def _direction(ch, depuis_debut, n=6):
    """Direction du bout d'une chaîne, moyennée sur n pixels (le pixel seul
    est trop bruité pour dire où le trait allait).

    IL N'Y EN A QU'UNE. Le module en a porté DEUX du même nom pendant trois
    versions -- celle-ci et une jumelle en n=8 écrite pour `parcourir` -- et
    c'est la seconde définition rencontrée qui gagne en Python : `parcourir`
    tournait donc en n=6 sans que sa signature le dise. Les mesures qui ont
    validé le parcours de graphe ont été prises ainsi ; on garde n=6."""
    seg = ch[:n + 1] if depuis_debut else ch[-(n + 1):][::-1]
    if len(seg) < 2:
        return (0.0, 0.0)
    dy = seg[0][0] - seg[-1][0]
    dx = seg[0][1] - seg[-1][1]
    m = math.hypot(dx, dy) or 1.0
    return (dy / m, dx / m)


def _pixels_entre(p, q):
    """Les pixels du segment droit ouvert ]p, q[, un par pas d'un pixel.

    Sert à REMPLIR un raccord : la chaîne cousue reste continue, donc
    l'invariant « une chaîne ne saute jamais » vaut encore après soudure."""
    n = max(1, int(round(math.hypot(q[0] - p[0], q[1] - p[1]))))
    return [(int(round(p[0] + (q[0] - p[0]) * t / n)),
             int(round(p[1] + (q[1] - p[1]) * t / n))) for t in range(1, n)]


def parcourir(aretes, cycles):
    """Les arêtes enchaînées en GESTES, en traversant les jonctions tout droit.

    À chaque nœud, les bouts d'arête sont appariés deux à deux par continuité
    de direction : celui qui repart le plus droit prolonge le geste. Le
    nombre de gestes n'est alors plus décidé par l'ordre de balayage mais par
    le graphe lui-même -- c'est ce qu'on cherchait."""
    bouts = {}
    for i, a in enumerate(aretes):
        bouts.setdefault(a[0], []).append((i, 0))
        bouts.setdefault(a[-1], []).append((i, 1))
    paire = {}
    for _pt, lst in bouts.items():
        libres = list(lst)
        while len(libres) >= 2:
            best = None
            for p in range(len(libres)):
                for q in range(p + 1, len(libres)):
                    dp = _direction(aretes[libres[p][0]], libres[p][1] == 0)
                    dq = _direction(aretes[libres[q][0]], libres[q][1] == 0)
                    sc = -(dp[0] * dq[0] + dp[1] * dq[1])
                    if best is None or sc > best[0]:
                        best = (sc, p, q)
            if best is None:
                break
            _s, p, q = best
            paire[libres[p]] = libres[q]
            paire[libres[q]] = libres[p]
            for k in sorted((p, q), reverse=True):
                libres.pop(k)

    faits, gestes = set(), []

    def marcher(i, sens):
        g = []
        while i not in faits:
            faits.add(i)
            a = aretes[i] if sens == 0 else aretes[i][::-1]
            g.extend(a if not g else a[1:])
            nxt = paire.get((i, 1 - sens))
            if nxt is None or nxt[0] in faits:
                break
            i, sens = nxt
        return g

    for i in range(len(aretes)):
        for b in (0, 1):
            if i not in faits and (i, b) not in paire:
                g = marcher(i, b)
                if len(g) >= 2:
                    gestes.append(g)
    for i in range(len(aretes)):
        if i not in faits:
            g = marcher(i, 0)
            if len(g) >= 2:
                gestes.append(g)
    return gestes + [list(c) for c in cycles]


def souder(gestes, encre, larg_px, k_largeurs=SOUDURE_EN_LARGEURS,
           cos_mini=0.0):
    """Recolle deux gestes dont les bouts se touchent presque.

    `parcourir` apparie les branches NŒUD PAR NŒUD : à une jonction de trois
    branches il en marie deux et laisse la troisième pendre. Quand deux
    jonctions sont voisines -- ce qui est la règle à un croisement de cursive,
    l'amincissement y fabrique un petit pont -- chacune laisse son bout
    pendre, et les deux bouts se retrouvent à un ou deux pixels l'un de
    l'autre sans jamais se voir, puisqu'ils appartiennent à deux nœuds
    différents.

    Ce qui en sort n'est pas seulement un geste de trop : la tête relève,
    transite, replonge et repart AU MÊME ENDROIT. Ce demi-millimètre est donc
    brûlé DEUX FOIS, avec en prime deux arrêts, et il ressort en pâté noir.
    Christophe, 04/08/2026, photo de la gravure encadrée en rouge : « je
    pense qu'il y a trop de puissance ou on ne va pas assez vite dans
    certains endroits » -- quatorze de ces amas sur les cinquante extrémités.

    Trois conditions, dans cet ordre :

    * l'écart tient dans la LARGEUR DE L'ENCRE à cet endroit (`k_largeurs`) --
      un critère proportionnel, donc insensible à la taille du texte ;
    * le segment droit du raccord reste ENTIÈREMENT DANS L'ENCRE. C'est le
      garde-fou : sans lui, refermer une chaîne sur un bout lointain a déjà
      gravé un trait droit en travers des dix-huit lettres du mot ;
    * repartir sur le second prolonge le premier plutôt que de rebrousser
      (`cos_mini`).

    Le raccord est rempli par ses pixels intermédiaires, si bien que la chaîne
    reste continue : l'invariant « une chaîne ne saute jamais » vaut encore à
    la sortie."""
    ch = [list(g) for g in gestes]
    H, W = encre.shape

    def dans_encre(p, q):
        for y, x in _pixels_entre(p, q) + [q]:
            if not (0 <= y < H and 0 <= x < W) or not encre[y, x]:
                return False
        return True

    encore, garde = True, 0
    while encore and garde <= len(ch) + 5:
        encore, garde = False, garde + 1
        cands = []
        for i in range(len(ch)):
            if ch[i] is None:
                continue
            for bi in (0, 1):
                pi = ch[i][-1] if bi else ch[i][0]
                di = _direction(ch[i], bi == 0)
                for j in range(i + 1, len(ch)):
                    if ch[j] is None:
                        continue
                    for bj in (0, 1):
                        pj = ch[j][-1] if bj else ch[j][0]
                        d = math.hypot(pi[0] - pj[0], pi[1] - pj[1])
                        if d > k_largeurs * larg_px[pi[0], pi[1]]:
                            continue
                        dj = _direction(ch[j], bj == 0)
                        s = -(di[0] * dj[0] + di[1] * dj[1])
                        if s < cos_mini or not dans_encre(pi, pj):
                            continue
                        cands.append((-s, d, i, bi, j, bj))
        cands.sort()
        pris = set()
        for _s, _d, i, bi, j, bj in cands:
            if i in pris or j in pris:
                continue
            a = ch[i] if bi else ch[i][::-1]
            b = ch[j][::-1] if bj else ch[j]
            ch[i] = a + _pixels_entre(a[-1], b[0]) + b
            ch[j] = None
            pris.add(i)
            pris.add(j)
            encore = True
    return [c for c in ch if c]


# Échelle du contrôle de couverture. Dessiner quarante mille disques à la
# résolution du rendu coûtait 25 s par mot -- inacceptable pour un verdict
# qui se recalcule à la frappe. Un trou qui compte fait 150 px et plus : au
# tiers, il en fait encore 17, largement de quoi être vu. On paie neuf fois
# moins de pixels pour la même décision.
ECHELLE_CONTROLE = 3


def couverture(encre, chaines_mm, mm_px, hauteur_mm, echelle=ECHELLE_CONTROLE):
    """Le masque de ce que les gestes déposeraient réellement, à l'échelle
    réduite `echelle` (1 = pleine résolution)."""
    from PIL import Image, ImageDraw
    np = _numpy()
    H, W = encre.shape
    k = float(max(1, int(echelle)))
    im = Image.new("L", (max(1, int(W / k)), max(1, int(H / k))), 0)
    d = ImageDraw.Draw(im)
    for c in chaines_mm:
        for (x0, y0, w0), (x1, y1, w1) in zip(c, c[1:]):
            X0, Y0 = x0 / mm_px / k, (hauteur_mm - y0) / mm_px / k
            X1, Y1 = x1 / mm_px / k, (hauteur_mm - y1) / mm_px / k
            d.line([X0, Y0, X1, Y1], fill=255,
                   width=max(1, int(round(0.5 * (w0 + w1) / mm_px / k))))
            r = 0.5 * max(w0, w1) / mm_px / k
            d.ellipse([X1 - r, Y1 - r, X1 + r, Y1 + r], fill=255)
        x, y, w = c[0]
        X, Y, r = x / mm_px / k, (hauteur_mm - y) / mm_px / k, 0.5 * w / mm_px / k
        d.ellipse([X - r, Y - r, X + r, Y + r], fill=255)
    return np.array(im) > 127


def encre_oubliee(encre, couvert, mini_px=6, echelle=ECHELLE_CONTROLE):
    """Les régions d'`encre` qu'AUCUN geste ne couvre, rendues chacune par un
    court trait le long de son grand axe.

    L'appelant choisit l'encre qu'il soumet, et c'est là que se joue tout le
    sens de cette fonction. Elle a d'abord servi l'encre ENTIÈRE, pour
    réparer les « coupures dans les lettres » : l'axe médian s'arrête à une
    demi-largeur de l'extrémité d'un trait effilé, le plus grand disque
    inscrit ne pouvant pas aller plus loin. Le parcours de graphe (v2.65.0) a
    supprimé ces coupures à leur source, et servir toute l'encre s'est mis à
    coûter bien plus qu'il ne rapportait : sur « Atelier du Verdier », 24
    comblements sur 27 tombaient DANS une lettre déjà tracée, en petits
    traits épars le long des jonctions. Christophe, 04/08/2026, capture
    surlignée à l'appui : « ces petits tracés ne vont pas [...] il faut juste
    le squelette de la lettre et bien sûr les points sur les i et accents ».

    On ne lui soumet donc plus que les TACHES DÉTACHÉES -- point d'un i,
    accent, ponctuation, virgule : une composante d'encre que le squelette ne
    touche nulle part, donc dont aucune chaîne ne peut sortir.

    Plutôt que de deviner la topologie, on regarde CE QUI RESTE : l'encre
    non couverte. C'est la même façon de juger que le balayage qui a tranché
    la question de la largeur -- on compare au dessin, pas au raisonnement.
    """
    np = _numpy()
    from scipy import ndimage
    k = max(1, int(echelle))
    petit = encre[::k, ::k]
    h, w = min(petit.shape[0], couvert.shape[0]), min(petit.shape[1], couvert.shape[1])
    manque = petit[:h, :w] & ~couvert[:h, :w]
    if not manque.any():
        return []
    lab, n = ndimage.label(manque)
    dist = ndimage.distance_transform_edt(encre)
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < mini_px:
            continue                       # frange d'un pixel : sans objet
        ys, xs = ys * k, xs * k            # retour à la pleine résolution
        larg = 2.0 * dist[ys, xs].max()
        if larg <= 1.0:
            continue
        cy, cx = float(ys.mean()), float(xs.mean())
        dy, dx = ys - cy, xs - cx
        cov = np.array([[float((dy * dy).mean()), float((dy * dx).mean())],
                        [float((dy * dx).mean()), float((dx * dx).mean())]])
        vals, vecs = np.linalg.eigh(cov)
        # PAS `k` : c'est le facteur de réduction, utilisé juste au-dessus
        # pour revenir en pleine résolution. L'écraser avec un indice de
        # valeur propre faisait lire toutes les régions SUIVANTES aux
        # mauvaises coordonnées (multipliées par 0 ou 1 au lieu de 3), donc
        # hors de l'encre, donc rejetées : sur « Swirly Canalope », les deux
        # points des « i » -- 3347 px chacun, dûment détectés comme non
        # gravés -- disparaissaient à cette ligne-là.
        j = int(np.argmax(vals))
        v = vecs[:, j]
        demi = max(float(np.sqrt(max(vals[j], 0.0))), 0.6 * larg)
        out.append(([(int(round(cy - v[0] * demi)), int(round(cx - v[1] * demi))),
                     (int(round(cy + v[0] * demi)), int(round(cx + v[1] * demi)))],
                    larg))
    return out


def gestes_utiles(encre, chaines_mm, mm_px, hauteur_mm,
                  apport_mini=APPORT_MINI, echelle=ECHELLE_CONTROLE):
    """Les gestes qui déposent de l'encre qu'aucun autre ne dépose déjà.

    On les passe du plus long au plus court -- le trait de la lettre d'abord,
    le résidu ensuite -- en cumulant ce qui est brûlé. Un geste dont moins de
    `apport_mini` de l'empreinte est neuve ne grave rien de plus.

    Ce sont les petits ponts que l'amincissement laisse entre deux jonctions
    voisines, longs de 0,04 à 0,5 mm : sur Blacksword ils font 30 des 66
    gestes. Renvoie la liste filtrée DANS SON ORDRE D'ORIGINE."""
    np = _numpy()
    from PIL import Image
    if not chaines_mm:
        return []
    vide = couverture(encre, [], mm_px, hauteur_mm, echelle=echelle)
    petit = Image.fromarray((np.asarray(encre) > 0).astype(np.uint8) * 255)
    enc = np.array(petit.resize((vide.shape[1], vide.shape[0]))) > 127
    cumul = np.zeros_like(vide)
    gardes = set()
    ordre = sorted(range(len(chaines_mm)),
                   key=lambda i: -_longueur_chaine(chaines_mm[i]))
    for i in ordre:
        propre = couverture(encre, [chaines_mm[i]], mm_px, hauteur_mm,
                            echelle=echelle) & enc
        total = int(propre.sum())
        if total and float((propre & ~cumul).sum()) / total < apport_mini:
            continue
        gardes.add(i)
        cumul |= propre
    return [c for i, c in enumerate(chaines_mm) if i in gardes]


def _longueur_chaine(chaine):
    """Longueur parcourue, en mm, d'une chaîne de triplets (x, y, largeur)."""
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(chaine, chaine[1:]))


def taches_sans_geste(encre, couvert, echelle=ECHELLE_CONTROLE):
    """Les composantes d'encre qu'AUCUN geste ne touche, même en partie.

    C'est la définition exacte de ce qu'un tracé de squelette n'a pas su
    servir : un point d'i, un accent, une virgule de ponctuation. Tout le
    reste de l'encre appartient à une lettre que les gestes parcourent déjà,
    et n'a donc rien à recevoir en plus.

    Le critère est la COUVERTURE, pas la présence d'un squelette. Une tache
    détachée porte bel et bien un squelette -- un ou deux pixels -- mais trop
    court pour donner une arête qui survive au parcours : sur « Swirly
    Canalope » les deux points des « i » font 3347 px chacun et le squelette
    les touche, alors qu'aucun geste n'en sort. Juger sur le squelette les
    aurait déclarés servis et laissés nus.

    Renvoie un masque booléen de la taille de `encre`."""
    np = _numpy()
    from scipy import ndimage
    lab, n = ndimage.label(encre > 0, np.ones((3, 3), dtype=bool))
    if n == 0:
        return np.zeros(encre.shape, dtype=bool)
    k = max(1, int(echelle))
    ys, xs = np.nonzero(couvert)
    servies = np.zeros(n + 1, dtype=bool)
    if len(ys):
        # `couvert` est à l'échelle réduite : chaque pixel couvert désigne un
        # bloc k x k de l'encre, dont il suffit de lire le coin.
        yy = np.clip(ys * k, 0, encre.shape[0] - 1)
        xx = np.clip(xs * k, 0, encre.shape[1] - 1)
        servies[lab[yy, xx]] = True
    servies[0] = True                       # le fond n'est pas une tache
    return (lab > 0) & ~servies[lab]


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

def _bouts_libres(sq, chaine):
    """Combien des deux bouts de cette chaîne sont des extrémités LIBRES.

    2 = trait isolé (rien d'autre ne s'y raccroche) ; 1 = appendice greffé
    sur un trait, donc candidat au statut de barbe ; 0 = morceau tendu entre
    deux jonctions, jamais une barbe."""
    n = 0
    for bout in (chaine[0], chaine[-1]):
        if len(_voisins(sq, *bout)) <= 1:
            n += 1
    return n


def chaines_calligraphie(chemin_police, texte, largeur_mm=None,
                         hauteur_mm=None, em_px=EM_PX, lissage_mm=LISSAGE_MM,
                         min_chaine_mm=None, pas_arc_mm=PAS_ARC_MM):
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

    # Le graphe, pas le ramassage : 136 gestes -> 48 sur « Atelier du
    # Verdier » en Swirly Canalope, 151 -> 29 en La Graziela, 239 -> 68 en
    # Blacksword, à couverture 100 % et sans un seul saut. Chaque geste en
    # moins, c'est deux terminaisons franches en moins -- et une terminaison
    # au milieu d'un plein se grave en pâté.
    _ar, _cy, _rap = construire(sq)
    # UN CROISEMENT D'ABORD, DEUX JONCTIONS ENSUITE. Fusionner les nœuds
    # qu'un même disque d'encre contient rend au parcours le vrai degré du
    # croisement, sans quoi il coupe un trait en son milieu. La soudure
    # rattrape ensuite ce qui reste pendant.
    _ar = fusionner_jonctions(_ar, larg_px)
    brutes = souder(parcourir(_ar, _cy), b > 0, larg_px)
    fenetre = max(3, int(round(lissage_mm / max(pas_arc_mm, 1e-6))))
    chaines, w_min, w_max, longueur = [], float("inf"), 0.0, 0.0
    for ch in brutes:
        ch_orig = ch
        # Repère CNC : Y vers le haut, alors que la ligne 0 de l'image est
        # en haut. Sans ce retournement le texte sortirait en miroir.
        pts = [(x * mm_px, (H - 1 - y) * mm_px) for y, x in ch]
        lar = [larg_px[y, x] * mm_px for y, x in ch]
        p2, l2, lg = _reechantillonner(pts, lar, pas_arc_mm)
        if len(p2) < 2:
            continue
        # BARBE OU TRAIT ? Un trait isolé se garde (point d'i, accent) ; un
        # appendice ne se jette que s'il tient dans l'épaisseur de ce sur
        # quoi il est greffé.
        libres = _bouts_libres(sq, ch_orig)
        if libres >= 2:
            if lg < MIN_TRAIT_ISOLE_MM:
                continue
        elif libres == 1:
            epaisseur = max(lar) if lar else 0.0
            seuil = max(BARBE_MAX_LARGEURS * epaisseur,
                        min_chaine_mm or 0.0)
            if lg < seuil:
                continue
        # Le zéro absolu d'abord : une chaîne de largeur nulle échapperait
        # à la règle proportionnelle (0 < 0.5 x 0 est faux) et sortirait un
        # G1 immobile, qui ne grave rien.
        # Un point d'i est PLUS COURT QUE LARGE par définition : la règle
        # du geste mini ne vaut que pour ce qui est greffé sur un trait,
        # dont l'encre est déjà déposée par le porteur. Un trait isolé n'a
        # pas de porteur.
        if lg <= 1e-9 or (libres < 2 and
                          lg < GESTE_MINI_EN_LARGEURS * (max(l2) if l2 else 0.0)):
            continue
        if len(l2) >= 5:
            # OUVERTURE d'abord, moyenne ensuite. Le disque inscrit ENFLE à
            # un croisement -- il y tient toute la jonction, pas le trait --
            # et la largeur y bondissait de 0,63 mm d'un point au suivant,
            # 0,4 mm plus loin. À la gravure cela fait des renflements le
            # long du trait ; Christophe, 04/08/2026 : « les traits ont
            # l'apparence de petits boudins ».
            #
            # Une ouverture (érosion puis dilatation) supprime les pics plus
            # ÉTROITS que sa fenêtre en laissant le galbe intact : c'est
            # exactement la distinction voulue entre une bosse de jonction,
            # brève, et un plein de calligraphie, qui s'étale sur des
            # millimètres. La moyenne qui suit ne fait plus qu'adoucir.
            arr = np.array(l2)
            ouv = max(3, int(round(OUVERTURE_MM / max(pas_arc_mm, 1e-6))))
            arr = ndimage.grey_opening(arr, size=ouv, mode="nearest")
            l2 = list(ndimage.uniform_filter1d(arr, size=fenetre,
                                               mode="nearest"))
        chaines.append([(float(x), float(y), float(w))
                        for (x, y), w in zip(p2, l2)])
    # LES TACHES DÉTACHÉES, et rien d'autre : point d'i, accent, ponctuation.
    # Une composante d'encre qu'aucun geste ne touche ne peut rien recevoir
    # d'autre ; tout le reste appartient à une lettre déjà parcourue. Servir
    # l'encre entière, comme on le faisait avant le parcours de graphe,
    # semait de petits traits épars le long des jonctions -- 24 sur 27
    # comblements sur « La Graziela ».
    hauteur_totale = (H - 1) * mm_px
    chaines = gestes_utiles(b, chaines, mm_px, hauteur_totale)
    couvert = couverture(b, chaines, mm_px, hauteur_totale)
    for pts_px, larg_px_tache in encre_oubliee(taches_sans_geste(b, couvert),
                                               couvert):
        pts = [(x * mm_px, (H - 1 - y) * mm_px) for y, x in pts_px]
        w = larg_px_tache * mm_px
        p2, l2, lg = _reechantillonner(pts, [w, w], pas_arc_mm)
        if len(p2) < 2:
            p2, l2 = pts, [w, w]
            lg = math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
        if lg <= 1e-9:
            # Tache trop petite pour porter un axe : la graver reviendrait à
            # un G1 immobile, qui ne marque rien et coûte deux mouvements.
            continue
        chaines.append([(float(x), float(y), float(ww))
                        for (x, y), ww in zip(p2, l2)])

    if not chaines:
        raise ErreurCalligraphie(
            "Aucun trait assez long à cette taille -- agrandis le texte.")
    # LES CHIFFRES SE LISENT SUR CE QUI SERA GRAVÉ, pas sur ce qui a été
    # envisagé. Les cumuler au fil de la boucle comptait aussi les gestes
    # qu'`gestes_utiles` jette ensuite : la longueur annoncée gonflait, et
    # surtout un moignon jeté pouvait fixer à lui seul la largeur MINIMALE,
    # celle sur laquelle le panneau juge si le matériau sait faire le trait.
    for c in chaines:
        for _x, _y, w in c:
            w_min = min(w_min, w)
            w_max = max(w_max, w)
        longueur += _longueur_chaine(c)
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
