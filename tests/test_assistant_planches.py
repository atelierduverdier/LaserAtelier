# -*- coding: utf-8 -*-
"""Les boutons ① de l'ASSISTANT MATÉRIAU, pilotés pour de vrai.

C'était le dernier angle mort de la calibration (relevé le 03/08/2026) :
l'Assistant est le point d'entrée d'un matériau neuf -- c'est lui que le
parcours ★3 désigne -- et aucun test ne CLIQUAIT ses boutons. Il était
seulement construit par l'outil de captures, donc on savait qu'il ne
plantait pas à l'ouverture, et rien de plus. Sa moitié ② est couverte
ailleurs (`_MesuresPlanchesControleur`, cinq fichiers) ; c'est ① qui
manquait.

On clique le bouton, on intercepte l'écriture, et on regarde le G-CODE
qui en sort -- pas la fonction qu'il appelle. La différence n'est pas
théorique : le bouton « Générer » de la Grille de test a été livré cassé
le 01/08/2026 (`self.spn_cell`, un widget inexistant) parce que la
vérification appelait l'helper au lieu du bouton.
"""
from harness import preparer, sans_dialogues
h = preparer()
core, tp = h.core, h.tp
import FreeCAD
from PySide6 import QtWidgets as _Qt
import re as _re

sans_dialogues()          # un QMessageBox attendrait un clic humain

# Les boutons ecrivent via _write_gcode_with_dialog : on l'intercepte pour
# ne rien poser sur le disque et pour saisir ce qui serait grave.
_ecrits = []
_vrai_write = tp._write_gcode_with_dialog


def _faux_write(parent, gcode, chemin_defaut):
    _ecrits.append((chemin_defaut, gcode))
    return chemin_defaut


tp._write_gcode_with_dialog = _faux_write
_doc = FreeCAD.newDocument("EssaiAssistantPlanches")
try:
    p = tp.TaskPanelAssistant()
    # Les boutons de planches, retrouves par leur LIBELLE -- c'est ce que
    # l'utilisateur lit et clique.
    boutons = {b.text(): b for b in p.form.findChildren(_Qt.QPushButton)}
    attendus = ["Planche 1", "Planche 2", "Planche 2b", "Planche 3",
                "Toutes les planches"]
    trouves = {}
    for cle in attendus:
        cands = [t for t in boutons if t.startswith(cle)]
        assert cands, ("bouton introuvable dans l'Assistant", cle,
                       sorted(boutons))
        trouves[cle] = boutons[sorted(cands, key=len)[0]]
    print("1. les {} boutons de planches sont là : {} OK".format(
        len(trouves), ", ".join(sorted(trouves))))

    # --- 2. Chaque bouton produit un G-code COMPLET ---------------------
    for cle in attendus:
        _ecrits.clear()
        trouves[cle].click()
        assert _ecrits, ("« {} » n'a rien écrit : le bouton est mort "
                         "(c'est exactement le défaut du 01/08/2026)".format(cle))
        chemin, g = _ecrits[-1]
        assert g and len(g) > 500, (cle, "G-code vide ou minuscule", len(g or ""))
        # Le contrat d'un fichier machine, verifie sur la SORTIE. PAS
        # l'estampille de version : elle est posee par l'ECRITURE
        # (_write_gcode_with_dialog), qu'on intercepte justement ici -- le
        # generateur, lui, rend son propre en-tete.
        assert g.lstrip().startswith("(G-Code Laser"), (cle, g[:60])
        assert "\nM2" in g or g.rstrip().endswith("M2"), (cle, "pas de fin M2")
        assert "G21" in g and "G90" in g, (cle, "en-tête incomplet")
        # Jamais de G4 faisceau allume (regle non negociable du projet).
        # On SUIT l'etat du faisceau ligne a ligne, exactement comme
        # test_panneaux : chercher un motif dans le texte se trompe (« G43
        # H100 », la compensation d'outil, commence par « G4 »).
        _s = 0
        for ligne in g.split("\n"):
            _ms = _re.search(r"\bS(\d+)", ligne)
            if _ms:
                _s = int(_ms.group(1))
            if ligne.startswith("G4 "):
                assert _s == 0, (cle, "pause faisceau allumé", ligne)
        print("   {:<22} {:>6} lignes, écrit vers {} OK".format(
            cle, len(g.split("\n")), chemin.split("/")[-1]))
    print("2. les 5 boutons produisent un G-code complet et sanitisé OK")

    # --- 3. « Toutes les planches » = UN fichier, pas cinq ---------------
    _ecrits.clear()
    trouves["Toutes les planches"].click()
    assert len(_ecrits) == 1, (
        "« Toutes les planches » doit écrire UN seul fichier", len(_ecrits))
    _tout = _ecrits[-1][1]
    _ecrits.clear()
    trouves["Planche 1"].click()
    _p1 = _ecrits[-1][1]
    assert len(_tout) > len(_p1) * 1.5, (
        "le fichier « toutes les planches » n'est pas plus gros que la "
        "planche 1 seule : les autres n'y sont pas", len(_tout), len(_p1))
    print("3. « Toutes les planches » réunit bien les planches en UN fichier "
          "({} lignes contre {} pour la planche 1 seule) OK".format(
              len(_tout.split("\n")), len(_p1.split("\n"))))

    # --- 3bis. Les 4 planches ne se CHEVAUCHENT pas ---------------------
    # Un fichier combine qui superpose deux planches est irrattrapable : on
    # s'en apercoit sur le bois, apres la gravure. La disposition a ete
    # resserree le 03/08/2026 (231 x 173 mm au lieu de 225 x 217, soit
    # 44 mm de hauteur en moins) en glissant la planche 3 dans le vide a
    # droite de la 2 -- exactement le genre de calcul ou deux planches
    # peuvent se mettre a se toucher.
    _ecrits.clear()
    trouves["Toutes les planches"].click()
    _g = _ecrits[-1][1]
    _boites, _cur = {}, None
    for _l in _g.split("\n"):
        _m = _re.match(r"\(===== (Planche [^:]+) :", _l)
        if _m:
            _cur = _m.group(1); _boites.setdefault(_cur, [1e9, -1e9, 1e9, -1e9])
            continue
        _m = _re.match(r"G[01] X(-?[\d.]+) Y(-?[\d.]+)", _l)
        if _m and _cur:
            _x, _y = float(_m.group(1)), float(_m.group(2))
            _b = _boites[_cur]
            _b[0] = min(_b[0], _x); _b[1] = max(_b[1], _x)
            _b[2] = min(_b[2], _y); _b[3] = max(_b[3], _y)
    _reelles = {n: b for n, b in _boites.items() if b[1] > b[0]}
    assert len(_reelles) >= 3, ("moins de 3 planches dans le fichier combiné",
                               sorted(_boites))
    _noms = sorted(_reelles)
    for _i in range(len(_noms)):
        for _j in range(_i + 1, len(_noms)):
            _a, _c = _reelles[_noms[_i]], _reelles[_noms[_j]]
            _croise = (_a[0] < _c[1] - 1e-6 and _c[0] < _a[1] - 1e-6
                       and _a[2] < _c[3] - 1e-6 and _c[2] < _a[3] - 1e-6)
            assert not _croise, (
                "deux planches se superposent dans le fichier combiné",
                _noms[_i], _reelles[_noms[_i]], _noms[_j], _reelles[_noms[_j]])
    _xs = [v for b in _reelles.values() for v in b[:2]]
    _ys = [v for b in _reelles.values() for v in b[2:]]
    _W, _H = max(_xs) - min(_xs), max(_ys) - min(_ys)
    # La disposition doit rester COMPACTE. Pas une cote figee (elle bouge
    # avec les plages S/F) mais un plafond : la somme des surfaces ne doit
    # pas etre noyee dans du vide.
    _utile = sum((b[1] - b[0]) * (b[3] - b[2]) for b in _reelles.values())
    assert _utile / (_W * _H) > 0.6, (
        "le fichier combiné gaspille plus de 40 % de sa surface : les "
        "planches sont mal rangées",
        round(100 * _utile / (_W * _H)), round(_W, 1), round(_H, 1))
    print("3bis. {} planches côte à côte sans se toucher, {:.0f} x {:.0f} mm, "
          "{:.0f} % de surface utile OK".format(
              len(_reelles), _W, _H, 100 * _utile / (_W * _H)))

    # --- 3ter. Cadrage embarque, PAUSE, puis gravure ---------------------
    # Le projet refusait d'embarquer le cadrage dans le job reel : « risque
    # de le lancer en pensant verifier alors que le laser va reellement
    # graver juste apres, SANS REPRISE DE MAIN entre les deux ». L'idee de
    # Christophe (03/08/2026) leve exactement cette objection : M0 EST la
    # reprise de main. Ce qui doit rester vrai, et que ce controle fige :
    #   - un seul M0, et RIEN qui grave avant lui ;
    #   - pendant le tour de cadrage et la pause, le laser n'est pas arme.
    _lignes = _g.split("\n")
    _i_m0 = [i for i, l in enumerate(_lignes) if l.strip() == "M0"]
    assert len(_i_m0) == 1, ("il faut UN seul arrêt, sinon on ne sait plus "
                             "ce qu'on relance", len(_i_m0))
    _i_m0 = _i_m0[0]
    _visee = core.FRAME_POWER
    _s = 0
    for _l in _lignes[:_i_m0]:
        _m = _re.search(r"\bQ(\d+)|\bS(\d+)", _l)
        if _m:
            _s = int(_m.group(1) or _m.group(2))
        assert not (_l.startswith("G1 ") and _s > _visee), (
            "le laser GRAVE avant la pause de cadrage : c'est exactement le "
            "risque pour lequel le cadrage embarqué avait été refusé", _l, _s)
    # ... et il est DÉSARMÉ au moment de la pause.
    _etat = None
    for _l in _lignes[:_i_m0]:
        if _l.startswith("M3"):
            _etat = "arme"
        elif _l.startswith("M5"):
            _etat = "desarme"
    assert _etat != "arme", (
        "le laser reste ARMÉ pendant la pause : on attend un cycle-start "
        "devant une machine sous tension")
    # La gravure, elle, commence bien apres.
    _s, _apres = 0, False
    for _l in _lignes[_i_m0:]:
        _m = _re.search(r"\bQ(\d+)|\bS(\d+)", _l)
        if _m:
            _s = int(_m.group(1) or _m.group(2))
        if _l.startswith("G1 ") and _s > _visee:
            _apres = True
            break
    assert _apres, "rien ne grave après la pause : le job serait vide"
    # Et la taille de la chute est annoncee en tete.
    assert any("CHUTE NECESSAIRE" in l for l in _lignes[:6]), (
        "l'encombrement total n'est pas annoncé en tête du fichier",
        _lignes[:6])
    print("3ter. cadrage au faisceau de visée (S{:.0f}), laser désarmé, UN "
          "seul M0, gravure après OK".format(_visee))

    # --- 4. Le bandeau ★3 est là, et il est LE bon -----------------------
    # L'etape 3 a longtemps designe la Grille de test ; depuis la v2.47.0
    # les planches se gravent ICI, et le bandeau doit suivre.
    from harness import texte as _texte
    _tous = " ".join(_texte(l.text()) for l in p.form.findChildren(_Qt.QLabel))
    assert "Étape 3" in _tous, (
        "l'Assistant n'affiche pas « ★ Étape 3/4 » alors que c'est lui qui "
        "grave les planches")
    print("4. le bandeau « ★ Étape 3/4 » s'affiche sur l'Assistant OK")
finally:
    tp._write_gcode_with_dialog = _vrai_write
    FreeCAD.closeDocument(_doc.Name)

print("\nTOUS LES TESTS assistant_planches PASSENT")
