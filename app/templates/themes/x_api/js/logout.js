localStorage.removeItem('jwt');
sessionStorage.removeItem('jwt');

const url = new URL(window.location.href);
const baseUrl = `${url.protocol}//${url.host}`;
window.location.href = baseUrl;
