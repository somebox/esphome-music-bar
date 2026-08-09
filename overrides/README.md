# Artwork overrides

Your own images for library items, used ahead of whatever Music Assistant has.
They fill gaps where MA has no artwork, and replace anything of its own you
would rather not look at.

Name each file after the item's slug — lowercase, non-alphanumerics collapsed
to underscores:

```
Radio Meuh   ->  radio_meuh.png
70s Manhattan Club  ->  70s_manhattan_club.png
```

Because the slug comes from the item name, renaming something in Music
Assistant carries its override along with it.

These bypass Music Assistant's image proxy, so nothing is bounding their size
server-side — and an unbounded image is what crash-looped the original build.
Supply PNGs already sized for the tile. The generator checks dimensions and
byte size and fails on anything too large rather than shipping it.

Deploy them where `artwork.override_base_url` points. The default is Home
Assistant's own `www` folder, which needs no extra infrastructure:

```
<ha-config>/www/ma-bar/   ->   http://<ha>:8123/local/ma-bar/
```
