export default function Commandes() {
  return (
    <section>
      <select data-testid="filtre-statut" />
      <button data-testid="tri-date">Trier par date</button>
      <button data-testid="bouton-nouvelle">Nouvelle</button>
      <button data-testid="bouton-export">Exporter</button>
      <nav data-testid="pagination" />
    </section>
  );
}
