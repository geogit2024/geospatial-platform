import { NextRequest, NextResponse } from "next/server";

// Read at request time (runtime), not baked in at build time
const API_URL = process.env.API_URL || "http://localhost:8000";

async function proxy(
  req: NextRequest,
  params: { path: string[] },
  method: string
): Promise<NextResponse> {
  const path = params.path.join("/");
  const search = req.nextUrl.searchParams.toString();
  const url = `${API_URL}/api/${path}${search ? "?" + search : ""}`;

  const init: RequestInit = { method };

  if (method !== "GET" && method !== "DELETE") {
    const body = await req.text();
    if (body) {
      init.body = body;
      init.headers = { "Content-Type": "application/json" };
    }
  }

  const upstream = await fetch(url, init);

  if (upstream.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params, "GET");
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params, "POST");
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params, "DELETE");
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params, "PUT");
}
