/**
 * The operator's session: one signed cookie, no store.
 *
 * ADR-0002 settled that there is one operator and no tenancy, so there is
 * nothing to look a session *up* in — no users table, no session table, no auth
 * provider. What is left is proving that whoever holds this cookie typed the
 * password at some point, and that is a signature over an expiry.
 *
 * The API key is a different thing and stays where it is. It guards FastAPI
 * from anything that reaches it directly and never enters a browser
 * (`proxy.ts`). This guards the *web app*, which until now was open to anyone
 * who found the URL — and which holds the key, so an open UI handed out the
 * API too.
 *
 * Web Crypto rather than `node:crypto`, because `proxy.ts` runs on the Edge
 * runtime where `node:crypto` is not available. The same code then works in the
 * route handlers, which run on Node.
 */

export const SESSION_COOKIE = "fb_agent_session";

/** Thirty days. Long, because there is one operator and a re-login costs them
 *  a trip to a password manager for a credential nothing else uses. */
export const SESSION_MAX_AGE = 60 * 60 * 24 * 30;

function secret(): string {
  return process.env.AUTH_SECRET ?? "";
}

async function key(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * `<expires-at>.<signature>`.
 *
 * The expiry is inside the signed payload as well as on the cookie, so an
 * operator editing `Max-Age` in devtools does not extend anything — the server
 * reads the value, not the browser's opinion of it.
 */
export async function issueSession(now: number = Date.now()): Promise<string> {
  const expires = String(now + SESSION_MAX_AGE * 1000);
  const signature = await crypto.subtle.sign(
    "HMAC",
    await key(),
    new TextEncoder().encode(expires),
  );
  return `${expires}.${hex(signature)}`;
}

export async function isValidSession(
  token: string | undefined,
  now: number = Date.now(),
): Promise<boolean> {
  // A blank `AUTH_SECRET` must not produce a *valid* signature that anyone
  // could reproduce by also having no secret. Deny instead, the same direction
  // `settings.api_key` takes: a misconfigured deploy that comes up open looks
  // exactly like a working one.
  if (!secret() || !token) return false;

  const [expires, signature] = token.split(".");
  if (!expires || !signature) return false;

  const expected = await crypto.subtle.verify(
    "HMAC",
    await key(),
    Uint8Array.from(
      signature.match(/.{1,2}/g)?.map((byte) => parseInt(byte, 16)) ?? [],
    ),
    new TextEncoder().encode(expires),
  );
  if (!expected) return false;

  return Number(expires) > now;
}

/**
 * Constant-time string comparison.
 *
 * `===` on a secret leaks its length and its matching prefix through timing.
 * The window is small over a network and the credential is one operator's, but
 * this is four lines.
 */
export function matches(given: string, expected: string): boolean {
  if (!expected) return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  let diff = a.length ^ b.length;
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    diff |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return diff === 0;
}
