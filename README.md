# MailCleaner Zacoka 2 — Windows et macOS

Application graphique permettant de connecter Gmail et Outlook via une page de connexion officielle, ainsi qu'OVH par IMAP.

## Ce que fait cette version

- Interface en tableau avec une case à cocher par message.
- Boutons « Tout cocher » et « Tout décocher ».
- Filtres par âge, taille, expéditeur et objet.
- Détection des newsletters, messages non lus et pièces jointes.
- Aperçu du volume récupérable.
- Archivage ou déplacement vers la corbeille.
- Export CSV.
- Aucun effacement définitif automatique.
- Gmail : OAuth dans le navigateur.
- Outlook / Hotmail / Microsoft 365 : OAuth Microsoft.
- OVH : mot de passe stocké dans le coffre-fort du système.
- Compatible Windows et macOS.

## Important : pourquoi faut-il configurer OAuth ?

Google et Microsoft n'autorisent pas une application inconnue à lire une boîte mail. Il faut donc créer gratuitement une identité d'application. Cette opération ne se fait qu'une fois.

Le programme contient un menu **Configuration > Paramètres OAuth** permettant d'importer les identifiants.

## Configuration Google

1. Ouvrez Google Cloud Console.
2. Créez un projet, par exemple `MailCleaner Zacoka`.
3. Activez **Gmail API**.
4. Configurez l'écran de consentement OAuth.
5. Pendant les tests, ajoutez vos deux adresses Gmail dans les utilisateurs de test.
6. Créez un client OAuth de type **Application de bureau**.
7. Téléchargez le JSON.
8. Dans MailCleaner : **Configuration > Paramètres OAuth > Choisir le JSON**.
9. Cliquez sur **Connexion Google**.

Pour une diffusion publique à beaucoup d'utilisateurs, Google peut demander une vérification supplémentaire, car l'accès à Gmail est sensible.

## Configuration Microsoft

1. Ouvrez le portail Microsoft Entra.
2. Créez une nouvelle inscription d'application.
3. Types de comptes pris en charge :
   - comptes de cet annuaire ;
   - comptes d'autres annuaires ;
   - comptes Microsoft personnels.
4. Dans **Authentification**, activez « Autoriser les flux de clients publics ».
5. Ajoutez les permissions Microsoft Graph déléguées :
   - `User.Read`
   - `Mail.ReadWrite`
6. Copiez l'**ID d'application (client)**.
7. Collez-le dans **Configuration > Paramètres OAuth**.
8. Cliquez sur **Connexion Microsoft**.

## OVH

Cliquez sur **Ajouter OVH**, puis saisissez :

- l'adresse complète ;
- le mot de passe de la boîte ;
- serveur `ssl0.ovh.net` ou `imap.mail.ovh.net`.

Le mot de passe passe dans le coffre-fort Windows ou le Trousseau macOS grâce à `keyring`.

## Lancer en mode développement

### Windows

Double-cliquez sur `run_windows.bat`.

### macOS

Dans Terminal :

```bash
chmod +x run_macos.command build_macos.command
./run_macos.command
```

Au premier lancement, macOS peut demander l'autorisation d'ouvrir l'application.

## Créer les applications

### Windows

Double-cliquez sur `build_windows.bat`.

Résultat :

`dist\MailCleaner_Zacoka.exe`

### macOS

Sur le Mac, exécutez :

```bash
chmod +x build_macos.command
./build_macos.command
```

Résultat :

`dist/MailCleaner Zacoka.app`

Une application macOS doit être construite sur macOS. Un fichier `.app` généré sous Windows n'est pas valable.

## Signature et avertissements

Une application non signée peut déclencher SmartScreen sous Windows ou Gatekeeper sous macOS. Pour une distribution propre, il faut ensuite signer :

- l'EXE avec un certificat de signature de code ;
- l'application Mac avec un compte Apple Developer, puis la notariser.

## Limites actuelles

- Microsoft Graph ne donne pas toujours la taille exacte d'un message dans la liste, donc l'estimation de taille Microsoft peut rester à zéro.
- La détection des newsletters Microsoft repose en partie sur l'aperçu du message.
- La détection précise de toutes les pièces jointes OVH nécessiterait de lire davantage de structure MIME.
- Cette version analyse la boîte de réception. L'analyse globale de tous les dossiers pourra être ajoutée ensuite.
