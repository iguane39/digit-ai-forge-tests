"""TF-0372 — un second terme de comparaison externe : les anomalies déclarées.

Le fait : les cahiers du produit portaient `exigences_source: (absent)`, donc « les cas sont
dérivés de la SEULE surface inventoriée ». Honnête, déclaré — et c'est la limite fondatrice que
`invariants.py` énonce lui-même : on extrait l'invariant TEL QU'IMPLÉMENTÉ, donc un cas généré
sur une garde fausse CONFIRME le bug au lieu de le révéler.

Mais un référentiel d'exigences est rare, alors qu'une liste d'anomalies ouvertes existe sur
presque tout produit vivant. Sur celui-ci : treize, ouvertes les 29 et 30/07. Coût mesuré de leur
absence — six campagnes, 131 entrées au ledger, et **pas un seul de ces treize identifiants cité
où que ce soit**. Huit étaient toujours servies le 18/08.

Ce que ces tests vérifient surtout : que la mécanique est bien **RÉEMPLOYÉE** et non redoublée.
Deux calculs du même rattachement finiraient par ne plus dire la même chose.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests.livrables import anomalies, exigences

_TREIZE = chr(10).join([
    '{"id": "9870", "titre": "alerte creee le 29/07 enregistree au 24/07",'
    ' "statut": "ouvert", "priorite": 2}',
    '{"id": "9873", "titre": "des annonces sont localisees dans la mer bordant l Afrique",'
    ' "statut": "ouvert", "priorite": 1}',
    '{"id": "9858", "titre": "les notifications push ne fonctionnent pas",'
    ' "statut": "ouvert", "priorite": 2}',
    '{"id": "9801", "titre": "ancienne anomalie deja corrigee",'
    ' "statut": "closed", "priorite": 3}',
    "",
])


def _fichier(racine: Path, contenu: str = _TREIZE) -> Path:
    chemin = racine / "forge" / "anomalies.jsonl"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


# --- Le réemploi, qui est le sujet ------------------------------------------------------------
def test_le_referentiel_a_la_FORME_que_la_mecanique_des_exigences_lit(tmp_path: Path) -> None:
    """C'est ce qui permet de ne pas écrire une seconde mécanique de rattachement — et donc de ne
    pas avoir deux façons divergentes de décider qu'un cas « touche » quelque chose."""
    ref = anomalies.charger(_fichier(tmp_path))

    assert "exigences" in ref, "la clé porte le nom que `exigences` lit"
    entree = ref["exigences"][0]
    for champ in ("id", "enonce", "critere", "palier", "elements", "_racines"):
        assert champ in entree, f"champ attendu par `exigences` : {champ}"


def test_le_rattachement_est_celui_des_EXIGENCES_pas_un_second(tmp_path: Path) -> None:
    """La preuve du réemploi : c'est `exigences.rattacher` qui apparie, sans rien réimplémenter."""
    ref = anomalies.charger(_fichier(tmp_path))
    element = {"id": "qualif:route:/annonces", "libelle": "annonces localisees sur la carte"}

    lies = exigences.rattacher(ref, element)

    assert any(r["id"] == "9873" for r in lies), [r["id"] for r in lies]


def test_la_RECIPROQUE_est_celle_des_exigences_aussi(tmp_path: Path) -> None:
    """« la réciproque, que personne ne regarde jamais : les exigences qu AUCUN cas ne
    touche » — exactement le chapitre qui manquait pour les anomalies."""
    ref = anomalies.charger(_fichier(tmp_path))
    rattachements = {"qualif:route:/annonces": [{"id": "9873"}]}

    orphelines = exigences.sans_cas(anomalies.restreindre_aux_ouvertes(ref), rattachements)

    assert {a["id"] for a in orphelines} == {"9870", "9858"}


# --- Le chapitre qui manquait -----------------------------------------------------------------
def test_le_chapitre_dit_couverte_ET_non_couverte_avec_les_ids(tmp_path: Path) -> None:
    ref = anomalies.charger(_fichier(tmp_path))
    rattachements = {"qualif:route:/annonces": [{"id": "9873"}]}

    ch = anomalies.chapitre(ref, rattachements)

    assert ch["declare"] is True
    assert [c["id"] for c in ch["couvertes"]] == ["9873"]
    assert {n["id"] for n in ch["non_couvertes"]} == {"9870", "9858"}
    assert "3 anomalie(s) OUVERTE(S)" in ch["resume"]


def test_une_anomalie_FERMEE_n_entre_pas_au_reste_a_faire(tmp_path: Path) -> None:
    """L exiger ferait grossir le reste-à-faire avec tout l historique du produit, et un
    reste qui grossit cesse d être lu."""
    ref = anomalies.charger(_fichier(tmp_path))

    ids_ouvertes = {a["id"] for a in anomalies.ouvertes(ref)}

    assert "9801" not in ids_ouvertes
    assert len(ids_ouvertes) == 3


def test_le_chapitre_EXISTE_meme_sans_liste_declaree_et_dit_le_cout(tmp_path: Path) -> None:
    """Loi 3 : un bloc vide se DIT. Et ce qu'il dit ici est le fait fondateur — c'est l'état dans
    lequel six campagnes ont tourné sans savoir que treize anomalies existaient."""
    ch = anomalies.chapitre(None, {})

    assert ch["declare"] is False
    assert "AUCUN terme de comparaison externe" in ch["resume"]
    assert "six campagnes" in ch["resume"]


# --- Les refus --------------------------------------------------------------------------------
def test_un_chemin_DECLARE_et_introuvable_est_un_REFUS_pas_un_silence(tmp_path: Path) -> None:
    """Même règle qu'`exigences`. Croire « aucune anomalie » parce que le chemin est faux serait
    le pire des deux : c'est précisément l'état qu'on vient de corriger."""
    try:
        anomalies.charger(tmp_path / "absent.jsonl")
    except FileNotFoundError as erreur:
        assert "ne se remplace pas par « aucune anomalie »" in str(erreur)
    else:
        raise AssertionError("un chemin déclaré et introuvable doit lever, pas rendre None")


def test_une_ligne_ILLISIBLE_est_refusee_sans_perdre_les_autres(tmp_path: Path) -> None:
    """JSONL exactement pour ça : une ligne cassée n'empêche pas de lire les suivantes. Et elle
    est COMPTÉE — refusée, jamais confondue avec une absence."""
    chemin = _fichier(tmp_path, _TREIZE + "{ ceci n est pas du JSON\n" + '{"titre": "sans id"}\n')

    ref = anomalies.charger(chemin)
    ch = anomalies.chapitre(ref, {})

    assert len(ref["exigences"]) == 4, "les quatre lignes valides sont lues"
    assert ref["illisibles"] == [5, 6]
    assert "2 ligne(s) illisible(s)" in ch["resume"]
    assert "jamais comptée(s) comme absentes" in ch["resume"]


def test_sans_variable_declaree_aucun_chemin_n_est_devine(monkeypatch) -> None:
    monkeypatch.delenv(anomalies.VARIABLE, raising=False)

    assert anomalies.chemin_declare(Path(".")) is None


def test_les_limites_du_rattachement_LEXICAL_sont_declarees() -> None:
    """La plus importante : un cas qui partage des mots avec une anomalie ne prouve pas qu'il la
    couvre. Le recouvrement fortuit du 18/08 tenait au hasard de la séquence de test."""
    declare = " ".join(anomalies.NON_JUGE)

    assert "PISTE, pas une preuve" in declare
    assert "OUVERTES" in declare
    # c'est le projet qui exporte : la forge ne va jamais chercher dans un gestionnaire
    assert "aucune API tierce" in declare
