// Proxy hacia la API FastAPI: misma origen para la cookie de sesión (httpOnly) y sin CORS.
// API_URL se lee al arrancar, no en el build.
const API = process.env.API_URL ?? "http://127.0.0.1:8000";
const FORWARD = ["content-type", "cookie", "x-d8-client", "user-agent"];

export const dynamic = "force-dynamic";

async function proxy(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${API}/${path.map(encodeURIComponent).join("/")}${new URL(req.url).search}`;
  const headers: Record<string, string> = {};
  for (const name of FORWARD) {
    const value = req.headers.get(name);
    if (value) headers[name] = value;
  }
  try {
    const res = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
    const out = new Headers();
    for (const name of ["content-type", "content-disposition", "x-content-sha256", "x-content-type-options", "cache-control"]) {
      const value = res.headers.get(name);
      if (value) out.set(name, value);
    }
    for (const cookie of res.headers.getSetCookie()) out.append("set-cookie", cookie);
    return new Response(res.status === 204 ? null : res.body, { status: res.status, headers: out });
  } catch {
    return Response.json(
      { code: "api_unavailable", message: "La API no responde. Arráncala con scripts/start-api.ps1." },
      { status: 502 },
    );
  }
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
