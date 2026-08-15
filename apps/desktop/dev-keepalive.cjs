// Keep-alive for Tauri's beforeDevCommand.
// The Vite dev server is started/stopped manually (external to `tauri dev`) so that
// tauri's rebuild/restart cycle never kills the frontend process (which made
// tauri dev exit with "beforeDevCommand terminated with a non-zero status code").
setInterval(() => {}, 1000);
