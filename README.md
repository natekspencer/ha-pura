[![Release](https://img.shields.io/github/v/release/natekspencer/ha-pura?style=for-the-badge)](https://github.com/natekspencer/ha-pura/releases)
[![Buy Me A Coffee/Beer](https://img.shields.io/badge/Buy_Me_A_☕/🍺-F16061?style=for-the-badge&logo=ko-fi&logoColor=white&labelColor=grey)](https://ko-fi.com/natekspencer)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

![Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/total?style=flat-square)
![Latest Downloads](https://img.shields.io/github/downloads/natekspencer/ha-pura/latest/total?style=flat-square)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://brands.home-assistant.io/pura/dark_logo.png">
  <img alt="Pura logo" src="https://brands.home-assistant.io/pura/logo.png">
</picture>

# Pura for Home Assistant

Home Assistant integration for Pura smart fragrance diffusers.

## Installation

There are two main ways to install this custom component within your Home Assistant instance:

1. Using HACS (see https://hacs.xyz/ for installation instructions if you do not already have it installed):
   1. From within Home Assistant, click on the link to **HACS**
   2. Click on **Integrations**
   3. Click on the vertical ellipsis in the top right and select **Custom repositories**
   4. Enter the URL for this repository in the section that says _Add custom repository URL_ and select **Integration** in the _Category_ dropdown list
   5. Click the **ADD** button
   6. Close the _Custom repositories_ window
   7. You should now be able to see the _Pura_ card on the HACS Integrations page. Click on **INSTALL** and proceed with the installation instructions.
   8. Restart your Home Assistant instance and then proceed to the _Configuration_ section below.

2. Manual Installation:
   1. Download or clone this repository
   2. Copy the contents of the folder **custom_components/pura** into the same file structure on your Home Assistant instance
      - An easy way to do this is using the [Samba add-on](https://www.home-assistant.io/getting-started/configuration/#editing-configuration-via-sambawindows-networking), but feel free to do so however you want
   3. Restart your Home Assistant instance and then proceed to the _Configuration_ section below.

While the manual installation above seems like less steps, it's important to note that you will not be able to see updates to this custom component unless you are subscribed to the watch list. You will then have to repeat each step in the process. By using HACS, you'll be able to see that an update is available and easily update the custom component.

## Configuration

There is a config flow for this Pura integration. After installing the custom component:

1. Go to **Configuration**->**Integrations**
2. Click **+ ADD INTEGRATION** to setup a new integration
3. Search for **Pura** and click on it
4. You will be guided through the rest of the setup process via the config flow

## Troubleshooting

If you created your Pura account using one of the third-party provider options (e.g., Apple, Facebook, Google), you will need to set a password on your account before using this integration. You will still be able to use your third-party provider sign in with the Pura mobile app or on [pura.com](https://pura.com/). To do so, follow these steps in the Pura mobile app:

1. Open the Pura app, go to the `Settings` tab and note your email address.
2. Scroll down and sign out of the app.
3. On the login screen, click `Sign into your account`.
4. Click on `Forgot your password?`.
5. Enter the email from step 1 and click `Send code`.
6. Follow the steps in the Pura app to set your new password (check your email, enter the verification code and create your password). If you didn't receive a verification code, check your spam folder or request a new code.
7. Once you have successfully set a password, follow the configuration steps above.

## Actions

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

## Support Me

I'm not employed by Pura, and provide this custom component purely for your own enjoyment and home automation needs.

If you don't already own a Pura diffuser, please consider using [my referal code (JG5JN31)](http://rwrd.io/ref_JG5JN31) to get $20 off your first order of $50+ (as well as a tip to me in appreciation)!

If you already own a Pura diffuser and still want to donate, consider buying me a coffee ☕ (or beer 🍺) instead by using the link below:

<a href='https://ko-fi.com/natekspencer' target='_blank'><img height='35' style='border:0px;height:46px;' src='https://az743702.vo.msecnd.net/cdn/kofi3.png?v=0' border='0' alt='Buy Me a Coffee at ko-fi.com' />
