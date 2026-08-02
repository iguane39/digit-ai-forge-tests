-- +migrate Up
ALTER TABLE commande ADD CONSTRAINT commande_statut_check
  CHECK (statut IN ('brouillon','validee','annulee'));

-- +migrate Down
ALTER TABLE commande DROP CONSTRAINT commande_statut_check;
