/**
 * Where the workspace finds the API.
 *
 * 8787 is the API's own default, and the comment on it says so: it is what the
 * phone and the web workspace expect locally. Carrying a different number here
 * meant every request the browser made was proxied to a port nothing listened
 * on, and sign-in failed with a server error that named no cause.
 */
export const DEFAULT_API_PORT = 8787;

export const API_ORIGIN =
  process.env.SP_API_ORIGIN ??
  `http://127.0.0.1:${process.env.SP_API_PORT ?? DEFAULT_API_PORT}`;
