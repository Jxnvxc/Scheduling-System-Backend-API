(() => {
  const apiUrlMeta = document.querySelector('meta[name="smartshift-api-url"]');
  const defaultApiUrl =
    window.location.protocol === "file:"
      ? "http://127.0.0.1:8000"
      : `${window.location.protocol}//${window.location.hostname}:8000`;

  window.SMARTSHIFT_API_URL = (
    apiUrlMeta?.content || defaultApiUrl
  ).replace(/\/+$/, "");
})();
