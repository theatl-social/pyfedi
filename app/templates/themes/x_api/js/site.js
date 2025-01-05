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

const navbar = document.getElementById('navbar_items');
if (jwt != null) {
  var request = {method: "GET", headers: {Authorization: `Bearer ${jwt}`}};
} else {
  var request = {method: "GET"};
  navbar.innerHTML =  '<li class="nav-item"><a class="nav-link" href="/api/alpha/auth/login">Log in (via API)</a></li>' +
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

        if (jwt != null) {
          const all_communities_item = document.createElement('li');
          all_communities_item.innerHTML = '<a class="dropdown-item" href="/api/alpha/communities">All communities</a>'

          const communities_menu = document.createElement('ul');
          communities_menu.className = 'dropdown-menu'
          communities_menu.appendChild(all_communities_item)

          if (data.my_user.moderates.length > 0) {
            const dropdown_divider = document.createElement('li');
            dropdown_divider.innerHTML = '<hr class="dropdown-divider">'
            communities_menu.appendChild(dropdown_divider)
            const dropdown_header = document.createElement('li');
            dropdown_header.innerHTML = '<h6 class="dropdown-header">Moderating</h6>'
            communities_menu.appendChild(dropdown_header)

            for (let mods of data.my_user.moderates) {
              let moderated_community_item = document.createElement('li');
              if (mods.community.local) {
                moderated_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/c/' + mods.community.name + '">' +
                                                        mods.community.title + '<span class="text-body-secondary">' + ' (' + mods.community.ap_domain + ')</span>' +
                                                      '</a>'
              } else {
                moderated_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/c/' + mods.community.name + '@' + mods.community.ap_domain + '">' +
                                                        mods.community.title + '<span class="text-body-secondary">' + ' (' + mods.community.ap_domain + ')</span>' +
                                                      '</a>'
              }
              communities_menu.appendChild(moderated_community_item)
            }
          }

          if (data.my_user.follows.length > 0) {
            const dropdown_divider = document.createElement('li');
            dropdown_divider.innerHTML = '<hr class="dropdown-divider">'
            communities_menu.appendChild(dropdown_divider)
            const dropdown_header = document.createElement('li');
            dropdown_header.innerHTML = '<h6 class="dropdown-header">Joined Communities</h6>'
            communities_menu.appendChild(dropdown_header)

            for (let follows of data.my_user.follows) {
              let followed_community_item = document.createElement('li');
              if (follows.community.local) {
                followed_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/c/' + follows.community.name + '">' +
                                                        follows.community.title + '<span class="text-body-secondary">' + ' (' + follows.community.ap_domain + ')</span>' +
                                                      '</a>'
              } else {
                followed_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/c/' + follows.community.name + '@' + follows.community.ap_domain + '">' +
                                                        follows.community.title + '<span class="text-body-secondary">' + ' (' + follows.community.ap_domain + ')</span>' +
                                                      '</a>'
              }
              communities_menu.appendChild(followed_community_item)
            }
          }

          const communities_item = document.createElement('li')
          communities_item.className = 'nav-item dropdown'
          communities_item.innerHTML = '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">Communities</a>'
          communities_item.appendChild(communities_menu)
          navbar.appendChild(communities_item)



          /*const login_item = document.createElement('li')
          login_item.className = 'nav-item'
          login_item.innerHTML = '<a class="nav-link" href="/api/alpha/auth/login">Log in (via API)</a>'
          ul.appendChild(login_item)

          const communities_dropdown = document.createElement('li')
          communities_dropdown.className =  'nav-item dropdown'
          communities_dropdown.innerHTML =  '<a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">' +
                                              'Communities' +
                                            '</a>'
            const communities_dropdown_ul = document.createElement('ul')
            communities_dropdown_ul.className = 'dropdown-menu'
              const communities_dropdown_ul_item = document.createElement('li')
              communities_dropdown_ul_item.className = 'dropdown-item'
              communities_dropdown_ul_item.href = '/api/alpha/communities'
              communities_dropdown_ul.appendChild(communities_dropdown_ul_item)
            communities_dropdown.appendChild(communities_dropdown_ul)
          ul.appendChild(communities_dropdown)*/
        }

        // site info
        document.querySelector('#site_json').textContent = JSON.stringify(data, null, 2);
  })

