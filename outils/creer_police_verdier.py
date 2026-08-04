#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dessine « Verdier », la police mono-trait de l'Atelier du Verdier.

    outils/creer_police_verdier.py            # écrit le module
    outils/creer_police_verdier.py --specimen # ... et un aperçu SVG

Contrairement aux quarante-quatre autres, celle-ci n'est convertie de rien :
chaque lettre est TRACÉE ici, trait par trait. Elle n'a donc ni source ni
licence tierce -- elle est à l'atelier, et rien n'interdit de la
redistribuer avec lui.

CE QUI L'A DESSINÉE

* **Le sens du geste.** Chaque trait est écrit dans la direction où une main
  le tracerait : les fûts DESCENDENT, les barres vont de gauche à droite,
  les panses tournent dans le sens de l'écriture. Ça ne se voit pas sur le
  papier et ça se voit sur la machine -- le fuseau (largeur portée par le Z)
  épaissit là où une plume aurait appuyé, et la tête parcourt la lettre
  comme une main, pas comme un traceur.
* **Lisible gravée petit.** Elle finira sur les étiquettes des planches de
  calibration, à 3 mm de haut : ouverture large, pas de fioriture, pas
  d'empattement. Les « fioritures » de cet atelier se paient en brûlure.
* **Un seul trait par branche**, jamais un contour. Les polices à fût
  contourné gravent chaque branche deux fois ; le registre les étiquette.
  Celle-ci tourne autour de 2 traits par lettre.
* **Le français en entier**, œ et Œ compris. Ils manquent aux 216 glyphes
  de TOUTES les polices d'oskay -- seule Relief SingleLine, sur les
  quarante-quatre, les portait. Verdier est la seconde ; partout ailleurs
  c'est le repli typographique qui sauve « cœur » en « coeur ».
* **Le chapeau melon**, la signature de l'atelier, est un glyphe : tape
  `¤` et il se grave.

Métriques (unités police, ligne de base y=0) : capitale 700, hauteur d'x
480, ascendante 730, descendante -200, chasse par défaut 460.
"""
import math
import os
import sys

CAP = 700.0          # hauteur de capitale
XH = 480.0           # hauteur d'x
ASC = 730.0          # ascendantes (b d f h k l)
DESC = -200.0        # descendantes (g j p q y)
OVER = 12.0          # débord des rondes, pour qu'un O ne paraisse pas petit


# --------------------------------------------------------------------------
# OUTILS DE TRACÉ
# --------------------------------------------------------------------------
def arc(cx, cy, rx, ry, a0, a1, n=None):
    """Arc d'ellipse en polyligne, de l'angle a0 à a1 (degrés, sens direct).

    Le nombre de points suit l'AMPLITUDE : une panse de 180° et un petit
    raccord de 30° ne demandent pas la même finesse, et un arc trop
    grossier se voit sur du bois bien avant de se voir à l'écran."""
    if n is None:
        n = max(4, int(abs(a1 - a0) / 12.0) + 2)
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def ligne(*pts):
    """Une polyligne, telle quelle."""
    return [(float(x), float(y)) for x, y in pts]


def decaler(traits, dx=0.0, dy=0.0):
    return [[(x + dx, y + dy) for x, y in t] for t in traits]


# --------------------------------------------------------------------------
# LE CHAPEAU — la signature de l'atelier, en glyphe
# --------------------------------------------------------------------------
def chapeau():
    """Le melon : une calotte, un bord, et le ruban qui les sépare.

    Trois traits, dessinés dans l'ordre où on le poserait : le bord d'abord
    (c'est lui qui pose l'objet), puis la calotte, puis le ruban."""
    return [
        ligne((30, 150), (90, 120), (200, 108), (330, 108), (440, 120),
              (500, 150), (440, 176), (330, 188), (200, 188), (90, 176),
              (30, 150)),
        arc(265, 175, 150, 205, 180, 0) + [(115, 175)],
        ligne((120, 205), (200, 222), (330, 222), (410, 205)),
    ]


# --------------------------------------------------------------------------
# CAPITALES — fûts descendants, barres de gauche à droite
# --------------------------------------------------------------------------
CAPS = {
    'A': (560, [ligne((40, 0), (280, CAP), (520, 0)), ligne((122, 245), (438, 245))]),
    'B': (540, [ligne((70, CAP), (70, 0)),
                ligne((70, CAP), (330, CAP)) + arc(330, 567, 165, 133, 90, -90) + ligne((70, 434)),
                ligne((70, 434), (355, 434)) + arc(355, 217, 180, 217, 90, -90) + ligne((70, 0))]),
    'C': (560, [arc(320, 350, 250, 350, 42, 318)]),
    'D': (560, [ligne((70, CAP), (70, 0)),
                ligne((70, CAP), (280, CAP)) + arc(280, 350, 215, 350, 90, -90) + ligne((70, 0))]),
    'E': (500, [ligne((450, CAP), (70, CAP), (70, 0), (450, 0)), ligne((70, 370), (390, 370))]),
    'F': (480, [ligne((450, CAP), (70, CAP), (70, 0)), ligne((70, 370), (380, 370))]),
    'G': (585, [arc(320, 350, 250, 350, 42, 330) + ligne((536, 300), (360, 300))]),
    'H': (560, [ligne((70, CAP), (70, 0)), ligne((490, CAP), (490, 0)),
                ligne((70, 370), (490, 370))]),
    'I': (240, [ligne((120, CAP), (120, 0))]),
    'J': (420, [ligne((330, CAP), (330, 150)) + arc(180, 150, 150, 150, 0, -180)]),
    'K': (540, [ligne((70, CAP), (70, 0)), ligne((490, CAP), (70, 300)),
                ligne((215, 405), (500, 0))]),
    'L': (460, [ligne((70, CAP), (70, 0), (430, 0))]),
    'M': (660, [ligne((60, 0), (60, CAP), (330, 190), (600, CAP), (600, 0))]),
    'N': (580, [ligne((70, 0), (70, CAP), (510, 0), (510, CAP))]),
    'O': (620, [arc(310, 350, 250, 350, 90, 450)]),
    'P': (520, [ligne((70, 0), (70, CAP), (320, CAP))
                + arc(320, 512, 175, 188, 90, -90) + ligne((70, 324))]),
    'Q': (620, [arc(310, 350, 250, 350, 90, 450), ligne((430, 135), (615, -55))]),
    'R': (540, [ligne((70, 0), (70, CAP), (320, CAP))
                + arc(320, 512, 175, 188, 90, -90) + ligne((70, 324)),
                ligne((300, 324), (510, 0))]),
    'S': (500, [arc(252, 528, 178, 172, 35, 215) + arc(250, 175, 180, 175, 35, -160)]),
    'T': (500, [ligne((250, CAP), (250, 0)), ligne((30, CAP), (470, CAP))]),
    'U': (560, [ligne((70, CAP), (70, 190)) + arc(300, 190, 230, 190, 180, 360)
                + ligne((530, CAP))]),
    'V': (560, [ligne((40, CAP), (280, 0), (520, CAP))]),
    'W': (800, [ligne((40, CAP), (215, 0), (400, 480), (585, 0), (760, CAP))]),
    'X': (540, [ligne((60, CAP), (480, 0)), ligne((480, CAP), (60, 0))]),
    'Y': (540, [ligne((60, CAP), (270, 350), (480, CAP)), ligne((270, 350), (270, 0))]),
    'Z': (520, [ligne((60, CAP), (460, CAP), (60, 0), (460, 0))]),
}


# --------------------------------------------------------------------------
# BAS DE CASSE — les panses partent en haut et tournent vers la gauche,
# comme la main les trace
# --------------------------------------------------------------------------
BAS = {
    'a': (490, [arc(255, 240, 175, 240, 60, 420),
                ligne((430, XH - 10), (430, 0))]),
    'b': (490, [ligne((70, ASC), (70, 0)),
                arc(255, 240, 185, 240, 180, -180)]),
    'c': (450, [arc(250, 240, 180, 240, 48, 312)]),
    'd': (490, [ligne((420, ASC), (420, 0)),
                arc(235, 240, 185, 240, 0, 360)]),
    'e': (460, [ligne((70, 250), (425, 252)) + arc(245, 240, 185, 240, 4, 330)]),
    'f': (300, [ligne((290, ASC)) + arc(160, ASC - 60, 130, 60, 90, 180) + ligne((30, 0)),
                ligne((40, XH), (285, XH))]),
    'g': (490, [arc(245, 240, 185, 240, 0, 360),
                ligne((430, XH), (430, -60)) + arc(255, -60, 175, 140, 0, -180)]),
    'h': (480, [ligne((70, ASC), (70, 0)),
                ligne((70, 300)) + arc(250, 300, 180, 180, 180, 0) + ligne((430, 0))]),
    'i': (220, [ligne((110, XH), (110, 0)), ligne((110, 640), (110, 660))]),
    'j': (240, [ligne((150, XH), (150, -60)) + arc(20, -60, 130, 140, 0, -180),
                ligne((150, 640), (150, 660))]),
    'k': (450, [ligne((70, ASC), (70, 0)), ligne((410, XH), (70, 180)),
                ligne((190, 265), (420, 0))]),
    'l': (220, [ligne((110, ASC), (110, 0))]),
    'm': (720, [ligne((70, XH), (70, 0)),
                ligne((70, 300)) + arc(230, 300, 160, 180, 180, 0) + ligne((390, 0)),
                ligne((390, 300)) + arc(550, 300, 160, 180, 180, 0) + ligne((710, 0))]),
    'n': (480, [ligne((70, XH), (70, 0)),
                ligne((70, 300)) + arc(250, 300, 180, 180, 180, 0) + ligne((430, 0))]),
    'o': (490, [arc(245, 240, 185, 240, 90, 450)]),
    'p': (490, [ligne((70, XH), (70, DESC)),
                arc(255, 240, 185, 240, 180, -180)]),
    'q': (490, [ligne((420, XH), (420, DESC)),
                arc(235, 240, 185, 240, 0, 360)]),
    'r': (330, [ligne((70, XH), (70, 0)),
                ligne((70, 300)) + arc(210, 300, 140, 180, 180, 20)]),
    's': (410, [arc(207, 352, 145, 122, 35, 215) + arc(205, 125, 148, 122, 35, -160)]),
    't': (300, [ligne((150, ASC), (150, 110)) + arc(230, 110, 80, 110, 180, 285),
                ligne((30, XH), (275, XH))]),
    'u': (480, [ligne((70, XH), (70, 180)) + arc(250, 180, 180, 180, 180, 360)
                + ligne((430, XH)), ligne((430, 180), (430, 0))]),
    'v': (450, [ligne((30, XH), (225, 0), (420, XH))]),
    'w': (660, [ligne((30, XH), (180, 0), (330, 330), (480, 0), (630, XH))]),
    'x': (440, [ligne((40, XH), (400, 0)), ligne((400, XH), (40, 0))]),
    'y': (450, [ligne((30, XH), (225, 0)), ligne((420, XH), (140, DESC))]),
    'z': (430, [ligne((50, XH), (380, XH), (50, 0), (380, 0))]),
}


# --------------------------------------------------------------------------
# CHIFFRES ET PONCTUATION
# --------------------------------------------------------------------------
CHIFFRES = {
    '0': (540, [arc(270, 350, 210, 350, 90, 450)]),
    '1': (300, [ligne((70, 545), (215, CAP), (215, 0)), ligne((70, 0), (360, 0))]),
    '2': (520, [arc(255, 495, 190, 205, 170, -55) + ligne((60, 0), (470, 0))]),
    '3': (520, [arc(250, 530, 175, 170, 160, -100),
                arc(245, 175, 195, 175, 95, -160)]),
    '4': (520, [ligne((370, 0), (370, CAP), (50, 195), (480, 195))]),
    '5': (520, [ligne((450, CAP), (140, CAP), (110, 400))
                + arc(255, 205, 205, 205, 105, -115)]),
    '6': (520, [arc(265, 205, 205, 205, 90, 450), arc(265, 205, 205, 495, 180, 80)]),
    '7': (490, [ligne((50, CAP), (450, CAP), (170, 0))]),
    '8': (520, [arc(260, 530, 175, 170, 90, 450), arc(260, 190, 205, 190, 90, 450)]),
    '9': (520, [arc(255, 495, 205, 205, 90, 450), arc(255, 495, 205, 495, 0, -100)]),
}

PONCT = {
    ' ': (300, []),
    '\r': (300, []),
    '.': (240, [ligne((110, 0), (110, 30))]),
    ',': (240, [ligne((130, 40), (130, 10), (70, -110))]),
    ':': (240, [ligne((110, 0), (110, 30)), ligne((110, 300), (110, 330))]),
    ';': (240, [ligne((130, 40), (130, 10), (70, -110)), ligne((120, 300), (120, 330))]),
    '!': (240, [ligne((115, CAP), (115, 175)), ligne((115, 0), (115, 30))]),
    '?': (450, [arc(225, 545, 160, 155, 175, -85) + ligne((225, 175)),
                ligne((225, 0), (225, 30))]),
    "'": (180, [ligne((90, CAP), (90, 545))]),
    '"': (300, [ligne((90, CAP), (90, 545)), ligne((210, CAP), (210, 545))]),
    '(': (280, [arc(250, 300, 190, 400, 155, 205)]),
    ')': (280, [arc(30, 300, 190, 400, 25, -25)]),
    '[': (280, [ligne((230, 720), (90, 720), (90, -120), (230, -120))]),
    ']': (280, [ligne((50, 720), (190, 720), (190, -120), (50, -120))]),
    '-': (380, [ligne((60, 330), (320, 330))]),
    '–': (520, [ligne((40, 330), (480, 330))]),
    '—': (700, [ligne((40, 330), (660, 330))]),
    '_': (500, [ligne((20, -130), (480, -130))]),
    '/': (400, [ligne((40, -60), (360, CAP))]),
    '\\': (400, [ligne((40, CAP), (360, -60))]),
    '|': (240, [ligne((120, -120), (120, 720))]),
    '+': (520, [ligne((80, 350), (440, 350)), ligne((260, 170), (260, 530))]),
    '=': (520, [ligne((80, 250), (440, 250)), ligne((80, 450), (440, 450))]),
    '<': (480, [ligne((410, 550), (70, 330), (410, 110))]),
    '>': (480, [ligne((70, 550), (410, 330), (70, 110))]),
    '*': (400, [ligne((200, 420), (200, 700)), ligne((80, 490), (320, 630)),
                ligne((80, 630), (320, 490))]),
    '#': (600, [ligne((190, 0), (250, CAP)), ligne((370, 0), (430, CAP)),
                ligne((70, 230), (520, 230)), ligne((90, 450), (540, 450))]),
    '%': (700, [arc(180, 545, 120, 130, 90, 450), arc(520, 155, 120, 130, 90, 450),
                ligne((600, CAP), (100, 0))]),
    # L'esperluette a demande trois essais. Une seule polyligne n'y arrive
    # pas : la diagonale traverse la panse et le tout se lit « b ». Deux
    # boucles fermees et une queue, c'est la construction des polices CNC,
    # et elle se lit sans hesiter.
    '&': (640, [arc(255, 520, 148, 158, 90, 450), arc(250, 180, 195, 180, 90, 450),
                ligne((380, 310), (610, 20))]),
    '@': (760, [arc(350, 300, 138, 138, 90, 450),
                ligne((488, 430), (488, 195)) + arc(370, 300, 330, 330, -22, 292)]),
    '«': (460, [ligne((210, 420), (60, 300), (210, 180)),
                     ligne((400, 420), (250, 300), (400, 180))]),
    '»': (460, [ligne((60, 420), (210, 300), (60, 180)),
                     ligne((250, 420), (400, 300), (250, 180))]),
    '°': (300, [arc(150, 600, 90, 90, 90, 450)]),
    '€': (620, [arc(340, 350, 230, 350, 42, 318),
                     ligne((60, 270), (400, 270)), ligne((60, 430), (400, 430))]),
    '¤': (540, chapeau()),
}


# --------------------------------------------------------------------------
# ACCENTS — composés, jamais redessinés
# --------------------------------------------------------------------------
ACC_H = 620.0        # hauteur des accents sur bas de casse
ACC_CAP = 760.0      # ... et sur capitales

def _accents(h):
    return {
        'aigu':    [ligne((-70, h), (60, h + 105))],
        'grave':   [ligne((-70, h + 105), (60, h))],
        'circon':  [ligne((-80, h), (0, h + 110), (80, h))],
        'trema':   [ligne((-75, h + 40), (-75, h + 75)), ligne((75, h + 40), (75, h + 75))],
        'tilde':   [ligne((-90, h + 20)) + arc(-45, h + 40, 45, 45, 200, 20)
                    + arc(45, h + 45, 45, 45, 180, 0) + ligne((90, h + 65))],
    }

# (caractère composé, base, accent, sur capitale ?)
COMPOSES = [
    ('à', 'a', 'grave', False), ('â', 'a', 'circon', False),
    ('ä', 'a', 'trema', False), ('ã', 'a', 'tilde', False),
    ('é', 'e', 'aigu', False), ('è', 'e', 'grave', False),
    ('ê', 'e', 'circon', False), ('ë', 'e', 'trema', False),
    ('î', 'i', 'circon', False), ('ï', 'i', 'trema', False),
    ('í', 'i', 'aigu', False), ('ì', 'i', 'grave', False),
    ('ô', 'o', 'circon', False), ('ö', 'o', 'trema', False),
    ('ó', 'o', 'aigu', False), ('ò', 'o', 'grave', False),
    ('õ', 'o', 'tilde', False),
    ('ù', 'u', 'grave', False), ('û', 'u', 'circon', False),
    ('ü', 'u', 'trema', False), ('ú', 'u', 'aigu', False),
    ('ÿ', 'y', 'trema', False), ('ñ', 'n', 'tilde', False),
    ('À', 'A', 'grave', True), ('Â', 'A', 'circon', True), ('Ä', 'A', 'trema', True),
    ('É', 'E', 'aigu', True), ('È', 'E', 'grave', True), ('Ê', 'E', 'circon', True),
    ('Ë', 'E', 'trema', True),
    ('Î', 'I', 'circon', True), ('Ï', 'I', 'trema', True),
    ('Ô', 'O', 'circon', True), ('Ö', 'O', 'trema', True),
    ('Ù', 'U', 'grave', True), ('Û', 'U', 'circon', True), ('Ü', 'U', 'trema', True),
    ('Ñ', 'N', 'tilde', True),
]


def cedille(x):
    """La cédille, accrochée sous la panse à l'abscisse x."""
    return [ligne((x, 20), (x, -40)) + arc(x - 55, -40, 55, 60, 0, -170)]


# --------------------------------------------------------------------------
# ASSEMBLAGE
# --------------------------------------------------------------------------
def construire():
    g = {}
    g.update(CAPS)
    g.update(BAS)
    g.update(CHIFFRES)
    g.update(PONCT)

    # i et j sans point : le point est un trait à part, on le remonte à la
    # bonne hauteur (les listes ci-dessus le posent à 640-660, provisoire).
    for c in ('i', 'j'):
        adv, traits = g[c]
        g[c] = (adv, [traits[0], ligne((traits[1][0][0], 600),
                                       (traits[1][0][0], 640))])

    for car, base, nom_acc, sur_cap in COMPOSES:
        adv, traits = g[base]
        acc = _accents(ACC_CAP if sur_cap else ACC_H)[nom_acc]
        # l'accent se centre sur la lettre, pas sur la chasse : un « É »
        # dont l'accent penche à droite se voit tout de suite.
        xs = [x for t in traits for x, _y in t]
        cx = (min(xs) + max(xs)) / 2.0
        # i et j perdent leur point sous l'accent -- deux marques
        # superposées, c'est une faute, pas un détail.
        corps = traits[:1] if base in ('i', 'j') else traits
        g[car] = (adv, corps + decaler(acc, dx=cx))

    # Ç / ç : la cédille s'accroche sous le C, à l'aplomb de sa panse.
    for haut, bas_ in (('Ç', 'C'), ('ç', 'c')):
        adv, traits = g[bas_]
        xs = [x for t in traits for x, _y in t]
        g[haut] = (adv, traits + cedille((min(xs) + max(xs)) / 2.0))

    # Æ / æ, Œ / œ : les LIGATURES, et œ manque à TOUTES les polices
    # d'oskay -- 216 glyphes chacune, pas un œ. C'est le seul accent
    # français qu'aucune ne sait tracer.
    # La panse du « a » se FERME (360 degres) : ouverte, la ligature se
    # lisait « ce ». Et la barre du « e » enchaine sur sa panse au point
    # ou elle finit -- sans quoi le raccourci dessine un triangle, defaut
    # deja corrige sur le « e » seul.
    g['æ'] = (770, [arc(250, 240, 175, 240, 60, 420),
                    ligne((425, XH - 10), (425, 0)),
                    ligne((430, 250), (765, 252)) + arc(577, 240, 190, 240, 4, 330)])
    g['Æ'] = (880, [ligne((40, 0), (390, CAP), (830, CAP)),
                    ligne((390, CAP), (390, 0), (830, 0)),
                    ligne((175, 245), (390, 245)),
                    ligne((390, 350), (690, 350))])
    g['œ'] = (800, [arc(245, 240, 185, 240, 90, 450),
                    ligne((400, 250), (775, 252)) + arc(587, 240, 190, 240, 4, 330)])
    g['Œ'] = (900, [arc(320, 350, 250, 350, 90, 270),
                    ligne((320, CAP), (870, CAP)), ligne((320, 0), (870, 0)),
                    ligne((450, 370), (800, 370))])
    g['ß'] = (520, [ligne((70, 0), (70, 560)) + arc(215, 560, 145, 140, 180, 0)
                    + ligne((360, 330), (230, 300))
                    + arc(300, 155, 145, 145, 115, -100)])

    # La chasse par défaut sert aux caractères absents ; on la prend au
    # milieu de l'alphabet plutôt qu'au hasard.
    return g


def cap_height_mesure(g):
    """La hauteur de capitale MESURÉE sur le 'H', jamais déclarée.

    Le piège coûte cher et il a déjà servi : les SVG d'oskay annoncent 500
    et dessinent 662, si bien que tout texte sortait 32 % trop haut, sur
    toutes les étiquettes des planches. Ici la donnée est calculée depuis
    les traits eux-mêmes -- elle ne PEUT pas diverger du dessin."""
    ys = [y for t in g['H'][1] for _x, y in t]
    return max(ys) - min(ys)


def ecrire(dest, g):
    cap = cap_height_mesure(g)
    lignes = [
        "# -*- coding: utf-8 -*-",
        '"""Police vectorielle MONO-TRAIT (un seul trait par branche).',
        "",
        "Verdier -- la police de l'Atelier du Verdier.",
        "Source : dessinee trait par trait par outils/creer_police_verdier.py",
        "Licence : LGPL-2.1-or-later, comme l'atelier (aucune fonte tierce).",
        "",
        "Genere par outils/creer_police_verdier.py -- ne pas editer",
        "a la main. GLYPHES[car] = (avance_x, [trait, ...]) ;",
        "trait = [(x, y), ...] en unites police (ligne de base y=0,",
        "hauteur de capitale = CAP_HEIGHT).",
        '"""',
        "",
        "CAP_HEIGHT = {:.0f}".format(cap),
        "ADV_DEFAULT = 460",
        "",
        "GLYPHES = {",
    ]
    for car in sorted(g, key=lambda c: (len(c), c)):
        adv, traits = g[car]
        tr = "[" + ",".join(
            "[" + ",".join("({:.4g},{:.4g})".format(x, y) for x, y in t) + "]"
            for t in traits) + "]"
        lignes.append("    {!r}: ({:.0f}, {}),".format(car, adv, tr))
    lignes.append("}")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")
    return cap


def specimen(g, dest):
    """Un SVG pour REGARDER la police, parce qu'on ne juge pas un dessin
    sur une liste de coordonnées."""
    lignes_txt = ["ABCDEFGHIJKLM", "NOPQRSTUVWXYZ", "abcdefghijklm",
                  "nopqrstuvwxyz", "0123456789 &@%", "aeiouAEIOU",
                  "Atelier du Verdier ¤", "« français, cœur, où ? »",
                  "ÇçÆæŒœß ÀÉÈÊËÎÏÔÖÙÛÜ", "àéèêëîïôöùûüÿñ 12,50 € (S400/F800)"]
    out, y = [], 0.0
    for txt in lignes_txt:
        x = 0.0
        for ch in txt:
            adv, traits = g.get(ch, (460, []))
            for t in traits:
                d = "M " + " L ".join("{:.1f},{:.1f}".format(x + px, y - py)
                                      for px, py in t)
                out.append('<path d="{}"/>'.format(d))
            x += adv + 40
        y += 1150
    with open(dest, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="-50 -900 9200 {}" '
                'width="1150">\n<g fill="none" stroke="#2f3540" stroke-width="26" '
                'stroke-linecap="round" stroke-linejoin="round">\n{}\n</g></svg>\n'
                .format(y + 500, "\n".join(out)))


if __name__ == "__main__":
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    g = construire()
    dest = os.path.join(racine, "polices_monotrait", "hershey_font_verdier.py")
    cap = ecrire(dest, g)
    traits = sum(len(t) for _a, t in g.values())
    lettres = [c for c in g if c.isalpha()]
    print("Verdier : {} glyphes, {} traits, {:.1f} traits/lettre, "
          "hauteur de capitale mesuree {:.0f}"
          .format(len(g), traits,
                  sum(len(g[c][1]) for c in lettres) / float(len(lettres)), cap))
    print("  ->", dest)
    if "--specimen" in sys.argv:
        sp = os.path.join(racine, "docs", "assets", "specimen_verdier.svg")
        specimen(g, sp)
        print("  ->", sp)
