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

These are read by the artwork normalizer, not by the panel. It composites them
onto the tile mat at exactly the configured size, so an override can be any
reasonable dimensions and does not have to be square — nothing unbounded ever
reaches the device.

The normalizer writes its output where `artwork.base_url` points. The default
is Home Assistant's own `www` folder, which needs no extra infrastructure:

```
<ha-config>/www/ma-bar/   ->   http://<ha>:8123/local/ma-bar/
```
