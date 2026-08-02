"""API du banc — 7 couples endpoint x méthode, 26 codes de retour déclarés (19 d'erreur).

Les codes sont déclarés dans `responses=` : c'est la source d'énumération de la surface API.
Stockage en mémoire : le banc doit rester exécutable sans base.
"""

from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

app = FastAPI(title="Banc d essai — commandes de repas")

UTILISATEURS = {"chef@exemple.fr": "secret"}
JETON = "jeton-de-test"
COMMANDES: dict[int, dict] = {}
STATUTS = ("brouillon", "validee", "annulee")
_SEQ = {"id": 0}


class Identifiants(BaseModel):
    email: str
    mot_de_passe: str


class CommandeIn(BaseModel):
    plat: str
    quantite: int


class CommandePatch(BaseModel):
    quantite: int | None = None
    statut: str | None = None


def _auth(authorization: str | None) -> None:
    if authorization != f"Bearer {JETON}":
        raise HTTPException(status_code=401, detail="jeton absent ou invalide")


@app.post("/api/login", responses={200: {}, 401: {}, 422: {}})
def login(ids: Identifiants) -> dict:
    if UTILISATEURS.get(ids.email) != ids.mot_de_passe:
        raise HTTPException(status_code=401, detail="identifiants refusés")
    return {"jeton": JETON}


@app.get("/api/commandes", responses={200: {}, 400: {}, 401: {}})
def lister(statut: str | None = None, authorization: str | None = Header(None)) -> dict:
    _auth(authorization)
    if statut is not None and statut not in STATUTS:
        raise HTTPException(status_code=400, detail=f"statut inconnu : {statut}")
    items = [c for c in COMMANDES.values() if statut is None or c["statut"] == statut]
    return {"commandes": items}


@app.post("/api/commandes", status_code=201, responses={201: {}, 400: {}, 401: {}, 422: {}})
def creer(corps: CommandeIn, authorization: str | None = Header(None)) -> dict:
    _auth(authorization)
    if corps.quantite <= 0:
        raise HTTPException(status_code=400, detail="quantite doit être strictement positive")
    _SEQ["id"] += 1
    commande = {
        "id": _SEQ["id"],
        "plat": corps.plat,
        "quantite": corps.quantite,
        "statut": "brouillon",
        "lignes": [{"plat": corps.plat, "quantite": corps.quantite}],
    }
    COMMANDES[commande["id"]] = commande
    return commande


@app.get("/api/commandes/{cid}", responses={200: {}, 401: {}, 404: {}})
def detail(cid: int, authorization: str | None = Header(None)) -> dict:
    _auth(authorization)
    if cid not in COMMANDES:
        raise HTTPException(status_code=404, detail="commande inconnue")
    return COMMANDES[cid]


@app.patch("/api/commandes/{cid}", responses={200: {}, 401: {}, 404: {}, 409: {}, 422: {}})
def modifier(cid: int, corps: CommandePatch, authorization: str | None = Header(None)) -> dict:
    _auth(authorization)
    if cid not in COMMANDES:
        raise HTTPException(status_code=404, detail="commande inconnue")
    commande = COMMANDES[cid]
    if commande["statut"] == "annulee":
        raise HTTPException(status_code=409, detail="commande annulée, non modifiable")
    if corps.statut is not None and corps.statut not in STATUTS:
        raise HTTPException(status_code=422, detail="statut hors liste")
    if corps.quantite is not None:
        commande["quantite"] = corps.quantite
        commande["lignes"] = [{"plat": commande["plat"], "quantite": corps.quantite}]
    if corps.statut is not None:
        commande["statut"] = corps.statut
    return commande


@app.delete("/api/commandes/{cid}", status_code=204, responses={204: {}, 401: {}, 404: {}, 409: {}})
def supprimer(cid: int, authorization: str | None = Header(None)) -> Response:
    _auth(authorization)
    if cid not in COMMANDES:
        raise HTTPException(status_code=404, detail="commande inconnue")
    if COMMANDES[cid]["statut"] == "validee":
        raise HTTPException(status_code=409, detail="commande validée, non supprimable")
    # Suppression en cascade : les lignes partent avec la commande, jamais orphelines.
    COMMANDES[cid]["lignes"] = []
    del COMMANDES[cid]
    return Response(status_code=204)


@app.post("/api/import", status_code=202, responses={202: {}, 400: {}, 401: {}, 415: {}})
async def importer_fichier(request: Request, authorization: str | None = Header(None)) -> dict:
    _auth(authorization)
    if request.headers.get("content-type", "") not in ("text/csv", "application/csv"):
        raise HTTPException(status_code=415, detail="type de média non supporté")
    from app.importer import importer_csv

    brut = await request.body()
    try:
        lignes, total = importer_csv(brut)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"importees": len(lignes), "total": total}
