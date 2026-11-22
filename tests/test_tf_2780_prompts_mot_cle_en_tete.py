"""TF-2780 — le pan `prompts` n'écarte plus une consigne dont le nom COMMENCE par le mot-clé.

Fait remonté par Produit-12 (retour du 22/11/2026, RS-48) : `INSTRUCTIONS_REDACTION` n'avait pas
été vue, le pan affichait 1/19 au lieu de 3/21, et il a fallu rejouer un audit complet après
renommage. Le motif de nom de constante exigeait une majuscule AVANT `PROMPT`, `INSTRUCTIONS`,
`SYSTEM` ou `SYSTEME` : un nom qui s'ouvre sur le mot-clé n'y entrait pas.

Sens prouvés :
  - ROUGE  — sur l'ancien motif, `INSTRUCTIONS_REDACTION` n'est pas inventoriée ;
  - VERT   — elle l'est, comme `SYSTEM_PROMPT` et `MON_SYSTEME_PROMPT` qui l'étaient déjà ;
  - PUBLICATION — une constante qui porte le mot-clé sous une autre forme (`_SYSTEM_PROMPT`,
             `system_prompt`) reste hors inventaire, mais le non-jugé la NOMME ;
  - CONTRE-ÉPREUVES — un nom sans mot-clé, ou une valeur courte, n'entre ni à l'inventaire ni à
             la liste des écartées ; sans écartée, aucune ligne n'est ajoutée.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.adaptateurs import prompts

LONG = "Tu rediges une reponse claire, courte et sourcee pour le lecteur du dossier."


def _ecrire(racine: Path, relatif: str, contenu: str) -> Path:
    chemin = racine / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _ids(racine: Path) -> list[str]:
    return [e.id for e in prompts.inventaire(racine)]


def test_rouge_une_constante_dont_le_nom_commence_par_le_mot_cle_est_inventoriee(
    tmp_path: Path,
) -> None:
    _ecrire(tmp_path, "app/redaction.py", f'INSTRUCTIONS_REDACTION = "{LONG}"\n')
    assert "prompt:app/redaction.py:INSTRUCTIONS_REDACTION" in _ids(tmp_path)


def test_les_formes_deja_reconnues_le_restent(tmp_path: Path) -> None:
    _ecrire(
        tmp_path,
        "app/formes.py",
        f'SYSTEM_PROMPT = "{LONG}"\nMON_SYSTEME_PROMPT = "{LONG}"\nPROMPT = "{LONG}"\n'
        f'SYSTEM = "{LONG}"\nREDACTION_INSTRUCTIONS = "{LONG}"\n',
    )
    assert _ids(tmp_path) == [
        "prompt:app/formes.py:MON_SYSTEME_PROMPT",
        "prompt:app/formes.py:PROMPT",
        "prompt:app/formes.py:REDACTION_INSTRUCTIONS",
        "prompt:app/formes.py:SYSTEM",
        "prompt:app/formes.py:SYSTEM_PROMPT",
    ]


def test_une_annotation_de_type_ne_change_rien(tmp_path: Path) -> None:
    _ecrire(tmp_path, "app/typee.py", f'INSTRUCTIONS_ACCUEIL: str = "{LONG}"\n')
    assert _ids(tmp_path) == ["prompt:app/typee.py:INSTRUCTIONS_ACCUEIL"]


def test_une_candidate_a_la_forme_de_nom_non_reconnue_est_nommee_au_non_juge(
    tmp_path: Path,
) -> None:
    _ecrire(
        tmp_path,
        "app/ecartees.py",
        f'_SYSTEM_PROMPT = "{LONG}"\nsystem_prompt = "{LONG}"\nINSTRUCTIONS_OK = "{LONG}"\n',
    )
    assert _ids(tmp_path) == ["prompt:app/ecartees.py:INSTRUCTIONS_OK"]
    sortie = prompts.analyser(tmp_path)
    lignes = [ligne for ligne in sortie.non_juge if "forme de nom non reconnue" in ligne]
    assert len(lignes) == 1
    assert "2 constantes" in lignes[0]
    assert "app/ecartees.py:_SYSTEM_PROMPT" in lignes[0]
    assert "app/ecartees.py:system_prompt" in lignes[0]
    assert "INSTRUCTIONS_OK" not in lignes[0]  # celle qui est reconnue n'est pas « écartée »


def test_contre_epreuve_sans_mot_cle_ou_valeur_courte_rien_n_est_inventorie_ni_nomme(
    tmp_path: Path,
) -> None:
    _ecrire(
        tmp_path,
        "app/neutre.py",
        f'LIBELLE_LONG = "{LONG}"\nINSTRUCTIONS_COURTES = "trop court"\nsystem_court = "x"\n',
    )
    assert _ids(tmp_path) == []
    sortie = prompts.analyser(tmp_path)
    assert not any("forme de nom non reconnue" in ligne for ligne in sortie.non_juge)


def test_contre_epreuve_sans_candidate_ecartee_aucune_ligne_n_est_ajoutee(tmp_path: Path) -> None:
    _ecrire(tmp_path, "app/redaction.py", f'INSTRUCTIONS_REDACTION = "{LONG}"\n')
    sortie = prompts.analyser(tmp_path)
    assert not any("forme de nom non reconnue" in ligne for ligne in sortie.non_juge)


def test_la_liste_des_ecartees_est_bornee_et_le_total_se_dit() -> None:
    noms = [f"app/x.py:_SYSTEM_{n}" for n in range(prompts._MAX_NON_SUIVIS_NOMMES + 5)]
    (ligne,) = prompts._mention_ecartees(noms)
    assert f"{len(noms)} constantes" in ligne and "et 5 autres" in ligne
    assert noms[prompts._MAX_NON_SUIVIS_NOMMES] not in ligne


def test_la_mention_d_une_seule_ecartee_s_accorde() -> None:
    (ligne,) = prompts._mention_ecartees(["app/x.py:_SYSTEM_PROMPT"])
    assert "1 constante Python" in ligne and "porte un mot-cle" in ligne and "est ecartee" in ligne
