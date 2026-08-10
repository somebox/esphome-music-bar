# Adoption and onboarding

How the panel is discovered, provisioned and adopted, and the security model
behind those choices. The goal: plug it in, let Home Assistant find it, add it —
never type a Wi-Fi password into a YAML file, never paste an encryption key.

The design rule this follows: **nothing in the firmware needs editing, before or
after adoption.** Everything the panel displays — your Music Assistant player,
your favorites, your artwork URLs — arrives at runtime from Home Assistant
([spec §7](spec.md#7-runtime-architecture)), so there is nothing left that a
user would have to configure in the config itself.

## The four discovery paths, in priority order

### 1. BLE Improv — the end-user path

`esp32_improv` advertises an Improv GATT service over BLE. Home Assistant's
Bluetooth integration sees the advertisement and offers to set the panel up;
you pick your network, enter the password, and the panel joins Wi-Fi. No app, no
browser, no cable beyond power. This is what the factory firmware is built
around.

### 2. USB-CDC improv_serial — the web-flasher path

`improv_serial` speaks the same protocol over the USB-CDC serial port, so a
Chromium browser at `web.esphome.io` (or the ESPHome Device Builder) can
provision over Web Serial. This is the fallback when Bluetooth is unavailable,
and the path used straight after a browser flash.

### 3. mDNS — how Home Assistant finds it afterwards

Once on Wi-Fi, `mdns` announces `_esphomelib._tcp.local` on port 6053. Home
Assistant's ESPHome integration listens for these and surfaces the panel under
*Settings → Devices & Services → Discovered*.

### 4. Device Builder adopt

`music-bar.factory.yaml` carries a `dashboard_import:` line, so the ESPHome Device
Builder can **Take Control** of a discovered panel and build it from this repo.

## The runtime encryption key

The native API uses the Noise protocol. Since ESPHome 2025.10.0 a firmware can
ship with no baked-in key (`api: encryption:` with no `key:`):

1. The panel compiles with both plaintext and Noise support, and no PSK in flash.
2. On first connect it accepts a plaintext API connection and reports
   `api_encryption_supported` in its device info.
3. Home Assistant generates a fresh 32-byte PSK and sends it with the
   `noise_encryption_set_key` RPC.
4. The panel persists it and disables plaintext. Only a factory reset removes it.

So one factory binary can be flashed to every panel, and each ends up with a
unique key assigned at adoption. No `secrets.yaml`, no `openssl rand`, no
per-device YAML edit.

Upstream references:

- Runtime PSK: <https://github.com/esphome/esphome/pull/7296>
- Native API component: <https://esphome.io/components/api/>
- Improv Wi-Fi standard: <https://www.improv-wifi.com/>
- Made for ESPHome: <https://esphome.io/guides/made_for_esphome/>

## Why `import_full_config` is false

`music-bar.factory.yaml` includes the base with a local `!include`, and sets
`import_full_config: false`.

With it **true**, the Device Builder copies the factory file's *text* into the
user's own config — and the `!include` inside it would then point at a file
they do not have. With it **false**, the adopted config references the factory
file as a remote package instead; ESPHome clones the repo to resolve it, so the
include resolves along with it. Made for ESPHome explicitly permits remote
packages in an adopted config.

The trade is that an adopted panel gets a thin config that tracks this repo,
rather than an inlined copy to edit in place. Anyone who wants to change the
LVGL layout clones the repo and builds `music-bar.example.yaml`.

## The handshake, and the toggle it exists for

Home Assistant's per-device **"Allow the device to perform Home Assistant
actions"** toggle defaults *off* on recent releases, and silently no-ops every
call the panel makes — with nothing logged anywhere. Buttons visibly react and
nothing happens. It is the single most likely thing to go wrong on a fresh
install, and it looks exactly like a firmware bug.

The panel cannot read that setting, but it can notice that nobody answered. It
fires an `esphome.music_bar_hello` event; the blueprint answers by calling the
panel's `hello_ack` action. If no answer arrives, the panel says so — on its own
screen, and in the **Setup Status** diagnostic sensor in Home Assistant.

It asks repeatedly rather than once, because there are two windows early in a
connection where an event is discarded and neither is visible to the panel.
Both were hit on hardware:

- Wi-Fi connects several seconds before the API client attaches, and an event
  fired then is dropped with *"no client connected"*. This is why the handshake
  triggers on `api: on_client_connected` rather than on `wifi: on_connect`.
- The client attaches before it subscribes to actions, and an event fired in
  *that* window is dropped with *"client has not subscribed to actions (yet)"*.

So the panel retries until it is answered, and stops as soon as it is. Firing on
client connect also means a Home Assistant restart re-runs the handshake without
anyone pressing Retry.

**Importing the blueprints is not enough.** A blueprint is a template; nothing
answers until an automation has been created from it. A panel that reports
Home Assistant never answered, on an install where the toggle is on and the
blueprints are imported, has almost always got no automation instance.

There is a **Retry Home Assistant Handshake** button for checking after you flip
the toggle, so this does not need a reboot to confirm.

## Security model

### API — open for one adoption window, then Noise-only

Accepted. The plaintext window exists only until Home Assistant adopts the panel
and stores a key; afterwards plaintext is refused and cannot be re-enabled
without a factory reset. Adoption happens on the trusted LAN.

### OTA — open on the LAN, for the life of the device

ESPHome has no runtime OTA-password adoption flow, so the factory firmware's
`ota:` block has no password and anyone on the LAN can push firmware to the
panel. Mitigations: OTA needs LAN access, and **Safe Mode** and **Factory
Reset** buttons exist for recovery. A project-wide OTA password would have to be
baked into the factory binary, which breaks the single-firmware goal. Recorded
as accepted risk on the trusted-LAN model, not as solved.

### Fallback AP — open, captive portal only

`wifi: ap: {}` comes up only if Wi-Fi fails, and serves only the provisioning
page.

### Web server — off

Not enabled. Home Assistant is the interface, and the panel wants its RAM for
the framebuffer. The block is commented in `music-bar.base.yaml` for anyone who
wants it; it has no `auth:` as written.

## Made for ESPHome checklist

Logos only after Open Home Foundation approval — do not display them yet.

| Requirement | Status |
|---|---|
| Runs ESPHome on an ESP32-S3 | Yes |
| Open-source config users can modify | Yes (`esphome/`) |
| `esp32_improv` + `improv_serial` | Yes |
| `dashboard_import`, no secrets, no static network config | Yes (`music-bar.factory.yaml`) |
| Valid and runs with no user changes after adopt | Yes — all content arrives at runtime |
| Every component has an `id` | Yes |
| Product name does not contain "ESPHome" | Yes ("Music Bar") |
| Users can apply updates to ready-made devices | Partial — ESPHome OTA from HA works; HTTP self-update and a web-flasher binary need a published release |

## Open questions

1. **BLE's RAM cost against the framebuffer.** The factory image already uses
   42.2% of internal RAM with no display in it. `esp32_improv` is part of that,
   and the LVGL draw buffers are not yet. If the display port comes up short,
   moving BLE provisioning behind a build flag is the first thing to try. Folded
   into the phase-1 probe.
2. **Improv authorizer for dev units.** `authorizer: none` means anyone in BLE
   range of an unprovisioned panel can provision it. Fine for a retail unit out
   of the box, arguably not for a bench unit that gets reflashed often.
3. **Hosted manifest URL** for HTTP self-update, rather than
   `raw.githubusercontent.com`.
4. **Runtime OTA password** — waiting on upstream ESPHome.
