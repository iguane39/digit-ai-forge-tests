"""TF-0315 (lot Produit-11 20260817a) — `champs_requis` demandait de fournir ce qui était
déjà fourni, et « pas de compte » ne se distinguait pas de « compte fourni, connexion échouée ».

Les six `non_testables[]` du rapport du 17/08 publiaient
`champs_requis: [FORGE_TESTS_QUALIF_LOGIN, FORGE_TESTS_QUALIF_PASSWORD]` alors que les deux
variables étaient renseignées ET valides — la contre-épreuve leur a fait ouvrir la session. Le
`pour_couvrir` ajoutait « déclarer FORGE_TESTS_QUALIF_CONNEXION » : elle valait déjà `/login`, la
bonne route. Un opérateur qui suit le rapport à la lettre refait trois gestes déjà faits, puis
conclut que son compte est mauvais.

Le mécanisme existait à côté — `CHAMPS_REQUIS_SESSION_FOURNIE` (TF-0222) sait dire « la session
fournie a été refusée, recapture-la » — mais il ne couvrait que storage state et bearer. Ce
fichier prouve le TROISIÈME état : `CHAMPS_REQUIS_CONNEXION_ECHOUEE`, dont le motif dit CE QUI A
ÉTÉ TENTÉ et OÙ ÇA S EST ARRÊTÉ. L information était déjà produite par `_connecter` ; elle était
diluée dans `non_juge`, hors du champ que l opérateur relit pour réparer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_tests.adaptateurs import qualif

_REFUS_401 = "Failed to load resource: the server responded with a status of 401 (UNAUTHORIZED)"


def _config(**surcharges: object) -> dict:
    return {
        "base": "https://bav.exemple.test",
        "login": "audit-2026",
        "mdp": "motdepasse-audit",
        "connexion": "/login",
        "marqueurs": {},
        "storage_state": "",
        "bearer": "",
        **surcharges,
    }


def _page_refusee(route: str) -> dict:
    return {
        "route": route,
        "statut": 200,
        "problemes": [],
        "affordances": [],
        "corps": "<h1>Connexion</h1>",
        "console": [_REFUS_401],
    }


def _session_echouee() -> list[dict]:
    """Ce que `_connecter` rend dans le cas mesuré : la mire n a pas été trouvée sur /login."""
    return [
        {
            "role": "",
            "etat": qualif.SESSION_SANS_MIRE,
            "motif": (
                "aucune mire de connexion trouvee, APRES attente d apparition du champ mot de "
                "passe (10 s par route) — routes essayees : /login : aucun "
                "« input[type=password] » apparu en 10 s"
            ),
            "arret": "/login : aucun « input[type=password] » apparu en 10 s",
        }
    ]


# --- 1. Les trois états sont DISTINCTS ---------------------------------------------------------
@pytest.mark.parametrize(
    ("libelle", "config", "sessions", "attendu"),
    [
        (
            "aucun compte fourni : c est bien un compte qu il manque",
            _config(login="", mdp=""),
            None,
            qualif.CHAMPS_REQUIS_SESSION,
        ),
        (
            "session capturee et refusee : il faut la RECAPTURER (TF-0222)",
            _config(storage_state="C:/x/storageState.json"),
            None,
            qualif.CHAMPS_REQUIS_SESSION_FOURNIE,
        ),
        (
            "compte fourni, connexion echouee : ni le compte, ni une recapture",
            _config(),
            _session_echouee(),
            qualif.CHAMPS_REQUIS_CONNEXION_ECHOUEE,
        ),
    ],
)
def test_les_trois_etats_reclament_trois_choses_differentes(
    libelle: str, config: dict, sessions: list[dict] | None, attendu: tuple[str, ...]
) -> None:
    assert qualif.champs_a_fournir(config, sessions) == attendu, libelle


def test_le_troisieme_etat_ne_reclame_JAMAIS_le_compte_deja_fourni() -> None:
    """Le défaut, énoncé comme tel : c est la présence de ces deux noms qui coûtait trois gestes
    inutiles et une conclusion fausse sur la validité du compte."""
    assert "FORGE_TESTS_QUALIF_LOGIN" not in qualif.CHAMPS_REQUIS_CONNEXION_ECHOUEE
    assert "FORGE_TESTS_QUALIF_PASSWORD" not in qualif.CHAMPS_REQUIS_CONNEXION_ECHOUEE


def test_les_trois_tuples_sont_bien_trois_etats_et_pas_deux() -> None:
    assert (
        len(
            {
                qualif.CHAMPS_REQUIS_SESSION,
                qualif.CHAMPS_REQUIS_SESSION_FOURNIE,
                qualif.CHAMPS_REQUIS_CONNEXION_ECHOUEE,
            }
        )
        == 3
    )


def test_la_route_de_la_mire_est_REVENDIQUEE_par_le_pan() -> None:
    """RT-13 : sans revendication, `FORGE_TESTS_QUALIF_CONNEXION` serait réclamée au nom du pan
    `data`, qui n en ferait rien — et jamais au nom de celui qu elle débloque."""
    from forge_tests.adaptateurs import REGISTRE
    from forge_tests.qualification import proprietaires

    assert "FORGE_TESTS_QUALIF_CONNEXION" in qualif.CHAMPS_REQUIS
    assert proprietaires(REGISTRE)["FORGE_TESTS_QUALIF_CONNEXION"] == {"qualif"}


# --- 2. Le motif dit CE QUI A ÉTÉ TENTÉ et OÙ ÇA S EST ARRÊTÉ ----------------------------------
def test_le_detail_republie_la_route_essayee_et_le_point_d_arret() -> None:
    detail = qualif.detail_connexion(_session_echouee())

    assert "TENTE :" in detail and "ARRET :" not in detail  # l arrêt est déjà dans le motif
    assert "/login" in detail
    assert "aucun « input[type=password] » apparu en 10 s" in detail


def test_un_arret_absent_du_motif_est_ajoute_explicitement() -> None:
    sessions = [
        {
            "etat": qualif.SESSION_ECHOUEE,
            "motif": "la mire /login a ete remplie et soumise, sans ouverture constatee",
            "arret": "/login : soumission sans effet observable",
        }
    ]

    detail = qualif.detail_connexion(sessions)

    assert "TENTE :" in detail and "ARRET : /login : soumission sans effet observable" in detail


def test_sans_echec_de_connexion_aucun_detail_n_est_invente() -> None:
    """Sens rouge : le champ ne se remplit pas quand il n y a rien à y mettre."""
    assert qualif.detail_connexion(None) == ""
    assert qualif.detail_connexion([{"etat": qualif.SESSION_OUVERTE, "preuve": "2 cookies"}]) == ""
    assert qualif.detail_connexion([{"etat": qualif.SESSION_SANS_COMPTE}]) == ""


# --- 3. Au rapport : le champ que l opérateur relit pour réparer --------------------------------
def test_les_non_testables_reclament_la_mire_ou_une_session_PAS_le_compte(tmp_path: Path) -> None:
    """Le cas complet du lot : compte fourni et valide, mire jamais atteinte, six routes muettes."""
    from forge_tests import qualification

    releve = [_page_refusee("/"), _page_refusee("/annonces"), _page_refusee("/mon-compte")]
    qualification.oublier(tmp_path)

    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, _session_echouee())
    reclames = set(qualification.requis(tmp_path, "acces"))
    qualification.oublier(tmp_path)

    assert sortie.verdict == "SKIP"
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_CONNEXION_ECHOUEE)
        for nt in sortie.non_testables
    )
    # Ni au registre de qualification, ni au non_testable : le compte n est plus redemandé.
    assert "FORGE_TESTS_QUALIF_LOGIN" not in reclames
    assert "FORGE_TESTS_QUALIF_PASSWORD" not in reclames
    # Et chaque non_testable porte la cause, dans SON champ.
    motifs = [nt.motif for nt in sortie.non_testables]
    assert all("TENTE :" in motif for motif in motifs)
    assert all("input[type=password]" in motif for motif in motifs)


def test_le_motif_de_precondition_dit_que_le_compte_n_est_PAS_en_cause(tmp_path: Path) -> None:
    releve = [_page_refusee("/"), _page_refusee("/annonces")]

    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, _session_echouee())

    motif = next(ligne for ligne in sortie.non_juge if "PRECONDITION NON ETABLIE" in ligne)
    assert "ce n est donc pas le compte qui manque ici" in motif
    assert "FORGE_TESTS_QUALIF_LOGIN" not in motif
    assert "PERIME" not in motif  # ce n est pas le cas de péremption d une session capturée


def test_sans_compte_fourni_le_motif_reclame_TOUJOURS_un_compte(tmp_path: Path) -> None:
    """Non-régression TF-0211 : le message d origine ne bouge pas quand rien n a été fourni."""
    releve = [_page_refusee("/"), _page_refusee("/annonces")]

    sortie = qualif.conclure(tmp_path, _config(login="", mdp=""), releve, [], None, None)

    motif = next(ligne for ligne in sortie.non_juge if "PRECONDITION NON ETABLIE" in ligne)
    assert "FORGE_TESTS_QUALIF_LOGIN" in motif
    assert "ce n est donc pas le compte qui manque ici" not in motif
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_SESSION) for nt in sortie.non_testables
    )


def test_une_session_capturee_refusee_reste_une_RECAPTURE(tmp_path: Path) -> None:
    """Non-régression TF-0222 : la session fournie prime — c est elle qu il faut renouveler, et
    l état CONNEXION_ECHOUEE ne vient pas la recouvrir."""
    releve = [_page_refusee("/"), _page_refusee("/annonces")]
    config = _config(storage_state="C:/x/storageState.json")

    sortie = qualif.conclure(tmp_path, config, releve, [], None, _session_echouee())

    motif = next(ligne for ligne in sortie.non_juge if "PRECONDITION NON ETABLIE" in ligne)
    assert "PERIME" in motif
    assert all(
        nt.champs_requis == list(qualif.CHAMPS_REQUIS_SESSION_FOURNIE)
        for nt in sortie.non_testables
    )


# --- 4. L action rendue à l opérateur nomme les bons champs ------------------------------------
def test_l_action_de_configuration_ne_cite_plus_le_compte(tmp_path: Path) -> None:
    """Le champ que le DOSSIER-MEP extrait (`categorie == manuelle_utilisateur`) : c est là que
    l opérateur lit ce qu il doit faire, et c est là que trois gestes inutiles étaient prescrits."""
    from forge_tests.actions import classifier

    releve = [_page_refusee("/"), _page_refusee("/annonces")]
    sortie = qualif.conclure(tmp_path, _config(), releve, [], None, _session_echouee())

    actions = classifier(
        [],
        [
            {"element": nt.element, "champs_requis": nt.champs_requis, "pan": nt.pan}
            for nt in sortie.non_testables
        ],
    )

    attendus = " ".join(action["attendu"] for action in actions)
    assert "FORGE_TESTS_QUALIF_CONNEXION" in attendus
    assert "FORGE_TESTS_QUALIF_LOGIN" not in attendus
    assert "FORGE_TESTS_QUALIF_PASSWORD" not in attendus
