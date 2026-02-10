<!-- BEGIN AUTO-GENERATED HEADER -->

[![Release](https://img.shields.io/github/v/release/natekspencer/ha-pura?style=for-the-badge)](https://github.com/natekspencer/ha-pura/releases)
[![HACS Badge](https://img.shields.io/badge/HACS-default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor_💜-6f42c1?style=for-the-badge&logo=github&logoColor=white&labelColor=grey)](https://github.com/sponsors/natekspencer)

![Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/total?style=flat-square)
![Latest Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/latest/total?style=flat-square)

<!-- END AUTO-GENERATED HEADER -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://brands.home-assistant.io/pura/dark_logo.png">
  <img alt="Pura logo" src="https://brands.home-assistant.io/pura/logo.png">
</picture>

# Pura for Home Assistant

Home Assistant integration for Pura smart fragrance diffusers.

<!-- BEGIN AUTO-GENERATED INSTALLATION -->

## ⬇️ Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=natekspencer&repository=ha-pura&category=integration)

This integration is available in the default [HACS](https://hacs.xyz/) repository.

1. Use the **My Home Assistant** badge above, or from within Home Assistant, click on **HACS**
2. Search for `Pura` and click on the appropriate repository
3. Click **DOWNLOAD**
4. Restart Home Assistant

### Manual

If you prefer manual installation:

1. Download or clone this repository
2. Copy the `custom_components/pura` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

> ⚠️ Manual installation will not provide automatic update notifications. HACS installation is recommended unless you have a specific need.

## ➕ Setup

Once installed, you can set up the integration by clicking on the following badge:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=pura)

Alternatively:

1. Go to [Settings > Devices & services](https://my.home-assistant.io/redirect/integrations/)
2. In the bottom-right corner, select **Add integration**
3. Type `Pura` and select the **Pura** integration
4. Follow the instructions to add the integration to your Home Assistant
<!-- END AUTO-GENERATED INSTALLATION -->

## 🚨 Troubleshooting

If you created your Pura account using one of the third-party provider options (e.g., Apple, Facebook, Google), you will need to set a password on your account before using this integration. You will still be able to use your third-party provider sign in with the Pura mobile app or on [pura.com](https://pura.com/). To do so, follow these steps in the Pura mobile app:

1. Open the Pura app, go to the `Settings` tab and note your email address.
2. Scroll down and sign out of the app.
3. On the login screen, click `Sign into your account`.
4. Click on `Forgot your password?`.
5. Enter the email from step 1 and click `Send code`.
6. Follow the steps in the Pura app to set your new password (check your email, enter the verification code and create your password). If you didn't receive a verification code, check your spam folder or request a new code.
7. Once you have successfully set a password, follow the configuration steps above.

## 🎬 Actions

The following custom actions are available:

### `start_timer`

Start a fragrance timer.

| Field         | Required | Type     | Default  | Description                                                                                                                           |
| ------------- | -------- | -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `area_id`\*   | No       | Area     | None     | The area(s) to target. If an area is specified, all Pura devices in that area will be targeted. (e.g., `living_room`).                |
| `device_id`\* | No       | Device   | None     | The device(s) to target, filtered by Pura models.                                                                                     |
| `slot`        | No       | Select   | None     | The slot (`"1"` or `"2"`) of an available fragrance. Leave blank to automatically select the fragrance with the most scent remaining. |
| `intensity`   | Yes      | Number   | 4        | The intensity of the fragrance. 1 is the lowest (subtle), and 10 is the highest (strong).                                             |
| `duration`    | Yes      | Duration | 00:30:00 | How long the diffuser should run for.                                                                                                 |

\* - Either an area_id with Pura devices or a valid Pura device_id must be supplied or an error will occur.

Example:

```yaml
action: pura.start_timer
data:
  device_id:
    - <device-id>
  slot: "1"
  intensity: 9
  duration:
    hours: 0
    minutes: 30
    seconds: 0
```

---

<!-- BEGIN AUTO-GENERATED FOOTER -->

## ❤️ Support Me

I maintain this Home Assistant integration in my spare time. If you find it useful, consider supporting development:

- 💜 [Sponsor me on GitHub](https://github.com/sponsors/natekspencer)
- ☕ [Buy me a coffee / beer](https://ko-fi.com/natekspencer)
- 💸 [PayPal (direct support)](https://www.paypal.com/paypalme/natekspencer)
- ⭐ [Star this project](https://github.com/natekspencer/ha-pura)
- 📦 If you’d like to support in other ways, such as donating hardware for testing, feel free to [reach out to me](https://github.com/natekspencer)

If you don't already own a Pura diffuser, please consider using [my referral code (JG5JN31)](http://rwrd.io/ref_JG5JN31) to get $20 off your first order of $50+ (as well as a tip to me in appreciation)!

## 📈 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=natekspencer/ha-pura)](https://www.star-history.com/#natekspencer/ha-pura)

<!-- END AUTO-GENERATED FOOTER -->
