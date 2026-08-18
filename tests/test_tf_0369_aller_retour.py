"""TF-0369 — ce que le produit accepte d'écrire est-il ce qu'il relit ?

La classe : le produit répond 200 et range autre chose. Ni la couverture, ni la mutation (0,90
sur le produit émetteur), ni un parcours ne la voient — **le parcours passe parce que le produit
fait ce que le parcours regarde.**

Deux défauts mesurés, tous deux DANS le périmètre couvert (69 tests verts) :

  (1) `default=datetime.now(timezone.utc)` : évalué UNE FOIS au chargement du module, donc
      chaque ligne porte l'instant du démarrage du processus. Écart constaté par l'utilisateur :
      cinq jours, exactement l'âge du conteneur (anomalie 9870) ;
  (2) `POST /alerts` écrase `email_notifications` à `False` en dur : la case cochée par
      l'utilisateur disparaît sans un mot.

Les deux ne se contrôlent pas de la même façon, et c'est le sujet de ce fichier. (1) est une
erreur de LANGAGE — un couple de parenthèses — donc statique. (2) est un comportement qui peut
être voulu, donc il ne se voit qu'en RELISANT champ par champ : c'est un cas dérivé.

Le détail qui rendait (1) invisible est rejoué en toute fin : **en local, le processus vient de
naître**. L'écart est de quelques secondes — invisible même en regardant. C'est pourquoi le cas
dérivé compare à l'HORLOGE et exige deux objets, jamais une valeur à elle-même.
"""

from __future__ import annotations

from pathlib import Path

from forge_tests import relecture


def _modele(racine: Path, corps: str, nom: str = "models_alerts.py") -> Path:
    cible = racine / "backend" / "src" / "alerts" / nom
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(corps, encoding="utf-8")
    return racine


# --- (A) le défaut évalué à l'import ------------------------------------------------------------
_FIGE = '''
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, String

class Alert:
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
'''

_CORRECT = _FIGE.replace("default=datetime.now(timezone.utc)", "default=datetime.now")


def test_le_cas_fondateur_de_la_date_figee_est_CONSTATE(tmp_path: Path) -> None:
    cible = _modele(tmp_path, _FIGE)

    findings = relecture.defauts_evalues_a_l_import(cible)

    assert len(findings) == 1, [f.id for f in findings]
    assert findings[0].classe == "defaut-evalue-a-l-import"
    assert "évalué UNE FOIS au chargement" in findings[0].message
    assert "models_alerts.py:7" in findings[0].localisation


def test_le_message_dit_POURQUOI_c_est_invisible_en_local(tmp_path: Path) -> None:
    """Sans ça, un lecteur qui vérifie sur son poste conclut « ça marche » et referme l'item :
    l'écart y est de quelques secondes. Le message doit donner le fait qui l'en empêche."""
    findings = relecture.defauts_evalues_a_l_import(_modele(tmp_path, _FIGE))

    assert "invisible en local" in findings[0].message
    assert "l âge du conteneur" in findings[0].message


def test_le_MEME_defaut_sans_parentheses_est_INNOCENT(tmp_path: Path) -> None:
    """Le second sens, et il tient à un couple de parenthèses : `default=datetime.now` est un
    callable, évalué à chaque insertion. Les deux se lisent presque pareil et ne font pas du tout
    la même chose — c'est exactement pourquoi un contrôle est utile ici."""
    findings = relecture.defauts_evalues_a_l_import(_modele(tmp_path, _CORRECT))

    assert findings == []


def test_les_autres_mots_de_DEFAUT_sont_couverts_pas_seulement_default(tmp_path: Path) -> None:
    """`server_default`, `default_factory`, `missing` : on ne devine pas l'ORM du projet."""
    cible = _modele(tmp_path, '''
from datetime import datetime
from dataclasses import field

class A:
    a = field(default_factory=datetime.now())
    b = X(server_default=datetime.utcnow())
''')

    findings = relecture.defauts_evalues_a_l_import(cible)

    assert len(findings) == 2, [f.message[:60] for f in findings]


def test_un_defaut_CALCULE_par_une_fonction_maison_n_est_PAS_denonce(tmp_path: Path) -> None:
    """La liste des appels temporels est NOMINATIVE, et c'est déclaré : deviner « toute fonction
    pourrait dépendre du temps » ferait dénoncer chaque défaut calculé, donc plus rien de
    lisible."""
    cible = _modele(tmp_path, '''
class A:
    a = Column(String, default=slug_par_defaut())
''')

    assert relecture.defauts_evalues_a_l_import(cible) == []


def test_un_appel_IMBRIQUE_ou_sur_plusieurs_lignes_est_vu(tmp_path: Path) -> None:
    """Lecture par AST, pas par expression régulière : un motif textuel aurait manqué les deux."""
    cible = _modele(tmp_path, '''
from datetime import datetime

class A:
    a = Column(
        DateTime,
        default=datetime.now(
            tz=timezone.utc,
        ),
    )
''')

    assert len(relecture.defauts_evalues_a_l_import(cible)) == 1


def test_les_dossiers_de_TEST_ne_sont_pas_lus(tmp_path: Path) -> None:
    """Une date figée dans une fixture de test est voulue — c'est même le contraire d'un défaut."""
    fixture = tmp_path / "tests" / "conftest.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(_FIGE, encoding="utf-8")

    assert relecture.defauts_evalues_a_l_import(tmp_path) == []


def test_un_fichier_qui_ne_PARSE_pas_n_interrompt_rien(tmp_path: Path) -> None:
    """Un défaut de syntaxe est un défaut du projet, que son propre lint dira mieux. Le doubler
    ici coûterait un second diagnostic du même fait — et surtout, planter ferait perdre TOUS les
    autres fichiers."""
    _modele(tmp_path, _FIGE)
    (tmp_path / "backend" / "src" / "casse.py").write_text("def (:", encoding="utf-8")

    assert len(relecture.defauts_evalues_a_l_import(tmp_path)) == 1


# --- (B) l'axe de cas dérivé ---------------------------------------------------------------------
def test_une_route_d_ECRITURE_recoit_un_cas_aller_retour() -> None:
    cas = relecture.cas_aller_retour("endpoint:POST /api/c13s/alerts")

    assert cas is not None
    assert cas["suffixe"] == "aller-retour"
    assert "POST /api/c13s/alerts" in cas["titre"]


def test_une_route_de_LECTURE_n_en_recoit_PAS() -> None:
    """Il n'y a pas d'aller-retour à vérifier sur un GET : rien n'a été écrit."""
    assert relecture.cas_aller_retour("endpoint:GET /api/c13s/alerts") is None
    assert relecture.cas_aller_retour("code:POST /x=422") is None
    assert relecture.cas_aller_retour("contrainte:alerts_pkey") is None


def test_le_cas_exige_les_SCALAIRES_pas_seulement_les_criteres() -> None:
    """C'est ce qui rendait le défaut (2) invisible : le parcours relisait les critères de
    l'alerte, jamais ses booléens."""
    gestes = " ".join(relecture.cas_aller_retour("endpoint:POST /alerts")["gestes"])

    assert "CHAMP PAR CHAMP" in gestes
    assert "booléens" in gestes
    assert "ne relit que les critères" in gestes


def test_le_cas_compare_une_DATE_a_l_horloge_et_jamais_a_elle_meme() -> None:
    """Le cœur du cas. Une valeur figée reste cohérente AVEC ELLE-MÊME : la comparer à elle-même
    est exactement ce qui laissait passer la date de démarrage du conteneur."""
    cas = relecture.cas_aller_retour("endpoint:PUT /alerts/{id}")
    gestes = " ".join(cas["gestes"])

    assert "comparer à l horloge du test" in gestes
    assert "JAMAIS à la valeur relue d un autre objet ni à elle-même" in gestes
    assert "SECOND objet" in gestes, "deux dates identiques à la seconde révèlent la valeur figée"
    assert "portent des dates différentes" in cas["resultat_attendu"]


def test_l_ecrasement_VOULU_a_une_issue_declaree() -> None:
    """Sinon le cas serait infalsifiable : un serveur a le droit de fixer un champ, à condition
    que son contrat le dise. L'attendu exige alors la ligne qui le déclare."""
    attendu = relecture.cas_aller_retour("endpoint:POST /alerts")["resultat_attendu"]

    assert "écrasement VOULU se déclare dans le contrat" in attendu


def test_l_axe_entre_dans_le_cahier_a_COTE_de_la_verification_pas_a_sa_place() -> None:
    """Vérifier qu'une route accepte une valeur conforme et vérifier qu'elle la RELIT sont deux
    questions ; c'est la seconde que six campagnes n'ont jamais posée."""
    from forge_tests.livrables.cahiers import _cas_unitaire

    element = {"id": "endpoint:POST /api/c13s/alerts"}
    cas = _cas_unitaire(element, {"code": "T1", "axe_cas": "unitaire"}, "jeu")
    suffixes = [c["suffixe"] for c in cas]

    assert "aller-retour" in suffixes
    assert "verification" in suffixes, "l'axe s'ajoute, il ne remplace pas"


def test_les_limites_des_DEUX_moities_sont_declarees() -> None:
    declare = " ".join(relecture.NON_JUGE)

    assert "NOMINATIVE" in declare, "la liste des appels temporels"
    assert "faux positif ASSUMÉ" in declare, "un `default=` hors modèle est signalé quand même"
    assert "relire exige une instance" in declare, "le cas est dérivé, pas exécuté"
