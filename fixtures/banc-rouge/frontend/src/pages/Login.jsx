export default function Login() {
  return (
    <form>
      <input data-testid="champ-email" name="email" />
      <input data-testid="champ-mot-de-passe" name="mot_de_passe" type="password" />
      <button data-testid="bouton-valider" type="submit">Valider</button>
    </form>
  );
}
