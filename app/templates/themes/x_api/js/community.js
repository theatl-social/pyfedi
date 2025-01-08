const element = document.getElementById('community_request');
const community_id = element.getAttribute('data-value');

import { baseUrl } from './site.js';
const community_api = baseUrl + '/api/alpha/community?id=' + community_id;
const community_post_list_api = baseUrl + '/api/alpha/post/list?sort=Hot&page=1&community_id=' + community_id;

import { jwt } from './site.js';
if (jwt != null) {
  var request = {method: "GET", headers: {Authorization: `Bearer ${jwt}`}};
} else {
  var request = {method: "GET"};
}

fetch(community_api, request)
  .then(response => response.json())
  .then(data => {
        document.querySelector('#community_json').textContent = JSON.stringify(data, null, 2);
  })


fetch(community_post_list_api, request)
  .then(response => response.json())
  .then(data => {
        document.querySelector('#community_post_list_json').textContent = JSON.stringify(data, null, 2);
  })
