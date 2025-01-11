(function () {
  function hideFieldsetContent(fieldset, options) {
    const content = fieldset.querySelectorAll('*:not(legend)');
    if (options.animation) {
      content.forEach((element) => {
        element.style.display = 'none';
      });
    } else {
      content.forEach((element) => {
        element.style.display = 'none';
      });
    }
    fieldset.classList.remove('expanded');
    fieldset.classList.add('collapsed');
    content.forEach((element) => {
      element.setAttribute('aria-expanded', 'false');
    });
    if (!options.animation) {
      fieldset.dispatchEvent(new Event('update'));
    }
    setCookie(`fieldset_${fieldset.id}_state`, 'collapsed', 365);
  }

  function showFieldsetContent(fieldset, options) {
    const content = fieldset.querySelectorAll('*:not(legend)');
    if (options.animation) {
      content.forEach((element) => {
        element.style.display = '';
      });
    } else {
      content.forEach((element) => {
        element.style.display = '';
      });
    }
    fieldset.classList.remove('collapsed');
    fieldset.classList.add('expanded');
    content.forEach((element) => {
      element.setAttribute('aria-expanded', 'true');
    });
    if (!options.animation) {
      fieldset.dispatchEvent(new Event('update'));
    }
    setCookie(`fieldset_${fieldset.id}_state`, 'expanded', 365);
  }

  function doToggle(fieldset, setting) {
    if (fieldset.classList.contains('collapsed')) {
      showFieldsetContent(fieldset, setting);
      setCookie(`fieldset_${fieldset.id}_state`, 'expanded', 365);
    } else if (fieldset.classList.contains('expanded')) {
      hideFieldsetContent(fieldset, setting);
      setCookie(`fieldset_${fieldset.id}_state`, 'collapsed', 365);
    }
  }

  function coolfieldset(selector, options) {
    const fieldsets = document.querySelectorAll(selector);
    const setting = { collapsed: false, animation: true, speed: 'medium', ...options };

    fieldsets.forEach((fieldset) => {
      const legend = fieldset.querySelector('legend');

      if (setting.collapsed) {
        hideFieldsetContent(fieldset, { animation: false });
      } else {
        fieldset.classList.add('expanded');
      }

      legend.addEventListener('click', () => doToggle(fieldset, setting));
    });
  }

  window.coolfieldset = coolfieldset;
})();

// Usage:
// coolfieldset('.coolfieldset', { collapsed: true, animation: true, speed: 'slow' });

document.addEventListener('DOMContentLoaded', function () {
  coolfieldset('.coolfieldset.collapsed', { collapsed: true, animation: true, speed: 'slow' });
  coolfieldset('.coolfieldset:not(.collapsed)', { collapsed: false, animation: true, speed: 'slow' });
});
