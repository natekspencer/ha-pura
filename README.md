<!-- BEGIN AUTO-GENERATED HEADER -->

[![Release](https://img.shields.io/github/v/release/natekspencer/ha-pura?style=for-the-badge)](https://github.com/natekspencer/ha-pura/releases)
[![HACS Badge](https://img.shields.io/badge/HACS-default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor_💜-6f42c1?style=for-the-badge&logo=github&logoColor=white&labelColor=grey)](https://github.com/sponsors/natekspencer)

![Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/total?style=flat-square)
![Latest Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/latest/total?style=flat-square)

<!-- END AUTO-GENERATED HEADER -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/pura/brand/dark_logo.png">
  <img alt="Pura logo" src="custom_components/pura/brand/logo.png">
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

## 🧩 Entities

Entities are created based on what each device supports. "Home" refers to all generations of wall diffusers.

### Controls and configuration

| Entity                    | Type   | Devices            | Description                                                                                                                                                                                                                                                                                                                           |
| ------------------------- | ------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fragrance                 | Select | Home, Plus, Mini   | The primary control. `Off` stops the diffuser and `Slot 1`/`Slot 2` runs that fragrance continuously. Only installed slots are listed. To run for a limited time, use the [`start_timer`](#start_timer) action instead.                                                                                                               |
| Intensity                 | Select | Home, Plus, Mini   | Intensity of the active fragrance: `Subtle`, `Light`, `Medium`, `Pronounced` or `Strong`. A fragrance must already be running to change it. `Off` stops the diffuser, the same as setting Fragrance to `Off`.                                                                                                                         |
| Nightlight                | Light  | Home, Mini         | The nightlight, including brightness and color.                                                                                                                                                                                                                                                                                       |
| Away mode                 | Switch | Home, Plus, Mini † | Enables Pura's own away mode, which pauses the diffuser when the phone running the Pura app leaves the area. It does **not** mean you are away. To turn diffusers off when nobody is home, use a Home Assistant automation that sets Fragrance to `Off` instead. While Pura's away mode is active, the diffuser cannot be controlled. |
| Auto-alternate fragrances | Switch | Home v4/v5, Plus † | Alternates between both fragrances. Only created for devices that support multiple diffusion modes.                                                                                                                                                                                                                                   |
| Ambient mode              | Switch | Early Pura 3       | Pura's ambient mode setting. Only available on early Pura 3 hardware (version 2); later hardware does not support it.                                                                                                                                                                                                                 |

† Created for any device that reports support for the feature, so it may also appear on other models as Pura adds support. The devices listed are those known to support it.

### Sensors

| Entity                | Devices          | Description                                                                                                                                                              |
| --------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Active fragrance      | Home, Plus       | The name of the fragrance currently running, or `None`.                                                                                                                  |
| Controller            | Home, Plus, Mini | What is currently controlling the diffuser: `Default` (manual or always on), `Schedule`, `Timer` or `Away`.                                                              |
| Timer                 | Home, Plus, Mini | When the running timer ends, if one is active.                                                                                                                           |
| Fragrance ‡           | All              | The name of the installed fragrance.                                                                                                                                     |
| Fragrance remaining ‡ | All              | The estimated percentage of fragrance remaining.                                                                                                                         |
| Runtime ‡             | All              | How long the installed fragrance has been running in total.                                                                                                              |
| Low fragrance ‡       | All              | Whether the fragrance is running low. Unavailable while the slot is empty.                                                                                               |
| Fragrance installed ‡ | Home, Plus, Mini | When the fragrance was installed. Disabled by default.                                                                                                                   |
| Fan intensity         | Car              | The fan intensity of the car diffuser.                                                                                                                                   |
| Last active           | Car              | When the car diffuser was last active.                                                                                                                                   |
| Battery               | Car              | The battery level. Only created for devices that report it, such as the Car Pro.                                                                                         |
| Connected             | Home, Plus, Mini | Whether the device is connected to Pura's cloud.                                                                                                                         |
| Firmware              | All              | An update entity showing whether newer firmware is available. Updates can be installed from Home Assistant, except for car diffusers, which update through the Pura app. |

‡ On two-slot devices (Home, Plus), these are created for each slot and include the slot number, e.g. `Slot 1 fragrance remaining`. Single-slot devices (Mini, Car) have no number.

A single **Pura** calendar entity also shows the schedules for all of your devices.

> ℹ️ Pura devices do not measure how much oil is left. Fragrance remaining is an estimate calculated by Pura based on runtime and intensity, and matches what the Pura app shows.

For a dashboard card designed for these entities, see the community-made [Pura card](https://github.com/sabourinj/ha-pura-card).

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

[![Star History Chart](https://api.star-history.com/chart?repos=natekspencer/ha-pura&type=date&legend=top-left)](https://www.star-history.com/?repos=natekspencer%2Fha-pura)

<!-- END AUTO-GENERATED FOOTER -->
