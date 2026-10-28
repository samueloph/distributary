# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0

PYTHON ?= python3

TARGETS = svg raster hdr grub plymouth installer banners previews video website \
          downloads editor switcher

all:
	$(PYTHON) build.py all

$(TARGETS):
	$(PYTHON) build.py $@

check:
	$(PYTHON) check.py

clean:
	rm -rf build

# Copy the showcase site (with the palette editor, the colour options and
# the videos) into a static web site.  samueloph.dev serves it from the
# personal_website_files repository, a GitHub Pages site of its own:
#   make export-site DEST=<personal_website_files>/debian-distributary-theme
# Only the videos the page shows are copied, as real files.
export-site:
	@test -n "$(DEST)" || { echo "usage: make export-site DEST=<folder>"; exit 1; }
	mkdir -p "$(DEST)/media"
	rsync -a --delete --exclude /media --exclude '*.json' website/ "$(DEST)/"
	# the page leaves out the document skeleton (claude.ai's viewer adds it); a
	# plain web server needs it
	{ printf '<!doctype html>\n<html lang="en">\n'; cat website/index.html; } > "$(DEST)/index.html"
	# one version in the URLs of the page's and the editor's data, and of the
	# links between them, so a browser never pairs a new page with old data
	v=$$(cat website/index.html website/editor/index.html website/schemes/index.js \
	    website/editor/data/river.js | sha1sum | cut -c1-10); \
	sed -i "s|schemes/index.js\"|schemes/index.js?v=$$v\"|; s|editor/index.html|editor/index.html?v=$$v|g" \
	    "$(DEST)/index.html" && \
	sed -i "s|data/river.js\"|data/river.js?v=$$v\"|; s|\"\.\./index.html\"|\"../index.html?v=$$v\"|" \
	    "$(DEST)/editor/index.html"
	rsync -a --delete $$(grep -o 'media/[a-z0-9.-]*\.mp4' website/index.html | sort -u | \
	    sed 's|^media/|--include=|') --exclude='*' media/ "$(DEST)/media/"

# The wallpapers to download (./build.py [--scheme KEY] downloads) go to a
# site of their own, samueloph.dev/distributary-wallpapers/ (DL_BASE in
# website/index.html): with every colour they are 712 MB, and a GitHub Pages
# site holds 1 GB.  Its .git, .nojekyll and index.html stay; everything else
# at its top level mirrors build/downloads/:
#   make export-downloads DEST=<distributary-wallpapers>
export-downloads:
	@test -n "$(DEST)" || { echo "usage: make export-downloads DEST=<folder>"; exit 1; }
	@test -d build/downloads || { echo "no build/downloads: run ./build.py [--scheme KEY] downloads"; exit 1; }
	rsync -a --delete --exclude /.git --exclude /.nojekyll --exclude /index.html \
	    build/downloads/ "$(DEST)/"

.PHONY: all check clean export-site export-downloads $(TARGETS)
