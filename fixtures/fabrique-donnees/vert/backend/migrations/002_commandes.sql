-- +migrate Up
-- Clés étrangères simples et composées, identité GENERATED ALWAYS, relation d ordre entre deux
-- colonnes, contraintes posées par ALTER TABLE, index unique sur expression.
CREATE TABLE commande (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES client (id),
  statut statut_commande NOT NULL DEFAULT 'brouillon',
  passee_le TIMESTAMPTZ NOT NULL,
  livree_le TIMESTAMPTZ,
  CONSTRAINT commande_livraison_apres CHECK (livree_le IS NULL OR livree_le >= passee_le)
);

CREATE TABLE ligne_commande (
  commande_id BIGINT NOT NULL,
  produit_code CHAR(6) NOT NULL,
  quantite INTEGER NOT NULL,
  remise_pct INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (commande_id, produit_code),
  CONSTRAINT ligne_commande_commande_fk FOREIGN KEY (commande_id) REFERENCES commande (id),
  CONSTRAINT ligne_commande_produit_fk FOREIGN KEY (produit_code) REFERENCES produit (code)
);

ALTER TABLE ligne_commande ADD CONSTRAINT ligne_commande_quantite_bornee
  CHECK (quantite > 0 AND quantite < 100);
ALTER TABLE ligne_commande ADD CONSTRAINT ligne_commande_remise_admise
  CHECK (remise_pct = ANY (ARRAY[0, 5, 10, 15]));
CREATE UNIQUE INDEX client_courriel_sans_casse_idx ON client (lower(courriel));

-- +migrate Down
DROP INDEX client_courriel_sans_casse_idx;
DROP TABLE ligne_commande;
DROP TABLE commande;
