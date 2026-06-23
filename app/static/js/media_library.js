/**
 * Media library functionality
 *
 * Basic usage:
 * const mediaLibrary = new MediaLibrary({
 *     dialogId: 'insertImageDialog',
 *     dialogCloseId: 'insert_image_dialog_close',
 *     triggerLinkId: 'insertImage',
 *     loadContainerId: 'loadImagesHere',
 *     targetTextareaId: 'body',
 *     uploadInputId: 'imageUploadInput',
 *     uploadButtonId: 'imageUploadButton',
 *     uploadStatusId: 'uploadStatus',
 *     translations: {
 *         loading: 'Loading...',
 *         noImages: 'No images found.',
 *         errorLoading: 'Error loading images.',
 *         insert: 'Insert',
 *         more: 'More',
 *         delete: 'Delete',
 *         confirmDelete: 'Are you sure you want to delete this image?',
 *         deleteError: 'Failed to delete image. Please try again.',
 *         selectFile: 'Please select a file.',
 *         selectImage: 'Please select an image file.',
 *         uploading: 'Uploading...',
 *         uploadSuccess: 'Upload successful!',
 *         uploadError: 'Upload failed. Please try again.',
 *         pasteUploadError: 'Failed to upload pasted image. Please try again.'
 *     }
 * });
 *
 * To override DownArea markdown editor's image button:
 * mediaLibrary.overrideDownAreaImageButton('#body');
 */

class MediaLibrary {
    static activeInstance = null;

    constructor(options) {
        this.dialog = document.getElementById(options.dialogId);
        this.triggerLink = document.getElementById(options.triggerLinkId);
        this.dialogClose = document.getElementById(options.dialogCloseId);
        this.loadContainer = document.getElementById(options.loadContainerId);
        this.targetTextarea = document.getElementById(options.targetTextareaId);
        this.uploadInput = document.getElementById(options.uploadInputId);
        this.uploadButton = document.getElementById(options.uploadButtonId);
        this.uploadStatus = document.getElementById(options.uploadStatusId);

        this.translations = options.translations || {};
        this.needsRefresh = false;

        this.init();
    }

    init() {
        this.setupDialogHandlers();
        this.setupUploadHandlers();
        this.setupPasteHandler();
    }

    /**
     * Override DownArea markdown editor's image button to use media library
     * Call this method after DownArea is initialized
     * @param {string} textareaSelector - CSS selector for the textarea (e.g., '#body' or '#textarea_in_reply_to_123')
     * @param {number} delay - Delay in ms to wait for DownArea initialization (default: 100)
     */
    overrideDownAreaImageButton(textareaSelector, delay = 100) {
        // DownArea initializes asynchronously and independently of MediaLibrary,
        // so a single fixed-delay lookup races against the editor being ready.
        // On a heavier page (e.g. a post with many comment editors) the toolbar
        // can take well over `delay` ms to appear; when the lookup missed, the
        // toolbar image button kept DownArea's default handler and inserted an
        // empty "![](https://)" placeholder instead of opening the media library.
        // Poll up to ~5s so the override attaches reliably regardless of timing.
        const maxAttempts = 50;

        const findImageButton = () => {
            if (textareaSelector) {
                const textarea = document.querySelector(textareaSelector);
                if (textarea && textarea.parentNode && textarea.parentNode.parentNode) {
                    return textarea.parentNode.parentNode.querySelector('.downarea-toolbar-tool[data-action="image"]');
                }
                return null;
            }
            return document.querySelector('.downarea-toolbar-tool[data-action="image"]');
        };

        const attach = (attempt) => {
            const imageButton = findImageButton();

            if (imageButton) {
                // Idempotency guard: don't re-bind if we've already overridden it.
                if (imageButton.dataset.mediaLibraryBound === '1') return;

                // Remove the default click handler by cloning the element.
                const newImageButton = imageButton.cloneNode(true);
                newImageButton.dataset.mediaLibraryBound = '1';
                imageButton.parentNode.replaceChild(newImageButton, imageButton);

                // Open the media library dialog instead of inserting a placeholder.
                newImageButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (this.triggerLink) {
                        this.triggerLink.click();
                    }
                });
                return;
            }

            if (attempt < maxAttempts) {
                setTimeout(() => attach(attempt + 1), delay);
            }
        };

        setTimeout(() => attach(1), delay);
    }

    setupDialogHandlers() {
        if (!this.triggerLink || !this.dialog) return;

        // Open dialog
        this.triggerLink.addEventListener('click', (e) => {
            e.preventDefault();

            // Set this instance as active
            MediaLibrary.activeInstance = this;

            // Load images if not already loaded or if refresh needed
            if (this.loadContainer.children.length === 0 || this.needsRefresh) {
                this.loadImageThumbnails();
                this.needsRefresh = false;
            }

            this.dialog.showModal();
        });

        // Close button
        if (this.dialogClose) {
            this.dialogClose.addEventListener('click', () => {
                this.dialog.close();
            });
        }

        // Close on backdrop click
        this.dialog.addEventListener('click', (e) => {
            const rect = this.dialog.getBoundingClientRect();
            const isInDialog = (rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
                               rect.left <= e.clientX && e.clientX <= rect.left + rect.width);
            if (!isInDialog) {
                this.dialog.close();
            }
        });
    }

    /**
     * Map an API error code (the `message` field returned by the alpha API's
     * shared_error_handler) to a human-friendly, actionable message.
     * Falls back to the generic uploadError translation for unknown codes.
     */
    friendlyUploadError(code) {
        const t = this.translations || {};
        const map = {
            'quota_exceeded': t.quotaExceeded || 'Storage quota exceeded. Delete some images from your media library below to free up space, then try again.',
            'incorrect_login': t.loginRequired || 'You must be logged in to upload images.',
            'filetype not allowed': t.filetypeNotAllowed || 'That file type is not allowed.',
            'file not uploaded': t.selectFile || 'Please select a file.',
        };
        return map[code] || t.uploadError || 'Upload failed. Please try again.';
    }

    /**
     * Read the JSON error body from a failed upload response and throw an Error
     * whose message is the API error code, so .catch() can surface the reason.
     */
    throwUploadError(response) {
        return response.json()
            .catch(() => ({}))
            .then(data => { throw new Error((data && data.message) || 'upload_failed'); });
    }

    setupUploadHandlers() {
        if (!this.uploadButton) return;

        this.uploadButton.addEventListener('click', () => {
            const file = this.uploadInput.files[0];
            if (!file) {
                this.uploadStatus.innerHTML = `<p class="text-warning small">${this.translations.selectFile}</p>`;
                return;
            }

            // Validate file type
            if (!file.type.startsWith('image/')) {
                this.uploadStatus.innerHTML = `<p class="text-danger small">${this.translations.selectImage}</p>`;
                return;
            }

            // Show uploading status
            this.uploadStatus.innerHTML = `<p class="text-info small">${this.translations.uploading}</p>`;
            this.uploadButton.disabled = true;

            // Create FormData and upload
            const formData = new FormData();
            formData.append('file', file);

            fetch('/api/alpha/upload/image', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (!response.ok) {
                    return this.throwUploadError(response);
                }
                return response.json();
            })
            .then(data => {
                this.uploadStatus.innerHTML = `<p class="text-success small">${this.translations.uploadSuccess}</p>`;
                this.uploadInput.value = '';
                this.uploadButton.disabled = false;

                // Reload the image grid after a short delay to allow R2 to propagate
                setTimeout(() => {
                    this.loadImageThumbnails();
                }, 1000);

                // Clear upload status after 3 seconds
                setTimeout(() => {
                    this.uploadStatus.innerHTML = '';
                }, 3000);
            })
            .catch(error => {
                console.error('Upload error:', error);
                // friendlyUploadError only matches error.message against a fixed
                // map and returns controlled strings, so nothing untrusted reaches innerHTML.
                this.uploadStatus.innerHTML = `<p class="text-danger small">${this.friendlyUploadError(error.message)}</p>`;
                this.uploadButton.disabled = false;
            });
        });
    }

    setupPasteHandler() {
        if (!this.targetTextarea) return;

        this.targetTextarea.addEventListener('paste', (e) => {
            const items = e.clipboardData.items;

            for (let i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image') !== -1) {
                    e.preventDefault();

                    const file = items[i].getAsFile();
                    const cursorPos = this.targetTextarea.selectionStart;

                    // Insert placeholder text
                    const placeholder = '\n[Uploading image...]\n';
                    const textBefore = this.targetTextarea.value.substring(0, cursorPos);
                    const textAfter = this.targetTextarea.value.substring(cursorPos);
                    this.targetTextarea.value = textBefore + placeholder + textAfter;

                    // Upload the image
                    const formData = new FormData();
                    formData.append('file', file);

                    fetch('/api/alpha/upload/image', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => {
                        if (!response.ok) {
                            return this.throwUploadError(response);
                        }
                        return response.json();
                    })
                    .then(data => {
                        // Replace placeholder with actual markdown
                        const markdown = '\n![image](' + data.url + ')\n';
                        this.targetTextarea.value = this.targetTextarea.value.replace(placeholder, markdown);

                        // Set cursor after the inserted markdown
                        const newCursorPos = cursorPos + markdown.length;
                        this.targetTextarea.focus();
                        this.targetTextarea.setSelectionRange(newCursorPos, newCursorPos);

                        // Mark that media library needs refresh
                        this.needsRefresh = true;
                    })
                    .catch(error => {
                        console.error('Paste upload error:', error);
                        // Replace placeholder with error message
                        this.targetTextarea.value = this.targetTextarea.value.replace(placeholder, '\n[Image upload failed]\n');
                        // Surface the actual reason (e.g. quota exceeded) instead of a generic message.
                        alert(this.friendlyUploadError(error.message));
                    });

                    break;
                }
            }
        });
    }

    loadImageThumbnails() {
        this.loadContainer.innerHTML = `<p class="text-center">${this.translations.loading}</p>`;

        fetch('/api/alpha/user/media?limit=50')
            .then(response => response.json())
            .then(data => {
                this.loadContainer.innerHTML = '';

                if (data.media && data.media.length > 0) {
                    const grid = document.createElement('div');
                    grid.className = 'd-grid gap-2';
                    grid.style.gridTemplateColumns = 'repeat(auto-fill, minmax(150px, 1fr))';

                    data.media.forEach((image) => {
                        const imgWrapper = this.createImageThumbnail(image);
                        grid.appendChild(imgWrapper);
                    });

                    this.loadContainer.appendChild(grid);
                } else {
                    this.loadContainer.innerHTML = `<p class="text-center text-muted">${this.translations.noImages}</p>`;
                }
            })
            .catch(error => {
                console.error('Error loading media:', error);
                this.loadContainer.innerHTML = `<p class="text-center text-danger">${this.translations.errorLoading}</p>`;
            });
    }

    createImageThumbnail(image) {
        const imgWrapper = document.createElement('div');
        imgWrapper.style.position = 'relative';
        imgWrapper.style.cursor = 'pointer';
        imgWrapper.style.aspectRatio = '1';
        imgWrapper.style.overflow = 'hidden';
        imgWrapper.style.borderRadius = '8px';
        imgWrapper.style.border = '2px solid transparent';
        imgWrapper.style.transition = 'border-color 0.2s';

        const img = document.createElement('img');
        img.src = image.url;
        img.alt = image.name;
        img.style.width = '100%';
        img.style.height = '100%';
        img.style.objectFit = 'cover';

        // Retry loading if image fails (for R2 propagation delays)
        let retryCount = 0;
        img.onerror = function() {
            if (retryCount < 3) {
                retryCount++;
                setTimeout(function() {
                    img.src = image.url + '?retry=' + retryCount;
                }, retryCount * 500); // 500ms, 1s, 1.5s
            }
        };

        imgWrapper.appendChild(img);

        // Create overlay with action buttons
        const overlay = this.createOverlay(image);
        imgWrapper.appendChild(overlay);

        // Show overlay on click
        imgWrapper.addEventListener('click', (e) => {
            // Hide all other overlays
            document.querySelectorAll(`#${this.loadContainer.id} .d-grid > div > div[style*="position: absolute"]`).forEach((el) => {
                el.style.display = 'none';
            });
            // Show this overlay
            overlay.style.display = 'flex';
        });

        // Hover effect
        imgWrapper.addEventListener('mouseenter', () => {
            if (overlay.style.display !== 'flex') {
                imgWrapper.style.borderColor = '#0d6efd';
            }
        });
        imgWrapper.addEventListener('mouseleave', () => {
            imgWrapper.style.borderColor = 'transparent';
        });

        return imgWrapper;
    }

    createOverlay(image) {
        const overlay = document.createElement('div');
        overlay.style.position = 'absolute';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100%';
        overlay.style.height = '100%';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        overlay.style.display = 'none';
        overlay.style.flexDirection = 'column';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
        overlay.style.gap = '10px';
        overlay.style.padding = '10px';

        // Insert button
        const insertBtn = document.createElement('button');
        insertBtn.className = 'btn btn-primary btn-sm';
        insertBtn.textContent = this.translations.insert;
        insertBtn.style.width = '80%';
        insertBtn.onclick = (e) => {
            e.stopPropagation();
            this.insertImage(image);
        };

        // More button with dropdown
        const moreContainer = this.createMoreDropdown(image);

        overlay.appendChild(insertBtn);
        overlay.appendChild(moreContainer);

        return overlay;
    }

    createMoreDropdown(image) {
        const moreContainer = document.createElement('div');
        moreContainer.className = 'dropdown';
        moreContainer.style.width = '80%';

        const moreBtn = document.createElement('button');
        moreBtn.className = 'btn btn-secondary btn-sm dropdown-toggle w-100';
        moreBtn.textContent = this.translations.more;
        moreBtn.setAttribute('data-bs-toggle', 'dropdown');
        moreBtn.onclick = (e) => {
            e.stopPropagation();
        };

        const dropdownMenu = document.createElement('ul');
        dropdownMenu.className = 'dropdown-menu';

        // Delete option
        const deleteItem = document.createElement('li');
        const deleteLink = document.createElement('a');
        deleteLink.className = 'dropdown-item text-danger';
        deleteLink.href = '#';
        deleteLink.textContent = this.translations.delete;
        deleteLink.onclick = (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.deleteImage(image);
        };
        deleteItem.appendChild(deleteLink);

        dropdownMenu.appendChild(deleteItem);

        moreContainer.appendChild(moreBtn);
        moreContainer.appendChild(dropdownMenu);

        return moreContainer;
    }

    insertImage(image) {
        // Use the active instance's textarea
        const activeInstance = MediaLibrary.activeInstance || this;
        if (!activeInstance.targetTextarea) return;

        const cursorPos = activeInstance.targetTextarea.selectionStart;
        const textBefore = activeInstance.targetTextarea.value.substring(0, cursorPos);
        const textAfter = activeInstance.targetTextarea.value.substring(cursorPos);

        // Don't add leading newline if textarea is empty or cursor is at start
        const leadingNewline = (textBefore.trim().length === 0) ? '' : '\n';
        // Don't add trailing newline if at end of empty textarea
        const trailingNewline = (textAfter.trim().length === 0 && textBefore.trim().length === 0) ? '' : '\n';

        const markdown = leadingNewline + '![' + image.name + '](' + image.url + ')' + trailingNewline;

        activeInstance.targetTextarea.value = textBefore + markdown + textAfter;

        this.dialog.close();

        // Set focus and cursor position after dialog closes
        setTimeout(() => {
            activeInstance.targetTextarea.focus();
            activeInstance.targetTextarea.setSelectionRange(cursorPos + markdown.length, cursorPos + markdown.length);
        }, 0);
    }

    deleteImage(image) {
        if (!confirm(this.translations.confirmDelete)) {
            return;
        }

        fetch('/api/alpha/image/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ file: image.url })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Delete failed');
            }
            return response.json();
        })
        .then(data => {
            // Reload the image grid to show the updated list
            this.loadImageThumbnails();
        })
        .catch(error => {
            console.error('Delete error:', error);
            alert(this.translations.deleteError);
        });
    }
}
