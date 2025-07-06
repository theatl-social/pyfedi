if(!setTheme) {
    const setTheme = theme => {
        if (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
          document.documentElement.setAttribute('data-bs-theme', 'dark')
        } else {
          document.documentElement.setAttribute('data-bs-theme', theme)
        }
    }
}

// fires after DOM is ready for manipulation
document.addEventListener("DOMContentLoaded", function () {
    if(navigator.getBattery) {
        navigator.getBattery().then(function(battery) {
            // Only load youtube videos in teasers if there is plenty of power available
            if (battery.charging) {
                setupYouTubeLazyLoad();
            }
        });
    }
    setupVotingLongPress();
    setupVotingDialogHandlers();
    setupCommunityNameInput();
    setupShowMoreLinks();
    setupConfirmFirst();
    setupSendPost();
    setupSubmitOnInputChange();
    setupTimeTracking();
    setupMobileNav();
    setupLightDark();
    setupKeyboardShortcuts();
    setupTopicChooser();
    setupConversationChooser();
    setupMarkdownEditorEnabler();
    setupAddPollChoice();
    setupShowElementLinks();
    setupLightboxTeaser();
    setupLightboxPostBody();
    setupPostTeaserHandler();
    setupPostTypeSwitcher();
    setupSelectNavigation();
    setupUserPopup();
    preventDoubleFormSubmissions();
    setupSelectAllCheckbox();
    setupFontSizeChangers();
    setupAddPassKey();
    setupFancySelects();
    setupImagePreview();
    setupNotificationPermission();
    setupFederationModeToggle();
    setupMegaMenuNavigation();
    setupPopupCommunitySidebar();
    setupVideoSpoilers();
    setupDynamicContentObserver();
    setupCommunityFilter();
    setupPopupTooltips();

    // save user timezone into a timezone field, if it exists
    const timezoneField = document.getElementById('timezone');
    if(timezoneField && timezoneField.type === 'hidden') {
        timezoneField.value = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    // iOS doesn't support beforeinstallprompt, so detect iOS and show PWA button manually
    if(/iPad|iPhone|iPod/.test(navigator.userAgent)) {
        document.getElementById('btn_add_home_screen').style.display = 'inline-block';
        document.body.classList.add('ios');
    }

});


function setupUserPopup() {
    document.querySelectorAll('.render_username .author_link').forEach(anchor => {
        let timeoutId;

        anchor.addEventListener('mouseover', function() {
            timeoutId = setTimeout(function () {
                anchor.nextElementSibling.classList.remove('d-none');
            }, 1000);
        });

        anchor.addEventListener('mouseout', function() {
            clearTimeout(timeoutId);

            let userPreview = anchor.closest('.render_username').querySelector('.user_preview');
            if (userPreview) {
                userPreview.classList.add('d-none');
            }
        });
    });
}
function setupPostTeaserHandler() {
    document.querySelectorAll('.post_teaser_clickable').forEach(div => {
        div.onclick = function() {
            const firstAnchor = this.parentElement.querySelector('h3 a');
            if (firstAnchor) {
                window.location.href = firstAnchor.href;
            }
        };
    });
}

function setupPostTypeSwitcher() {
    document.querySelectorAll('#type_of_post a').forEach(a => {
        a.onclick = function() {
            setCookie('post_title', document.getElementById('title').value, 0.1);
            setCookie('post_description', document.getElementById('body').value, 0.1);
            setCookie('post_tags', document.getElementById('tags').value, 0.1);
        };
    });

    var typeSwitcher = document.getElementById('type_of_post');
    var title = document.getElementById('title');
    var body = document.getElementById('body');
    var tags = document.getElementById('tags');
    if(typeSwitcher && title && body && tags) {
        var cookie_title = getCookie('post_title');
        var cookie_description = getCookie('post_description');
        var cookie_tags = getCookie('post_tags');
        if(cookie_title)
            title.value = cookie_title;
        if(cookie_description)
            body.value = cookie_description;
        if(cookie_tags)
            tags.value = cookie_tags;
    }
}

function setupSelectNavigation() {
    document.querySelectorAll("select.navigate_on_change").forEach(select => {
        select.addEventListener("change", function () {
            if (this.value) {
                window.location.href = this.value;
            }
        });
    });
}

function setupYouTubeLazyLoad() {
    const lazyVideos = document.querySelectorAll(".video-wrapper");

    if ("IntersectionObserver" in window) {
        let videoObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    let videoWrapper = entry.target;
                    let iframe = document.createElement("iframe");
                    iframe.src = videoWrapper.getAttribute("data-src");
                    iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen";

                    videoWrapper.innerHTML = "";
                    videoWrapper.appendChild(iframe);

                    videoObserver.unobserve(videoWrapper);
                }
            });
        }, {
            rootMargin: "0px 0px 300px 0px" // Preload when 300px away from the viewport
        });

        lazyVideos.forEach((video) => {
            videoObserver.observe(video);
        });
    } else {
        // Fallback for older browsers
        lazyVideos.forEach((video) => {
            let iframe = document.createElement("iframe");
            iframe.src = video.getAttribute("data-src");
            iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen";

            video.innerHTML = "";
            video.appendChild(iframe);
        });
    }
}

// All elements with the class "showElement" will show the DOM element referenced by the data-id attribute
function setupShowElementLinks() {
    var elements = document.querySelectorAll('.showElement');
    elements.forEach(function(element) {
        element.addEventListener('click', function(event) {
            event.preventDefault();
            var dataId = this.getAttribute('data-id');
            var targetElement = document.getElementById(dataId);
            if (targetElement) {
                targetElement.style.display = 'inherit';
            }
        });
    });
}

function renderMasonry(masonry, htmlSnippets) {
      const mainPane = document.querySelector('.main_pane');
      const mainPaneWidth = mainPane.offsetWidth;
      let numColumns;

      if (mainPaneWidth < 600) {
          numColumns = 2; // 2 columns for mobile
      } else if (mainPaneWidth < 992) {
          numColumns = 3; // 3 columns for phablet
      } else if (mainPaneWidth < 1200) {
          numColumns = 4; // 4 columns for tablet or laptop
      } else {
          numColumns = 5; // 5 columns for larger screens
      }
      const columns = [];

      // Create and append column divs
      for (let i = 0; i < numColumns; i++) {
        const column = document.createElement('div');
        column.classList.add('column');
        masonry.appendChild(column);
        columns.push(column);
      }

      // Distribute HTML snippets to columns
      htmlSnippets.forEach(function(htmlSnippet, index) {
        const columnIndex = index % numColumns;
        const column = columns[columnIndex];
        const item = document.createElement('div');
        item.innerHTML = htmlSnippet;
        column.appendChild(item);
      });

      setupLightboxGallery();
}

function setupLightboxGallery() {
    // Check if there are elements with either "post_list_masonry_wide" or "post_list_masonry" class
    var galleryPosts = document.querySelectorAll('.masonry');

    // Enable lightbox on masonry images
    if (galleryPosts.length > 0) {
        baguetteBox.run('.masonry', {
            fullScreen: false,
            titleTag: true,
            preload: 5,
            captions: function(element) {
                return element.getElementsByTagName('img')[0].title;
            }
        });
    }
}


function setupLightboxTeaser() {
    if(typeof baguetteBox !== 'undefined') {
        function popStateListener(event) {
            baguetteBox.hide();
        };
        function baguetteBoxClickImg(event) {
          if (this.style.width != "100vw" && this.offsetWidth < window.innerWidth) {
            this.style.width = "100vw";
            this.style.maxHeight = "none";
          } else {
            baguetteBox.hide();
          }
        };
        baguetteBox.run('.post_teaser', {
            fullScreen: false,
            noScrollbars: true,
            async: true,
            preload: 3,
            ignoreClass: 'preview_image',
            afterShow: function() {
                window.history.pushState('#lightbox', document.title, document.location+'#lightbox');
                window.addEventListener('popstate', popStateListener);
                for (const el of document.querySelectorAll('div#baguetteBox-overlay img')) {
                  el.addEventListener('click', baguetteBoxClickImg);
                }
            },
            afterHide: function() {
                if (window.history.state === '#lightbox') {
                  for (const el of document.querySelectorAll('div#baguetteBox-overlay img')) {
                    el.style.width = "";
                    el.style.maxHeight = "";
                    el.removeEventListener('click', baguetteBoxClickImg);
                  }
                  window.removeEventListener('popstate', popStateListener);
                  window.history.back();
                }
            },
        });
    }

}

function setupLightboxPostBody() {
    if(typeof baguetteBox !== 'undefined') {
        const images = document.querySelectorAll('.post_body img');
        images.forEach(function(img) {
            const parent = img.parentNode;
            const link = document.createElement('a');
            link.href = img.src;
            link.setAttribute('data-caption', img.alt);
            parent.replaceChild(link, img);
            link.appendChild(img);
        });

        baguetteBox.run('.post_body', {
            fullScreen: false,
            titleTag: true,
            async: true,
            preload: 3
        });
    }

}

// fires after all resources have loaded, including stylesheets and js files
window.addEventListener("load", function () {
    setupHideButtons();
});

function setupMobileNav() {
    var navbarToggler = document.getElementById('navbar-toggler');
    var navbarSupportedContent = document.getElementById('navbarSupportedContent');
    navbarToggler.addEventListener("click", function(event) {
        toggleClass('navbarSupportedContent', 'show_menu');
        var isExpanded = navbarSupportedContent.classList.contains('show_menu');
        navbarToggler.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        navbarSupportedContent.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
    });
    if(window.innerWidth < 992) {
        navbarToggler.setAttribute('aria-expanded', 'false');
    }
}

function setupLightDark() {
    const elem = document.getElementById('color_mode');
    const icon = document.getElementById('color_mode_icon');

    const showActiveTheme = (theme) => {
        if (theme === 'dark') {
            elem.setAttribute('aria-label', 'Light mode');
            elem.setAttribute('title', 'Light mode');
            elem.setAttribute('data-bs-theme-value', 'light');
            icon.classList.remove('fe-moon');
            icon.classList.add('fe-sun');
        } else {
            elem.setAttribute('aria-label', 'Dark mode');
            elem.setAttribute('title', 'Dark mode');
            elem.setAttribute('data-bs-theme-value', 'dark');
            icon.classList.remove('fe-sun');
            icon.classList.add('fe-moon');
        }
    };

    elem.addEventListener("click", function(event) {
        const theme = elem.getAttribute('data-bs-theme-value');
        setStoredTheme(theme);
        setTheme(theme);
        showActiveTheme(theme);
    });

    var preferredTheme = getStoredTheme();
    if (!preferredTheme || (preferredTheme !== 'light' && preferredTheme !== 'dark')) {
        preferredTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    //setTheme(preferredTheme);
    icon.classList.remove('fe-eye');
    showActiveTheme(preferredTheme);
}

function toggleClass(elementId, className) {
  var element = document.getElementById(elementId);

  if (element.classList.contains(className)) {
    // If the element has the class, remove it
    element.classList.remove(className);
  } else {
    // If the element doesn't have the class, add it
    element.classList.add(className);
  }
}

function findOutermostParent(element, className) {
  while (element && !element.classList.contains(className)) {
    element = element.parentNode;
  }
  return element;
}

function setupAutoResize(element) {
    const elem = document.getElementById(element);
    elem.addEventListener("keyup", function(event) {
        const outerWrapper = findOutermostParent(elem, 'downarea');
        elem.style.height = 'auto'; // Reset height to auto to calculate scrollHeight accurately
        elem.style.height = (elem.scrollHeight + 2) + 'px'; // Add 2px to avoid cutting off text
        outerWrapper.style.height = (elem.scrollHeight + 61) + 'px';
    });

}


// disabled for now
function setupImageExpander() {
    // Get all elements with the class "preview_image"
    var imageLinks = document.querySelectorAll('.preview_image');

    // Loop through each element and attach a click event listener
    imageLinks.forEach(function(link) {
      link.addEventListener('click', function(event) {
        event.preventDefault(); // Prevent the default behavior of the anchor link

        // Check if the image is already visible
        var image = this.nextElementSibling; // Assumes the image is always the next sibling
        var isImageVisible = image && image.style.display !== 'none';

        // Toggle the visibility of the image
        if (isImageVisible) {
          image.remove(); // Remove the image from the DOM
        } else {
          image = document.createElement('img');
          image.src = this.href; // Set the image source to the href of the anchor link
          image.alt = 'Image'; // Set the alt attribute for accessibility
          image.className = 'preview_image_shown';

          // Add click event listener to the inserted image
          image.addEventListener('click', function() {
            // Replace location.href with the URL of the clicked image
            window.location.href = image.src;
          });

          // Insert the image after the anchor link
          this.parentNode.insertBefore(image, this.nextSibling);
        }

        // Toggle a class on the anchor to indicate whether the image is being shown or not
        this.classList.toggle('imageVisible', !isImageVisible);
      });
    });
}

function collapseReply(comment_id) {
    const reply = document.getElementById('comment_' + comment_id);
    let isHidden = false;
    if(reply) {
        const hidables = parentElement.querySelectorAll('.hidable');

        hidables.forEach(hidable => {
            hidable.style.display = isHidden ? 'block' : 'none';
        });

        const moreHidables = parentElement.parentElement.querySelectorAll('.hidable');
        moreHidables.forEach(hidable => {
            hidable.style.display = isHidden ? 'block' : 'none';
        });

        // Toggle the content of hideEl
        if (isHidden) {
            hideEl.innerHTML = "<a href='#'>[-] hide</a>";
        } else {
            hideEl.innerHTML = "<a href='#'>[+] show</a>";
        }

        isHidden = !isHidden; // Toggle the state
    }
}

// every element with the 'confirm_first' class gets a popup confirmation dialog
function setupConfirmFirst() {
    const show_first = document.querySelectorAll('.confirm_first');
    show_first.forEach(element => {
        element.addEventListener("click", function(event) {
            if (!confirm("Are you sure?")) {
              event.preventDefault(); // As the user clicked "Cancel" in the dialog, prevent the default action.
              event.stopImmediatePropagation(); // Stop other event listeners from running
              event.action_cancelled = true; // Custom flag for setupSendPost handlers
            }
        }, true); // Use capture phase to run before other handlers
    });

    const go_back = document.querySelectorAll('.go_back');
    go_back.forEach(element => {
        element.addEventListener("click", function(event) {
            history.back();
            event.preventDefault();
            return false;
        });
    })

    const redirect_login = document.querySelectorAll('.redirect_login');
    redirect_login.forEach(element => {
        element.addEventListener("click", function(event) {
            location.href = '/auth/login';
            event.preventDefault();
            return false;
        });
    });
}

// Handle custom POST requests for destructive actions
function setupSendPost() {
    const sendPostElements = document.querySelectorAll('a.send_post');
    sendPostElements.forEach(element => {
        element.addEventListener("click", function(event) {
            // Check if the event was cancelled by confirm_first
            if (event.action_cancelled) {
                return;
            }
            
            event.preventDefault();
            
            const url = element.getAttribute('data-url');
            if (!url) return;
            
            // Get CSRF token from meta tag
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
            
            // Create a form and submit it to preserve flash messages
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = url;
            form.style.display = 'none';
            
            // Add CSRF token as hidden input
            const tokenInput = document.createElement('input');
            tokenInput.type = 'hidden';
            tokenInput.name = 'csrf_token';
            tokenInput.value = csrfToken;
            form.appendChild(tokenInput);
            
            document.body.appendChild(form);
            form.submit();
        });
    });
}

function setupSubmitOnInputChange() {
    const inputElements = document.querySelectorAll('.submit_on_change');

    inputElements.forEach(element => {
        element.addEventListener("change", function() {
            const form = findParentForm(element);
            if (form) {
                form.submit();
            }
        });
    });
}

// Find the parent form of an element
function findParentForm(element) {
    let currentElement = element;
    while (currentElement) {
        if (currentElement.tagName === 'FORM') {
            return currentElement;
        }
        currentElement = currentElement.parentElement;
    }
    return null;
}

function setupShowMoreLinks() {
    const comments = document.querySelectorAll('.comment');

    comments.forEach(comment => {
        const content = comment.querySelector('.limit_height');
        if (content && content.clientHeight > 400) {
            content.style.overflow = 'hidden';
            content.style.maxHeight = '400px';
            const showMoreLink = document.createElement('a');
            showMoreLink.classList.add('show-more');
            showMoreLink.classList.add('hidable');
            showMoreLink.innerHTML = '<i class="fe fe-angles-down" title="Read more"></i>';
            showMoreLink.href = '#';
            showMoreLink.addEventListener('click', function(event) {
                event.preventDefault();
                content.classList.toggle('expanded');
                if (content.classList.contains('expanded')) {
                    content.style.overflow = 'visible';
                    content.style.maxHeight = '';
                    showMoreLink.innerHTML = '<i class="fe fe-angles-up" title="Collapse"></i>';
                } else {
                    content.style.overflow = 'hidden';
                    content.style.maxHeight = '400px';
                    showMoreLink.innerHTML = '<i class="fe fe-angles-down" title="Read more"></i>';
                }
            });
            content.insertAdjacentElement('afterend', showMoreLink);
        }
    });
}

function setupCommunityNameInput() {
   var communityNameInput = document.getElementById('community_name');

   if (communityNameInput) {
       communityNameInput.addEventListener('keyup', function() {
          var urlInput = document.getElementById('url');
          urlInput.value = titleToURL(communityNameInput.value);
       });
   }
}


function setupHideButtons() {
    const hideEls2 = document.querySelectorAll('.hide_button a');
    hideEls2.forEach(hideEl => {
        let isHidden = false;

        hideEl.addEventListener('click', event => {
            event.preventDefault();
            const parentElement = hideEl.parentElement.parentElement;
            const hidables = parentElement.parentElement.querySelectorAll('.hidable');

            hidables.forEach(hidable => {
                hidable.style.display = 'none';
            });

            const unhide = parentElement.parentElement.querySelectorAll('.unhide');
            unhide[0].style.display = 'inline-block';
        });
    });

    const showEls = document.querySelectorAll('a.unhide');
    showEls.forEach(showEl => {
        showEl.addEventListener('click', event => {
            event.preventDefault();
            showEl.style.display = 'none';
            const hidables = showEl.parentElement.parentElement.parentElement.querySelectorAll('.hidable');
            hidables.forEach(hidable => {
                hidable.style.display = '';
            });
        });
    });

    if(typeof toBeHidden !== "undefined" && toBeHidden) {
        toBeHidden.forEach((arrayElement) => {
          // Build the ID of the outer div
          const divId = "comment_" + arrayElement;

          // Access the outer div by its ID
          const commentDiv = document.getElementById(divId);

          if (commentDiv) {
            // Access the inner div with class "hide_button" inside the outer div
            const hideButton = commentDiv.querySelectorAll(".hide_button a");

            if (hideButton) {
              // Programmatically trigger a click event on the "hide_button" anchor
              hideButton[0].click();
            } else {
              console.log(`"hide_button" not found in ${divId}`);
            }
          } else {
            console.log(`Div with ID ${divId} not found`);
          }
        });
    }
}

function titleToURL(title) {
  // Convert the title to lowercase and replace spaces with hyphens
  return title.toLowerCase().replace(/\s+/g, '_');
}

var timeTrackingInterval;
var currentlyVisible = true;

function setupTimeTracking() {
    // Check for Page Visibility API support
    if (document.visibilityState) {
        const lastUpdate = new Date(localStorage.getItem('lastUpdate')) || new Date();

       // Initialize variables to track time
       let timeSpent = parseInt(localStorage.getItem('timeSpent')) || 0;

       displayTimeTracked();

       timeTrackingInterval = setInterval(() => {
          timeSpent += 2;
          localStorage.setItem('timeSpent', timeSpent);
          // Display timeSpent
          displayTimeTracked();
       }, 2000)


       // Event listener for visibility changes
       document.addEventListener("visibilitychange", function() {
          const currentDate = new Date();

          if (currentDate.getMonth() !== lastUpdate.getMonth() || currentDate.getFullYear() !== lastUpdate.getFullYear()) {
            // Reset counter for a new month
            timeSpent = 0;
            localStorage.setItem('timeSpent', timeSpent);
            localStorage.setItem('lastUpdate', currentDate.toString());
            displayTimeTracked();
          }

          if (document.visibilityState === "visible") {
              console.log('visible')
              currentlyVisible = true
              timeTrackingInterval = setInterval(() => {
                  timeSpent += 2;
                  localStorage.setItem('timeSpent', timeSpent);
                  displayTimeTracked();
              }, 2000)
          } else {
              currentlyVisible = false;
              if(timeTrackingInterval) {
                 clearInterval(timeTrackingInterval);
              }
          }
       });
    }
}

var currentPost;                        // keep track of which is the current post. Set by mouse movements (see const votableElements) and by J and K key presses
var showCurrentPost = false;    // when true, the currently selected post will be visibly different from the others. Set to true by J and K key presses

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        if (document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
            if(document.activeElement.classList.contains('skip-link')) {
                return;
            }
            // Don't intercept keyboard shortcuts when modifier keys are pressed
            if (event.ctrlKey || event.metaKey || event.altKey) {
                return;
            }
            var didSomething = false;
            if(event.shiftKey && event.key === '?') {
                location.href = '/keyboard_shortcuts';
                didSomething = true;
            } else if (event.key === 'a') {
                if(currentPost) {
                    currentPost.querySelector('.upvote_button').click();
                    didSomething = true;
                }
            } else if (event.key === 'z') {
                if(currentPost) {
                    currentPost.querySelector('.downvote_button').click();
                    didSomething = true;
                }
            } else if (event.key === 'x') {
                if(currentPost) {
                    currentPost.querySelector('.preview_image').click();
                    didSomething = true;
                }
            } else if (event.key === 'l') {
                if (currentPost) {
                    currentPost.querySelector('.post_link').click();
                    didSomething = true;
                }
            } else if (event.key === 'Enter') {
                if(currentPost && document.activeElement.tagName !== 'a') {
                    var target_element = currentPost.querySelector('.post_teaser_title_a');
                    if(target_element == null && (document.activeElement.classList.contains('upvote_button') || document.activeElement.classList.contains('downvote_button'))) {
                        target_element = document.activeElement;
                    }
                    if(target_element)
                        target_element.click();
                    didSomething = true;
                }
            } else if (event.key === 'j') {
                showCurrentPost = true;
                if(currentPost) {
                    if(currentPost.nextElementSibling) {
                        var elementToRemoveClass = document.querySelector('.post_teaser.current_post');
                        if(elementToRemoveClass)
                            elementToRemoveClass.classList.remove('current_post');
                        currentPost = currentPost.nextElementSibling;
                        currentPost.classList.add('current_post');
                    }
                    didSomething = true;
                }
                else {
                    currentPost = document.querySelector('.post_teaser');
                    currentPost.classList.add('current_post');
                }
                // Check if the current post is out of the viewport
                var rect = currentPost.getBoundingClientRect();
                if (rect.bottom > window.innerHeight || rect.top < 0) {
                    currentPost.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            } else if (event.key === 'k') {
                showCurrentPost = true;
                if(currentPost) {
                    if(currentPost.previousElementSibling) {
                        var elementToRemoveClass = document.querySelector('.post_teaser.current_post');
                        if(elementToRemoveClass)
                            elementToRemoveClass.classList.remove('current_post');
                        currentPost = currentPost.previousElementSibling;
                        currentPost.classList.add('current_post');
                    }
                    didSomething = true;
                }
                else {
                    currentPost = document.querySelector('.post_teaser');
                    currentPost.classList.add('current_post');
                }
                // Check if the current post is out of the viewport
                var rect = currentPost.getBoundingClientRect();
                if (rect.bottom > window.innerHeight || rect.top < 0) {
                    currentPost.scrollIntoView({ behavior: 'smooth', block: 'end' });
                }
            }
            if(didSomething) {
                event.preventDefault();
            }
        }

        // While typing a post or reply, Ctrl + Enter (or Cmd + Enter on Mac) submits the form
        if(document.activeElement.tagName === 'TEXTAREA') {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                // Special handling for textareas with name "body"
                if (document.activeElement.name === 'body') {
                    event.preventDefault();
                    handleCtrlEnterForBodyTextarea(document.activeElement);
                } else {
                    var form = document.activeElement.closest('form');
                    if (form) {
                        form.submit.click();
                    }
                }
            }
        }
    });

    const votableElements = document.querySelectorAll('.post_teaser, .post_full');
    votableElements.forEach(votable => {
        votable.addEventListener('mouseover', event => {
            currentPost = event.currentTarget;
            if(showCurrentPost) {
                var elementToRemoveClass = document.querySelector('.post_teaser.current_post');
                elementToRemoveClass.classList.remove('current_post');
                currentPost.classList.add('current_post');
            }
        });
        votable.addEventListener('mouseout', event => {
            //currentPost = null;
            if(showCurrentPost) {
                //var elementToRemoveClass = document.querySelector('.post_teaser.current_post');
                //elementToRemoveClass.classList.remove('current_post');
            }
        });
    });
}

function setupTopicChooser() {
    // at /topic/news/submit, clicking on an anchor element needs to save the clicked community id to a hidden field and then submit the form
    var chooseTopicLinks = document.querySelectorAll('a.choose_topic_for_post');
    chooseTopicLinks.forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            var communityIdInput = document.getElementById('community_id');
            var communityForm = document.getElementById('choose_community');

            // Set the value of the hidden input field
            if (communityIdInput) {
                communityIdInput.value = this.getAttribute('data-id');
            }
            if (communityForm) {
                communityForm.submit();
            }
        });
    });
}

function setupConversationChooser() {
    const changeSender = document.getElementById('changeSender');
    if(changeSender) {
        changeSender.addEventListener('change', function() {
            const user_id = changeSender.options[changeSender.selectedIndex].value;
            location.href = '/chat/' + user_id;
        });
    }
}

function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  let result = '';

  if (hours > 0) {
    result += `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }

  if (minutes > 0) {
    if (result !== '') {
      result += ' ';
    }
    result += `${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`;
  }

  if (result === '') {
    result = 'Less than a minute';
  }

  return result;
}

function displayTimeTracked() {
    const timeSpentElement = document.getElementById('timeSpent');
    let timeSpent = parseInt(localStorage.getItem('timeSpent')) || 0;
    if(timeSpentElement && timeSpent) {
        timeSpentElement.textContent = formatTime(timeSpent)
    }
}

function setupMarkdownEditorEnabler() {
    const markdownEnablerLinks = document.querySelectorAll('.markdown_editor_enabler');
    markdownEnablerLinks.forEach(function(link) {
        link.addEventListener('click', function(event) {
            event.preventDefault();
            const dataId = link.dataset.id;
            if(dataId) {
                var downarea = new DownArea({
                    elem: document.querySelector('#' + dataId),
                    resize: DownArea.RESIZE_VERTICAL,
                    hide: ['heading', 'bold-italic'],
                    value: document.getElementById(dataId).value
                });
                setupAutoResize(dataId);
                link.style.display = 'none';
            }
        });
    });
}

function setupAddPollChoice() {
    const addChoiceButton = document.getElementById('addPollChoice');
    const pollChoicesFieldset = document.getElementById('pollChoicesFieldset');
    if(pollChoicesFieldset == null) {
        return;
    }
    const formGroups = pollChoicesFieldset.getElementsByClassName('form-group');

    if(addChoiceButton && addChoiceButton) {
        addChoiceButton.addEventListener('click', function(event) {
            // Loop through the form groups and show the first hidden one
            for (let i = 0; i < formGroups.length; i++) {
                if (formGroups[i].style.display === 'none') {
                    formGroups[i].style.display = 'block';
                    break; // Stop once we've shown the next hidden form group
                }
            }
        });
    }
}

function preventDoubleFormSubmissions() {
    let submitting = false;
    const form = document.querySelector('form');
    if (form) {
      form.addEventListener('submit', function (e) {
          if (submitting) {
            e.preventDefault();
          } else {
            submitting = true;
          }
      });
    }
}

function setupSelectAllCheckbox() {
    const selectAllCheckbox = document.getElementById("select_all");

    if(selectAllCheckbox) {
        selectAllCheckbox.addEventListener("change", function() {
            const checkboxes = document.querySelectorAll("input.can_select_all");
            checkboxes.forEach(cb => {
                cb.checked = selectAllCheckbox.checked;
            });
        });
    }
}

function setupFontSizeChangers() {
    const increaseFontSize = document.getElementById('increase_font_size');
    if(increaseFontSize) {
        document.getElementById('increase_font_size').addEventListener('click', (e) => {
            e.preventDefault();
            let current = getCurrentFontSize();
            current += 0.1;
            applyFontSize(current);
            setCookie('fontSize', current, 100000);
        });
        document.getElementById('decrease_font_size').addEventListener('click', (e) => {
            e.preventDefault();
            let current = getCurrentFontSize();
            current = Math.max(0.5, current - 0.1); // Prevent too small
            applyFontSize(current);
            setCookie('fontSize', current, 100000);
        });
    }
}

function setupAddPassKey() {
    const passkeyButton = document.getElementById('add_passkey_button');
    if(passkeyButton) {
        document.getElementById('add_passkey_button').addEventListener('click', () => {
           const { startRegistration } = SimpleWebAuthnBrowser;
           fetch('/user/passkeys/registration/options')
              .then(response => {
                if (!response.ok) {
                  throw new Error(`Options request failed: ${response.statusText}`);
                }
                return response.json();
              })
              .then(registrationOptionsJSON => {
                // Start WebAuthn registration
                startRegistration({ optionsJSON: registrationOptionsJSON })
                  .then(regResp => {
                    const device = prompt(`Enter a name for this passkey:`);

                    fetch('/user/passkeys/registration/verification', {
                      method: 'POST',
                      headers: {
                        'Content-Type': 'application/json'
                      },
                      body: JSON.stringify({
                        response: regResp,
                        device: device
                      })
                    })
                      .then(response => {
                        if (!response.ok) {
                          throw new Error(`Verification request failed: ${response.statusText}`);
                        }
                        return response.text();
                      })
                      .then(result => {
                        if (result === 'FAILED') {
                          console.log(`Verification request failed.`);
                          alert(`Something went wrong, and we couldn't register the passkey.`);
                        } else {
                          setCookie('passkey', result.trim(), 365);
                          location.href = `/user/passkeys`;
                        }
                      })
                      .catch(error => {
                        alert(error.message);
                        alert(`Something went wrong, and we couldn't register the passkey.`);
                      });
                  })
                  .catch(error => {
                    alert(error.message);
                    alert(`Something went wrong, and we couldn't register the passkey.`);
                  });
              })
              .catch(error => {
                alert(error.message);
                alert(`Something went wrong, and we couldn't register the passkey.`);
              });

        });
    }

    const logInWithPasskey = document.getElementById('log_in_with_passkey');
    if(logInWithPasskey) {
        document.getElementById('log_in_with_passkey').addEventListener('click', async () => {
            const { browserSupportsWebAuthn } = SimpleWebAuthnBrowser;
            let passkeyUsername = getCookie('passkey');
            if(!passkeyUsername) {
                passkeyUsername = document.getElementById('user_name').value;
                if(!passkeyUsername) {
                   passkeyUsername = prompt('What is your user name?');
                }
            }

            const { startAuthentication, browserSupportsWebAuthnAutofill } = SimpleWebAuthnBrowser;
            let redirect = getValueFromQueryString('next');
            // Submit options
            const apiAuthOptsResp = await fetch('/auth/passkeys/login_options', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username: passkeyUsername,
                }),
            });
            const authenticationOptionsJSON = await apiAuthOptsResp.json();

            console.log('AUTHENTICATION OPTIONS');
            console.log(JSON.stringify(authenticationOptionsJSON, null, 2));

            if (authenticationOptionsJSON.error) {
                $.prompt(authenticationOptionsJSON.error);
                return;
            }

            // Start WebAuthn authentication
            const authResp = await startAuthentication({ optionsJSON: authenticationOptionsJSON, useBrowserAutofill: false });

            console.log('AUTHENTICATION RESPONSE');
            console.log(JSON.stringify(authResp, null, 2));

            // Submit response
            const apiAuthVerResp = await fetch('/auth/passkeys/login_verification', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username: passkeyUsername,
                    redirect: redirect,
                    response: authResp,
                }),
            });
            const verificationJSON = await apiAuthVerResp.json()

            if (verificationJSON.verified === true) {
                setCookie('passkey', passkeyUsername, 1000);
                location.href = verificationJSON.redirectTo;
            } else {
                console.log(`Authentication failed: ${verificationJSON.message}`);
                $.prompt(verificationJSON.message);
            }
        });
    }
}

function setupFancySelects() {
    var crossPostCommunity = document.getElementById('which_community');
    if(crossPostCommunity && crossPostCommunity.type === 'select-one') {
        new TomSelect('#which_community', {maxOptions: null, maxItems: 1});
    }

    var communities = document.getElementById('communities');
    if(communities && communities.type === 'select-one') {
        new TomSelect('#communities', {maxOptions: null, maxItems: 1});
    }

    var community = document.getElementById('community');
    if(community && community.type === 'select-one') {
        new TomSelect('#community', {maxOptions: null, maxItems: 1});
    }

    var languageSelect = document.querySelector('#tom_select div #language_id');
    if (languageSelect) {
        new TomSelect('#tom_select #language_id', {maxOptions: null, maxItems: 1});
    }

    var languageSelect2 = document.querySelector('#tom_select div #languages');
    if (languageSelect2) {
        new TomSelect('#tom_select #languages', {maxOptions: null});
    }
}

function setupImagePreview() {
    const input = document.getElementById('image_file');
    const preview = document.getElementById('image_preview');

    if(input) {
        input.addEventListener('change', () => {
            const file = input.files[0];
            if (file) {
                const url = URL.createObjectURL(file);
                preview.src = url;
                preview.style.display = 'block';

                // revoke the object URL later to free memory
                preview.onload = () => URL.revokeObjectURL(url);
            } else {
                preview.src = '';
                preview.style.display = 'none';
            }
        });
    }
}

function setupNotificationPermission() {
    const permissionButton = document.getElementById('enableNotifications');
    if(permissionButton) {
        if(Notification.permission !== "granted") {
            permissionButton.addEventListener('click', () => {
                Notification.requestPermission().then((permission) => {
                  permissionButton.innerText = 'Granted'
                });
            });
        }
        else {
            const enableNotificationWrapper = document.getElementById('enableNotificationWrapper');
            if(enableNotificationWrapper)
                enableNotificationWrapper.style.display = 'none';
        }
    }
}

function setupFederationModeToggle() {
    const federationModeRadios = document.querySelectorAll('input[name="federation_mode"]');
    const allowlistField = document.getElementById('allowlist');
    const blocklistField = document.getElementById('blocklist');
    
    if (federationModeRadios.length === 0 || !allowlistField || !blocklistField) {
        return; // Exit if we're not on the federation page
    }
    
    // Get the form groups containing the textarea fields
    const allowlistGroup = allowlistField.closest('.form-group');
    const blocklistGroup = blocklistField.closest('.form-group');
    
    function toggleFields() {
        const selectedMode = document.querySelector('input[name="federation_mode"]:checked').value;
        
        if (selectedMode === 'allowlist') {
            allowlistGroup.style.display = '';
            blocklistGroup.style.display = 'none';
        } else {
            allowlistGroup.style.display = 'none';
            blocklistGroup.style.display = '';
        }
    }
    
    // Set initial state
    toggleFields();
    
    // Add event listeners to radio buttons
    federationModeRadios.forEach(radio => {
        radio.addEventListener('change', toggleFields);
    });
}

function getCurrentFontSize() {
    const fontSize = getComputedStyle(document.body).fontSize;
    return parseFloat(fontSize) / parseFloat(getComputedStyle(document.documentElement).fontSize);
}

// Apply font size to target elements
function applyFontSize(sizeRem) {
    document.body.style.fontSize = sizeRem + 'rem';
    document.querySelectorAll('.form-control').forEach(el => {
        el.style.fontSize = sizeRem + 'rem';
    });
}


// ------------------- Utilities -------------------


// Retrieve a value from the query string by key
function getValueFromQueryString(key) {
    const queryString = window.location.search;
    const params = new URLSearchParams(queryString);
    return params.get(key);
}

function getCookie(name) {
    var cookies = document.cookie.split(';');

    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();

        if (cookie.indexOf(name + '=') === 0) {
            return decodeURIComponent(cookie.substring(name.length + 1));
        }
    }

    return null;
}

function setCookie(name, value, days) {
    var expires;

    if (days) {
        var date = new Date();
        date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
        expires = "; expires=" + date.toGMTString();
    } else {
        expires = "";
    }
    document.cookie = encodeURIComponent(name) + "=" + encodeURIComponent(value) + expires + "; path=/";
}

function eraseCookie(name) {
    setCookie(name, "", -1);
}

/* register a service worker */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('/service_worker.js', {scope: '/'}).then(function(registration) {
      // Registration was successful
      // console.log('ServiceWorker2 registration successful with scope: ', registration.scope);
    }, function(err) {
      // registration failed :(
      console.log('ServiceWorker registration failed: ', err);
    });
  });
}



// Add PieFed app button to install PWA
let deferredPrompt;

window.addEventListener('beforeinstallprompt', function (e) {
    // Prevent the mini-infobar from appearing on mobile
    e.preventDefault();
    // Stash the event so it can be triggered later.
    deferredPrompt = e;
    document.getElementById('btn_add_home_screen').style.display = 'inline-block';
});

document.getElementById('btn_add_home_screen').addEventListener('click', function () {
    // iOS doesn't support beforeinstallprompt, so show manual instructions
    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
        alert('To add this app to your home screen:\n\n1. Tap the Share button at the bottom of the screen\n2. Select "Add to Home Screen" from the menu\n3. Tap "Add" to confirm');
    } else if (deferredPrompt) {
        // For other browsers that support beforeinstallprompt
        document.getElementById('btn_add_home_screen').style.display = 'none';
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function (choiceResult) {
            if (choiceResult.outcome === 'accepted') {
                console.log('User accepted the A2HS prompt');
            } else {
                console.log('User dismissed the A2HS prompt');
            }
            deferredPrompt = null;
        });
    }
});

function setupMegaMenuNavigation() {
    // Custom dropdown management since Bootstrap's data-bs-toggle gets in the way
    const dropdownToggle = document.querySelector('.nav-link.dropdown-toggle[href="/communities"]');
    const dropdownMenu = document.querySelector('.dropdown-menu.communities_menu');
    
    if (dropdownToggle && dropdownMenu) {
        // Handle dropdown toggle click
        dropdownToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const isVisible = dropdownMenu.style.display === 'block';
            if (isVisible) {
                hideDropdown();
            } else {
                const accountMenu = document.querySelector('.account_menu_parent');
                if(accountMenu) {
                    const accountAnchor = accountMenu.querySelector('a');
                    if(accountAnchor) {
                        accountAnchor.classList.remove('show');
                        accountAnchor.setAttribute('aria-expanded', 'false');
                    }
                    const accountUl = accountMenu.querySelector('ul');
                    if(accountUl) {
                        accountUl.classList.remove('show');
                        accountUl.removeAttribute('data-bs-popper');
                    }
                }
                const adminMenu = document.querySelector('.admin_menu_parent');
                if(adminMenu) {
                    const adminAnchor = adminMenu.querySelector('a');
                    if(adminAnchor) {
                        adminAnchor.classList.remove('show');
                        adminAnchor.setAttribute('aria-expanded', 'false');
                    }
                    const adminUl = adminMenu.querySelector('ul');
                    if(adminUl) {
                        adminUl.classList.remove('show');
                        adminUl.removeAttribute('data-bs-popper');
                    }
                }
                showDropdown();
            }
        });
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            if (!dropdownToggle.contains(e.target) && !dropdownMenu.contains(e.target)) {
                hideDropdown();
            }
        });

    }
    
    function showDropdown() {
        dropdownMenu.classList.add('show');
        dropdownMenu.style.setProperty('display', 'block', 'important');
        dropdownToggle.setAttribute('aria-expanded', 'true');
        dropdownToggle.parentElement.classList.add('show');
    }
    
    function hideDropdown() {
        dropdownMenu.classList.remove('show');
        dropdownMenu.style.setProperty('display', 'none', 'important');
        dropdownToggle.setAttribute('aria-expanded', 'false');
        dropdownToggle.parentElement.classList.remove('show');
    }
}

function setupPopupCommunitySidebar() {
    const dialog = document.getElementById('communitySidebar');

    document.querySelectorAll('.showPopupCommunitySidebar').forEach(anchor => {
        anchor.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();

            const communityId = this.getAttribute('data-id');

            if (communityId && dialog) {
                fetch(`/community/get_sidebar/${communityId}`)
                    .then(response => response.text())
                    .then(html => {
                        dialog.innerHTML = `
                            <div style="position: relative;">
                                <button id="closeCommunitySidebar" style="position: absolute; top: -10px; right: 0; background: none; border: none; font-size: 24px; cursor: pointer; z-index: 1000;" aria-label="Close">&times;</button>
                                ${html}
                            </div>
                        `;

                        const closeButton = dialog.querySelector('#closeCommunitySidebar');
                        if (closeButton) {
                            closeButton.addEventListener('click', function() {
                                dialog.close();
                            });
                        }

                        dialog.showModal();
                    })
                    .catch(error => {
                        console.error('Error fetching community sidebar:', error);
                    });
            }
        });
    });

    if (dialog) {
        dialog.addEventListener('click', function(event) {
            if (event.target === dialog) {
                dialog.close();
            }
        });
    }
}

function setupVideoSpoilers() {
    const videosBlurred = document.querySelectorAll('.responsive-video.blur');

    videosBlurred.forEach(function(vid) {
        vid.addEventListener('play', function(playing) {
            vid.classList.remove("blur");
        });
        vid.addEventListener('pause', function(paused) {
            vid.classList.add("blur");
        });
    });
}

// Setup MutationObserver to detect dynamically loaded content (e.g., from htmx)
function setupDynamicContentObserver() {
    const observer = new MutationObserver(function(mutations) {
        let shouldResetup = false;
        
        mutations.forEach(function(mutation) {
            // Check if new nodes were added
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                mutation.addedNodes.forEach(function(node) {
                    // Only process element nodes (not text nodes)
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        // Check if the added content contains elements that need event handlers
                        if (node.querySelector && (
                            node.querySelector('.send_post') ||
                            node.querySelector('.confirm_first') ||
                            node.querySelector('.showElement') ||
                            node.querySelector('.show-more') ||
                            node.querySelector('.user_preview') ||
                            node.classList.contains('send_post') ||
                            node.classList.contains('confirm_first') ||
                            node.classList.contains('showElement')
                        )) {
                            shouldResetup = true;
                        }
                    }
                });
            }
        });
        
        // Re-run setup functions for the new content
        if (shouldResetup) {
            setupDynamicContent();
        }
    });
    
    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

// handle Ctrl+Enter for comment textareas
function handleCtrlEnterForBodyTextarea(textarea) {
    // First try to find btn-primary within the same form
    const form = textarea.closest('form');
    if (form) {
        const btnPrimary = form.querySelector('.btn-primary');
        if (btnPrimary) {
            btnPrimary.click();
            return;
        }
    }

    // If no form or no btn-primary in form, search in the parent container
    let container = textarea.parentElement;
    while (container && container !== document.body) {
        const btnPrimary = container.querySelector('.btn-primary');
        if (btnPrimary) {
            btnPrimary.click();
            return;
        }
        container = container.parentElement;
    }
}

// Re-run specific setup functions for dynamically loaded content
function setupDynamicContent() {
    // These are the key functions needed for post options and other dynamic content
    setupConfirmFirst();
    setupSendPost();
    setupShowElementLinks();
    setupShowMoreLinks();
    setupUserPopup();
    setupVotingLongPress();
    setupDynamicKeyboardShortcuts();
}

// Setup keyboard shortcuts for dynamically loaded content
function setupDynamicKeyboardShortcuts() {
    // Add event listeners to any new textarea elements with name "body"
    document.querySelectorAll('textarea[name="body"]').forEach(textarea => {
        // Remove existing listener to avoid duplicates
        textarea.removeEventListener('keydown', handleDynamicCtrlEnter);
        // Add new listener
        textarea.addEventListener('keydown', handleDynamicCtrlEnter);
    });
}

// Handler for dynamic textarea keydown events
function handleDynamicCtrlEnter(event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && event.target.name === 'body') {
        event.preventDefault();
        handleCtrlEnterForBodyTextarea(event.target);
    }
}

// Community filter (search box)
function setupCommunityFilter() {
    // Try and hookup the filter first (in case HTMX already loaded)
    hookupCommunityFilter();

    // HTMX event listeners for dynamic content loading
    document.addEventListener('htmx:afterSwap', function(event) {
        // Check if the swapped content contains the communities menu
        if (event.target.classList && event.target.classList.contains('communities_menu')) {
            hookupCommunityFilter();
        }
        
        // Also check if the swapped content is inside the communities menu
        const communitiesMenu = event.target.closest('.communities_menu');
        if (communitiesMenu) {
            hookupCommunityFilter();
        }
    });

    document.addEventListener('htmx:afterSettle', function(event) {
        // Double-check after settle in case afterSwap missed it
        if (event.target.classList && event.target.classList.contains('communities_menu')) {
            hookupCommunityFilter();
        }
    });
}

function hookupCommunityFilter() {
    // Set up community filter functionality for the communities dropdown
    const filterInput = document.getElementById('community-filter');
    const clearButton = document.getElementById('clear-community-filter');

    if (!filterInput) {
        return; // Only run if filter element exists in current theme
    }
    
    const communityItems = document.querySelectorAll('.community-item');
    const communitySections = document.querySelectorAll('.community-section');

    function prevSection(communityItem) {
        let current = communityItem.previousElementSibling;
        
        while (current) {
            if (current.classList.contains('community-section')) {
                return current;
            }
            current = current.previousElementSibling;
        }
        
        return null; // No section found
    }

    function filterCommunities() {
        const filterText = filterInput.value.toLowerCase().trim();
        
        let visibleInSection = {};
        
        // Show/hide clear button
        if (clearButton) {
            clearButton.style.display = filterText ? 'block' : 'none';
        }
        
        communityItems.forEach((item, index) => {
            const communityName = item.getAttribute('data-community-name') || '';
            const isVisible = !filterText || communityName.includes(filterText);
            
            item.style.display = isVisible ? 'list-item' : 'none';
            
            // Track which sections have visible items
            if (isVisible) {
                const parentSection = prevSection(item);
                if (parentSection) {
                    const sectionType = parentSection.getAttribute('data-community-section');
                    if (sectionType) {
                        visibleInSection[sectionType] = true;
                    }
                }
            }
        });
        
        // Show/hide section headers based on whether they have visible items
        communitySections.forEach((section, index) => {
            let shouldShow = false;
            
            const sectionType = section.getAttribute('data-community-section');
            if (sectionType) {
                shouldShow = visibleInSection[sectionType];
            }
            
            section.style.display = shouldShow ? 'list-item' : 'none';
        });
    }
    
    function clearFilter() {
        filterInput.value = '';
        filterCommunities();
        filterInput.focus();
    }
    
    // Event listeners
    filterInput.addEventListener('input', filterCommunities);
    filterInput.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            clearFilter();
        }
    });
    
    if (clearButton) {
        clearButton.addEventListener('click', clearFilter);
    }
    
    // Focus the input when the dropdown becomes visible
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.type === 'childList' && mutation.target.classList.contains('communities_menu')) {
                // Check if the filter input is now in the DOM and visible
                const currentFilter = document.getElementById('community-filter');
                if (currentFilter && currentFilter.offsetParent !== null) {
                    setTimeout(() => currentFilter.focus(), 100);
                }
            }
        });
    });
    
    // Observe the communities menu for changes (HTMX loading)
    const communitiesMenu = document.querySelector('.communities_menu');
    if (communitiesMenu) {
        observer.observe(communitiesMenu, { childList: true, subtree: true });
    }
}

function checkLanguage(languageSelect, warningDiv, recipientLanguage) {
    if (typeof languageSelect === 'string') {
        languageSelect = document.querySelector(languageSelect);
    }

    if (typeof warningDiv === 'string') {
        warningDiv = document.querySelector(warningDiv);
    }

    if (warningDiv === undefined) {
        warnignDiv = languageSelect.getAttribute('data-warning-div-id');
    }

    if (recipientLanguage === undefined && languageSelect) {
        recipientLanguage = languageSelect.getAttribute('data-recipient-language');
    }


    if (recipientLanguage && languageSelect.value !== recipientLanguage) {
        warningDiv.classList.remove('d-none');
    } else {
        warningDiv.classList.add('d-none');
    }
}

function addLanguageCheck(languageSelect, warningDiv, recipientLanguage) {
    if (typeof languageSelect === 'string') {
        languageSelect = document.querySelector(languageSelect);
    }

    if (typeof warningDiv === 'string') {
        warningDiv = document.querySelector(warningDiv);
    }

    if (warningDiv === undefined && languageSelect) {
        warningDiv = document.getElementById(languageSelect.getAttribute('data-warning-div-id'));
    }

    if (recipientLanguage === undefined && languageSelect) {
        recipientLanguage = languageSelect.getAttribute('data-recipient-language');
    }

    console.log(languageSelect, warningDiv, recipientLanguage);
    

    if (languageSelect && warningDiv) {
        // Initial check
        checkLanguage(languageSelect, warningDiv, recipientLanguage);

        // Add event listener for changes
        languageSelect.addEventListener('change', function () {
            console.log('languageSelect change');
            checkLanguage(languageSelect, warningDiv, recipientLanguage);
        });

        return languageSelect;
    }
}
function setupVotingLongPress() {
    const votingElements = document.querySelectorAll('.voting_buttons_new');

    votingElements.forEach(element => {
        let longPressTimer;
        let isLongPress = false;
        let touchStartX = 0;
        let touchStartY = 0;
        let hasMoved = false;

        // Mouse events
        element.addEventListener('mousedown', function(event) {
            isLongPress = false;
            longPressTimer = setTimeout(() => {
                isLongPress = true;
                openVotingDialog(element);
            }, 2000); // 2 seconds
        });

        element.addEventListener('mouseup', function(event) {
            clearTimeout(longPressTimer);
        });

        element.addEventListener('mouseleave', function(event) {
            clearTimeout(longPressTimer);
        });

        // Touch events for mobile
        element.addEventListener('touchstart', function(event) {
            isLongPress = false;
            hasMoved = false;
            touchStartX = event.touches[0].clientX;
            touchStartY = event.touches[0].clientY;
            longPressTimer = setTimeout(() => {
                if (!hasMoved) {
                    isLongPress = true;
                    openVotingDialog(element);
                }
            }, 2000); // 2 seconds
        });

        element.addEventListener('touchmove', function(event) {
            if (!hasMoved) {
                const touch = event.touches[0];
                const deltaX = Math.abs(touch.clientX - touchStartX);
                const deltaY = Math.abs(touch.clientY - touchStartY);
                
                // If the user has moved more than 10 pixels in any direction, consider it scrolling
                if (deltaX > 10 || deltaY > 10) {
                    hasMoved = true;
                    clearTimeout(longPressTimer);
                }
            }
        });

        element.addEventListener('touchend', function(event) {
            clearTimeout(longPressTimer);
        });

        element.addEventListener('touchcancel', function(event) {
            clearTimeout(longPressTimer);
        });

        // Prevent normal click if it was a long press
        element.addEventListener('click', function(event) {
            if (isLongPress) {
                event.preventDefault();
                event.stopPropagation();
            }
        });
    });
}

function openVotingDialog(votingElement) {
    const dialog = document.getElementById('voting_dialog');
    if (!dialog) return;

    // Get the base URL from the voting element
    const baseUrl = votingElement.getAttribute('data-base-url');
    if (!baseUrl) {
        console.error('No data-base-url found on voting element');
        return;
    }

    // Store the base URL and reference to original voting element on the dialog
    dialog.dataset.currentBaseUrl = baseUrl;
    dialog.originalVotingElement = votingElement;

    // Get position of triggering element
    const rect = votingElement.getBoundingClientRect();

    // Show the dialog first to get its dimensions
    dialog.showModal();

    // Now get the dialog dimensions and position it
    const dialogRect = dialog.getBoundingClientRect();

    // Calculate position - center dialog over the voting element
    const left = rect.left + (rect.width / 2) - (dialogRect.width / 2);
    const top = rect.top + (rect.height / 2) - (dialogRect.height / 2);

    // Keep dialog within viewport bounds
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    const finalLeft = Math.max(10, Math.min(left, viewportWidth - dialogRect.width - 10));
    const finalTop = Math.max(10, Math.min(top, viewportHeight - dialogRect.height - 10));

    // Apply positioning
    dialog.style.position = 'fixed';
    dialog.style.left = finalLeft + 'px';
    dialog.style.top = finalTop + 'px';
    dialog.style.margin = '0';
}

function setupVotingDialogHandlers() {
    const dialog = document.getElementById('voting_dialog');
    if (!dialog || dialog.dataset.handlersAttached) return;

    // Mark that handlers are attached to prevent duplicates
    dialog.dataset.handlersAttached = 'true';

    // Close button functionality
    const closeButton = dialog.querySelector('#voting_dialog_close');
    if (closeButton) {
        closeButton.addEventListener('click', function() {
            dialog.close();
        });
    }

    // Voting button event handlers using HTMX JS API
    const votingButtons = [
        { id: '#voting_dialog_upvote_public', path: '/upvote/public' },
        { id: '#voting_dialog_upvote_private', path: '/upvote/private' },
        { id: '#voting_dialog_downvote_private', path: '/downvote/private' },
        { id: '#voting_dialog_downvote_public', path: '/downvote/public' }
    ];

    votingButtons.forEach(buttonConfig => {
        const button = dialog.querySelector(buttonConfig.id);
        if (button) {
            button.addEventListener('click', function() {
                const baseUrl = dialog.dataset.currentBaseUrl;
                const originalVotingElement = dialog.originalVotingElement;

                if (!baseUrl) {
                    console.error('No base URL available for voting');
                    return;
                }

                if (!originalVotingElement) {
                    console.error('No original voting element available for swap');
                    return;
                }

                const url = baseUrl + buttonConfig.path;
                console.log('Making HTMX request to:', url);

                // Use HTMX JavaScript API to make the request
                htmx.ajax('POST', url, {
                    source: button,
                    target: originalVotingElement,
                    swap: 'innerHTML',
                    headers: {
                        'HX-Request': 'true'
                    }
                }).then(() => {
                    console.log('Vote request completed');
                    dialog.close();
                }).catch((error) => {
                    console.error('Vote request failed:', error);
                    dialog.close();
                });
            });
        }
    });

    // Close on backdrop click
    dialog.addEventListener('click', function(event) {
        if (event.target === dialog) {
            dialog.close();
        }
    });
}

function setupPopupTooltips() {
    // Find all elements with a title, add the necessary bootstrap attributes
    document.querySelectorAll('[title]').forEach(el => {
      if (!el.hasAttribute('data-bs-toggle')) {     // don't mess with dropdowns that use data-bs-toggle
        el.setAttribute('data-bs-toggle', 'tooltip');
        el.setAttribute('data-bs-placement', 'top');
      }
    });

    // Initialize tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    [...tooltipTriggerList].map(el =>
      new bootstrap.Tooltip(el, {
          delay: { show: 750, hide: 200 }
      })
    );
}
