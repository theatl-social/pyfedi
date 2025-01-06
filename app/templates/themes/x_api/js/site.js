const url = new URL(window.location.href);
export const baseUrl = `${url.protocol}//${url.host}`;
const api_site = baseUrl + '/api/alpha/site';

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

fetch(api_site, request)
  .then(response => response.json())
  .then(data => {
        // head
        document.querySelector('#head_title').textContent = data.site.name;
        document.querySelector('#icon_152').href = data.site.icon_152;
        document.querySelector('#icon_32').href = data.site.icon_32;
        document.querySelector('#icon_16').href = data.site.icon_16;
        document.querySelector('#icon_shortcut').href = data.site.icon_32;

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
                moderated_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/api/alpha/c/' + mods.community.name + '">' +
                                                        mods.community.title + '<span class="text-body-secondary">' + ' (' + mods.community.ap_domain + ')</span>' +
                                                      '</a>'
              } else {
                moderated_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/api/alpha/c/' + mods.community.name + '@' + mods.community.ap_domain + '">' +
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
                followed_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/api/alpha/c/' + follows.community.name + '">' +
                                                        follows.community.title + '<span class="text-body-secondary">' + ' (' + follows.community.ap_domain + ')</span>' +
                                                      '</a>'
              } else {
                followed_community_item.innerHTML =  '<a class="dropdown-item" href="' + baseUrl + '/api/alpha/c/' + follows.community.name + '@' + follows.community.ap_domain + '">' +
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

          const user_settings_item = document.createElement('li')
          user_settings_item.className = 'nav-item'
          user_settings_item.innerHTML = '<a class="nav-link" href="/user/settings">User settings</a>';
          navbar.appendChild(user_settings_item)

          const logout_item = document.createElement('li')
          logout_item.className = 'nav-item'
          logout_item.innerHTML = '<a class="nav-link" href="/api/alpha/auth/logout">Log out (via API)</a>';
          navbar.appendChild(logout_item)
        }

        // site info
        let postlist = document.querySelector('#post_list_request')
        if (jwt != null) {
          document.querySelector('#site_request').innerHTML = 'GET <code>/api/alpha/site</code> [LOGGED IN]'
          if (postlist) {
            postlist.innerHTML = 'GET <code>/api/alpha/post/list?type_=Subscribed&sort=New&page=1</code></p>'
          }
        } else {
          document.querySelector('#site_request').innerHTML = 'GET <code>/api/alpha/site</code> [LOGGED OUT]'
          if (postlist) {
            postlist.innerHTML = 'GET <code>/api/alpha/post/list?type_=Popular&sort=Hot&page=1</code></p>'
          }
        }

        document.querySelector('#site_json').textContent = JSON.stringify(data, null, 2);
  })


let postlist = document.querySelector('#post_list_request');
if (postlist) {
  if (jwt != null) {
    var api_postlist = baseUrl + '/api/alpha/post/list?type_=Subscribed&sort=New&page=1';
  } else {
    var api_postlist = baseUrl + '/api/alpha/post/list?type_=Popular&sort=Hot&page=1';
  }

  fetch(api_postlist, request)
    .then(response => response.json())
    .then(data => {
      document.querySelector('#post_list_json').textContent = JSON.stringify(data, null, 2);
  })
}
