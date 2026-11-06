"""Réponses réalistes d'une cible tierce, pour les bancs (TF-2275).

Fait remonté (Produit-86, lot 20261106d, RP-48) : le premier job réel d'un outil qui lit les
réponses d'une application derrière Cloudflare Access a révélé quatre défauts que 21 tests
unitaires laissaient passer : constats recréés à chaque tour, bilan figé, message de tour faux,
jetons de la cible en clair dans la preuve. Les bancs ne jouaient ni deux tours, ni une réponse 302
avec cookie : des réponses factices idéales (200 sans cookie, un seul passage) ne ressemblent à
aucune cible réelle.

Ce module fournit ce qui manquait aux bancs, sans réseau ni dépendance :

  - `servir(scenario)` monte un serveur local (bibliothèque standard) qui répond comme une cible
    réelle : redirection 302 avec `Set-Cookie`, mire de connexion, jeton dans l'en-tête, la
    requête et le corps, et un état qui change d'un TOUR à l'autre ;
  - `JETONS_DE_LA_CIBLE` et `jetons_visibles(texte)` : les valeurs que tout outil doit MASQUER dans
    ce qu'il publie (preuve, rapport, journal) ;
  - `rejouer_deux_fois(ingerer)` : la règle d'une ingestion, appliquée — la même source ingérée
    deux fois ne recrée rien et ne change aucun identifiant.

Les valeurs sont fictives et marquées comme telles : aucun secret réel n'entre dans un banc.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: Jeton d'accès FICTIF, de la forme d'un JWT (trois segments) : ce que la cible pose en cookie, en
#: en-tête et dans la requête. Tout texte publié qui le contient fuit la preuve de la cible.
JETON_ACCES = "eyJhbGciOiJub25lIn0.eyJzdWIiOiJmaWN0aWYtYmFuYyJ9.c2lnbmF0dXJlLWZpY3RpdmU"
COOKIE_ACCES = "CF_Authorization"
JETONS_DE_LA_CIBLE: tuple[str, ...] = (JETON_ACCES,)

SCENARIOS = ("acces-302-cookie", "deux-tours")

#: Les constats que la cible rend au tour 1, puis au tour 2 : les deux premiers sont les MÊMES
#: (mêmes identifiants), le troisième est neuf. Une ingestion qui recrée les deux premiers au
#: tour 2 est le défaut du lot.
CONSTATS_PAR_TOUR: dict[int, list[dict]] = {
    1: [
        {"id": "XSS-001", "titre": "XSS reflété sur /recherche", "gravite": "haute"},
        {"id": "CSP-002", "titre": "En-tête CSP absent", "gravite": "moyenne"},
    ],
    2: [
        {"id": "XSS-001", "titre": "XSS reflété sur /recherche", "gravite": "haute"},
        {"id": "CSP-002", "titre": "En-tête CSP absent", "gravite": "moyenne"},
        {"id": "COOKIE-003", "titre": "Cookie sans attribut Secure", "gravite": "basse"},
    ],
}


@dataclass
class Cible:
    """Une cible servie : son adresse, le journal de ce qu'elle a reçu, son tour courant."""

    url: str
    scenario: str
    tour: int = 1
    requetes: list[dict] = field(default_factory=list)

    def tour_suivant(self) -> int:
        self.tour += 1
        return self.tour


def _gestionnaire(cible: Cible) -> type[BaseHTTPRequestHandler]:
    class Reponse(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:  # silence : un banc n'imprime pas
            return

        def _cookie_present(self) -> bool:
            return f"{COOKIE_ACCES}={JETON_ACCES}" in (self.headers.get("Cookie") or "")

        def _repondre(self, code: int, corps: str, entetes: dict[str, str] | None = None,
                      type_contenu: str = "text/html; charset=utf-8") -> None:
            octets = corps.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", type_contenu)
            self.send_header("Content-Length", str(len(octets)))
            for nom, valeur in (entetes or {}).items():
                self.send_header(nom, valeur)
            self.end_headers()
            self.wfile.write(octets)

        def do_GET(self) -> None:  # noqa: N802 — nom imposé par http.server
            chemin = self.path.split("?")[0]
            cible.requetes.append({
                "chemin": self.path, "cookie": self._cookie_present(), "tour": cible.tour,
            })
            if cible.scenario == "deux-tours" and chemin == "/api/constats":
                self._repondre(200, json.dumps({"tour": cible.tour,
                                                "constats": CONSTATS_PAR_TOUR[min(cible.tour, 2)]}),
                               type_contenu="application/json")
                return
            if chemin == "/login":
                self._repondre(200, "<html><body><form>Connexion</form></body></html>")
            elif chemin == "/":
                # Accès sans cookie : 302 vers la mire, jeton de session posé en cookie ET dans la
                # requête de retour, comme le font les passerelles d'accès.
                self._repondre(
                    302, "",
                    {"Location": f"/app?token={JETON_ACCES}",
                     "Set-Cookie": f"{COOKIE_ACCES}={JETON_ACCES}; Path=/; HttpOnly"},
                )
            elif chemin == "/app":
                if self._cookie_present():
                    self._repondre(
                        200, json.dumps({"session": {"token": JETON_ACCES}, "page": "tableau"}),
                        {"X-Access-Token": JETON_ACCES}, type_contenu="application/json",
                    )
                else:
                    self._repondre(302, "", {"Location": "/login"})
            else:
                self._repondre(404, "introuvable")

    return Reponse


@contextmanager
def servir(scenario: str) -> Iterator[Cible]:
    """Monte la cible `scenario` sur 127.0.0.1 (port libre) le temps du bloc."""
    if scenario not in SCENARIOS:
        raise ValueError(f"scénario inconnu : {scenario!r} (connus : {', '.join(SCENARIOS)})")
    cible = Cible(url="", scenario=scenario)
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _gestionnaire(cible))
    cible.url = f"http://127.0.0.1:{serveur.server_address[1]}"
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    try:
        yield cible
    finally:
        serveur.shutdown()
        serveur.server_close()
        fil.join(timeout=5)


def jetons_visibles(texte: str, jetons: tuple[str, ...] = JETONS_DE_LA_CIBLE) -> list[str]:
    """Les jetons de la cible qui figurent EN CLAIR dans `texte` (preuve, rapport, journal)."""
    return [jeton for jeton in jetons if jeton and jeton in texte]


def rejouer_deux_fois(ingerer: Callable[[], list[dict]]) -> dict[str, list[str]]:
    """La règle d'une ingestion : la même source ingérée DEUX fois ne recrée rien.

    `ingerer()` lit la source et rend les enregistrements produits, chacun avec son `id`. Rend les
    défauts relevés, par nature ; une liste vide partout est l'ingestion idempotente :

      - `doublons` — un identifiant produit plusieurs fois dans un même passage ;
      - `recrees` — un enregistrement du passage 1 que le passage 2 ne retrouve pas à l'identique
        (identifiant instable : le constat est recréé à chaque tour) ;
      - `modifies` — même identifiant, contenu différent alors que la source n'a pas changé.
    """
    premier, second = ingerer(), ingerer()
    defauts: dict[str, list[str]] = {"doublons": [], "recrees": [], "modifies": []}
    for passage in (premier, second):
        vus: set[str] = set()
        for enregistrement in passage:
            identifiant = str(enregistrement["id"])
            if identifiant in vus and identifiant not in defauts["doublons"]:
                defauts["doublons"].append(identifiant)
            vus.add(identifiant)
    avant = {str(e["id"]): e for e in premier}
    apres = {str(e["id"]): e for e in second}
    defauts["recrees"] = sorted(set(avant) ^ set(apres))
    defauts["modifies"] = sorted(i for i in set(avant) & set(apres) if avant[i] != apres[i])
    return defauts
