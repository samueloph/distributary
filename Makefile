# SPDX-FileCopyrightText: 2026 Samuel Henrique <samueloph@debian.org>
# SPDX-License-Identifier: GPL-2.0-or-later OR CC-BY-SA-4.0

PYTHON ?= python3

TARGETS = svg raster hdr grub plymouth installer banners previews video website \
          downloads editor switcher unlit

all:
	$(PYTHON) build.py all

$(TARGETS):
	$(PYTHON) build.py $@

check:
	$(PYTHON) check.py

clean:
	rm -rf build

# Copy the showcase site (with the palette editor, the colour options, the
# videos and the downloads) into a static web site.  samueloph.dev keeps
# its big files in the personal_website_files repository:
#   make export-site DEST=<site>/static/personal_website_files/debian-14-artwork
# Only the videos the page shows are copied, as real files.
export-site:
	@test -n "$(DEST)" || { echo "usage: make export-site DEST=<folder>"; exit 1; }
	mkdir -p "$(DEST)/media"
	rsync -a --delete --exclude /media --exclude /downloads --exclude '*.json' website/ "$(DEST)/"
	# the page leaves out the document skeleton (claude.ai's viewer adds it); a
	# plain web server needs it
	{ printf '<!doctype html>\n<html lang="en">\n'; cat website/index.html; } > "$(DEST)/index.html"
	rsync -a --delete $$(grep -o 'media/[a-z0-9.-]*\.mp4' website/index.html | sort -u | \
	    sed 's|^media/|--include=|') --exclude='*' media/ "$(DEST)/media/"
	# wallpapers to download (./build.py [--scheme KEY] downloads), if built
	if [ -d build/downloads ]; then rsync -a --delete build/downloads/ "$(DEST)/downloads/"; fi

.PHONY: all check clean export-site $(TARGETS)
