# static/images/* and how they are used

`apple-touch-icon.png`
  * This is a transparent background .png file intended to be used for iOS the Progressive Web Application (PWA) of Piefed.

`favicon-16x16.png` and `favicon-32x32.png`
  * This is a transparent background .png used as the tiny icons in browser tabs.
  * This one is exported from the `piefed_logo_nav_t_300x300.svg` vector file using Inkscape.

`favicon.ico`
  * This is an icon file for windows, with multiple sized icons inside it.
  * It was created using the command:
  `convert -density 300 -define icon:auto-resize=512,256,192,128,96,64,48,32,16 -background none piefed_logo_full_t_300x300.svg favicon.ico`

`fediverse_logo.svg`
  * This is a vector file at 196 pixels by 196 pixels. It is used on the user profile pages.

`menu.svg`
  * This is a vector file at 75 pixels width by 78 pixels height.
  * It is used in the css.

`mstile-150x150.png`
  * This is a transparent background .png used in the `static/browserconfig.xml` file.
  * It is used for Windows systems as part of the config for [Pinned Sites](https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/platform-apis/hh772707(v=vs.85))

`piefed_logo_icon_t_256x256.svg`
  * This is the base vector file used to create the `piefed_logo_icon_t_*.png` files.

`piefed_logo_icon_t_*.png`
  * These are transparent background .png files used for app icons for non-iOS Progressive Web Application versions of Piefed.
  * These are exported from the `piefed_logo_icon_t_256x256.svg` vector file using Inkscape.

`piefed_logo_icon_t_75.png`
  * This is a transparent background .png file at 75 pixels by 75 pixels.
  * It was exported from the `piefed_logo_full_t_300x300.svg` vector file using Inkscape.
  * It is used in multiple places in the code base.

`piefed_logo_full_t_300x300.svg`
  * This is a vector file at 300 pixels by 300 pixels.
  * It is used for the website's default navigation banner logo.
  * This can be overridden by uploading a new icon in the admin interface, under the "Site" tab.
