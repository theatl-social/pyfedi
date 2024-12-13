const url = new URL(window.location.href);
export const baseUrl = `${url.protocol}//${url.host}`;
const api = baseUrl + '/api/alpha/site';

let jwt = null;
let session_jwt = sessionStorage.getItem('jwt');
if (session_jwt != null) {
  jwt = session_jwt;
} else {
  let local_jwt = localStorage.getItem('jwt');
  if (local_jwt != null) {
    jwt = local_jwt;
  }
}
export { jwt };

const ul = document.getElementById('navbar_items');
if (jwt != null) {
  var request = {method: "GET", headers: {Authorization: `Bearer ${jwt}`}};
  ul.innerHTML = '<li class="nav-item dropdown">' +
                    '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">' +
                      'Communities' +
                    '</a>' +
                    '<ul class="dropdown-menu">' +
                      '<li><a class="dropdown-item" href="/api/alpha/communities">All communities</a></li>' +
                    '</ul>' +
                  '</li>' +

                  '<li class="nav-item"><a class="nav-link" href="/user/settings">User settings</a></li>' +

                  '<li class="nav-item"><a class="nav-link" href="/donate">Donate</a></li>' +

                  '<li class="nav-item"><a class="nav-link" href="/api/alpha/auth/logout">Logout (via API)</a></li>';
} else {
  var request = {method: "GET"};
  ul.innerHTML = '<li class="nav-item"><a class="nav-link" href="/api/alpha/auth/login">Log in (via API)</a></li>' +
                 '<li class="nav-item dropdown">' +
                    '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">' +
                      'Communities' +
                    '</a>' +
                    '<ul class="dropdown-menu">' +
                      '<li><a class="dropdown-item" href="/api/alpha/communities">All communities</a></li>' +
                    '</ul>' +
                  '</li>' +
                 '<li class="nav-item"><a class="nav-link" href="/user/settings">User settings</a></li>' +
                 '<li class="nav-item"><a class="nav-link" href="/donate">Donate</a></li>';
}

fetch(api, request)
  .then(response => response.json())
  .then(data => {
        // head
        document.querySelector('#head_title').textContent = data.site.name;
        document.querySelector('#icon_152').href = data.site.icon_152;
        document.querySelector('#icon_32').href = data.site.icon_32;
        document.querySelector('#icon_16').href = data.site.icon_16;
        document.querySelector('#icon_shortcut').href = data.site.icon_32;
        document.querySelector('#favicon').href = baseUrl + '/static/images/favicon.ico';

        // navbar
        document.querySelector('#navbar_title').innerHTML = '<img src="' + data.site.icon + '" alt="Logo" width="36" height="36" />' + ' ' + data.site.name;

        // site info
        document.querySelector('#site_json').textContent = JSON.stringify(data, null, 2);
  })

