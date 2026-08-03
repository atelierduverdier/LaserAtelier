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
