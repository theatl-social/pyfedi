import { baseUrl } from './site.js';
const  api = baseUrl + '/api/alpha/community/list';

import { jwt } from './site.js';
if (jwt != null) {
  var request = {method: "GET", headers: {Authorization: `Bearer ${jwt}`}};
} else {
  var request = {method: "GET"};
}

fetch(api, request)
  .then(response => response.json())
  .then(data => {
        document.querySelector('#community_list_json').textContent = JSON.stringify(data, null, 2);
  })
