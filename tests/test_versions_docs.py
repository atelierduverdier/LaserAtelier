# -*- coding: utf-8 -*-
"""La version et les chiffres cités deux fois doivent concorder.

CE FICHIER EXISTE À CAUSE D'UNE LIGNE RESTÉE 44 VERSIONS EN RETARD. Le
`VERSION` de l'atelier est recopié dans six endroits — `package.xml`, le
badge du site, la ligne sous le logo du README, trois tampons du manuel — et
`CLAUDE.md` demande de les bouger « ensemble, en UN seul commit ». C'était
une consigne, pas un contrôle : rien ne rougissait quand on en oubliait un.
Un numéro de version faux ne se voit nulle part à l'usage — il s'imprime en
tête de chaque G-code écrit, et c'est en cherchant d'où vient un fichier,
des mois plus tard, qu'on découvre qu'il ment.

Le même piège a été relevé le 28/08/2026 sur un autre chiffre : le README
renvoyait au « chapitre 14 » du manuel pour un journal qui est au 13, et
annonçait « 87 entrées » alors que les compteurs du manuel en totalisaient
157. Écrit le 04/08/2026, jamais rouvert. Ces deux nombres-là sont donc
tenus ici aussi.

Ce que ce fichier tient :

1. les six tampons de version disent tous la même chose que `laser_core` ;
2. `package.xml` porte une date plausible, au bon format ;
3. le journal du manuel est bien le chapitre que le README annonce, et son
   total d'entrées est celui que le README affiche ;
4. chaque compteur de groupe du journal compte juste (une entrée = un
   paragraphe qui nomme sa version).

Aucun besoin de FreeCAD ici : on lit des fichiers. Le test tourne quand même
par le lanceur commun, pour être dans le rapport avec les autres.
"""
import io
import os
import re
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
sys.path.insert(0, RACINE)


def lire(*bouts):
    with io.open(os.path.join(RACINE, *bouts), encoding="utf-8") as f:
        return f.read()


CORE = lire("laser_core.py")
VERSION = re.search(r'^VERSION = "([^"]+)"', CORE, re.M).group(1)
assert re.match(r"^\d+\.\d+\.\d+$", VERSION), ("VERSION mal formée", VERSION)


# --- 1. LES SIX TAMPONS -----------------------------------------------
PAQUET = lire("package.xml")
INDEX = lire("docs", "index.html")
LISEZMOI = lire("README.md")
MANUEL = lire("docs", "manuel.html")

_tampons = [
    ("package.xml", re.findall(r"<version>([^<]+)</version>", PAQUET)),
    ("docs/index.html", re.findall(r"Version <b>([\d.]+)</b>", INDEX)),
    ("README.md", re.findall(r"<b>v([\d.]+)</b>", LISEZMOI)),
    ("docs/manuel.html", [
        m for m in re.findall(r'<span class="ver">Version ([\d.]+)</span>', MANUEL)]
        + re.findall(r"La version décrite ici est la <strong>([\d.]+)</strong>", MANUEL)
        + re.findall(r"LaserAtelier v([\d.]+) — Atelier du Verdier", MANUEL)),
]
_faux = []
for nom, trouves in _tampons:
    if not trouves:
        _faux.append((nom, "aucun tampon trouvé -- le motif a changé ?"))
    for v in trouves:
        if v != VERSION:
            _faux.append((nom, v))
assert not _faux, (
    "des fichiers annoncent une autre version que laser_core.py ({}) : "
    "ils se bougent ENSEMBLE, en un seul commit".format(VERSION), _faux)
# Le manuel en porte TROIS, pas une : la couverture, la frise et la
# signature de fin. En rater un est le cas le plus fréquent.
_n_manuel = len(_tampons[3][1])
assert _n_manuel == 3, (
    "le manuel doit porter 3 tampons de version (couverture, frise, "
    "signature) ; trouvés", _n_manuel)
print("version : {} — package.xml, site, README et les 3 tampons du manuel "
      "concordent OK".format(VERSION))


# --- 2. LA DATE DU PAQUET ----------------------------------------------
_date = re.search(r"<date>([^<]+)</date>", PAQUET).group(1)
assert re.match(r"^\d{4}-\d{2}-\d{2}$", _date), ("date mal formée", _date)
# Elle bouge avec la version : une date plus vieille que le dernier tampon
# de version ne serait pas fausse en soi, mais elle raconte une livraison
# qui n'a pas eu lieu ce jour-là. On se contente de la borner grossièrement.
assert _date >= "2026-07-15", ("date antérieure au début du projet", _date)
print("package.xml : date {} au bon format OK".format(_date))


# --- 3 & 4. LE JOURNAL, ET LES DEUX NOMBRES QUE LE README EN CITE ------
_sections = re.findall(r'<section class="chap" id="(c\d+)"', MANUEL)
_chapitre_journal = _sections.index("c13") + 1

_compteurs = [int(n) for n in re.findall(
    r'<span class="jcompte">\s*—\s*(\d+) entrées</span>', MANUEL)]
assert _compteurs, "plus aucun compteur de groupe dans le journal"
_total = sum(_compteurs)

_cite = re.search(r"chapitre (\d+) «&nbsp;\[Journal de l'atelier\]"
                  r"\([^)]*\)&nbsp;», (\d+) entrées", LISEZMOI)
assert _cite, ("le README ne cite plus le journal sous la forme attendue : "
               "ce contrôle ne contrôle plus rien")
assert int(_cite.group(1)) == _chapitre_journal, (
    "le README renvoie au chapitre {} ; le journal est le chapitre {}"
    .format(_cite.group(1), _chapitre_journal))
assert int(_cite.group(2)) == _total, (
    "le README annonce {} entrées de journal ; les compteurs du manuel en "
    "totalisent {}".format(_cite.group(2), _total))
print("journal : chapitre {}, {} entrées — le README dit la même chose OK"
      .format(_chapitre_journal, _total))

# Chaque compteur de groupe compte juste. Une ENTRÉE est un paragraphe en
# gras qui nomme sa version -- ou qui n'en nomme pas parce qu'il raconte une
# décision et non une livraison. Les paragraphes en gras qui commencent par
# « Et&nbsp;» sont des SUITES d'entrée (« Et le champ Description tient enfin
# son texte. ») et ne comptent pas : c'est la forme employée dans tout le
# journal pour ajouter un second fait à la même livraison. Règle vérifiée
# sur les huit groupes le 28/08/2026, sans exception à lister.
_JOURNAL = MANUEL[MANUEL.index('id="c13"'):]
_tetes = list(re.finditer(
    r'<h3>([^<]*)<span class="jcompte">\s*—\s*(\d+) entrées</span></h3>',
    _JOURNAL))
_ecarts, _suites = [], 0
for i, m in enumerate(_tetes):
    fin = _tetes[i + 1].start() if i + 1 < len(_tetes) else len(_JOURNAL)
    paras = re.findall(r"<p><b>(.{0,300}?)</b>", _JOURNAL[m.end():fin], re.S)
    entrees = [p for p in paras
               if re.search(r"\(v\d", p) or not p.lstrip().startswith("Et ")]
    _suites += len(paras) - len(entrees)
    if len(entrees) != int(m.group(2)):
        _ecarts.append((m.group(1).strip(), m.group(2), len(entrees)))
assert _tetes, "plus aucun groupe dans le journal"
assert not _ecarts, (
    "des compteurs de groupe ne comptent plus juste (groupe, annoncé, "
    "compté)", _ecarts)
print("journal : {} groupes, tous les compteurs justes, {} paragraphes de "
      "suite écartés OK".format(len(_tetes), _suites))
