#!/usr/bin/env bash

# Compile SCSS
sass --style expanded styles.scss styles.css
sass --style expanded structure.scss structure.css

# https://github.com/feimosi/baguetteBox.js (MIT license)
curl -o js/lightbox/baguetteBox.css -L https://github.com/feimosi/baguetteBox.js/raw/dev/dist/baguetteBox.min.css
curl -o js/lightbox/baguetteBox.js -L https://github.com/feimosi/baguetteBox.js/raw/dev/dist/baguetteBox.min.js

# https://github.com/fatihege/downarea (MIT license)
curl -o js/markdown/downarea.css -L https://github.com/fatihege/downarea/raw/main/src/downarea.min.css
curl -o js/markdown/downarea.js -L https://github.com/fatihege/downarea/raw/main/src/downarea.min.js

# https://htmx.org/ (Zero-Clause BSD)
curl -o js/htmx.min.js -L https://unpkg.com/htmx.org@2.0.0

# https://momentjs.com/ (MIT license)
curl -o js/moment-with-locales.min.js -L https://momentjs.com/downloads/moment-with-locales.min.js

# ToDo: coolfieldset.js

# ToDo: Feather webfont
