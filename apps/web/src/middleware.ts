import { NextResponse, type NextRequest } from "next/server";

// Redirección temprana a /login si no hay cookie de sesión. La validación real la hace la API.
export function middleware(req: NextRequest) {
  if (!req.cookies.get("d8_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(req.nextUrl.pathname + req.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!api|login|_next|favicon.ico).*)"] };
