export default function Login() {
  return (
    <form>
      <input data-testid="champ-email" name="email" aria-label="Adresse e-mail" />
      <input data-testid="champ-mot-de-passe" name="mot_de_passe" type="password"
             aria-label="Mot de passe" />
      <button data-testid="bouton-valider" type="submit">Valider</button>
    </form>
  );
}
