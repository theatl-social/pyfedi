#!/usr/bin/env bash

# Compile SCSS
sass --style expanded styles.scss styles.css

# https://github.com/feimosi/baguetteBox.js (MIT license)
curl -o js/lightbox/baguetteBox.css -L https://github.com/feimosi/baguetteBox.js/raw/dev/dist/baguetteBox.min.css
curl -o js/lightbox/baguetteBox.js -L https://github.com/feimosi/baguetteBox.js/raw/dev/dist/baguetteBox.min.js

# https://github.com/fatihege/downarea (MIT license)
curl -o js/markdown/downarea.css -L https://codeberg.org/PieFed/downarea2/raw/branch/main/src/downarea.css
curl -o js/markdown/downarea.js -L https://codeberg.org/PieFed/downarea2/raw/branch/main/src/downarea.js

# https://htmx.org/ (Zero-Clause BSD)
curl -o js/htmx.min.js -L https://unpkg.com/htmx.org@2.0.0


# ToDo: coolfieldset.js

# ToDo: Feather webfont
