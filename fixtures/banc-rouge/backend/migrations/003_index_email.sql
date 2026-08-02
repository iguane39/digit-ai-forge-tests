-- +migrate Up
CREATE UNIQUE INDEX utilisateur_email_idx ON utilisateur (email);
-- H-12 : cette migration DEFAIT ce que 002 avait pose. Chaque instruction s execute sans
-- erreur, aucun test ne casse, et le schema final n a plus la contrainte que le code croit
-- appliquee. Seule la comparaison ANNONCE / SCHEMA OBTENU le voit.
ALTER TABLE commande DROP CONSTRAINT commande_statut_check;
