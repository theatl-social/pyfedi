const url = new URL(window.location.href);
const baseUrl = `${url.protocol}//${url.host}`;
const api = baseUrl + '/api/alpha/site'

fetch(api)
  .then(response => response.json())
  .then(data => {
        // navbar
        document.querySelector('#head-title').textContent = data.site.name
        document.querySelector('#navbar-title').innerHTML = '<img src="' + data.site.icon + '" alt="Logo" width="36" height="36" />' + ' ' + data.site.name

        // site info
        document.querySelector('#site_version').textContent = data.version
        document.querySelector('#site_actor_id').textContent = data.site.actor_id
        document.querySelector('#site_description').textContent = data.site.description
        document.querySelector('#site_enable_downvotes').textContent = data.site.enable_downvotes
        document.querySelector('#site_icon').textContent = data.site.icon
        document.querySelector('#site_name').textContent = data.site.name
        document.querySelector('#site_sidebar').textContent = data.site.sidebar
        document.querySelector('#site_user_count').textContent = data.site.user_count

        let lang_names = data.site.all_languages[0].name;
        let lang_count = data.site.all_languages.length;

        for (let i = 1; i < lang_count; i++) {
          lang_names += ", " + data.site.all_languages[i].name;
        }

        document.querySelector('#site_all_languages').textContent = lang_names
  })
