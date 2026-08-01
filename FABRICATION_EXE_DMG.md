# FABRICATION AUTOMATIQUE DU EXE ET DU DMG

Le projet est prêt à fabriquer automatiquement :

- `MailCleaner_Zacoka_Setup_Windows.exe`
- `MailCleaner_Zacoka_macOS.dmg`

## Méthode la plus simple

1. Crée un dépôt privé vide sur GitHub.
2. Dépose tout le contenu de ce dossier dans le dépôt.
3. Ouvre l'onglet **Actions**.
4. Sélectionne **Build MailCleaner Windows and macOS**.
5. Clique sur **Run workflow**.
6. Quand la fabrication est terminée, télécharge les deux fichiers dans **Artifacts** :
   - `MailCleaner-Windows-EXE`
   - `MailCleaner-macOS-DMG`

Aucune installation de Python n'est nécessaire sur les ordinateurs qui utiliseront les installateurs.

## Connexion Google et Microsoft

L'application demande encore une configuration OAuth unique :

- Google : fichier `credentials.json`
- Microsoft : identifiant client Microsoft Entra

C'est une exigence de sécurité de Google et Microsoft, pas une limitation de l'installateur.

## Avertissements possibles

Les fichiers ne sont pas signés numériquement. Windows SmartScreen ou macOS Gatekeeper peuvent donc afficher un avertissement. Une signature officielle nécessite :

- un certificat de signature de code Windows ;
- un compte Apple Developer pour signer et notariser le DMG.
