document.querySelector('#login_json').textContent = '{"username_or_email": "", "password": ""}'

const login_form = document.getElementById('login_form');
const username = document.getElementById('username');
const password = document.getElementById('password');
const remember_me = document.getElementById('remember_me');

login_form.addEventListener('submit', async event => {
  event.preventDefault();

  json_string = JSON.stringify({ username_or_email: username.value, password: password.value })

  const url = new URL(window.location.href);
  const baseUrl = `${url.protocol}//${url.host}`;
  const api = baseUrl + '/api/alpha/user/login';

  try {
    const response = await fetch(api, {method: 'POST', body: json_string});
    if (!response.ok) {
      throw new Error(`Response status: ${response.status}`);
    }

    const response_json = await response.json();

    if (remember_me.checked == true) {
      localStorage.setItem('jwt', response_json['jwt']);
    } else {
      sessionStorage.setItem('jwt', response_json['jwt']);
    }

    window.location.href = baseUrl;

  } catch (error) {
    console.error(error.message);
  }
});


