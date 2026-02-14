# Xpenz iOS App (Expo)

Internal expense capture app for CaterBase Pro estimates.

## What It Does

- Logs in to your Django backend with `/api/xpenz/login/`
- Loads estimate jobs from `/api/xpenz/estimates/`
- Lets staff capture `receipt + voice note` per expense
- Opens an expense text/amount input on each captured item before save
- Supports `+ Manual Expense` entries without receipt/audio
- Saves to estimate Additional Info entries via `/api/xpenz/estimates/<id>/expenses/`

## Local Run (Expo Go)

1. `cd Xpenz`
2. `npm install`
3. `npm run start`
4. Open in Expo Go on iPhone and log in with your CaterBase admin user
5. API base URL default is `https://cater-base-pro.herokuapp.com` (editable on login screen)

## Backend Requirements

From project root:

1. `./venv/bin/python manage.py migrate`
2. Deploy backend changes to Heroku
3. Run migrations on Heroku after deploy:
   `heroku run python manage.py migrate --app cater-base-pro`

## EAS / TestFlight

### One-time setup

1. Install EAS CLI: `npm i -g eas-cli`
2. `cd Xpenz`
3. `eas login`
4. Update `app.json` bundle ID if needed:
   - `expo.ios.bundleIdentifier`
5. Update `eas.json` placeholders:
   - `submit.production.ios.ascAppId`
   - `submit.production.ios.appleId`

### Build for TestFlight

1. `cd Xpenz`
2. `eas build --platform ios --profile production`

### Submit to TestFlight

1. `eas submit --platform ios --profile production`

## Notes

- Receipt and voice data are internal-only and visible in Django admin Additional Info step.
- These entries do not print on estimate PDFs.
