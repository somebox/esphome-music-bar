# Artwork overrides

Your own images for library items. They fill gaps where Music Assistant has no
artwork, and replace anything of its own you would rather not look at.

## Where they go

Here, by default — `overrides/` in your clone. Keeping them beside the config
means they are version controlled and backed up along with everything else, and
the normalizer reads them straight from disk.

If the normalizer runs somewhere you would rather not clone into, point
`artwork.overrides_dir` at any directory it can read. A folder on the Home
Assistant host works well, since you can already reach it over Samba, the File
Editor add-on, or SSH.

This is the **input** folder. Do not point it at `artwork.output_dir`, which
the normalizer writes into and manages.

## Adding one

Find out which items need help:

```bash
scripts/normalize-artwork.py --report
```

Items marked `gen` have no artwork anywhere and are currently showing a
generated monogram. The report ends with the exact filenames to create.

Drop the image in here named after the item's slug, and run the normalizer
again:

```
WKCR                ->  wkcr.png
Radio Meuh          ->  radio_meuh.png
Fréquence K         ->  frequence_k.png      (accents fold to ASCII)
70s Manhattan Club  ->  70s_manhattan_club.png
```

`.png`, `.jpg`, `.jpeg`, `.webp` and `.gif` all work. Any size, any aspect
ratio, transparent or not — the normalizer fits it to the tile, pads it onto
the mat rather than cropping, flattens transparency and rounds the corners.
Nothing unbounded ever reaches the panel, so a 4000px scan is fine to drop in.

Because the slug comes from the item name, **renaming an item in Music
Assistant orphans its override** — the new name makes a new slug, and the old
filename stops matching. The normalizer notices and tells you which files match
nothing, so the fix is renaming the file to match. The gallery page will also
show the item back on a monogram, with the filename it now wants.

## Changing one

Replace the file and run the normalizer again. The panel picks it up on its
next page turn, with no reflash and no restart.

That works because the normalizer fingerprints each tile's contents into the
manifest, and Home Assistant appends that fingerprint to the URL it pushes to
the device. New bytes mean a new URL, and a new URL is the only thing that
makes the device refetch — the filename alone never changes, so without this a
swapped override would go unnoticed until reboot.

## What gets generated

Every item resolves to something, so no tile is ever blank or broken:

1. your file here, if there is one
2. Music Assistant's artwork, if the proxy actually returns an image
3. a monogram — the item's initials on a colour derived from its name

The monogram is deterministic, so an item keeps the same colour across runs,
and different items get different colours rather than a row of identical
placeholder icons.
